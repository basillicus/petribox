"""
Libvirt Operations - VM management functions
"""

import subprocess
import time
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()


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
) -> str:
    """Create cloud-init seed ISO
    
    Args:
        vm_name: Name of the VM
        vm_user: Username for the VM
        ssh_key: SSH public key
        config: Optional configuration dict
        mounts: Optional list of mount points
        vm_password: Optional password for the user
        shell: Shell to configure (bash or zsh)
    """
    # Use home directory to avoid FUSE mount issues in /tmp
    import os
    sandbox_tmp = Path.home() / ".sandbox" / "tmp"
    sandbox_tmp.mkdir(parents=True, exist_ok=True)
    
    seed_iso = sandbox_tmp / f"{vm_name}-seed.iso"
    user_data_file = sandbox_tmp / f"{vm_name}-user-data.yml"
    network_data_file = sandbox_tmp / f"{vm_name}-network-config.yml"

    # Default packages
    default_packages = ["vim", "python3", "git", "curl", "wget", "tmux", "htop"]

    # Collect all packages (deduplicated)
    all_packages = list(dict.fromkeys(default_packages))  # Remove duplicates while preserving order

    # Add packages from config
    if config and "packages" in config:
        for pkg in config["packages"]:
            if pkg not in all_packages:
                all_packages.append(pkg)

    # Build packages YAML section
    packages_yaml = "\n".join(f"  - {pkg}" for pkg in all_packages)

    # Build user data - minimal for faster boot
    # Note: package_update can take 5-10 minutes on first boot
    # Ensure SSH key is truly single line (remove any line breaks)
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
    lock_passwd: true
"""

    # Add password if specified
    if vm_password:
        user_data += f"""    lock_passwd: false
passwd: {vm_password}
"""
    else:
        user_data += """    lock_passwd: true
"""

    user_data += f"""package_update: true
packages:
{packages_yaml}
  - libatomic
  - openssl-devel
  - bzip2-devel
  - libffi-devel
"""

    # Build runcmd - simple and reliable
    runcmd_items = [
        "[ systemctl, enable, --now, sshd ]",
    ]
    
    # Add mise installation (simple curl pipe)
    runcmd_items.append('[ curl, "-sSfL", "https://mise.run", "|", "sh" ]')
    
    # Add PATH configuration for mise
    runcmd_items.append('[ sh, "-c", "echo >> ~/.bashrc && echo \'# mise\' >> ~/.bashrc && echo \'export PATH=$HOME/.local/share/mise/bin:$PATH\' >> ~/.bashrc" ]')
    
    # Add mise global packages if specified
    if config and "mise_packages" in config:
        for pkg in config["mise_packages"]:
            runcmd_items.append(f'[ sh, "-c", "$HOME/.local/share/mise/bin/mise use -g {pkg}" ]')
    
    # Add pip packages if specified
    if config and "pip_packages" in config:
        pip_packages = " ".join(config["pip_packages"])
        runcmd_items.append(f'[ pip3, install, "--break-system-packages", "{pip_packages}" ]')

    # Add final message
    runcmd_items.append(f'[ echo, "Sandbox {vm_name} setup complete!" ]')

    # Add runcmd section
    runcmd_yaml = "\n".join(f"  - {item}" for item in runcmd_items)
    user_data += f"""
runcmd:
{runcmd_yaml}
"""

    # Write user data
    with open(str(user_data_file), "w") as f:
        f.write(user_data)

    # Network data (DHCP)
    network_data = """version: 2
ethernets:
  enp1s0:
    dhcp4: true
    dhcp6: false
"""
    with open(str(network_data_file), "w") as f:
        f.write(network_data)

    # Clean up old seed ISO if it exists
    if seed_iso.exists():
        seed_iso.unlink()

    # Create ISO
    subprocess.run(
        [
            "cloud-localds",
            str(seed_iso),
            str(user_data_file),
            "--network-config=" + str(network_data_file),
        ],
        check=True,
        capture_output=True,
    )

    # Make ISO readable by all (needed for virt-install with sudo)
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

    # Copy base image to libvirt directory if needed
    effective_base_image = base_image
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

    # Create disk (backed by base image)
    console.print(f"[dim]Creating {disk_size}GB disk...[/dim]")
    subprocess.run(
        ["sudo", "qemu-img", "create", "-f", "qcow2", "-F", "qcow2", "-b", effective_base_image, vm_disk],
        check=True,
        capture_output=True,
    )

    # Install VM
    console.print(f"[dim]Installing VM...[/dim]")
    cmd = [
        "sudo",
        "virt-install",
        "--name",
        vm_name,
        "--ram",
        str(ram),
        "--vcpus",
        str(cpus),
        "--disk",
        f"path={vm_disk},format=qcow2",
        "--disk",
        f"path={seed_iso},device=cdrom",
        "--import",
        "--os-variant",
        "rocky9",
        "--network",
        f"network={network},model=virtio",
        "--graphics",
        "vnc",
        "--console",
        "pty,target_type=serial",
        "--noautoconsole",
        "--boot",
        "hd",
    ]

    subprocess.run(cmd, check=True)


def start_vm(vm_name: str):
    """Start a VM"""
    subprocess.run(
        ["sudo", "virsh", "start", vm_name],
        check=True,
        capture_output=True,
    )


def destroy_vm(vm_name: str):
    """Stop a VM"""
    subprocess.run(
        ["sudo", "virsh", "destroy", vm_name],
        check=True,
        capture_output=True,
    )


def undefine_vm(vm_name: str):
    """Undefine and remove VM storage"""
    subprocess.run(
        ["sudo", "virsh", "undefine", vm_name, "--remove-all-storage"],
        check=True,
        capture_output=True,
    )


def get_vm_status(vm_name: str) -> Optional[str]:
    """Get VM status"""
    try:
        result = subprocess.run(
            ["sudo", "virsh", "dominfo", vm_name],
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
    """Get VM IP address from DHCP leases"""
    try:
        # Use domifaddr (most reliable for running VMs)
        result = subprocess.run(
            ["sudo", "virsh", "domifaddr", vm_name],
            capture_output=True,
            text=True,
        )
        
        if result.returncode == 0 and result.stdout:
            # Parse domifaddr output
            # Format: Name MAC address Protocol Address
            #         vnet4 52:54:00:cc:a6:71 ipv4 192.168.122.117/24
            for line in result.stdout.split("\n"):
                line = line.strip()
                if not line or line.startswith("Name") or line.startswith("-"):
                    continue
                parts = line.split()
                if len(parts) >= 4:
                    # Last column is IP/mask
                    ip_field = parts[-1]
                    if "/" in ip_field:
                        ip = ip_field.split("/")[0]
                        if ip and ip != "--":
                            return ip
        
        # Fallback: search DHCP leases
        dhcp_result = subprocess.run(
            ["sudo", "virsh", "net-dhcp-leases", network],
            capture_output=True,
            text=True,
        )
        
        if dhcp_result.returncode == 0 and dhcp_result.stdout:
            for line in dhcp_result.stdout.split("\n"):
                if vm_name in line or "52:54:00" in line:  # QEMU MAC prefix
                    parts = line.split()
                    if len(parts) >= 5:
                        ip_with_mask = parts[4]
                        if "/" in ip_with_mask:
                            return ip_with_mask.split("/")[0]
    except Exception:
        pass
    return None


def wait_for_vm(
    vm_name: str, network: str = "default", timeout: int = 120
) -> Optional[str]:
    """Wait for VM to boot and get IP"""
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
            # Check if VM is running
            status = get_vm_status(vm_name)
            if status and "running" in status.lower():
                progress.update(task, description=f"VM running, getting IP...")
                # Try to get IP
                vm_ip = get_vm_ip(vm_name, network)
                if vm_ip:
                    progress.update(task, completed=True)
                    return vm_ip

            attempt += 1
            if attempt % 5 == 0:
                progress.update(task, description=f"Waiting for {vm_name} to boot... ({attempt * 2}s)")
            time.sleep(2)

    return None
