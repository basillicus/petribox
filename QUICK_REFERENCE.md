# Sandbox Quick Reference

## First-Time Setup

```bash
# Run the automated setup
pixi run sandbox initial-setup

# This will:
# - Check for required tools (and show install commands)
# - Verify libvirt is running
# - Create SSH key for VMs
# - Download Rocky Linux image (with checksum verification)
# - Suggest a shell alias

# Note: You'll be prompted for sudo password when managing VMs
# (libvirt requires system-level access to create VMs)
```

---

## Your Current Setup

**VM Name**: `testingsand`  
**Username**: `usersand`  
**IP**: Auto-detected (check with `pixi run sandbox list`)

---

## Daily Workflow

```bash
# 1. Create sandbox (one-time)
pixi run sandbox create mybox --preset dev

# 2. Get IP address
pixi run sandbox list

# 3. Connect (two options)
#    Option A: Use the connect wrapper (convenient)
pixi run sandbox connect mybox

#    Option B: Use standard SSH (more control, works from anywhere)
ssh usersand@192.168.122.xxx

# 4. Work in VM (install packages, run code, etc.)
#    See "Rocky Linux Commands" below

# 5. Stop VM when done (saves resources)
pixi run sandbox down mybox

# 6. Resume later
pixi run sandbox up mybox
pixi run sandbox connect mybox
# or: ssh usersand@192.168.122.xxx
```

---

## Sandbox Management Commands

```bash
# First-time setup
pixi run sandbox initial-setup

# Create (interactive TUI)
pixi run sandbox create --tui

# Create (CLI)
pixi run sandbox create mybox --preset dev --ram 4096 --cpus 2

# List all sandboxes
pixi run sandbox list

# Show detailed status
pixi run sandbox status mybox

# Start/Stop
pixi run sandbox up mybox
pixi run sandbox down mybox

# Delete
pixi run sandbox delete mybox

# Connect via SSH (wrapper)
pixi run sandbox connect mybox
```

---

## Rocky Linux Commands (Inside VM)

### Package Management

```bash
# Install packages
sudo dnf install <package>

# Install multiple
sudo dnf install git vim python3-pip nodejs

# Update all
sudo dnf update

# Search
sudo dnf search <keyword>

# Remove
sudo dnf remove <package>

# Minimal install (fewer dependencies)
sudo dnf install --setopt=install_weak_deps=False <package>
```

### Mise Version Manager (Auto-installed)

**Mise** is automatically installed with all required system dependencies (`libatomic`, `openssl-devel`, etc.).

```bash
# Install global versions
mise use -g node@20
mise use -g python@3.12
mise use -g go@1.21

# List installed
mise ls

# Update all
mise upgrade

# Popular packages: node, python, go, rust, java, bun, deno, kubectl, terraform
```

### Common Installs

```bash
# Development tools
sudo dnf groupinstall "Development Tools"

# Python
sudo dnf install python3 python3-pip python3-devel

# Node.js
sudo dnf install nodejs npm

# Docker
sudo dnf install docker docker-compose
sudo systemctl enable --now docker
sudo usermod -aG docker $USER

# Essentials
sudo dnf install vim git curl wget tmux htop tree jq
```

### System Info

```bash
# System info
hostnamectl
cat /etc/os-release

# Disk usage
df -h
du -sh /path

# Memory
free -h

# Processes
top
htop

# Services
systemctl list-units --type=service
systemctl status <service>
```

### Network

```bash
# IP address
ip addr show
hostname -I

# Test connectivity
ping google.com
curl -I https://example.com
```

---

## Presets

| Preset | RAM | CPUs | Best For |
|--------|-----|------|----------|
| `minimal` | 2GB | 1 | Quick tests |
| `dev` | 4GB | 2 | Development |
| `ai-researcher` | 8GB | 4 | ML/AI work |
| `agentic` | 8GB | 4 | Agentic AI |

---

## Tips

1. **First boot**: Takes 2-3 minutes (cloud-init)
2. **Subsequent boots**: ~15 seconds
3. **SSH only**: No password by default, uses your SSH key
4. **Stop VMs**: Use `sandbox down` when not in use (saves CPU/RAM)
5. **Two connection options**:
   - `sandbox connect <name>` - Convenient wrapper (auto-discovers IP)
   - `ssh user@ip` - Direct SSH (works from IDEs, other machines)
6. **Disk freed**: `sandbox delete` removes VM and frees disk space
7. **Sudo**: Required for VM operations (or configure passwordless sudo)

---

## Sudo Configuration

**Optional: Passwordless sudo for libvirt**

```bash
# Add to sudoers (run: sudo visudo -f /etc/sudoers.d/libvirt)
%libvirt ALL=(ALL) NOPASSWD: /usr/bin/virsh, /usr/bin/virt-install, /usr/bin/qemu-img
```

---

## Disk Space

**Deleting a VM frees disk space:**

```bash
# Delete VM
pixi run sandbox delete mybox

# Disk space is automatically freed
# VM disk at /var/lib/libvirt/images/<name>.qcow2 is removed
```

```bash
# VM not responding?
pixi run sandbox status mybox

# Need IP?
sudo virsh domifaddr mybox

# Console access?
sudo virsh console mybox

# Force restart?
pixi run sandbox down mybox && pixi run sandbox up mybox

# Check libvirt
sudo virsh list --all
```
