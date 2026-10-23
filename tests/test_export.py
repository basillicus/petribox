"""export-recipe: the generated files carry the recipe's script and sizes."""

import subprocess
import shutil

import pytest
import yaml

from petribox import export, recipes


def recipe(**kw):
    base = dict(name="webshop", dir=recipes.BUILTIN / "debian", image="images:debian/13",
                cpus=4, memory="8GiB", disk="40GiB", extras=["node@24.22.1"])
    return recipes.Recipe(**{**base, **kw})


def test_vagrant_project(tmp_path):
    paths = export.export(recipe(), "vagrant", tmp_path)
    vagrantfile = (tmp_path / "Vagrantfile").read_text()
    assert 'config.vm.box = "bento/debian-13"' in vagrantfile
    assert "vm.cpus = 4" in vagrantfile and "vm.memory = 8192" in vagrantfile
    script = (tmp_path / "provision.sh").read_text()
    assert script.startswith("#!/bin/bash") and "VERSION=24.22.1" in script
    assert len(paths) == 2


@pytest.mark.skipif(not shutil.which("ruby"), reason="ruby not installed")
def test_vagrantfile_is_valid_ruby(tmp_path):
    export.export(recipe(), "vagrant", tmp_path)
    subprocess.run(["ruby", "-c", str(tmp_path / "Vagrantfile")], check=True, capture_output=True)


def test_lima_template_is_yaml_with_the_script(tmp_path):
    export.export(recipe(), "lima", tmp_path)
    doc = yaml.safe_load((tmp_path / "webshop.yaml").read_text())
    assert doc["base"] == ["template:_images/debian-13"]  # image only: no host mounts
    assert "mounts" not in doc
    assert (doc["cpus"], doc["memory"], doc["disk"]) == (4, "8GiB", "40GiB")
    script = doc["provision"][0]["script"]
    assert doc["provision"][0]["mode"] == "system"
    assert 'export PB_USER="{{.User}}"' in script and "== extra: node@24.22.1" in script


def test_unknown_image_asks_for_an_override(tmp_path):
    with pytest.raises(export.ExportError, match="vagrant_box"):
        export.export(recipe(image="my-local-image"), "vagrant", tmp_path)
    export.export(recipe(image="my-local-image", vagrant_box="acme/box"), "vagrant", tmp_path)


def test_kali_exports_to_vagrant_but_not_lima(tmp_path):
    kali = recipes.find("kali")
    export.export(kali, "vagrant", tmp_path)
    assert "kalilinux/rolling" in (tmp_path / "Vagrantfile").read_text()
    with pytest.raises(export.ExportError, match="lima_template"):
        export.export(kali, "lima", tmp_path)


def test_existing_files_need_force(tmp_path):
    export.export(recipe(), "lima", tmp_path)
    with pytest.raises(export.ExportError, match="--force"):
        export.export(recipe(), "lima", tmp_path)
    export.export(recipe(), "lima", tmp_path, force=True)
