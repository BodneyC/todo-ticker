from __future__ import annotations

from pathlib import PurePath

import pytest

from todo_ticker.languages import (
    C_LIKE,
    GENERIC,
    HASH,
    LUA,
    MARKUP,
    PHP,
    TEX,
    CommentSyntax,
    detect_syntax,
    interpreter_from_shebang,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("paper.tex", TEX),
        ("main.PY", HASH),
        ("app.ts", C_LIKE),
        ("README.md", MARKUP),
        ("Makefile", HASH),
        (".bashrc", HASH),
        ("CMakeLists.txt", HASH),
        ("init.lua", LUA),
    ],
)
def test_by_name_and_extension(name: str, expected: CommentSyntax) -> None:
    assert detect_syntax(PurePath(name), "") is expected


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("#!/bin/bash", "bash"),
        ("#!/usr/bin/env python3.12", "python"),
        ("#!/usr/bin/env -S node --flag", "node"),
        ("#!/usr/bin/env FOO=1 ruby", "ruby"),
        ("#!/usr/bin/env", None),
        ("#!", None),
        ("# not a shebang", None),
    ],
)
def test_interpreter_from_shebang(line: str, expected: str | None) -> None:
    assert interpreter_from_shebang(line) == expected


def test_shebang_detection() -> None:
    assert detect_syntax(PurePath("script"), "#!/usr/bin/env node\n") is C_LIKE
    assert detect_syntax(PurePath("script"), "#!/opt/weird-shell\n") is HASH


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        ("\\documentclass{article}", TEX),
        ("<!DOCTYPE html>", MARKUP),
        ("<?php echo 1;", PHP),
        ("just some words", GENERIC),
    ],
)
def test_content_sniffing(head: str, expected: CommentSyntax) -> None:
    assert detect_syntax(PurePath("noext"), head) is expected
