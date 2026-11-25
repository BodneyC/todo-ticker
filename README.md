# Todo Ticker

Find, list and tick off todos hiding in code comments.

```latex
% - [ ] Do a thing
% - [x] Do another thing
50\% done  % TODO: fix the citation
```

## Install

```sh
poetry install          # dev, venv in ./.venv
pipx install .          # or install the `todo-ticker` / `tick` commands globally
```

## Disclaimer

95% Claude. Just wanted this project to support another project.

## What it finds

Inside comments only, anywhere on a line (start or end), in line or block comments:

Form                         | Meaning
:--                          | :--
`- [ ] text` (`*`/`+` too)   | open
`- [x] text` / `- [X] text`  | done
`TODO: text`, `FIXME(me): x` | open (no box yet)
`TODO: [x] text`             | done

Comment syntax is chosen by filename (`Makefile`, `.bashrc`, …), then
extension, then shebang (`#!/usr/bin/env node`), then content sniffing
(`\documentclass`, `<!DOCTYPE`, `<?php`), falling back to a generic mode
accepting `#`, `//`, `%`, `--`, `;`, `/* */` and `<!-- -->`. Markers inside
string literals and LaTeX's `\%` are ignored. Markdown files are scanned
for `<!-- -->` comments only, so ordinary task lists aren't picked up.

Directories are walked using `git ls-files` (respects `.gitignore`,
`.git/info/exclude` and global excludes); outside a repo, `.gitignore` files
are applied directly. Files named explicitly are always scanned.

## Usage

```sh
tick                          # list everything under .
tick src/ notes.tex           # specific paths
tick -o                       # open only      (-d: done only)
tick -g name                  # group same-named files from different dirs
tick -g value                 # group identical todos across files (e.g. "Spelling")
tick -g none                  # flat path:line list
tick -k todo -k fixme         # only TODO:/FIXME: comments (box = - [ ] items)

tick count                    # 6 open · 5 done · 11 total (45% done) · 6 files
tick count -o                 # just the number: 6
tick count -g file            # table of open/done/total per file
tick count -g value -s total -n 10   # ten most-repeated todos
tick count --json -g name     # machine-readable
tick count -o --exit-code     # exit 1 if anything is open (CI, pre-commit)

tick check 7k2m               # by id (any unique prefix, like git)
tick check paper.tex:12       # by location
tick check "fix the citation" # by text (case-insensitive substring)
tick uncheck 7k2m
tick toggle 7k2m q9xd -n      # several at once; -n = dry run
tick check thing --all        # apply to every match of an ambiguous ref
```

Ticking a bare `TODO: text` turns it into `TODO: [x] text`; unticking gives
`TODO: [ ] text`.

### Ids

Each todo's id is a hash of the file's path within its project (the nearest
folder containing `.git`; the absolute path when there isn't one), the todo's
normalised text and its occurrence index, written in Crockford base32 (no `i`,
`l`, `o`, `u`). It is stable when the todo moves within the file, is
ticked/unticked, or the tool is run from a different directory, and identical
todos in same-named files in different folders get different ids. It changes
if the text is edited or the file is renamed or moved. `list` shows the
shortest unique prefix (min. 4 chars).

If any ref is missing or ambiguous, nothing is written. Files are written
atomically, preserving permissions and line endings.

## Development

```sh
poetry run pytest           # tests + coverage (>= 90%)
poetry run ruff check . && poetry run ruff format .
poetry run pyright
```
