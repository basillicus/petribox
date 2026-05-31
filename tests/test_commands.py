"""Command dispatch tests: verify commands map to the right incus calls."""

from argparse import Namespace
from unittest import mock

import pytest

from petribox import incus
from petribox.commands import forward, lifecycle, mounts


@pytest.fixture
def no_sleep():
    with mock.patch("petribox.commands._common.time.sleep"):
        yield


def test_create_resolves_preset_resources_and_injects_cloudinit(no_sleep):
    captured = []

    def fake_run(args, **kw):
        captured.append(list(args))
        import types
        cp = types.SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[:1] == ["info"]:
            cp.returncode = 1
        elif args[:1] == ["list"]:
            cp.stdout = "[]"
        return cp

    args = Namespace(name="lab", container=False, ram=None, cpus=None, disk=None,
                     user="petri", ssh_key=None, password=None, image=None,
                     dotfiles=None, mounts=["~/data:/data"], config=None,
                     shell="bash", preset="dev", agent=None, verbose=False, tui=False)
    with mock.patch.object(incus, "_run", side_effect=fake_run), \
         mock.patch("petribox.commands._common.time.time", side_effect=[0, 1000, 2000]):
        lifecycle.cmd_create(args)

    init = next(c for c in captured if c[:1] == ["init"])
    joined = " ".join(init)
    assert "--vm" in init
    assert "limits.cpu=2" in joined and "limits.memory=4096MiB" in joined  # dev preset
    assert "root,size=25GiB" in init                                       # dev preset disk
    assert "cloud-init.user-data=#cloud-config" in joined
    assert "cloud-init.network-config=" in joined and "dhcp4: true" in joined
    assert "user.petribox.preset=dev" in joined and "user.petribox.user=petri" in joined
    # VM gets the agent config drive (Rocky requires cdrom_agent)
    assert ["config", "device", "add", "lab", "agent", "disk", "source=agent:config"] in captured
    # mount attached as a disk device before start
    mount_dev = next(c for c in captured if c[:5] == ["config", "device", "add", "lab", "mnt-data"])
    assert "disk" in mount_dev and "path=/data" in " ".join(mount_dev)
    assert ["start", "lab"] in captured


def test_create_container_has_no_vm_flag(no_sleep):
    captured = []

    def fake_run(args, **kw):
        captured.append(list(args))
        import types
        cp = types.SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[:1] == ["info"]:
            cp.returncode = 1
        elif args[:1] == ["list"]:
            cp.stdout = "[]"
        return cp

    args = Namespace(name="c1", container=True, ram=1024, cpus=1, disk=10, user="petri",
                     ssh_key=None, password=None, image=None, dotfiles=None, mounts=None,
                     config=None, shell="bash", preset=None, agent=None, verbose=False, tui=False)
    with mock.patch.object(incus, "_run", side_effect=fake_run), \
         mock.patch("petribox.commands._common.time.time", side_effect=[0, 1000, 2000]):
        lifecycle.cmd_create(args)

    init = next(c for c in captured if c[:1] == ["init"])
    assert "--vm" not in init
    assert "limits.memory=1024MiB" in " ".join(init)
    # containers do not need the agent config drive
    assert not any(c[:6] == ["config", "device", "add", "c1", "agent", "disk"] for c in captured)


def test_create_rejects_existing():
    with mock.patch.object(incus, "exists", return_value=True), \
         mock.patch.object(incus, "available", return_value=True):
        args = Namespace(name="dup", container=False, ram=None, cpus=None, disk=None,
                         user="petri", ssh_key=None, password=None, image=None, dotfiles=None,
                         mounts=None, config=None, shell="bash", preset=None, agent=None,
                         verbose=False, tui=False)
        with pytest.raises(SystemExit):
            lifecycle.cmd_create(args)


def test_mount_adds_named_disk_device(tmp_path):
    share = tmp_path / "data"
    share.mkdir()
    with mock.patch.object(incus, "info", return_value={"name": "lab"}), \
         mock.patch.object(incus, "device_add") as add:
        args = Namespace(name="lab", host_path=str(share), vm_path="/data")
        mounts.cmd_mount(args)
    add.assert_called_once()
    a, kw = add.call_args.args, add.call_args.kwargs
    assert a[0] == "lab" and a[1] == "mnt-data" and a[2] == "disk"
    assert kw["path"] == "/data" and kw["source"] == str(share)


def test_port_forward_adds_proxy_device():
    with mock.patch.object(incus, "info", return_value={"name": "lab"}), \
         mock.patch.object(incus, "state", return_value=("running", "10.0.0.1")), \
         mock.patch.object(incus, "device_show", return_value={}), \
         mock.patch.object(incus, "device_add") as add:
        args = Namespace(name="lab", port=8888, local_port=None)
        forward.cmd_port_forward(args)
    a, kw = add.call_args.args, add.call_args.kwargs
    assert a[1] == "pf-8888" and a[2] == "proxy"
    assert kw["listen"] == "tcp:127.0.0.1:8888"
    assert kw["connect"] == "tcp:127.0.0.1:8888"


def test_delete_force_skips_prompt():
    with mock.patch.object(incus, "info", return_value={"name": "lab"}), \
         mock.patch.object(incus, "delete") as d:
        lifecycle.cmd_delete(Namespace(name="lab", force=True))
    d.assert_called_once_with("lab", force=True)
