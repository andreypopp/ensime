if !has('python')
    echo "Error: +python support is required."
    finish
endif

function! LocationOfCursor()
    let pos = col('.') -1
    let line = getline('.')
    let bc = strpart(line,0,pos)
    let ac = strpart(line, pos, len(line)-pos)
    let col = getpos('.')[2]
    let linesTillC = getline(1, line('.')-1)+[getline('.')[:(col-1)]]
    return len(join(linesTillC,"\n"))
endfunction

" Assuming the Python files are in the same directory as this ensime.vim, this
" should load them correctly.
python << EOF
import vim, sys

# Where this script is located, and hopefully the Python scripts too.
VIMENSIMEPATH = vim.eval("""expand("<sfile>:p:h")""")
sys.path.append(VIMENSIMEPATH)
EOF
execute "pyfile ".fnameescape(fnamemodify(expand("<sfile>"), ":p:h")."/sexpr.py")
execute "pyfile ".fnameescape(fnamemodify(expand("<sfile>"), ":p:h")."/ensime.py")

python << EOF
# All global Python variables are defined here.
class Printer(object):

    def out(self, arg):
        vim.command('echom "ensime: %s"' % arg)
    def err(self, arg):
        vim.command('echohl Error | echom "ensime: %s"' % arg)

def cursorOffset():
    return vim.eval("""LocationOfCursor()""")

def fullFileName():
    return vim.eval("""fnameescape(expand("%:p"))""")

ensimeclient = None
printer = Printer()

EOF

function! EnsimeStart()
python << EOF
if ensimeclient is not None:
    printer.err("ensime instance already runned")
else:
    try:
        currentfiledir = vim.eval("expand('%:p:h')")
        ensimeclient = Client(printer)
        ensimeclient.connect(currentfiledir)
    except RuntimeError as msg:
        printer.err(msg)
EOF
autocmd VimLeavePre * call EnsimeStop()
return
endfunction

function! EnsimeStop()
python << EOF
try:
    if ensimeclient is not None:
        ensimeclient.disconnect()
        ensimeclient = None
    else:
        printer.err("no instance running")
except (ValueError, RuntimeError) as msg:
    printer.err(msg)
EOF
return
endfunction

function! TypecheckFile()
python << EOF
ensimeclient.swank_send("""(swank:typecheck-file "%s")""" % fullFileName())
EOF
endfunction

function! TypeAtPoint()
python << EOF
ensimeclient.swank_send("""(swank:type-at-point "%s" %d)""" % (fullFileName(), int(cursorOffset())))
EOF
endfunction
