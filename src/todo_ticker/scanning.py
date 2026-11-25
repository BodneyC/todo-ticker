"""Read files and turn them into :class:`Entry` objects."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from functools import lru_cache
from pathlib import Path

from .ids import assign_ids
from .languages import detect_syntax
from .models import Entry, Todo
from .parser import scan_text

MAX_BYTES = 4 * 1024 * 1024
SNIFF_BYTES = 8192

Warn = Callable[[str], None]


class UnreadableFile(Exception):
    """A file that cannot (or should not) be scanned as text."""


def read_text(path: Path) -> str:
    """Read ``path`` as UTF-8 text, preserving line endings.

    Raises :class:`UnreadableFile` for binary, oversized or undecodable files.
    """
    try:
        if path.stat().st_size > MAX_BYTES:
            raise UnreadableFile(f"{path}: larger than {MAX_BYTES // (1024 * 1024)} MiB, skipped")
        data = path.read_bytes()
    except OSError as exc:
        raise UnreadableFile(f"{path}: {exc.strerror or exc}") from exc
    if b"\0" in data[:SNIFF_BYTES]:
        raise UnreadableFile(f"{path}: binary file, skipped")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnreadableFile(f"{path}: not valid UTF-8, skipped") from exc


def scan_file_text(path: Path, text: str) -> list[Todo]:
    return scan_text(text, detect_syntax(path, text[:SNIFF_BYTES]))


RootFinder = Callable[[Path], "Path | None"]


@lru_cache(maxsize=1024)
def project_root(directory: Path) -> Path | None:
    """The nearest ancestor of ``directory`` (inclusive) containing ``.git``
    (a directory, or a file for worktrees and submodules), else ``None``."""
    for candidate in (directory, *directory.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def id_key(path: Path, find_root: RootFinder = project_root) -> str:
    """The file part of a todo's id: its path relative to the project root, so
    it doesn't depend on the current directory. Outside a project the absolute
    path is used."""
    absolute = path.resolve()
    root = find_root(absolute.parent)
    return (absolute.relative_to(root) if root is not None else absolute).as_posix()


def entries_for(path: Path, todos: list[Todo], find_root: RootFinder = project_root) -> list[Entry]:
    ids = assign_ids(id_key(path, find_root), todos)
    return [Entry(path, todo, id_) for todo, id_ in zip(todos, ids, strict=True)]


def collect(
    files: Iterable[Path],
    reader: Callable[[Path], str] = read_text,
    warn: Warn | None = None,
) -> list[Entry]:
    """Scan ``files`` and return all todos found, in file then line order."""
    entries: list[Entry] = []
    for path in files:
        try:
            text = reader(path)
        except UnreadableFile as exc:
            if warn is not None:
                warn(str(exc))
            continue
        entries.extend(entries_for(path, scan_file_text(path, text)))
    return entries
