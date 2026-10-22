"""
Secrets: resolve API keys on the host, deliver them into a dish safely.

Threat model: the agent inside a dish is untrusted, so a dish only ever
receives the *values* it was given — never access to the host's secret store.
Values are resolved on the host (literal, hidden prompt, or a user-configured
command such as `secret-tool lookup ...`, `keepassxc-cli show ...`, `pass ...`)
and written to `~/.config/petribox/env` (mode 0600) inside the dish over the
stdin of `incus exec`. They never appear in host argv, in cloud-init user-data,
or in `incus config`, so `petribox export` tarballs only carry them if the file
is still inside the dish's disk.

Per-user secret sources live in `$XDG_CONFIG_HOME/petribox/config.toml`:

    [secrets]
    OPENAI_API_KEY = { cmd = "secret-tool lookup service openai" }
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Optional

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

from . import incus, meta

# Relative to the dish user's home. Sourced from the shell rc.
ENV_FILE = ".config/petribox/env"
SOURCE_LINE = f'[ -f ~/{ENV_FILE} ] && . ~/{ENV_FILE}'

_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SecretError(RuntimeError):
    """A secret could not be resolved or delivered."""


def valid_key(key: str) -> bool:
    return bool(_KEY_RE.match(key))


# ---------------------------------------------------------------------------
# Host side: per-user config and resolution
# ---------------------------------------------------------------------------
def user_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "petribox" / "config.toml"


def configured_sources() -> dict[str, str]:
    """Map KEY -> shell command from the `[secrets]` table of the user config."""
    path = user_config_path()
    if not path.exists():
        return {}
    try:
        data = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise SecretError(f"{path}: {exc}") from exc
    sources = {}
    for key, entry in (data.get("secrets") or {}).items():
        cmd = entry.get("cmd") if isinstance(entry, dict) else None
        if not cmd:
            raise SecretError(f"{path}: [secrets].{key} needs a `cmd = \"...\"` value")
        sources[key] = cmd
    return sources


def run_source(cmd: str) -> str:
    """Run a user-configured secret command and return its output.

    stdin/stderr stay on the terminal so tools that ask for a master password
    (keepassxc-cli, gpg) can prompt; only stdout is captured.
    """
    proc = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, text=True)
    value = proc.stdout.rstrip("\n")
    if proc.returncode != 0 or not value:
        raise SecretError(f"secret command failed or printed nothing: {cmd}")
    return value


def resolve(key: str, *, from_cmd: Optional[str] = None) -> str:
    """Resolve KEY from an explicit command, else from the user config."""
    if from_cmd:
        return run_source(from_cmd)
    cmd = configured_sources().get(key)
    if cmd is None:
        raise SecretError(
            f"{key} has no source in {user_config_path()} "
            f"(add [secrets] {key} = {{ cmd = \"...\" }})"
        )
    return run_source(cmd)


def mask(value: str) -> str:
    """Show just enough to tell keys apart."""
    return "****" + value[-4:] if len(value) > 8 else "****"


# ---------------------------------------------------------------------------
# Dish side: the env file
# ---------------------------------------------------------------------------
def _as_user(name: str, user: str, script: str, text_input: Optional[str] = None):
    return incus.exec_input(name, ["su", "-", user, "-c", script], text_input)


def parse_env(text: str) -> dict[str, str]:
    env = {}
    for line in text.splitlines():
        if not line.startswith("export "):
            continue
        parts = shlex.split(line.removeprefix("export "))
        if parts and "=" in parts[0]:
            key, _, value = parts[0].partition("=")
            env[key] = value
    return env


def render_env(env: dict[str, str]) -> str:
    lines = ["# Managed by petribox (petribox env ...). Mode 0600."]
    lines += [f"export {k}={shlex.quote(v)}" for k, v in sorted(env.items())]
    return "\n".join(lines) + "\n"


def read_env(name: str, user: str) -> dict[str, str]:
    proc = _as_user(name, user, f"cat ~/{ENV_FILE} 2>/dev/null || true")
    if proc.returncode != 0:
        raise SecretError(f"cannot read env file in '{name}': {proc.stderr.strip()}")
    return parse_env(proc.stdout)


def write_env(name: str, user: str, env: dict[str, str], rc_file: str) -> None:
    """Replace the dish's env file (contents via stdin) and make sure the rc sources it."""
    env_dir = os.path.dirname(ENV_FILE)
    script = (
        f"umask 077 && mkdir -p ~/{env_dir} && cat > ~/{ENV_FILE} && chmod 600 ~/{ENV_FILE} && "
        f"(grep -qF {shlex.quote(SOURCE_LINE)} ~/{rc_file} 2>/dev/null || "
        f"echo {shlex.quote(SOURCE_LINE)} >> ~/{rc_file})"
    )
    proc = _as_user(name, user, script, render_env(env))
    if proc.returncode != 0:
        raise SecretError(f"cannot write env file in '{name}': {proc.stderr.strip()}")
    # Record names only (never values) so `export` can warn without exec.
    meta.set_meta(name, env_keys=",".join(sorted(env)))


def update_env(name: str, user: str, rc_file: str, *,
               set_: Optional[dict[str, str]] = None,
               unset: Optional[list[str]] = None,
               clear: bool = False) -> dict[str, str]:
    env = {} if clear else read_env(name, user)
    for key in unset or []:
        env.pop(key, None)
    env.update(set_ or {})
    write_env(name, user, env, rc_file)
    return env


def wait_for_user(name: str, user: str, timeout: int = 300) -> bool:
    """Wait until cloud-init has created the dish user (needed before writing)."""
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        if incus.exec_capture(name, ["id", "-u", user]).returncode == 0:
            return True
        time.sleep(2)
    return False
