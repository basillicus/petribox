"""
Configuration Loader - Load and apply YAML configurations
"""

import subprocess
from pathlib import Path
from typing import Optional

import yaml
from rich.console import Console

from .ssh_ops import ssh_connect

console = Console()


def load_config(config_path: Path) -> dict:
    """
    Load configuration from YAML file

    Expected format:
    ```yaml
    packages:
      - vim-enhanced
      - python3-pip
      - nodejs

    mise_packages:
      - node@20
      - python@latest
      - go@1.21

    pip_packages:
      - jupyterlab
      - numpy

    apt_packages:  # For dnf/yum
      - some-package

    dotfiles:
      preset: dev
      # or
      git: https://github.com/user/dotfiles
      # or
      path: ~/.dotfiles

    mounts:
      - host: ~/data
        vm: /data
        type: 9p

    runcmd:
      - echo "Hello"
      - pip install something

    environment:
      MY_VAR: value
    ```

    **Note:** System dependencies for mise (`libatomic`, `openssl-devel`, 
    `bzip2-devel`, `libffi-devel`) are automatically installed before 
    `mise_packages` are configured.
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    return config or {}


def apply_config_packages(
    vm_ip: str,
    vm_user: str,
    config: dict,
):
    """
    Install packages specified in config

    Args:
        vm_ip: VM IP address
        vm_user: VM username
        config: Configuration dictionary
    """
    # Install system packages (dnf for Rocky Linux)
    packages = config.get("packages", [])
    if packages:
        console.print(f"[dim]Installing {len(packages)} packages...[/dim]")
        pkg_list = " ".join(packages)
        ssh_connect(
            vm_ip,
            vm_user,
            command=["sudo", "dnf", "install", "-y"] + packages,
        )

    # Install pip packages
    pip_packages = config.get("pip_packages", [])
    if pip_packages:
        console.print(f"[dim]Installing {len(pip_packages)} pip packages...[/dim]")
        pkg_list = " ".join(pip_packages)
        ssh_connect(
            vm_ip,
            vm_user,
            command=[
                "pip3",
                "install",
                "--break-system-packages",
            ]
            + pip_packages,
        )

    # Run custom commands
    runcmd = config.get("runcmd", [])
    for cmd in runcmd:
        if isinstance(cmd, list):
            ssh_connect(vm_ip, vm_user, command=cmd)
        else:
            ssh_connect(vm_ip, vm_user, command=["bash", "-c", cmd])

    # Set environment variables
    environment = config.get("environment", {})
    if environment:
        console.print("[dim]Setting environment variables...[/dim]")
        env_lines = "\n".join(f'export {k}="{v}"' for k, v in environment.items())
        script = f"""
cat >> ~/.bashrc << 'EOF'

# Sandbox environment
{env_lines}
EOF
"""
        ssh_connect(vm_ip, vm_user, command=["bash", "-c", script])
