"""What to do next when something fails.

No list of known problems is ever complete, so every error ends with the
general moves (where settings go, where the logs are, how to continue), and
the known ones get a specific fix first. Commands call `context()` as they
go, so the hints can name the instance and recipe involved.
"""

from __future__ import annotations

import re

from . import ui

_ctx: dict[str, str] = {}


def context(**values: str) -> None:
    """Record what is being worked on: instance=, recipe=, phase=."""
    _ctx.update({k: v for k, v in values.items() if v})


def reset() -> None:
    _ctx.clear()


# (pattern in the error text, hint). {instance} and {recipe} are filled in.
KNOWN = [
    (r"secureboot",
     "The image cannot boot with Secure Boot. In the recipe: "
     'config = {{ "security.secureboot" = "false" }}; for one instance: '
     "incus config set {instance} security.secureboot=false"),
    (r"functional idmap",
     "Containers need subordinate ids for root (once per host): "
     "echo 'root:1000000:1000000000' | sudo tee -a /etc/subuid /etc/subgid "
     "&& sudo systemctl restart incus"),
    (r"no agent after|has no Incus agent",
     "The image has no Incus agent, or it did not start. See the README, "
     "'Images without an agent', then: petribox build {recipe} --resume"),
    (r"no network/DNS|Temporary failure resolving|Could not resolve host",
     "The instance has no network. Check that it got an IPv4 (incus list); "
     "with ufw: sudo ufw allow in on incusbr0 && sudo ufw route allow in on incusbr0 "
     "&& sudo ufw route allow out on incusbr0"),
    (r"Failed shutting down|context deadline exceeded",
     "The guest ignored the shutdown request: incus stop --force {instance}"),
    (r"PGP signature|unknown trust|NO_PUBKEY|keyring",
     "Package signatures do not verify: the image's keyring is older than its "
     "repositories. Update the keyring package first in provision.sh, then --rebuild."),
    (r"No space left|not enough space|disk quota",
     'Out of disk space: raise disk = "..." in the recipe (or incus config device set '
     "{instance} root size=40GiB), or free space in the storage pool (incus storage info default)"),
    (r"DNS name .* already used on network",
     "Another Incus project has an instance with this name on the same network. "
     "Pick another name; remove the stopped copy first: petribox delete {instance}"),
    (r"already exists",
     "Pick another name, or remove the old one: petribox delete {instance}"),
    (r"Image not found|Couldn't find the requested image|not found in remote",
     "Unknown image. List what exists: incus image list images: <distro> "
     "(and incus image list for local ones)"),
    (r"PXE|No bootable device|boot failed",
     "The VM finds nothing to boot: an image made for legacy BIOS needs "
     'config = {{ "security.csm" = "true", "security.secureboot" = "false" }}'),
]


def show(error: str) -> None:
    instance = _ctx.get("instance", "NAME")
    recipe = _ctx.get("recipe", "RECIPE")
    fill = {"instance": instance, "recipe": recipe}
    specific = [hint.format(**fill) for pattern, hint in KNOWN
                if re.search(pattern, error, re.IGNORECASE)]
    if _ctx.get("phase") == "provision":
        specific.append(
            "The provisioning script failed: the first error is in the output above. "
            f"Fix the recipe's provision.sh or extras, then petribox build {recipe} --resume "
            f"(runs the script again on the existing base) or --rebuild (starts over)."
        )
    for hint in specific:
        ui.err_console.print(f"[yellow]→[/yellow] {ui.escape(hint)}")
    if "instance" not in _ctx:
        return
    ui.err_console.print("[dim]If that does not help:[/dim]" if specific else "[dim]What to try:[/dim]")
    for label, command in [
        ("Logs", f"incus info --show-log {instance}"),
        ("Screen (VMs)", f"incus console {instance} --type=vga"),
        ("Inside", f"incus exec {instance} -- bash"),
        ("Settings", f"recipe.toml config = {{...}}, or incus config set {instance} key=value"),
    ]:
        ui.err_console.print(f"  [dim]{label}:[/dim] [cyan]{ui.escape(command)}[/cyan]")
