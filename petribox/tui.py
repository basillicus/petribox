"""Interactive dish creation (petribox create --tui)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table

from .agents import AGENTS
from .presets import PRESETS

console = Console()

# Common API keys offered proactively in the secrets step.
COMMON_SECRETS = [
    ("OPENAI_API_KEY",       "OpenAI (ChatGPT, GPT-4)"),
    ("ANTHROPIC_API_KEY",    "Anthropic (Claude)"),
    ("OPENROUTER_API_KEY",   "OpenRouter (multi-provider)"),
    ("NVIDIA_API_KEY",       "NVIDIA (NemoClaw, build.nvidia.com)"),
    ("GITHUB_TOKEN",         "GitHub personal access token"),
    ("HUGGINGFACE_TOKEN",    "HuggingFace Hub"),
]


def run_create_tui():
    console.print()
    console.print(Panel.fit(
        "[bold green]Petribox — Dish Creator[/bold green]\n"
        "[dim]Interactive setup for an isolated AI-agent environment[/dim]",
        border_style="green",
    ))

    # ── 1. Basics ───────────────────────────────────────────────────────────
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

    # ── 2. User & shell ─────────────────────────────────────────────────────
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

    # ── 3. Dotfiles ─────────────────────────────────────────────────────────
    console.print("\n[cyan]3. Dotfiles[/cyan]\n")
    dotfile_choice = Prompt.ask(
        "Dotfiles",
        choices=["none", "preset:minimal", "preset:dev", "preset:ai-researcher", "git", "local"],
        default="none",
    )
    dotfiles_source = None
    if dotfile_choice.startswith("preset:"):
        dotfiles_source = dotfile_choice.split(":", 1)[1]
    elif dotfile_choice == "git":
        dotfiles_source = Prompt.ask("Git repository URL")
    elif dotfile_choice == "local":
        dotfiles_source = Prompt.ask("Local path")

    # ── 4. Agent ────────────────────────────────────────────────────────────
    console.print("\n[cyan]4. Agent (optional)[/cyan]\n")
    agent_table = Table(show_header=True, header_style="bold")
    agent_table.add_column("Key", style="cyan")
    agent_table.add_column("Name")
    agent_table.add_column("Description")
    for key, cfg in AGENTS.items():
        agent_table.add_row(key, cfg["name"], cfg["description"])
    console.print(agent_table)

    agent_choice = Prompt.ask(
        "Install an agent",
        choices=["none", *AGENTS.keys()],
        default="none",
    )
    agent = None if agent_choice == "none" else agent_choice

    # ── 5. Secrets / API keys ───────────────────────────────────────────────
    console.print("\n[cyan]5. Secrets & API keys (optional)[/cyan]\n")
    console.print("[dim]These are written to the user's shell rc inside the dish.[/dim]\n")
    env_vars: dict[str, str] = {}

    # Warn about keys the chosen agent requires
    if agent:
        required = AGENTS[agent].get("required_env", [])
        if required:
            console.print(
                f"[yellow]  {AGENTS[agent]['name']} needs: {', '.join(required)}[/yellow]\n"
            )

    if Confirm.ask("Add API keys / secrets?", default=bool(agent)):
        # Offer common keys
        for env_key, label in COMMON_SECRETS:
            val = Prompt.ask(f"  {env_key} [{label}]", default="")
            if val:
                env_vars[env_key] = val

        # Free-form extras
        while Confirm.ask("  Add another variable?", default=False):
            extra_key = Prompt.ask("    KEY")
            extra_val = Prompt.ask("    VALUE")
            if extra_key:
                env_vars[extra_key] = extra_val

    # ── 6. Shared directories ───────────────────────────────────────────────
    console.print("\n[cyan]6. Shared directories (optional)[/cyan]\n")
    mounts = []
    if Confirm.ask("Add shared directories?", default=False):
        while True:
            host_path = Prompt.ask("Host path (or 'done')")
            if host_path.lower() == "done":
                break
            vm_path = Prompt.ask("Mount path in dish", default=f"/mnt/{Path(host_path).name}")
            mounts.append(f"{host_path}:{vm_path}")
            console.print(f"[green]✓[/green] {host_path} -> {vm_path}\n")

    # ── Summary ─────────────────────────────────────────────────────────────
    console.print("\n" + "=" * 50)
    console.print("[bold]Summary[/bold]\n")
    console.print(f"  Name:     {name}")
    console.print(f"  Type:     {instance_type}")
    console.print(f"  Resources:{ram} MB / {cpus} CPU / {disk} GB")
    console.print(f"  User:     {user} ({shell})")
    console.print(f"  Preset:   {preset_choice}")
    console.print(f"  Dotfiles: {dotfiles_source or 'none'}")
    console.print(f"  Agent:    {agent or 'none'}")
    if env_vars:
        console.print(f"  Secrets:  {', '.join(env_vars.keys())}")
    if mounts:
        console.print(f"  Mounts:   {', '.join(mounts)}")
    console.print()

    if not Confirm.ask("Create this dish?", default=True):
        console.print("\n[yellow]Cancelled[/yellow]\n")
        return

    # ── Save template ────────────────────────────────────────────────────────
    if Confirm.ask("Save as a reusable config template?", default=False):
        default_path = f"{name}-config.yaml"
        out_path = Prompt.ask("Template file", default=default_path)
        template: dict = {}
        if preset_choice != "custom":
            template["# preset"] = preset_choice  # type: ignore[assignment]
        if env_vars:
            template["environment"] = {k: "<redacted>" for k in env_vars}
            console.print(
                "[yellow]  Note: API key values are redacted in the saved template.[/yellow]"
            )
        Path(out_path).write_text(
            "# petribox config — use with: petribox create <name> --config " + out_path + "\n"
            + yaml.dump(template, default_flow_style=False, sort_keys=False),
        )
        console.print(f"[green]✓ Template saved to {out_path}[/green]")

    # ── Build args and create ────────────────────────────────────────────────
    env_list = [f"{k}={v}" for k, v in env_vars.items()] or None

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
        env=env_list,
        verbose=False,
        tui=False,
    )

    from .commands import cmd_create

    cmd_create(args)
    console.print(f"\n[dim]Connect with: petribox connect {name}[/dim]\n")
