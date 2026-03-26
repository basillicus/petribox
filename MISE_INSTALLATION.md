# Mise Auto-Installation Implementation

## Overview

Mise (the universal version manager) is now **automatically installed** in all sandboxes during VM creation, along with all required system dependencies. Shell activation is configured for bash (~/.bashrc) and/or zsh (~/.zshrc).

## What Gets Installed

### System Dependencies (Auto-installed)
These are installed via cloud-init `packages:` section **before** any mise commands run:

- `libatomic` - Required by Node.js and other binaries
- `openssl-devel` - For secure connections and native modules
- `bzip2-devel` - Required by some Python/node packages
- `libffi-devel` - Required by Python packages with C extensions

### Mise Installation (runcmd)
Installed via `runcmd` in cloud-init:

1. Enable SSH daemon
2. **Install system dependencies** (dnf install)
3. Download and run mise installer ( curl https://mise.run/bash | sh )
4. **Configure shell activation** if not activated by installtion script (~/.bashrc and/or ~/.zshrc)
5. Install global mise packages (if specified)

### Shell Activation
The following is added to your shell config:

```bash
# ~/.bashrc or ~/.zshrc
# Activate mise (tools/tasks/environment manager written in rust, of course)
eval "$($HOME/.local/bin/mise activate bash)"
```

**Shell Options:**
```bash
# Create with bash (default)
pixi run sandbox create mybox --shell bash

# Create with zsh
pixi run sandbox create mybox --shell zsh
```

## Installation Order

```yaml
# cloud-init user-data
packages:
  - vim
  - git
  - curl
  - libatomic              # ← System deps installed first
  - openssl-devel
  - bzip2-devel
  - libffi-devel

runcmd:
  - [systemctl, enable, --now, sshd]
  - [dnf, install, -y, libatomic, ...]  # ← Redundant but ensures installation
  - [curl, mise.run]       # ← Then mise is downloaded
  - [mise, use, -g, ...]   # ← Finally, mise packages installed
```

## Usage

### In Configuration File

```yaml
# my-config.yaml
packages:
  - vim-enhanced
  - git

mise_packages:
  - node@20
  - python@3.12
  - go@1.21
```

### Create VM

```bash
pixi run sandbox create mybox --config my-config.yaml
```

### Connect and Verify

```bash
ssh user@vm-ip

# Check mise
mise --version

# Check installed tools
node --version
python --version
go version
```

## For Existing VMs

If you have a VM that was created before this fix:

```bash
# SSH into VM
ssh usersand@192.168.122.117

# Install missing dependency
sudo dnf install -y libatomic openssl-devel bzip2-devel libffi-devel

# Mise should now work
mise use -g node@latest
```

## Files Modified

1. **sandbox/libvirt_ops.py** - Added system dependencies to packages and runcmd
2. **sandbox/config_loader.py** - Added documentation note
3. **README.md** - Updated mise documentation
4. **QUICK_REFERENCE.md** - Updated mise section
5. **examples/config-mise-autoinstall.yaml** - New example config

## Example Configs

See `examples/` for mise configurations:
- `config-mise-autoinstall.yaml` - Basic mise setup
- `config-mise-node.yaml` - Node.js development
- `config-mise-python.yaml` - Python development
- `config-mise-multilang.yaml` - Multi-language setup

## Troubleshooting

### Node.js fails with "libatomic.so.1: cannot open shared object file"

```bash
# Install missing dependency
sudo dnf install -y libatomic
```

### Mise command not found

```bash
# Source bashrc or restart shell
source ~/.bashrc

# Or use full path
~/.local/share/mise/bin/mise --version
```

### Mise packages fail to install

Check that system dependencies are installed:
```bash
sudo dnf install -y libatomic openssl-devel bzip2-devel libffi-devel
```

Then retry:
```bash
mise use -g node@latest
```
