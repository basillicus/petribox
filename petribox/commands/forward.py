"""Port-forward commands backed by Incus proxy devices.

Proxy devices are persistent (survive host reboots) and managed entirely by
Incus, so there is no stale state to clean.

VM vs container proxy behaviour differs:
- Containers: userspace proxy, listen on 127.0.0.1 (accessible at localhost).
- VMs: NAT-only proxy; listen address must be a real host IP (non-loopback),
  and connect IP must be the VM's current IPv4. We use the incusbr0 bridge IP
  as the listen address. Note: the forward breaks if the VM's DHCP lease changes.
"""

from __future__ import annotations

import re
import subprocess

from rich.table import Table

from .. import incus
from ._common import console, fail, get_instance_or_exit, proxy_device_name, require_running


def _forwards(name: str) -> dict:
    return {
        dev: props
        for dev, props in incus.device_show(name).items()
        if props.get("type") == "proxy"
    }


def _bridge_ip() -> "str | None":
    """Return the host-side IPv4 of incusbr0 (the Incus bridge)."""
    proc = subprocess.run(
        ["ip", "addr", "show", "incusbr0"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return None
    m = re.search(r"inet (\d+\.\d+\.\d+\.\d+)/", proc.stdout)
    return m.group(1) if m else None


def cmd_port_forward(args):
    """Forward a dish port via a proxy device."""
    inst = get_instance_or_exit(args.name)
    require_running(args.name)

    local_port = args.local_port or args.port
    device = proxy_device_name(args.port)

    if device in _forwards(args.name):
        console.print(f"[green]Forward already exists for port {args.port}[/green]")
        return

    is_vm = inst.get("type") == "virtual-machine"

    if is_vm:
        vm_ip = incus.first_ipv4(inst)
        if not vm_ip:
            fail(f"'{args.name}' has no IPv4 address yet — wait for it to boot fully.")
        bridge_ip = _bridge_ip()
        if not bridge_ip:
            fail("Could not determine incusbr0 address. Is Incus initialised?")
        incus.device_add(
            args.name, device, "proxy",
            listen=f"tcp:{bridge_ip}:{local_port}",
            connect=f"tcp:{vm_ip}:{args.port}",
            nat="true",
        )
        console.print("[green]✓ Port forward active[/green]")
        console.print(f"  {bridge_ip}:{local_port} -> {args.name}:{args.port}")
        console.print(
            f"[dim]Access at http://{bridge_ip}:{local_port} "
            "(VM forwards use the bridge IP, not localhost)[/dim]"
        )
    else:
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
