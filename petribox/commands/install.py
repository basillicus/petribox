"""Install agents or mise packages into a running dish (via incus exec)."""

from __future__ import annotations

from .. import incus, meta
from ._common import console, get_instance_or_exit, require_running


def _exec_root(name: str, script: str) -> "tuple[int, str]":
    """Run a shell script in the dish as root; return (rc, combined output)."""
    proc = incus.exec_capture(name, ["sh", "-c", script])
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _exec_user(name: str, user: str, script: str) -> "tuple[int, str]":
    """Run a shell script as the dish user (login env), so files are user-owned."""
    proc = incus.exec_capture(name, ["su", "-", user, "-c", script])
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def cmd_install(args):
    """Install an AI agent and/or mise packages into an existing dish."""
    get_instance_or_exit(args.name)
    require_running(args.name)
    user = meta.get_meta(args.name).get("user", "petri")

    did_something = False

    if getattr(args, "agent", None):
        from ..agents import get_agent_config

        agent = get_agent_config(args.agent)
        console.print(f"[green]Installing agent: {agent['name']}[/green]")
        did_something = True

        if agent.get("packages"):  # system packages need root
            rc, out = _exec_root(args.name, "dnf install -y " + " ".join(agent["packages"]))
            if rc != 0:
                console.print(f"[yellow]Package install warning: {out.strip()[:300]}[/yellow]")

        for pkg in agent.get("mise_packages", []):
            console.print(f"[dim]mise use -g {pkg}[/dim]")
            rc, out = _exec_user(args.name, user, f"~/.local/bin/mise use -g {pkg}")
            if rc != 0:
                console.print(f"[yellow]mise {pkg} warning: {out.strip()[:300]}[/yellow]")

        if agent.get("install_script"):
            console.print("[dim]Running agent installer...[/dim]")
            rc, out = _exec_user(args.name, user, agent["install_script"])
            if rc != 0:
                console.print(f"[red]Agent install failed: {out.strip()[:500]}[/red]")
                raise SystemExit(1)
            console.print(f"[green]✓ {agent['name']} installed[/green]")
            if agent.get("setup_command"):
                console.print(f"[cyan]Next:[/cyan] connect and run [green]{agent['setup_command']}[/green]")
                if agent.get("setup_notes"):
                    console.print(f"[dim]{agent['setup_notes']}[/dim]")
        elif agent.get("repo"):
            console.print(f"[dim]No automated installer; clone: {agent['repo']}[/dim]")

    for pkg in getattr(args, "mise_packages", None) or []:
        console.print(f"[dim]mise use -g {pkg}[/dim]")
        rc, out = _exec_user(args.name, user, f"~/.local/bin/mise use -g {pkg}")
        if rc != 0:
            console.print(f"[red]Failed to install {pkg}: {out.strip()[:300]}[/red]")
            raise SystemExit(1)
        console.print(f"[green]✓ {pkg} installed[/green]")
        did_something = True

    if not did_something:
        console.print("[yellow]Nothing to install. Use --agent or --mise-package[/yellow]")
