"""Thin helpers over the `incus` CLI. Errors carry incus's own stderr."""

from __future__ import annotations

import subprocess
import time


class IncusError(RuntimeError):
    """An `incus` invocation failed."""


def run(*args: str, input: str | None = None, capture: bool | str = True,
        check: bool = True) -> subprocess.CompletedProcess:
    """Run `incus <args>`.

    Without input, stdin is /dev/null: some incus commands read YAML from a
    non-tty stdin and would otherwise wait forever. capture=False lets output
    (provisioning logs) go straight to the terminal; capture="stderr" shows
    stdout (image download progress) but keeps the error text for the message.
    """
    try:
        proc = subprocess.run(
            ["incus", *args], input=input, text=True,
            stdout=subprocess.PIPE if capture is True else None,
            stderr=subprocess.PIPE if capture else None,
            stdin=subprocess.DEVNULL if input is None else None,
        )
    except FileNotFoundError as exc:
        raise IncusError("incus is not installed or not on PATH") from exc
    if check and proc.returncode != 0:
        msg = (proc.stderr or "").strip().removeprefix("Error: ") if capture else ""
        raise IncusError(msg or f"`incus {' '.join(args[:3])}` failed (exit {proc.returncode})")
    return proc


def exists(name: str) -> bool:
    return run("query", f"/1.0/instances/{name}", check=False).returncode == 0


def has_snapshot(name: str, snapshot: str) -> bool:
    return run("query", f"/1.0/instances/{name}/snapshots/{snapshot}", check=False).returncode == 0


def image_requirements(image: str, vm: bool) -> dict[str, str]:
    """An image's `requirements.*` properties (e.g. secureboot: false), or {}
    when the image cannot be looked up (incus init will then say why)."""
    proc = run("image", "info", image, *(["--vm"] if vm else []), check=False)
    reqs = {}
    for line in proc.stdout.splitlines() if proc.returncode == 0 else []:
        key, _, value = line.strip().partition(": ")
        if key.startswith("requirements."):
            reqs[key.removeprefix("requirements.")] = value.strip()
    return reqs


def config_get(name: str, key: str) -> str:
    return run("config", "get", name, key).stdout.strip()


def stop(name: str, timeout: int = 60) -> bool:
    """Stop cleanly if the guest agrees, else by force after syncing its disks
    (some guests ignore the ACPI shutdown request). True if it was clean."""
    run("exec", name, "--", "sync", check=False)
    if run("stop", name, "--timeout", str(timeout), check=False).returncode == 0:
        return True
    run("stop", name, "--force")
    return False


def wait_for_agent(name: str, timeout: float = 300) -> None:
    """Block until `incus exec` works (VM agent up / container running)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if run("exec", name, "--", "true", check=False).returncode == 0:
            return
        time.sleep(2)
    raise IncusError(f"{name}: no agent after {timeout:.0f}s (does the image ship incus-agent?)")
