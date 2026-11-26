"""Pure helpers for grouping and filtering entries, shared by list and count."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import Literal

from .ids import normalise
from .models import Entry

Group = Literal["file", "name", "value", "none"]
Kind = Literal["box", "todo", "fixme"]
Status = Literal["all", "open", "done"]
Filter = Callable[[Entry], bool]

GROUPS: tuple[Group, ...] = ("file", "name", "value", "none")
KINDS: tuple[Kind, ...] = ("box", "todo", "fixme")


def display_path(path: Path, cwd: Path) -> str:
    """``path`` relative to ``cwd``, always with forward slashes (matching ids
    and ``path:line`` refs, which Windows accepts too)."""
    try:
        return Path(os.path.relpath(path, cwd)).as_posix()
    except ValueError:  # pragma: no cover - different drive on Windows
        return path.as_posix()


def group_key(entry: Entry, group: Group, cwd: Path) -> str:
    if group == "name":
        return entry.path.name
    if group == "value":
        return normalise(entry.todo.text)
    if group == "none":
        return ""
    return display_path(entry.path, cwd)


def group_label(members: Sequence[Entry], group: Group, cwd: Path) -> str:
    """Human-readable name for a group (``members`` must be non-empty)."""
    first = members[0]
    if group == "value":
        return first.todo.text
    if group == "name":
        return first.path.name
    if group == "none":
        return "all"
    return display_path(first.path, cwd)


def ordered_groups(entries: Sequence[Entry], group: Group, cwd: Path) -> list[list[Entry]]:
    """Split ``entries`` into groups, each in path then line order. Value
    groups are ordered most-repeated first; file and name groups
    alphabetically."""
    buckets: dict[str, list[Entry]] = {}
    for entry in sorted(entries, key=lambda e: (display_path(e.path, cwd), e.todo.line)):
        buckets.setdefault(group_key(entry, group, cwd), []).append(entry)
    if group == "value":
        return [buckets[k] for k in sorted(buckets, key=lambda k: (-len(buckets[k]), k))]
    return [buckets[k] for k in sorted(buckets)]


def kind_of(entry: Entry) -> Kind:
    if entry.todo.kind == "box":
        return "box"
    return "fixme" if entry.todo.keyword == "FIXME" else "todo"


def by_kind(entries: Iterable[Entry], kinds: Iterable[Kind]) -> list[Entry]:
    """Keep entries of the given kinds; no kinds means keep everything."""
    wanted = set(kinds)
    return [e for e in entries if not wanted or kind_of(e) in wanted]


def status_filter(status: Status) -> Filter:
    if status == "open":
        return lambda e: not e.todo.checked
    if status == "done":
        return lambda e: e.todo.checked
    return lambda _e: True
