"""Secret resolution on the host and env-file handling in the dish."""

import types
from argparse import Namespace
from unittest import mock

import pytest

from petribox import incus, secrets
from petribox.commands import lifecycle


def test_env_roundtrip_survives_shell_metacharacters():
    env = {"A": "plain", "B": "it's $HOME `id` \"q\"", "C": ""}
    assert secrets.parse_env(secrets.render_env(env)) == env


def test_configured_sources_from_xdg_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = tmp_path / "petribox" / "config.toml"
    cfg.parent.mkdir()
    cfg.write_text('[secrets]\nOPENAI_API_KEY = { cmd = "printf sk-from-store" }\n')
    assert secrets.configured_sources() == {"OPENAI_API_KEY": "printf sk-from-store"}
    assert secrets.resolve("OPENAI_API_KEY") == "sk-from-store"


def test_resolve_without_source_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    with pytest.raises(secrets.SecretError):
        secrets.resolve("MISSING_KEY")


def test_failing_command_is_an_error():
    with pytest.raises(secrets.SecretError):
        secrets.run_source("false")


def test_mask_hides_all_but_tail():
    assert secrets.mask("sk-abcdefghijkl") == "****ijkl"
    assert secrets.mask("short") == "****"


def test_create_pushes_env_over_stdin_not_argv(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = tmp_path / "petribox" / "config.toml"
    cfg.parent.mkdir()
    cfg.write_text('[secrets]\nANTHROPIC_API_KEY = { cmd = "printf sk-ant-secret" }\n')
    calls = []

    def fake_run(args, text_input=None, **kw):
        calls.append((list(args), text_input))
        cp = types.SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[:1] == ["info"]:
            cp.returncode = 1
        elif args[:1] == ["list"]:
            cp.stdout = "[]"
        return cp

    args = Namespace(name="lab", container=True, ram=1024, cpus=1, disk=10, user="petri",
                     ssh_key=None, password=None, image=None, dotfiles=None, mounts=None,
                     config=None, shell="bash", preset=None, agent=None, verbose=False,
                     tui=False, env=["OPENAI_API_KEY=sk-literal"], secret=["ANTHROPIC_API_KEY"])
    with mock.patch.object(incus, "_run", side_effect=fake_run), \
         mock.patch("petribox.commands._common.time.sleep"), \
         mock.patch.object(secrets, "wait_for_user", return_value=True), \
         mock.patch("petribox.commands._common.time.time", side_effect=[0, 1000, 2000]):
        lifecycle.cmd_create(args)

    for argv, _ in calls:
        joined = " ".join(argv)
        assert "sk-literal" not in joined and "sk-ant-secret" not in joined
    pushed = [stdin for _, stdin in calls if stdin]
    assert len(pushed) == 1
    assert secrets.parse_env(pushed[0]) == {
        "OPENAI_API_KEY": "sk-literal", "ANTHROPIC_API_KEY": "sk-ant-secret"}
    # names (not values) recorded so export can warn
    assert any("user.petribox.env_keys=ANTHROPIC_API_KEY,OPENAI_API_KEY" in a for c, _ in calls for a in c)
