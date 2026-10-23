"""petribox command line. Everything not here is plain `incus` (see README)."""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shlex
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from . import __version__, export, incus, recipes, secrets, ui, wizard
from .ui import fail

USER_KEY = "user.petribox.user"  # set on the base, so every copy carries it
RECIPE_KEY = "user.petribox.recipe"


def image_config(image: str, vm: bool, config: dict) -> list[str]:
    """`-c` options an image needs that the recipe did not set. Some VM
    images (Arch) are not signed for Secure Boot and say so in their
    metadata; Incus refuses to create them with Secure Boot on."""
    reqs = incus.image_requirements(image, vm)
    if vm and reqs.get("secureboot") == "false" and "security.secureboot" not in config:
        ui.info(f"{image} needs Secure Boot off; setting security.secureboot=false")
        return ["-c", "security.secureboot=false"]
    return []


def create(init: list[str], name: str) -> None:
    """`incus init`, removing a half-created instance if it fails, so the
    next attempt does not trip over it."""
    try:
        incus.run(*init, capture=False)  # shows the image download progress
    except incus.IncusError:
        if incus.exists(name):
            incus.run("delete", "--force", name, check=False)
        raise


def dish_user(name: str) -> str:
    user = incus.config_get(name, USER_KEY)
    if not user:
        fail(f"'{name}' was not made by petribox ({USER_KEY} is not set)")
    return user


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------
def cmd_recipes(args) -> None:
    rows = []
    for r in recipes.all_recipes():
        built = ui.Text("✓ built", style="green") if incus.has_snapshot(r.base, "clean") else ui.Text("-", style="dim")
        rows.append((r.name, "vm" if r.vm else "container", built, r.image, r.description))
    ui.table([("Recipe", "cyan"), ("Type", ""), ("Base", ""), ("Image", "dim"), ("Description", "")],
             rows, title="Recipes")


def cmd_build(args) -> None:
    build_base(recipes.find(args.recipe), rebuild=args.rebuild, resume=args.resume,
               timeout=args.timeout)


def build_base(r: recipes.Recipe, rebuild: bool = False, resume: bool = False,
               timeout: float = 300) -> None:
    """Plain image -> provisioned base instance, stopped, with a `clean` snapshot."""
    if resume:
        # Finish a build that stopped at the agent (e.g. after installing it by hand).
        if not incus.exists(r.base):
            fail(f"nothing to resume: {r.base} does not exist")
        if incus.run("info", r.base).stdout.find("Status: RUNNING") < 0:
            incus.run("start", r.base)
        provision_and_snapshot(r, timeout)
        return
    if incus.exists(r.base):
        if not rebuild:
            fail(f"{r.base} already exists; pass --rebuild to start it over, or --resume")
        incus.run("delete", "--force", r.base)

    init = ["init", r.image, r.base,
            "-c", f"limits.cpu={r.cpus}", "-c", f"limits.memory={r.memory}",
            "-c", f"{USER_KEY}={r.user}", "-c", f"{RECIPE_KEY}={r.name}",
            "-d", f"root,size={r.disk}"]
    for key, value in r.config.items():
        init += ["-c", f"{key}={value}"]
    init += image_config(r.image, r.vm, r.config)
    if r.vm:
        init.append("--vm")
    ui.step(f"{r.base}: creating from {r.image}")
    create(init, r.base)
    if r.vm:
        # Images without a built-in agent (cloud variants, imported disks) need
        # the agent config drive; for the others it does no harm.
        incus.run("config", "device", "add", r.base, "agent", "disk", "source=agent:config",
                  check=False)
    incus.run("start", r.base)
    provision_and_snapshot(r, timeout)


def provision_and_snapshot(r: recipes.Recipe, timeout: float) -> None:
    try:
        with ui.spinner(f"Waiting for the Incus agent in {r.base}..."):
            incus.wait_for_agent(r.base, timeout=timeout)
    except incus.IncusError:
        fail(f"{r.base} is running but has no Incus agent. Install it inside the instance "
             f"(see README, 'Images without an agent'), then: petribox build {r.name} --resume")

    ui.step(f"{r.base}: provisioning")
    run_script(r.base, r.user, r.script())

    ui.step(f"{r.base}: snapshot 'clean'")
    # Some guests (Kali's desktop image) ignore the ACPI shutdown request, so
    # flush the disks first and force the stop if the clean one times out.
    with ui.spinner(f"Stopping {r.base}..."):
        incus.run("exec", r.base, "--", "sync", check=False)
        stopped = incus.run("stop", r.base, "--timeout", "60", check=False).returncode == 0
        if not stopped:
            incus.run("stop", r.base, "--force")
    if not stopped:
        ui.warn(f"{r.base} ignored the shutdown request; stopped it by force after syncing")
    if incus.has_snapshot(r.base, "clean"):
        incus.run("snapshot", "delete", r.base, "clean")
    incus.run("snapshot", "create", r.base, "clean")
    ui.ok(f"{r.base} built")


def run_script(name: str, user: str, script: str) -> None:
    """Run a provisioning script as root. It goes in as a file, not on stdin,
    so a command in it that reads stdin cannot swallow the rest."""
    path = "/var/tmp/petribox-provision.sh"
    incus.run("exec", name, "--", "sh", "-c", f"umask 077 && cat > {path}", input=script)
    env = ["--env", f"PB_USER={user}"]
    key = host_ssh_key()
    if key:
        env += ["--env", f"PB_SSH_KEY={key}"]  # a public key: fine on argv
    try:
        incus.run("exec", name, *env, "--", "bash", path, capture=False)
    finally:
        incus.run("exec", name, "--", "rm", "-f", path, check=False)


def host_ssh_key() -> str:
    for kind in ("ed25519", "ecdsa", "rsa"):
        pub = Path.home() / ".ssh" / f"id_{kind}.pub"
        if pub.is_file():
            return pub.read_text().strip()
    return ""


def ipv4(inst: dict) -> str:
    """First IPv4 of an instance (from `incus list` or a state query)."""
    network = (inst.get("state") or inst).get("network") or {}
    for nic, net in network.items():
        for addr in net.get("addresses", []) if nic != "lo" else []:
            if addr.get("family") == "inet":
                return addr["address"]
    return ""


def cmd_extras(args) -> None:
    ui.table([("Extra", "cyan"), ("Needs", "dim"), ("Description", "")],
             [(e.name, " ".join(e.needs), e.description) for e in recipes.all_extras().values()],
             title="Extras (recipe: extras = [...]; one dish: petribox new ... --extra NAME)")


def cmd_new(args) -> None:
    """A dish from a built recipe (--from), straight from an image (--image),
    or, with neither, from answers to a few questions."""
    if not (args.recipe or args.image):
        if not sys.stdin.isatty():
            fail("give --from RECIPE or --image IMAGE (or run on a terminal to be asked)")
        if not wizard.ask(args):
            ui.warn("Cancelled")
            return
    elif not args.name:
        fail("give the dish a name: petribox new NAME --from RECIPE")
    if args.recipe and args.image:
        fail("--from and --image are alternatives; pick one")
    if incus.exists(args.name):
        fail(f"'{args.name}' already exists")
    shares = [Path(d).expanduser().resolve() for d in args.share or []]
    for d in shares:
        if not d.is_dir():
            fail(f"no such directory: {d}")
    r = recipes.find(args.recipe) if args.recipe else None
    extras = args.extra or []
    recipes.resolve_extras(extras)  # unknown names fail now, not after the copy

    # Resolve secrets before anything is created, so a prompt or a failing
    # command costs nothing.
    env = {key: secrets.resolve(key) for key in args.secret or []}

    if r and not incus.has_snapshot(r.base, "clean"):
        ui.info(f"Recipe '{r.name}' has no base yet; building it once (a few minutes).")
        build_base(r, rebuild=incus.exists(r.base))

    limits = []
    if args.cpus:
        limits += ["-c", f"limits.cpu={args.cpus}"]
    if args.memory:
        limits += ["-c", f"limits.memory={args.memory}"]
    if r:
        copy = ["copy", f"{r.base}/clean", args.name, "-c", f"{RECIPE_KEY}={r.name}", *limits]
        copy += ["--ephemeral"] if args.ephemeral else []
        with ui.spinner(f"Creating {args.name} from {r.base}/clean..."):
            incus.run(*copy)
            incus.run("start", args.name)
        ui.ok(f"{args.name} created ({'vm' if r.vm else 'container'}, recipe {r.name})")
        with ui.spinner(f"Waiting for {args.name} to boot..."):
            incus.wait_for_agent(args.name)
        if extras:
            ui.step(f"{args.name}: extras {', '.join(extras)}")
            run_script(args.name, dish_user(args.name), recipes.provision_script(extras))
    else:
        launch_from_image(args, limits, extras)

    user = dish_user(args.name)
    if env:
        secrets.write_env(args.name, user, env)
        ui.ok(f"Secrets: {', '.join(sorted(env))}")
    repo = (secrets.user_config().get("dotfiles") or {}).get("repo")
    if repo and not args.no_dotfiles:
        apply_dotfiles(args.name, user, repo)
    for d in shares:
        mount_dir(args.name, user, d)

    ui.ok(f"Dish '{args.name}' is ready")
    if args.ephemeral:
        ui.info("Ephemeral: it is deleted when it stops.")
    ui.hint("Enter", f"petribox shell {args.name}")
    if "ssh" in [e.name for e, _ in recipes.resolve_extras((r.extras if r else []) + extras)]:
        addr = ipv4(json.loads(incus.run("query", f"/1.0/instances/{args.name}/state").stdout))
        ui.hint("SSH", f"ssh {user}@{addr or '<ip from petribox list>'}")
    ui.hint("Share", f"petribox mount {args.name} ./dir")
    ui.hint("Delete", f"incus delete -f {args.name}")


def launch_from_image(args, limits: list[str], extras: list[str]) -> None:
    """No recipe, no base: the image itself, set up with `_common.sh` only.
    Slower per dish than a recipe (packages install every time)."""
    vm = not args.container
    user = args.user or "petri"
    init = ["init", args.image, args.name, *limits, "-c", f"{USER_KEY}={user}",
            "-c", f"{RECIPE_KEY}={args.image}"]
    init += ["-d", f"root,size={args.disk}"] if args.disk else []
    init += image_config(args.image, vm, {})
    init += ["--vm"] if vm else []
    init += ["--ephemeral"] if args.ephemeral else []
    ui.step(f"{args.name}: creating from {args.image}")
    create(init, args.name)
    if vm:
        incus.run("config", "device", "add", args.name, "agent", "disk", "source=agent:config",
                  check=False)
    incus.run("start", args.name)
    with ui.spinner(f"Waiting for {args.name} to boot..."):
        incus.wait_for_agent(args.name)
    ui.step(f"{args.name}: setting up user '{user}'" + (f", extras {', '.join(extras)}" if extras else ""))
    run_script(args.name, user, recipes.provision_script(extras))


def apply_dotfiles(name: str, user: str, repo: str) -> None:
    """chezmoi does the dotfiles; installed into ~/.local/bin if missing."""
    script = (
        "export PATH=$HOME/.local/bin:$PATH; "
        "command -v chezmoi >/dev/null || sh -c \"$(curl -fsLS get.chezmoi.io)\" -- -b ~/.local/bin; "
        f"chezmoi init --apply {shlex.quote(repo)}"
    )
    ui.step(f"Dotfiles: {repo}")
    incus.run("exec", name, "--", "su", "-", user, "-c", script, capture=False)


def cmd_list(args) -> None:
    """Instances petribox made (dishes, and bases with --bases)."""
    rows = []
    for inst in json.loads(incus.run("list", "--format", "json").stdout or "[]"):
        conf = inst.get("config") or {}
        if USER_KEY not in conf:
            continue
        is_base = inst["name"].startswith(recipes.BASE_PREFIX)
        if is_base and not args.bases:
            continue
        recipe = conf.get(RECIPE_KEY) or (inst["name"].removeprefix(recipes.BASE_PREFIX) if is_base else "?")
        kind = "vm" if inst.get("type") == "virtual-machine" else "container"
        notes = ", ".join(n for n, on in (("base", is_base), ("ephemeral", inst.get("ephemeral"))) if on)
        rows.append((inst["name"], recipe, kind, ui.state(inst["status"]),
                     ipv4(inst) or "-", notes))
    if not rows:
        ui.warn("No dishes")
        ui.hint("Make one", "petribox new NAME --from RECIPE")
        return
    ui.table([("Name", "cyan"), ("Recipe", ""), ("Type", ""), ("State", ""), ("IPv4", "dim"), ("", "yellow")],
             rows, title="Petribox dishes")


def cmd_mount(args) -> None:
    src = Path(args.source).expanduser().resolve()
    if not src.is_dir():
        fail(f"no such directory: {src}")
    mount_dir(args.name, dish_user(args.name), src, args.dest, args.device)


def mount_dir(name: str, user: str, src: Path, dest: str | None = None,
              device: str | None = None) -> None:
    """Share a host directory into a dish (an Incus disk device)."""
    if not dest:
        home = incus.run("exec", name, "--", "getent", "passwd", user).stdout.split(":")[5]
        dest = f"{home}/{src.name}"
    device = device or re.sub(r"[^A-Za-z0-9-]", "-", src.name).strip("-") or "share"
    disk = ["config", "device", "add", name, device, "disk", f"source={src}", f"path={dest}"]
    if json.loads(incus.run("query", f"/1.0/instances/{name}").stdout).get("type") == "container":
        disk.append("shift=true")  # map host ownership onto the container's users
    incus.run(*disk)
    # In a running VM the agent mounts it a few seconds later; wait for that.
    with ui.spinner(f"Mounting {dest}..."):
        for _ in range(30):
            if incus.run("exec", name, "--", "mountpoint", "-q", dest, check=False).returncode == 0:
                break
            time.sleep(1)
        else:
            ui.warn(f"{dest} is not mounted yet; it will be after a restart")
    ui.ok(f"{src} -> {name}:{dest}")
    ui.hint("Unmount", f"incus config device remove {name} {device}")


def cmd_export_recipe(args) -> None:
    """A recipe as a Vagrant project or a Lima template, for hosts without Incus."""
    r = recipes.find(args.recipe)
    out = Path(args.output or (f"{r.name}-vagrant" if args.to == "vagrant" else "."))
    for path in export.export(r, args.to, out, force=args.force):
        ui.ok(f"Wrote {path}")
    if not r.vm:
        ui.warn(f"'{r.name}' is a container recipe; the export is a VM")
    if args.to == "vagrant":
        ui.hint("Start", f"cd {out} && vagrant up")
    else:
        ui.hint("Start", f"limactl start {out / (r.name + '.yaml')}")


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
        ui.step(f"Importing {disk.name} as '{args.alias}' (copies the whole disk)")
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
        if not env:
            ui.info(f"{args.name} has no secrets")
            return
        ui.table([("Secret", "cyan"), ("Value", "dim")],
                 [(k, secrets.mask(v)) for k, v in sorted(env.items())], title=f"Secrets in {args.name}")
        return
    for key in args.unset or []:
        env.pop(key, None)
    for key in args.keys:
        env[key] = secrets.resolve(key)
    secrets.write_env(args.name, user, env)
    ui.ok(f"{args.name}: {', '.join(sorted(env)) or 'no secrets'}")


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

    p = sub.add_parser("extras", help="list extras (ssh, mise, node, agents, ...)")
    p.set_defaults(func=cmd_extras)

    p = sub.add_parser("build", help="build a recipe's base instance and its 'clean' snapshot")
    p.add_argument("recipe")
    p.add_argument("--rebuild", action="store_true", help="delete an existing base first")
    p.add_argument("--resume", action="store_true", help="provision an existing base (after a manual step)")
    p.add_argument("--timeout", type=float, default=300, help="seconds to wait for the agent")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("new", help="make a dish (no arguments: answer a few questions)")
    p.add_argument("name", nargs="?")
    src = p.add_argument_group("source (neither: interactive)")
    src.add_argument("--from", dest="recipe", metavar="RECIPE", help="a built recipe")
    src.add_argument("--image", help="any Incus image, set up on the spot, e.g. images:debian/13")
    p.add_argument("--container", action="store_true", help="with --image: a container, not a VM")
    p.add_argument("--ephemeral", action="store_true", help="delete the dish when it stops")
    p.add_argument("--secret", action="append", metavar="KEY", help="hand in a secret (repeatable)")
    p.add_argument("--share", action="append", metavar="DIR", help="mount a host folder (repeatable)")
    p.add_argument("--extra", action="append", metavar="NAME", help="install an extra (repeatable; see `petribox extras`)")
    p.add_argument("--cpus", type=int, help="CPU limit (default: the recipe's)")
    p.add_argument("--memory", help="memory limit, e.g. 8GiB (default: the recipe's)")
    p.add_argument("--disk", help="with --image: root disk size, e.g. 40GiB")
    p.add_argument("--user", help="with --image: the dish user (default: petri)")
    p.add_argument("--no-dotfiles", action="store_true", help="skip [dotfiles] from the config")
    p.set_defaults(func=cmd_new)

    p = sub.add_parser("list", help="list dishes with their recipe and address")
    p.add_argument("--bases", action="store_true", help="include the pb-* base instances")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("mount", help="share a host directory into a dish")
    p.add_argument("name")
    p.add_argument("source", help="host directory")
    p.add_argument("dest", nargs="?", help="path in the dish (default: ~user/<dir name>)")
    p.add_argument("--device", help="Incus device name (default: from the dir name)")
    p.set_defaults(func=cmd_mount)

    p = sub.add_parser("export-recipe", help="write a recipe as a Vagrantfile or a Lima template")
    p.add_argument("recipe")
    p.add_argument("--to", choices=["vagrant", "lima"], required=True)
    p.add_argument("-o", "--output", help="directory (default: ./RECIPE-vagrant, or . for Lima)")
    p.add_argument("--force", action="store_true", help="overwrite existing files")
    p.set_defaults(func=cmd_export_recipe)

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
    except (incus.IncusError, recipes.RecipeError, secrets.SecretError, export.ExportError) as exc:
        fail(str(exc))
    except KeyboardInterrupt:
        sys.exit(130)
