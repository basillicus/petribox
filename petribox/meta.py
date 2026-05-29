"""
Petribox metadata stored in Incus `user.petribox.*` instance config keys.

Incus is the single source of truth, so there is no separate store to keep in
sync. Petribox-specific fields (preset, agent, dotfiles source, creation time,
comms port, ...) live as instance config under the `user.petribox.` namespace.
"""

from __future__ import annotations

from typing import Optional

from . import incus

PREFIX = "user.petribox."


def set_meta(name: str, **kv: Optional[str]) -> None:
    """Set user.petribox.<key> for each provided key. None values are skipped."""
    values = {
        f"{PREFIX}{key}": str(value)
        for key, value in kv.items()
        if value is not None
    }
    if values:
        incus.config_set_many(name, values)


def get_meta(name: str) -> dict[str, str]:
    """Return petribox metadata for an instance (keys with the prefix stripped)."""
    inst = incus.info(name)
    if not inst:
        return {}
    config = inst.get("config", {}) or {}
    return {
        key[len(PREFIX):]: value
        for key, value in config.items()
        if key.startswith(PREFIX)
    }
