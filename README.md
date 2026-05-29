# Petribox — Incus dishes for AI agents

Spin up isolated, pre-configured Linux **dishes** (Incus VMs or system
containers) to breed, run, and evolve AI agents — then **carry a dish anywhere**
(another machine or the cloud) by exporting/migrating the instance.

It's deliberately opinionated: the goal isn't every Linux knob, it's a *working*
environment that's ready to install and run agents in seconds.

> Backed by [Incus](https://linuxcontainers.org/incus/). No `sudo` per command —
> just membership in the `incus` group. See `docs/ARCHITECTURE.md` for the design
> and `docs/ROADMAP.md` for the agent-comms vision.

## Features

- **One-command dishes** — VMs by default, `--container` for instant lightweight ones.
- **Connect with no SSH** — `petribox connect` uses `incus exec`.
- **Real shared folders** — `--mount HOST:VM` attaches a virtiofs disk device (hot-pluggable).
- **Native port-forwarding** — Incus proxy devices, persistent across reboots.
- **Presets & configs** — `minimal` / `dev` / `ai-researcher` / `agentic`, or your own YAML.
- **Dotfiles** — from a git repo, a local dir, or a built-in preset.
- **Agents** — install Hermes / OpenClaw / ZeroClaw at creation or later.
- **Portability** — `export`/`import` and `move` to a remote Incus host.
- **Comms-ready** — mark dishes for A2A/MCP agent-to-agent communication.

## Requirements

Linux with [Incus](https://github.com/lxc/incus) installed and your user in the
`incus` (or `incus-admin`) group. Python 3.10+. `petribox initial-setup` checks
and helps set all of this up.

## Quick start

```bash
# 1. One-time setup (installs/initialises Incus, checks group membership)
pixi run petribox initial-setup

# 2. Create a dish
pixi run petribox create lab --preset dev          # a VM
pixi run petribox create fast --container --preset minimal   # a container

# 3. Use it
pixi run petribox connect lab
pixi run petribox list
```

Prefer a plain command? `pipx install -e .` (or `pip install -e .`) gives you a
`petribox` executable with no `pixi run` prefix.

First boot runs cloud-init (packages, mise, agent) and takes 1–3 minutes;
subsequent boots are seconds.

## Commands

| Command | Description |
|---|---|
| `create <name> [opts]` / `create --tui` | Create a dish (VM, or `--container`) |
| `list` / `status <name>` | List dishes / show one in detail |
| `up <name>` / `down <name>` / `delete <name>` | Start / stop / delete |
| `connect <name> [cmd]` | Shell (or run a command) via `incus exec` |
| `console <name>` | Attach to the instance console |
| `mount <name> <host> <vm>` / `umount <name> <vm>` | Share / unshare a host dir (virtiofs) |
| `port-forward <name> <port> [--local-port P]` | Forward a dish port to localhost |
| `port-forward-list` / `port-forward-stop <name> <port>` | Manage forwards |
| `install <name> --agent X` / `--mise-package P` | Install into a running dish |
| `export <name> [-o file]` / `import <file> [name]` | Portable backup / restore |
| `move <name> <remote[:name]> [--copy]` | Migrate to a remote Incus host |
| `remote-add <name> <url>` / `remote-list` | Manage remote Incus servers |
| `comms <name> [--protocol a2a\|mcp] [--expose] [--runtime CMD]` | Mark comms-ready |
| `initial-setup [-y]` | Install/initialise Incus prerequisites |

### Create options

`--container`, `--ram MB`, `--cpus N`, `--disk GB`, `--user NAME` (default `petri`),
`--ssh-key PATH` (optional — connect works without it), `--password`, `--image`
(default `images:rockylinux/9/cloud`), `--dotfiles SRC`, `--mount HOST:VM`
(repeatable), `--config FILE`, `--shell bash|zsh`, `--preset NAME`, `--agent NAME`.

## Presets

| Preset | RAM | CPUs | Disk | Includes (beyond base: vim, python3, git, curl, wget, tmux, mise) |
|---|---|---|---|---|
| `minimal` | 2 GB | 1 | 15 GB | — |
| `dev` | 4 GB | 2 | 25 GB | gcc, make, `node@24` (mise) |
| `ai-researcher` | 8 GB | 4 | 40 GB | `python@3.12` (mise), jupyterlab, numpy, pandas, matplotlib, scikit-learn |
| `agentic` | 8 GB | 4 | 50 GB | docker, `python@3.12`+`node@24` (mise), langchain, langgraph, pydantic, httpx |

Preset resources are defaults; override with `--ram/--cpus/--disk`.

## Config files

```yaml
# my-config.yaml
packages: [vim-enhanced, python3-pip]
mise_packages: [node@20, python@3.12]
pip_packages: [jupyterlab, numpy]
environment: { EDITOR: vim }
runcmd: ["echo setup complete"]
```
```bash
pixi run petribox create mybox --config my-config.yaml
```
See `examples/` for more.

## Data sharing

```bash
petribox create box --mount ~/data:/data      # at creation
petribox mount box ~/projects /projects        # at runtime (hot-plug)
```
For VMs this is virtiofs, mounted automatically by the Incus agent at the target path.

## Portability — breed locally, run anywhere

```bash
petribox down lab
petribox export lab -o lab.tar.gz     # self-contained backup
# ...move lab.tar.gz to another machine...
petribox import lab.tar.gz && petribox up lab

# or migrate live to a remote/cloud Incus host:
petribox remote-add cloud https://incus.example.com:8443
petribox move lab cloud
```

## Agent communication (preview)

`petribox comms <name>` marks a dish ready for agent-to-agent comms: it records a
protocol + port and (with `--expose`) opens it. Dishes reach each other by Incus
DNS name (`<name>.incus`). Standards: **A2A** for agent↔agent, **MCP** for
agent↔tools/knowledge. Full protocol support and a shared knowledge store are on
the roadmap — see `docs/ROADMAP.md`.

## Development

```bash
pip install -e ".[test]"
pytest -m "not e2e"            # fast unit tests (mock incus)
PETRIBOX_E2E=1 pytest -m e2e   # real Incus instances (opt-in; not in CI)
```

See `docs/E2E-CHECKLIST.md` for the manual walkthrough and `docs/ARCHITECTURE.md`
for internals.

## License

MIT
