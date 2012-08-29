Ensime + vim integration
========================

Implemented features:

  - typecheck current file (:EnsimeTypecheckFile)

  - typecheck all files in project (:EnsimeTypecheckAll)

  - autocompletion (via omnicompletion -- <C-x> <C-o>)

  - type at point (:EnsimeTypeAtPoint)

Installation:

  - make sure you have scala-mode for vim installed so you get filetype plugins
    works for Scala code

  - git clone repo into pathogen managed bundles dir or install manually

  - run `sbt stage` to produce a build of ensime server

  - `ln -s dist_2.9.2 dist` in ensime dir

Usage:

  - setup mappings for common actions:

    autocmd FileType scala nnoremap <F5> :EnsimeTypecheckFile<CR>
    autocmd FileType scala nnoremap <leader>, :EnsimeTypeAtPoint<CR>

  - initialize ensime with `:Ensime` vim command
