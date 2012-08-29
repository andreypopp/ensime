""" ensime client"""

import vim
import os
import select
import socket
import subprocess
import tempfile
import threading
import sexpr
import time

__all__ = ('Client', 'get_ensime_dir')

def get_ensime_dir(cwd):
    """ Return closest dir form ``cwd`` with .ensime file in it"""
    if not os.path.isdir(cwd):
        cwd = os.path.dirname(cwd)
    path = os.path.abspath(cwd)
    if not os.path.isdir(path):
        raise RuntimeError("%s is not a directory" % path)
    if os.path.exists(os.path.join(path, ".ensime")):
        return path
    par = os.path.dirname(path)
    if par == path:
        return None
    if os.access(par, os.R_OK) and os.access(par, os.X_OK):
        return get_ensime_dir(par)
    else:
        return None

class SocketPoller(threading.Thread):
    """ Thread which reads data from socket"""

    def __init__(self, enclosing):
        self.enclosing  = enclosing
        self.ensime_sock = enclosing.ensime_sock
        self.printer    = enclosing.printer
        threading.Thread.__init__(self)

    def read_length(self):
        msg_len = ""
        while len(msg_len) < 6:
            chunk = self.ensime_sock.recv(6 - len(msg_len))
            if chunk == "":
                raise RuntimeError("socket connection broken (read)")
            msg_len = msg_len + chunk

        return int(msg_len, 16)

    def read_msg(self, msg_len):
        msg = u""
        while len(msg) < msg_len:
            chunk = self.ensime_sock.recv(msg_len - len(msg))
            if chunk == "":
                raise RuntimeError("socket connection broken (read)")
            msg = msg + chunk.decode('utf-8')
        return msg

    def run(self):
        while not self.enclosing.shutdown:
            try:
                msg_len = self.read_length()
                msg = self.read_msg(msg_len)
                parsed = sexpr.parse(msg)
                # dispatch to handler or just print unhandled
                if not self.enclosing.on(parsed):
                    self.printer.out(parsed)
            except Exception as e:
                self.printer.err('exception in reader thread: %s' % e)

def ensime_home():
    result = os.getenv("ENSIMEHOME")
    if not result:
        cwd = os.path.dirname(__file__)
        result = os.path.join(cwd, '..', '..', 'dist')
    return result

class Client(object):

    ENSIMESERVER = "bin/server"
    ENSIMEWD = ensime_home()

    def __init__(self, printer):
        self.ensimeproc = None
        self.ensimeport = None
        self.ensime_sock = None
        self.last_message_id = 1
        self.lock = threading.Lock()
        self.waiting_lock = threading.Lock()
        self.poller = None
        self.DEVNULL = open("/dev/null", "w")
        self.printer = printer
        self.started = False
        self.shutdown  = False

        # mapping from message id to event or result of RPC,
        # oh... we need futures for that
        self.waiting = {}

    def on(self, message):
        if message[0] == ":scala-notes":
            return self.on_scala_notes(message)

        elif message[0] in (
                ":compiler-ready",
                ":full-typecheck-finished",
                ":indexer-ready"):
            return self.on_message(message[0][1:].replace("-", " "))

        elif message[0] == ":background-message":
            if message[1] in (105,):
                return self.on_message(message[2])

        elif message[0] == ":return":
            num = message[2]
            with self.waiting_lock:
                if num in self.waiting:
                    ev = self.waiting.pop(num)
                    self.waiting[num] = message[1]
                    ev.set()
                    return True

    def on_scala_notes(self, message):
        notes = message[1][3]
        for note in notes:
            note = sexpr.to_mapping(note)
            if note.get('severity') == 'error':
                command = 'caddexpr "%(file)s:%(line)s:%(col)s:%(msg)s"' % note
                try:
                    vim.command(command)
                except vim.error as e:
                    self.printer.err(e)
        return True

    def on_message(self, msg):
        self.printer.out(msg)
        return True

    def fresh_msg_id(self):
        with self.lock:
            self.last_message_id += 1
            return self.last_message_id

    def connect(self,cwd):
        if self.shutdown:
            raise RuntimeError(
                "cannot reconnect client once it has been disconnected")
        if self.started:
            raise RuntimeError("client already running")
        if self.ENSIMEWD is None:
            raise RuntimeError("environment variable ENSIMEHOME is not set")
        ensime_dir = get_ensime_dir(cwd)
        if ensime_dir is None:
            raise RuntimeError(
                "could not find '.ensime' file in any parent directory")
        tfname = tempfile.NamedTemporaryFile(
            prefix="ensimeportinfo",delete=False).name
        self.ensimeproc = subprocess.Popen([self.ENSIMESERVER, tfname],
                cwd=self.ENSIMEWD, stdin=None, stdout=self.DEVNULL,
                stderr=self.DEVNULL, shell=False, env=None)
        self.printer.out("waiting for port number...")

        while True:
            with open(tfname, 'r') as fh:
                line = fh.readline()
                if line != '':
                    self.ensimeport = int(line.strip())
                    break
                time.sleep(1)

        self.started = True
        self.printer.out("port number is %d." % self.ensimeport)
        self.ensime_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.ensime_sock.connect(("127.0.0.1", self.ensimeport))
        self.poller = SocketPoller(self)
        self.poller.start()
        self.swank_send('(swank:init-project (:root-dir "%s"))' % ensime_dir)

    def disconnect(self):
        # stops the polling thread
        self.printer.out("disconnecting...")
        self.shutdown = True
        self.swank_send("(swank:shutdown-server)")
        self.printer.out("disconnected")
        if self.ensimeproc is not None:
            self.ensimeproc.kill()
        self.ensimeport = None

    def swank_send(self, message):
        if self.ensime_sock != None:
            m_id = self.fresh_msg_id()
            full_msg = "(:swank-rpc %s %d)" % (message, m_id)
            msg_len = len(full_msg)
            as_hex = hex(msg_len)[2:]
            as_hex_padded = (6-len(as_hex))*"0" + as_hex
            self.sock_write(as_hex_padded + full_msg)
        return m_id

    def sock_write(self, text):
        self.ensime_sock.sendall(text)

    def typecheck(self, filename):
        self.swank_send('(swank:typecheck-file "%s")' % filename)

    def typecheck_all(self):
        self.swank_send('(swank:typecheck-all)')

    def type_at_point(self, filename, offset):
        self.swank_send('(swank:type-at-point "%s" %s)' % (filename, offset))

    def completions(self, filename, offset):
        with self.waiting_lock:
            event = threading.Event()
            m_id = self.swank_send(
                '(swank:completions "%s" %s 0 t)' % (filename, offset))
            self.waiting[m_id] = event

        if not event.wait(5):
            self.printer.err("timeout on completion")
        else:
            with self.waiting_lock:
                data = self.waiting.pop(m_id)
            if data[0] == ":ok":
                result = sexpr.to_mapping(data[1])
                result.setdefault('completions', [])
                result['completions'] = [
                    sexpr.to_mapping(x) for x in result['completions']]
                return result
            else:
                self.printer.err(data)

    def __del__(self):
        self.disconnect()
