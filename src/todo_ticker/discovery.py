"""Find the files to scan, honouring ``.gitignore``.

Inside a git work tree we ask git itself (``git ls-files``), which also covers
``.git/info/exclude`` and global excludes. Elsewhere we walk the directory and
apply any ``.gitignore`` files found along the way.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path

import pathspec

GitLister = Callable[[Path], "list[Path] | None"]

ALWAYS_SKIP_DIRS = frozenset({".git", ".hg", ".svn"})


def git_ls_files(directory: Path) -> list[Path] | None:
    """Tracked and untracked-but-not-ignored files under ``directory``, or
    ``None`` if git is unavailable or this is not a work tree."""
    try:
        result = subprocess.run(
            ["git", "-C", str(directory), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    names = result.stdout.decode("utf-8", "surrogateescape").split("\0")
    return [directory / name for name in names if name]


def _load_spec(directory: Path) -> pathspec.GitIgnoreSpec | None:
    ignore_file = directory / ".gitignore"
    try:
        lines = ignore_file.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    return pathspec.GitIgnoreSpec.from_lines(lines)


def walk_with_gitignore(root: Path) -> Iterator[Path]:
    """Walk ``root`` skipping anything matched by ``.gitignore`` files.

    Each ``.gitignore`` applies to paths relative to its own directory. A
    path is skipped if any applicable ``.gitignore`` ignores it.
    """
    specs: list[tuple[Path, pathspec.GitIgnoreSpec]] = []

    def ignored(path: Path, is_dir: bool) -> bool:
        for base, spec in specs:
            try:
                rel = path.relative_to(base).as_posix()
            except ValueError:
                continue
            if spec.match_file(rel + "/" if is_dir else rel):
                return True
        return False

    for dirpath, dirnames, filenames in os.walk(root):
        current = Path(dirpath)
        # Drop specs from sibling branches we have left.
        specs[:] = [(base, spec) for base, spec in specs if current == base or base in current.parents]
        spec = _load_spec(current)
        if spec is not None:
            specs.append((current, spec))
        dirnames[:] = sorted(d for d in dirnames if d not in ALWAYS_SKIP_DIRS and not ignored(current / d, True))
        for name in sorted(filenames):
            path = current / name
            if not ignored(path, False):
                yield path


def discover(paths: Iterable[Path], git_lister: GitLister = git_ls_files) -> list[Path]:
    """Expand ``paths`` into the files to scan.

    Explicitly named files are always included, even if ignored. Directories
    are expanded respecting ignore rules. The result is de-duplicated.
    """
    found: dict[Path, None] = {}
    for path in paths:
        if path.is_dir():
            listed = git_lister(path)
            candidates = listed if listed is not None else walk_with_gitignore(path)
            for candidate in candidates:
                if candidate.is_file() and not candidate.is_symlink():
                    found.setdefault(candidate, None)
        elif path.is_file():
            found.setdefault(path, None)
        else:
            raise FileNotFoundError(path)
    return list(found)
