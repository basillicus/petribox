"""Opt-in end-to-end tests against a real Incus daemon.

Skipped unless PETRIBOX_E2E=1 and the `incus` CLI is available. Uses a system
container (fast) by default; set PETRIBOX_E2E_VM=1 to exercise the VM path too.
These create and destroy real instances, so they are excluded from CI.

Run: PETRIBOX_E2E=1 pytest -m e2e
"""

import os
import subprocess
import time
import uuid

import pytest

from petribox import incus

pytestmark = pytest.mark.e2e

E2E_ENABLED = os.environ.get("PETRIBOX_E2E") == "1" and incus.available()

skip_unless_e2e = pytest.mark.skipif(
    not E2E_ENABLED, reason="set PETRIBOX_E2E=1 and install incus to run e2e tests"
)

USE_VM = os.environ.get("PETRIBOX_E2E_VM") == "1"


@pytest.fixture
def dish():
    name = f"petri-e2e-{uuid.uuid4().hex[:8]}"
    yield name
    # Teardown: always try to remove.
    incus.delete(name, force=True) if incus.exists(name) else None


@skip_unless_e2e
def test_create_exec_mount_forward_export(dish, tmp_path):
    image = "images:rockylinux/9/cloud" if USE_VM else "images:rockylinux/9"
    incus.init(dish, image, vm=USE_VM, config={"limits.memory": "1024MiB"})
    incus.start(dish)

    # Wait for running + IP.
    for _ in range(90):
        status, ip = incus.state(dish)
        if status == "running" and ip:
            break
        time.sleep(2)
    else:
        pytest.fail("instance never came up")

    # exec
    proc = incus.exec_capture(dish, ["echo", "hello"])
    assert proc.returncode == 0 and "hello" in proc.stdout

    # mount
    share = tmp_path / "share"
    share.mkdir()
    (share / "marker").write_text("ok")
    incus.device_add(dish, "mnt-data", "disk", source=str(share), path="/data")
    time.sleep(3)
    proc = incus.exec_capture(dish, ["cat", "/data/marker"])
    assert "ok" in proc.stdout

    # proxy port-forward device add/remove
    incus.device_add(dish, "pf-9", "proxy",
                     listen="tcp:127.0.0.1:0", connect="tcp:127.0.0.1:9")
    assert "pf-9" in incus.device_show(dish)
    incus.device_remove(dish, "pf-9")

    # export
    out = tmp_path / "dish.tar.gz"
    incus.stop(dish, force=True)
    incus.export(dish, str(out), instance_only=True)
    assert out.exists() and out.stat().st_size > 0
