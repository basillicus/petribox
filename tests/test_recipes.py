"""Recipe loading, overrides and the assembled provisioning script."""

import pytest

from petribox import recipes


def _write(root, name, toml, provision=None):
    d = root / "petribox" / "recipes" / name
    d.mkdir(parents=True)
    (d / "recipe.toml").write_text(toml)
    if provision is not None:
        (d / "provision.sh").write_text(provision)
    return d


def test_builtin_recipes_load():
    names = {r.name for r in recipes.all_recipes()}
    assert {"rocky", "debian", "arch"} <= names
    for r in recipes.all_recipes():
        assert r.image and r.base == "pb-" + r.name


def test_user_recipe_overrides_builtin(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _write(tmp_path, "rocky", 'image = "images:rockylinux/10"\ncpus = 8\n', "echo mine\n")
    r = recipes.find("rocky")
    assert (r.image, r.cpus, r.vm) == ("images:rockylinux/10", 8, True)
    script = r.script()
    assert script.index("PB_USER") < script.index("echo mine")  # _common.sh first


def test_unknown_key_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    _write(tmp_path, "bad", 'image = "x"\nram = 4096\n')
    with pytest.raises(recipes.RecipeError, match="ram"):
        recipes.find("bad")


def test_missing_recipe(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    with pytest.raises(recipes.RecipeError):
        recipes.find("nope")
