"""Install the Incus agent into an imported VM image that has none, over SSH.

Some images (a distro's own QEMU image) ship sshd but no Incus agent and no
key or password login petribox could use. systemd reads "credentials" from
the VM firmware (SMBIOS type 11) at boot, and `tmpfiles.extra` makes it
write files. So the first boot of a base gets, for this boot only:

- a one-off SSH key in the recipe user's authorized_keys,
- a passwordless sudo rule for that user,

then petribox logs in, installs the agent from Incus's agent drive, and
removes all three (key, rule, firmware entry) before provisioning goes on.
The same trick as Omarchy's own `vm-boot` script. Needs systemd >= 252 and
an sshd that starts by default.
"""

from __future__ import annotations

import base64
import json
import subprocess
import tempfile
import time
from pathlib import Path

from . import incus

SUDOERS = "/etc/sudoers.d/90-petribox-bootstrap"
COMMENT = "petribox-bootstrap"

# As root throughout: the agent drive is readable by root only.
INSTALL = (
    "sudo sh -c 'set -e; d=$(mktemp -d); "
    "mount -o ro /dev/disk/by-label/incus-agent $d 2>/dev/null || mount -t 9p config $d -o ro; "
    "cd $d; ./install.sh; cd /; umount $d; rmdir $d; systemctl start incus-agent'"
)


def credential(user: str, pubkey: str) -> str:
    """The `-smbios` argument: tmpfiles lines that write the key and rule."""
    home = f"/home/{user}"
    lines = (
        f"d {home}/.ssh 0700 {user} {user} -\n"
        f"f+ {home}/.ssh/authorized_keys 0600 {user} {user} - {pubkey}\n"
        f"f+ {SUDOERS} 0440 root root - {user} ALL=(ALL) NOPASSWD:ALL\n"
    )
    b64 = base64.b64encode(lines.encode()).decode()
    return f"-smbios type=11,value=io.systemd.credential.binary:tmpfiles.extra={b64}"


def ipv4(name: str) -> str:
    state = json.loads(incus.run("query", f"/1.0/instances/{name}/state").stdout or "{}")
    for nic, net in (state.get("network") or {}).items():
        for addr in net.get("addresses", []) if nic != "lo" else []:
            if addr.get("family") == "inet":
                return addr["address"]
    return ""


def install_agent(name: str, user: str, timeout: float = 300) -> None:
    """Boot `name` (stopped) with a one-off key, install the agent over SSH,
    and leave it running with the agent up and the key, the sudo rule and the
    firmware entry gone. While the entry is set, systemd writes the key and
    rule again on every boot, and Incus only drops it from a stopped VM."""
    with tempfile.TemporaryDirectory() as tmp:
        key = Path(tmp) / "id_ed25519"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", COMMENT,
                        "-f", str(key)], check=True)
        pubkey = key.with_suffix(".pub").read_text().strip()
        incus.run("config", "set", name, f"raw.qemu={credential(user, pubkey)}")
        try:
            incus.run("start", name)
            login_and_install(name, user, key, timeout)
        finally:
            # Also on failure: never leave the way in configured.
            if incus.run("info", name).stdout.find("Status: RUNNING") >= 0:
                incus.stop(name)
            incus.run("config", "unset", name, "raw.qemu")

    incus.run("start", name)
    incus.wait_for_agent(name, timeout=120)
    keys = f"/home/{user}/.ssh/authorized_keys"
    incus.run("exec", name, "--", "sh", "-c",
              f"rm -f {SUDOERS}; [ -f {keys} ] && sed -i '/ {COMMENT}$/d' {keys}; true")
    left = incus.run("exec", name, "--", "sh", "-c",
                     f"ls {SUDOERS} 2>/dev/null; grep -l ' {COMMENT}$' {keys} 2>/dev/null; true").stdout
    if left.strip() or incus.config_get(name, "raw.qemu"):
        raise incus.IncusError(f"{name}: the one-off key or sudo rule is still there: {left.strip()}")


def login_and_install(name: str, user: str, key: Path, timeout: float) -> None:
    ssh = ["ssh", "-i", str(key), "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes",
           "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
           "-o", "LogLevel=ERROR", "-o", "ConnectTimeout=3"]
    deadline, addr = time.time() + timeout, ""
    while time.time() < deadline:
        addr = addr or ipv4(name)
        if addr and subprocess.run([*ssh, f"{user}@{addr}", "true"],
                                   stdin=subprocess.DEVNULL, capture_output=True).returncode == 0:
            break
        time.sleep(3)
    else:
        raise incus.IncusError(
            f"{name}: no SSH login with the one-off key after {timeout:.0f}s "
            f"({'no IPv4' if not addr else 'at ' + addr}); the image may not run sshd "
            f"by default or may predate systemd credentials")
    proc = subprocess.run([*ssh, f"{user}@{addr}", INSTALL], stdin=subprocess.DEVNULL,
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise incus.IncusError(f"{name}: installing the agent over SSH failed: "
                               f"{proc.stderr.strip() or proc.stdout.strip()}")
    incus.wait_for_agent(name, timeout=120)
