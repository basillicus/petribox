"""Secret resolution on the host and env-file handling in the dish."""

import pytest

from petribox import secrets


def test_env_roundtrip_survives_shell_metacharacters():
    env = {"A": "plain", "B": "it's $HOME `id` \"q\"", "C": ""}
    assert secrets.parse_env(secrets.render_env(env)) == env


def test_resolve_from_config(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    cfg = tmp_path / "petribox" / "config.toml"
    cfg.parent.mkdir()
    cfg.write_text('[secrets]\nOPENAI_API_KEY = { cmd = "printf sk-from-store" }\n')
    assert secrets.resolve("OPENAI_API_KEY") == "sk-from-store"


def test_no_source_and_no_terminal_fails(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    with pytest.raises(secrets.SecretError):
        secrets.resolve("MISSING_KEY")


def test_invalid_name_and_failing_command():
    with pytest.raises(secrets.SecretError):
        secrets.resolve("NOT-A-NAME")
    with pytest.raises(secrets.SecretError):
        secrets.run_source("false")


def test_write_env_sends_values_on_stdin_only(monkeypatch):
    calls = []
    monkeypatch.setattr(secrets.incus, "run",
                        lambda *a, **kw: calls.append((a, kw)) or type("P", (), {"returncode": 0})())
    secrets.write_env("lab", "petri", {"TOKEN": "s3cret-value"})
    (args, kw), = calls
    assert "s3cret-value" not in " ".join(args)
    assert "s3cret-value" in kw["input"]


def test_mask():
    assert secrets.mask("sk-abcdefghijkl") == "****ijkl"
    assert secrets.mask("short") == "****"
