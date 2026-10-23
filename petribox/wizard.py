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


# Common images on the default `images:` server. Kali is container-only
# there (the `kali` recipe is the VM, from Kali's own image).
IMAGES = ["debian/13", "ubuntu/26.04", "rockylinux/10", "rockylinux/9", "fedora/44",
          "archlinux", "opensuse/tumbleweed", "kali"]
CONTAINER_ONLY = {"kali"}


def ask(args) -> bool:
    """Fill `args` interactively. False if the user cancels."""
    console.print(Panel.fit("[bold green]petribox: new dish[/bold green]\n"
                            "[dim]Enter keeps the default shown in brackets.[/dim]",
                            border_style="green"))

    section("1. Source")
    all_recipes = recipes.all_recipes()
    rows = []
    for r in all_recipes:
        built = incus.has_snapshot(r.base, "clean")
        base = ui.Text("ready", style="green") if built else ui.Text("builds first", style="yellow")
        rows.append((r.name, "vm" if r.vm else "container", base, r.description))
    rows.append(("image", "vm or container", ui.Text("set up each time", style="dim"),
                 "any Incus image, no recipe (you can save it as one at the end)"))
    ui.table([("Choice", "cyan"), ("Type", ""), ("Base", ""), ("Description", "")], rows)
    ui.info("A recipe's base is built once (minutes), then each dish is a copy (seconds).")
    names = [r.name for r in all_recipes]
    choice = Prompt.ask("From", choices=names + ["image"], default="image")
    if choice == "image":
        args.recipe = None
        ui.info("Images: " + ", ".join(IMAGES) + ", or other")
        pick = Prompt.ask("Image", choices=IMAGES + ["other"], default="debian/13", show_choices=False)
        args.image = Prompt.ask("Image (remote:alias)") if pick == "other" else f"images:{pick}"
        if pick in CONTAINER_ONLY:
            ui.info(f"{pick} is container-only on images: (for a VM, use the kali recipe)")
            args.container = True
        else:
            args.container = Prompt.ask("Type", choices=["vm", "container"], default="vm") == "container"
        defaults = recipes.Recipe(name="", dir=Path(), image=args.image)
    else:
        args.recipe, args.image = choice, None
        defaults = next(r for r in all_recipes if r.name == choice)

    section("2. Dish")
    args.name = Prompt.ask("Name", default=args.name or "lab")
    args.cpus = IntPrompt.ask("CPUs", default=args.cpus or defaults.cpus)
    args.memory = Prompt.ask("Memory", default=args.memory or defaults.memory)
    if args.image:
        args.disk = Prompt.ask("Disk", default=args.disk or defaults.disk)
        args.user = Prompt.ask("User", default=args.user or defaults.user)
    args.ephemeral = Confirm.ask("Ephemeral (deleted when it stops)?", default=True)

    section("3. Extras")
    extras = recipes.all_extras()
    ui.table([("Extra", "cyan"), ("Description", "")],
             [(e.name, e.description) for e in extras.values()])
    if defaults.extras:
        ui.info(f"Already in the recipe: {', '.join(defaults.extras)}")
    while True:
        picked = Prompt.ask("Extras, comma-separated, NAME@VERSION to pin (blank: none)", default="")
        args.extra = [x.strip() for x in picked.split(",") if x.strip()]
        unknown = [x for x in args.extra if x.partition("@")[0] not in extras]
        if not unknown:
            break
        ui.warn(f"unknown: {', '.join(unknown)}")

    section("4. Secrets")
    known = sorted(secrets.configured_sources())
    if known:
        ui.info(f"From your config: {', '.join(known)}. Others are asked for, hidden.")
    picked = Prompt.ask("Variables, comma-separated (blank: none)", default="")
    args.secret = [k.strip() for k in picked.split(",") if k.strip()]

    section("5. Dotfiles and shared folders")
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

    if args.image:
        offer_to_save(args)

    console.print()
    ui.hint("Same without the questions", command_line(args))
    return Confirm.ask("Create it?", default=True)


def offer_to_save(args) -> None:
    """Image answers -> a recipe, so next time it is a menu entry and a fast copy."""
    section("6. Save")
    if not Confirm.ask("Save this setup as a recipe?", default=True):
        return
    default = args.image.split(":", 1)[-1].replace("/", "-").replace(".", "")
    while True:
        name = Prompt.ask("Recipe name", default=default)
        exists = any(r.name == name for r in recipes.all_recipes())
        if not exists or Confirm.ask(f"Recipe '{name}' exists; replace it?", default=False):
            break
    r = recipes.Recipe(
        name=name, dir=Path(), image=args.image, vm=not args.container, cpus=args.cpus,
        memory=args.memory, disk=args.disk, user=args.user, extras=args.extra,
        description=Prompt.ask("Description", default=f"{args.image}"
                               + (f" with {', '.join(args.extra)}" if args.extra else "")),
    )
    path = recipes.save(r)
    ui.ok(f"Saved {path}/recipe.toml (add a provision.sh there for anything else)")
    # The dish now comes from the recipe: built once here, copied from then on.
    args.recipe, args.image, args.extra = name, None, []


def command_line(args) -> str:
    cmd = ["petribox", "new", args.name]
    if args.recipe:
        cmd += ["--from", args.recipe]
    else:
        cmd += ["--image", args.image] + (["--container"] if args.container else [])
        cmd += ["--disk", args.disk, "--user", args.user]
    cmd += ["--cpus", str(args.cpus), "--memory", args.memory]
    cmd += ["--ephemeral"] if args.ephemeral else []
    for name in args.extra:
        cmd += ["--extra", name]
    for key in args.secret:
        cmd += ["--secret", key]
    for path in args.share:
        cmd += ["--share", path]
    cmd += ["--no-dotfiles"] if args.no_dotfiles else []
    return shlex.join(cmd)
