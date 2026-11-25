from __future__ import annotations

from pathlib import Path

import pytest

from todo_ticker.editing import EditError, apply_states, set_line_state
from todo_ticker.ids import ALPHABET, assign_ids, looks_like_id, make_id, shortest_unique_prefixes
from todo_ticker.languages import HASH
from todo_ticker.models import Entry, Todo
from todo_ticker.parser import scan_text
from todo_ticker.resolve import location_path, resolve
from todo_ticker.scanning import entries_for, id_key, project_root

# --- ids ---------------------------------------------------------------------


def test_id_shape_and_stability() -> None:
    a = make_id("f.py", "Do a thing")
    assert len(a) == 8
    assert set(a) <= set(ALPHABET)
    assert make_id("f.py", "  do   A thing ") == a  # whitespace/case-insensitive
    assert make_id("g.py", "Do a thing") != a
    assert make_id("f.py", "Do a thing", 1) != a


def test_id_survives_ticking_and_moving() -> None:
    before = scan_text("# - [ ] thing\n", HASH)
    after = scan_text("\n\nx = 1  # TODO: [x] thing\n", HASH)
    assert assign_ids("f.py", before) == assign_ids("f.py", after)


def test_duplicate_texts_get_distinct_ids() -> None:
    todos = scan_text("# - [ ] same\n# - [ ] same\n", HASH)
    ids = assign_ids("f.py", todos)
    assert len(set(ids)) == 2


def test_shortest_unique_prefixes() -> None:
    result = shortest_unique_prefixes(["abcdef12", "abcdxy34", "zzzzzzzz"])
    assert result == {"abcdef12": "abcde", "abcdxy34": "abcdx", "zzzzzzzz": "zzzz"}
    assert shortest_unique_prefixes(["abc", "abc"]) == {"abc": "abc"}
    assert shortest_unique_prefixes([]) == {}


@pytest.mark.parametrize(("ref", "ok"), [("7k2m", True), ("7K2M", True), ("ab", False), ("hello", False)])
def test_looks_like_id(ref: str, ok: bool) -> None:
    assert looks_like_id(ref) is ok


# --- resolve -----------------------------------------------------------------


@pytest.fixture
def entries(tmp_path: Path) -> list[Entry]:
    f = tmp_path / "notes.py"
    f.write_text("# - [ ] Write the intro\n# - [ ] Write the outro\n# TODO: intro\n")
    return entries_for(f, scan_text(f.read_text(), HASH))


def test_resolve_by_id_prefix(entries: list[Entry]) -> None:
    target = entries[1]
    res = resolve(target.id[:5], entries)
    assert res.how == "id"
    assert res.matches == (target,)
    assert resolve("#" + target.id[:5], entries).matches == (target,)


def test_resolve_by_location(entries: list[Entry], tmp_path: Path) -> None:
    res = resolve(f"{tmp_path / 'notes.py'}:2", entries)
    assert res.how == "location"
    assert res.matches == (entries[1],)


def test_resolve_exact_text_beats_partial(entries: list[Entry]) -> None:
    res = resolve("INTRO", entries)
    assert res.how == "text"
    assert res.matches == (entries[2],)


def test_resolve_partial_ambiguous(entries: list[Entry]) -> None:
    assert len(resolve("write", entries).matches) == 2


def test_resolve_text_only_skips_ids(entries: list[Entry]) -> None:
    assert resolve(entries[0].id, entries, text_only=True).how == "none"


def test_resolve_nothing(entries: list[Entry]) -> None:
    assert resolve("   ", entries).how == "none"
    assert resolve("missing", entries).matches == ()


def test_location_path(tmp_path: Path) -> None:
    f = tmp_path / "a.py"
    f.write_text("")
    assert location_path(f"{f}:3") == f
    assert location_path(f"{tmp_path / 'nope.py'}:3") is None
    assert location_path("no-line-number") is None


# --- editing -----------------------------------------------------------------


def _one(line: str) -> Todo:
    [todo] = scan_text(line, HASH)
    return todo


@pytest.mark.parametrize(
    ("line", "checked", "expected"),
    [
        ("# - [ ] a", True, "# - [x] a"),
        ("# - [x] a", False, "# - [ ] a"),
        ("# - [X] a", True, "# - [X] a"),  # already checked, left alone
        ("# TODO: a", True, "# TODO: [x] a"),
        ("# TODO: a", False, "# TODO: [ ] a"),
        ("# TODO:a", True, "# TODO: [x] a"),
        ("# TODO: [ ] a", True, "# TODO: [x] a"),
        ("x()  # FIXME(me): a", True, "x()  # FIXME(me): [x] a"),
    ],
)
def test_set_line_state(line: str, checked: bool, expected: str) -> None:
    assert set_line_state(line, _one(line), checked) == expected


def test_set_line_state_mismatch_raises() -> None:
    todo = _one("# - [ ] a")
    with pytest.raises(EditError):
        set_line_state("totally different", todo, True)
    bare = _one("# TODO: something long")
    with pytest.raises(EditError):
        set_line_state("#", bare, True)


def test_apply_states_preserves_crlf_and_other_lines() -> None:
    text = "keep\r\n# - [ ] a\r\n# TODO: b\r\n"
    todos = scan_text(text, HASH)
    out = apply_states(text, [(todos[0], True), (todos[1], True)])
    assert out == "keep\r\n# - [x] a\r\n# TODO: [x] b\r\n"


def test_apply_states_out_of_range() -> None:
    todo = _one("# - [ ] a")
    with pytest.raises(EditError):
        apply_states("", [(Todo(line=5, kind=todo.kind, checked=False, has_box=True, text="a", col=5), True)])


# --- file keys -----------------------------------------------------------------


def test_same_name_same_text_different_dirs_get_distinct_ids(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    todos = scan_text("# - [ ] Spelling\n", HASH)
    a = entries_for(tmp_path / "ch1" / "main.tex", todos)
    b = entries_for(tmp_path / "ch2" / "main.tex", todos)
    assert a[0].id != b[0].id


def test_id_key_relative_to_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".git").write_text("gitdir: elsewhere\n")  # worktree/submodule style
    (tmp_path / "sub").mkdir()
    target = tmp_path / "sub" / "x.py"
    target.write_text("")
    project_root.cache_clear()
    assert id_key(target) == "sub/x.py"
    monkeypatch.chdir(tmp_path / "sub")
    assert id_key(Path("x.py")) == "sub/x.py"  # independent of cwd


def test_id_key_without_project_uses_absolute_path(tmp_path: Path) -> None:
    target = tmp_path / "x.py"
    assert id_key(target, find_root=lambda _d: None) == target.resolve().as_posix()


def test_project_root_none_outside_repo(tmp_path: Path) -> None:
    project_root.cache_clear()
    assert project_root(tmp_path) is None
