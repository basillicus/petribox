# Refactor Plan: Installation & Privileges

## Status Update (Session Pause)
- [x] Improved Arch Linux support (pacman).
- [x] Added modular libvirt daemon support (virtqemud).
- [x] Fixed Disk Sizing Bug (added `qemu-img resize`).
- [x] Added VT-x/AMD-V detection and troubleshooting.
- [x] Improved TUI SSH key discovery.
- [ ] Refactor Mise/Agent installation (Next Task).

## The Plan for `refactor-installation-privileges` branch:

### 1. Mise Refactor
- **Current Issue**: Installing mise per-user in `~/.local/bin` and using `sudo` to manage it causes permission friction and is non-idiomatic.
- **Solution**:
    - Install `mise` globally to `/usr/local/bin`.
    - Generate `~/.config/mise/config.toml` via `write_files` in cloud-init.
    - Run `su - {user} -c "mise install -y"` to fetch runtimes.

### 2. Agent Installation Refactor
- **Current Issue**: Installers run as root or require `chown` hacks.
- **Solution**:
    - Ensure all `runcmd` items for agents are wrapped in user context switches (`su - {user}`).
    - Ensure environment variables (like `HOME`) are correctly set during the cloud-init `runcmd` phase.

### 3. Verification Steps
- [ ] Boot VM on Arch with VT-x enabled.
- [ ] Check `~/.config/mise/config.toml` exists and is owned by user.
- [ ] Check `mise ls` shows runtimes installed without sudo.
- [ ] Check agent folder (e.g., `~/hermes`) is owned by user.

## How to Resume
1. Finish BIOS update and ensure VT-x is enabled.
2. Check if `/dev/kvm` exists.
3. Switch to the `refactor-installation-privileges` branch.
4. Run `pixi run sandbox create --tui` to test the new logic.
