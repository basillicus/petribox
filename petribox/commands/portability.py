"""Portability: export/import a dish, migrate to a remote, manage remotes.

This is the "breed locally, carry it anywhere" capability. `incus export`
produces a self-contained backup (no backing-file chain), and `incus copy` to a
remote migrates a dish to another host or a cloud Incus server.
"""

from __future__ import annotations

from pathlib import Path

from rich.table import Table

from .. import incus, meta
from ._common import console, fail, get_instance_or_exit


def _warn_secrets(name: str, inst: dict) -> None:
    """Exports carry the dish's disk, so any env file inside travels too."""
    config = inst.get("config", {}) or {}
    keys = config.get(f"{meta.PREFIX}env_keys", "")
    # Dishes made by older petribox versions baked --env values into user-data.
    legacy = "export " in config.get("cloud-init.user-data", "")
    if keys or legacy:
        console.print(
            f"[yellow]Warning: this export will contain env vars / secrets"
            f"{' (' + keys.replace(',', ', ') + ')' if keys else ''}.[/yellow]"
        )
        console.print(f"[dim]To strip them first: petribox up {name} && "
                      f"petribox env unset {name} --all && petribox down {name}[/dim]")
    if legacy:
        console.print("[dim]Its cloud-init user-data also holds values from an older "
                      "petribox; recreate the dish to remove those.[/dim]")


def cmd_export(args):
    """Export a dish to a portable tarball (incus backup format)."""
    inst = get_instance_or_exit(args.name)
    output = args.output or f"{args.name}.tar.gz"
    _warn_secrets(args.name, inst)
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
