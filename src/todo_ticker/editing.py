"""Pure text transformations for ticking/unticking todos."""

from __future__ import annotations

from collections.abc import Iterable

from .models import Todo


class EditError(ValueError):
    """Raised when a line no longer looks like the todo we expected."""


def set_line_state(line: str, todo: Todo, checked: bool) -> str:
    """Return ``line`` with ``todo`` set to ``checked``.

    Checkbox todos have their mark replaced. Bare ``TODO:`` comments gain a
    ``[x] `` or ``[ ] `` box in front of their text.
    """
    mark = "x" if checked else " "
    if todo.has_box:
        if todo.col >= len(line) or line[todo.col] not in " xX":
            raise EditError(f"line {todo.line}: expected a checkbox at column {todo.col + 1}")
        if (line[todo.col] != " ") == checked:
            return line  # already in the requested state; keep e.g. an "X"
        return line[: todo.col] + mark + line[todo.col + 1 :]

    if todo.col > len(line):
        raise EditError(f"line {todo.line}: line is shorter than expected")
    spacer = "" if todo.col == 0 or line[todo.col - 1] in " \t" else " "
    rest = line[todo.col :]
    box = f"[{mark}] " if rest else f"[{mark}]"
    return f"{line[: todo.col]}{spacer}{box}{rest}"


def apply_states(text: str, changes: Iterable[tuple[Todo, bool]]) -> str:
    """Apply several ``(todo, checked)`` changes to ``text`` at once.

    Lines are split on ``\\n`` only, so ``\\r\\n`` endings survive untouched.
    """
    lines = text.split("\n")
    # Right-to-left within a line so earlier columns stay valid.
    for todo, checked in sorted(changes, key=lambda c: (c[0].line, c[0].col), reverse=True):
        if not 1 <= todo.line <= len(lines):
            raise EditError(f"line {todo.line} is out of range")
        lines[todo.line - 1] = set_line_state(lines[todo.line - 1], todo, checked)
    return "\n".join(lines)
