"""
Interactive TUI for Sandbox Creation

Uses simple terminal prompts for interactive configuration.
"""

import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


# Preset configurations
PRESETS = {
    "minimal": {
        "description": "Basic tools (vim, python3, git, curl)",
        "ram": 2048,
        "cpus": 1,
        "disk": 15,
        "packages": ["vim", "python3", "git", "curl"],
    },
    "dev": {
        "description": "Development environment (Node.js, npm, gcc, make)",
        "ram": 4096,
        "cpus": 2,
        "disk": 25,
        "packages": ["vim", "python3", "git", "curl", "wget", "gcc", "make", "nodejs", "npm"],
    },
    "ai-researcher": {
        "description": "AI/ML research (Jupyter, numpy, pandas, sklearn)",
        "ram": 8192,
        "cpus": 4,
        "disk": 40,
        "packages": ["vim", "python3", "python3-pip", "git", "curl", "wget", "gcc", "tmux", "htop"],
        "pip_packages": ["jupyterlab", "numpy", "pandas", "scikit-learn", "matplotlib"],
    },
    "agentic": {
        "description": "Agentic AI development (LangChain, Docker, tools)",
        "ram": 8192,
        "cpus": 4,
        "disk": 50,
        "packages": ["vim", "python3", "python3-pip", "git", "curl", "wget", "tmux", "docker"],
        "pip_packages": ["jupyterlab", "langchain", "langgraph", "pydantic", "httpx"],
    },
}

# Dotfile presets
DOTFILE_PRESETS = ["minimal", "dev", "ai-researcher"]


def run_create_tui():
    """Run interactive TUI for sandbox creation"""
    console.print()
    console.print(Panel.fit(
        "[bold green]Sandbox Creator[/bold green]\n"
        "[dim]Interactive VM configuration[/dim]",
        border_style="green",
    ))
    console.print()

    # Get sandbox name
    console.print("[cyan]Step 1: Basic Configuration[/cyan]\n")
    
    name = Prompt.ask(
        "Sandbox name",
        default="sandbox",
    )

    # Select preset
    console.print("\n[dim]Select a preset configuration:[/dim]")
    preset_table = Table(show_header=True, header_style="bold")
    preset_table.add_column("Preset", style="cyan")
    preset_table.add_column("Description")
    preset_table.add_column("RAM", justify="right")
    preset_table.add_column("CPUs", justify="right")
    preset_table.add_column("Disk", justify="right")

    for preset_name, preset in PRESETS.items():
        preset_table.add_row(
            preset_name,
            preset["description"],
            f"{preset['ram']} MB",
            str(preset['cpus']),
            f"{preset['disk']} GB",
        )

    console.print(preset_table)
    console.print()

    preset_choice = Prompt.ask(
        "Preset",
        choices=["minimal", "dev", "ai-researcher", "agentic", "custom"],
        default="dev",
    )

    # Get resource configuration
    if preset_choice != "custom":
        preset = PRESETS[preset_choice]
        ram = IntPrompt.ask("RAM (MB)", default=preset["ram"])
        cpus = IntPrompt.ask("CPUs", default=preset["cpus"])
        disk = IntPrompt.ask("Disk size (GB)", default=preset["disk"])
    else:
        ram = IntPrompt.ask("RAM (MB)", default=4096)
        cpus = IntPrompt.ask("CPUs", default=2)
        disk = IntPrompt.ask("Disk size (GB)", default=20)

    # Username
    console.print("\n[cyan]Step 2: User Configuration[/cyan]\n")
    console.print("[dim]This username will be used for SSH login[/dim]")
    user = Prompt.ask("Username", default="sandbox")
    console.print(f"[green]✓ Username: {user}[/green]\n")

    # SSH key
    console.print("\n[dim]SSH key configuration:[/dim]")
    
    # Try to find a default SSH key
    ssh_keys = []
    # Check for sandbox-specific key first
    sandbox_key = Path.home() / ".ssh" / "sandbox_id_ed25519.pub"
    if sandbox_key.exists():
        ssh_keys.append(sandbox_key)
        
    # Check other common keys
    for key_name in ["id_ed25519.pub", "id_rsa.pub", "id_ecdsa.pub"]:
        path = Path.home() / ".ssh" / key_name
        if path.exists() and path not in ssh_keys:
            ssh_keys.append(path)
            
    default_ssh_key = None
    if ssh_keys:
        default_ssh_key = str(ssh_keys[0])
        for key_path in ssh_keys:
            console.print(f"  [green]✓ Found:[/green] {key_path}")
    else:
        console.print("  [yellow]⚠ No SSH key found in default locations[/yellow]")

    ssh_key = Prompt.ask(
        "SSH public key path",
        default=default_ssh_key or "",
    )

    # Shell selection
    console.print("\n[cyan]Step 3: Shell Configuration[/cyan]\n")
    console.print("[dim]Choose your preferred shell for mise activation[/dim]")
    shell = Prompt.ask(
        "Shell",
        choices=["bash", "zsh"],
        default="bash",
    )
    console.print(f"[green]✓ Shell: {shell}[/green]\n")

    # Dotfiles
    console.print("\n[cyan]Step 4: Dotfiles Configuration[/cyan]\n")
    console.print("[dim]Configure your development environment:[/dim]\n")

    dotfile_choice = Prompt.ask(
        "Dotfiles source",
        choices=[
            "none",
            "preset:minimal",
            "preset:dev",
            "preset:ai-researcher",
            "git",
            "local",
        ],
        default="preset:dev",
    )

    dotfiles_source = None
    if dotfile_choice.startswith("preset:"):
        dotfiles_source = dotfile_choice.replace("preset:", "")
    elif dotfile_choice == "git":
        dotfiles_source = Prompt.ask("Git repository URL")
    elif dotfile_choice == "local":
        dotfiles_source = Prompt.ask("Local path")

    # Data mounts
    console.print("\n[cyan]Step 4: Data Mounting[/cyan]\n")
    console.print("[dim]Share directories between host and sandbox:[/dim]\n")

    mounts = []
    if Confirm.ask("Add shared directories?", default=False):
        while True:
            host_path = Prompt.ask("Host path (or 'done' to finish)")
            if host_path.lower() == "done":
                break
            vm_path = Prompt.ask("VM mount path", default=f"/mnt/{Path(host_path).name}")
            mount_type = Prompt.ask(
                "Mount type",
                choices=["9p", "sshfs"],
                default="9p",
            )
            mounts.append(f"{host_path}:{vm_path}")
            console.print(f"[green]✓ Added:[/green] {host_path} -> {vm_path} ({mount_type})\n")

    # Summary
    console.print("\n" + "=" * 50)
    console.print("[bold]Configuration Summary[/bold]\n")
    console.print(f"  [cyan]Name:[/cyan]     {name}")
    console.print(f"  [cyan]RAM:[/cyan]      {ram} MB")
    console.print(f"  [cyan]CPUs:[/cyan]     {cpus}")
    console.print(f"  [cyan]Disk:[/cyan]     {disk} GB")
    console.print(f"  [cyan]User:[/cyan]     {user}")
    console.print(f"  [cyan]SSH Key:[/cyan]  {ssh_key or 'Not configured'}")
    console.print(f"  [cyan]Dotfiles:[/cyan] {dotfiles_source or 'None'}")
    if mounts:
        console.print(f"  [cyan]Mounts:[/cyan]")
        for mount in mounts:
            console.print(f"    - {mount}")
    console.print()

    if not Confirm.ask("Create sandbox with this configuration?", default=True):
        console.print("\n[yellow]Creation cancelled[/yellow]\n")
        return

    # Build and execute command
    console.print("\n[green]Creating sandbox...[/green]\n")

    cmd_parts = ["sandbox", "create", name]
    cmd_parts.extend(["--ram", str(ram)])
    cmd_parts.extend(["--cpus", str(cpus)])
    cmd_parts.extend(["--disk", str(disk)])
    cmd_parts.extend(["--user", user])

    if ssh_key:
        cmd_parts.extend(["--ssh-key", ssh_key])

    if dotfiles_source:
        cmd_parts.extend(["--dotfiles", dotfiles_source])

    for mount in mounts:
        cmd_parts.extend(["--mount", mount])

    # Execute via subprocess to use the actual create command
    import subprocess
    from .cli import main as cli_main
    import sys

    # Parse and execute
    class Args:
        pass

    args = Args()
    args.name = name
    args.ram = ram
    args.cpus = cpus
    args.disk = disk
    args.user = user
    args.ssh_key = Path(ssh_key) if ssh_key else None
    args.password = None
    args.network = "default"
    args.image = None
    args.dotfiles = dotfiles_source
    args.mounts = mounts if mounts else None
    args.mount_type = "9p"
    args.config = None
    args.preset = preset_choice if preset_choice != "custom" else None
    args.shell = shell
    args.verbose = False
    args.tui = False
    args.template = None
    args.save_template = None

    from .commands import cmd_create
    cmd_create(args)

    console.print("\n[green]✓ Sandbox creation complete![/green]\n")
    console.print(f"[dim]Connect with: sandbox connect {name}[/dim]\n")

    try:
        save_template = Prompt.ask(
            "Save this configuration as a template?",
            choices=["y", "n"],
            default="n"
        )
        if save_template == "y":
            template_name = Prompt.ask("Template filename", default=f"{name}-template.yaml")
            template_path = Path(template_name)
            if not template_path.suffix:
                template_path = template_path.with_suffix(".yaml")
            
            import yaml
            template = {
                "ram": ram,
                "cpus": cpus,
                "disk": disk,
                "user": user,
                "preset": preset_choice if preset_choice != "custom" else None,
                "dotfiles": dotfiles_source,
                "shell": shell,
                "mounts": mounts,
            }
            with open(template_path, "w") as f:
                yaml.dump(template, f, default_flow_style=False)
            console.print(f"[green]✓ Template saved: {template_path}[/green]")
            console.print(f"[dim]Use with: sandbox create <new-name> --template {template_path}[/dim]")
    except (EOFError, KeyboardInterrupt):
        pass
