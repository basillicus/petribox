"""Unit tests for the incus CLI wrapper (mocking subprocess)."""

import types
from unittest import mock

import pytest

from petribox import incus


def _proc(returncode=0, stdout="", stderr=""):
    return types.SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def test_run_raises_incuserror_with_stderr():
    with mock.patch("petribox.incus.subprocess.run",
                    return_value=_proc(returncode=1, stderr="boom")):
        with pytest.raises(incus.IncusError, match="boom"):
            incus._run(["info", "x"])


def test_run_missing_binary_message():
    with mock.patch("petribox.incus.subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(incus.IncusError, match="initial-setup"):
            incus._run(["list"])


def test_device_add_builds_command():
    with mock.patch.object(incus, "_run", return_value=_proc()) as m:
        incus.device_add("lab", "share", "disk", source="/h", path="/data")
    assert m.call_args.args[0] == [
        "config", "device", "add", "lab", "share", "disk", "source=/h", "path=/data",
    ]


def test_init_includes_vm_and_config_and_device():
    with mock.patch.object(incus, "_run", return_value=_proc()) as m:
        incus.init("lab", "img", vm=True,
                   config={"limits.cpu": "2", "skip": None},
                   device_overrides=["root,size=20GiB"])
    args = m.call_args.args[0]
    assert args[:3] == ["init", "img", "lab"]
    assert "--vm" in args
    assert "limits.cpu=2" in args
    assert "skip=None" not in " ".join(args)  # None values skipped
    assert "root,size=20GiB" in args


def test_first_ipv4_picks_global_inet():
    inst = {"state": {"network": {
        "lo": {"addresses": [{"family": "inet", "scope": "local", "address": "127.0.0.1"}]},
        "eth0": {"addresses": [
            {"family": "inet6", "scope": "global", "address": "fe80::1"},
            {"family": "inet", "scope": "global", "address": "10.0.0.5"},
        ]},
    }}}
    assert incus.first_ipv4(inst) == "10.0.0.5"


def test_state_parses_status_and_ip():
    inst = {"name": "lab", "status": "Running",
            "state": {"network": {"eth0": {"addresses": [
                {"family": "inet", "scope": "global", "address": "10.0.0.9"}]}}}}
    with mock.patch.object(incus, "info", return_value=inst):
        assert incus.state("lab") == ("running", "10.0.0.9")


def test_info_missing_returns_none():
    with mock.patch.object(incus, "_run", return_value=_proc(returncode=1)):
        assert incus.info("nope") is None
