"""
Incus backend - typed wrapper over the `incus` CLI.

Every function shells out to `incus` and raises IncusError (carrying stderr) on
failure, so callers get a useful message.

Design notes:
- Create uses `incus init` + `incus start` so config and devices can be applied
  before first boot (cloud-init runs once on first boot).
- cloud-init.user-data can be multi-KB YAML; we pass it as a single argv element
  (no shell), so no escaping is needed and ARG_MAX is not a concern in practice.
- The default image is the *cloud* variant, which ships cloud-init wired to the
  Incus NoCloud datasource.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Optional

# Cloud variant ships cloud-init + the Incus agent; required for user-data + exec.
DEFAULT_IMAGE = "images:rockylinux/9/cloud"


class IncusError(RuntimeError):
    """An `incus` invocation failed; message carries stderr."""


def available() -> bool:
    """True if the incus CLI is on PATH."""
    return shutil.which("incus") is not None


def _run(
    args: list[str],
    *,
    text_input: Optional[str] = None,
    check: bool = True,
    capture: bool = True,
) -> subprocess.CompletedProcess:
    """Run `incus <args>`. Raise IncusError on non-zero exit when check=True."""
    try:
        proc = subprocess.run(
            ["incus", *args],
            input=text_input,
            capture_output=capture,
            text=True,
        )
    except FileNotFoundError as exc:
        raise IncusError(
            "incus CLI not found. Run 'petribox initial-setup' to install it."
        ) from exc

    if check and proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        raise IncusError(
            stderr or f"`incus {' '.join(args)}` failed (exit {proc.returncode})"
        )
    return proc


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
def init(
    name: str,
    image: str = DEFAULT_IMAGE,
    *,
    vm: bool = True,
    config: Optional[dict[str, str]] = None,
    device_overrides: Optional[list[str]] = None,
) -> None:
    """Create (but do not start) an instance.

    config: map of instance config keys (limits.cpu, limits.memory,
            cloud-init.user-data, user.petribox.*, ...).
    device_overrides: e.g. ["root,size=20GiB"] to resize the root disk.
    """
    args = ["init", image, name]
    if vm:
        args.append("--vm")
    for key, value in (config or {}).items():
        if value is None:
            continue
        args += ["-c", f"{key}={value}"]
    for override in device_overrides or []:
        args += ["-d", override]
    _run(args)


def start(name: str) -> None:
    _run(["start", name])


def stop(name: str, *, force: bool = True) -> None:
    args = ["stop", name]
    if force:
        args.append("--force")
    _run(args)


def restart(name: str, *, force: bool = True) -> None:
    args = ["restart", name]
    if force:
        args.append("--force")
    _run(args)


def delete(name: str, *, force: bool = True) -> None:
    args = ["delete", name]
    if force:
        args.append("--force")
    _run(args)


def exists(name: str) -> bool:
    return _run(["info", name], check=False).returncode == 0


# ---------------------------------------------------------------------------
# Config & metadata
# ---------------------------------------------------------------------------
def config_set(name: str, key: str, value: str) -> None:
    _run(["config", "set", name, key, value])


def config_set_many(name: str, values: dict[str, str]) -> None:
    args = ["config", "set", name]
    for key, value in values.items():
        if value is None:
            continue
        args.append(f"{key}={value}")
    if len(args) > 3:
        _run(args)


def config_get(name: str, key: str) -> str:
    return _run(["config", "get", name, key]).stdout.strip()


# ---------------------------------------------------------------------------
# Devices (mounts via disk, port-forward via proxy)
# ---------------------------------------------------------------------------
def device_add(name: str, device: str, dtype: str, **props: str) -> None:
    """`incus config device add <name> <device> <dtype> k=v ...`"""
    args = ["config", "device", "add", name, device, dtype]
    args += [f"{k}={v}" for k, v in props.items()]
    _run(args)


def device_remove(name: str, device: str) -> None:
    _run(["config", "device", "remove", name, device])


def device_list(name: str) -> list[str]:
    out = _run(["config", "device", "list", name]).stdout
    return [line.strip() for line in out.splitlines() if line.strip()]


def device_show(name: str) -> dict:
    """Return the devices map from `incus config show` (instance-local only)."""
    out = _run(["config", "show", name]).stdout
    try:
        import yaml  # local import; PyYAML is a hard dep

        data = yaml.safe_load(out) or {}
        return data.get("devices", {}) or {}
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Exec & file transfer
# ---------------------------------------------------------------------------
def exec_capture(name: str, command: list[str]) -> subprocess.CompletedProcess:
    """Run a command in the instance, capturing output. Does not raise."""
    return _run(["exec", name, "--", *command], check=False)


def exec_interactive(name: str, command: Optional[list[str]] = None) -> None:
    """Replace the current process with an interactive `incus exec` (for connect)."""
    args = ["incus", "exec", name, "--"]
    args += command or ["bash", "-l"]
    os.execvp("incus", args)


def file_push(
    name: str,
    local_path: str,
    remote_path: str,
    *,
    create_dirs: bool = True,
    mode: Optional[str] = None,
) -> None:
    args = ["file", "push", local_path, f"{name}{remote_path}"]
    if create_dirs:
        args.append("--create-dirs")
    if mode:
        args += ["--mode", mode]
    _run(args)


# ---------------------------------------------------------------------------
# Query / state
# ---------------------------------------------------------------------------
def list_instances() -> list[dict]:
    """All instances as parsed JSON (includes config, devices, and state)."""
    out = _run(["list", "--format", "json"]).stdout
    return json.loads(out) if out.strip() else []


def info(name: str) -> Optional[dict]:
    """Single instance as JSON, or None if it doesn't exist."""
    proc = _run(["list", name, "--format", "json"], check=False)
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    for inst in json.loads(proc.stdout):
        if inst.get("name") == name:
            return inst
    return None


def first_ipv4(instance: dict) -> Optional[str]:
    """Extract the first global IPv4 from an instance's JSON state."""
    state = instance.get("state") or {}
    network = state.get("network") or {}
    for iface, details in network.items():
        if iface == "lo":
            continue
        for addr in details.get("addresses", []):
            if addr.get("family") == "inet" and addr.get("scope") == "global":
                return addr.get("address")
    return None


def state(name: str) -> tuple[Optional[str], Optional[str]]:
    """Return (status, ipv4). status is lowercased e.g. 'running'/'stopped'."""
    inst = info(name)
    if inst is None:
        return None, None
    status = (inst.get("status") or "").lower() or None
    return status, first_ipv4(inst)


# ---------------------------------------------------------------------------
# Portability & remotes
# ---------------------------------------------------------------------------
def export(name: str, path: str, *, instance_only: bool = True) -> None:
    args = ["export", name, path]
    if instance_only:
        args.append("--instance-only")
    _run(args)


def import_(path: str, name: Optional[str] = None) -> None:
    args = ["import", path]
    if name:
        args.append(name)
    _run(args)


def copy(source: str, dest: str) -> None:
    """Copy an instance, e.g. copy('lab', 'cloud:lab') for migration."""
    _run(["copy", source, dest])


def move(source: str, dest: str) -> None:
    _run(["move", source, dest])


def remote_add(name: str, url: str) -> None:
    _run(["remote", "add", name, url])


def remote_list() -> list[dict]:
    out = _run(["remote", "list", "--format", "json"], check=False).stdout
    if not out.strip():
        return []
    data = json.loads(out)
    # `incus remote list --format json` returns a name->info map.
    if isinstance(data, dict):
        return [{"name": k, **(v or {})} for k, v in data.items()]
    return data
