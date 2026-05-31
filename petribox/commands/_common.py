"""Shared helpers for petribox commands."""

from __future__ import annotations

import re
import sys
import time
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from .. import incus

console = Console()


def fail(message: str) -> None:
    """Print an error and exit non-zero."""
    console.print(f"[red]Error: {message}[/red]")
    sys.exit(1)


def get_instance_or_exit(name: str) -> dict:
    """Return the instance JSON, or exit with a helpful message."""
    inst = incus.info(name)
    if inst is None:
        fail(f"Dish '{name}' not found. List dishes with: petribox list")
    return inst


def require_running(name: str) -> str:
    """Ensure the dish is running; return its IPv4 (may be empty string)."""
    status, ip = incus.state(name)
    if status is None:
        fail(f"Dish '{name}' not found.")
    if status != "running":
        console.print(f"[yellow]Dish '{name}' is not running (status: {status})[/yellow]")
        console.print(f"[dim]Start it with: petribox up {name}[/dim]")
        sys.exit(1)
    return ip or ""


def resolve_resources(args, preset: dict) -> tuple[int, int, int]:
    """Resolve ram/cpus/disk: explicit flag > preset > hard default."""
    ram = args.ram if args.ram is not None else preset.get("ram", 4096)
    cpus = args.cpus if args.cpus is not None else preset.get("cpus", 2)
    disk = args.disk if args.disk is not None else preset.get("disk", 20)
    return ram, cpus, disk


def mount_device_name(vm_path: str) -> str:
    """Deterministic Incus device name for a guest mount path."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", vm_path).strip("-").lower() or "root"
    return f"mnt-{slug}"


def proxy_device_name(port: int) -> str:
    return f"pf-{port}"


def wait_until_running(name: str, timeout: int = 180) -> Optional[str]:
    """Wait for the dish to reach running state with an IPv4. Returns the IP."""
    deadline = time.time() + timeout
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task(f"Waiting for {name} to boot...", total=None)
        while time.time() < deadline:
            status, ip = incus.state(name)
            if status == "running" and ip:
                return ip
            if status == "running":
                progress.update(task, description=f"{name} running, waiting for network...")
            time.sleep(2)
    return None
