"""Command-line interface (the imperative shell)."""

from __future__ import annotations

import json
import os
import tempfile
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

import click
from rich.console import Console
from rich.markup import escape

from . import __version__
from .counting import SORTS, Sort, summarise
from .discovery import discover
from .editing import EditError, apply_states
from .grouping import GROUPS, KINDS, Group, Kind, Status, by_kind, display_path, status_filter
from .ids import shortest_unique_prefixes
from .models import Entry
from .render import render, render_change, render_counts
from .resolve import location_path, resolve
from .scanning import UnreadableFile, collect, read_text, scan_file_text

Action = Literal["check", "uncheck", "toggle"]


class DefaultToList(click.Group):
    """Run ``list`` when no sub-command is given, so ``tick foo.tex`` works."""

    def parse_args(self, ctx: click.Context, args: list[str]) -> list[str]:
        if not args or (args[0] not in self.commands and args[0] not in ("--help", "-h", "--version")):
            args = ["list", *args]
        return super().parse_args(ctx, args)


def _consoles(no_color: bool) -> tuple[Console, Console]:
    out = Console(no_color=no_color or None, highlight=False)
    err = Console(stderr=True, no_color=no_color or None, highlight=False)
    return out, err


def _scan(paths: Sequence[Path], err: Console, quiet: bool) -> list[Entry]:
    try:
        files = discover(paths or [Path(".")])
    except FileNotFoundError as exc:
        raise click.BadParameter(f"no such file or directory: {exc.args[0]}", param_hint="PATHS") from exc

    def warn(message: str) -> None:
        if not quiet:
            err.print(f"[yellow]warning:[/] {message}", markup=True, highlight=False)

    return collect(files, warn=warn)


_path_type = click.Path(exists=True, path_type=Path)
_no_color = click.option("--no-color", is_flag=True, envvar="NO_COLOR", help="Disable colour output.")
_quiet = click.option("-q", "--quiet", is_flag=True, help="Hide warnings about skipped files.")


@click.group(cls=DefaultToList, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "--version")
def main() -> None:
    """Find, list and tick off todos hiding in code comments.

    \b
    Recognised inside comments (any comment syntax, start or end of line):
      - [ ] open item        - [x] done item
      TODO: something        TODO: [x] something done
      FIXME(me): something

    Running with no sub-command lists todos, e.g. `tick src/ notes.tex`.
    """


_status_options = [
    click.option("-o", "--open", "only_open", is_flag=True, help="Only unticked todos."),
    click.option("-d", "--done", "only_done", is_flag=True, help="Only ticked todos."),
]
_kind_option = click.option(
    "-k",
    "--kind",
    "kinds",
    multiple=True,
    type=click.Choice(KINDS),
    help="Only todos of this kind: box (- [ ]), todo (TODO:), fixme (FIXME:). Repeatable.",
)
_GROUP_HELP = (
    "Group by file path, by file name (same-named files together), by todo value (identical todos "
    "together), or not at all."
)


def _group_option(default: Group) -> Any:
    return click.option(
        "-g", "--group", type=click.Choice(GROUPS), default=default, show_default=True, help=_GROUP_HELP
    )


def _status(only_open: bool, only_done: bool) -> Status:
    if only_open and only_done:
        raise click.UsageError("--open and --done are mutually exclusive")
    return "open" if only_open else "done" if only_done else "all"


def _with(*decorators: Any) -> Any:
    def apply(func: Any) -> Any:
        for decorator in reversed(decorators):
            func = decorator(func)
        return func

    return apply


@main.command("list")
@click.argument("paths", nargs=-1, type=_path_type)
@_with(*_status_options, _kind_option, _group_option("file"), _no_color, _quiet)
def list_cmd(
    paths: tuple[Path, ...],
    only_open: bool,
    only_done: bool,
    kinds: tuple[Kind, ...],
    group: Group,
    no_color: bool,
    quiet: bool,
) -> None:
    """List todos in PATHS (default: current directory, minus gitignored files)."""
    status = _status(only_open, only_done)
    out, err = _consoles(no_color)
    entries = _scan(paths, err, quiet)
    short = shortest_unique_prefixes([e.id for e in entries])
    render(out, by_kind(entries, kinds), short, cwd=Path.cwd(), group=group, visible=status_filter(status))


@main.command("count")
@click.argument("paths", nargs=-1, type=_path_type)
@_with(*_status_options, _kind_option, _group_option("none"))
@click.option("-s", "--sort", type=click.Choice(SORTS), default="open", show_default=True, help="Order of groups.")
@click.option("-n", "--limit", type=click.IntRange(min=1), help="Show only the first N groups.")
@click.option("--json", "as_json", is_flag=True, help="Print machine-readable JSON.")
@click.option("--exit-code", is_flag=True, help="Exit with status 1 if any open todos are counted (for CI/hooks).")
@_with(_no_color, _quiet)
def count_cmd(
    paths: tuple[Path, ...],
    only_open: bool,
    only_done: bool,
    kinds: tuple[Kind, ...],
    group: Group,
    sort: Sort,
    limit: int | None,
    as_json: bool,
    exit_code: bool,
    no_color: bool,
    quiet: bool,
) -> None:
    """Count todos in PATHS (default: current directory, minus gitignored files).

    \b
    With -o or -d (and no -g) just the number is printed, for scripts:
      tick count -o          ->  9
    """
    status = _status(only_open, only_done)
    out, err = _consoles(no_color)
    keep = status_filter(status)
    entries = [e for e in by_kind(_scan(paths, err, quiet), kinds) if keep(e)]
    overall, groups = summarise(entries, group, Path.cwd(), sort=sort)
    omitted = max(0, len(groups) - limit) if limit is not None else 0
    groups = groups[: len(groups) - omitted]

    if as_json:
        payload: dict[str, Any] = overall.as_dict()
        del payload["label"]
        if group != "none":
            payload["group"] = group
            payload["groups"] = [t.as_dict() for t in groups]
            payload["omitted_groups"] = omitted
        click.echo(json.dumps(payload, indent=2))
    elif status != "all" and group == "none":
        click.echo(overall.total)
    else:
        render_counts(out, overall, groups, group=group, omitted=omitted)

    if exit_code and overall.open:
        raise SystemExit(1)


def _write_atomic(path: Path, text: str) -> None:
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tick")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.chmod(tmp, path.stat().st_mode & 0o7777)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _apply(
    action: Action,
    refs: tuple[str, ...],
    paths: tuple[Path, ...],
    text_only: bool,
    allow_many: bool,
    dry_run: bool,
    no_color: bool,
    quiet: bool,
) -> None:
    out, err = _consoles(no_color)
    scope = list(paths) or [Path(".")]
    scope += [p for p in (location_path(r) for r in refs) if p is not None]
    entries = _scan(scope, err, quiet)
    short = shortest_unique_prefixes([e.id for e in entries])
    cwd = Path.cwd()

    # Resolve everything before touching any file: all-or-nothing.
    selected: dict[tuple[Path, str], Entry] = {}
    problems: list[str] = []
    for ref in refs:
        res = resolve(ref, entries, text_only=text_only)
        if not res.matches:
            problems.append(f"no todo matches [bold]{escape(repr(ref))}[/]")
        elif len(res.matches) > 1 and not allow_many:
            lines = "\n".join(
                f"    [magenta]{short[e.id]}[/]  "
                f"[cyan]{display_path(e.path, cwd)}:{e.todo.line}[/]  {escape(e.todo.text)}"
                for e in res.matches
            )
            problems.append(
                f"{escape(repr(ref))} is ambiguous ({len(res.matches)} matches by {res.how}); "
                f"use an id, path:line, or --all:\n{lines}"
            )
        else:
            for entry in res.matches:
                selected[(entry.path, entry.id)] = entry
    if problems:
        for problem in problems:
            err.print(f"[red]error:[/] {problem}", highlight=False)
        raise SystemExit(1)

    by_file: defaultdict[Path, list[tuple[Entry, bool]]] = defaultdict(list)
    for entry in selected.values():
        target = {"check": True, "uncheck": False}.get(action, not entry.todo.checked)
        by_file[entry.path].append((entry, target))

    for path, changes in by_file.items():
        try:
            text = read_text(path)
        except UnreadableFile as exc:
            raise click.ClickException(str(exc)) from exc
        current = {(t.line, t.text) for t in scan_file_text(path, text)}
        if any((e.todo.line, e.todo.text) not in current for e, _ in changes):  # pragma: no cover - race
            raise click.ClickException(f"{path} changed while running; nothing written")
        real = [(e.todo, c) for e, c in changes if e.todo.checked != c or not e.todo.has_box]
        try:
            new_text = apply_states(text, real)
        except EditError as exc:
            raise click.ClickException(f"{path}: {exc}") from exc
        if new_text != text and not dry_run:
            _write_atomic(path, new_text)
        for entry, checked in sorted(changes, key=lambda c: c[0].todo.line):
            changed = entry.todo.checked != checked or not entry.todo.has_box
            render_change(out, entry, checked, short[entry.id], cwd, changed=changed)

    if dry_run:
        out.print("[bright_black italic](dry run: no files were modified)[/]")


def _edit_command(action: Action, help_text: str) -> Any:
    @main.command(action, help=help_text)
    @click.argument("refs", nargs=-1, required=True)
    @click.option(
        "-p", "--path", "paths", multiple=True, type=_path_type, help="Restrict the search (repeatable). Default: ."
    )
    @click.option("-t", "--text", "text_only", is_flag=True, help="Treat REFS as todo text only (not ids/locations).")
    @click.option("-a", "--all", "allow_many", is_flag=True, help="Apply to every match of an ambiguous ref.")
    @click.option("-n", "--dry-run", is_flag=True, help="Show what would change without writing.")
    @_no_color
    @_quiet
    def command(
        refs: tuple[str, ...],
        paths: tuple[Path, ...],
        text_only: bool,
        allow_many: bool,
        dry_run: bool,
        no_color: bool,
        quiet: bool,
    ) -> None:
        _apply(action, refs, paths, text_only, allow_many, dry_run, no_color, quiet)

    return command


_REF_HELP = """

REFS can be an id (or unique prefix) as shown by `list`, a `path:line`
location, or (part of) the todo's text, case-insensitive.
"""

check = _edit_command("check", "Tick todos. Bare TODO: comments gain a [x]." + _REF_HELP)
uncheck = _edit_command("uncheck", "Untick todos. Bare TODO: comments gain a [ ]." + _REF_HELP)
toggle = _edit_command("toggle", "Flip todos between ticked and unticked." + _REF_HELP)


if __name__ == "__main__":  # pragma: no cover
    main()
