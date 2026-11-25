from __future__ import annotations

from pathlib import Path

from todo_ticker.counting import Tally, summarise, tally
from todo_ticker.grouping import by_kind, group_key, group_label, kind_of, ordered_groups, status_filter
from todo_ticker.languages import HASH
from todo_ticker.models import Entry
from todo_ticker.parser import scan_text
from todo_ticker.scanning import entries_for

ROOT = Path("/proj")


def _entries(path: str, text: str) -> list[Entry]:
    return entries_for(ROOT / path, scan_text(text, HASH), find_root=lambda _d: ROOT)


def _sample() -> list[Entry]:
    return [
        *_entries("a/x.py", "# - [ ] Spelling\n# - [x] Figures\n# TODO: refs\n"),
        *_entries("b/x.py", "# - [x] spelling\n# FIXME: crash\n"),
        *_entries("c.py", "# - [ ] Spelling\n"),
    ]


def test_tally_and_percent() -> None:
    t = tally(_sample())
    assert (t.open, t.done, t.total, t.files) == (4, 2, 6, 3)
    assert round(t.percent_done) == 33
    assert Tally("x", 0, 0, 0).percent_done == 0.0
    assert t.as_dict()["percent_done"] == 33.3


def test_kind_filtering() -> None:
    entries = _sample()
    assert [kind_of(e) for e in entries] == ["box", "box", "todo", "box", "fixme", "box"]
    assert len(by_kind(entries, ["todo", "fixme"])) == 2
    assert by_kind(entries, []) == entries


def test_status_filter() -> None:
    entries = _sample()
    assert sum(map(status_filter("open"), entries)) == 4
    assert sum(map(status_filter("done"), entries)) == 2
    assert all(map(status_filter("all"), entries))


def test_group_keys_and_labels() -> None:
    e = _sample()[0]
    assert group_key(e, "file", ROOT) == "a/x.py"
    assert group_key(e, "name", ROOT) == "x.py"
    assert group_key(e, "value", ROOT) == "spelling"
    assert group_key(e, "none", ROOT) == ""
    assert group_label([e], "none", ROOT) == "all"
    assert group_label([e], "file", ROOT) == "a/x.py"


def test_value_groups_most_repeated_first() -> None:
    groups = ordered_groups(_sample(), "value", ROOT)
    assert len(groups[0]) == 3
    assert {e.path.name for e in groups[0]} == {"x.py", "c.py"}


def test_summarise_sorts() -> None:
    overall, groups = summarise(_sample(), "file", ROOT)
    assert overall.total == 6
    assert [g.label for g in groups] == ["a/x.py", "b/x.py", "c.py"]  # open desc, then total
    _, by_done = summarise(_sample(), "file", ROOT, sort="done")
    assert by_done[0].done == 1
    _, by_total = summarise(_sample(), "name", ROOT, sort="total")
    assert by_total[0].label == "x.py"
    assert by_total[0].total == 5
    _, by_name = summarise(_sample(), "value", ROOT, sort="name")
    assert [g.label for g in by_name] == ["crash", "Figures", "refs", "Spelling"]
    assert summarise(_sample(), "none", ROOT)[1] == []
