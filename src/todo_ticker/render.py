"""Colourful terminal output."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from rich.console import Console
from rich.table import Table
from rich.text import Text

from .counting import Tally
from .grouping import Filter, Group, display_path, group_label, ordered_groups
from .models import Entry

__all__ = ["Filter", "Group", "display_path", "render", "render_change", "render_counts", "render_summary"]

ICON_DONE = "✔"
ICON_OPEN = "☐"


def _progress(entries: Sequence[Entry]) -> Text:
    return _bar(sum(e.todo.checked for e in entries), len(entries))


def _bar(done: int, total: int) -> Text:
    style = "bold green" if done == total else ("yellow" if done else "red")
    width = 10
    filled = round(width * done / total) if total else 0
    return Text.assemble(
        ("━" * filled, "green"),
        ("━" * (width - filled), "bright_black"),
        " ",
        (f"{done}/{total}", style),
    )


def todo_text(entry: Entry, *, with_text: bool = True) -> Text:
    todo = entry.todo
    text = Text()
    if todo.keyword is not None:
        badge = "bold black on yellow" if todo.keyword == "TODO" else "bold white on red"
        text.append(f" {todo.keyword} ", style=badge)
        text.append(" ")
    if with_text:
        text.append(todo.text, style="strike bright_black" if todo.checked else "default")
    return text


def _row(entry: Entry, short_ids: dict[str, str], location: Text, *, with_text: bool = True) -> list[Text]:
    icon = Text(ICON_DONE, style="bold green") if entry.todo.checked else Text(ICON_OPEN, style="bold yellow")
    return [
        icon,
        Text(short_ids.get(entry.id, entry.id), style="magenta"),
        location,
        todo_text(entry, with_text=with_text),
    ]


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'s' if n != 1 else ''}"


def _header(members: Sequence[Entry], group: Group, cwd: Path) -> Text:
    title = Text(group_label(members, group, cwd), style="bold cyan")
    if group == "value":
        files = len({e.path for e in members})
        title.append(f"  ({_plural(len(members), 'occurrence')} in {_plural(files, 'file')})", style="bright_black")
        return title
    if group == "name":
        dirs = {e.path.parent for e in members}
        title.append(f"  ({_plural(len(dirs), 'location')})", style="bright_black")
        return title
    return title


def _table(location_justify: Literal["left", "right"] = "right") -> Table:
    table = Table.grid(padding=(0, 1))
    table.add_column(width=1, no_wrap=True)
    table.add_column(no_wrap=True)
    table.add_column(justify=location_justify, no_wrap=True)
    table.add_column(overflow="fold")
    return table


def render(
    console: Console,
    entries: Sequence[Entry],
    short_ids: dict[str, str],
    *,
    cwd: Path,
    group: Group = "file",
    visible: Filter = lambda _e: True,
) -> int:
    """Print ``entries`` grouped as requested. Headers show progress over every
    entry in the group; rows show only those passing ``visible``.

    Returns the number of rows printed.
    """
    shown = 0
    if group == "none":
        rows = [e for e in entries if visible(e)]
        table = _table("left")
        for entry in rows:
            loc = Text.assemble((display_path(entry.path, cwd), "cyan"), (f":{entry.todo.line}", "bright_black"))
            table.add_row(*_row(entry, short_ids, loc))
        if rows:
            console.print(table)
        shown = len(rows)
    else:
        first = True
        for members in ordered_groups(entries, group, cwd):
            rows = [e for e in members if visible(e)]
            if not rows:
                continue
            if not first:
                console.print()
            first = False
            console.print(Text.assemble(_header(members, group, cwd), "  ", _progress(members)))
            by_location = group in ("name", "value")
            table = _table("left" if by_location else "right")
            for entry in rows:
                if by_location:
                    loc = Text(f"{display_path(entry.path, cwd)}:{entry.todo.line}", style="bright_black")
                else:
                    loc = Text(f"L{entry.todo.line}", style="bright_black")
                table.add_row(*_row(entry, short_ids, loc, with_text=group != "value"))
            console.print(table)
            shown += len(rows)

    render_summary(console, entries)
    return shown


def render_summary(console: Console, entries: Sequence[Entry]) -> None:
    if not entries:
        console.print(Text("No todos found.", style="bright_black italic"))
        return
    done = sum(e.todo.checked for e in entries)
    files = len({e.path for e in entries})
    console.print()
    console.print(
        Text.assemble(
            (f"{len(entries) - done} open", "bold yellow"),
            ("  ·  ", "bright_black"),
            (f"{done} done", "bold green"),
            ("  ·  ", "bright_black"),
            (f"{files} file{'s' if files != 1 else ''}", "cyan"),
        )
    )


def render_change(console: Console, entry: Entry, checked: bool, short_id: str, cwd: Path, *, changed: bool) -> None:
    if not changed:
        verb = Text("already " + ("checked" if checked else "unchecked"), style="bright_black")
    elif checked:
        verb = Text("checked  ", style="bold green")
    else:
        verb = Text("unchecked", style="bold yellow")
    icon = Text(ICON_DONE, style="bold green") if checked else Text(ICON_OPEN, style="bold yellow")
    console.print(
        Text.assemble(
            icon,
            " ",
            verb,
            " ",
            (short_id, "magenta"),
            " ",
            (f"{display_path(entry.path, cwd)}:{entry.todo.line}", "cyan"),
            "  ",
            entry.todo.text,
        )
    )


def render_counts(console: Console, overall: Tally, groups: Sequence[Tally], *, group: Group, omitted: int = 0) -> None:
    """Print a per-group count table (when grouped) and the overall totals.
    ``omitted`` is the number of further groups cut off by a limit."""
    if groups:
        table = Table(box=None, pad_edge=False, show_edge=False, header_style="bold")
        table.add_column(group.capitalize(), style="cyan", overflow="fold")
        table.add_column("Open", justify="right", style="yellow")
        table.add_column("Done", justify="right", style="green")
        table.add_column("Total", justify="right")
        table.add_column("Progress", no_wrap=True)
        for t in groups:
            table.add_row(t.label, str(t.open), str(t.done), str(t.total), _bar(t.done, t.total))
        console.print(table)
        if omitted:
            console.print(Text(f"… {omitted} more {group} group{'s' if omitted != 1 else ''}", style="bright_black"))
        console.print()
    console.print(
        Text.assemble(
            (f"{overall.open} open", "bold yellow"),
            ("  ·  ", "bright_black"),
            (f"{overall.done} done", "bold green"),
            ("  ·  ", "bright_black"),
            (f"{overall.total} total", "bold"),
            (f" ({overall.percent_done:.0f}% done)", "bright_black"),
            ("  ·  ", "bright_black"),
            (_plural(overall.files, "file"), "cyan"),
        )
    )
