# Quick Start

Get your first AI-agent dish running in a couple of minutes.

> **Platform:** Linux with [Incus](https://github.com/lxc/incus). No per-command sudo.

## 1. Install Incus

```bash
# Debian/Ubuntu
sudo apt install -y incus
# Fedora
sudo dnf install -y incus

# Join the group (full management) and re-login for it to take effect
sudo usermod -aG incus-admin $USER   # or 'incus' on some distros
```

## 2. One-time setup

```bash
# Install pixi if needed
curl -fsSL https://pixi.sh/install.sh | sh

# Initialise Incus + verify prerequisites
pixi run petribox initial-setup
```

This runs `incus admin init --minimal` (storage pool + `incusbr0` network),
checks your group membership, and verifies the image remote.

## 3. Create a dish

```bash
# Interactive
pixi run petribox create --tui

# Or directly
pixi run petribox create lab --preset dev               # VM
pixi run petribox create fast --container --preset minimal   # container
```

First boot runs cloud-init (1–3 min); later boots take seconds.

## 4. Use it

```bash
pixi run petribox connect lab          # shell via incus exec (no SSH needed)
pixi run petribox list                 # all dishes
pixi run petribox status lab
pixi run petribox mount lab ~/data /data
pixi run petribox port-forward lab 8888
pixi run petribox down lab             # stop when idle
pixi run petribox delete lab           # remove
```

## 5. Carry it anywhere

```bash
pixi run petribox down lab
pixi run petribox export lab -o lab.tar.gz   # move this file to another host
pixi run petribox import lab.tar.gz
```

## Presets

| Preset | RAM | CPUs | Use case |
|---|---|---|---|
| `minimal` | 2 GB | 1 | Basic testing |
| `dev` | 4 GB | 2 | General development (node@24) |
| `ai-researcher` | 8 GB | 4 | ML/AI with Jupyter |
| `agentic` | 8 GB | 4 | Agentic AI (LangChain, Docker) |

## Tips

- **No SSH required** — `connect` uses `incus exec`. Pass `--ssh-key` only if you want SSH too.
- **Containers** boot in seconds; **VMs** give full isolation and the cleanest cloud export.
- Full reference: [README.md](README.md). Internals: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
