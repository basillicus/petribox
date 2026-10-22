"""
Secrets: resolve values on the host, deliver them into a dish safely.

Threat model: the agent inside a dish is untrusted, so a dish only ever
receives the *values* it was given, never access to the host's secret store.
Values come from a command in the user config (`secret-tool lookup ...`,
`keepassxc-cli show ...`, `pass ...`) or a hidden prompt, and are written to
~/.config/petribox/env (mode 0600) inside the dish over the stdin of
`incus exec`. They never appear in host argv, in the instance config, or in
anything `incus export` carries apart from the dish's own disk.

    # $XDG_CONFIG_HOME/petribox/config.toml
    [secrets]
    OPENAI_API_KEY = { cmd = "secret-tool lookup service openai" }

For model APIs, consider not handing a key in at all: point the dish at a
proxy on the host that adds the key (e.g. LiteLLM with per-dish virtual keys).
"""

from __future__ import annotations

import getpass
import os
import re
import shlex
import subprocess
import sys
import tomllib
from pathlib import Path

from . import incus

ENV_FILE = ".config/petribox/env"  # relative to the dish user's home
SOURCE_LINE = f"[ -f ~/{ENV_FILE} ] && . ~/{ENV_FILE}"
_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SecretError(RuntimeError):
    """A secret could not be resolved or delivered."""


def valid_key(key: str) -> bool:
    return bool(_KEY_RE.match(key))


# ---------------------------------------------------------------------------
# Host side: user config and resolution
# ---------------------------------------------------------------------------
def user_config_path() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "petribox" / "config.toml"


def user_config() -> dict:
    path = user_config_path()
    if not path.exists():
        return {}
    try:
        return tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as exc:
        raise SecretError(f"{path}: {exc}") from exc


def configured_sources() -> dict[str, str]:
    """Map KEY -> shell command from the `[secrets]` table of the user config."""
    sources = {}
    for key, entry in (user_config().get("secrets") or {}).items():
        cmd = entry.get("cmd") if isinstance(entry, dict) else None
        if not cmd:
            raise SecretError(f"{user_config_path()}: [secrets].{key} needs a `cmd = \"...\"` value")
        sources[key] = cmd
    return sources


def run_source(cmd: str) -> str:
    """Run a configured secret command; only stdout is captured, so tools
    that ask for a master password can still prompt on the terminal."""
    proc = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, text=True)
    value = proc.stdout.rstrip("\n")
    if proc.returncode != 0 or not value:
        raise SecretError(f"secret command failed or printed nothing: {cmd}")
    return value


def resolve(key: str) -> str:
    """Resolve KEY from the user config, else ask with a hidden prompt."""
    if not valid_key(key):
        raise SecretError(f"invalid variable name: {key}")
    cmd = configured_sources().get(key)
    if cmd:
        return run_source(cmd)
    if not sys.stdin.isatty():
        raise SecretError(f"{key} has no source in {user_config_path()} and there is no terminal to ask")
    value = getpass.getpass(f"{key}: ")
    if not value:
        raise SecretError(f"{key}: empty value")
    return value


def mask(value: str) -> str:
    """Show just enough to tell keys apart."""
    return "****" + value[-4:] if len(value) > 8 else "****"


# ---------------------------------------------------------------------------
# Dish side: the env file
# ---------------------------------------------------------------------------
def _as_user(name: str, user: str, script: str, text_input: str | None = None):
    return incus.run("exec", name, "--", "su", "-", user, "-c", script,
                     input=text_input, check=False)


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
    lines = ["# Managed by petribox (petribox secret ...). Mode 0600."]
    lines += [f"export {k}={shlex.quote(v)}" for k, v in sorted(env.items())]
    return "\n".join(lines) + "\n"


def read_env(name: str, user: str) -> dict[str, str]:
    proc = _as_user(name, user, f"cat ~/{ENV_FILE} 2>/dev/null || true")
    if proc.returncode != 0:
        raise SecretError(f"cannot read the env file in '{name}': {proc.stderr.strip()}")
    return parse_env(proc.stdout)


def write_env(name: str, user: str, env: dict[str, str]) -> None:
    """Replace the dish's env file (contents via stdin) and source it from
    the shell rc files that exist (.bashrc is created if none does)."""
    source = shlex.quote(SOURCE_LINE)
    script = (
        f"umask 077 && mkdir -p ~/{os.path.dirname(ENV_FILE)} && cat > ~/{ENV_FILE} && "
        f"chmod 600 ~/{ENV_FILE} && "
        f"{{ [ -f ~/.zshrc ] || touch ~/.bashrc; }} && "
        f"for rc in ~/.bashrc ~/.zshrc; do "
        f"[ -f \"$rc\" ] && {{ grep -qF {source} \"$rc\" || echo {source} >> \"$rc\"; }}; done; true"
    )
    proc = _as_user(name, user, script, render_env(env))
    if proc.returncode != 0:
        raise SecretError(f"cannot write the env file in '{name}': {proc.stderr.strip()}")
