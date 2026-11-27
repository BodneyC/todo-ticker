"""Pure scanning of text for todos inside comments.

Two shapes are recognised inside a comment body:

* markdown checkboxes: ``- [ ] text`` / ``* [x] text`` / ``+ [X] text``
* keyword todos: ``TODO: text``, ``FIXME(me): text``, optionally followed by a
  checkbox, e.g. ``TODO: [x] text``.

Comments may sit anywhere on a line (``code  # - [ ] thing``) or span several
lines in a block comment.
"""

from __future__ import annotations

import re

from .languages import CommentSyntax
from .models import Todo

# Decoration that may precede a checkbox inside a comment body: repeated
# markers (``%%``, ``##``, ``///``, ``//!``) and block-comment gutters (`` * ``).
CHECKBOX_RE = re.compile(r"^[\s#%/;!*]*?[-*+][ \t]+\[(?P<mark>[ xX])\](?:[ \t]+(?P<text>.*))?$")
KEYWORD_RE = re.compile(r"\b(?P<kw>TODO|FIXME)\b(?:\([^)]*\))?:[ \t]*" r"(?:\[(?P<mark>[ xX])\][ \t]*)?(?P<text>.*)$")

# Text given to keyword todos with nothing after them, e.g. a bare ``TODO:``.
NO_CONTEXT = "[No context]"

Segment = tuple[int, int]
BlockState = tuple[str, str] | None


def _is_escaped(line: str, index: int) -> bool:
    backslashes = 0
    i = index - 1
    while i >= 0 and line[i] == "\\":
        backslashes += 1
        i -= 1
    return backslashes % 2 == 1


def comment_segments(line: str, syntax: CommentSyntax, state: BlockState) -> tuple[list[Segment], BlockState]:
    """Return the ``(start, end)`` spans of comment bodies on ``line``.

    ``state`` is the block comment that is open at the start of the line (if
    any); the returned state is the one open at the end of the line. Strings
    are tracked within a single line so markers inside them are ignored.
    """
    segments: list[Segment] = []
    line_markers = sorted(syntax.line, key=len, reverse=True)
    blocks = sorted(syntax.block, key=lambda b: len(b[0]), reverse=True)
    end_of_line = len(line)
    i = 0
    quote: str | None = None

    while i < end_of_line:
        if state is not None:
            close = line.find(state[1], i)
            if close == -1:
                segments.append((i, end_of_line))
                return segments, state
            segments.append((i, close))
            i = close + len(state[1])
            state = None
            continue

        ch = line[i]
        if quote is not None:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue

        opened = next((b for b in blocks if line.startswith(b[0], i)), None)
        marker = next((m for m in line_markers if line.startswith(m, i)), None)
        # Prefer the longer token when a block opener and line marker overlap
        # (e.g. Lua's ``--[[`` vs ``--``).
        if opened is not None and (marker is None or len(opened[0]) >= len(marker)):
            state = opened
            i += len(opened[0])
            continue
        if marker is not None and not (syntax.escapable_marker and _is_escaped(line, i)):
            segments.append((i + len(marker), end_of_line))
            return segments, None
        if ch in syntax.quotes:
            quote = ch
        i += 1

    return segments, state


def match_body(line: str, start: int, end: int, lineno: int) -> Todo | None:
    """Look for a todo in ``line[start:end]`` (a comment body)."""
    body = line[start:end]

    box = CHECKBOX_RE.match(body)
    if box is not None:
        text = (box.group("text") or "").strip()
        if text:
            return Todo(
                line=lineno,
                kind="box",
                checked=box.group("mark") != " ",
                has_box=True,
                text=text,
                col=start + box.start("mark"),
            )

    kw = KEYWORD_RE.search(body)
    if kw is None:
        return None
    text = kw.group("text").strip() or NO_CONTEXT
    mark = kw.group("mark")
    return Todo(
        line=lineno,
        kind="keyword",
        checked=mark is not None and mark != " ",
        has_box=mark is not None,
        text=text,
        col=start + (kw.start("mark") if mark is not None else kw.start("text")),
        keyword=kw.group("kw"),
    )


def scan_text(text: str, syntax: CommentSyntax) -> list[Todo]:
    """Find every todo in ``text``. Lines are split on ``\\n`` only so that line
    numbers agree with :mod:`todo_ticker.editing`."""
    todos: list[Todo] = []
    state: BlockState = None
    for index, raw in enumerate(text.split("\n")):
        line = raw.rstrip("\r")
        segments, state = comment_segments(line, syntax, state)
        for start, end in segments:
            todo = match_body(line, start, end, index + 1)
            if todo is not None:
                todos.append(todo)
    return todos
