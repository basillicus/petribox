# Quick Start Guide

Get your first AI sandbox VM running in 5 minutes.

> **Platform:** Tested on Linux only. Windows users may need WSL2 with libvirt. MacOS has not tested.

## Prerequisites

```bash
# Fedora/RHEL/Rocky
sudo dnf install virt-install cloud-image-utils libvirt-daemon-system libvirt-clients qemu-img

# Arch Linux
sudo pacman -S virt-install cloud-image-utils libvirt qemu-desktop openssh

# Debian/Ubuntu
sudo apt install virtinst qemu-utils libvirt-clients libvirt-daemon-system cloud-image-utils

# Start libvirt
sudo systemctl enable --now libvirtd

# Note: On some systems (like Arch Linux), you might prefer modular daemons:
# sudo systemctl enable --now virtqemud.socket virtnetworkd.socket virtstoraged.socket
```

## One-Time Setup

```bash
# Install pixi if you haven't
curl -fsSL https://pixi.sh/install.sh | sh

# Run automated setup
pixi run sandbox initial-setup
```

This will:
1. Check for required tools
2. Create SSH keys (or use existing)
3. Download Rocky Linux 9 image (~0.62GB)
4. Set up the libvirt network

## Create Your First Sandbox

```bash
# Interactive mode (recommended for first time)
pixi run sandbox create --tui

# Or with a preset
pixi run sandbox create ai-lab --preset ai-researcher

# With custom resources
pixi run sandbox create my-vm --preset dev --ram 8192 --cpus 4
```

## Connect to Your Sandbox

```bash
# Using the connect wrapper (auto-discovers IP)
pixi run sandbox connect my-vm

# Or with standard SSH
pixi run sandbox list  # Get IP
ssh sandbox@192.168.122.xxx
```

## Common Commands

```bash
pixi run sandbox list              # List all VMs
pixi run sandbox status my-vm      # Show details
pixi run sandbox up my-vm          # Start VM
pixi run sandbox down my-vm        # Stop VM
pixi run sandbox delete my-vm      # Delete VM
pixi run sandbox console my-vm     # Serial console
```

## Presets

| Preset | RAM | CPUs | Use Case |
|--------|-----|------|----------|
| `minimal` | 2GB | 1 | Basic testing |
| `dev` | 4GB | 2 | General development |
| `ai-researcher` | 8GB | 4 | ML/AI with Jupyter |
| `agentic` | 8GB | 4 | Agentic AI with Docker |

## Tips

1. **First boot**: Takes 2-3 minutes (cloud-init)
2. **Subsequent boots**: ~15 seconds
3. **SSH only**: No password by default, uses your SSH key
4. **Stop VMs**: Use `sandbox down` when not in use (saves CPU/RAM)
5. **Disk freed**: `sandbox delete` removes VM and frees disk space

## Troubleshooting

### "Host does not support any virtualization options"
Enable **VT-x** or **AMD-V** in your BIOS/UEFI settings. If using WSL2, enable `nestedVirtualization=true` in your `.wslconfig`.

### VM won't boot
```bash
pixi run sandbox console my-vm  # Check console output
```

### Can't connect via SSH or packages are not installed
Wait 2-3 minutes for cloud-init to complete on first boot.

---

For full documentation, see [README.md](README.md).
