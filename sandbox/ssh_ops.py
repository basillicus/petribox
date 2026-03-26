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
    Mount host directory in VM using SSHFS

    Args:
        host: Target host IP
        user: Username
        host_path: Path on host to mount
        vm_path: Mount point inside VM
    """
    # First, create the mount point in VM
    ssh_connect(host, user, command=["mkdir", "-p", vm_path])

    # Use SSHFS to mount
    # Note: SSHFS runs on the host and mounts remote filesystem
    # For mounting host->VM, we need a different approach
    # We'll use 9p or instruct user to mount from inside VM

    console.print("[yellow]SSHFS mounts from host to VM require additional setup[/yellow]")
    console.print("[dim]Installing sshfs in VM...[/dim]")

    # Install sshfs in VM
    ssh_connect(
        host,
        user,
        command=[
            "sudo",
            "dnf",
            "install",
            "-y",
            "fuse-sshfs",
        ],
    )

    # Create a reverse mount script in VM
    mount_script = f"""#!/bin/bash
# Mount {host_path} to {vm_path}
# Run this from inside the VM, providing host details

HOST_IP=$(ip route | grep default | awk '{{print $3}}')
sshfs {user}@${{HOST_IP}}:{host_path} {vm_path} -o allow_other
"""

    console.print("[green]Mount instructions:[/green]")
    console.print(f"[dim]1. From inside VM, run:[/dim]")
    console.print(f"   sshfs {user}@<host-ip>:{host_path} {vm_path}")
    console.print(f"[dim]2. Or use the gateway approach with 9p[/dim]")


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
