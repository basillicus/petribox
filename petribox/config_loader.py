"""
Configuration loader - load YAML configs for dish creation.

The config is folded into cloud-init at create time (see cloudinit.build_user_data),
so there is no separate post-boot package-application step anymore.
"""

from __future__ import annotations

from pathlib import Path

import yaml


def load_config(config_path: Path) -> dict:
    """Load a dish configuration from a YAML file.

    Recognised keys: packages, mise_packages, pip_packages, runcmd, environment.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    with open(config_path, "r") as handle:
        return yaml.safe_load(handle) or {}
