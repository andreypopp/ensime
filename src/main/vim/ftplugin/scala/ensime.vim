if !has('python')
  echo "Error: +python support is required."
  finish
endif

python << EOF
import vim, sys

# Where this script is located, and hopefully the Python scripts too.
VIMENSIMEPATH = vim.eval('expand("<sfile>:p:h")')
__ensime_omniresult = None
sys.path.append(VIMENSIMEPATH)

from ensime import Client

class Printer(object):

    def out(self, arg):
        vim.command('echom "ensime: %s"' % arg)
    def err(self, arg):
        vim.command('echohl Error | echom "ensime: %s"' % arg)

def cursor_offset():
    return vim.eval("""LocationOfCursor()""")

def filename():
    return vim.eval("""fnameescape(expand("%:p"))""")

def ensime_start():
    global ensimeclient
    if ensimeclient is not None:
        printer.err("ensime instance already runned")
    else:
        try:
            currentfiledir = vim.eval("expand('%:p:h')")
            ensimeclient = Client(printer)
            ensimeclient.connect(currentfiledir)
        except RuntimeError as msg:
            printer.err(msg)

def ensime_stop():
    global ensimeclient
    try:
        if ensimeclient is not None:
            ensimeclient.disconnect()
            ensimeclient = None
        else:
            printer.err("no instance running")
    except (ValueError, RuntimeError) as msg:
        printer.err(msg)

ensimeclient = None
printer = Printer()
EOF

function! LocationOfCursor()
  let pos = col('.') -1
  let line = getline('.')
  let bc = strpart(line,0,pos)
  let ac = strpart(line, pos, len(line)-pos)
  let col = getpos('.')[2]
  let linesTillC = getline(1, line('.')-1)+[getline('.')[:(col-1)]]
  return len(join(linesTillC,"\n"))
endfunction

function! EnsimeStart()
  py ensime_start()
  autocmd VimLeavePre * call EnsimeStop()
  return
endfunction

function! EnsimeStop()
  py ensime_stop()
  return
endfunction

function! EnsimeTypecheckFile()
call setqflist([])
py ensimeclient.typecheck(filename())
endfunction

function! EnsimeTypeAtPoint()
py ensimeclient.type_at_point(filename(), cursor_offset())
endfunction

function! EnsimeOmniCompletion(findstart, base)
  if a:findstart
py << EOF
vim.command("w")
result = ensimeclient.completions(filename(), cursor_offset())
if not result:
  vim.command("return -1")
else:
  __ensime_omniresult = result
  position = int(vim.eval("col('.')")) - len(result['prefix']) - 1
  vim.command("return %d" % position)
EOF
  else
py << EOF
result = __ensime_omniresult
completions = [{
    'word': x['name'].encode('utf8'),
    'menu': x['type-sig'].encode('utf8'),
  } for x in result['completions']]
vim.command("return %s" % completions)
EOF
  endif
endfunction

set omnifunc=EnsimeOmniCompletion
