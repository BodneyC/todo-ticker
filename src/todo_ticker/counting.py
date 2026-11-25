"""Pure tallying of todos for the ``count`` command."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .grouping import Group, group_label, ordered_groups
from .models import Entry

Sort = Literal["open", "total", "done", "name"]
SORTS: tuple[Sort, ...] = ("open", "total", "done", "name")


@dataclass(frozen=True)
class Tally:
    label: str
    open: int
    done: int
    files: int

    @property
    def total(self) -> int:
        return self.open + self.done

    @property
    def percent_done(self) -> float:
        return 100.0 * self.done / self.total if self.total else 0.0

    def as_dict(self) -> dict[str, str | int | float]:
        return {
            "label": self.label,
            "open": self.open,
            "done": self.done,
            "total": self.total,
            "files": self.files,
            "percent_done": round(self.percent_done, 1),
        }


def tally(entries: Sequence[Entry], label: str = "all") -> Tally:
    done = sum(e.todo.checked for e in entries)
    return Tally(label, len(entries) - done, done, len({e.path for e in entries}))


_SORT_KEYS: dict[Sort, Callable[[Tally], tuple[int | str, ...]]] = {
    "open": lambda t: (-t.open, -t.total, t.label.casefold()),
    "total": lambda t: (-t.total, -t.open, t.label.casefold()),
    "done": lambda t: (-t.done, -t.total, t.label.casefold()),
    "name": lambda t: (t.label.casefold(),),
}


def summarise(
    entries: Sequence[Entry],
    group: Group,
    cwd: Path,
    *,
    sort: Sort = "open",
) -> tuple[Tally, list[Tally]]:
    """Overall tally plus one sorted tally per group (empty for
    ``group="none"``)."""
    overall = tally(entries)
    if group == "none":
        return overall, []
    groups = [tally(m, group_label(m, group, cwd)) for m in ordered_groups(entries, group, cwd)]
    groups.sort(key=_SORT_KEYS[sort])
    return overall, groups
