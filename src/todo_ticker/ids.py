"""Stable, human-friendly ids for todos.

An id is derived from a *file key* (the file's path relative to its project
root, see :func:`todo_ticker.scanning.id_key`), the todo's normalised text and
its occurrence index among identical texts in that file. It therefore survives
the todo moving around the file, being ticked/unticked, being converted from
``TODO:`` to ``- [ ]``, and running the tool from a different directory, while
identical todos in same-named files in different folders still get different
ids.

Ids use Crockford's base32 alphabet (no ``i l o u``) so they are easy to read
aloud and type. Like git hashes, any unique prefix can be used.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter
from collections.abc import Iterable, Sequence

from .models import Todo

ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"
ID_LENGTH = 8
MIN_DISPLAY = 4

_WS = re.compile(r"\s+")


def normalise(text: str) -> str:
    return _WS.sub(" ", text.strip()).casefold()


def make_id(file_key: str, text: str, occurrence: int = 0) -> str:
    digest = hashlib.sha1(f"{file_key}\0{normalise(text)}\0{occurrence}".encode()).digest()
    value = int.from_bytes(digest[:5], "big")  # 40 bits -> 8 base32 chars
    chars: list[str] = []
    for _ in range(ID_LENGTH):
        value, rem = divmod(value, 32)
        chars.append(ALPHABET[rem])
    return "".join(reversed(chars))


def assign_ids(file_key: str, todos: Iterable[Todo]) -> list[str]:
    seen: Counter[str] = Counter()
    ids: list[str] = []
    for todo in todos:
        key = normalise(todo.text)
        ids.append(make_id(file_key, todo.text, seen[key]))
        seen[key] += 1
    return ids


def shortest_unique_prefixes(ids: Sequence[str], minimum: int = MIN_DISPLAY) -> dict[str, str]:
    """Map each id to its shortest prefix (at least ``minimum`` long) that no
    other id in ``ids`` shares."""
    ordered = sorted(set(ids))
    result: dict[str, str] = {}
    for i, current in enumerate(ordered):
        needed = minimum
        for neighbour in (ordered[i - 1] if i > 0 else None, ordered[i + 1] if i + 1 < len(ordered) else None):
            if neighbour is None:
                continue
            common = 0
            while common < len(current) and current[common] == neighbour[common]:
                common += 1
            needed = max(needed, common + 1)
        result[current] = current[: min(needed, len(current))]
    return result


def looks_like_id(ref: str) -> bool:
    ref = ref.lower()
    return len(ref) >= 3 and all(c in ALPHABET for c in ref)
