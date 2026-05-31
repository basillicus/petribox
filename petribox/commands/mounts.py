"""Mount commands: share host directories via Incus disk devices (virtiofs for VMs)."""

from __future__ import annotations

from pathlib import Path

from .. import incus
from ._common import console, fail, get_instance_or_exit, mount_device_name


def cmd_mount(args):
    """Attach a host directory to a running dish.

    For VMs this is virtiofs; the incus-agent mounts it at vm_path automatically.
    Hot-pluggable, so no recreate/restart is required.
    """
    get_instance_or_exit(args.name)
    host_path = Path(args.host_path).expanduser().resolve()
    if not host_path.exists():
        fail(f"Host path does not exist: {host_path}")

    device = mount_device_name(args.vm_path)
    console.print(f"[yellow]Mounting {host_path} -> {args.vm_path}[/yellow]")
    incus.device_add(args.name, device, "disk", source=str(host_path), path=args.vm_path)
    console.print("[green]✓ Mount attached[/green]")


def cmd_umount(args):
    """Detach a previously attached mount by its guest path."""
    get_instance_or_exit(args.name)
    device = mount_device_name(args.vm_path)
    console.print(f"[yellow]Removing mount at {args.vm_path}[/yellow]")
    incus.device_remove(args.name, device)
    console.print("[green]✓ Mount removed[/green]")
