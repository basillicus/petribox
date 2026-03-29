"""
SSH Operations - SSH connection and file operations
"""

import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from rich.console import Console

console = Console()


def ssh_connect(
    host: str,
    user: str,
    command: Optional[List[str]] = None,
    options: Optional[dict] = None,
):
    """
    Connect via SSH

    Args:
        host: Target host IP
        user: Username
        command: Optional command to execute
        options: SSH options dict
    """
    ssh_opts = [
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "LogLevel=ERROR",
    ]

    if options:
        for key, value in options.items():
            ssh_opts.extend(["-o", f"{key}={value}"])

    cmd = ["ssh"] + ssh_opts + [f"{user}@{host}"]

    if command:
        cmd.extend(command)

    # Run SSH command
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        pass


def ssh_mount(
    host: str,
    user: str,
    host_path: Path,
    vm_path: str,
    options: Optional[dict] = None,
):
    """
    Mount host directory in VM using SSHFS (runs sshfs from inside VM)

    Args:
        host: Target VM IP
        user: VM username
        host_path: Path on host to mount
        vm_path: Mount point inside VM
    """
    ssh_connect(host, user, command=["mkdir", "-p", vm_path])

    console.print("[dim]Installing fuse-sshfs in VM (requires EPEL)...[/dim]")

    ssh_connect(
        host,
        user,
        command=[
            "sudo", "bash", "-c",
            "dnf config-manager --set-enabled crb 2>/dev/null || true; "
            "dnf install -y epel-release 2>/dev/null || true; "
            "dnf install -y fuse-sshfs 2>/dev/null || true"
        ],
    )

    gateway_ip = None
    result = subprocess.run(
        ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
         "-o", "LogLevel=ERROR", f"{user}@{host}",
         "ip route | grep default | awk '{print $3}'"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        gateway_ip = result.stdout.strip()

    if not gateway_ip:
        gateway_ip = "<GATEWAY_IP>"

    host_user = options.get("host_user") if options else None
    if not host_user:
        import getpass
        host_user = getpass.getuser()

    console.print()
    console.print("[yellow]SSHFS requires mounting from inside the VM:[/yellow]")
    console.print()
    console.print(f"  1. SSH into the VM:")
    console.print(f"     [dim]sandbox connect vmname[/dim]")
    console.print()
    console.print(f"  2. Run this command inside the VM:")
    console.print(f"     [cyan]sshfs {host_user}@{gateway_ip}:{host_path} {vm_path}[/cyan]")
    console.print()
    console.print(f"  3. Enter your host password when prompted")
    console.print()
    console.print("[dim]Note: For automatic mounts, use --mount at VM creation time (9p/virtiofs)[/dim]")


def ssh_umount(host: str, user: str, vm_path: str):
    """
    Unmount directory from VM

    Args:
        host: Target host IP
        user: Username
        vm_path: Mount point inside VM to unmount
    """
    ssh_connect(host, user, command=["fusermount", "-u", vm_path])


def ssh_copy_file(
    host: str,
    user: str,
    local_path: Path,
    remote_path: str,
):
    """
    Copy file to VM via SCP

    Args:
        host: Target host IP
        user: Username
        local_path: Local file path
        remote_path: Remote file path
    """
    cmd = [
        "scp",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "LogLevel=ERROR",
        str(local_path),
        f"{user}@{host}:{remote_path}",
    ]
    subprocess.run(cmd, check=True)


def ssh_run_script(
    host: str,
    user: str,
    script_content: str,
    remote_path: str = "/tmp/sandbox-script.sh",
):
    """
    Run a script in VM

    Args:
        host: Target host IP
        user: Username
        script_content: Script content to execute
        remote_path: Where to write script in VM
    """
    # Write script to temp file
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
        f.write(script_content)
        temp_path = f.name

    try:
        # Copy to VM
        ssh_copy_file(host, user, Path(temp_path), remote_path)

        # Make executable and run (use shell to handle &&)
        ssh_connect(
            host,
            user,
            command=["bash", "-c", f"chmod +x {remote_path} && bash {remote_path}"],
        )
    finally:
        import os

        os.unlink(temp_path)
