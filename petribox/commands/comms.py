"""Agent comms-readiness.

Sets up the convention that lets scattered agents talk; the full A2A/MCP
protocol implementation is roadmap (see docs/ROADMAP.md). Concretely this:

- records the protocol + reserved comms port in user.petribox.comms_*,
- optionally exposes the port to the host via a proxy device (--expose),
- optionally runs a user-supplied runtime install command in the dish.

Discovery convention: every dish on incusbr0 is reachable from peer dishes by
its Incus DNS name `<name>.incus` on the recorded comms port. Use A2A for
agent<->agent and MCP for agent<->tools/knowledge.
"""

from __future__ import annotations

from .. import incus, meta
from ._common import console, get_instance_or_exit, proxy_device_name, require_running

DEFAULT_COMMS_PORT = 41241  # petribox convention for the agent comms endpoint


def cmd_comms(args):
    get_instance_or_exit(args.name)
    port = args.port or DEFAULT_COMMS_PORT
    protocol = args.protocol

    meta.set_meta(args.name, comms_protocol=protocol, comms_port=str(port))
    console.print(f"[green]✓ {args.name} marked comms-ready[/green] ({protocol} on port {port})")
    console.print(f"[dim]Peers reach it at: {args.name}.incus:{port}[/dim]")

    if args.runtime:
        require_running(args.name)
        console.print(f"[dim]Installing runtime: {args.runtime}[/dim]")
        proc = incus.exec_capture(args.name, ["sh", "-c", args.runtime])
        if proc.returncode != 0:
            console.print(f"[red]Runtime install failed: {(proc.stderr or '').strip()[:400]}[/red]")
            raise SystemExit(1)
        console.print("[green]✓ Runtime installed[/green]")

    if args.expose:
        require_running(args.name)
        device = proxy_device_name(port)
        if device not in incus.device_show(args.name):
            incus.device_add(
                args.name, device, "proxy",
                listen=f"tcp:127.0.0.1:{port}",
                connect=f"tcp:127.0.0.1:{port}",
            )
        console.print(f"[green]✓ Exposed to host at localhost:{port}[/green]")
