"""petribox command line. Everything not here is plain `incus` (see README)."""

from __future__ import annotations

import argparse
import io
import json
import os
import platform
import re
import shlex
import sys
import tarfile
import tempfile
import time
from pathlib import Path

from rich.prompt import Confirm

from . import __version__, bootstrap, export, hints, incus, recipes, secrets, ui, wizard
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
    if incus.exists(name):
        # Never clean up an instance this call did not make.
        raise incus.IncusError(f"'{name}' already exists")
    try:
        incus.run(*init, capture="stderr")  # shows the image download progress
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
    hints.context(instance=r.base, recipe=r.name, phase="create")
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
    if r.vm and r.agent_via_ssh:
        with ui.spinner(f"Installing the Incus agent in {r.base} over SSH (one-off key)..."):
            bootstrap.install_agent(r.base, r.user, timeout=timeout)
        ui.ok(f"{r.base}: Incus agent installed; one-off key and sudo rule removed")
    else:
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
    hints.context(phase="provision")
    run_script(r.base, r.user, r.script())
    hints.context(phase="snapshot")

    ui.step(f"{r.base}: snapshot 'clean'")
    # Some guests (Kali's desktop image) ignore the ACPI shutdown request, so
    # flush the disks first and force the stop if the clean one times out.
    with ui.spinner(f"Stopping {r.base}..."):
        stopped = incus.stop(r.base)
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
    hints.context(instance=args.name, recipe=args.recipe or "", phase="create")
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
        hints.context(instance=args.name, phase="create")
        if extras:
            ui.step(f"{args.name}: extras {', '.join(extras)}")
            hints.context(phase="provision")
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
        ssh_hint(args.name, user)
    ui.hint("Share", f"petribox mount {args.name} ./dir")
    ui.hint("Delete", f"petribox delete {args.name}")


def ssh_hint(name: str, user: str) -> None:
    addr = ipv4(json.loads(incus.run("query", f"/1.0/instances/{name}/state").stdout))
    ui.hint("SSH", f"ssh {user}@{addr or '<ip from petribox list>'}")


def cmd_add(args) -> None:
    """Install extras into an existing dish. Only that dish gets them: for
    every future dish, put them in the recipe and rebuild its base."""
    name = args.name
    hints.context(instance=name, phase="create")
    if name.startswith(recipes.BASE_PREFIX):
        recipe = name.removeprefix(recipes.BASE_PREFIX)
        fail(f"'{name}' is a base: add the extras to recipe '{recipe}' (extras = [...]), "
             f"then petribox build {recipe} --resume")
    if not incus.exists(name):
        fail(f"no such dish: {name}")
    user = dish_user(name)
    recipes.resolve_extras(args.extras)  # unknown names fail before anything runs
    state = json.loads(incus.run("query", f"/1.0/instances/{name}/state").stdout or "{}")
    if state.get("status") != "Running":
        incus.run("start", name)
    with ui.spinner(f"Waiting for {name}..."):
        incus.wait_for_agent(name)
    ui.step(f"{name}: extras {', '.join(args.extras)}")
    hints.context(phase="provision")
    run_script(name, user, recipes.provision_script(args.extras))
    ui.ok(f"Installed into {name}: {', '.join(args.extras)}")
    if "ssh" in [e.name for e, _ in recipes.resolve_extras(args.extras)]:
        ssh_hint(name, user)
    recipe = incus.config_get(name, RECIPE_KEY)
    if recipe and not recipe.count(":"):
        ui.info(f"Only this dish has them. For every new dish: add them to recipe '{recipe}' "
                f"and run petribox build {recipe} --resume")


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
    hints.context(phase="provision")
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
        notes = ", ".join(n for n, on in ((kind, True), ("base", is_base),
                                          ("ephemeral", inst.get("ephemeral"))) if on)
        cpus, memory, disk = resources(inst)
        rows.append((inst["name"], recipe, ui.state(inst["status"]),
                     ipv4(inst) or "-", cpus, memory, disk, notes))
    if not rows:
        ui.warn("No dishes")
        ui.hint("Make one", "petribox new NAME --from RECIPE")
        return
    ui.table([("Name", "cyan"), ("Recipe", ""), ("State", ""), ("IPv4", "dim", True),
              ("CPUs", ""), ("Mem GiB", "", True), ("Disk GiB", "", True), ("Notes", "yellow")],
             rows, title="Petribox dishes")
    ui.info("Memory and disk in GiB: used / limit, while running. Disk is what the dish sees; "
            "on the host, copies share the base's unchanged blocks. Live: incus top")


def size(text: str) -> float:
    """'4GiB', '512MiB', '20GB' -> bytes (0 if unreadable)."""
    m = re.fullmatch(r"\s*([\d.]+)\s*([KMGT]?)(i?)B?\s*", text or "")
    if not m:
        return 0
    return float(m.group(1)) * (1024 if m.group(3) or not m.group(2) else 1000) ** "_KMGT".index(m.group(2) or "_")


def gib(n: float) -> str:
    return f"{n / 2**30:.1f}".removesuffix(".0")


def resources(inst: dict) -> tuple[str, str, str]:
    """CPUs, memory and disk of one `incus list` entry, as table cells."""
    conf, state = inst.get("expanded_config") or {}, inst.get("state") or {}
    running = inst.get("status") == "Running"
    cpus = conf.get("limits.cpu", "all")
    mem_limit = size(conf.get("limits.memory", ""))
    mem_used = (state.get("memory") or {}).get("usage", 0) if running else 0
    root = (inst.get("expanded_devices") or {}).get("root") or {}
    disk_limit = size(root.get("size", ""))
    disk_used = ((state.get("disk") or {}).get("root") or {}).get("usage", -1) if running else -1
    if disk_used < 0 and running and inst.get("type") == "virtual-machine":
        # Incus cannot see into a VM's disk on some storage drivers (btrfs): ask the guest.
        out = incus.run("exec", inst["name"], "--", "df", "-B1", "--output=used", "/", check=False).stdout
        disk_used = int(out.split()[-1]) if out.split() and out.split()[-1].isdigit() else -1

    def cell(used: float, limit: float) -> str:
        if used > 0:
            shown = gib(used) if used >= 2**30 / 10 else "<0.1"
            return f"{shown} / {gib(limit)}" if limit else shown
        return gib(limit) if limit else "-"
    return cpus, cell(mem_used, mem_limit), cell(max(disk_used, 0), disk_limit)


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
    # The host's architecture: Incus only runs images built for it.
    arch = {"amd64": "x86_64", "arm64": "aarch64"}.get(platform.machine().lower(), platform.machine())
    metadata = (
        f"architecture: {arch}\n"
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


def instance_status(name: str) -> str:
    if not incus.exists(name):
        fail(f"no such instance: {name}")
    return json.loads(incus.run("query", f"/1.0/instances/{name}").stdout or "{}").get("status", "")


def cmd_start(args) -> None:
    """`incus start NAME...`, skipping the ones already running."""
    for name in args.names:
        if instance_status(name) == "Running":
            ui.info(f"{name} is already running")
            continue
        ui.info(f"incus start {name}")
        incus.run("start", name)
        ui.ok(f"{name} started")


def cmd_stop(args) -> None:
    """`incus stop NAME...`: like `incus stop --timeout 60`, then `--force` if
    the guest ignores the request (disks are synced first)."""
    for name in args.names:
        if instance_status(name) != "Running":
            ui.info(f"{name} is not running")
            continue
        ephemeral = incus.run("query", f"/1.0/instances/{name}").stdout.find('"ephemeral":true') >= 0
        if args.force:
            ui.info(f"incus stop --force {name}")
            incus.run("stop", "--force", name)
        else:
            ui.info(f"incus stop --timeout 60 {name}")
            if not incus.stop(name):
                ui.warn(f"{name} ignored the shutdown request; stopped with --force")
        ui.ok(f"{name} stopped" + (" and deleted (ephemeral)" if ephemeral else ""))


def cmd_delete(args) -> None:
    """`incus delete --force NAME...`: stops and removes, with everything in it."""
    for name in args.names:
        instance_status(name)  # fails on a name that does not exist
    if not args.yes:
        if not sys.stdin.isatty():
            fail("deleting cannot be undone; pass --yes to confirm")
        if not Confirm.ask(f"Delete {', '.join(args.names)} and everything in "
                           f"{'them' if len(args.names) > 1 else 'it'}?", default=False):
            ui.warn("Cancelled")
            return
    for name in args.names:
        ui.info(f"incus delete --force {name}")
        incus.run("delete", "--force", name)
        ui.ok(f"{name} deleted")
        if name.startswith(recipes.BASE_PREFIX):
            ui.info(f"The next petribox new --from {name.removeprefix(recipes.BASE_PREFIX)} builds it again.")


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
    p.add_argument("--resume", action="store_true", help="run the recipe's script again on the existing base, then re-snapshot")
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

    p = sub.add_parser("add", help="install extras into an existing dish")
    p.add_argument("name")
    p.add_argument("extras", nargs="+", metavar="EXTRA", help="NAME or NAME@VERSION (see `petribox extras`)")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("start", help="start dishes (incus start NAME)")
    p.add_argument("names", nargs="+", metavar="NAME")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("stop", help="stop dishes; ephemeral ones are deleted (incus stop --timeout 60 NAME, "
                                    "then --force if the guest ignores it)")
    p.add_argument("names", nargs="+", metavar="NAME")
    p.add_argument("-f", "--force", action="store_true", help="do not wait for a clean shutdown (incus stop --force)")
    p.set_defaults(func=cmd_stop)

    p = sub.add_parser("delete", help="delete dishes or bases, after a question (incus delete --force NAME)")
    p.add_argument("names", nargs="+", metavar="NAME")
    p.add_argument("-y", "--yes", action="store_true", help="do not ask")
    p.set_defaults(func=cmd_delete)

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
    # `petribox CMD --help` shows the same line as `petribox --help`.
    for action in sub._choices_actions:
        sub.choices[action.dest].description = action.help
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    hints.reset()
    try:
        args.func(args)
    except (incus.IncusError, recipes.RecipeError, secrets.SecretError, export.ExportError) as exc:
        fail(str(exc))
    except KeyboardInterrupt:
        sys.exit(130)
