""" ensime client"""

import os
import select
import socket
import subprocess
import tempfile
import threading
import sexpr

__all__ = ('Client',)

class Client(object):

    def __init__(self,printer):
        self.ensimeproc = None
        self.ensimeport = None
        self.ensime_sock = None
        self.used_ids    = set()
        self.lock       = threading.Lock()
        self.poller     = None
        self.DEVNULL    = None #open("/dev/null", "w")
        self.printer    = printer
        self.started    = False
        self.shutdown   = False
        self.ENSIMESERVER = "bin/server"
        self.ENSIMEWD     = os.getenv("ENSIMEHOME")

    class SocketPoller(threading.Thread):

        def __init__(self, enclosing):
            self.enclosing  = enclosing
            self.ensime_sock = enclosing.ensime_sock
            self.printer    = enclosing.printer
            threading.Thread.__init__(self)

        def run(self):
            while not self.enclosing.shutdown:
                readable = []
                while readable == []:
                    # Should always be very fast...
                    readable,writable,errors = select.select([self.ensime_sock], [], [], 60)
                s = readable[0]
                msg_len = ""
                while len(msg_len) < 6:
                    chunk = self.ensime_sock.recv(6-len(msg_len))
                    if chunk == "":
                        raise RuntimeError("socket connection broken (read)")
                    msg_len = msg_len + chunk
                msg_len = int("0x" + msg_len, 16)
                msg = ""
                while len(msg) < msg_len:
                    chunk = self.ensime_sock.recv(msg_len-len(msg))
                    if chunk == "":
                        raise RuntimeError("socket connection broken (read)")
                    msg = msg + chunk
                parsed = sexpr.parse(msg)
                self.printer.out(parsed)

    def fresh_msg_id(self):
        with self.lock:
            i = 1
            while i in self.used_ids:
                i += 1
            self.used_ids.add(i)
        return i

    def free_msg_id(self, i):
        with self.lock:
            self.used_ids.remove(i)
        return

    def get_ensime_dir(self,cwd,depth=0):
        # What an ugly hack. Unfortunately, there seems to be no way
        # to check whether you have reached / in the parent chain...
        if depth > 100:
            return None
        path = os.path.abspath(cwd)
        if not os.path.isdir(path):
            raise RuntimeError("%s is not a directory" % path)
        if ".ensime" in os.listdir(path):
            return path
        parent = os.path.join(path, os.path.pardir)
        if os.access(parent, os.R_OK) and os.access(parent, os.X_OK):
            return self.get_ensime_dir(parent,depth+1)
        else:
            return None

    def connect(self,cwd):
        if self.shutdown:
            raise RuntimeError("cannot reconnect client once it has been disconnected")
        if self.started:
            raise RuntimeError("client already running")
        if self.ENSIMEWD is None:
            raise RuntimeError("environment variable ENSIMEHOME is not set")
        ensime_dir = self.get_ensime_dir(cwd)
        if ensime_dir is None:
            raise RuntimeError("could not find '.ensime' file in any parent directory")
        tfname = tempfile.NamedTemporaryFile(prefix="ensimeportinfo",delete=False).name
        self.ensimeproc = subprocess.Popen([self.ENSIMESERVER, tfname],
                cwd=self.ENSIMEWD, stdin=None, stdout=self.DEVNULL,
                stderr=self.DEVNULL, shell=False, env=None)
        self.printer.out("waiting for port number...")
        ok = False

        while not ok:
            fh = open(tfname, 'r')
            line = fh.readline()
            if line != "":
                ok = True
                self.ensimeport = int(line.strip())
            fh.close()
        self.started = True
        self.printer.out("port number is %d." % self.ensimeport)
        self.ensime_sock = socket.socket(
            socket.AF_INET, socket.SOCK_STREAM)
        self.ensime_sock.connect(("127.0.0.1", self.ensimeport))
        self.ensime_sock.setblocking(0)
        self.poller = self.SocketPoller(self)
        self.poller.start()
        self.swank_send("""(swank:init-project (:root-dir "%s"))""" % ensime_dir)
        return

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
        return

    def sock_write(self, text):
        writable = []
        while writable == []:
            # Should always be very fast...
            readable,writable,errors = select.select([], [self.ensime_sock], [], 60)
        s = writable[0]
        total_sent = 0
        text_len = len(text)
        while total_sent < text_len:
            sent = self.ensime_sock.send(text[total_sent:])
            if sent == 0:
                raise RuntimeError("socket connection broken (write)")
            total_sent += sent
        return

    def __del__(self):
        self.disconnect()
