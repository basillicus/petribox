# Petribox

Opinionated convenience on top of [Incus](https://linuxcontainers.org/incus/) for spinning up Linux environments ready to run AI agents.

If you know Incus well, petribox is mostly convenience. Its value is that it encodes the tribal knowledge — cloud-init YAML, mise setup, Rocky-specific quirks, DHCPv4 network config, which packages the Rocky cloud image is missing — into named presets. You get a working environment with one command instead of writing 60 lines of YAML and hitting three non-obvious bugs.

```bash
petribox create lab --preset dev          # VM, 4 GB RAM, mise + node@24
petribox create fast --container --preset minimal   # container, boots in seconds
petribox connect lab                      # shell as the configured user, not root
```

vs the raw Incus equivalent: write `user-data.yaml` + `network-config.yaml`, know that Rocky needs `agent:config` added before start, know that `tar`/`gzip` and `openssh-server` are missing from the cloud image, know to run mise as the user not root, manually poll for cloud-init, then `su -` to your user because `incus exec` gives you root.

**What petribox is not:** a security sandbox, a policy engine, or an agent framework. It is a provisioning layer.

## What it does

- **Presets** — `minimal` / `dev` / `ai-researcher` / `agentic` encode opinionated defaults for RAM, CPU, disk, packages, and mise toolchains.
- **cloud-init generation** — builds the user-data and network-config YAML correctly for Rocky Linux VMs (the gotchas are handled for you).
- **User setup** — `--user alice` creates the user, wires SSH keys, stores it, and `petribox connect` drops you in as that user.
- **Portability** — `export`/`import`/`move` to migrate a dish to another machine or a remote Incus host.
- **Mounts** — `petribox mount` attaches a host directory via virtiofs (VMs) or bind mount (containers). Requires `virtiofsd` installed on the host for VMs.
- **Port-forwards** — Incus proxy devices, persistent across reboots.
- **Agent installs** — `--agent hermes` wires an agent's install script and mise packages into cloud-init.

## Requirements

Linux, [Incus](https://github.com/lxc/incus) installed, user in the `incus` or `incus-admin` group. Python 3.10+.

```bash
petribox initial-setup   # checks and explains anything missing
```

For VM mounts: `sudo apt install -y virtiofsd` (containers work without it).

## Quick start

```bash
# one-time
pixi run petribox initial-setup

# create
pixi run petribox create lab --preset dev
pixi run petribox connect lab

# or install the command directly
pipx install -e .
petribox create lab --preset dev
```

First boot (cloud-init) takes 1–3 minutes. Subsequent boots are seconds.

## Commands

| Command | Description |
|---|---|
| `create <name> [opts]` / `create --tui` | Create a dish (VM by default, `--container` for lightweight) |
| `list` / `status <name>` | List dishes / show one in detail |
| `up <name>` / `down <name>` / `delete <name>` | Start / stop / delete |
| `connect <name> [cmd]` | Shell (or run a command) via `incus exec` |
| `connect <name> --gui` | Shell over `ssh -Y` with X11 forwarding for GUI apps (`ase gui`, interactive matplotlib) |
| `console <name>` | Attach to the instance console |
| `mount <name> <host> <vm>` / `umount <name> <vm>` | Share / unshare a host directory |
| `port-forward <name> <port> [--local-port P]` | Forward a dish port to the host |
| `port-forward-list` / `port-forward-stop <name> <port>` | Manage forwards |
| `install <name> --agent X` / `--mise-package P` | Install into a running dish |
| `export <name> [-o file]` / `import <file> [name]` | Backup / restore |
| `move <name> <remote[:name]> [--copy]` | Migrate to a remote Incus host |
| `remote-add <name> <url>` / `remote-list` | Manage remote Incus servers |
| `comms <name> [--protocol a2a\|mcp] [--expose] [--runtime CMD]` | Mark a dish comms-ready |
| `ssh-config` | Refresh `~/.ssh/petribox_config` with running dishes; adds `Include` to `~/.ssh/config` once |
| `initial-setup [-y]` | Check / set up Incus prerequisites |

### Create options

`--container`, `--ram MB`, `--cpus N`, `--disk GB`, `--user NAME` (default `petri`),
`--ssh-key PATH`, `--password`, `--image` (default `images:rockylinux/9/cloud`),
`--dotfiles SRC`, `--mount HOST:VM` (repeatable), `--config FILE`,
`--shell bash|zsh`, `--preset NAME`, `--agent NAME`.

## Presets

| Preset | RAM | CPUs | Disk | Extras |
|---|---|---|---|---|
| `minimal` | 2 GB | 1 | 15 GB | base packages only |
| `dev` | 4 GB | 2 | 25 GB | gcc, make, `node@24` via mise |
| `ai-researcher` | 8 GB | 4 | 40 GB | `python@3.12` via mise, jupyterlab, numpy, pandas, matplotlib, scikit-learn |
| `agentic` | 8 GB | 4 | 50 GB | docker, `python@3.12` + `node@24` via mise, langchain, langgraph, pydantic, httpx |

Base packages on every dish: vim, python3, git, curl, wget, tmux, mise.

Override any resource: `--ram 8192 --cpus 4 --disk 50`.

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
petribox create mybox --config my-config.yaml
```

## Portability

```bash
petribox down lab
petribox export lab -o lab.tar.gz
# copy lab.tar.gz to another machine
petribox import lab.tar.gz && petribox up lab

# or migrate live to a remote Incus host
petribox remote-add cloud https://incus.example.com:8443
petribox move lab cloud
```

## Agent communication (preview)

`petribox comms <name>` records a protocol and port in the instance metadata and optionally opens it. Dishes reach each other by Incus DNS name (`<name>.incus`). Full A2A/MCP protocol support is on the roadmap — see `docs/ROADMAP.md`.

## Development

```bash
pip install -e ".[test]"
pytest -m "not e2e"            # unit tests (mocked incus)
PETRIBOX_E2E=1 pytest -m e2e   # real Incus instances (opt-in)
```

See `docs/ARCHITECTURE.md` and `docs/E2E-CHECKLIST.md`.

## License

MIT

---

## Appendix: which agent should I use?

A quick guide for picking the right agent. Every agent below installs with `petribox create <name> --agent <key>`.

### At a glance

| Agent | Key | Language | Binary size | RAM footprint | Primary use |
|---|---|---|---|---|---|
| Hermes | `hermes` | Python + Node | Medium | ~150 MB | Autonomous task execution |
| OpenClaw | `openclaw` | Node | Medium | ~100 MB | Life automation via chat apps |
| NemoClaw | `nemoclaw` | Node (NVIDIA) | Large | ~200 MB + Docker | Secure OpenClaw with policy controls |
| NullClaw | `nullclaw` | Zig | **678 KB** | ~1 MB | Minimal edge/embedded AI |
| PicoClaw | `picoclaw` | Go | ~10 MB | ~10 MB | Edge + chat integrations + web UI |
| Loong | `loong` | Rust | Medium | ~30 MB | Building custom vertical agents |
| ZeroClaw | `zeroclaw` | Rust | Small | ~5 MB | Provider-agnostic personal assistant |
| Pi | `pi` | TypeScript | Medium | ~80 MB | Interactive terminal coding |

---

### Hermes
**Autonomous task execution** built by NousResearch. Given a goal, Hermes breaks it down, executes steps, and reports results. Closest to a "do this for me" agent — it acts on your behalf rather than waiting for turn-by-turn input.

**Use Hermes if:** you want to hand off a multi-step task and come back to a result.

---

### OpenClaw
**Life automation via chat.** Connects to WhatsApp, Telegram, and other messaging apps and handles email, calendar, flight check-ins, and similar daily tasks. It is not a coding agent — it is a personal-life automation layer.

**Use OpenClaw if:** you want an agent running in a dish that manages your inbox and calendar without you opening a laptop.

---

### NemoClaw (NVIDIA)
**OpenClaw with enterprise security.** Wraps OpenClaw with network policy enforcement (agents must request permission before making network calls), multi-provider inference routing, and an operator approval workflow. Adds Docker as a dependency and requires an NVIDIA API key.

**Use NemoClaw instead of OpenClaw if:** you are deploying in a shared or regulated environment and need to control what the agent is allowed to reach on the network.

**Skip NemoClaw if:** you are doing local personal use — the governance overhead is not worth it.

---

### NullClaw
**The smallest possible AI agent.** A 678 KB static Zig binary with zero runtime dependencies. Boots in under 8 ms, uses about 1 MB of RAM. No web UI, no chat integrations — just the agent binary.

**Use NullClaw if:** you are targeting genuinely constrained hardware, you want zero moving parts, or you philosophically prefer the smallest footprint possible.

**NullClaw vs PicoClaw:** NullClaw is smaller and has zero deps; PicoClaw trades some size for a web UI, 16 chat integrations, and multi-architecture pre-built binaries. Pick NullClaw for raw minimalism, PicoClaw for minimalism-with-UX.

---

### PicoClaw (Sipeed)
**Lightweight Go binary with a web UI and chat integrations.** ~10 MB, <1 second startup, runs on Raspberry Pi, Android, RISC-V. Supports 16+ messaging platforms (Telegram, Discord, Slack, WeChat, DingTalk, etc.) and 10+ LLM providers. Has native MCP support.

**Use PicoClaw if:** you want to deploy an agent on a Raspberry Pi or similar hardware and need it to respond via Telegram or another chat platform, not just the terminal.

**PicoClaw vs NullClaw:** PicoClaw is larger but ready to integrate with external services out of the box. NullClaw is a bare binary with no integrations.

---

### Loong
**A framework for building your own vertical agents.** Not a ready-made assistant — it is infrastructure. Comes with 42+ LLM/tool providers and 25+ channels (Slack, Lark, Discord, DingTalk) pre-wired. You configure which providers and channels you want, then write the agent logic on top.

**Use Loong if:** you want to build a custom agent that routes through specific providers and channels rather than running someone else's agent as-is. Think of it as the backbone, not the product.

**Skip Loong if:** you just want to install and run an agent without writing Rust.

---

### ZeroClaw
**Provider-agnostic personal assistant in Rust.** Positions itself as "99% less memory than OpenClaw" (≈5 MB RAM). Works with any OpenRouter-compatible provider — you supply the API key and the provider name.

**Use ZeroClaw if:** you want a low-memory personal assistant without committing to OpenAI or Anthropic specifically, and you are comfortable using a Rust-native binary.

**ZeroClaw vs NullClaw:** ZeroClaw is provider-agnostic and has a real CLI UX; NullClaw is even smaller but more opinionated about its interface.

---

### Pi (earendil-works)
**A minimal, extensible terminal coding agent.** Unlike Hermes (autonomous task runner) or OpenClaw (life automation), Pi is specifically a *coding* assistant that lives in your terminal. Its differentiator is that it imposes no workflow — you can write TypeScript plugins, custom prompts, and skills to shape exactly how it behaves. Supports 20+ LLM providers with a unified interface.

**Use Pi if:** you want an AI pair-programmer in the terminal that you can customise deeply, and you do not want it to silently make decisions about how to structure the interaction.

**Pi vs Hermes:** Hermes is autonomous (it acts and reports back); Pi is interactive (you stay in the loop). Pi is more like a smart terminal co-pilot. Hermes is more like delegating the task entirely.

**Pi vs Claude Code / Cursor:** Pi is provider-agnostic and fully open to extension. Claude Code and Cursor are polished products with opinionated UX. Pi is the right choice if you want to own the workflow.
