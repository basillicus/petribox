"""The firmware credential that lets petribox in once to install the agent."""

import base64

from petribox import bootstrap


def test_credential_writes_the_key_and_sudo_rule():
    arg = bootstrap.credential("omarchy", "ssh-ed25519 AAAA petribox-bootstrap")
    assert arg.startswith("-smbios type=11,value=io.systemd.credential.binary:tmpfiles.extra=")
    lines = base64.b64decode(arg.split("tmpfiles.extra=", 1)[1]).decode().splitlines()
    assert lines[0] == "d /home/omarchy/.ssh 0700 omarchy omarchy -"
    assert lines[1].endswith("- ssh-ed25519 AAAA petribox-bootstrap")
    assert lines[2].startswith(f"f+ {bootstrap.SUDOERS} 0440 root root - omarchy ALL=(ALL) NOPASSWD:ALL")
    assert "," not in arg.split("tmpfiles.extra=")[1]  # qemu splits -smbios on commas
