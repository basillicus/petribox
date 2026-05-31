"""Generate and maintain ~/.ssh/petribox_config for all running dishes."""

from __future__ import annotations

from pathlib import Path

from .. import incus, meta
from ._common import console

PETRIBOX_SSH_CONFIG = Path.home() / ".ssh" / "petribox_config"
PETRIBOX_KNOWN_HOSTS = Path.home() / ".ssh" / "petribox_known_hosts"
SSH_CONFIG = Path.home() / ".ssh" / "config"
_INCLUDE = f"Include {PETRIBOX_SSH_CONFIG}"
_HEADER = "# Managed by petribox — do not edit manually. Run: petribox ssh-config"


def cmd_ssh_config(args):
    """
    Write ~/.ssh/petribox_config with a Host block for every running dish,
    then ensure ~/.ssh/config includes it.

    Re-run after creating or deleting dishes to keep the file in sync.
    Dishes are only included while running (stopped dishes have no live IP).
    """
    instances = incus.list_instances()

    blocks: list[str] = [_HEADER, ""]
    count = 0
    for inst in instances:
        ip = incus.first_ipv4(inst)
        if not ip:
            continue
        name = inst.get("name", "")
        user = meta.get_meta(name).get("user", "petri")
        blocks += [
            f"Host {name}",
            f"    HostName {ip}",
            f"    User {user}",
            # Dishes get new IPs on restart — keep host keys in a separate
            # file so ~/.ssh/known_hosts isn't cluttered with stale entries.
            f"    UserKnownHostsFile {PETRIBOX_KNOWN_HOSTS}",
            f"    StrictHostKeyChecking accept-new",
            "",
        ]
        count += 1

    PETRIBOX_SSH_CONFIG.write_text("\n".join(blocks))
    PETRIBOX_SSH_CONFIG.chmod(0o600)
    console.print(f"[green]✓[/green] {count} dish(es) → {PETRIBOX_SSH_CONFIG}")

    _ensure_include()

    if count:
        console.print("\nConnect with hostname directly:")
        for inst in instances:
            if incus.first_ipv4(inst):
                console.print(f"  [dim]ssh {inst['name']}[/dim]")
                console.print(f"  [dim]kitten ssh {inst['name']}[/dim]")
    else:
        console.print("[dim]No running dishes with an IP — file cleared.[/dim]")


def _ensure_include() -> None:
    """Add Include line to ~/.ssh/config if not already present."""
    SSH_CONFIG.parent.mkdir(mode=0o700, exist_ok=True)

    if SSH_CONFIG.exists():
        content = SSH_CONFIG.read_text()
        if _INCLUDE in content:
            console.print(f"[dim]Include already in {SSH_CONFIG}[/dim]")
            return
        # Prepend — Include must appear before any Host blocks it should
        # take precedence over, so the top of the file is the right place.
        SSH_CONFIG.write_text(_INCLUDE + "\n\n" + content)
    else:
        SSH_CONFIG.write_text(_INCLUDE + "\n")
        SSH_CONFIG.chmod(0o600)

    console.print(f"[green]✓[/green] Added Include to {SSH_CONFIG}")
