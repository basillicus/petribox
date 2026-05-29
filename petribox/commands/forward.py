"""Port-forward commands backed by Incus proxy devices.

Replaces the old SSH-tunnel + PID-tracking machinery. Proxy devices are
persistent (survive host reboots) and managed entirely by Incus, so there is
no stale state to clean.
"""

from __future__ import annotations

from rich.table import Table

from .. import incus
from ._common import console, get_instance_or_exit, proxy_device_name, require_running


def _forwards(name: str) -> dict:
    return {
        dev: props
        for dev, props in incus.device_show(name).items()
        if props.get("type") == "proxy"
    }


def cmd_port_forward(args):
    """Forward a dish port to localhost via a proxy device."""
    get_instance_or_exit(args.name)
    require_running(args.name)

    local_port = args.local_port or args.port
    device = proxy_device_name(args.port)

    if device in _forwards(args.name):
        console.print(f"[green]Forward already exists for port {args.port}[/green]")
        return

    incus.device_add(
        args.name, device, "proxy",
        listen=f"tcp:127.0.0.1:{local_port}",
        connect=f"tcp:127.0.0.1:{args.port}",
    )
    console.print("[green]✓ Port forward active[/green]")
    console.print(f"  localhost:{local_port} -> {args.name}:{args.port}")
    console.print(f"[dim]Stop with: petribox port-forward-stop {args.name} {args.port}[/dim]")


def cmd_port_forward_list(args):
    """List active proxy-device port forwards across all dishes."""
    instances = incus.list_instances()
    rows = []
    for inst in instances:
        name = inst.get("name", "")
        for props in _forwards(name).values():
            rows.append((name, props.get("connect", ""), props.get("listen", "")))

    if not rows:
        console.print("[dim]No active port forwards[/dim]")
        return

    table = Table(title="Port forwards")
    table.add_column("Dish", style="cyan")
    table.add_column("Dish port")
    table.add_column("Local listen")
    for name, connect, listen in rows:
        table.add_row(name, connect, listen)
    console.print(table)


def cmd_port_forward_stop(args):
    """Remove a port forward."""
    get_instance_or_exit(args.name)
    device = proxy_device_name(args.port)
    if device not in _forwards(args.name):
        console.print(f"[yellow]No forward for '{args.name}' port {args.port}[/yellow]")
        return
    incus.device_remove(args.name, device)
    console.print(f"[green]✓ Forward stopped for port {args.port}[/green]")


def cmd_port_forward_clean(args):
    """Proxy devices are Incus-managed; nothing to clean. Informational."""
    console.print(
        "[green]Port forwards are Incus proxy devices — persistent and "
        "self-managed, so there is no stale state to clean.[/green]"
    )
    console.print("[dim]List them with: petribox port-forward-list[/dim]")
