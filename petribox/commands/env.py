"""Environment variable / secret management for running dishes.

Values live in ~/.config/petribox/env (mode 0600) inside the dish, sourced from
the shell rc. See petribox/secrets.py for the threat model.
"""

from __future__ import annotations

import getpass

from rich.table import Table

from .. import incus, meta, secrets
from ._common import console, fail, require_running


def _rc_file(name: str) -> str:
    shell = meta.get_meta(name).get("shell", "bash")
    return ".zshrc" if shell == "zsh" else ".bashrc"


def _dish_user(name: str) -> str:
    return meta.get_meta(name).get("user", "petri")


def _value_for(key: str, value: "str | None", from_cmd: "str | None") -> str:
    """Literal value > --from-cmd > configured source > hidden prompt."""
    if value is not None:
        return value
    if from_cmd or key in secrets.configured_sources():
        return secrets.resolve(key, from_cmd=from_cmd)
    entered = getpass.getpass(f"{key} (input hidden): ")
    if not entered:
        fail("No value entered")
    return entered


def _strip_legacy_rc(name: str, user: str, rc: str, keys: list[str]) -> None:
    """Remove `export KEY=` lines older petribox versions wrote into the rc."""
    if not keys:
        return
    pattern = "^export (" + "|".join(keys) + ")="
    incus.exec_capture(name, [
        "su", "-", user, "-c",
        f"[ -f ~/{rc} ] && {{ grep -Ev '{pattern}' ~/{rc} > ~/{rc}.tmp; mv ~/{rc}.tmp ~/{rc}; }}",
    ])


def cmd_env_set(args):
    """Set an environment variable (typically an API key) in a dish."""
    require_running(args.name)
    if not secrets.valid_key(args.key):
        fail(f"Invalid variable name: {args.key}")
    try:
        value = _value_for(args.key, args.value, getattr(args, "from_cmd", None))
        user = _dish_user(args.name)
        secrets.update_env(args.name, user, _rc_file(args.name), set_={args.key: value})
    except secrets.SecretError as exc:
        fail(str(exc))
    console.print(f"[green]✓[/green] {args.key} set in {user}'s ~/{secrets.ENV_FILE}")
    console.print("[dim]Takes effect in new shells.[/dim]")


def cmd_env_list(args):
    """List environment variables set in a dish (values masked unless --show)."""
    require_running(args.name)
    try:
        env = secrets.read_env(args.name, _dish_user(args.name))
    except secrets.SecretError as exc:
        fail(str(exc))
    if not env:
        console.print(f"[dim]No variables in ~/{secrets.ENV_FILE}[/dim]")
        return
    table = Table(title=f"Env vars in {args.name} (~/{secrets.ENV_FILE})")
    table.add_column("Key", style="cyan")
    table.add_column("Value")
    for key, val in sorted(env.items()):
        table.add_row(key, val if getattr(args, "show", False) else secrets.mask(val))
    console.print(table)


def cmd_env_unset(args):
    """Remove one variable, or all of them with --all."""
    require_running(args.name)
    clear = getattr(args, "all", False)
    if not clear and not args.key:
        fail("Give a KEY or --all")
    if not clear and not secrets.valid_key(args.key):
        fail(f"Invalid variable name: {args.key}")
    user, rc = _dish_user(args.name), _rc_file(args.name)
    try:
        keys = sorted(secrets.read_env(args.name, user)) if clear else [args.key]
        secrets.update_env(args.name, user, rc, unset=keys, clear=clear)
    except secrets.SecretError as exc:
        fail(str(exc))
    _strip_legacy_rc(args.name, user, rc, keys)
    console.print(f"[green]✓[/green] removed: {', '.join(keys) or 'nothing to remove'}")
