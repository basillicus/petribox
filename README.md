# Sandbox - AI Experiment VM Manager

Quick and isolated Rocky Linux 9 sandboxes for AI experiments, Agentic AI development, and evaluation.

## Features

- **One-command VM creation** - Fully configured Rocky Linux 9 VMs with cloud-init
- **SSH access** - Via `sandbox connect` command or direct SSH to VMs
- **Lifecycle management** - Create, list, start, stop, delete VMs
- **Data sharing** - Mount host directories via 9p or SSHFS
- **Dotfiles support** - Apply your configs from git repo, local directory, or built-in presets
- **Configuration files** - YAML configs for packages, tools, and environment
- **Interactive TUI** - Menu-driven creation with preset configurations
- **Port forwarding** - Forward VM ports to localhost with background tunnel management
- **Agent installation** - Install AI agents (Hermes, OpenClaw, ZeroClaw) at VM creation
- **Mise auto-installation** - Version manager automatically installed with dependencies

---

## Platform Requirements

**Linux** This tool requires:

- `libvirt` with QEMU/KVM
- `virt-install`, `virsh`, `qemu-img`, `cloud-localds`
- Python 3.10+

**Windows users:** This tool does **not** work on native Windows. Use **WSL2** with libvirt configured inside the WSL2 environment. Not tested

**macOS users:** Not tested.

---

## Quick Start

### One-Time Setup

Install pixi first:

```bash
curl -fsSL https://pixi.sh/install.sh | sh
```

Then run the automated setup:

```bash
pixi run sandbox initial-setup
```

This will:
1. Check for required tools and show install commands if missing
2. Verify libvirt service is running
3. Create or reuse SSH keys for VM access
4. Download and verify Rocky Linux image (checksum verified)
5. Suggest a convenient shell alias

**Note:** You will be prompted for your sudo password when creating or managing sandboxes. This is required because libvirt needs system-level access.

### Prerequisites

```bash
# Install required packages (Fedora/RHEL/Rocky)
sudo dnf install virt-install cloud-image-utils libvirt-daemon-system libvirt-clients

# Install required packages (Debian/Ubuntu)
sudo apt install virtinst qemu-utils libvirt-clients libvirt-daemon-system

# Start libvirt
sudo systemctl enable --now libvirtd

# Add user to  libvirt group
sudo usermod -aG libvirt $USER
newgrp libvirt
```

### Create Your First Sandbox

```bash
# Interactive mode (recommended for first time)
pixi run sandbox create --tui

# Or directly with a preset
pixi run sandbox create my-ai-lab --preset ai-researcher --ram 8192 --cpus 4
```

### Connect to Your Sandbox

```bash
# Option 1: Using the connect wrapper (convenient)
pixi run sandbox connect my-sandbox

# Option 2: Using standard SSH
pixi run sandbox list  # Get IP
ssh sandbox@192.168.122.xxx
```

NOTE: If you have kitty, you may want to run once: 
```bash
kitten ssh sandbox@192.168.122.xxx
```
This will pass all the necesary files to have a fully working terminal on the remote machine.


---

## CLI Commands

### VM Management

| Command | Description |
|---------|-------------|
| `sandbox create <name> [options]` | Create a new sandbox |
| `sandbox create --tui` | Interactive creation mode |
| `sandbox list` | List all sandboxes |
| `sandbox status <name>` | Show detailed status |
| `sandbox up <name>` | Start a stopped sandbox |
| `sandbox down <name>` | Stop a running sandbox |
| `sandbox delete <name>` | Delete a sandbox (removes VM and disk) |
| `sandbox connect <name>` | SSH into a sandbox |
| `sandbox console <name>` | Connect to serial console |

### Create Options

| Option | Description | Default |
|--------|-------------|---------|
| `--ram MB` | RAM in MB | 4096 |
| `--cpus NUM` | Number of CPUs | 2 |
| `--disk GB` | Disk size in GB | 20 |
| `--user NAME` | Username | sandbox |
| `--password PASS` | User password (optional) | none |
| `--ssh-key PATH` | SSH public key file | ~/.ssh/id_ed25519.pub |
| `--shell TYPE` | Shell (bash/zsh) | bash |
| `--preset NAME` | Configuration preset | none |
| `--config FILE` | YAML configuration file | none |
| `--dotfiles SRC` | Dotfiles source | none |
| `--mount HOST:VM` | Mount host directory | none |
| `--agent NAME` | Install AI agent at creation | none |

### Port Forwarding

```bash
# Forward VM port to localhost
sandbox port-forward <name> <port> [--local-port PORT] [-b]

# List active tunnels
sandbox port-forward-list

# Stop a tunnel
sandbox port-forward-stop <name> <port>

# Clean up stale tunnels
sandbox port-forward-clean
```

### Install Command

Install software into a running sandbox:

```bash
# Install an AI agent
sandbox install <name> --agent hermes

# Install mise packages
sandbox install <name> --mise-package node@22 --mise-package python@3.12
```

---

## Presets

| Preset | RAM | CPUs | Disk | Use Case |
|--------|-----|------|------|----------|
| `minimal` | 2GB | 1 | 15GB | Basic testing, lightweight tasks |
| `dev` | 4GB | 2 | 25GB | General development |
| `ai-researcher` | 8GB | 4 | 40GB | ML/AI work with Jupyter |
| `agentic` | 8GB | 4 | 50GB | Agentic AI with LangChain |

### What Each Preset Includes

**All presets include:**
- Mise (version manager) auto-installed
- System dependencies: libatomic, openssl-devel, bzip2-devel, libffi-devel
- Basic tools: vim, python3, git, curl, wget, tmux

**Additional by preset:**
- **dev**: gcc, make, node@24 via mise
- **ai-researcher**: python3-pip, python@3.12 via mise, jupyterlab, numpy, pandas, matplotlib, scikit-learn
- **agentic**: docker, node@24 + python@3.12 via mise, jupyterlab, langchain, langgraph, pydantic, httpx

---

## Configuration Files

Create YAML configs for reproducible environments:

```yaml
# my-config.yaml
packages:
  - vim-enhanced
  - python3-pip
  - git
  - tmux

mise_packages:
  - node@20
  - python@3.12

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

See `examples/` for complete configuration examples.

---

## Dotfiles

Apply your development environment automatically after VM creation. Three sources are supported:

### From Git Repository

```bash
pixi run sandbox create mybox --dotfiles https://github.com/youruser/dotfiles
```

The tool clones your dotfiles repo inside the VM and:
- Runs `install.sh` or `make install` if present
- Otherwise, symlinks dotfiles from `~/.dotfiles` to your home directory

### From Local Directory

```bash
pixi run sandbox create mybox --dotfiles ~/.dotfiles
```

Your local dotfiles are tarballed, copied to the VM via SCP, extracted, and symlinked to the home directory.

### Built-in Presets

```bash
pixi run sandbox create mybox --dotfiles dev
```

Available presets:
- `minimal` - Basic vim and inputrc configuration
- `dev` - Enhanced vim, tmux, and git config
- `ai-researcher` - + Jupyter configuration and ML aliases

---

## AI Agents

Install AI agents at VM creation or into existing VMs:

```bash
# At creation
pixi run sandbox create agent-box --agent hermes

# Into existing VM
sandbox install my-vm --agent openclaw
```

Available agents:
- **hermes** - AI agent for autonomous task execution
- **openclaw** - AI assistant for email, calendar, tasks via chat apps
- **zeroclaw** - Lightweight Rust-based AI assistant

---

## Data Sharing

### 9p Mounts (at creation)

```bash
pixi run sandbox create mybox \
  --mount ~/data:/data \
  --mount ~/projects:/projects
```

Note: 9p mounts require VM restart to activate.

### SSHFS (runtime, from inside VM)

```bash
# From inside the VM
sshfs your-host-user@192.168.122.1:/home/your-host-user/data ~/data
```

---

## Rocky Linux Quick Reference

Inside your sandbox:

```bash
# Package management
sudo dnf install <package>
sudo dnf update
sudo dnf search <keyword>

# Mise (version manager)
mise use -g node@24
mise use -g python@3.12
mise ls

# System info
hostnamectl
df -h
free -h

# Network
ip addr show
ping google.com
```

---

## Troubleshooting

### VM won't boot
```bash
sandbox console <name>  # Check console output
sudo journalctl -u libvirtd
```

### Can't connect via SSH 
Wait 2-3 minutes for cloud-init on first boot. Then:
```bash
sandbox status <name>
sudo virsh domifaddr <name>
```
### Not all packages are installed
Wait 2-3 minutes for cloud-init on first boot. You may be able to connect to the VM before all packages have been fully installed. 

### Permission denied for virsh
```bash
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
sandbox delete <name> --force
```

---

## Architecture

```
sandbox/                   # Python package
├── __init__.py
├── __main__.py           # Entry point
├── cli.py                # CLI argument parsing
├── commands.py           # Command implementations
├── database.py           # SQLite database (~/.sandbox/sandboxes.db)
├── libvirt_ops.py        # Libvirt operations
├── ssh_ops.py            # SSH operations
├── mount_ops.py          # 9p/virtiofs mounts
├── dotfiles.py           # Dotfiles management
├── config_loader.py      # Config loading
├── tunnel_manager.py     # Port-forward tracking
├── agents.py             # AI agent configurations
└── tui.py                # Interactive TUI
```

---

## Project Structure

```
vmisos/
├── sandbox/                  # Python package
├── examples/                 # Example YAML configs
├── pixi.toml                 # Pixi environment
├── sandbox.sh                # Wrapper script
├── README.md                 # This file
├── QUICK_START.md            # Getting started guide
└── Rocky-9-*.qcow2           # Base image (downloaded)
```

---

## Extending

1. **New commands** - Add to `cli.py` and implement in `commands.py`
2. **New presets** - Add to `PRESETS` dict in `commands.py` and `tui.py`
3. **New dotfiles** - Add to `DOTFILE_PRESETS` in `dotfiles.py`
4. **New agents** - Add to `AGENTS` dict in `agents.py`
5. **Custom packages** - Use YAML config files

---

## License

MIT
