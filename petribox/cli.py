#!/usr/bin/env python3
"""petribox CLI - manage Incus-backed dishes for AI agents."""

import argparse
import sys
from pathlib import Path

from .commands import (
    cmd_comms,
    cmd_config,
    cmd_console,
    cmd_create,
    cmd_delete,
    cmd_down,
    cmd_export,
    cmd_import,
    cmd_initial_setup,
    cmd_install,
    cmd_list,
    cmd_mount,
    cmd_move,
    cmd_port_forward,
    cmd_port_forward_clean,
    cmd_port_forward_list,
    cmd_port_forward_stop,
    cmd_remote_add,
    cmd_remote_list,
    cmd_ssh,
    cmd_status,
    cmd_umount,
    cmd_up,
)
from .presets import PRESET_NAMES
from .tui import run_create_tui

AGENT_CHOICES = ["hermes", "openclaw", "zeroclaw"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="petribox",
        description="Manage isolated Incus dishes (VMs/containers) for AI agents",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose errors")

    sub = parser.add_subparsers(dest="command", help="Commands")

    # create
    p = sub.add_parser("create", help="Create a new dish")
    p.add_argument("name", nargs="?", help="Dish name (optional with --tui)")
    p.add_argument("--tui", action="store_true", help="Interactive creation")
    p.add_argument("--container", action="store_true",
                   help="Create a system container instead of a VM (faster, lighter)")
    p.add_argument("--ram", type=int, default=None, help="RAM in MB (default: preset or 4096)")
    p.add_argument("--cpus", type=int, default=None, help="CPU count (default: preset or 2)")
    p.add_argument("--disk", type=int, default=None, help="Disk in GB (default: preset or 20)")
    p.add_argument("--user", default="petri", help="Username (default: petri)")
    p.add_argument("--ssh-key", type=Path, help="SSH public key for optional SSH login")
    p.add_argument("--password", help="User password (optional)")
    p.add_argument("--image", help=f"Incus image (default: {''}images:rockylinux/9/cloud)")
    p.add_argument("--dotfiles", help="Dotfiles: git URL, local path, or preset name")
    p.add_argument("--mount", action="append", dest="mounts", metavar="HOST:VM",
                   help="Share a host directory (repeatable)")
    p.add_argument("--config", type=Path, help="YAML config (packages, mise, pip, ...)")
    p.add_argument("--shell", choices=["bash", "zsh"], default="bash", help="Login shell")
    p.add_argument("--preset", choices=PRESET_NAMES, help="Configuration preset")
    p.add_argument("--agent", choices=AGENT_CHOICES, help="Install an AI agent at creation")
    p.set_defaults(func=cmd_create)

    # list
    p = sub.add_parser("list", help="List all dishes")
    p.set_defaults(func=cmd_list)

    # up / down
    p = sub.add_parser("up", help="Start a dish")
    p.add_argument("name")
    p.set_defaults(func=cmd_up)
    p = sub.add_parser("down", help="Stop a dish")
    p.add_argument("name")
    p.set_defaults(func=cmd_down)

    # delete
    p = sub.add_parser("delete", help="Delete a dish")
    p.add_argument("name")
    p.add_argument("--force", "-f", action="store_true", help="No confirmation")
    p.set_defaults(func=cmd_delete)

    # status
    p = sub.add_parser("status", help="Show dish status")
    p.add_argument("name")
    p.set_defaults(func=cmd_status)

    # console / connect
    p = sub.add_parser("console", help="Attach to the dish console")
    p.add_argument("name")
    p.set_defaults(func=cmd_console)
    p = sub.add_parser("connect", help="Open a shell in the dish (incus exec)")
    p.add_argument("name")
    p.add_argument("ssh_command", nargs="*", help="Command to run (optional)")
    p.set_defaults(func=cmd_ssh)

    # mount / umount
    p = sub.add_parser("mount", help="Share a host directory into a dish")
    p.add_argument("name")
    p.add_argument("host_path")
    p.add_argument("vm_path")
    p.set_defaults(func=cmd_mount)
    p = sub.add_parser("umount", help="Remove a shared directory")
    p.add_argument("name")
    p.add_argument("vm_path")
    p.set_defaults(func=cmd_umount)

    # config
    p = sub.add_parser("config", help="View presets or a dish's settings")
    p.add_argument("action", choices=["list", "show", "edit"])
    p.add_argument("name", nargs="?")
    p.set_defaults(func=cmd_config)

    # port-forward
    p = sub.add_parser("port-forward", help="Forward a dish port to localhost")
    p.add_argument("name")
    p.add_argument("port", type=int)
    p.add_argument("--local-port", type=int, help="Local port (default: same)")
    p.add_argument("--background", "-b", action="store_true",
                   help="(Accepted for compatibility; proxy devices are always persistent)")
    p.set_defaults(func=cmd_port_forward)
    p = sub.add_parser("port-forward-list", help="List active port forwards")
    p.set_defaults(func=cmd_port_forward_list)
    p = sub.add_parser("port-forward-stop", help="Stop a port forward")
    p.add_argument("name")
    p.add_argument("port", type=int)
    p.set_defaults(func=cmd_port_forward_stop)
    p = sub.add_parser("port-forward-clean", help="(No-op; forwards are Incus-managed)")
    p.set_defaults(func=cmd_port_forward_clean)

    # install
    p = sub.add_parser("install", help="Install agents/packages into a running dish")
    p.add_argument("name")
    p.add_argument("--agent", choices=AGENT_CHOICES)
    p.add_argument("--mise-package", action="append", dest="mise_packages", metavar="PKG")
    p.set_defaults(func=cmd_install)

    # portability
    p = sub.add_parser("export", help="Export a dish to a portable tarball")
    p.add_argument("name")
    p.add_argument("--output", "-o", help="Output file (default: <name>.tar.gz)")
    p.set_defaults(func=cmd_export)
    p = sub.add_parser("import", help="Import a dish from a tarball")
    p.add_argument("file")
    p.add_argument("name", nargs="?", help="New dish name (optional)")
    p.set_defaults(func=cmd_import)
    p = sub.add_parser("move", help="Migrate a dish to a remote Incus server")
    p.add_argument("name")
    p.add_argument("dest", help="Remote, e.g. 'cloud' or 'cloud:newname'")
    p.add_argument("--copy", action="store_true", help="Copy instead of move (keep local)")
    p.set_defaults(func=cmd_move)
    p = sub.add_parser("remote-add", help="Register a remote Incus server")
    p.add_argument("name")
    p.add_argument("url")
    p.set_defaults(func=cmd_remote_add)
    p = sub.add_parser("remote-list", help="List configured remotes")
    p.set_defaults(func=cmd_remote_list)

    # comms
    p = sub.add_parser("comms", help="Mark a dish comms-ready (A2A/MCP)")
    p.add_argument("name")
    p.add_argument("--protocol", choices=["a2a", "mcp"], default="a2a")
    p.add_argument("--port", type=int, help="Comms port (default: 41241)")
    p.add_argument("--expose", action="store_true", help="Expose the port to the host")
    p.add_argument("--runtime", help="Shell command to install the comms runtime in the dish")
    p.set_defaults(func=cmd_comms)

    # initial-setup
    p = sub.add_parser("initial-setup", help="Install/initialise Incus prerequisites")
    p.add_argument("--auto", "-y", action="store_true", help="Accept all defaults")
    p.set_defaults(func=cmd_initial_setup)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "create" and args.tui:
        run_create_tui()
        sys.exit(0)

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nOperation cancelled.")
        sys.exit(130)
    except Exception as exc:  # noqa: BLE001
        if getattr(args, "verbose", False):
            import traceback
            traceback.print_exc()
        else:
            print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
