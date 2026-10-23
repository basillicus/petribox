"""Every error says what to do next; known ones get a specific fix."""

import pytest

from petribox import cli, hints, incus


@pytest.fixture(autouse=True)
def clean():
    hints.reset()
    yield
    hints.reset()


def shown(capsys, error):
    hints.show(error)
    return capsys.readouterr().err


def test_known_error_gets_its_fix_with_the_names_filled_in(capsys):
    hints.context(instance="pb-arch", recipe="arch")
    err = shown(capsys, "The image used by this instance is incompatible with secureboot")
    assert "incus config set pb-arch security.secureboot=false" in err
    assert "incus info --show-log pb-arch" in err  # the general moves follow


def test_unknown_error_still_gets_the_general_moves(capsys):
    hints.context(instance="lab")
    err = shown(capsys, "something nobody has seen before")
    assert "→" not in err
    assert "incus console lab --type=vga" in err and "incus config set lab" in err


def test_failed_provisioning_points_at_resume_and_rebuild(capsys):
    hints.context(instance="pb-webshop", recipe="webshop", phase="provision")
    err = shown(capsys, "`incus exec pb-webshop --env` failed (exit 1)")
    assert "petribox build webshop --resume" in err and "--rebuild" in err


def test_errors_without_an_instance_skip_the_instance_moves(capsys):
    err = shown(capsys, "no recipe 'nope'")
    assert err == ""


def test_cli_errors_end_with_hints(monkeypatch, capsys):
    def run(*args, **kw):
        if args[0] == "init":
            raise incus.IncusError("System doesn't have a functional idmap setup")
        import types
        return types.SimpleNamespace(returncode=0, stdout="", stderr="")
    monkeypatch.setattr(incus, "run", run)
    monkeypatch.setattr(incus, "exists", lambda n: False)
    monkeypatch.setattr(incus, "image_requirements", lambda i, v: {})
    with pytest.raises(SystemExit):
        cli.main(["build", "kali-container"])
    err = capsys.readouterr().err
    assert "Error:" in err and "/etc/subuid" in err and "pb-kali-container" in err
