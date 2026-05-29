"""Interactive dish creation (petribox create --tui)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from .presets import PRESETS

console = Console()

DOTFILE_PRESET_CHOICES = ["minimal", "dev", "ai-researcher"]


def run_create_tui():
    console.print()
    console.print(Panel.fit(
        "[bold green]Petribox - Dish Creator[/bold green]\n"
        "[dim]Interactive setup for an isolated AI-agent environment[/dim]",
        border_style="green",
    ))

    console.print("\n[cyan]1. Basics[/cyan]\n")
    name = Prompt.ask("Dish name", default="my-dish")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Preset", style="cyan")
    table.add_column("Description")
    table.add_column("RAM", justify="right")
    table.add_column("CPUs", justify="right")
    table.add_column("Disk", justify="right")
    for pname, preset in PRESETS.items():
        table.add_row(pname, preset["description"], f"{preset['ram']} MB",
                      str(preset["cpus"]), f"{preset['disk']} GB")
    console.print(table)

    preset_choice = Prompt.ask("Preset", choices=[*PRESETS, "custom"], default="dev")
    if preset_choice != "custom":
        preset = PRESETS[preset_choice]
        ram = IntPrompt.ask("RAM (MB)", default=preset["ram"])
        cpus = IntPrompt.ask("CPUs", default=preset["cpus"])
        disk = IntPrompt.ask("Disk (GB)", default=preset["disk"])
    else:
        ram = IntPrompt.ask("RAM (MB)", default=4096)
        cpus = IntPrompt.ask("CPUs", default=2)
        disk = IntPrompt.ask("Disk (GB)", default=20)

    instance_type = Prompt.ask("Instance type", choices=["vm", "container"], default="vm")

    console.print("\n[cyan]2. User & shell[/cyan]\n")
    user = Prompt.ask("Username", default="petri")
    shell = Prompt.ask("Shell", choices=["bash", "zsh"], default="bash")

    default_key = None
    for key in (Path.home() / ".ssh" / "id_ed25519.pub", Path.home() / ".ssh" / "id_rsa.pub"):
        if key.exists():
            default_key = str(key)
            console.print(f"[green]✓ SSH key:[/green] {key}")
            break
    ssh_key = Prompt.ask("SSH public key path (blank = exec-only access)",
                         default=default_key or "")

    console.print("\n[cyan]3. Dotfiles[/cyan]\n")
    dotfile_choice = Prompt.ask(
        "Dotfiles",
        choices=["none", "preset:minimal", "preset:dev", "preset:ai-researcher", "git", "local"],
        default="preset:dev",
    )
    dotfiles_source = None
    if dotfile_choice.startswith("preset:"):
        dotfiles_source = dotfile_choice.split(":", 1)[1]
    elif dotfile_choice == "git":
        dotfiles_source = Prompt.ask("Git repository URL")
    elif dotfile_choice == "local":
        dotfiles_source = Prompt.ask("Local path")

    console.print("\n[cyan]4. Agent (optional)[/cyan]\n")
    agent_choice = Prompt.ask("Install an agent",
                              choices=["none", "hermes", "openclaw", "zeroclaw"], default="none")
    agent = None if agent_choice == "none" else agent_choice

    console.print("\n[cyan]5. Shared directories (optional)[/cyan]\n")
    mounts = []
    if Confirm.ask("Add shared directories?", default=False):
        while True:
            host_path = Prompt.ask("Host path (or 'done')")
            if host_path.lower() == "done":
                break
            vm_path = Prompt.ask("Mount path in dish", default=f"/mnt/{Path(host_path).name}")
            mounts.append(f"{host_path}:{vm_path}")
            console.print(f"[green]✓[/green] {host_path} -> {vm_path}\n")

    console.print("\n" + "=" * 50)
    console.print("[bold]Summary[/bold]\n")
    console.print(f"  Name:     {name}")
    console.print(f"  Type:     {instance_type}")
    console.print(f"  Resources:{ram} MB / {cpus} CPU / {disk} GB")
    console.print(f"  User:     {user} ({shell})")
    console.print(f"  Preset:   {preset_choice}")
    console.print(f"  Dotfiles: {dotfiles_source or 'none'}")
    console.print(f"  Agent:    {agent or 'none'}")
    if mounts:
        console.print(f"  Mounts:   {', '.join(mounts)}")
    console.print()

    if not Confirm.ask("Create this dish?", default=True):
        console.print("\n[yellow]Cancelled[/yellow]\n")
        return

    args = SimpleNamespace(
        name=name,
        container=(instance_type == "container"),
        ram=ram, cpus=cpus, disk=disk,
        user=user, shell=shell,
        ssh_key=Path(ssh_key) if ssh_key else None,
        password=None,
        image=None,
        dotfiles=dotfiles_source,
        mounts=mounts or None,
        config=None,
        preset=preset_choice if preset_choice != "custom" else None,
        agent=agent,
        verbose=False,
        tui=False,
    )

    from .commands import cmd_create

    cmd_create(args)
    console.print(f"\n[dim]Connect with: petribox connect {name}[/dim]\n")
