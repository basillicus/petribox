"""Record the demo casts in docs/demo/ with asciinema, typing for you.

Each scene is a list of steps: a comment to show, or a command to type and
run, with the answers to give its prompts. Commands run for real against
Incus, so record in a throwaway project (see README.md next to this file).

    uv run --with pexpect docs/demo/record.py [SCENE...]
"""

from __future__ import annotations

import json
import os
import random
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
COLS, ROWS = 110, 32

# (kind, text, answers): "#" shows a comment, "$" runs a command. Answers are
# (start of the prompt, what to type) pairs, given in order. {ip:NAME} is
# filled in.
SCENES: dict[str, list] = {
    "quickstart": [
        ("#", "Recipes describe a machine; each one is built once into a base.", []),
        ("$", "petribox recipes", []),
        ("#", "A dish is a copy of a base: ready in seconds, with the recipe's tools.", []),
        ("$", "petribox new shop1 --from webshop --ephemeral", []),
        ("$", "petribox shell shop1 'node --version; uv --version'", []),
        ("$", "petribox list", []),
        ("#", "Ephemeral: stopping it deletes it.", []),
        ("$", "petribox stop shop1", []),
    ],
    "wizard": [
        ("#", "No flags: petribox asks, then prints the command to repeat it.", []),
        ("$", "petribox new", [
            ("From", "webshop"), ("Name", "shop-try"), ("CPUs", ""), ("Memory", ""),
            ("Ephemeral", "y"), ("Extras, comma", "claude-code"), ("Variables, comma", ""),
            ("Share a host folder", ""), ("Create it", "y"),
        ]),
        ("$", "petribox shell shop-try claude --version", []),
        ("$", "petribox delete shop-try --yes", []),
    ],
    "daily": [
        ("$", "petribox new shop-web --from webshop", []),
        ("#", "Add tools to a dish that already exists:", []),
        ("$", "petribox add shop-web opencode", []),
        ("#", "Hand in a secret: asked for hidden, never on the command line.", []),
        ("$", "petribox secret shop-web API_TOKEN", [("API_TOKEN", "demo-token-not-real")]),
        ("$", "petribox shell shop-web 'echo ${API_TOKEN:0:5}...'", []),
        ("#", "Share a project folder from the host:", []),
        ("$", "petribox mount shop-web ./src", []),
        ("$", "petribox shell shop-web ls src", []),
        ("#", "The ssh extra authorised your host key:", []),
        ("$", "ssh petri@{ip:shop-web} uname -a", []),
        ("$", "petribox delete shop-web --yes", []),
    ],
}

# ssh reads keys and known_hosts from the passwd home, not $HOME: point it
# at the demo's own, without showing that on screen.
SSH = ("ssh -i ~/.ssh/id_ed25519 -o UserKnownHostsFile=~/.ssh/known_hosts "
       "-o StrictHostKeyChecking=accept-new -o LogLevel=ERROR ")


def ip(name: str) -> str:
    out = subprocess.run(["incus", "list", name, "--format", "json"],
                         capture_output=True, text=True).stdout
    for inst in json.loads(out or "[]"):
        for nic, net in ((inst.get("state") or {}).get("network") or {}).items():
            for addr in net.get("addresses", []) if nic != "lo" else []:
                if addr["family"] == "inet":
                    return addr["address"]
    return "IP"


def fill(text: str) -> str:
    while "{ip:" in text:
        start = text.index("{ip:")
        end = text.index("}", start)
        text = text[:start] + ip(text[start + 4:end]) + text[end + 1:]
    return text


def type_out(text: str, write=None) -> None:
    write = write or (lambda c: (sys.stdout.write(c), sys.stdout.flush()))
    for ch in text:
        write(ch)
        time.sleep(random.uniform(0.03, 0.08))


def play(steps: list) -> None:
    import pexpect

    for kind, text, answers in steps:
        if kind == "#":
            sys.stdout.write("\x1b[2m# ")
            type_out(text)
            sys.stdout.write("\x1b[0m\n")
            time.sleep(1.2)
            continue
        cmd = fill(text)
        sys.stdout.write("\x1b[1;32m$\x1b[0m ")
        type_out(cmd)
        time.sleep(0.4)
        sys.stdout.write("\r\n")
        sys.stdout.flush()
        run = SSH + cmd.removeprefix("ssh ") if cmd.startswith("ssh ") else cmd
        child = pexpect.spawn("bash", ["-c", run], encoding="utf-8", dimensions=(ROWS, COLS),
                              timeout=1800)
        child.logfile_read = sys.stdout
        for prompt, answer in answers:
            # Up to the ": " that ends the prompt; colour codes may sit between.
            child.expect(re.escape(prompt) + r"[^\n]*: ", timeout=300)
            time.sleep(0.8)
            type_out(answer, write=child.send)
            child.send("\r")
        child.expect(pexpect.EOF)
        child.close()
        time.sleep(2)


def main() -> None:
    names = sys.argv[1:] or list(SCENES)
    if os.environ.get("PB_DEMO_SCENE"):  # inside asciinema: play one scene
        random.seed(1)
        play(SCENES[os.environ["PB_DEMO_SCENE"]])
        return
    for name in names:
        cast = HERE / f"{name}.cast"
        env = {**os.environ, "PB_DEMO_SCENE": name}
        subprocess.run(["asciinema", "rec", "--overwrite", "--headless", "--idle-time-limit", "2",
                        "--window-size", f"{COLS}x{ROWS}", "--title", f"petribox: {name}",
                        "--command", f"{shlex.quote(sys.executable)} {shlex.quote(__file__)}",
                        str(cast)], env=env, check=True)
        # The header records the command line, with this machine's paths.
        lines = cast.read_text().splitlines(keepends=True)
        header = json.loads(lines[0])
        header.pop("command", None)
        header.pop("env", None)
        cast.write_text(json.dumps(header) + "\n" + "".join(lines[1:]))
        print(f"wrote {cast}", file=sys.stderr)


if __name__ == "__main__":
    main()
