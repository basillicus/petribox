"""
Libvirt Operations - VM management functions

Uses system libvirt (qemu:///system). User must be in libvirt group.
Only disk operations and network creation require sudo.
"""

import subprocess
import time
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()

LIBVIRT_URI = "qemu:///system"


def check_prereqs():
    """Check if required tools are installed"""
    required = {
        "virt-install": "virtinst package",
        "cloud-localds": "cloud-image-utils package",
        "virsh": "libvirt-clients package",
    }

    for cmd, package in required.items():
        try:
            subprocess.run(
                ["which", cmd],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError:
            raise RuntimeError(f"{cmd} not found. Install {package}")


def create_seed_iso(
    vm_name: str,
    vm_user: str,
    ssh_key: str,
    config: Optional[dict] = None,
    mounts: Optional[list] = None,
    vm_password: Optional[str] = None,
    shell: str = "bash",
    agent: Optional[str] = None,
) -> str:
    import os
    import uuid
    
    sandbox_tmp = Path.home() / ".sandbox" / "tmp"
    sandbox_tmp.mkdir(parents=True, exist_ok=True)
    
    seed_iso = sandbox_tmp / f"{vm_name}-seed.iso"
    user_data_file = sandbox_tmp / f"{vm_name}-user-data.yml"
    meta_data_file = sandbox_tmp / f"{vm_name}-meta-data.yml"
    network_data_file = sandbox_tmp / f"{vm_name}-network-config.yml"

    default_packages = ["vim", "python3", "git", "curl", "wget", "tmux"]

    all_packages = list(dict.fromkeys(default_packages))

    if config and "packages" in config:
        for pkg in config["packages"]:
            if pkg not in all_packages:
                all_packages.append(pkg)

    packages_yaml = "\n".join(f"  - {pkg}" for pkg in all_packages)

    ssh_key_clean = ' '.join(ssh_key.split())
    
    user_data = f"""#cloud-config
hostname: {vm_name}
users:
  - name: {vm_user}
    gecos: "Sandbox User"
    sudo: ALL=(ALL) NOPASSWD:ALL
    groups: wheel,sudo
    ssh_authorized_keys:
      - {ssh_key_clean}
"""

    if vm_password:
        user_data += f"""    lock_passwd: false
    passwd: {vm_password}
"""
    else:
        user_data += """    lock_passwd: true
"""

    user_data += f"""
package_update: true
packages:
{packages_yaml}
  - libatomic
  - openssl-devel
  - bzip2-devel
  - libffi-devel
"""

    user_home = f"/home/{vm_user}"
    mise_url = f"https://mise.run/{shell}"

    agent_config = None
    if agent:
        from .agents import get_agent_config
        agent_config = get_agent_config(agent)
        console.print(f"[dim]Agent: {agent_config['name']}[/dim]")

    runcmd_items = [
        "[ systemctl, enable, --now, sshd ]",
    ]

    epel_packages = ["htop", "fuse-sshfs"]
    if epel_packages:
        runcmd_items.append('[ sh, "-c", "dnf config-manager --set-enabled crb; dnf install -y epel-release; dnf install -y htop fuse-sshfs" ]')

    runcmd_items.append(f'[ sh, "-c", "export HOME={user_home} && curl -sSfL {mise_url} | sh" ]')
    runcmd_items.append(f'[ sh, "-c", "chown -R {vm_user}:{vm_user} {user_home}/.local" ]')

    mise_packages = []
    if config and "mise_packages" in config:
        mise_packages.extend(config["mise_packages"])
    if agent_config and "mise_packages" in agent_config:
        for pkg in agent_config["mise_packages"]:
            if pkg not in mise_packages:
                mise_packages.append(pkg)
    
    for pkg in mise_packages:
        runcmd_items.append(f'[ sh, "-c", "export HOME={user_home} && {user_home}/.local/bin/mise use -g {pkg}" ]')

    if config and "pip_packages" in config:
        pip_packages = " ".join(config["pip_packages"])
        runcmd_items.append(f'[ sh, "-c", "pip3 install --break-system-packages {pip_packages}" ]')

    if agent_config and agent_config.get("install_script"):
        install_script = agent_config["install_script"]
        runcmd_items.append(f'[ sh, "-c", "export HOME={user_home} && {install_script}" ]')

    runcmd_items.append(f'[ sh, "-c", "echo \\"Sandbox {vm_name} setup complete!\\"" ]')

    runcmd_yaml = "\n".join(f"  - {item}" for item in runcmd_items)
    user_data += f"""
runcmd:
{runcmd_yaml}
"""

    with open(str(user_data_file), "w") as f:
        f.write(user_data)

    instance_id = f"{vm_name}-{uuid.uuid4()}"
    meta_data = f"""instance-id: {instance_id}
local-hostname: {vm_name}
"""
    with open(str(meta_data_file), "w") as f:
        f.write(meta_data)

    network_data = """version: 2
ethernets:
  enp1s0:
    dhcp4: true
    dhcp6: false
"""
    with open(str(network_data_file), "w") as f:
        f.write(network_data)

    if seed_iso.exists():
        seed_iso.unlink()

    subprocess.run(
        [
            "cloud-localds",
            str(seed_iso),
            str(user_data_file),
            str(meta_data_file),
            "--network-config=" + str(network_data_file),
        ],
        check=True,
        capture_output=True,
    )

    subprocess.run(
        ["chmod", "644", str(seed_iso)],
        check=True,
        capture_output=True,
    )

    return str(seed_iso)


def create_vm(
    vm_name: str,
    ram: int,
    cpus: int,
    disk_size: int,
    base_image: str,
    seed_iso: str,
    network: str = "default",
):
    """Create VM using virt-install"""
    import os

    vm_dir = "/var/lib/libvirt/images"
    vm_disk = f"{vm_dir}/{vm_name}.qcow2"

    if not base_image.startswith(vm_dir):
        local_base = f"{vm_dir}/.{vm_name}-base.qcow2"
        console.print(f"[dim]Copying base image to {local_base}...[/dim]")
        subprocess.run(
            ["sudo", "cp", base_image, local_base],
            check=True,
        )
        subprocess.run(
            ["sudo", "chmod", "644", local_base],
            check=True,
        )
        effective_base_image = local_base
    else:
        effective_base_image = base_image

    console.print(f"[dim]Creating {disk_size}GB disk...[/dim]")
    subprocess.run(
        ["sudo", "qemu-img", "create", "-f", "qcow2", "-F", "qcow2", "-b", effective_base_image, vm_disk],
        check=True,
        capture_output=True,
    )

    console.print(f"[dim]Installing VM...[/dim]")
    cmd = [
        "sudo", "virt-install",
        "--connect", LIBVIRT_URI,
        "--name", vm_name,
        "--ram", str(ram),
        "--vcpus", str(cpus),
        "--disk", f"path={vm_disk},format=qcow2",
        "--disk", f"path={seed_iso},device=cdrom",
        "--import",
        "--os-variant", "rocky9",
        "--network", f"network={network},model=virtio",
        "--graphics", "vnc",
        "--console", "pty,target_type=serial",
        "--noautoconsole",
        "--boot", "hd",
    ]

    subprocess.run(cmd, check=True)


def start_vm(vm_name: str):
    """Start a VM"""
    subprocess.run(
        ["virsh", "-c", LIBVIRT_URI, "start", vm_name],
        check=True,
        capture_output=True,
    )


def destroy_vm(vm_name: str):
    """Stop a VM"""
    subprocess.run(
        ["virsh", "-c", LIBVIRT_URI, "destroy", vm_name],
        check=True,
        capture_output=True,
    )


def undefine_vm(vm_name: str):
    """Undefine and remove VM storage"""
    subprocess.run(
        ["virsh", "-c", LIBVIRT_URI, "undefine", vm_name, "--remove-all-storage"],
        check=True,
        capture_output=True,
    )


def get_vm_status(vm_name: str) -> Optional[str]:
    """Get VM status"""
    try:
        result = subprocess.run(
            ["virsh", "-c", LIBVIRT_URI, "dominfo", vm_name],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None

        for line in result.stdout.split("\n"):
            if "State:" in line:
                return line.split(":")[1].strip().lower()
    except Exception:
        pass
    return None


def get_vm_ip(vm_name: str, network: str = "default") -> Optional[str]:
    """Get VM IP address (IPv4 only)"""
    result = subprocess.run(
        ["virsh", "-c", LIBVIRT_URI, "domifaddr", vm_name],
        capture_output=True,
        text=True,
    )
    
    if result.returncode == 0 and result.stdout:
        for line in result.stdout.split("\n"):
            line = line.strip()
            if not line or line.startswith("Name") or line.startswith("-"):
                continue
            parts = line.split()
            if len(parts) >= 4:
                ip_field = parts[-1]
                if "/" in ip_field:
                    ip = ip_field.split("/")[0]
                    if ip and ip != "--" and "." in ip and not ip.startswith("127."):
                        return ip
    
    return None


def wait_for_vm(
    vm_name: str, network: str = "default", timeout: int = 180
) -> Optional[str]:
    """Wait for VM to boot and get valid IPv4 address"""
    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

    start_time = time.time()
    attempt = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        transient=True,
    ) as progress:
        task = progress.add_task(f"Waiting for {vm_name} to boot...", total=None)

        while time.time() - start_time < timeout:
            status = get_vm_status(vm_name)
            if status and "running" in status.lower():
                progress.update(task, description=f"VM running, getting IP...")
                vm_ip = get_vm_ip(vm_name, network)
                if vm_ip:
                    progress.update(task, completed=True)
                    return vm_ip

            attempt += 1
            if attempt % 5 == 0:
                progress.update(task, description=f"Waiting for {vm_name} to boot... ({attempt * 2}s)")
            time.sleep(2)

    return None
