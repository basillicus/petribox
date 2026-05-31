# Petribox Architecture

Design record for the Incus-backed implementation. Companion: [ROADMAP.md](ROADMAP.md).

## What petribox is

A CLI that spins up isolated, **opinionated**, pre-configured Linux "dishes"
(Incus VMs, or lightweight system containers) for growing, deploying, and
evolving AI agents. The goal is a *working* environment that's ready to install
and run agents immediately — not every Linux knob. Dishes are designed to be
**bred locally and then carried/migrated to the cloud** by moving the instance.

## Design decisions

- **Backend: Incus.** Sudo-less for the user (membership in the `incus` /
  `incus-admin` group), with managed networking, virtiofs mounts, proxy-device
  port forwarding, `exec`/`file push`, an image server, and `export`/`copy`/`move`.
- **Instance type:** VMs by default; `--container` for system containers
  (instant boot, low RAM, shared kernel) when isolation/portability matter less.
- **State:** No separate database. Incus is the single source of truth;
  petribox metadata lives in `user.petribox.*` instance config keys.
- **Image:** `images:rockylinux/9/cloud` by default (the cloud variant ships
  cloud-init wired to the Incus NoCloud datasource); `--image` overrides.
- **Access:** `connect` uses `incus exec`, so no SSH or IP is required. An SSH
  key is still provisioned (when available) for users who want SSH.

## Module layout

```
petribox/
├── __init__.py            # version, package docstring
├── __main__.py            # `python -m petribox` → cli.main()
├── cli.py                 # argparse surface
├── incus.py               # typed wrapper over the `incus` CLI (IncusError on failure)
├── meta.py                # read/write user.petribox.* metadata
├── cloudinit.py           # build_user_data(): cloud-config generation
├── presets.py             # the four presets (resources + package config)
├── agents.py              # AGENTS catalogue
├── dotfiles.py            # dotfile presets + apply via incus exec/file push
├── config_loader.py       # load YAML configs
└── commands/
    ├── _common.py         # console, error/exit, resource resolution, device naming, wait
    ├── lifecycle.py       # create, list, status, up, down, delete, config
    ├── access.py          # connect (incus exec), console
    ├── mounts.py          # share host dirs via disk devices (virtiofs)
    ├── forward.py         # port forwarding via proxy devices
    ├── install.py         # install agents / mise packages into a running dish
    ├── portability.py     # export / import / move / remote-*
    ├── comms.py           # A2A/MCP comms-readiness
    └── setup.py           # initial-setup (install/init Incus, checks)

pyproject.toml             # packaging + `petribox` console_script
tests/                     # pytest: unit + gated e2e (-m e2e, PETRIBOX_E2E=1)
docs/                      # ARCHITECTURE.md, ROADMAP.md, E2E-CHECKLIST.md
```

## How it works

**Create.** `lifecycle.cmd_create` resolves resources (explicit flag > preset >
default), folds the preset and any `--config` YAML into a cloud-config document
(`cloudinit.build_user_data`), and runs `incus init` with `limits.cpu`,
`limits.memory`, `cloud-init.user-data`, a root-disk size override, and the
`user.petribox.*` metadata. `--mount` directories are attached as disk devices
before `incus start`, so they're present on first boot. cloud-init then installs
packages, mise, mise/pip packages, and any agent. Dotfiles are applied
afterwards over `incus exec`/`incus file push`.

**Mounts.** A disk device (`incus config device add <dish> <dev> disk
source=<host> path=<guest>`); for VMs this is virtiofs, mounted by the Incus
agent at the target path. Hot-pluggable, so no restart is needed.

**Port forwarding.** A proxy device (`listen=tcp:127.0.0.1:<local>
connect=tcp:127.0.0.1:<remote>`), persistent across host reboots.

**Connect / install.** `incus exec` for interactive shells and for running setup
commands; `incus file push` for file transfer.

**Portability.** `incus export` produces a self-contained tarball (no
backing-file chain); `incus import` restores it. `incus copy`/`move` to a
registered remote migrates a dish to another host or a cloud Incus server.

**Comms-readiness.** Records a protocol + reserved port in `user.petribox.comms_*`
and optionally exposes it via a proxy device. Dishes reach each other by Incus
DNS name (`<name>.incus`). Full A2A/MCP support is in ROADMAP.md.

## Testing

- `pytest -m "not e2e"` — unit tests with `subprocess`/`incus` mocked: cloud-init
  generation, preset merge, metadata round-trip, the incus wrapper (error
  propagation, IPv4/state parsing, command building), and command dispatch.
- `PETRIBOX_E2E=1 pytest -m e2e` — opt-in tests that create and destroy a real
  Incus instance (excluded from CI). See `E2E-CHECKLIST.md` for the manual walkthrough.
