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
VIMENSIMEPATH = vim.eval('expand("<sfile>:p:h")')
__ensime_omniresult = None
sys.path.append(VIMENSIMEPATH)
EOF
let g:__ensime_vim = expand("<sfile>")
execute "pyfile ".fnameescape(fnamemodify(expand("<sfile>"), ":p:h")."/sexpr.py")
execute "pyfile ".fnameescape(fnamemodify(expand("<sfile>"), ":p:h")."/ensime.py")

python << EOF
# All global Python variables are defined here.
class Printer(object):

    def out(self, arg):
        vim.command('echom "ensime: %s"' % arg)
    def err(self, arg):
        vim.command('echohl Error | echom "ensime: %s"' % arg)

def cursor_offset():
    return vim.eval("""LocationOfCursor()""")

def filename():
    return vim.eval("""fnameescape(expand("%:p"))""")

ensimeclient = None
printer = Printer()

EOF

function! EnsimeResource()
  call EnsimeStop()
  execute "pyfile ".fnameescape(fnamemodify(g:__ensime_vim, ":p:h")."/sexpr.py")
  execute "pyfile ".fnameescape(fnamemodify(g:__ensime_vim, ":p:h")."/ensime.py")
  call EnsimeStart()
endfunction

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

"""
""" Vim interface to Ensime
"""

function! TypecheckFile()
call setqflist([])
py ensimeclient.typecheck(filename())
endfunction

function! TypeAtPoint()
py ensimeclient.type_at_point(filename(), cursor_offset())
endfunction

function! CompletionAtPoint()
py print ensimeclient.completions(filename(), cursor_offset())
endfunction

function! ScalaOmniCompletion(findstart, base)
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
completions = [x['name'] for x in result['completions']]
vim.command("return %s" % completions)
EOF
  endif
endfunction

set omnifunc=ScalaOmniCompletion
