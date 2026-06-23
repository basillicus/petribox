"""Access commands: connect (incus exec) and console."""

from __future__ import annotations

import os
import shutil
import subprocess

from .. import incus, meta
from ._common import console, fail, get_instance_or_exit, require_running
from .ssh_config import PETRIBOX_KNOWN_HOSTS

# Everything a dish needs to *carry* a forwarded GUI: an X11 cookie tool and an
# sshd that allows forwarding. The Rocky cloud image ships neither, and its
# sshd_config has no `Include` for sshd_config.d/, so a drop-in would be ignored
# — we edit the main config. sshd honours the *first* value of a keyword, so we
# strip any existing X11Forwarding lines before appending ours. The app's own
# libraries (Tk, Qt, ...) ship with the app and are not our concern.
_GUI_SETUP = r"""
need=0
rpm -q xorg-x11-xauth >/dev/null 2>&1 || need=1
sshd -T 2>/dev/null | grep -qi '^x11forwarding yes' || need=1
if [ "$need" = 1 ]; then
  dnf install -y xorg-x11-xauth >/dev/null 2>&1 || exit 11
  sed -i '/^[[:space:]]*#*[[:space:]]*X11Forwarding/Id' /etc/ssh/sshd_config
  printf '\n# petribox: GUI forwarding\nX11Forwarding yes\nX11UseLocalhost yes\n' \
    >> /etc/ssh/sshd_config
  systemctl reload sshd 2>/dev/null || systemctl restart sshd
fi
"""


def cmd_ssh(args):
    """Open a shell in the dish as the dish user.

    Default path uses `incus exec` (no SSH, no keys needed); `incus exec` runs as
    root, so we drop to the configured user with a login shell (`su -`).

    With --gui, GUI apps can't ride the `incus exec` channel (it has no display),
    so we route through real `ssh -Y` instead, after making the dish able to
    forward X11. Works on any X11 app (ase gui, interactive matplotlib, ...).
    """
    get_instance_or_exit(args.name)
    requested = list(args.ssh_command) if getattr(args, "ssh_command", None) else None

    if getattr(args, "gui", False):
        return _connect_gui(args.name, requested)

    require_running(args.name)
    user = meta.get_meta(args.name).get("user") or "root"

    if user == "root":
        incus.exec_interactive(args.name, requested)
    elif requested:
        incus.exec_interactive(args.name, ["su", "-", user, "-c", " ".join(requested)])
    else:
        incus.exec_interactive(args.name, ["su", "-", user])


def _connect_gui(name: str, requested: "list[str] | None") -> None:
    """Ensure the dish can forward X11, then open an `ssh -Y` session to it."""
    ip = require_running(name)
    if not ip:
        fail(f"Dish '{name}' has no IPv4 yet. Try again once the network is up.")

    user = meta.get_meta(name).get("user") or "root"

    # Local side: forwarding is useless without an X server (Xwayland counts).
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        console.print(
            "[yellow]No local DISPLAY/WAYLAND_DISPLAY — no X server to forward to. "
            "Run from a graphical session.[/yellow]"
        )
    if shutil.which("xauth") is None:
        console.print(
            "[yellow]Local 'xauth' not found — install it (e.g. 'xorg-x11-xauth' / "
            "'xauth') or forwarding will fall back to fake auth and fail.[/yellow]"
        )

    proc = incus.exec_capture(name, ["bash", "-c", _GUI_SETUP])
    if proc.returncode != 0:
        fail(
            f"Could not prepare GUI forwarding on '{name}' "
            f"(installing xorg-x11-xauth failed). {proc.stderr.strip()}"
        )

    ssh_cmd = [
        "ssh", "-Y",
        "-o", f"UserKnownHostsFile={PETRIBOX_KNOWN_HOSTS}",
        "-o", "StrictHostKeyChecking=accept-new",
        f"{user}@{ip}",
    ]
    if requested:
        ssh_cmd += requested
    else:
        console.print(f"[dim]GUI session to '{name}' — launch e.g. 'ase gui'.[/dim]")
    subprocess.run(ssh_cmd)


def cmd_console(args):
    """Attach to the dish's console."""
    get_instance_or_exit(args.name)
    require_running(args.name)
    console.print(f"[dim]Connecting to console of '{args.name}'... (detach: Ctrl+a q)[/dim]")
    subprocess.run(["incus", "console", args.name])
