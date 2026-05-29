# Petribox Architecture & Overhaul Analysis

> Canonical design record for the Incus-based rewrite. Written so any agent can
> pick up the work cold. Companion: [ROADMAP.md](ROADMAP.md).

## What petribox is

A CLI that spins up isolated, **opinionated**, pre-configured Linux "dishes"
(VMs, or lightweight containers) for growing, deploying, and evolving AI agents.
The point is not "every Linux option at your disposal" — it's a *working* env
that's ready to install/run agents immediately. Dishes are meant to be **bred
locally and then carried/migrated to the cloud** by moving the instance.

## Why this overhaul exists

The repo was caught mid-rebrand from `sandbox` → `petribox`. The committed
`sandbox/` package was copied into an untracked, half-converted `petribox/` that
**does not run**, on top of pre-existing architectural problems. Rather than
patch the libvirt design, we are **switching the backend to Incus**, which turns
most of the broken/hand-rolled functionality into native one-liners and directly
serves the local→cloud portability and multi-host (scattered agents) vision.

---

## Findings inventory (state at start of overhaul)

Line refs are to the untracked `petribox/` copy unless noted.

### Blocking bugs (tool did not run)
1. **NameError epidemic** — `commands.py` renamed the DB layer to `Dish`/`DishDB`
   and assigns `dish = db.get_dish(...)`, but function bodies still reference an
   undefined `sandbox` (~100 sites): `cmd_create` (`:137` `db.create_dish(sandbox)`,
   `:138`, `:196`), `cmd_up` (`:267`), `cmd_down` (`:299`), `cmd_delete` (`:323`),
   `cmd_status` (`:375`), `cmd_console` (`:422`), `cmd_ssh` (`:444`), `cmd_mount`
   (`:490`/`:524`), `cmd_umount` (`:533`), `cmd_config` (`:573`),
   `cmd_port_forward` (`:714`), `cmd_install` (`:1282`). `py_compile` passes
   because names resolve only at call time.
2. **Port-forward KeyError** — `cmd_port_forward_list` (`:700`) /
   `cmd_port_forward_clean` (`:814`) read `tunnel["petribox_name"]`, but
   `tunnel_manager.create_tunnel` stores `dish_name`.
3. **Wrong package wired up** — `pixi.toml` task `sandbox = "python -m sandbox"`
   runs the OLD committed package; `pixi run sandbox` never executes `petribox/`.
   `petribox.sh` relies on CWD; `run_sandbox.sh` hardcodes dead path
   `/home/abbasi-perezd/vmisos`.

### Features that don't do what they claim
4. **Mounts are fake.** `cmd_create` passes `args.mounts` to `create_seed_iso`,
   which ignores the parameter — no device is ever added; only DB rows are
   written. `mount_ops.setup_9p_mount`/`remove_9p_mount`/`setup_virtiofs` only
   print manual instructions and are never called. `cmd_mount` errors for `9p`;
   for sshfs it calls `ssh_ops.ssh_mount`, which also only prints instructions,
   yet `cmd_mount` then prints "✓ Mount created" (false success).
5. **Dead code** — `config_loader.apply_config_packages` and all of
   `mount_ops.py` are imported but unused (packages are baked into cloud-init).

### Architecture / correctness smells
6. **Per-VM base copy** — `libvirt_ops.create_vm` (`:211-224`) `sudo cp`s the full
   ~650MB base image per VM, defeating qcow2 backing-file sharing.
7. **Excess/inconsistent sudo** — `sudo cp/qemu-img/chmod/virt-install/virsh
   console` mixed with non-sudo `virsh`. Self-inflicted; not required on
   `qemu:///system` for a `libvirt`-group member using a storage pool.
8. **Two sources of truth** — every command re-reads libvirt status and patches
   the SQLite row; DB and hypervisor drift.
9. **Error opacity** — `subprocess.run(check=True, capture_output=True)` hides
   stderr; `cli.py` then prints a bare `Error: …returned non-zero exit status N`.
10. **cloud-init password** — `create_seed_iso` writes plaintext `passwd:`; needs
    a hashed value / `chpasswd`. Insecure / non-functional.
11. **Prereq lists disagree** across `check_prereqs`, `cmd_initial_setup`, README.

### Branding / UX inconsistencies
12. Default user differs: `--user` default `petri`, README `sandbox`,
    `user-data.yml` `test`, DB default `petri`.
13. Output strings say `sandbox ssh <name>`, but the subcommand is `connect`
    (→ `cmd_ssh`); there is no `ssh` subcommand.
14. `tui.py`: per-mount `mount_type` collected then discarded (`args.mount_type`
    hardcoded `"9p"`, `:216`); agent never selectable (`args.agent = None`);
    sets unused `args.template`/`args.save_template`.
15. Three diverging preset definitions: `commands.get_preset_config`,
    `tui.PRESETS`, README table.
16. Clutter: untracked `petribox/` (the real code), duplicate `Rocky9.qcow2`,
    stray `petri list.yaml`, empty `shared_openclaw/`, `.trash/`, committed
    `__pycache__/`, reference-only `user-data.yml`.

---

## Locked decisions

- **Backend:** Incus (drop libvirt entirely). Sudo-less via `incus` group.
- **Instance type:** VMs by default; `--container` opt-in (system containers:
  instant boot, low RAM, shared kernel — for when isolation/portability matter less).
- **State:** No SQLite DB. Incus is the single source of truth; petribox metadata
  lives in `user.petribox.*` instance config keys.
- **Images:** Default `images:rockylinux/9` (cached by Incus); `--image` overrides.
- **In scope this phase:** working sudo-less rebranded tool; native virtiofs
  mounts; native proxy port-forwarding; `export`/`import`/`move`+`remote`
  portability; A2A/MCP comms-readiness (see ROADMAP).
- **Tests:** unit (mocked subprocess) + opt-in real e2e (gated, not CI) + manual checklist.

## Why Incus removes the breakage

| Old (broken/hacky) | New (Incus-native) |
|---|---|
| `create_vm` per-VM `sudo cp` base | `incus launch images:rockylinux/9 <n> --vm`; Incus manages image cache + storage pool |
| `mount_ops` / 9p / sshfs instructions | `incus config device add <n> <tag> disk source=H path=V` (virtiofs auto) |
| `tunnel_manager` + SSH tunnels + PID files | `incus config device add <n> pf proxy listen=tcp:127.0.0.1:L connect=tcp:127.0.0.1:R` |
| `ssh_ops` setup/copy/run-script | `incus exec`, `incus file push` |
| `database.py` + status reconciliation | `incus list/info` + `user.petribox.*` keys |
| seed-ISO via `cloud-localds` | `incus config set <n> cloud-init.user-data=…` |
| manual image download + checksum | `images:` remote (cached); `--image` for custom |
| portability: none | `incus export` / `incus copy <local>:<n> <remote>:<n>` / `incus move` |

`connect` uses `incus exec <n>` (no SSH needed); SSH stays optional (sshd + key
still provisioned via cloud-init for users who want it).

---

## Target layout

```
petribox/
├── __init__.py            # version, package docstring
├── __main__.py            # `python -m petribox` → cli.main()
├── cli.py                 # argparse surface (mostly preserved)
├── commands/              # split the 1368-line commands.py by concern
│   ├── lifecycle.py       # create, list, status, up, down, delete
│   ├── access.py          # connect (exec/console), exec, file push/pull
│   ├── mounts.py          # add/remove disk-device (virtiofs) shares
│   ├── forward.py         # proxy-device port forwarding
│   ├── install.py         # install agents / mise pkgs into running dish
│   ├── portability.py     # export / import / move (remote)
│   ├── comms.py           # A2A/MCP readiness wiring
│   └── setup.py           # initial-setup (install incus, group, init)
├── incus.py               # typed wrapper over `incus` CLI (replaces
│                          #   libvirt_ops + ssh_ops + tunnel_manager + mount_ops)
├── cloudinit.py           # build_user_data() ported from create_seed_iso
├── presets.py             # single PRESETS source (merges the 3 copies)
├── agents.py              # AGENTS dict (kept)
├── dotfiles.py            # presets kept; apply via incus file push/exec
├── config_loader.py       # load_config kept; apply_config_packages removed
├── meta.py                # read/write user.petribox.* (replaces database.py)
└── tui.py                 # interactive create, rewired + bugfixes

pyproject.toml             # PEP 621 + `petribox` console_script entrypoint
tests/                     # pytest: unit + gated e2e (-m e2e, PETRIBOX_E2E=1)
docs/ARCHITECTURE.md       # this file
docs/ROADMAP.md            # A2A/MCP comms + shared knowledge
docs/E2E-CHECKLIST.md      # manual end-to-end verification
```

### Removed
`sandbox/`, `sandbox.sh`, `run_sandbox.sh`, `petri list.yaml`, `Rocky9.qcow2`,
`shared_openclaw/`, `user-data.yml`, and within petribox: `libvirt_ops.py`,
`ssh_ops.py`, `tunnel_manager.py`, `mount_ops.py`, `database.py`.

### Reused (don't rewrite)
`agents.AGENTS`; `dotfiles.DOTFILE_PRESETS` + script gen (swap ssh→incus);
`config_loader.load_config`; `tui`/`cli` shape; `create_seed_iso`'s user-data
generation → `cloudinit.build_user_data`.

## Verification

- **Unit:** `pixi run pytest -m "not e2e"` — cloud-init/meta/preset/command-mapping, no Incus needed.
- **e2e (`PETRIBOX_E2E=1 pytest -m e2e`, or manual checklist):** initial-setup →
  no sudo prompts after; `create lab --preset dev` (VM) + `create fast
  --container`; `connect` via exec; `mount lab ~/data /data` (real virtiofs);
  `port-forward lab 8888` (proxy device, survives host restart); `install lab
  --agent hermes`; `export`→`delete`→`import` round-trip; comms-readiness name
  resolution; `delete` leaves no devices or `~/.petribox` residue.
- **Regression:** `grep sandbox` returns only historical refs; all user-facing
  strings say `petribox`; default user consistent.
