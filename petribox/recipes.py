"""Recipes: an Incus image plus a provisioning script.

A recipe is a directory with `recipe.toml` and, optionally, `provision.sh`.
Built-in recipes ship in petribox/recipes/; your own go in
$XDG_CONFIG_HOME/petribox/recipes/<name>/ and win over a built-in of the same
name. Provisioning runs as root inside the instance: `_common.sh` first
(network wait, package helpers, the dish user), then the recipe's extras,
then its own script.

Extras are small shell scripts that install one thing (ssh, mise, an agent)
and can be picked by name, in a recipe or for one dish. Built-ins are in
petribox/recipes/_extras/, yours in $XDG_CONFIG_HOME/petribox/extras/. A
script's first lines may say what it is and what it needs first:

    # description: Node.js LTS (through mise)
    # needs: mise

Pin a version with NAME@VERSION (`node@24.22.1`); the script gets it as
$VERSION, and an extra whose script never uses $VERSION cannot be pinned.
"""

from __future__ import annotations

import json
import os
import shlex
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

BUILTIN = Path(__file__).parent / "recipes"
BUILTIN_EXTRAS = BUILTIN / "_extras"
BASE_PREFIX = "pb-"


class RecipeError(RuntimeError):
    """A recipe is missing or malformed."""


@dataclass
class Recipe:
    name: str
    dir: Path
    image: str
    vm: bool = True
    cpus: int = 2
    memory: str = "4GiB"
    disk: str = "20GiB"
    user: str = "petri"
    description: str = ""
    config: dict = field(default_factory=dict)  # extra instance config, e.g. security.secureboot
    extras: list = field(default_factory=list)  # e.g. ["ssh", "node@24.22.1"]
    vagrant_box: str = ""     # for `petribox export-recipe`, when the image has no known box
    lima_template: str = ""   # likewise for Lima

    @property
    def base(self) -> str:
        """Name of the base instance that holds the `clean` snapshot."""
        return BASE_PREFIX + self.name

    def script(self) -> str:
        """The full provisioning script: _common.sh, extras, the recipe's own."""
        own = self.dir / "provision.sh"
        return provision_script(self.extras, own.read_text() if own.exists() else "")


@dataclass
class Extra:
    name: str
    path: Path
    description: str = ""
    needs: list = field(default_factory=list)


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "petribox"


def user_dir() -> Path:
    return config_dir() / "recipes"


def all_extras() -> dict[str, Extra]:
    found: dict[str, Extra] = {}
    for root in (BUILTIN_EXTRAS, config_dir() / "extras"):  # yours override built-ins
        for path in sorted(root.glob("*.sh")) if root.is_dir() else []:
            extra = Extra(path.stem, path)
            for line in path.read_text().splitlines():
                if not line.startswith("#"):
                    break
                key, _, value = line.lstrip("# ").partition(":")
                if key == "description":
                    extra.description = value.strip()
                elif key == "needs":
                    extra.needs = value.split()
            found[extra.name] = extra
    return dict(sorted(found.items()))


def resolve_extras(names: list[str]) -> list[tuple[Extra, str]]:
    """The named extras plus what they need, dependencies first, no repeats,
    each with its pinned version ("" for latest)."""
    known, order, seen = all_extras(), [], set()
    versions: dict[str, str] = {}
    for spec in names:
        name, _, version = spec.partition("@")
        if versions.get(name, version) != version:
            raise RecipeError(f"extra '{name}' is pinned twice: {versions[name]} and {version}")
        if version or name not in versions:
            versions[name] = version

    def visit(name: str, chain: tuple) -> None:
        if name in chain:
            raise RecipeError(f"extras need each other in a loop: {' -> '.join(chain + (name,))}")
        if name not in known:
            raise RecipeError(f"no extra '{name}' (see `petribox extras`)")
        if name in seen:
            return
        for dep in known[name].needs:
            visit(dep, chain + (name,))
        version = versions.get(name, "")
        if version and "VERSION" not in known[name].path.read_text():
            raise RecipeError(f"extra '{name}' cannot be pinned (its script ignores $VERSION)")
        seen.add(name)
        order.append((known[name], version))

    for spec in names:
        visit(spec.partition("@")[0], ())
    return order


def provision_script(extras: list[str], own: str = "") -> str:
    parts = [(BUILTIN / "_common.sh").read_text()]
    for extra, version in resolve_extras(extras):
        label = extra.name + (f"@{version}" if version else "")
        parts.append(f'echo "== extra: {label}"\nVERSION={shlex.quote(version)}\n{extra.path.read_text()}')
    if own:
        parts.append(own)
    return "\n".join(parts)


def save(r: Recipe) -> Path:
    """Write a recipe to the user dir (for the wizard's "save as recipe")."""
    path = user_dir() / r.name
    path.mkdir(parents=True, exist_ok=True)
    q = json.dumps  # a JSON string or list of strings is valid TOML
    lines = [f"description = {q(r.description)}", f"image = {q(r.image)}",
             f"vm = {'true' if r.vm else 'false'}", f"cpus = {r.cpus}",
             f"memory = {q(r.memory)}", f"disk = {q(r.disk)}", f"user = {q(r.user)}",
             f"extras = {q(r.extras)}"]
    lines += [f"vagrant_box = {q(r.vagrant_box)}"] if r.vagrant_box else []
    lines += [f"lima_template = {q(r.lima_template)}"] if r.lima_template else []
    (path / "recipe.toml").write_text("\n".join(lines) + "\n")
    return path


def load(path: Path) -> Recipe:
    try:
        data = tomllib.loads((path / "recipe.toml").read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise RecipeError(f"{path}/recipe.toml: {exc}") from exc
    if "image" not in data:
        raise RecipeError(f"{path}/recipe.toml: `image` is required")
    known = Recipe.__dataclass_fields__.keys() - {"name", "dir"}
    unknown = set(data) - known
    if unknown:
        raise RecipeError(f"{path}/recipe.toml: unknown keys {sorted(unknown)}")
    return Recipe(name=path.name, dir=path, **data)


def find(name: str) -> Recipe:
    for root in (user_dir(), BUILTIN):
        if (root / name / "recipe.toml").exists():
            return load(root / name)
    raise RecipeError(f"no recipe '{name}' (see `petribox recipes`)")


def all_recipes() -> list[Recipe]:
    found: dict[str, Recipe] = {}
    for root in (BUILTIN, user_dir()):  # user recipes override built-ins
        if root.is_dir():
            for path in sorted(root.iterdir()):
                if (path / "recipe.toml").exists():
                    found[path.name] = load(path)
    return [found[k] for k in sorted(found)]
