from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from click.testing import CliRunner

from todo_ticker.cli import main


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "paper.tex").write_text("% - [ ] Do a thing\n% - [x] Do another thing\n")
    (tmp_path / "b" / "paper.tex").write_text("text % TODO: cite [Smith]\n")
    (tmp_path / "app.py").write_text("x = 1  # - [ ] tidy\n")
    return tmp_path


def invoke(*args: str) -> tuple[int, str]:
    result = CliRunner().invoke(main, list(args))
    return result.exit_code, result.output


def test_default_command_lists(project: Path) -> None:
    code, out = invoke("--no-color")
    assert code == 0
    assert "a/paper.tex" in out
    assert "Do a thing" in out
    assert "cite [Smith]" in out  # brackets are not swallowed as markup
    assert "3 open" in out
    assert "1 done" in out


def test_list_specific_paths(project: Path) -> None:
    code, out = invoke("app.py", "--no-color")
    assert code == 0
    assert "tidy" in out
    assert "paper" not in out


def test_list_filters(project: Path) -> None:
    _, out = invoke("list", "--open", "--no-color")
    assert "Do another thing" not in out
    _, out = invoke("list", "--done", "--no-color")
    assert "Do a thing" not in out
    assert "Do another thing" in out
    code, out = invoke("list", "--open", "--done")
    assert code != 0
    assert "mutually exclusive" in out


def test_group_by_name_and_none(project: Path) -> None:
    _, out = invoke("-g", "name", "--no-color")
    assert "paper.tex  (2 locations)" in out
    _, out = invoke("-g", "none", "--no-color")
    assert "a/paper.tex:1" in out


def test_no_todos(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "x.py").write_text("print(1)\n")
    assert "No todos found." in invoke("--no-color")[1]


def test_missing_path_errors(project: Path) -> None:
    code, _ = invoke("nope.py")
    assert code == 2


def test_check_by_text_id_and_location(project: Path) -> None:
    code, out = invoke("check", "tidy", "--no-color")
    assert code == 0, out
    assert "checked" in out
    assert (project / "app.py").read_text() == "x = 1  # - [x] tidy\n"

    code, out = invoke("check", "b/paper.tex:1", "--no-color")
    assert code == 0, out
    assert (project / "b" / "paper.tex").read_text() == "text % TODO: [x] cite [Smith]\n"

    _, listing = invoke("-g", "none", "--no-color")
    row = next(line for line in listing.splitlines() if "Do a thing" in line)
    short_id = row.split()[1]
    code, out = invoke("toggle", short_id, "--no-color")
    assert code == 0, out
    assert (project / "a" / "paper.tex").read_text().startswith("% - [x] Do a thing")


def test_uncheck_and_already(project: Path) -> None:
    code, out = invoke("uncheck", "Do another thing", "--no-color")
    assert code == 0
    assert (project / "a" / "paper.tex").read_text() == "% - [ ] Do a thing\n% - [ ] Do another thing\n"
    code, out = invoke("uncheck", "Do another thing", "--no-color")
    assert "already unchecked" in out


def test_uncheck_bare_todo_adds_empty_box(project: Path) -> None:
    code, _ = invoke("uncheck", "cite", "--no-color")
    assert code == 0
    assert (project / "b" / "paper.tex").read_text() == "text % TODO: [ ] cite [Smith]\n"


def test_ambiguous_ref_aborts_everything(project: Path) -> None:
    before = (project / "app.py").read_text()
    code, out = invoke("check", "tidy", "thing", "--no-color")
    assert code == 1
    assert "ambiguous" in out
    assert (project / "app.py").read_text() == before  # nothing written


def test_all_flag_applies_to_every_match(project: Path) -> None:
    code, _ = invoke("check", "thing", "--all", "--no-color")
    assert code == 0
    assert (project / "a" / "paper.tex").read_text() == "% - [x] Do a thing\n% - [x] Do another thing\n"


def test_no_match(project: Path) -> None:
    code, out = invoke("check", "zzz-nothing", "--no-color")
    assert code == 1
    assert "no todo matches" in out


def test_dry_run_writes_nothing(project: Path) -> None:
    code, out = invoke("check", "tidy", "--dry-run", "--no-color")
    assert code == 0
    assert "dry run" in out
    assert "[ ] tidy" in (project / "app.py").read_text()


def test_path_scope_option(project: Path) -> None:
    code, out = invoke("check", "thing", "-p", "app.py", "--no-color")
    assert code == 1
    assert "no todo matches" in out


def test_write_preserves_mode_and_crlf(project: Path) -> None:
    script = project / "run.sh"
    script.write_bytes(b"#!/bin/sh\r\necho hi  # - [ ] crlf\r\n")
    os.chmod(script, 0o755)
    code, out = invoke("check", "crlf", "--no-color")
    assert code == 0, out
    assert script.read_bytes() == b"#!/bin/sh\r\necho hi  # - [x] crlf\r\n"
    if os.name != "nt":  # Windows has no Unix permission bits to preserve
        assert stat.S_IMODE(script.stat().st_mode) == 0o755
    assert not [p for p in project.iterdir() if p.name.endswith(".tick")]


def test_warnings_shown_unless_quiet(project: Path) -> None:
    (project / "blob.bin").write_bytes(b"\0\0")
    runner = CliRunner()
    result = runner.invoke(main, ["--no-color"])
    assert "binary file" in result.output
    result = runner.invoke(main, ["--no-color", "-q"])
    assert "binary file" not in result.output


def test_version_and_help() -> None:
    assert "0.1.1" in invoke("--version")[1]
    assert "TODO:" in invoke("--help")[1]


def test_group_by_value_text(project: Path) -> None:
    (project / "a" / "notes.tex").write_text("% - [ ] Spelling\n")
    (project / "b" / "notes.tex").write_text("%% - [x] spelling\n")
    (project / "app.py").write_text("x = 1  # TODO: Spelling\n# - [ ] one-off\n")
    code, out = invoke("-g", "value", "--no-color")
    assert code == 0, out
    lines = out.splitlines()
    # Most-repeated group first, merged case-insensitively across files and styles.
    assert lines[0].startswith("Spelling  (3 occurrences in 3 files)")
    assert "1/3" in lines[0]
    block = lines[1:4]
    assert any("a/notes.tex:1" in line for line in block)
    assert any("b/notes.tex:1" in line for line in block)
    assert any("app.py:1" in line and "TODO" in line for line in block)
    assert "one-off  (1 occurrence in 1 file)" in out


def test_group_by_value_respects_filter(project: Path) -> None:
    (project / "a" / "notes.tex").write_text("% - [x] Spelling\n")
    (project / "b" / "notes.tex").write_text("% - [x] spelling\n")
    _, out = invoke("-g", "value", "--open", "--no-color")
    assert "Spelling" not in out


def test_count_totals(project: Path) -> None:
    code, out = invoke("count", "--no-color")
    assert code == 0
    assert "3 open" in out
    assert "1 done" in out
    assert "4 total (25% done)" in out
    assert "3 files" in out


def test_count_bare_number_with_status(project: Path) -> None:
    assert invoke("count", "-o")[1] == "3\n"
    assert invoke("count", "-d")[1] == "1\n"
    code, out = invoke("count", "-o", "-d")
    assert code != 0
    assert "mutually exclusive" in out


def test_count_grouped_table_and_limit(project: Path) -> None:
    _, out = invoke("count", "-g", "file", "--no-color")
    assert out.splitlines()[0].split() == ["File", "Open", "Done", "Total", "Progress"]
    assert "a/paper.tex" in out
    _, out = invoke("count", "-g", "file", "-n", "1", "--no-color")
    assert "… 2 more file groups" in out
    _, out = invoke("count", "-g", "file", "-n", "2", "--no-color")
    assert "… 1 more file group\n" in out


def test_count_kind_filter(project: Path) -> None:
    assert invoke("count", "-o", "-k", "todo")[1] == "1\n"
    assert invoke("count", "-o", "-k", "box", "-k", "fixme")[1] == "2\n"


def test_count_json(project: Path) -> None:
    import json

    data = json.loads(invoke("count", "--json")[1])
    assert data == {"open": 3, "done": 1, "total": 4, "files": 3, "percent_done": 25.0}
    data = json.loads(invoke("count", "--json", "-g", "name", "-n", "1")[1])
    assert data["group"] == "name"
    assert data["groups"][0]["label"] == "paper.tex"
    assert data["groups"][0]["open"] == 2
    assert data["omitted_groups"] == 1


def test_count_exit_code(project: Path) -> None:
    assert invoke("count", "--exit-code", "--no-color")[0] == 1
    assert invoke("count", "--exit-code", "-d")[0] == 0
    assert invoke("count", "--no-color")[0] == 0


def test_list_kind_filter(project: Path) -> None:
    _, out = invoke("list", "-k", "todo", "--no-color")
    assert "cite" in out
    assert "Do a thing" not in out
