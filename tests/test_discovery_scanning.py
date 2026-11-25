from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from todo_ticker.discovery import discover, git_ls_files, walk_with_gitignore
from todo_ticker.scanning import MAX_BYTES, UnreadableFile, collect, read_text


def _tree(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("# - [ ] a\n")
    (root / "src" / "skip.log").write_text("# - [ ] log\n")
    (root / "build").mkdir()
    (root / "build" / "b.py").write_text("# - [ ] b\n")
    (root / "notes.tex").write_text("% TODO: n\n")
    (root / ".gitignore").write_text("build/\n")
    (root / "src" / ".gitignore").write_text("*.log\n")


def _names(paths: list[Path], root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in paths}


def test_walk_with_gitignore(tmp_path: Path) -> None:
    _tree(tmp_path)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("")
    found = _names(list(walk_with_gitignore(tmp_path)), tmp_path)
    assert found == {".gitignore", "notes.tex", "src/.gitignore", "src/a.py"}


def test_walk_ignores_undecodable_gitignore(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_bytes(b"\xff\xfe")
    (tmp_path / "a.py").write_text("")
    assert _names(list(walk_with_gitignore(tmp_path)), tmp_path) == {".gitignore", "a.py"}


def test_discover_without_git(tmp_path: Path) -> None:
    _tree(tmp_path)
    found = discover([tmp_path], git_lister=lambda _p: None)
    assert "build/b.py" not in _names(found, tmp_path)


def test_discover_explicit_ignored_file_is_included(tmp_path: Path) -> None:
    _tree(tmp_path)
    explicit = tmp_path / "build" / "b.py"
    found = discover([tmp_path, explicit, explicit], git_lister=lambda _p: None)
    assert found.count(explicit) == 1


def test_discover_missing_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        discover([tmp_path / "nope"])


def test_discover_uses_git_lister(tmp_path: Path) -> None:
    (tmp_path / "x.py").write_text("")
    calls: list[Path] = []

    def lister(path: Path) -> list[Path]:
        calls.append(path)
        return [path / "x.py", path / "deleted.py"]

    assert discover([tmp_path], git_lister=lister) == [tmp_path / "x.py"]
    assert calls == [tmp_path]


def test_git_ls_files_real_repo(tmp_path: Path) -> None:
    _tree(tmp_path)
    try:
        subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    except (OSError, subprocess.CalledProcessError):  # pragma: no cover
        pytest.skip("git unavailable")
    listed = git_ls_files(tmp_path)
    assert listed is not None
    assert _names(listed, tmp_path) == {".gitignore", "notes.tex", "src/.gitignore", "src/a.py"}


def test_git_ls_files_not_a_repo(tmp_path: Path) -> None:
    # tmp dirs live outside any repo, so git exits non-zero
    assert git_ls_files(tmp_path) is None


def test_git_ls_files_no_git(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def boom(*_a: object, **_k: object) -> None:
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "run", boom)
    assert git_ls_files(tmp_path) is None


def test_read_text_rejections(tmp_path: Path) -> None:
    binary = tmp_path / "b.bin"
    binary.write_bytes(b"abc\0def")
    latin = tmp_path / "l.txt"
    latin.write_bytes(b"caf\xe9")
    big = tmp_path / "big.txt"
    big.write_bytes(b"x" * (MAX_BYTES + 1))
    for path, needle in [(binary, "binary"), (latin, "UTF-8"), (big, "larger"), (tmp_path / "gone", "gone")]:
        with pytest.raises(UnreadableFile, match=needle):
            read_text(path)


def test_read_text_keeps_crlf(tmp_path: Path) -> None:
    f = tmp_path / "w.py"
    f.write_bytes(b"# - [ ] a\r\n")
    assert read_text(f) == "# - [ ] a\r\n"


def test_collect_warns_and_continues(tmp_path: Path) -> None:
    good = tmp_path / "a.py"
    good.write_text("# - [ ] a\n")
    bad = tmp_path / "b.bin"
    bad.write_bytes(b"\0")
    warnings: list[str] = []
    entries = collect([bad, good], warn=warnings.append)
    assert [e.todo.text for e in entries] == ["a"]
    assert len(warnings) == 1
    assert collect([bad]) == []  # no warn callback is fine
