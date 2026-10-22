"""petribox command line. Everything not here is plain `incus` (see README)."""

from __future__ import annotations

import argparse
import io
import json
import os
import shlex
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from . import __version__, incus, recipes, secrets

USER_KEY = "user.petribox.user"  # set on the base, so every copy carries it


def fail(msg: str) -> None:
    print(f"petribox: {msg}", file=sys.stderr)
    sys.exit(1)


def dish_user(name: str) -> str:
    user = incus.config_get(name, USER_KEY)
    if not user:
        fail(f"'{name}' was not made by petribox ({USER_KEY} is not set)")
    return user


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_recipes(args) -> None:
    for r in recipes.all_recipes():
        built = "built" if incus.has_snapshot(r.base, "clean") else "-"
        kind = "vm" if r.vm else "container"
        print(f"{r.name:15s} {kind:9s} {built:5s}  {r.image:24s} {r.description}")


def cmd_build(args) -> None:
    """Plain image -> provisioned base instance, stopped, with a `clean` snapshot."""
    r = recipes.find(args.recipe)
    if args.resume:
        # Finish a build that stopped at the agent (e.g. after installing it by hand).
        if not incus.exists(r.base):
            fail(f"nothing to resume: {r.base} does not exist")
        if incus.run("info", r.base).stdout.find("Status: RUNNING") < 0:
            incus.run("start", r.base)
        provision_and_snapshot(r, args.timeout)
        return
    if incus.exists(r.base):
        if not args.rebuild:
            fail(f"{r.base} already exists; pass --rebuild to start it over, or --resume")
        incus.run("delete", "--force", r.base)

    init = ["init", r.image, r.base,
            "-c", f"limits.cpu={r.cpus}", "-c", f"limits.memory={r.memory}",
            "-c", f"{USER_KEY}={r.user}", "-d", f"root,size={r.disk}"]
    for key, value in r.config.items():
        init += ["-c", f"{key}={value}"]
    if r.vm:
        init.append("--vm")
    print(f"== {r.base}: creating from {r.image}")
    incus.run(*init, capture=False)  # shows the image download progress
    if r.vm:
        # Images without a built-in agent (cloud variants, imported disks) need
        # the agent config drive; for the others it does no harm.
        incus.run("config", "device", "add", r.base, "agent", "disk", "source=agent:config",
                  check=False)
    incus.run("start", r.base)
    provision_and_snapshot(r, args.timeout)


def provision_and_snapshot(r: recipes.Recipe, timeout: float) -> None:
    try:
        incus.wait_for_agent(r.base, timeout=timeout)
    except incus.IncusError:
        fail(f"{r.base} is running but has no Incus agent. Install it inside the instance "
             f"(see README, 'Images without an agent'), then: petribox build {r.name} --resume")

    print(f"== {r.base}: provisioning")
    incus.run("exec", r.base, "--env", f"PB_USER={r.user}", "--", "bash", "-s",
              input=r.script(), capture=False)

    print(f"== {r.base}: snapshot 'clean'")
    incus.run("stop", r.base)
    if incus.has_snapshot(r.base, "clean"):
        incus.run("snapshot", "delete", r.base, "clean")
    incus.run("snapshot", "create", r.base, "clean")
    print(f"Done. Make a dish: petribox new <name> --from {r.name}")


def cmd_new(args) -> None:
    r = recipes.find(args.recipe)
    if not incus.has_snapshot(r.base, "clean"):
        fail(f"recipe '{r.name}' is not built yet: petribox build {r.name}")
    if incus.exists(args.name):
        fail(f"'{args.name}' already exists")

    # Resolve secrets before the copy, so a prompt or a failing command
    # happens before anything is created.
    env = {key: secrets.resolve(key) for key in args.secret or []}

    copy = ["copy", f"{r.base}/clean", args.name]
    if args.ephemeral:
        copy.append("--ephemeral")
    if args.cpus:
        copy += ["-c", f"limits.cpu={args.cpus}"]
    if args.memory:
        copy += ["-c", f"limits.memory={args.memory}"]
    incus.run(*copy)
    incus.run("start", args.name)
    incus.wait_for_agent(args.name)

    user = dish_user(args.name)
    if env:
        secrets.write_env(args.name, user, env)
        print(f"secrets: {', '.join(sorted(env))}")
    repo = (secrets.user_config().get("dotfiles") or {}).get("repo")
    if repo and not args.no_dotfiles:
        apply_dotfiles(args.name, user, repo)

    note = " (ephemeral: deleted when it stops)" if args.ephemeral else ""
    print(f"Dish '{args.name}' is running{note}. Enter it: petribox shell {args.name}")


def apply_dotfiles(name: str, user: str, repo: str) -> None:
    """chezmoi does the dotfiles; installed into ~/.local/bin if missing."""
    script = (
        "export PATH=$HOME/.local/bin:$PATH; "
        "command -v chezmoi >/dev/null || sh -c \"$(curl -fsLS get.chezmoi.io)\" -- -b ~/.local/bin; "
        f"chezmoi init --apply {shlex.quote(repo)}"
    )
    print(f"dotfiles: {repo}")
    incus.run("exec", name, "--", "su", "-", user, "-c", script, capture=False)


def cmd_import_image(args) -> None:
    """A VM disk image (qcow2, e.g. a distro's official QEMU image) -> local Incus image."""
    disk = Path(args.disk).resolve()
    if not disk.is_file():
        fail(f"no such file: {disk}")
    metadata = (
        "architecture: x86_64\n"
        f"creation_date: {int(time.time())}\n"
        "properties:\n"
        f"  description: {json.dumps(args.description or disk.name)}\n"
    )
    with tempfile.TemporaryDirectory() as tmp:
        meta = Path(tmp) / "metadata.tar"
        with tarfile.open(meta, "w") as tar:
            info = tarfile.TarInfo("metadata.yaml")
            info.size = len(metadata.encode())
            tar.addfile(info, io.BytesIO(metadata.encode()))
        print(f"importing {disk.name} as '{args.alias}' (copies the whole disk)")
        incus.run("image", "import", str(meta), str(disk), "--alias", args.alias, capture=False)


def cmd_shell(args) -> None:
    user = dish_user(args.name)
    argv = ["incus", "exec", args.name, "--", "su", "-", user]
    if args.command:
        argv += ["-c", " ".join(args.command)]  # like ssh: words joined, the shell parses
    os.execvp("incus", argv)


def cmd_secret(args) -> None:
    user = dish_user(args.name)
    env = secrets.read_env(args.name, user)
    if not (args.keys or args.unset):
        for key, value in sorted(env.items()):
            print(f"{key}={secrets.mask(value)}")
        return
    for key in args.unset or []:
        env.pop(key, None)
    for key in args.keys:
        env[key] = secrets.resolve(key)
    secrets.write_env(args.name, user, env)
    print(f"{args.name}: {', '.join(sorted(env)) or 'no secrets'}")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="petribox",
        description="Incus sandboxes built from recipes. Everything else is plain incus.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("recipes", help="list recipes and whether their base is built")
    p.set_defaults(func=cmd_recipes)

    p = sub.add_parser("build", help="build a recipe's base instance and its 'clean' snapshot")
    p.add_argument("recipe")
    p.add_argument("--rebuild", action="store_true", help="delete an existing base first")
    p.add_argument("--resume", action="store_true", help="provision an existing base (after a manual step)")
    p.add_argument("--timeout", type=float, default=300, help="seconds to wait for the agent")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("new", help="make a dish from a built recipe")
    p.add_argument("name")
    p.add_argument("--from", dest="recipe", required=True, metavar="RECIPE")
    p.add_argument("--ephemeral", action="store_true", help="delete the dish when it stops")
    p.add_argument("--secret", action="append", metavar="KEY", help="hand in a secret (repeatable)")
    p.add_argument("--cpus", type=int, help="override the recipe's CPU limit")
    p.add_argument("--memory", help="override the recipe's memory limit, e.g. 8GiB")
    p.add_argument("--no-dotfiles", action="store_true", help="skip [dotfiles] from the config")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("import-image", help="turn a VM disk image (qcow2) into a local Incus image")
    p.add_argument("disk")
    p.add_argument("alias", help="name to use as a recipe's image")
    p.add_argument("--description")
    p.set_defaults(func=cmd_import_image)

    p = sub.add_parser("shell", help="login shell (or one command) as the dish user")
    p.add_argument("name")
    p.add_argument("command", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_shell)

    p = sub.add_parser("secret", help="list (masked), set or unset a dish's secrets")
    p.add_argument("name")
    p.add_argument("keys", nargs="*", metavar="KEY", help="set these (from config or a prompt)")
    p.add_argument("--unset", action="append", metavar="KEY")
    p.set_defaults(func=cmd_secret)
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except (incus.IncusError, recipes.RecipeError, secrets.SecretError) as exc:
        fail(str(exc))
    except KeyboardInterrupt:
        sys.exit(130)
