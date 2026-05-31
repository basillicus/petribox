"""Portability: export/import a dish, migrate to a remote, manage remotes.

This is the "breed locally, carry it anywhere" capability. `incus export`
produces a self-contained backup (no backing-file chain), and `incus copy` to a
remote migrates a dish to another host or a cloud Incus server.
"""

from __future__ import annotations

from pathlib import Path

from rich.table import Table

from .. import incus
from ._common import console, fail, get_instance_or_exit


def cmd_export(args):
    """Export a dish to a portable tarball (incus backup format)."""
    get_instance_or_exit(args.name)
    output = args.output or f"{args.name}.tar.gz"
    console.print(f"[yellow]Exporting '{args.name}' -> {output}[/yellow]")
    console.print("[dim]The dish should be stopped for a consistent export.[/dim]")
    incus.export(args.name, str(output), instance_only=True)
    console.print(f"[green]✓ Exported to {output}[/green]")
    console.print(
        "[dim]Move it to another machine and run: petribox import "
        f"{Path(output).name}[/dim]"
    )


def cmd_import(args):
    """Import a dish from a tarball produced by `petribox export`."""
    path = Path(args.file)
    if not path.exists():
        fail(f"File not found: {path}")
    console.print(f"[yellow]Importing {path}...[/yellow]")
    incus.import_(str(path), args.name)
    console.print("[green]✓ Imported[/green]")
    console.print("[dim]Start it with: petribox up <name>[/dim]")


def cmd_move(args):
    """Migrate a dish to a remote Incus server (e.g. a cloud host)."""
    get_instance_or_exit(args.name)
    dest = args.dest if ":" in args.dest else f"{args.dest}:{args.name}"
    console.print(f"[yellow]Migrating '{args.name}' -> {dest}[/yellow]")
    if args.copy:
        incus.copy(args.name, dest)
        console.print(f"[green]✓ Copied to {dest} (local copy kept)[/green]")
    else:
        incus.move(args.name, dest)
        console.print(f"[green]✓ Moved to {dest}[/green]")


def cmd_remote_add(args):
    """Register a remote Incus server so one CLI can drive scattered hosts."""
    incus.remote_add(args.name, args.url)
    console.print(f"[green]✓ Remote '{args.name}' added[/green]")


def cmd_remote_list(args):
    remotes = incus.remote_list()
    if not remotes:
        console.print("[dim]No remotes configured[/dim]")
        return
    table = Table(title="Incus remotes")
    table.add_column("Name", style="cyan")
    table.add_column("URL", style="dim")
    for remote in remotes:
        table.add_row(remote.get("name", ""), remote.get("Addr") or remote.get("addr", ""))
    console.print(table)
