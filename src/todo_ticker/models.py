"""Plain data types shared across the package."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Kind = Literal["box", "keyword"]


@dataclass(frozen=True)
class Todo:
    """A single todo found in a comment.

    ``col`` is the column of the mark character inside ``[ ]`` when the todo
    has a checkbox, otherwise the column where a checkbox should be inserted.
    """

    line: int  # 1-based
    kind: Kind
    checked: bool
    has_box: bool
    text: str
    col: int
    keyword: str | None = None


@dataclass(frozen=True)
class Entry:
    """A todo located in a particular file, with its stable id."""

    path: Path
    todo: Todo
    id: str
