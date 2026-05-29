"""
Sandbox Commands - Implementation of CLI commands
"""

import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

from .database import Dish, DishDB
from .libvirt_ops import (
    check_prereqs,
    create_seed_iso,
    create_vm,
    destroy_vm,
    get_vm_ip,
    get_vm_status,
    start_vm,
    undefine_vm,
    wait_for_vm,
)
from .ssh_ops import ssh_connect, ssh_mount, ssh_umount
from .mount_ops import setup_9p_mount, remove_9p_mount
from .dotfiles import apply_dotfiles
from .config_loader import load_config, apply_config_packages
from .tunnel_manager import TunnelManager

console = Console()


def cmd_create(args):
    """Create a new sandbox VM"""
    from .tui import run_create_tui

    # If no name provided and not using TUI, show error
    if not args.name and not args.tui:
        console.print("[red]Error: Sandbox name is required[/red]")
        console.print("Usage: sandbox create <name> [options]")
        console.print("   or: sandbox create --tui")
        sys.exit(1)

    name = args.name

    # Determine base image path
    if args.image:
        base_image = str(args.image.resolve())
    else:
        # Look for image in project directory
        project_dir = Path(__file__).parent.parent
        default_image = project_dir / "Rocky-9-GenericCloud-Base.latest.x86_64.qcow2"
        if default_image.exists():
            base_image = str(default_image.resolve())
        else:
            console.print("[red]Error: Base image not found[/red]")
            console.print(
                "Use --image to specify the path to Rocky-9-GenericCloud-Base.latest.x86_64.qcow2"
            )
            sys.exit(1)

    # Determine SSH key
    if args.ssh_key:
        ssh_key_path = args.ssh_key
    else:
        # Try common SSH key locations
        ssh_key_path = None
        for key_path in [
            Path.home() / ".ssh" / "id_ed25519.pub",
            Path.home() / ".ssh" / "id_rsa.pub",
            Path.home() / ".ssh" / "id_ecdsa.pub",
        ]:
            if key_path.exists():
                ssh_key_path = key_path
                break

    if not ssh_key_path or not ssh_key_path.exists():
        console.print("[red]Error: No SSH key found[/red]")
        console.print(
            "Generate one with: ssh-keygen -t ed25519"
        )
        console.print(
            "Or specify with: --ssh-key ~/.ssh/your_key.pub"
        )
        sys.exit(1)

    ssh_key = ssh_key_path.read_text().strip()

    console.print(f"[green]=== Creating Dish: {name} ===[/green]")

    # Check prerequisites
    check_prereqs()

    # Load config file if specified
    config = None
    if args.config:
        config = load_config(args.config)
        console.print(f"[dim]Loaded config: {args.config}[/dim]")

    # Apply preset if specified
    if args.preset:
        preset_config = get_preset_config(args.preset)
        if config:
            config = merge_configs(config, preset_config)
        else:
            config = preset_config
        console.print(f"[dim]Applied preset: {args.preset}[/dim]")

    # Create database record
    db = DishDB()
    existing = db.get_dish(name)
    if existing:
        console.print(f"[red]Error: Sandbox '{name}' already exists[/red]")
        sys.exit(1)

    dish = Dish(
        id=None,
        name=name,
        ram=args.ram,
        cpus=args.cpus,
        disk=args.disk,
        user=args.user,
        ssh_key=ssh_key,
        network=args.network,
        image=base_image,
        status="creating",
        created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        updated_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
        dotfiles_source=args.dotfiles,
        config_file=str(args.config) if args.config else None,
        preset=args.preset,
        notes=None,
    )

    dish = db.create_dish(sandbox)
    console.print(f"[dim]Database record created (ID: {sandbox.id})[/dim]")

    # Create seed ISO with cloud-init
    seed_iso = create_seed_iso(
        vm_name=name,
        vm_user=args.user,
        ssh_key=ssh_key,
        config=config,
        mounts=args.mounts,
        vm_password=args.password,
        shell=args.shell,
        agent=getattr(args, 'agent', None),
    )
    console.print(f"[green]✓ Seed ISO created[/green]")

    # Create VM
    create_vm(
        vm_name=name,
        ram=args.ram,
        cpus=args.cpus,
        disk_size=args.disk,
        base_image=base_image,
        seed_iso=seed_iso,
        network=args.network,
    )
    console.print(f"[green]✓ VM created[/green]")

    # Wait for VM to be ready
    console.print()
    console.print("[dim]First boot may take 2-3 minutes for cloud-init to complete[/dim]")
    console.print("[dim]Subsequent boots will be much faster (~15 seconds)[/dim]")
    console.print()
    vm_ip = wait_for_vm(name, args.network)

    if vm_ip:
        console.print(f"[green]✓ VM ready at {vm_ip}[/green]")
    else:
        console.print("[yellow]VM created but IP not yet available[/yellow]")
        console.print("[dim]It may still be initializing. Check with: sandbox status {}[/dim]".format(name))

    # Update status
    db.update_status(name, "running" if vm_ip else "stopped")

    # Apply dotfiles if specified
    if args.dotfiles and vm_ip:
        console.print("[yellow]Applying dotfiles...[/yellow]")
        try:
            apply_dotfiles(name, vm_ip, args.user, args.dotfiles)
            console.print("[green]✓ Dotfiles applied[/green]")
        except Exception as e:
            console.print(f"[red]Failed to apply dotfiles: {e}[/red]")

    # Setup 9p mounts if specified
    if args.mounts and args.mount_type == "9p":
        console.print("[yellow]Note: 9p mounts require VM restart to activate[/yellow]")
        console.print("[dim]Run 'sandbox down {} && sandbox up {}' to activate mounts[/dim]".format(name, name))
        for mount in args.mounts or []:
            host_path, vm_path = mount.split(":")
            db.add_mount(sandbox.id, host_path, vm_path, "9p")

    console.print()
    console.print("[green]========================================[/green]")
    console.print(f"[green]  Sandbox '{name}' is ready![/green]")
    console.print("[green]========================================[/green]")
    console.print()
    console.print(f"[dim]Connect: sandbox ssh {name}[/dim]")
    console.print(f"[dim]Stop:    sandbox down {name}[/dim]")
    console.print(f"[dim]Delete:  sandbox delete {name}[/dim]")

    if vm_ip:
        console.print()
        console.print(f"[dim]IP: {vm_ip}[/dim]")


def cmd_list(args):
    """List all sandboxes"""
    db = DishDB()

    if args.all:
        sandboxes = db.list_dishes(include_destroyed=True)
    else:
        sandboxes = db.list_dishes()

    if not sandboxes:
        console.print("[yellow]No sandboxes found[/yellow]")
        return

    table = Table(title="Sandbox VMs")
    table.add_column("Name", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("RAM", justify="right")
    table.add_column("CPUs", justify="right")
    table.add_column("Disk", justify="right")
    table.add_column("User")
    table.add_column("IP", style="dim")
    table.add_column("Created", style="dim")

    for sb in sandboxes:
        # Get actual VM status from libvirt
        actual_status = get_vm_status(sb.name)
        if actual_status:
            status = actual_status
        else:
            status = sb.status

        # Get IP if running
        ip = ""
        if status == "running":
            ip = get_vm_ip(sb.name, sb.network) or ""

        table.add_row(
            sb.name,
            status,
            f"{sb.ram} MB",
            str(sb.cpus),
            f"{sb.disk} GB",
            sb.user,
            ip,
            sb.created_at[:10] if sb.created_at else "",
        )

    console.print(table)


def cmd_up(args):
    """Start a sandbox"""
    db = DishDB()
    dish = db.get_dish(args.name)

    if not sandbox:
        console.print(f"[red]Error: Sandbox '{args.name}' not found[/red]")
        sys.exit(1)

    # Check if already running
    current_status = get_vm_status(args.name)
    if current_status == "running":
        console.print(f"[yellow]Sandbox '{args.name}' is already running[/yellow]")
        return

    console.print(f"[green]Starting sandbox '{args.name}'...[/green]")

    # Start VM
    start_vm(args.name)

    # Wait for it to be ready
    console.print("[yellow]Waiting for VM to boot...[/yellow]")
    vm_ip = wait_for_vm(args.name, sandbox.network, timeout=60)

    if vm_ip:
        console.print(f"[green]✓ Sandbox '{args.name}' is running at {vm_ip}[/green]")
        db.update_status(args.name, "running")
    else:
        console.print(f"[yellow]Sandbox '{args.name}' started (IP not yet available)[/yellow]")
        db.update_status(args.name, "running")


def cmd_down(args):
    """Stop a sandbox"""
    db = DishDB()
    dish = db.get_dish(args.name)

    if not sandbox:
        console.print(f"[red]Error: Sandbox '{args.name}' not found[/red]")
        sys.exit(1)

    # Check if already stopped
    current_status = get_vm_status(args.name)
    if current_status == "shut off":
        console.print(f"[yellow]Sandbox '{args.name}' is already stopped[/yellow]")
        return

    console.print(f"[yellow]Stopping sandbox '{args.name}'...[/yellow]")

    # Stop VM
    destroy_vm(args.name)

    db.update_status(args.name, "stopped")
    console.print(f"[green]✓ Sandbox '{args.name}' stopped[/green]")


def cmd_delete(args):
    """Delete a sandbox"""
    db = DishDB()
    dish = db.get_dish(args.name)

    if not sandbox:
        console.print(f"[red]Error: Sandbox '{args.name}' not found[/red]")
        sys.exit(1)

    if not args.force:
        console.print(f"[yellow]This will permanently delete sandbox '{args.name}'[/yellow]")
        console.print("[yellow]All data will be lost![/yellow]")
        # Simple confirmation
        try:
            response = input("Are you sure? [y/N]: ")
            if response.lower() != "y":
                console.print("[dim]Deletion cancelled[/dim]")
                return
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Deletion cancelled[/dim]")
            return

    console.print(f"[red]Deleting sandbox '{args.name}'...[/red]")

    # Destroy if running
    current_status = get_vm_status(args.name)
    if current_status == "running":
        destroy_vm(args.name)

    # Undefine VM (even if not in libvirt, ignore errors)
    try:
        undefine_vm(args.name)
    except Exception:
        pass  # VM might not exist in libvirt

    # Clean up seed ISO if it exists
    seed_iso = Path.home() / ".petribox" / "tmp" / f"{args.name}-seed.iso"
    if seed_iso.exists():
        seed_iso.unlink()

    # Remove from database (hard delete - allows reusing name)
    db.remove_dish(args.name)

    # Kill any active port-forward tunnels
    tunnel_mgr = TunnelManager()
    killed = tunnel_mgr.kill_all_for_dish(args.name)
    if killed > 0:
        console.print(f"[dim]Stopped {killed} port-forward tunnel(s)[/dim]")

    console.print(f"[green]✓ Sandbox '{args.name}' deleted[/green]")


def cmd_status(args):
    """Show detailed sandbox status"""
    db = DishDB()
    dish = db.get_dish(args.name)

    if not sandbox:
        console.print(f"[red]Error: Sandbox '{args.name}' not found[/red]")
        sys.exit(1)

    # Get actual VM status from libvirt
    vm_status = get_vm_status(args.name)
    vm_ip = get_vm_ip(args.name, sandbox.network) if vm_status == "running" else None

    console.print(f"[green]=== Status: {args.name} ===[/green]")
    console.print()
    console.print(f"  Database Status:  {sandbox.status}")
    console.print(f"  VM Status:        {vm_status or 'not in libvirt'}")
    console.print(f"  IP Address:       {vm_ip or 'N/A'}")
    console.print()
    console.print(f"  RAM:              {sandbox.ram} MB")
    console.print(f"  CPUs:             {sandbox.cpus}")
    console.print(f"  Disk:             {sandbox.disk} GB")
    console.print(f"  User:             {sandbox.user}")
    console.print(f"  Network:          {sandbox.network}")
    console.print()
    console.print(f"  Created:          {sandbox.created_at}")
    console.print(f"  Updated:          {sandbox.updated_at}")

    if sandbox.id:
        mounts = db.get_mounts(sandbox.id)
        if mounts:
            console.print()
            console.print("  Mounts:")
            for m in mounts:
                console.print(f"    {m['host_path']} -> {m['vm_path']} ({m['mount_type']})")

    console.print()
    if vm_status == "running" and vm_ip:
        console.print(f"[dim]Connect: sandbox ssh {args.name}[/dim]")
        console.print(f"[dim]Console: sandbox console {args.name}[/dim]")
    elif vm_status == "shut off":
        console.print(f"[dim]Start: sandbox up {args.name}[/dim]")
    else:
        console.print("[yellow]VM may still be initializing...[/yellow]")
        console.print("[dim]Check with: sudo virsh console <name>[/dim]")


def cmd_console(args):
    """Connect to VM serial console"""
    db = DishDB()
    dish = db.get_dish(args.name)

    if not sandbox:
        console.print(f"[red]Error: Sandbox '{args.name}' not found[/red]")
        sys.exit(1)

    vm_status = get_vm_status(args.name)
    if vm_status != "running":
        console.print(f"[yellow]Sandbox '{args.name}' is not running[/yellow]")
        console.print(f"[dim]Start it with: sandbox up {args.name}[/dim]")
        sys.exit(1)

    console.print(f"[dim]Connecting to console of '{args.name}'...[/dim]")
    console.print("[dim]Press Ctrl+] to disconnect[/dim]")
    console.print()

    subprocess.run(["sudo", "virsh", "console", args.name])


def cmd_ssh(args):
    """SSH into a sandbox (connect command)"""
    db = DishDB()
    dish = db.get_dish(args.name)

    if not sandbox:
        console.print(f"[red]Error: Sandbox '{args.name}' not found[/red]")
        sys.exit(1)

    # Get actual VM status from libvirt
    current_status = get_vm_status(args.name)

    # Sync database status if different
    if sandbox.status != current_status:
        db.update_status(args.name, current_status)

    if current_status != "running":
        console.print(f"[yellow]Sandbox '{args.name}' is not running (status: {current_status or 'unknown'})[/yellow]")
        console.print(f"[dim]Start it with: sandbox up {args.name}[/dim]")
        sys.exit(1)

    # Get IP
    vm_ip = get_vm_ip(args.name, sandbox.network)
    if not vm_ip:
        console.print(f"[red]Error: Could not determine IP for '{args.name}'[/red]")
        console.print("[dim]Check: virsh net-dhcp-leases default[/dim]")
        sys.exit(1)

    # Build SSH command and exec directly
    ssh_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        f"{sandbox.user}@{vm_ip}",
    ]

    # Add user command if provided
    if args.ssh_command:
        ssh_cmd.extend(args.ssh_command)

    # Exec SSH directly (replaces Python process)
    import os
    os.execvp("ssh", ssh_cmd)


def cmd_mount(args):
    """Mount host directory in sandbox"""
    db = DishDB()
    dish = db.get_dish(args.name)

    if not sandbox:
        console.print(f"[red]Error: Sandbox '{args.name}' not found[/red]")
        sys.exit(1)

    # Get VM status
    current_status = get_vm_status(args.name)
    if current_status != "running":
        console.print(f"[yellow]Sandbox '{args.name}' is not running[/yellow]")
        sys.exit(1)

    # Get IP
    vm_ip = get_vm_ip(args.name, sandbox.network)
    if not vm_ip:
        console.print("[red]Error: Could not determine VM IP[/red]")
        sys.exit(1)

    host_path = args.host_path.resolve()
    if not host_path.exists():
        console.print(f"[red]Error: Host path does not exist: {host_path}[/red]")
        sys.exit(1)

    console.print(f"[yellow]Mounting {host_path} -> {args.vm_path}[/yellow]")

    if args.type == "9p":
        # 9p mounts need to be configured at VM creation time
        console.print("[red]Error: 9p mounts must be configured at VM creation[/red]")
        console.print("[dim]Use sshfs for runtime mounting, or recreate VM with --mount[/dim]")
        sys.exit(1)
    else:
        # SSHFS mount
        ssh_mount(vm_ip, sandbox.user, host_path, args.vm_path)
        console.print("[green]✓ Mount created[/green]")

    # Record in database
    if sandbox.id:
        db.add_mount(sandbox.id, str(host_path), args.vm_path, args.type)


def cmd_umount(args):
    """Unmount directory from sandbox"""
    db = DishDB()
    dish = db.get_dish(args.name)

    if not sandbox:
        console.print(f"[red]Error: Sandbox '{args.name}' not found[/red]")
        sys.exit(1)

    # Get VM status
    current_status = get_vm_status(args.name)
    if current_status != "running":
        console.print(f"[yellow]Sandbox '{args.name}' is not running[/yellow]")
        sys.exit(1)

    # Get IP
    vm_ip = get_vm_ip(args.name, sandbox.network)
    if not vm_ip:
        console.print("[red]Error: Could not determine VM IP[/red]")
        sys.exit(1)

    console.print(f"[yellow]Unmounting {args.vm_path}[/yellow]")

    ssh_umount(vm_ip, sandbox.user, args.vm_path)
    console.print("[green]✓ Mount removed[/green]")


def cmd_config(args):
    """Manage sandbox configurations"""
    db = DishDB()

    if args.action == "list":
        # List available presets
        console.print("[green]Available presets:[/green]")
        for preset in ["minimal", "dev", "ai-researcher", "agentic"]:
            config = get_preset_config(preset)
            packages = config.get("packages", [])
            console.print(f"  [cyan]{preset}[/cyan]: {len(packages)} packages")

    elif args.action == "show":
        if not args.name:
            console.print("[red]Error: Sandbox name required[/red]")
            sys.exit(1)

        dish = db.get_dish(args.name)
        if not sandbox:
            console.print(f"[red]Error: Sandbox '{args.name}' not found[/red]")
            sys.exit(1)

        console.print(f"[green]Configuration for '{args.name}':[/green]")
        console.print(f"  RAM: {sandbox.ram} MB")
        console.print(f"  CPUs: {sandbox.cpus}")
        console.print(f"  Disk: {sandbox.disk} GB")
        console.print(f"  User: {sandbox.user}")
        console.print(f"  Preset: {sandbox.preset or 'none'}")
        console.print(f"  Dotfiles: {sandbox.dotfiles_source or 'none'}")
        console.print(f"  Config file: {sandbox.config_file or 'none'}")

        if sandbox.id:
            mounts = db.get_mounts(sandbox.id)
            if mounts:
                console.print("  Mounts:")
                for m in mounts:
                    console.print(f"    {m['host_path']} -> {m['vm_path']} ({m['mount_type']})")

            packages = db.get_packages(sandbox.id)
            if packages:
                console.print("  Packages:")
                for p in packages:
                    status = "✓" if p["installed"] else "○"
                    console.print(f"    {status} {p['name']}")

    elif args.action == "edit":
        console.print("[yellow]Interactive config editing not yet implemented[/yellow]")
        console.print("[dim]Edit the YAML config file directly instead[/dim]")


def get_preset_config(preset_name: str) -> dict:
    """Get a predefined configuration preset"""
    presets = {
        "minimal": {
            "packages": ["vim", "python3", "git", "curl"],
        },
        "dev": {
            "packages": [
                "vim",
                "python3",
                "git",
                "curl",
                "wget",
                "gcc",
                "make",
            ],
            "mise_packages": ["node@24"],
        },
        "ai-researcher": {
            "packages": [
                "vim",
                "python3",
                "python3-pip",
                "git",
                "curl",
                "wget",
                "gcc",
                "tmux",
            ],
            "mise_packages": ["python@3.12"],
            "pip_packages": [
                "jupyter",
                "jupyterlab",
                "numpy",
                "pandas",
                "matplotlib",
                "scikit-learn",
            ],
        },
        "agentic": {
            "packages": [
                "vim",
                "python3",
                "python3-pip",
                "git",
                "curl",
                "wget",
                "gcc",
                "tmux",
            ],
            "mise_packages": ["python@3.12", "node@24"],
            "pip_packages": [
                "jupyterlab",
                "langchain",
                "langgraph",
                "pydantic",
                "httpx",
            ],
        },
    }
    return presets.get(preset_name, {})


def merge_configs(base: dict, override: dict) -> dict:
    """Merge two configuration dictionaries"""
    result = base.copy()
    for key, value in override.items():
        if key == "packages" and "packages" in result:
            result["packages"] = list(set(result["packages"] + value))
        elif key == "pip_packages" and "pip_packages" in result:
            result["pip_packages"] = list(set(result["pip_packages"] + value))
        else:
            result[key] = value
    return result


def cmd_port_forward_list(args):
    """List all active port-forward tunnels"""
    tunnel_mgr = TunnelManager()
    tunnels = tunnel_mgr.list_tunnels()

    if not tunnels:
        console.print("[dim]No active port-forward tunnels[/dim]")
        return

    table = Table(title="Active Port-Forward Tunnels")
    table.add_column("Sandbox", style="cyan")
    table.add_column("VM Port", justify="right")
    table.add_column("Local Port", justify="right")
    table.add_column("VM IP", style="dim")
    table.add_column("PID", justify="right")

    for tunnel in tunnels:
        table.add_row(
            tunnel["petribox_name"],
            str(tunnel["vm_port"]),
            str(tunnel["local_port"]),
            tunnel["vm_ip"],
            str(tunnel["pid"]),
        )

    console.print(table)


def cmd_port_forward(args):
    """Forward a VM port to localhost"""
    db = DishDB()
    dish = db.get_dish(args.name)

    if not sandbox:
        console.print(f"[red]Error: Sandbox '{args.name}' not found[/red]")
        sys.exit(1)

    # Get actual VM status from libvirt
    current_status = get_vm_status(args.name)
    if current_status != "running":
        console.print(f"[yellow]Sandbox '{args.name}' is not running (status: {current_status or 'unknown'})[/yellow]")
        console.print(f"[dim]Start it with: sandbox up {args.name}[/dim]")
        sys.exit(1)

    # Get IP
    vm_ip = get_vm_ip(args.name, sandbox.network)
    if not vm_ip:
        console.print(f"[red]Error: Could not determine IP for '{args.name}'[/red]")
        sys.exit(1)

    local_port = args.local_port or args.port
    tunnel_mgr = TunnelManager()

    # Check if tunnel already exists
    existing = tunnel_mgr.get_tunnel(args.name, args.port)
    if existing:
        console.print(f"[green]Tunnel already running[/green]")
        console.print(f"  {sandbox.user}@{vm_ip}:{args.port} -> localhost:{existing['local_port']}")
        console.print(f"  PID: {existing['pid']}")
        return

    # Build SSH tunnel command
    ssh_cmd = [
        "ssh",
        "-N",  # No remote command
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-L", f"{local_port}:127.0.0.1:{args.port}",
        f"{sandbox.user}@{vm_ip}",
    ]

    if args.background:
        # Run in background using subprocess
        proc = subprocess.Popen(
            ssh_cmd,
            start_new_session=True,  # Create new process group
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        
        # Give it a moment to start
        time.sleep(0.5)
        
        # Check if process started successfully
        if proc.poll() is not None:
            console.print(f"[red]Failed to start tunnel[/red]")
            sys.exit(1)

        # Save tunnel info
        tunnel_mgr.create_tunnel(args.name, args.port, local_port, proc.pid, vm_ip, sandbox.user)

        console.print(f"[green]Tunnel started in background[/green]")
        console.print(f"  {sandbox.user}@{vm_ip}:{args.port} -> localhost:{local_port}")
        console.print(f"  PID: {proc.pid}")
        console.print(f"[dim]Stop with: sandbox port-forward-stop {args.name} {args.port}[/dim]")
    else:
        # Run in foreground
        console.print(f"[green]Starting tunnel (Ctrl+C to stop)[/green]")
        console.print(f"  {sandbox.user}@{vm_ip}:{args.port} -> localhost:{local_port}")
        console.print()
        try:
            subprocess.run(ssh_cmd)
        except KeyboardInterrupt:
            console.print("\n[d]Tunnel stopped[/dim]")


def cmd_port_forward_stop(args):
    """Stop a port-forward tunnel"""
    tunnel_mgr = TunnelManager()
    
    tunnel = tunnel_mgr.get_tunnel(args.name, args.port)
    if not tunnel:
        console.print(f"[yellow]No active tunnel found for '{args.name}' port {args.port}[/yellow]")
        console.print("[dim]Tunnel may have already been stopped or killed manually[/dim]")
        return

    tunnel_mgr.kill_tunnel(args.name, args.port)
    console.print(f"[green]Tunnel stopped[/green]")
    console.print(f"  localhost:{tunnel['local_port']} -> {args.name}:{args.port}")


def cmd_port_forward_clean(args):
    """Clean up stale port-forward tunnels"""
    tunnel_mgr = TunnelManager()

    tunnels = tunnel_mgr.list_tunnels()
    if not tunnels:
        console.print("[green]No stale tunnels found[/green]")
        return

    console.print(f"[yellow]Found {len(tunnels)} stale tunnel(s)[/yellow]")
    for tunnel in tunnels:
        console.print(f"  {tunnel['petribox_name']}:{tunnel['vm_port']} -> localhost:{tunnel['local_port']} (PID: {tunnel['pid']})")

    cleaned = tunnel_mgr.clean_stale()
    console.print(f"[green]Cleaned up {cleaned} stale tunnel record(s)[/green]")


def cmd_initial_setup(args):
    """Initial setup: check prerequisites, create SSH key, download Rocky image"""
    import subprocess
    import hashlib
    import shutil
    
    console.print("[green]========================================[/green]")
    console.print("[green]  Sandbox Initial Setup[/green]")
    console.print("[green]========================================[/green]")
    console.print()
    console.print("[dim]Note: This tool manages libvirt VMs, which requires sudo privileges.[/dim]")
    console.print("[dim]You will be prompted for your password when creating or managing sandboxes.[/dim]")
    console.print()

    project_dir = Path(__file__).parent.parent
    all_ok = True
    auto = args.auto

    # =========================================================
    # Step 1: Check required tools
    # =========================================================
    console.print("[cyan]Step 1: Checking required tools[/cyan]")
    console.print()

    required_tools = {
        "python3": "python3",
        "pixi": "pixi",
        "virt-install": "virt-install",
        "qemu-img": "qemu-img",
        "virsh": "libvirt-client",
        "ssh-keygen": "openssh-clients",
    }

    missing_tools = []
    for tool, package in required_tools.items():
        if shutil.which(tool):
            console.print(f"  [green]✓[/green] {tool}")
        else:
            console.print(f"  [red]✗[/red] {tool}")
            missing_tools.append((tool, package))

    if missing_tools:
        console.print()
        console.print("[yellow]Missing tools - install with:[/yellow]")
        
        # Detect package manager
        if shutil.which("dnf"):
            console.print(f"  [dim]sudo dnf install {' '.join([pkg for _, pkg in missing_tools])}[/dim]")
        elif shutil.which("apt"):
            # Map package names for apt
            apt_map = {
                "virt-install": "virtinst",
                "qemu-img": "qemu-utils",
                "libvirt-client": "libvirt-clients",
                "ssh-keygen": "openssh-client",
            }
            apt_pkgs = [apt_map.get(pkg, pkg) for _, pkg in missing_tools]
            console.print(f"  [dim]sudo apt install {' '.join(apt_pkgs)}[/dim]")
        else:
            console.print("  [dim]Install missing tools using your package manager[/dim]")
        
        console.print()
        console.print("[yellow]After installing, run 'sandbox initial-setup' again[/yellow]")
        all_ok = False
    else:
        console.print()
        console.print("[green]✓ All required tools found[/green]")
        console.print()

    # =========================================================
    # Step 2: Check libvirt service
    # =========================================================
    console.print("[cyan]Step 2: Checking libvirt service[/cyan]")
    console.print()

    try:
        result = subprocess.run(
            ["systemctl", "is-active", "libvirtd"],
            capture_output=True, text=True
        )
        if result.stdout.strip() == "active":
            console.print("  [green]✓[/green] libvirtd is running")
        else:
            console.print("  [yellow]![/yellow] libvirtd is not running")
            console.print("  [dim]Enable and start with:[/dim]")
            console.print("    [dim]sudo systemctl enable --now libvirtd[/dim]")
            all_ok = False
    except Exception as e:
        console.print(f"  [red]✗[/red] Could not check libvirtd: {e}")
        all_ok = False

    console.print()

    # Check if user is in libvirt group
    import grp
    import getpass
    current_user = getpass.getuser()
    try:
        libvirt_group = grp.getgrnam("libvirt")
        if current_user in libvirt_group.gr_mem:
            console.print(f"  [green]✓[/green] User '{current_user}' is in libvirt group")
        else:
            console.print(f"  [yellow]![/yellow] User '{current_user}' is not in libvirt group")
            console.print("  [dim]Add user to group (optional, avoids sudo for virsh):[/dim]")
            console.print(f"    [dim]sudo usermod -aG libvirt {current_user}[/dim]")
            console.print(f"    [dim]Then log out and back in[/dim]")
    except KeyError:
        console.print("  [dim]libvirt group not found (normal on some systems)[/dim]")

    console.print()

    # =========================================================
    # Step 3: SSH Key
    # =========================================================
    console.print("[cyan]Step 3: SSH Key Setup[/cyan]")
    console.print()

    ssh_dir = Path.home() / ".ssh"
    ssh_dir.mkdir(exist_ok=True)

    # Default key path
    default_key_path = args.ssh_key_path or (ssh_dir / "petribox_id_ed25519")

    # Check for existing keys
    existing_keys = []
    for key_ext in ["_ed25519.pub", "_rsa.pub", "_ecdsa.pub"]:
        for key in ssh_dir.glob(f"*{key_ext}"):
            # Skip the sandbox key itself when looking for alternatives
            if not key.name.startswith("petribox_"):
                existing_keys.append(key)

    ssh_key_created = False
    ssh_key_to_use = None
    ssh_key_skipped = False

    if existing_keys:
        console.print("  Found existing SSH keys:")
        for i, key in enumerate(existing_keys[:5], 1):
            console.print(f"    {i}. {key}")
        if len(existing_keys) > 5:
            console.print(f"    ... and {len(existing_keys) - 5} more")
        console.print()

        if not auto:
            # Ask user what to do
            console.print("  Options:")
            console.print("    [1] Use an existing key (enter number)")
            console.print("    [2] Create a new key specifically for sandboxes (recommended)")
            console.print("    [3] Skip SSH key setup (configure manually later)")
            console.print()
            
            while True:
                try:
                    choice = input("  Select option [1-3]: ").strip()
                    if choice == "1":
                        # Let user pick which key
                        console.print()
                        for i, key in enumerate(existing_keys, 1):
                            console.print(f"    {i}. {key}")
                        try:
                            key_choice = input(f"  Enter key number [1-{len(existing_keys)}]: ").strip()
                            idx = int(key_choice) - 1
                            if 0 <= idx < len(existing_keys):
                                ssh_key_to_use = existing_keys[idx]
                                # Remove .pub extension to get private key
                                if ssh_key_to_use.suffix == ".pub":
                                    ssh_key_to_use = ssh_key_to_use.with_suffix("")
                                console.print(f"  [green]✓[/green] Will use existing key: {ssh_key_to_use}")
                                break
                            else:
                                console.print("  [red]Invalid selection[/red]")
                        except ValueError:
                            console.print("  [red]Please enter a number[/red]")
                    elif choice == "2":
                        break  # Proceed to create new key
                    elif choice == "3":
                        console.print("  [yellow]Skipping SSH key setup[/yellow]")
                        ssh_key_skipped = True
                        break
                    else:
                        console.print("  [red]Invalid option, please choose 1, 2, or 3[/red]")
                except (EOFError, KeyboardInterrupt):
                    console.print("\n  [yellow]Setup cancelled by user[/yellow]")
                    return
        console.print()
    elif not auto:
        # No existing keys found
        console.print("  [yellow]![/yellow] No existing SSH keys found")
        console.print()
        console.print("  Options:")
        console.print("    [1] Create a new SSH key for sandboxes (recommended)")
        console.print("    [2] Skip SSH key setup (configure manually later)")
        console.print()
        
        try:
            choice = input("  Select option [1-2]: ").strip()
            if choice == "2":
                console.print("  [yellow]Skipping SSH key setup[/yellow]")
                ssh_key_skipped = True
        except (EOFError, KeyboardInterrupt):
            console.print("\n  [yellow]Setup cancelled by user[/yellow]")
            return
        console.print()

    # Decide what to do about SSH key
    if ssh_key_skipped:
        # User explicitly skipped, don't create key
        pass
    elif ssh_key_to_use:
        # User chose existing key
        console.print(f"  [green]✓[/green] Using existing SSH key: {ssh_key_to_use}")
    elif default_key_path.exists():
        # Sandbox key already exists
        console.print(f"  [green]✓[/green] Sandbox SSH key already exists: {default_key_path}")
        console.print("  [dim]Remove it to create a new one: rm ~/.ssh/petribox_id_ed25519*[/dim]")
        ssh_key_to_use = default_key_path
    elif not auto:
        # Create new sandbox key
        use_passphrase = False
        console.print("  Creating new SSH key for sandboxes...")
        console.print()
        console.print("  [dim]A passphrase adds security but requires entering it each time[/dim]")
        console.print("  [dim]For sandbox VMs (isolated), no passphrase is typically fine[/dim]")
        console.print()
        try:
            passphrase_choice = input("  Add a passphrase to the key? [y/N]: ").strip().lower()
            use_passphrase = passphrase_choice in ("y", "yes")
        except (EOFError, KeyboardInterrupt):
            console.print("\n  [yellow]Setup cancelled by user[/yellow]")
            return

        try:
            keygen_cmd = [
                "ssh-keygen",
                "-t", "ed25519",
                "-f", str(default_key_path),
                "-C", "petribox@petribox",
            ]

            if use_passphrase:
                # Interactive mode for passphrase
                console.print("  [dim]You will be prompted to enter and confirm the passphrase[/dim]")
                console.print()
                subprocess.run(keygen_cmd, check=True)
            else:
                # No passphrase
                keygen_cmd.insert(3, "-N")
                keygen_cmd.insert(4, "")
                subprocess.run(keygen_cmd, check=True, capture_output=True)

            console.print(f"  [green]✓[/green] SSH key created: {default_key_path}")
            console.print(f"  [dim]Public key: {default_key_path}.pub[/dim]")
            ssh_key_created = True
            ssh_key_to_use = default_key_path
        except subprocess.CalledProcessError as e:
            console.print(f"  [red]✗[/red] Failed to create SSH key: {e}")
            console.print("  [dim]Create manually: ssh-keygen -t ed25519 -f ~/.ssh/petribox_id_ed25519[/dim]")
            all_ok = False
    else:
        # Auto mode and no key exists - create without asking
        console.print("  Creating new SSH key for sandboxes (no passphrase)...")
        try:
            keygen_cmd = [
                "ssh-keygen",
                "-t", "ed25519",
                "-f", str(default_key_path),
                "-N", "",
                "-C", "petribox@petribox",
            ]
            subprocess.run(keygen_cmd, check=True, capture_output=True)
            console.print(f"  [green]✓[/green] SSH key created: {default_key_path}")
            console.print(f"  [dim]Public key: {default_key_path}.pub[/dim]")
            ssh_key_created = True
            ssh_key_to_use = default_key_path
        except subprocess.CalledProcessError as e:
            console.print(f"  [red]✗[/red] Failed to create SSH key: {e}")
            all_ok = False

    console.print()

    # =========================================================
    # Step 4: Rocky Linux Image
    # =========================================================
    console.print("[cyan]Step 4: Rocky Linux Image[/cyan]")
    console.print()

    # Determine image path
    if args.image_path:
        image_path = args.image_path
    else:
        image_path = project_dir / f"Rocky-{args.rocky_version}-GenericCloud-Base.latest.x86_64.qcow2"

    # Check if image already exists
    if image_path.exists():
        console.print(f"  [green]✓[/green] Image found: {image_path}")
        console.print("  [dim]To download a fresh copy, remove or move this file first[/dim]")
    else:
        # Download image
        console.print(f"  [yellow]![/yellow] Image not found")
        console.print()
        
        if not auto:
            console.print(f"  Download Rocky Linux {args.rocky_version}? (~2-3 GB)")
            console.print(f"  Location: {image_path}")
            console.print()
            try:
                confirm = input("  Download now? [Y/n]: ").strip().lower()
                if confirm in ("n", "no"):
                    console.print("  [yellow]Skipping image download[/yellow]")
                    console.print("  [dim]Download manually from: https://rockylinux.org/download[/dim]")
                    image_path = None
            except (EOFError, KeyboardInterrupt):
                console.print("\n  [yellow]Setup cancelled by user[/yellow]")
                return
        
        if image_path and not image_path.exists():
            # URLs
            base_url = f"https://dl.rockylinux.org/pub/rocky/{args.rocky_version}/images/x86_64"
            image_url = f"{base_url}/Rocky-{args.rocky_version}-GenericCloud-Base.latest.x86_64.qcow2"
            checksum_url = f"{base_url}/CHECKSUM"

            console.print(f"  [dim]Downloading from: {image_url}[/dim]")
            
            try:
                # Download CHECKSUM file
                import urllib.request
                console.print("  Downloading CHECKSUM...")
                with urllib.request.urlopen(checksum_url) as response:
                    checksum_content = response.read().decode("utf-8")
                
                # Extract SHA256 hash for the image
                import re
                image_filename = f"Rocky-{args.rocky_version}-GenericCloud-Base.latest.x86_64.qcow2"
                match = re.search(r"([a-f0-9]{64})\s+.*" + re.escape(image_filename), checksum_content, re.IGNORECASE)
                if not match:
                    # Try alternate pattern
                    match = re.search(r"SHA256\s*\(\s*" + re.escape(image_filename) + r"\s*\)\s*=\s*([a-f0-9]{64})", checksum_content, re.IGNORECASE)
                
                expected_hash = match.group(1) if match else None
                if expected_hash:
                    console.print(f"  [dim]Expected SHA256: {expected_hash[:16]}...[/dim]")
                else:
                    console.print("  [yellow]Warning: Could not extract checksum from CHECKSUM file[/dim]")

                # Download image
                console.print("  Downloading image (this may take a few minutes)...")
                
                def report_progress(block_num, block_size, total_size):
                    downloaded = block_num * block_size
                    percent = min(downloaded * 100 / total_size, 100)
                    print(f"\r  [{percent:.1f}%] {downloaded // 1024 // 1024} MB / {total_size // 1024 // 1024} MB", end="", flush=True)

                urllib.request.urlretrieve(image_url, str(image_path), report_progress)
                print()  # Newline after progress

                # Verify checksum
                if expected_hash:
                    console.print("  Verifying checksum...")
                    sha256_hash = hashlib.sha256()
                    with open(image_path, "rb") as f:
                        for chunk in iter(lambda: f.read(8192), b""):
                            sha256_hash.update(chunk)
                    
                    actual_hash = sha256_hash.hexdigest()
                    if actual_hash.lower() == expected_hash.lower():
                        console.print(f"  [green]✓[/green] Checksum verified")
                    else:
                        console.print(f"  [red]✗[/red] Checksum mismatch!")
                        console.print(f"    Expected: {expected_hash}")
                        console.print(f"    Actual:   {actual_hash}")
                        console.print("  [yellow]Downloaded file may be corrupted. Delete and try again.[/yellow]")
                        all_ok = False
                else:
                    console.print("  [dim]Skipping checksum verification (hash not found)[/dim]")

            except Exception as e:
                console.print(f"  [red]✗[/red] Download failed: {e}")
                console.print("  [dim]Download manually from: {image_url}[/dim]")
                all_ok = False

    console.print()

    # =========================================================
    # Step 5: Suggest alias
    # =========================================================
    if not args.no_alias:
        console.print("[cyan]Step 5: Shell Alias (Optional)[/cyan]")
        console.print()

        project_path = project_dir.resolve()
        alias_cmd = f'alias sandbox="cd {project_path} && pixi run sandbox"'
        
        console.print("  Add this alias to your shell for convenient access:")
        console.print(f"  [green]{alias_cmd}[/green]")
        console.print()

        if not auto:
            # Ask if user wants to add it automatically
            shell_configs = []
            bashrc = Path.home() / ".bashrc"
            bash_aliases = Path.home() / ".bash_aliases"
            zshrc = Path.home() / ".zshrc"
            
            if bash_aliases.exists():
                shell_configs.append(("~/.bash_aliases", bash_aliases))
            elif bashrc.exists():
                shell_configs.append(("~/.bashrc", bashrc))
            if zshrc.exists():
                shell_configs.append(("~/.zshrc", zshrc))

            if shell_configs:
                console.print("  Detected shell config files:")
                for i, (name, _) in enumerate(shell_configs, 1):
                    console.print(f"    {i}. {name}")
                console.print()
                try:
                    choice = input("  Add alias automatically? [1 to add, N to skip]: ").strip()
                    if choice == "1":
                        target_name, target_path = shell_configs[0]
                        content = f"\n# Sandbox alias\n{alias_cmd}\n"
                        with open(target_path, "a") as f:
                            f.write(content)
                        console.print(f"  [green]✓[/green] Alias added to {target_name}")
                        console.print("  [dim]Restart your shell or run: source {target_name}[/dim]")
                    else:
                        console.print("  [dim]Add the alias manually to your shell config[/dim]")
                except (EOFError, KeyboardInterrupt):
                    console.print()
            else:
                console.print("  [dim]Add the alias manually to ~/.bashrc or ~/.bash_aliases[/dim]")
        else:
            console.print("  [dim]Add this to ~/.bashrc or ~/.bash_aliases manually[/dim]")

        console.print()

    # =========================================================
    # Summary
    # =========================================================
    console.print("[green]========================================[/green]")
    if all_ok:
        console.print("[green]  Setup Complete![/green]")
        console.print("[green]========================================[/green]")
        console.print()
        console.print("  You can now create sandboxes:")
        console.print("  [dim]pixi run sandbox create mybox --preset dev[/dim]")
        console.print()
        if ssh_key_to_use:
            console.print(f"  [dim]SSH key: {ssh_key_to_use}[/dim]")
    else:
        console.print("[yellow]  Setup Incomplete - Please address the issues above[/yellow]")
        console.print("[yellow]========================================[/yellow]")
        console.print()
        console.print("  Then run 'sandbox initial-setup' again")

    console.print()


def cmd_install(args):
    """Install software into an existing sandbox"""
    db = DishDB()
    dish = db.get_dish(args.name)

    if not sandbox:
        console.print(f"[red]Error: Sandbox '{args.name}' not found[/red]")
        sys.exit(1)

    if get_vm_status(args.name) != "running":
        console.print(f"[red]Error: Sandbox '{args.name}' is not running[/red]")
        console.print("Start it with: sandbox up " + args.name)
        sys.exit(1)

    vm_user = sandbox.user
    user_home = f"/home/{vm_user}"

    ip = get_vm_ip(args.name)
    if not ip:
        console.print(f"[red]Error: Could not get IP for '{args.name}'[/red]")
        sys.exit(1)

    if args.agent:
        from .agents import get_agent_config
        agent_config = get_agent_config(args.agent)
        console.print(f"[green]Installing agent: {agent_config['name']}[/green]")

        if agent_config.get("packages"):
            packages = " ".join(agent_config["packages"])
            console.print(f"[dim]Installing system packages: {packages}...[/dim]")
            cmd = f"sudo dnf install -y {packages}"
            result = subprocess.run(
                ["ssh", "-o", "StrictHostKeyChecking=no", f"{vm_user}@{ip}", cmd],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                console.print(f"[yellow]Warning: Failed to install packages: {result.stderr}[/yellow]")

        if agent_config.get("mise_packages"):
            for pkg in agent_config["mise_packages"]:
                console.print(f"[dim]Installing {pkg} via mise...[/dim]")
                cmd = f"export HOME={user_home} && {user_home}/.local/bin/mise use -g {pkg}"
                result = subprocess.run(
                    ["ssh", "-o", "StrictHostKeyChecking=no", f"{vm_user}@{ip}", cmd],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    console.print(f"[yellow]Warning: Failed to install {pkg}: {result.stderr}[/yellow]")

        if agent_config.get("install_script"):
            console.print(f"[dim]Running agent installer...[/dim]")
            install_script = agent_config["install_script"]
            cmd = f"export HOME={user_home} && {install_script}"
            result = subprocess.run(
                ["ssh", "-o", "StrictHostKeyChecking=no", f"{vm_user}@{ip}", cmd],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                console.print(f"[red]Error installing agent: {result.stderr}[/red]")
                sys.exit(1)
            console.print(f"[green]✓ Agent {agent_config['name']} installed[/green]")
            
            if agent_config.get("setup_command"):
                console.print()
                console.print(f"[cyan]Next step - Configure the agent:[/cyan]")
                console.print(f"  SSH into the VM and run: [green]{agent_config['setup_command']}[/green]")
                if agent_config.get("setup_notes"):
                    console.print(f"  [dim]{agent_config['setup_notes']}[/dim]")
        else:
            console.print(f"[yellow]No automated installer for {agent_config['name']}[/yellow]")
            if agent_config.get("repo"):
                console.print(f"[dim]Clone manually: git clone {agent_config['repo']}[/dim]")

    if args.mise_packages:
        for pkg in args.mise_packages:
            console.print(f"[dim]Installing {pkg} via mise...[/dim]")
            cmd = f"export HOME={user_home} && {user_home}/.local/bin/mise use -g {pkg}"
            result = subprocess.run(
                ["ssh", "-o", "StrictHostKeyChecking=no", f"{vm_user}@{ip}", cmd],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                console.print(f"[red]Error: {result.stderr}[/red]")
                sys.exit(1)
            console.print(f"[green]✓ {pkg} installed[/green]")

    if not args.agent and not args.mise_packages:
        console.print("[yellow]Nothing to install. Use --agent or --mise-package[/yellow]")
