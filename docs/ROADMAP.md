# Petribox Roadmap

Vision beyond the initial Incus overhaul. See [ARCHITECTURE.md](ARCHITECTURE.md)
for the current design and locked decisions.

## Vision

Breed AI agents in isolated local "dishes," then **carry or migrate them
anywhere** — another machine or the cloud — by moving the instance. Run many
**specialised agents** scattered across local and cloud hosts that can
**communicate**, backed eventually by a shared **source of truth** every agent
reads from and contributes to.

---

## In scope for the current overhaul (built now)

### Portability (`commands/portability.py`)
- `export <name> [--output FILE] [--format incus|qcow2|raw]` — `incus export` for
  a full self-contained backup; for cloud targets, extract the disk and
  `qemu-img convert` to qcow2/raw (document AWS VM Import, GCP raw `.tar.gz`,
  Azure fixed VHD conversions). Self-contained by construction (no backing chain).
- `import <file>` / `move <name> <remote>:` — `incus import` / `incus copy`.
- `remote add/list` — pass-through to `incus remote` so one CLI drives local +
  cloud Incus hosts.

### Comms-readiness (`commands/comms.py`) — readiness only, not the full protocol
- **Discovery convention:** dishes are reachable by Incus DNS name (`<name>.incus`)
  on `incusbr0`; a reserved comms port is recorded in `user.petribox.comms_port`.
- `--comms a2a|mcp` (and/or a preset) optionally installs a minimal A2A/MCP
  runtime via cloud-init and opens the port via a proxy device.
- Document the agent-card / endpoint convention.

---

## Deferred (design now, build later)

### Full agent-to-agent communication
Standards landscape (use these, don't invent):
- **A2A (Agent2Agent)** — best fit for agent↔agent: Agent Cards advertise
  capabilities + endpoint; task delegation over JSON-RPC/HTTP+SSE. Originated at
  Google, now under the Linux Foundation.
- **MCP (Model Context Protocol)** — Anthropic; agent↔tools/resources and the
  natural transport for the shared knowledge store; increasingly used for agent
  composition.
- **ACP (Agent Communication Protocol)** — IBM/BeeAI; adjacent to A2A.
- **FIPA-ACL / KQML** — historical academic agent languages (background only).
- **NIST** — provides the *AI Risk Management Framework* (governance), **not** a
  wire protocol. Don't expect a NIST messaging standard.

Deferred work: implement A2A agent cards + task delegation between dishes;
optional MCP server registration; cross-host discovery via `incus remote`.

### Centralised shared source of truth
A shared **MCP knowledge/memory server** (backed by a vector store such as
Qdrant/Chroma, or a git repo for auditability) running in its own dish or in the
cloud, that every agent reads from and writes to. Petribox exposes a stable
endpoint (well-known dish name/IP or reserved port) all dishes can reach. Build
after comms lands.

### Other candidate features
- Snapshots (`incus snapshot`) and rollback.
- Reusable templates/profiles mapped to Incus profiles.
- Multi-distro images beyond Rocky.
