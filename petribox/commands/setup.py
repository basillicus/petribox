"""initial-setup: install Incus, initialise it, and verify prerequisites."""

from __future__ import annotations

import getpass
import grp
import shutil
import subprocess

from .. import incus
from ._common import console

# Group that grants Incus management. Debian/Ubuntu use incus-admin; some
# distros use incus. We check both.
INCUS_GROUPS = ("incus-admin", "incus")


def _in_any_group(user: str, groups: tuple[str, ...]) -> "str | None":
    for group in groups:
        try:
            if user in grp.getgrnam(group).gr_mem:
                return group
        except KeyError:
            continue
    return None


def _install_hint() -> str:
    if shutil.which("apt"):
        return "sudo apt install -y incus"
    if shutil.which("dnf"):
        return "sudo dnf install -y incus"
    if shutil.which("zypper"):
        return "sudo zypper install -y incus"
    return "install the 'incus' package with your distribution's package manager"


def cmd_initial_setup(args):
    console.print("[green]=== Petribox initial setup ===[/green]\n")
    user = getpass.getuser()
    auto = getattr(args, "auto", False)
    all_ok = True

    # 1. Incus installed?
    console.print("[cyan]1. Incus[/cyan]")
    if incus.available():
        version = subprocess.run(["incus", "version"], capture_output=True, text=True)
        console.print(f"  [green]✓[/green] incus present ({version.stdout.strip().splitlines()[0] if version.stdout else 'ok'})")
    else:
        console.print("  [red]✗[/red] incus not found")
        console.print(f"  [dim]Install with: {_install_hint()}[/dim]")
        console.print("  [dim]Then re-run: petribox initial-setup[/dim]\n")
        # Without Incus we cannot continue the rest meaningfully.
        console.print("[yellow]Install Incus, then run setup again.[/yellow]")
        return

    # 2. Group membership (no sudo for incus once in the group + re-login).
    console.print("\n[cyan]2. Group membership[/cyan]")
    member_of = _in_any_group(user, INCUS_GROUPS)
    if member_of:
        console.print(f"  [green]✓[/green] '{user}' is in the '{member_of}' group")
    else:
        target = "incus-admin" if any(_group_exists(g) for g in ("incus-admin",)) else "incus"
        console.print(f"  [yellow]![/yellow] '{user}' is not in an Incus group")
        console.print(f"  [dim]Run: sudo usermod -aG {target} {user}[/dim]")
        console.print("  [dim]Then log out and back in (group change needs a new session)[/dim]")
        all_ok = False

    # 3. Initialise Incus (idempotent: only if no storage pool exists yet).
    console.print("\n[cyan]3. Incus initialisation[/cyan]")
    pools = subprocess.run(["incus", "storage", "list", "--format", "csv"],
                           capture_output=True, text=True)
    if pools.returncode == 0 and pools.stdout.strip():
        console.print("  [green]✓[/green] Incus already initialised (storage pool present)")
    else:
        console.print("  [yellow]![/yellow] Incus not initialised")
        if auto or _confirm("  Run 'incus admin init --minimal' now?"):
            init = subprocess.run(["incus", "admin", "init", "--minimal"])
            if init.returncode == 0:
                console.print("  [green]✓[/green] Initialised (default pool + incusbr0 network)")
            else:
                console.print("  [red]✗[/red] Initialisation failed (are you in the incus group?)")
                all_ok = False
        else:
            console.print("  [dim]Run later: incus admin init --minimal[/dim]")
            all_ok = False

    # 4. Image remote reachable.
    console.print("\n[cyan]4. Image remote[/cyan]")
    img = subprocess.run(["incus", "image", "list", incus.DEFAULT_IMAGE, "--format", "csv"],
                         capture_output=True, text=True)
    if img.returncode == 0:
        console.print(f"  [green]✓[/green] {incus.DEFAULT_IMAGE} reachable")
    else:
        console.print(f"  [yellow]![/yellow] could not query {incus.DEFAULT_IMAGE}")
        console.print("  [dim]Check connectivity to the images: remote[/dim]")

    console.print()
    if all_ok:
        console.print("[green]Setup complete. Create a dish:[/green]")
        console.print("  [dim]petribox create lab --preset dev[/dim]")
    else:
        console.print("[yellow]Setup incomplete — address the items above and re-run.[/yellow]")


def _group_exists(name: str) -> bool:
    try:
        grp.getgrnam(name)
        return True
    except KeyError:
        return False


def _confirm(prompt: str) -> bool:
    try:
        return input(f"{prompt} [y/N]: ").strip().lower() == "y"
    except (EOFError, KeyboardInterrupt):
        return False
