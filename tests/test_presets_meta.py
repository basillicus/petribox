"""Unit tests for presets and Incus-backed metadata."""

from unittest import mock

from petribox import meta, presets


def test_preset_names_canonical():
    assert presets.PRESET_NAMES == ["minimal", "dev", "ai-researcher", "agentic"]


def test_package_config_excludes_resources():
    cfg = presets.package_config("dev")
    assert "ram" not in cfg and "cpus" not in cfg and "disk" not in cfg
    assert cfg["mise_packages"] == ["node@24"]


def test_merge_config_unions_and_preserves_order():
    merged = presets.merge_config(
        {"packages": ["vim", "git"], "mise_packages": ["node@24"]},
        {"packages": ["git", "jq"], "pip_packages": ["numpy"]},
    )
    assert merged["packages"] == ["vim", "git", "jq"]  # order preserved, deduped
    assert merged["pip_packages"] == ["numpy"]
    assert merged["mise_packages"] == ["node@24"]


def test_get_preset_is_a_copy():
    p = presets.get_preset("dev")
    p["packages"].append("mutated")
    assert "mutated" not in presets.PRESETS["dev"]["packages"]


def test_set_meta_prefixes_and_skips_none():
    with mock.patch.object(meta.incus, "config_set_many") as m:
        meta.set_meta("lab", preset="dev", agent=None, user="petri")
    m.assert_called_once()
    name, values = m.call_args.args
    assert name == "lab"
    assert values == {"user.petribox.preset": "dev", "user.petribox.user": "petri"}


def test_get_meta_strips_prefix():
    inst = {"config": {"user.petribox.preset": "dev", "user.petribox.user": "petri",
                       "limits.cpu": "2", "image.os": "rocky"}}
    with mock.patch.object(meta.incus, "info", return_value=inst):
        out = meta.get_meta("lab")
    assert out == {"preset": "dev", "user": "petri"}
