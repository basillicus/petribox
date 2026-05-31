"""Environment variable management for running dishes."""

from __future__ import annotations

import shlex

from rich.table import Table

from .. import incus, meta
from ._common import console, fail, get_instance_or_exit


def _rc_file(name: str) -> str:
    shell = meta.get_meta(name).get("shell", "bash")
    return ".zshrc" if shell == "zsh" else ".bashrc"


def _dish_user(name: str) -> str:
    return meta.get_meta(name).get("user", "petri")


def _exec_as_user(name: str, cmd: str) -> str:
    user = _dish_user(name)
    proc = incus.exec_capture(name, ["su", "-", user, "-c", cmd])
    return proc.stdout.strip()


def cmd_env_set(args):
    """Inject an environment variable into a dish's shell rc."""
    get_instance_or_exit(args.name)
    rc = _rc_file(args.name)
    key = args.key
    value = args.value

    # Remove any existing export for this key, then append the new one.
    remove = f"grep -v '^export {key}=' ~/{rc} > ~/{rc}.tmp 2>/dev/null && mv ~/{rc}.tmp ~/{rc} || true"
    append = f"echo {shlex.quote('export ' + key + '=' + shlex.quote(value))} >> ~/{rc}"
    _exec_as_user(args.name, f"{remove}; {append}")
    console.print(f"[green]✓[/green] {key} set in {_dish_user(args.name)}'s ~/{rc}")
    console.print(f"[dim]Takes effect on next login or: source ~/{rc}[/dim]")


def cmd_env_list(args):
    """List environment variables set in a dish."""
    get_instance_or_exit(args.name)
    rc = _rc_file(args.name)
    out = _exec_as_user(args.name, f"grep '^export ' ~/{rc} 2>/dev/null || true")

    if not out:
        console.print(f"[dim]No exported variables in ~/{rc}[/dim]")
        return

    table = Table(title=f"Env vars in {args.name} (~/{rc})")
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    for line in out.splitlines():
        line = line.removeprefix("export ").strip()
        if "=" in line:
            key, _, val = line.partition("=")
            # Strip surrounding quotes from the stored value
            val = val.strip("'\"")
            table.add_row(key, val)
    console.print(table)


def cmd_env_unset(args):
    """Remove an environment variable from a dish's shell rc."""
    get_instance_or_exit(args.name)
    rc = _rc_file(args.name)
    key = args.key
    cmd = f"grep -v '^export {key}=' ~/{rc} > ~/{rc}.tmp 2>/dev/null && mv ~/{rc}.tmp ~/{rc} || true"
    _exec_as_user(args.name, cmd)
    console.print(f"[green]✓[/green] {key} removed from ~/{rc}")
