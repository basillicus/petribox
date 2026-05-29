"""Lifecycle commands: create, list, status, up, down, delete, config."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from rich.table import Table

from .. import cloudinit, incus, meta, presets
from ..config_loader import load_config
from ._common import (
    console,
    fail,
    get_instance_or_exit,
    mount_device_name,
    resolve_resources,
    wait_until_running,
)

SSH_KEY_CANDIDATES = ["id_ed25519.pub", "id_rsa.pub", "id_ecdsa.pub"]


def _discover_ssh_key(explicit: "Path | None") -> "str | None":
    """Return the public key text, or None if no key is available."""
    if explicit:
        if not explicit.exists():
            fail(f"SSH key not found: {explicit}")
        return explicit.read_text().strip()
    ssh_dir = Path.home() / ".ssh"
    for candidate in ("petribox_id_ed25519.pub", *SSH_KEY_CANDIDATES):
        path = ssh_dir / candidate
        if path.exists():
            return path.read_text().strip()
    return None


def cmd_create(args):
    """Create a new dish (Incus instance)."""
    name = args.name
    if not name:
        fail("Dish name is required. Usage: petribox create <name> [options]")

    if not incus.available():
        fail("incus is not installed. Run: petribox initial-setup")

    if incus.exists(name):
        fail(f"Dish '{name}' already exists")

    is_vm = not getattr(args, "container", False)
    image = args.image or incus.DEFAULT_IMAGE

    # Build package config: preset merged with optional --config file.
    config: dict = {}
    if args.preset:
        config = presets.package_config(args.preset)
        console.print(f"[dim]Preset: {args.preset}[/dim]")
    if args.config:
        file_config = load_config(args.config)
        config = presets.merge_config(config, file_config) if config else file_config
        console.print(f"[dim]Config: {args.config}[/dim]")

    preset_meta = presets.get_preset(args.preset) if args.preset else {}
    ram, cpus, disk = resolve_resources(args, preset_meta)

    ssh_key = _discover_ssh_key(args.ssh_key)
    if ssh_key is None:
        console.print(
            "[yellow]No SSH key found — SSH login disabled.[/yellow] "
            "Use 'petribox connect' (incus exec) or add a key with --ssh-key."
        )

    agent_config = None
    if getattr(args, "agent", None):
        from ..agents import get_agent_config

        agent_config = get_agent_config(args.agent)
        console.print(f"[dim]Agent: {agent_config['name']}[/dim]")

    user_data = cloudinit.build_user_data(
        hostname=name,
        user=args.user,
        ssh_key=ssh_key or "",
        config=config,
        agent_config=agent_config,
        password=args.password,
        shell=args.shell,
    )

    instance_config = {
        "limits.cpu": str(cpus),
        "limits.memory": f"{ram}MiB",
        "cloud-init.user-data": user_data,
        f"{meta.PREFIX}user": args.user,
        f"{meta.PREFIX}preset": args.preset or "",
        f"{meta.PREFIX}agent": getattr(args, "agent", "") or "",
        f"{meta.PREFIX}dotfiles": args.dotfiles or "",
        f"{meta.PREFIX}shell": args.shell,
        f"{meta.PREFIX}created": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    console.print(f"[green]=== Creating dish: {name} ===[/green]")
    incus.init(
        name,
        image,
        vm=is_vm,
        config=instance_config,
        device_overrides=[f"root,size={disk}GiB"],
    )
    console.print(f"[green]✓ Instance defined[/green] ({'VM' if is_vm else 'container'}, {ram}MB RAM, {cpus} CPU, {disk}GB disk)")

    if is_vm:
        # RHEL-family VM images (Rocky) need the incus-agent config delivered as
        # a CDROM (requirements.cdrom_agent); it is not auto-added.
        incus.device_add(name, "agent", "disk", source="agent:config")

    # Attach mounts before first boot so they are present immediately.
    for spec in args.mounts or []:
        host_path, _, vm_path = spec.partition(":")
        if not vm_path:
            fail(f"Invalid --mount '{spec}', expected HOST_PATH:VM_PATH")
        incus.device_add(
            name, mount_device_name(vm_path), "disk",
            source=str(Path(host_path).expanduser().resolve()), path=vm_path,
        )
        console.print(f"[dim]Mount: {host_path} -> {vm_path}[/dim]")

    incus.start(name)
    console.print("[dim]First boot runs cloud-init (packages, mise, agent) — 1-3 min.[/dim]")

    vm_ip = wait_until_running(name)
    if vm_ip:
        console.print(f"[green]✓ Dish ready at {vm_ip}[/green]")
    else:
        console.print("[yellow]Dish started; network not up yet. Check: petribox status " + name + "[/yellow]")

    if args.dotfiles:
        from ..dotfiles import apply_dotfiles

        console.print("[yellow]Applying dotfiles...[/yellow]")
        try:
            apply_dotfiles(name, args.user, args.dotfiles)
            console.print("[green]✓ Dotfiles applied[/green]")
        except Exception as exc:  # noqa: BLE001 - surface but don't fail create
            console.print(f"[red]Failed to apply dotfiles: {exc}[/red]")

    console.print()
    console.print(f"[green]Dish '{name}' is ready![/green]")
    console.print(f"[dim]Connect: petribox connect {name}[/dim]")
    console.print(f"[dim]Stop:    petribox down {name}[/dim]")
    console.print(f"[dim]Delete:  petribox delete {name}[/dim]")


def cmd_list(args):
    """List all dishes."""
    instances = incus.list_instances()
    if not instances:
        console.print("[yellow]No dishes found[/yellow]")
        return

    table = Table(title="Petribox dishes")
    table.add_column("Name", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Type")
    table.add_column("RAM", justify="right")
    table.add_column("CPUs", justify="right")
    table.add_column("IP", style="dim")
    table.add_column("Preset", style="dim")

    for inst in instances:
        config = inst.get("config", {}) or {}
        ip = incus.first_ipv4(inst) or ""
        itype = "vm" if inst.get("type") == "virtual-machine" else "container"
        table.add_row(
            inst.get("name", ""),
            (inst.get("status") or "").lower(),
            itype,
            config.get("limits.memory", "-"),
            config.get("limits.cpu", "-"),
            ip,
            config.get(f"{meta.PREFIX}preset", "") or "",
        )
    console.print(table)


def cmd_status(args):
    """Show detailed status of a dish."""
    inst = get_instance_or_exit(args.name)
    config = inst.get("config", {}) or {}
    status, ip = incus.state(args.name)
    info = meta.get_meta(args.name)

    console.print(f"[green]=== {args.name} ===[/green]")
    console.print(f"  Status:   {status}")
    console.print(f"  Type:     {'vm' if inst.get('type') == 'virtual-machine' else 'container'}")
    console.print(f"  IP:       {ip or 'N/A'}")
    console.print(f"  RAM:      {config.get('limits.memory', '-')}")
    console.print(f"  CPUs:     {config.get('limits.cpu', '-')}")
    console.print(f"  Preset:   {info.get('preset') or 'none'}")
    console.print(f"  Agent:    {info.get('agent') or 'none'}")
    console.print(f"  Dotfiles: {info.get('dotfiles') or 'none'}")
    console.print(f"  Created:  {info.get('created') or 'unknown'}")

    devices = incus.device_show(args.name)
    mounts = {k: v for k, v in devices.items() if v.get("type") == "disk" and "source" in v}
    forwards = {k: v for k, v in devices.items() if v.get("type") == "proxy"}
    if mounts:
        console.print("  Mounts:")
        for dev in mounts.values():
            console.print(f"    {dev.get('source')} -> {dev.get('path')}")
    if forwards:
        console.print("  Port forwards:")
        for dev in forwards.values():
            console.print(f"    {dev.get('listen')} -> {dev.get('connect')}")

    console.print()
    if status == "running":
        console.print(f"[dim]Connect: petribox connect {args.name}[/dim]")
    elif status:
        console.print(f"[dim]Start: petribox up {args.name}[/dim]")


def cmd_up(args):
    """Start a stopped dish."""
    get_instance_or_exit(args.name)
    status, _ = incus.state(args.name)
    if status == "running":
        console.print(f"[yellow]Dish '{args.name}' is already running[/yellow]")
        return
    console.print(f"[green]Starting '{args.name}'...[/green]")
    incus.start(args.name)
    ip = wait_until_running(args.name, timeout=60)
    if ip:
        console.print(f"[green]✓ '{args.name}' running at {ip}[/green]")
    else:
        console.print(f"[yellow]'{args.name}' started (network not up yet)[/yellow]")


def cmd_down(args):
    """Stop a running dish."""
    get_instance_or_exit(args.name)
    status, _ = incus.state(args.name)
    if status and status != "running":
        console.print(f"[yellow]Dish '{args.name}' is already stopped[/yellow]")
        return
    console.print(f"[yellow]Stopping '{args.name}'...[/yellow]")
    incus.stop(args.name)
    console.print(f"[green]✓ '{args.name}' stopped[/green]")


def cmd_delete(args):
    """Delete a dish and its resources."""
    get_instance_or_exit(args.name)
    if not args.force:
        console.print(f"[yellow]This permanently deletes dish '{args.name}' and its disk.[/yellow]")
        try:
            if input("Are you sure? [y/N]: ").strip().lower() != "y":
                console.print("[dim]Deletion cancelled[/dim]")
                return
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Deletion cancelled[/dim]")
            return
    console.print(f"[red]Deleting '{args.name}'...[/red]")
    incus.delete(args.name, force=True)  # also removes attached proxy/disk devices
    console.print(f"[green]✓ '{args.name}' deleted[/green]")


def cmd_config(args):
    """View configuration presets or a dish's settings."""
    if args.action == "list":
        console.print("[green]Available presets:[/green]")
        for pname, preset in presets.PRESETS.items():
            console.print(f"  [cyan]{pname}[/cyan]: {preset['description']}")
    elif args.action == "show":
        if not args.name:
            fail("Dish name required: petribox config show <name>")
        cmd_status(args)
    elif args.action == "edit":
        console.print("[yellow]Edit the YAML config file directly, then recreate the dish.[/yellow]")
