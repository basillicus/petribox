"""
Mount Operations - 9p and virtiofs mount management
"""

import subprocess
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()


def setup_9p_mount(
    vm_name: str,
    host_path: str,
    vm_path: str,
    mount_tag: str = "hostshare",
):
    """
    Configure 9p mount for a VM

    Note: 9p mounts require VM to be redefined and restarted

    Args:
        vm_name: VM name
        host_path: Path on host to share
        vm_path: Mount point inside VM
        mount_tag: 9p mount tag
    """
    console.print("[yellow]9p mount configuration requires VM restart[/yellow]")

    # Get VM XML
    result = subprocess.run(
        ["sudo", "virsh", "dumpxml", vm_name],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Failed to get VM XML: {result.stderr}")

    xml = result.stdout

    # Check if filesystem already exists
    if f"mount tag='{mount_tag}'" in xml:
        console.print(f"[dim]9p mount '{mount_tag}' already configured[/dim]")
        return

    # Add filesystem device to XML
    fs_xml = f"""
  <devices>
    <filesystem type='mount' accessmode='passthrough'>
      <driver type='virtiofs'/>
      <source dir='{host_path}'/>
      <target dir='{mount_tag}'/>
      <address type='pci' domain='0x0000' bus='0x{len(host_path) % 10:02x}' slot='0x00' function='0x0'/>
    </filesystem>
  </devices>
"""

    # This is a simplified approach - in practice, you'd need to properly
    # insert the filesystem element into the <devices> section
    console.print("[dim]Adding 9p filesystem device to VM configuration...[/dim]")

    # For now, provide manual instructions
    console.print("[yellow]Manual configuration required:[/yellow]")
    console.print(f"""
1. Edit VM XML: sudo virsh edit {vm_name}

2. Add this inside the <devices> section:

   <filesystem type='mount' accessmode='passthrough'>
     <driver type='virtiofs'/>
     <source dir='{host_path}'/>
     <target dir='{mount_tag}'/>
   </filesystem>

3. Restart VM: sandbox down {vm_name} && sandbox up {vm_name}

4. Inside VM, add to /etc/fstab:
   {mount_tag} {vm_path} 9p _netdev,trans=virtio,version=9p2000.L,rw 0 0

5. Mount: sudo mount {vm_path}
""")


def remove_9p_mount(vm_name: str, mount_tag: str):
    """
    Remove 9p mount configuration from VM

    Args:
        vm_name: VM name
        mount_tag: 9p mount tag to remove
    """
    console.print("[dim]Removing 9p mount configuration...[/dim]")

    # Get VM XML
    result = subprocess.run(
        ["sudo", "virsh", "dumpxml", vm_name],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Failed to get VM XML: {result.stderr}")

    console.print("[yellow]Manual removal required:[/yellow]")
    console.print(f"""
1. Edit VM XML: sudo virsh edit {vm_name}

2. Remove the <filesystem> section with mount tag '{mount_tag}'

3. Restart VM: sandbox down {vm_name} && sandbox up {vm_name}

4. Inside VM, remove from /etc/fstab and unmount
""")


def setup_virtiofs(
    vm_name: str,
    host_path: str,
    vm_path: str,
    socket_path: Optional[str] = None,
):
    """
    Configure virtiofs share for a VM

    Args:
        vm_name: VM name
        host_path: Path on host to share
        vm_path: Mount point inside VM
        socket_path: Path for virtiofs socket
    """
    if socket_path is None:
        socket_path = f"/tmp/{vm_name}-virtiofs.sock"

    console.print("[yellow]virtiofs setup requires manual configuration[/yellow]")
    console.print(f"""
1. Start virtiofs daemon on host:
   virtiofsd --socket-path={socket_path} --shared-dir={host_path}

2. Edit VM XML: sudo virsh edit {vm_name}
   Add to <devices>:
   <filesystem type='virtiofs'>
     <source type='unix' socket='{socket_path}'/>
     <target dir='virtiofs0'/>
   </filesystem>

3. Restart VM and mount inside VM
""")
