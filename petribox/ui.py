"""Terminal output: coloured steps, hints, errors, spinners and tables.

Messages are plain text (escaped), styles come from the helper you call.
rich drops the colours by itself when output is not a terminal.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager

from rich.console import Console
from rich.markup import escape
from rich.table import Table
from rich.text import Text  # noqa: F401  (re-exported for cells)

# soft_wrap: long commands and paths stay one line, so they copy-paste whole.
console = Console(highlight=False, soft_wrap=True)
err_console = Console(stderr=True, highlight=False, soft_wrap=True)


def step(msg: str) -> None:
    """A stage of a longer job (build, new)."""
    console.print(f"[bold green]==>[/bold green] [bold]{escape(msg)}[/bold]")


def ok(msg: str) -> None:
    console.print(f"[green]✓[/green] {escape(msg)}")


def info(msg: str) -> None:
    console.print(f"[dim]{escape(msg)}[/dim]")


def warn(msg: str) -> None:
    err_console.print(f"[yellow]! {escape(msg)}[/yellow]")


def hint(label: str, command: str) -> None:
    """`label: command`, the command highlighted for copy-paste."""
    console.print(f"[dim]{escape(label)}:[/dim] [cyan]{escape(command)}[/cyan]")


def error(msg: str) -> None:
    err_console.print(f"[bold red]Error:[/bold red] {escape(msg)}")


def fail(msg: str) -> None:
    """Report and exit; hints about what to do next are shown first."""
    from . import hints  # hints uses this module
    error(msg)
    hints.show(msg)
    sys.exit(1)


@contextmanager
def spinner(msg: str):
    """Spin while waiting on something that prints nothing (boot, shutdown)."""
    with console.status(f"[cyan]{escape(msg)}[/cyan]", spinner="dots"):
        yield


def table(columns: list[tuple], rows: list[tuple], title: str = "") -> None:
    """columns: (header, style) or (header, style, keep) tuples; cells: plain
    strings (escaped here) or Text. The first column and those with keep=True
    (names, addresses: things to copy) are never wrapped or cut."""
    t = Table(title=title or None, title_justify="left", header_style="bold")
    for i, (header, style, *keep) in enumerate(columns):
        whole = i == 0 or bool(keep and keep[0])
        t.add_column(header, style=style or None, no_wrap=whole, min_width=len(header) if whole else None)
    for row in rows:
        t.add_row(*(c if isinstance(c, Text) else escape(c) for c in row))
    console.print(t)


STATE_STYLE = {"Running": "green", "Stopped": "dim", "Frozen": "yellow", "Error": "red"}


def state(value: str) -> Text:
    return Text(value, style=STATE_STYLE.get(value, ""))
