# Sandbox - AI Experiment VM Manager

Quick and isolated Rocky Linux 9 sandboxes for AI experiments, Agentic AI development, and evaluation.

## Features

- **One-command VM creation** - Fully configured Rocky Linux 9 VMs with cloud-init
- **SSH access** - Direct SSH to VMs (standard `ssh user@ip`)
- **Lifecycle management** - Create, list, start, stop, delete VMs
- **Data sharing** - Mount host directories via 9p/virtiofs or SSHFS
- **Dotfiles support** - Apply your configs from git, local path, or presets
- **Configuration files** - YAML configs for packages, tools, and environment
- **Interactive TUI** - Menu-driven creation with preset configurations
- **Extensible** - Python-based, easy to add new features

---

## Quick Start

### One-Time Setup

Run the automated setup to install prerequisites, create SSH keys, and download Rocky Linux:

```bash
# Run initial setup (guides you through each step)
pixi run sandbox initial-setup

# Optional: Specify Rocky Linux version (9 or 10)
pixi run sandbox initial-setup --rocky-version 10

# Optional: Specify custom image location
pixi run sandbox initial-setup --image-path /path/to/image.qcow2
```

**Note:** You will be prompted for your sudo password when creating or managing sandboxes. This is required because libvirt needs system-level access to create VMs and manage storage.

The setup will:
1. Check for required tools and show install commands if missing
2. Verify libvirt service is running
3. Create or reuse SSH keys for VM access
4. Download and verify Rocky Linux image (checksum verified)
5. Suggest a convenient shell alias

### Prerequisites

```bash
# Install required packages (Fedora/RHEL/Rocky)
sudo dnf install virt-install cloud-image-utils libvirt-daemon-system libvirt-clients

# Install required packages (Debian/Ubuntu)
sudo apt install virtinst qemu-utils libvirt-clients libvirt-daemon-system

# Start libvirt
sudo systemctl enable --now libvirtd

# Add user to libvirt group (optional, to run without sudo)
sudo usermod -aG libvirt $USER
newgrp libvirt
```

### Setup with Pixi

After installing system prerequisites, set up the Python environment:

```bash
# Install dependencies in isolated environment
pixi install

# Add alias for convenience (optional)
echo 'alias sandbox="cd $(pwd) && pixi run sandbox"' >> ~/.bashrc
source ~/.bashrc
```

Now you're ready to create sandboxes!

### Create Your First Sandbox

```bash
# Using TUI (interactive)
pixi run sandbox create --tui

# Or directly with preset
pixi run sandbox create my-ai-lab --preset ai-researcher --ram 8192 --cpus 4
```

### Connect to Your Sandbox

You have two options to connect:

**Option 1: Using the `connect` wrapper (convenient)**
```bash
# The sandbox tool looks up the IP for you
pixi run sandbox connect my-sandbox
```

**Option 2: Using standard SSH (more control)**
```bash
# 1. Get the VM IP address
pixi run sandbox list
# or
sudo virsh domifaddr <vm-name>

# 2. SSH directly (works from any machine)
ssh <username>@<ip-address>

# Example:
ssh usersand@192.168.122.117
```

**Recommendation:** Use `sandbox connect` for quick access from your host machine. Use standard `ssh` when you need more control, want to connect from IDEs, or are connecting from a different machine.

---

## Workflow

### Typical Usage Pattern

```bash
# 1. Create a sandbox (one-time)
pixi run sandbox create my-experiment --preset ai-researcher

# 2. Get connection info
pixi run sandbox list
# Output shows: Name, IP, Username, Status

# 3. Connect (two options)
#    Option A: Use the connect wrapper (convenient)
pixi run sandbox connect my-experiment

#    Option B: Use standard SSH (more control, works from anywhere)
ssh myuser@192.168.122.xxx

# 4. Work in the VM as you would any Linux machine
#    - Install packages: sudo dnf install ...
#    - Run experiments: python3 train.py
#    - Edit files: nvim script.py

# 5. When done, stop the VM (saves resources)
pixi run sandbox down my-experiment

# 6. Resume later
pixi run sandbox up my-experiment
pixi run sandbox connect my-experiment
# or: ssh myuser@192.168.122.xxx
```

---

## Sandbox CLI Commands

### VM Management

```bash
# Create a new sandbox
pixi run sandbox create <name> [options]
pixi run sandbox create --tui  # Interactive mode

# List all sandboxes
pixi run sandbox list

# Show detailed status
pixi run sandbox status <name>

# Start a stopped sandbox
pixi run sandbox up <name>

# Stop a running sandbox
pixi run sandbox down <name>

# Delete a sandbox (removes VM and disk)
pixi run sandbox delete <name>

# Connect via SSH (wrapper command)
pixi run sandbox connect <name>
```

### Create Options

| Option | Description | Default |
|--------|-------------|---------|
| `--ram MB` | RAM in MB | 4096 |
| `--cpus NUM` | Number of CPUs | 2 |
| `--disk GB` | Disk size in GB | 20 |
| `--user NAME` | Username | sandbox |
| `--password PASS` | User password (optional) | none |
| `--ssh-key PATH` | SSH public key file | ~/.ssh/id_ed25519.pub |
| `--shell TYPE` | Shell to configure (bash/zsh) | bash |
| `--preset NAME` | Configuration preset | none |
| `--dotfiles SRC` | Dotfiles: git URL, local path, or preset | none |
| `--mount PATH:PATH` | Mount host directory (repeatable) | none |
| `--config FILE` | YAML configuration file | none |
| `--tui` | Interactive creation mode | false |

### Examples

```bash
# Quick development sandbox
pixi run sandbox create devbox --preset dev

# AI research environment
pixi run sandbox create ai-lab --preset ai-researcher --ram 16384 --cpus 6

# With custom dotfiles from git
pixi run sandbox create mybox --dotfiles https://github.com/youruser/dotfiles

# With shared data directory
pixi run sandbox create data-sandbox \
  --mount ~/datasets:/datasets \
  --mount ~/projects:/projects

# With configuration file
pixi run sandbox create custom --config my-config.yaml

# Agentic AI development with Docker
pixi run sandbox create agent-dev --preset agentic --ram 8192
```

---

## Rocky Linux Basics

Once connected to your sandbox via SSH, here are the essential commands for managing your Rocky Linux 9 VM.

### Package Management (DNF)

```bash
# Install packages
sudo dnf install <package-name>

# Install multiple packages
sudo dnf install git vim python3-pip nodejs

# Search for packages
sudo dnf search <keyword>

# Update all packages
sudo dnf update

# Update specific package
sudo dnf update <package-name>

# Remove packages
sudo dnf remove <package-name>

# List installed packages
dnf list installed

# Show package info
dnf info <package-name>

# Install without weak dependencies (minimal install)
sudo dnf install --setopt=install_weak_deps=False <package>
```

### Common Package Groups

```bash
# Development tools
sudo dnf groupinstall "Development Tools"

# Install C/C++ compilers
sudo dnf install gcc gcc-c++ make

# Install Python development
sudo dnf install python3 python3-pip python3-devel

# Install Node.js
sudo dnf install nodejs npm

# Install Docker
sudo dnf install docker docker-compose
sudo systemctl enable --now docker
sudo usermod -aG docker $USER

# Install essential tools
sudo dnf install vim git curl wget tmux htop tree jq
```

### Mise Version Manager (Auto-installed)

**Mise** is automatically installed in all sandboxes along with required system dependencies (`libatomic`, `openssl-devel`, `bzip2-devel`, `libffi-devel`).

**Shell activation** is automatically configured for bash (~/.bashrc) and/or zsh (~/.zshrc).

```bash
# Install global versions of tools
mise use -g node@20
mise use -g python@3.12
mise use -g go@1.21

# Install project-specific versions (creates .mise.toml)
mise use node@18
mise use python@3.11

# List installed versions
mise ls

# List current active versions
mise current

# Update a tool
mise upgrade node

# Update all tools
mise upgrade

# Remove a tool
mise uninstall node@18
```

**Popular mise packages:**
- `node@20`, `node@18`, `node@lts`
- `python@3.12`, `python@3.11`
- `go@1.21`, `go@latest`
- `rust@latest`
- `java@17`, `java@21`
- `bun@latest`, `deno@latest`
- `kubectl@latest`, `terraform@latest`, `gh@latest`

**Shell Options:**
```bash
# Create with bash (default)
pixi run sandbox create mybox --shell bash

# Create with zsh
pixi run sandbox create mybox --shell zsh
```

### System Management

```bash
# Check system info
hostnamectl
uname -a
cat /etc/os-release

# Check disk usage
df -h
du -sh /path/to/dir

# Check memory
free -h

# Check running processes
top
htop
ps aux

# Check services
systemctl list-units --type=service
systemctl status <service-name>

# Start/stop/restart services
sudo systemctl start <service>
sudo systemctl stop <service>
sudo systemctl restart <service>
sudo systemctl enable <service>  # Start on boot
```

### User Management

```bash
# Create new user
sudo useradd -m -G wheel newuser

# Set password
sudo passwd newuser

# Delete user
sudo userdel -r username

# Switch to another user
su - username

# Run command as another user
sudo -u username command
```

### File Permissions

```bash
# Change ownership
sudo chown user:group file

# Change permissions
chmod 755 file      # rwxr-xr-x
chmod 644 file      # rw-r--r--
chmod +x script.sh  # Make executable

# View permissions
ls -la
```

### Network

```bash
# Check IP address
ip addr show
hostname -I

# Check network connections
ss -tulpn
netstat -tulpn

# Test connectivity
ping google.com
curl -I https://example.com

# Check firewall
sudo firewall-cmd --list-all
sudo firewall-cmd --add-port=8080/tcp --permanent
sudo firewall-cmd --reload
```

---

## Configuration Files

Create YAML configs for reproducible environments:

```yaml
# my-config.yaml
packages:
  - vim-enhanced
  - python3-pip
  - nodejs
  - git
  - tmux

mise_packages:
  - node@20
  - python@latest
  - go@1.21

pip_packages:
  - jupyterlab
  - numpy
  - pandas

environment:
  EDITOR: vim
  MY_VAR: value

runcmd:
  - echo "Setup complete"
```

```bash
pixi run sandbox create mybox --config my-config.yaml
```

**Mise** is automatically installed during VM creation. Global packages from `mise_packages` are installed and available in your PATH.

See `examples/` for complete configuration examples including mise setups.

---

## Presets

| Preset | RAM | CPUs | Disk | Use Case |
|--------|-----|------|------|----------|
| `minimal` | 2GB | 1 | 15GB | Basic testing, lightweight tasks |
| `dev` | 4GB | 2 | 25GB | General development |
| `ai-researcher` | 8GB | 4 | 40GB | ML/AI work with Jupyter |
| `agentic` | 8GB | 4 | 50GB | Agentic AI with LangChain, Docker |

### Package Lists by Preset

**All presets include mise** (version manager) auto-installed.

**minimal:**
- vim, python3, git, curl, wget, tmux, htop

**dev:**
- All minimal packages + gcc, make, nodejs (via mise), npm (via mise)

**ai-researcher:**
- All dev packages + python3-pip, jupyterlab, numpy, pandas, scikit-learn, matplotlib
- mise: python@latest, jupyterlab, numpy, pandas

**agentic:**
- All ai-researcher packages + docker, langchain, langgraph, pydantic
- mise: node@20, python@latest, langchain tools

---

## Dotfiles

Apply your development environment automatically at VM creation:

```bash
# From git repository
pixi run sandbox create mybox --dotfiles https://github.com/youruser/dotfiles

# From local directory
pixi run sandbox create mybox --dotfiles ~/.dotfiles

# Using built-in preset
pixi run sandbox create mybox --dotfiles dev
```

Built-in presets:
- `minimal` - Basic vim configuration
- `dev` - Enhanced vim, tmux, git config
- `ai-researcher` - + Jupyter configuration

---

## Data Sharing

### At Creation (9p/virtiofs)

```bash
pixi run sandbox create mybox \
  --mount ~/data:/data \
  --mount ~/projects:/projects \
  --mount-type 9p
```

**Note:** 9p mounts require VM restart to activate:
```bash
pixi run sandbox down mybox && pixi run sandbox up mybox
```

Inside the VM, add to `/etc/fstab`:
```
hostshare /data 9p _netdev,trans=virtio,version=9p2000.L,rw 0 0
```

### Runtime (SSHFS from inside VM)

From **inside the VM**, mount host directories:

```bash
# Install SSHFS in VM
sudo dnf install fuse-sshfs

# Mount host directory
sshfs user@host-ip:/host/path /mnt/path
```

---

## Troubleshooting

### VM won't boot
```bash
# Check VM status
pixi run sandbox list

# View console
sudo virsh console <name>

# Check libvirt logs
sudo journalctl -u libvirtd
```

### Can't connect via SSH
```bash
# Wait 2-3 minutes for cloud-init (first boot only)
# Check if VM is running
pixi run sandbox status <name>

# Check IP address
sudo virsh domifaddr <name>

# Verify SSH key was injected
sudo virsh console <name>
# Login and check: cat ~/.ssh/authorized_keys
```

### Permission denied for virsh
```bash
# Add user to libvirt group
sudo usermod -aG libvirt $USER
newgrp libvirt
```

### No default network
```bash
sudo virsh net-define /usr/share/libvirt/networks/default.xml
sudo virsh net-start default
sudo virsh net-autostart default
```

### VM stuck in "creating" status
```bash
# Force delete from database
pixi run sandbox delete <name> --force

# Clean up any leftover VMs
sudo virsh list --all
sudo virsh destroy <name> 2>/dev/null
sudo virsh undefine <name> --remove-all-storage 2>/dev/null
```

### Disk Space Management

**Yes, deleting a VM removes its disk and frees space!**

When you run `sandbox delete <name>`:
1. VM is stopped (if running)
2. VM definition is removed from libvirt
3. **Disk image is deleted** (frees disk space)
4. Database record is marked as destroyed

```bash
# Check disk usage before
du -sh /var/lib/libvirt/images/

# Delete VM
pixi run sandbox delete mybox

# Check disk usage after (space is freed)
du -sh /var/lib/libvirt/images/
```

To verify a specific VM disk is removed:
```bash
ls -lh /var/lib/libvirt/images/<vm-name>.qcow2
# Should show: No such file or directory
```

### Sudo Usage

The sandbox tool uses `sudo` for VM operations (creation, start, stop, etc.) as it needs to interact with libvirt and system storage.

**Optional: Configure passwordless sudo for libvirt**

To avoid entering your password each time:

```bash
# Add user to libvirt group (optional, for non-sudo virsh commands)
sudo usermod -aG libvirt $USER

# Create sudoers rule for passwordless libvirt access
sudo visudo -f /etc/sudoers.d/libvirt

# Add this line:
%libvirt ALL=(ALL) NOPASSWD: /usr/bin/virsh, /usr/bin/virt-install, /usr/bin/qemu-img
```

---

## Architecture

```
sandbox CLI (Creation & Management Only)
├── database.py      # SQLite tracking of VMs (~/.sandbox/sandboxes.db)
├── libvirt_ops.py   # VM creation via virt-install
├── commands.py      # CLI command implementations
├── ssh_ops.py       # SSH operations
├── mount_ops.py     # 9p/virtiofs mounts
├── dotfiles.py      # Dotfiles management
├── config_loader.py # YAML config parsing
└── tui.py           # Interactive creation UI

Daily Usage
└── Standard SSH (ssh user@ip) - No tool needed
```

---

## Project Structure

```
vmisos/
├── sandbox/                  # Python package
│   ├── __init__.py
│   ├── __main__.py           # Entry point
│   ├── cli.py                # CLI argument parsing
│   ├── commands.py           # Command implementations
│   ├── database.py           # SQLite database
│   ├── libvirt_ops.py        # Libvirt operations
│   ├── ssh_ops.py            # SSH operations
│   ├── mount_ops.py          # Mount operations
│   ├── dotfiles.py           # Dotfiles management
│   ├── config_loader.py      # Config loading
│   ├── tui.py                # Interactive TUI
│   └── requirements.txt      # Python dependencies
├── examples/                 # Example configs
│   ├── config-minimal.yaml
│   ├── config-agentic.yaml
│   └── config-ai-researcher.yaml
├── pixi.toml                 # Pixi environment
├── sandbox.sh                # Wrapper script
├── QUICK_REFERENCE.md        # Quick command reference
└── Rocky-9-*.qcow2           # Base image
```

---

## Extending

The tool is designed to be easily extensible:

1. **New commands** - Add to `cli.py` and implement in `commands.py`
2. **New presets** - Add to `PRESETS` dict in `commands.py` or `tui.py`
3. **New dotfiles** - Add to `DOTFILE_PRESETS` in `dotfiles.py`
4. **Custom packages** - Use YAML config files

---

## License

MIT
