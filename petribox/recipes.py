"""Recipes: an Incus image plus a provisioning script.

A recipe is a directory with `recipe.toml` and, optionally, `provision.sh`.
Built-in recipes ship in petribox/recipes/; your own go in
$XDG_CONFIG_HOME/petribox/recipes/<name>/ and win over a built-in of the same
name. Provisioning runs as root inside the instance: `_common.sh` first
(network wait, package helpers, the dish user), then the recipe's script.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

BUILTIN = Path(__file__).parent / "recipes"
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

    @property
    def base(self) -> str:
        """Name of the base instance that holds the `clean` snapshot."""
        return BASE_PREFIX + self.name

    def script(self) -> str:
        """The full provisioning script: _common.sh, then the recipe's own."""
        parts = [(BUILTIN / "_common.sh").read_text()]
        own = self.dir / "provision.sh"
        if own.exists():
            parts.append(own.read_text())
        return "\n".join(parts)


def user_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "petribox" / "recipes"


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
