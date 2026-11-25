"""Work out which comment markers a file uses.

Detection order: exact filename, extension, shebang, content sniffing, and
finally a permissive generic syntax that accepts the common markers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePath

_QUOTES = ('"', "'")


@dataclass(frozen=True)
class CommentSyntax:
    name: str
    line: tuple[str, ...] = ()
    block: tuple[tuple[str, str], ...] = ()
    quotes: tuple[str, ...] = _QUOTES
    # LaTeX style: a backslash before the marker (``\%``) means "not a comment".
    escapable_marker: bool = False


HASH = CommentSyntax("hash", ("#",))
C_LIKE = CommentSyntax("c", ("//",), (("/*", "*/"),))
RUST = CommentSyntax("rust", ("//",), (("/*", "*/"),), quotes=('"',))
CSS = CommentSyntax("css", (), (("/*", "*/"),))
SCSS = CommentSyntax("scss", ("//",), (("/*", "*/"),))
PHP = CommentSyntax("php", ("//", "#"), (("/*", "*/"),))
MARKUP = CommentSyntax("markup", (), (("<!--", "-->"),), quotes=())
WEB_COMPONENT = CommentSyntax("component", ("//",), (("/*", "*/"), ("<!--", "-->")), quotes=())
TEX = CommentSyntax("tex", ("%",), quotes=(), escapable_marker=True)
PERCENT = CommentSyntax("percent", ("%",), (("%{", "%}"),), quotes=())
SQL = CommentSyntax("sql", ("--",), (("/*", "*/"),))
LUA = CommentSyntax("lua", ("--",), (("--[[", "]]"),))
HASKELL = CommentSyntax("haskell", ("--",), (("{-", "-}"),), quotes=('"',))
LISP = CommentSyntax("lisp", (";",), quotes=('"',))
INI = CommentSyntax("ini", (";", "#"), quotes=())
FORTRAN = CommentSyntax("fortran", ("!",))
OCAML = CommentSyntax("ocaml", (), (("(*", "*)"),), quotes=('"',))
JULIA = CommentSyntax("julia", ("#",), (("#=", "=#"),), quotes=('"',))
POWERSHELL = CommentSyntax("powershell", ("#",), (("<#", "#>"),))
GENERIC = CommentSyntax(
    "generic",
    ("#", "//", "%", "--", ";"),
    (("/*", "*/"), ("<!--", "-->")),
    quotes=(),
)


def _table(mapping: dict[CommentSyntax, str]) -> dict[str, CommentSyntax]:
    return {key: syntax for syntax, keys in mapping.items() for key in keys.split()}


EXTENSIONS: dict[str, CommentSyntax] = _table(
    {
        HASH: ".py .pyi .pyw .sh .bash .zsh .fish .ksh .rb .pl .pm .r .yaml .yml "
        ".toml .cfg .conf .mk .cmake .nim .ex .exs .coffee .tcl .awk .properties "
        ".dockerfile .env .gitignore .tf .hcl .nix .cr",
        C_LIKE: ".c .h .cc .cpp .cxx .hh .hpp .hxx .cs .java .js .jsx .mjs .cjs .ts "
        ".tsx .mts .cts .go .swift .kt .kts .scala .sc .dart .groovy .gradle .proto "
        ".zig .json5 .jsonc .v .sv .glsl .hlsl .frag .vert .d .m .mm",
        RUST: ".rs",
        CSS: ".css",
        SCSS: ".scss .sass .less .styl",
        PHP: ".php",
        MARKUP: ".html .htm .xhtml .xml .svg .md .markdown .mdx .xsl .xslt .plist",
        WEB_COMPONENT: ".vue .svelte .astro",
        TEX: ".tex .sty .cls .ltx .dtx .ins .bib .bst",
        PERCENT: ".erl .hrl .ps .eps",
        SQL: ".sql .ada .adb .ads .elm .vhd .vhdl",
        LUA: ".lua",
        HASKELL: ".hs .lhs .purs",
        LISP: ".lisp .lsp .cl .el .clj .cljs .cljc .edn .scm .ss .rkt .asm .s",
        INI: ".ini",
        FORTRAN: ".f90 .f95 .f03 .f08",
        OCAML: ".ml .mli .fs .fsi .fsx",
        JULIA: ".jl",
        POWERSHELL: ".ps1 .psm1 .psd1",
    }
)

FILENAMES: dict[str, CommentSyntax] = _table(
    {
        HASH: "makefile gnumakefile dockerfile containerfile cmakelists.txt .gitignore "
        ".gitattributes .dockerignore .bashrc .bash_profile .zshrc .zshenv .profile "
        ".env gemfile rakefile vagrantfile justfile procfile brewfile pipfile",
    }
)

INTERPRETERS: dict[str, CommentSyntax] = _table(
    {
        HASH: "python pypy sh bash zsh fish ksh dash ruby perl Rscript tclsh wish awk gawk make crystal elixir julia",
        C_LIKE: "node nodejs deno bun ts-node tsx",
        LUA: "lua luajit",
        POWERSHELL: "pwsh",
        LISP: "sbcl guile racket clojure",
    }
)

_SNIFFS: tuple[tuple[re.Pattern[str], CommentSyntax], ...] = (
    (re.compile(r"\\(documentclass|begin\{document\}|usepackage)"), TEX),
    (re.compile(r"^\s*<(\?xml|!doctype|html)", re.IGNORECASE), MARKUP),
    (re.compile(r"^\s*<\?php"), PHP),
)


def interpreter_from_shebang(first_line: str) -> str | None:
    """Return the interpreter named by a ``#!`` line, without version suffix."""
    if not first_line.startswith("#!"):
        return None
    parts = first_line[2:].split()
    if not parts:
        return None
    prog = PurePath(parts[0]).name
    if prog == "env":
        args = [p for p in parts[1:] if not p.startswith("-") and "=" not in p]
        if not args:
            return None
        prog = PurePath(args[0]).name
    return re.sub(r"[\d.]+$", "", prog) or None


def detect_syntax(path: PurePath, head: str) -> CommentSyntax:
    """Pick the comment syntax for ``path`` given the start of its contents."""
    name = path.name.lower()
    if name in FILENAMES:
        return FILENAMES[name]
    suffix = path.suffix.lower()
    if suffix in EXTENSIONS:
        return EXTENSIONS[suffix]
    first_line = head.split("\n", 1)[0]
    interpreter = interpreter_from_shebang(first_line)
    if interpreter is not None:
        return INTERPRETERS.get(interpreter, HASH)
    for pattern, syntax in _SNIFFS:
        if pattern.search(head):
            return syntax
    return GENERIC
