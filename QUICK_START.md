# Quick Start Guide

Get your first AI sandbox VM running in 5 minutes.

## Prerequisites

```bash
# Fedora/RHEL/Rocky
sudo dnf install virt-install cloud-image-utils libvirt-daemon-system libvirt-clients qemu-img

# Debian/Ubuntu
sudo apt install virtinst qemu-utils libvirt-clients libvirt-daemon-system cloud-image-utils

# Start libvirt
sudo systemctl enable --now libvirtd
```

## One-Time Setup

```bash
# Clone and enter the project
cd vmisos

# Run automated setup
pixi run sandbox initial-setup
```

This will:
1. Check for required tools
2. Create SSH keys (or use existing)
3. Download Rocky Linux 9 image (~2GB)
4. Set up the libvirt network (prompts for sudo)

## Networking

### Option A: Libvirt Network (Recommended)

When prompted during `initial-setup` or `create`, choose to create the network with sudo.

**Benefits:**
- Each VM gets a unique IP (192.168.123.x)
- VMs can communicate with each other
- Direct SSH access from host
- VMs can reach the Internet

**Requires:** One-time sudo for network creation, then all VM operations are sudo-free.

### Option B: SLIRP (User-Mode)

If you don't have sudo or prefer not to use it:

```bash
pixi run sandbox create my-vm --slirp
```

**Limitations:**
- Fixed IP (10.0.2.15) - not reachable from host
- No VM-to-VM communication
- Requires port forwarding for host access

## Create Your First Sandbox

```bash
# Interactive mode (recommended for first time)
pixi run sandbox create --tui

# Or with a preset
pixi run sandbox create ai-lab --preset ai-researcher

# Or with SLIRP (no sudo)
pixi run sandbox create test-vm --slirp
```

## Connect to Your Sandbox

### Libvirt Network Mode

```bash
# Direct SSH
pixi run sandbox ssh my-vm

# Or with standard SSH
pixi run sandbox list  # Get IP
ssh sandbox@192.168.123.x
```

### SLIRP Mode

```bash
# Port forward SSH
pixi run sandbox port-forward my-vm 22 --local-port 2222

# Then connect
ssh -p 2222 sandbox@localhost
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

## Troubleshooting

### VM won't boot
```bash
pixi run sandbox console my-vm  # Check console output
```

### Can't connect via SSH
Wait 2-3 minutes for cloud-init to complete on first boot.

### Network not found
Run `pixi run sandbox initial-setup` again, or use `--slirp` flag.

---

For full documentation, see [README.md](README.md).
