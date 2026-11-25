"""Turn a user-supplied reference into the todo(s) it means.

A reference is tried, in order, as:

1. ``path:line`` - e.g. ``paper.tex:12``
2. an id prefix - e.g. ``7k2m`` (optionally written ``#7k2m``)
3. text - a case-insensitive substring of the todo text; an exact match wins
   over partial ones.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from .ids import looks_like_id, normalise
from .models import Entry

_LOCATION = re.compile(r"^(?P<path>.+):(?P<line>\d+)$")


@dataclass(frozen=True)
class Resolution:
    ref: str
    how: str  # "location" | "id" | "text" | "none"
    matches: tuple[Entry, ...]


def _same_file(a: Path, b: Path) -> bool:
    try:
        return a.resolve() == b.resolve()
    except OSError:  # pragma: no cover - resolve() rarely fails
        return a == b


def resolve(ref: str, entries: Sequence[Entry], *, text_only: bool = False) -> Resolution:
    ref = ref.strip()
    if not text_only:
        loc = _LOCATION.match(ref)
        if loc is not None:
            target, line = Path(loc.group("path")), int(loc.group("line"))
            hits = tuple(e for e in entries if e.todo.line == line and _same_file(e.path, target))
            if hits:
                return Resolution(ref, "location", hits)

        candidate = ref.removeprefix("#").lower()
        if looks_like_id(candidate):
            hits = tuple(e for e in entries if e.id.startswith(candidate))
            if hits:
                return Resolution(ref, "id", hits)

    wanted = normalise(ref)
    if not wanted:
        return Resolution(ref, "none", ())
    exact = tuple(e for e in entries if normalise(e.todo.text) == wanted)
    if exact:
        return Resolution(ref, "text", exact)
    partial = tuple(e for e in entries if wanted in normalise(e.todo.text))
    return Resolution(ref, "text" if partial else "none", partial)


def location_path(ref: str) -> Path | None:
    """If ``ref`` looks like ``path:line`` and ``path`` is a file, return it."""
    loc = _LOCATION.match(ref.strip())
    if loc is None:
        return None
    path = Path(loc.group("path"))
    return path if path.is_file() else None
