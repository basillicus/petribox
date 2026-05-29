"""Access commands: connect (incus exec) and console."""

from __future__ import annotations

import subprocess

from .. import incus, meta
from ._common import console, get_instance_or_exit, require_running


def cmd_ssh(args):
    """Open a shell in the dish as the dish user via `incus exec` (no SSH needed).

    `incus exec` runs as root by default, so we drop to the configured user with
    a login shell (`su -`). Pass `--user root`-style by recreating with that user.
    """
    get_instance_or_exit(args.name)
    require_running(args.name)
    user = meta.get_meta(args.name).get("user") or "root"
    requested = list(args.ssh_command) if getattr(args, "ssh_command", None) else None

    if user == "root":
        incus.exec_interactive(args.name, requested)
    elif requested:
        incus.exec_interactive(args.name, ["su", "-", user, "-c", " ".join(requested)])
    else:
        incus.exec_interactive(args.name, ["su", "-", user])


def cmd_console(args):
    """Attach to the dish's console."""
    get_instance_or_exit(args.name)
    require_running(args.name)
    console.print(f"[dim]Connecting to console of '{args.name}'... (detach: Ctrl+a q)[/dim]")
    subprocess.run(["incus", "console", args.name])
