#!/usr/bin/env python3
"""
Sandbox CLI - Main entry point
"""

import argparse
import sys
from pathlib import Path

from .commands import (
    cmd_create,
    cmd_list,
    cmd_up,
    cmd_down,
    cmd_delete,
    cmd_ssh,
    cmd_mount,
    cmd_umount,
    cmd_config,
    cmd_status,
    cmd_console,
    cmd_port_forward,
    cmd_port_forward_stop,
    cmd_port_forward_clean,
    cmd_port_forward_list,
    cmd_initial_setup,
)
from .tui import run_create_tui


def main():
    parser = argparse.ArgumentParser(
        prog="sandbox",
        description="Manage isolated Rocky Linux sandboxes for AI experiments",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Create command
    create_parser = subparsers.add_parser(
        "create",
        help="Create a new sandbox VM",
        description="Create a new sandbox virtual machine",
    )
    create_parser.add_argument(
        "name",
        nargs="?",
        help="Name of the sandbox (optional if using TUI)",
    )
    create_parser.add_argument(
        "--tui",
        action="store_true",
        help="Use interactive TUI for creation",
    )
    create_parser.add_argument(
        "--ram",
        type=int,
        default=4096,
        help="RAM in MB (default: 4096)",
    )
    create_parser.add_argument(
        "--cpus",
        type=int,
        default=2,
        help="Number of CPUs (default: 2)",
    )
    create_parser.add_argument(
        "--disk",
        type=int,
        default=20,
        help="Disk size in GB (default: 20)",
    )
    create_parser.add_argument(
        "--user",
        default="sandbox",
        help="Username (default: sandbox)",
    )
    create_parser.add_argument(
        "--ssh-key",
        type=Path,
        help="SSH public key file (default: ~/.ssh/id_ed25519.pub or ~/.ssh/id_rsa.pub)",
    )
    create_parser.add_argument(
        "--password",
        type=str,
        help="User password (optional, for console login)",
    )
    create_parser.add_argument(
        "--network",
        default="default",
        help="Libvirt network (default: default)",
    )
    create_parser.add_argument(
        "--image",
        type=Path,
        help="Base image path (default: Rocky-9-GenericCloud-Base.latest.x86_64.qcow2)",
    )
    create_parser.add_argument(
        "--dotfiles",
        type=str,
        help="Dotfiles source: git URL, local path, or preset name",
    )
    create_parser.add_argument(
        "--mount",
        action="append",
        dest="mounts",
        metavar="HOST_PATH:VM_PATH",
        help="Mount host directory into VM (can be specified multiple times)",
    )
    create_parser.add_argument(
        "--mount-type",
        choices=["9p", "sshfs"],
        default="9p",
        help="Mount type for data sharing (default: 9p)",
    )
    create_parser.add_argument(
        "--config",
        type=Path,
        help="YAML config file with packages, tools, and settings",
    )
    create_parser.add_argument(
        "--shell",
        choices=["bash", "zsh"],
        default="bash",
        help="Shell to configure (default: bash)",
    )
    create_parser.add_argument(
        "--preset",
        type=str,
        choices=["minimal", "dev", "ai-researcher", "agentic"],
        help="Use a predefined configuration preset",
    )
    create_parser.set_defaults(func=cmd_create)

    # List command
    list_parser = subparsers.add_parser(
        "list",
        help="List all sandboxes",
        description="List all sandbox VMs (running and stopped)",
    )
    list_parser.add_argument(
        "--all",
        action="store_true",
        help="Show all VMs including destroyed ones (from database)",
    )
    list_parser.set_defaults(func=cmd_list)

    # Up command
    up_parser = subparsers.add_parser(
        "up",
        help="Start a sandbox",
        description="Start a stopped sandbox VM",
    )
    up_parser.add_argument(
        "name",
        help="Name of the sandbox to start",
    )
    up_parser.set_defaults(func=cmd_up)

    # Down command
    down_parser = subparsers.add_parser(
        "down",
        help="Stop a sandbox",
        description="Stop a running sandbox VM",
    )
    down_parser.add_argument(
        "name",
        help="Name of the sandbox to stop",
    )
    down_parser.set_defaults(func=cmd_down)

    # Delete command
    delete_parser = subparsers.add_parser(
        "delete",
        help="Delete a sandbox",
        description="Delete a sandbox VM and its resources",
    )
    delete_parser.add_argument(
        "name",
        help="Name of the sandbox to delete",
    )
    delete_parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Force deletion without confirmation",
    )
    delete_parser.set_defaults(func=cmd_delete)

    # Status command
    status_parser = subparsers.add_parser(
        "status",
        help="Show detailed sandbox status",
        description="Show detailed status of a sandbox VM",
    )
    status_parser.add_argument(
        "name",
        help="Name of the sandbox",
    )
    status_parser.set_defaults(func=cmd_status)

    # Console command
    console_parser = subparsers.add_parser(
        "console",
        help="Connect to VM serial console",
        description="Connect to the VM's serial console (like virsh console)",
    )
    console_parser.add_argument(
        "name",
        help="Name of the sandbox",
    )
    console_parser.set_defaults(func=cmd_console)

    # Connect command (SSH wrapper)
    connect_parser = subparsers.add_parser(
        "connect",
        help="SSH into a sandbox (convenience wrapper)",
        description="Connect to a sandbox via SSH (wrapper around standard ssh)",
    )
    connect_parser.add_argument(
        "name",
        help="Name of the sandbox to connect to",
    )
    connect_parser.add_argument(
        "ssh_command",
        nargs="*",
        help="Command to execute (optional)",
    )
    connect_parser.set_defaults(func=cmd_ssh)

    # Mount command
    mount_parser = subparsers.add_parser(
        "mount",
        help="Mount host directory in sandbox",
        description="Mount a host directory into a running sandbox",
    )
    mount_parser.add_argument(
        "name",
        help="Name of the sandbox",
    )
    mount_parser.add_argument(
        "host_path",
        type=Path,
        help="Path on host to mount",
    )
    mount_parser.add_argument(
        "vm_path",
        help="Mount point inside VM",
    )
    mount_parser.add_argument(
        "--type",
        choices=["9p", "sshfs"],
        default="sshfs",
        help="Mount type (default: sshfs for runtime mounting)",
    )
    mount_parser.set_defaults(func=cmd_mount)

    # Umount command
    umount_parser = subparsers.add_parser(
        "umount",
        help="Unmount directory from sandbox",
        description="Unmount a directory from a sandbox",
    )
    umount_parser.add_argument(
        "name",
        help="Name of the sandbox",
    )
    umount_parser.add_argument(
        "vm_path",
        help="Mount point inside VM to unmount",
    )
    umount_parser.set_defaults(func=cmd_umount)

    # Config command
    config_parser = subparsers.add_parser(
        "config",
        help="Manage sandbox configurations",
        description="View or edit sandbox configurations",
    )
    config_parser.add_argument(
        "action",
        choices=["list", "show", "edit"],
        help="Action to perform",
    )
    config_parser.add_argument(
        "name",
        nargs="?",
        help="Sandbox name (for show/edit)",
    )
    config_parser.set_defaults(func=cmd_config)

    # Port-forward command
    portforward_parser = subparsers.add_parser(
        "port-forward",
        help="Forward a VM port to localhost",
        description="Forward a port from the sandbox VM to localhost",
    )
    portforward_parser.add_argument(
        "name",
        help="Name of the sandbox",
    )
    portforward_parser.add_argument(
        "port",
        type=int,
        help="Port to forward",
    )
    portforward_parser.add_argument(
        "--local-port",
        type=int,
        help="Local port to use (default: same as remote port)",
    )
    portforward_parser.add_argument(
        "--background",
        "-b",
        action="store_true",
        help="Run tunnel in background",
    )
    portforward_parser.set_defaults(func=cmd_port_forward)

    # Port-forward list command
    portforward_list_parser = subparsers.add_parser(
        "port-forward-list",
        help="List active port-forward tunnels",
        description="List all active port-forward tunnels",
    )
    portforward_list_parser.set_defaults(func=cmd_port_forward_list)

    # Port-forward stop command
    portforward_stop_parser = subparsers.add_parser(
        "port-forward-stop",
        help="Stop a port-forward tunnel",
        description="Stop a port-forward tunnel by sandbox name and port",
    )
    portforward_stop_parser.add_argument(
        "name",
        help="Name of the sandbox",
    )
    portforward_stop_parser.add_argument(
        "port",
        type=int,
        help="Port to stop forwarding",
    )
    portforward_stop_parser.set_defaults(func=cmd_port_forward_stop)

    # Port-forward clean command
    portforward_clean_parser = subparsers.add_parser(
        "port-forward-clean",
        help="Clean up stale port-forward tunnels",
        description="Remove port-forward tunnels for processes that are no longer running",
    )
    portforward_clean_parser.set_defaults(func=cmd_port_forward_clean)

    # Initial-setup command
    setup_parser = subparsers.add_parser(
        "initial-setup",
        help="Set up sandbox prerequisites (libvirt, SSH key, Rocky image)",
        description="Automated initial setup: configures libvirt, creates SSH key, and downloads Rocky Linux image",
    )
    setup_parser.add_argument(
        "--rocky-version",
        choices=["9", "10"],
        default="9",
        help="Rocky Linux version to download (default: 9)",
    )
    setup_parser.add_argument(
        "--image-path",
        type=Path,
        help="Where to store the downloaded image, or path to existing image (default: project directory)",
    )
    setup_parser.add_argument(
        "--ssh-key-path",
        type=Path,
        help="Path for sandbox SSH key (default: ~/.ssh/sandbox_id_ed25519)",
    )
    setup_parser.add_argument(
        "--no-alias",
        action="store_true",
        help="Don't suggest adding the sandbox alias to shell config",
    )
    setup_parser.add_argument(
        "--auto",
        "-y",
        action="store_true",
        help="Non-interactive mode: accept all defaults without prompting",
    )
    setup_parser.set_defaults(func=cmd_initial_setup)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Handle TUI for create
    if args.command == "create" and args.tui:
        run_create_tui()
        sys.exit(0)

    if hasattr(args, "func"):
        try:
            args.func(args)
        except KeyboardInterrupt:
            print("\nOperation cancelled.")
            sys.exit(130)
        except Exception as e:
            if getattr(args, "verbose", False):
                import traceback
                traceback.print_exc()
            else:
                print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
