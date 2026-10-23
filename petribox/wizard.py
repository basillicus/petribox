"""`petribox new` with no arguments: decide everything on the spot.

The answers fill the same argparse namespace the flags would, and the
equivalent command line is printed so a quick test can be repeated without
the questions.
"""

from __future__ import annotations

import shlex
from pathlib import Path

from rich.markup import escape
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt

from . import incus, recipes, secrets, ui

console = ui.console


def section(title: str) -> None:
    console.print(f"\n[cyan]{escape(title)}[/cyan]")


def ask(args) -> bool:
    """Fill `args` interactively. False if the user cancels."""
    console.print(Panel.fit("[bold green]petribox: new dish[/bold green]\n"
                            "[dim]Enter keeps the default shown in brackets.[/dim]",
                            border_style="green"))

    section("1. Source")
    built = [r for r in recipes.all_recipes() if incus.has_snapshot(r.base, "clean")]
    ui.table([("Choice", "cyan"), ("Type", ""), ("Description", "")],
             [(r.name, "vm" if r.vm else "container", r.description) for r in built]
             + [("image", "vm or container", "any Incus image, set up on the spot (no recipe)")])
    choice = Prompt.ask("From", choices=[r.name for r in built] + ["image"],
                        default=built[0].name if built else "image")
    if choice == "image":
        args.recipe = None
        args.image = Prompt.ask("Image", default="images:debian/13")
        args.container = Prompt.ask("Type", choices=["vm", "container"], default="vm") == "container"
        defaults = recipes.Recipe(name="", dir=Path(), image=args.image)
    else:
        args.recipe, args.image = choice, None
        defaults = next(r for r in built if r.name == choice)

    section("2. Dish")
    args.name = Prompt.ask("Name", default=args.name or "lab")
    args.cpus = IntPrompt.ask("CPUs", default=args.cpus or defaults.cpus)
    args.memory = Prompt.ask("Memory", default=args.memory or defaults.memory)
    if args.image:
        args.disk = Prompt.ask("Disk", default=args.disk or defaults.disk)
        args.user = Prompt.ask("User", default=args.user or defaults.user)
    args.ephemeral = Confirm.ask("Ephemeral (deleted when it stops)?", default=True)

    section("3. Secrets")
    known = sorted(secrets.configured_sources())
    if known:
        ui.info(f"From your config: {', '.join(known)}. Others are asked for, hidden.")
    picked = Prompt.ask("Variables, comma-separated (blank: none)", default="")
    args.secret = [k.strip() for k in picked.split(",") if k.strip()]

    section("4. Dotfiles and shared folders")
    repo = (secrets.user_config().get("dotfiles") or {}).get("repo")
    if repo:
        args.no_dotfiles = not Confirm.ask(f"Apply dotfiles from {escape(repo)}?", default=True)
    else:
        ui.info("No [dotfiles] repo in the config; skipping.")
    args.share = []
    while True:
        path = Prompt.ask("Share a host folder (blank: done)", default="")
        if not path:
            break
        if not Path(path).expanduser().is_dir():
            ui.warn(f"not a directory: {path}")
            continue
        args.share.append(path)

    console.print()
    ui.hint("Same without the questions", command_line(args))
    return Confirm.ask("Create it?", default=True)


def command_line(args) -> str:
    cmd = ["petribox", "new", args.name]
    if args.recipe:
        cmd += ["--from", args.recipe]
    else:
        cmd += ["--image", args.image] + (["--container"] if args.container else [])
        cmd += ["--disk", args.disk, "--user", args.user]
    cmd += ["--cpus", str(args.cpus), "--memory", args.memory]
    cmd += ["--ephemeral"] if args.ephemeral else []
    for key in args.secret:
        cmd += ["--secret", key]
    for path in args.share:
        cmd += ["--share", path]
    cmd += ["--no-dotfiles"] if args.no_dotfiles else []
    return shlex.join(cmd)
