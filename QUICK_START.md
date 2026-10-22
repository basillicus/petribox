# Quick Start

Get your first AI-agent dish running in a couple of minutes.

> **Platform:** Linux with [Incus](https://github.com/lxc/incus). No per-command sudo.

## 1. Install Incus

```bash
# Debian/Ubuntu
sudo apt install -y incus
# Fedora
sudo dnf install -y incus
# Arch (the daemon is not started on install; cdrtools is needed for VMs)
sudo pacman -S incus cdrtools virtiofsd
sudo systemctl enable --now incus.socket incus.service

# Join the group (full management) and re-login for it to take effect
sudo usermod -aG incus-admin $USER   # or 'incus' on some distros
```

Don't want to log out? `newgrp incus-admin` picks up the group in the current
shell only. Repeat it in each new terminal until your next login.

### Arch notes

- `virtiofsd` installs to `/usr/lib/virtiofsd` (not on `PATH`). Incus finds it there.
- Without `cdrtools` (`mkisofs`), VMs fail to start with
  `Neither mkisofs nor genisoimage could be found`. Containers don't need it.
- `Failed to connect to local daemon ... unix.socket: no such file` means the
  daemon isn't running. Run the `systemctl enable --now` line above.

## 2. One-time setup

```bash
# Install petribox as a user-wide command (puts it in ~/.local/bin)
# Get uv: https://docs.astral.sh/uv/  (or use: pipx install git+...)
uv tool install git+https://github.com/<owner>/petribox
# from a local checkout: uv tool install .   (upgrade later: uv tool upgrade petribox)

# Initialise Incus + verify prerequisites
petribox initial-setup
```

This runs `incus admin init --minimal` (storage pool + `incusbr0` network),
checks your group membership, and verifies the image remote.

## 3. Create a dish

```bash
# Interactive
petribox create --tui

# Or directly
petribox create lab --preset dev               # VM
petribox create fast --container --preset minimal   # container
```

First boot runs cloud-init (1–3 min); later boots take seconds.

## 4. Use it

```bash
petribox connect lab          # shell via incus exec (no SSH needed)
petribox list                 # all dishes
petribox status lab
petribox mount lab ~/data /data
petribox port-forward lab 8888
petribox down lab             # stop when idle
petribox delete lab           # remove
```

## 5. Carry it anywhere

```bash
petribox down lab
petribox export lab -o lab.tar.gz   # move this file to another host
petribox import lab.tar.gz
```

## Presets

| Preset | RAM | CPUs | Use case |
|---|---|---|---|
| `minimal` | 2 GB | 1 | Basic testing |
| `dev` | 4 GB | 2 | General development (node@24) |
| `ai-researcher` | 8 GB | 4 | ML/AI with Jupyter |
| `agentic` | 8 GB | 4 | Agentic AI (LangChain, Docker) |

## Troubleshooting: a dish has no internet (packages/mise missing)

If `cloud-init status` shows `error` and `dnf` can't resolve mirrors, the dish
has IPv6 but no IPv4 — a **host firewall** is dropping the Incus bridge's DHCP/NAT.
A default-deny firewall overrides Incus's own allow rules. Allow `incusbr0`:

```bash
# ufw
sudo ufw allow in on incusbr0
sudo ufw route allow in on incusbr0
sudo ufw route allow out on incusbr0

# firewalld
sudo firewall-cmd --permanent --zone=trusted --add-interface=incusbr0 && sudo firewall-cmd --reload
```

Then recreate the dish. `petribox initial-setup` flags this if it detects ufw/firewalld/Docker.

## Tips

- **No SSH required** — `connect` uses `incus exec`. Pass `--ssh-key` only if you want SSH too.
- **Containers** boot in seconds; **VMs** give full isolation and the cleanest cloud export.
- Full reference: [README.md](README.md). Internals: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
