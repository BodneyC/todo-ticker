from __future__ import annotations

import pytest

from todo_ticker.languages import C_LIKE, GENERIC, HASH, LUA, MARKUP, RUST, TEX
from todo_ticker.parser import comment_segments, scan_text


def test_checkbox_at_line_start() -> None:
    [a, b] = scan_text("% - [ ] Do a thing\n% - [x] Done thing\n", TEX)
    assert (a.line, a.text, a.checked, a.kind) == (1, "Do a thing", False, "box")
    assert (b.line, b.text, b.checked) == (2, "Done thing", True)


def test_checkbox_at_end_of_line() -> None:
    [todo] = scan_text("x = 1  # - [ ] tidy this\n", HASH)
    assert todo.text == "tidy this"
    assert "x = 1  # - [".__len__() == todo.col


@pytest.mark.parametrize("bullet", ["-", "*", "+"])
def test_bullets(bullet: str) -> None:
    [todo] = scan_text(f"# {bullet} [X] shout\n", HASH)
    assert todo.checked


@pytest.mark.parametrize("line", ["%% - [ ] deco", "%- [ ] tight"])
def test_repeated_markers_and_no_space(line: str) -> None:
    assert len(scan_text(line, TEX)) == 1


def test_markers_inside_strings_ignored() -> None:
    [todo] = scan_text('x = "# - [ ] nope"  # - [ ] yes\n', HASH)
    assert todo.text == "yes"


def test_escaped_quote_in_string() -> None:
    [todo] = scan_text(r'x = "a \" # - [ ] nope"  # - [ ] yes', HASH)
    assert todo.text == "yes"


def test_url_in_string_not_comment() -> None:
    [todo] = scan_text('const u = "http://x"; // TODO: refactor\n', C_LIKE)
    assert todo.keyword == "TODO"
    assert todo.text == "refactor"


def test_rust_lifetimes_do_not_open_strings() -> None:
    [todo] = scan_text("fn f<'a>(x: &'a str) {} // - [ ] lifetimes\n", RUST)
    assert todo.text == "lifetimes"


def test_latex_escaped_percent() -> None:
    [todo] = scan_text(r"50\% done % TODO: cite", TEX)
    assert todo.text == "cite"
    assert scan_text(r"50\% - [ ] not a comment", TEX) == []


def test_double_backslash_is_not_escape() -> None:
    assert len(scan_text(r"a \\% - [ ] is a comment", TEX)) == 1


def test_block_comments_multiline() -> None:
    text = "/*\n * - [ ] first\n * TODO: second\n */\nint x; /* - [x] inline */ int y;\n"
    todos = scan_text(text, C_LIKE)
    assert [(t.line, t.text, t.checked) for t in todos] == [
        (2, "first", False),
        (3, "second", False),
        (5, "inline", True),
    ]


def test_block_comment_text_stops_at_close() -> None:
    [todo] = scan_text("<!-- - [ ] hidden -->\n- [ ] visible list item\n", MARKUP)
    assert todo.text == "hidden"


def test_lua_block_beats_line_marker() -> None:
    todos = scan_text("--[[\n- [ ] in block\n]]\n-- - [x] line\n", LUA)
    assert [(t.text, t.checked) for t in todos] == [("in block", False), ("line", True)]


def test_keyword_variants() -> None:
    text = "# TODO: plain\n# FIXME(ben): owner\n# TODO: [x] boxed\n# TODO: [ ] open box\n# note TODO: mid\n"
    todos = scan_text(text, HASH)
    assert [(t.keyword, t.text, t.checked, t.has_box) for t in todos] == [
        ("TODO", "plain", False, False),
        ("FIXME", "owner", False, False),
        ("TODO", "boxed", True, True),
        ("TODO", "open box", False, True),
        ("TODO", "mid", False, False),
    ]


def test_keyword_insert_column() -> None:
    line = "# TODO: plain"
    [todo] = scan_text(line, HASH)
    assert line[todo.col :] == "plain"


@pytest.mark.parametrize(
    "line",
    [
        "# - [ ]",
        "# TODO:",
        "# todo: lower case is not a keyword",
        "# TODOS: not a keyword",
        "# [ ] no bullet",
        "# - [y] wrong mark",
        "- [ ] not in a comment",
        "",
    ],
)
def test_non_todos(line: str) -> None:
    assert scan_text(line, HASH) == []


def test_crlf_line_endings() -> None:
    [todo] = scan_text("# - [ ] windows\r\n", HASH)
    assert todo.text == "windows"


def test_generic_syntax_accepts_common_markers() -> None:
    text = "# - [ ] a\n// - [ ] b\n% - [ ] c\n-- - [ ] d\n; - [ ] e\n/* - [ ] f */\n<!-- - [ ] g -->\n"
    assert [t.text for t in scan_text(text, GENERIC)] == list("abcdefg")


def test_comment_segments_unclosed_block_carries_state() -> None:
    segments, state = comment_segments("code /* open", C_LIKE, None)
    assert segments == [(7, 12)]
    assert state == ("/*", "*/")
    segments, state = comment_segments("still */ code", C_LIKE, state)
    assert segments == [(0, 6)]
    assert state is None
