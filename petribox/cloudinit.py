"""
cloud-init user-data generation.

Builds a cloud-config dict and serialises it with PyYAML. The result is
delivered to Incus via the `cloud-init.user-data` config key; the cloud image
variant runs it once on first boot to install packages, mise, and any agent.
"""

from __future__ import annotations

from typing import Optional

import yaml

# Always present, regardless of preset/config.
DEFAULT_PACKAGES = ["vim", "python3", "git", "curl", "wget", "tmux"]
# Build dependencies mise needs to compile language runtimes on Rocky.
MISE_BUILD_DEPS = ["libatomic", "openssl-devel", "bzip2-devel", "libffi-devel"]


def _dedup(seq: list[str]) -> list[str]:
    """Order-preserving de-duplication."""
    return list(dict.fromkeys(seq))


def build_user_data(
    *,
    hostname: str,
    user: str,
    ssh_key: str,
    config: Optional[dict] = None,
    agent_config: Optional[dict] = None,
    password: Optional[str] = None,
    shell: str = "bash",
) -> str:
    """Return a #cloud-config document as a string."""
    config = config or {}
    home = f"/home/{user}"

    # ---- packages ----------------------------------------------------------
    packages = list(DEFAULT_PACKAGES)
    packages += config.get("packages", [])
    if agent_config:
        packages += agent_config.get("packages", [])
    packages += MISE_BUILD_DEPS
    packages = _dedup(packages)

    # ---- user --------------------------------------------------------------
    account: dict = {
        "name": user,
        "gecos": "Petri User",
        "sudo": "ALL=(ALL) NOPASSWD:ALL",
        "groups": ["wheel", "adm"],
        "shell": "/bin/zsh" if shell == "zsh" else "/bin/bash",
        "ssh_authorized_keys": [" ".join(ssh_key.split())],
    }

    cloud_config: dict = {
        "hostname": hostname,
        "users": [account],
        "package_update": True,
        "packages": packages,
    }

    if password:
        account["lock_passwd"] = False
        cloud_config["ssh_pwauth"] = True
        cloud_config["chpasswd"] = {
            "expire": False,
            "users": [{"name": user, "password": password, "type": "text"}],
        }
    else:
        account["lock_passwd"] = True
        cloud_config["ssh_pwauth"] = False

    # ---- runcmd ------------------------------------------------------------
    runcmd: list[str] = ["systemctl enable --now sshd"]

    # EPEL + CRB for extras (htop).
    runcmd.append(
        "dnf config-manager --set-enabled crb || true; "
        "dnf install -y epel-release || true; "
        "dnf install -y htop || true"
    )

    # mise (version manager) + ownership fixup.
    runcmd.append(f"export HOME={home} && curl -sSfL https://mise.run/{shell} | sh")
    runcmd.append(f"chown -R {user}:{user} {home}/.local")

    mise_packages = list(config.get("mise_packages", []))
    if agent_config:
        for pkg in agent_config.get("mise_packages", []):
            if pkg not in mise_packages:
                mise_packages.append(pkg)
    for pkg in mise_packages:
        runcmd.append(f"export HOME={home} && {home}/.local/bin/mise use -g {pkg}")

    pip_packages = config.get("pip_packages", [])
    if pip_packages:
        runcmd.append("pip3 install --break-system-packages " + " ".join(pip_packages))

    if agent_config and agent_config.get("install_script"):
        runcmd.append(f"export HOME={home} && {agent_config['install_script']}")

    environment = config.get("environment", {})
    if environment:
        for key, value in environment.items():
            runcmd.append(
                f'echo \'export {key}="{value}"\' >> {home}/.bashrc'
            )

    for cmd in config.get("runcmd", []):
        runcmd.append(cmd if isinstance(cmd, str) else " ".join(cmd))

    runcmd.append(f"echo 'petribox dish {hostname} setup complete'")

    cloud_config["runcmd"] = runcmd

    body = yaml.dump(cloud_config, default_flow_style=False, sort_keys=False)
    return "#cloud-config\n" + body
