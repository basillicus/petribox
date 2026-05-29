"""Access commands: connect (incus exec) and console."""

from __future__ import annotations

import subprocess

from .. import incus
from ._common import console, get_instance_or_exit, require_running


def cmd_ssh(args):
    """Open an interactive shell in the dish via `incus exec` (no SSH needed)."""
    get_instance_or_exit(args.name)
    require_running(args.name)
    command = list(args.ssh_command) if getattr(args, "ssh_command", None) else None
    # Replaces the current process with incus exec.
    incus.exec_interactive(args.name, command)


def cmd_console(args):
    """Attach to the dish's console."""
    get_instance_or_exit(args.name)
    require_running(args.name)
    console.print(f"[dim]Connecting to console of '{args.name}'... (detach: Ctrl+a q)[/dim]")
    subprocess.run(["incus", "console", args.name])
