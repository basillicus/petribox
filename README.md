# petribox

Sandboxes ("dishes") on [Incus](https://linuxcontainers.org/incus/), built
from recipes. A recipe is a plain Incus image plus a provisioning script.
petribox does four things on top of Incus:

1. **build**: image → provisioned base instance → `clean` snapshot
2. **new**: copy that snapshot into a dish (optionally ephemeral)
3. **secrets**: resolve values on the host, hand them in over stdin
4. **dotfiles**: apply your [chezmoi](https://www.chezmoi.io/) repo in each new dish

Everything else is plain `incus` (see [the cheat sheet](#everything-else-is-incus)).
Linux hosts only, since that's where Incus runs. For macOS or Windows,
`petribox export-recipe` writes a recipe as a [Vagrant](https://developer.hashicorp.com/vagrant)
project or a [Lima](https://lima-vm.io/) template (see [Other platforms](#other-platforms)).

## Quick start

```bash
uv tool install .            # or: pipx install .
petribox recipes             # what can be built
petribox build rocky         # once per recipe; takes a few minutes
petribox new lab --from rocky --extra ssh --extra codex
petribox shell lab
```

![A dish from a built recipe: recipes, new, a command inside, list, stop](docs/demo/quickstart.gif)

Or run `petribox new` with no arguments and answer the questions: recipe or
image, size, extras, secrets, shared folders. It prints the equivalent
command, and after an image choice it offers to save the answers as a
recipe, so the next dish like it is a fast copy.

![petribox new with no arguments: the questions, then the equivalent command](docs/demo/wizard.gif)

Quick test without writing a recipe:

```bash
petribox new try1 --image images:debian/13 --ephemeral --extra ssh --share ./project
```

Throwaway dish that deletes itself when it stops:

```bash
petribox new try1 --from debian --ephemeral
petribox stop try1           # gone
```

Day to day: add tools to a dish, hand in a secret, share a folder, SSH in, delete:

![petribox add, secret, mount, ssh and delete](docs/demo/daily.gif)

The same as one terminal recording, with text you can copy:
`asciinema play docs/demo/tutorial.cast` ([how the recordings are made](docs/demo/README.md)).

## Commands

| Command | What it does |
|---|---|
| `petribox recipes` | List recipes and whether their base is built |
| `petribox extras` | List extras: ssh, mise, node, uv, podman and agent CLIs |
| `petribox export-recipe RECIPE --to vagrant\|lima [-o DIR]` | Write the recipe as a Vagrantfile + provision.sh, or a Lima template |
| `petribox build RECIPE [--rebuild\|--resume]` | Create `pb-RECIPE` from the image, run `_common.sh` + extras + `provision.sh` as root, stop it, snapshot `clean`. `--resume` runs the script again on the existing base (after a recipe change), `--rebuild` starts over |
| `petribox new` | Ask: recipe or image, resources, extras, secrets, dotfiles, shared folders; print the equivalent command; offer to save an image setup as a recipe |
| `petribox new NAME --from RECIPE [--ephemeral] [--extra X]... [--secret KEY]... [--share DIR]... [--cpus N] [--memory 8GiB] [--no-dotfiles]` | `incus copy pb-RECIPE/clean NAME` (building the base first if needed), start, install extras, hand in secrets, apply dotfiles, mount folders |
| `petribox new NAME --image IMAGE [--container] [--disk 40GiB] [--user U] ...` | No recipe: launch the image and set up the user on the spot (slower per dish; use a recipe for anything you repeat) |
| `petribox add NAME EXTRA...` | Install extras into an existing dish (only that dish; for every future one, add them to the recipe and `build --resume`) |
| `petribox start NAME...` / `stop NAME... [--force]` / `delete NAME... [--yes]` | Wrappers that print the `incus` command they run: `incus start`; `incus stop --timeout 60`, then `--force` if the guest ignores it (an ephemeral dish is then deleted); `incus delete --force`, after a question |
| `petribox list [--bases]` | Your dishes with recipe, state, IPv4, CPUs, and memory and disk as used / limit (`--bases` adds the `pb-*` bases). Live view: `incus top` |
| `petribox shell NAME [CMD...]` | Login shell (or one command) as the dish user |
| `petribox mount NAME DIR [DEST]` | Share a host directory, by default at `~user/<dir name>`; remove with `incus config device remove NAME <device>` |
| `petribox secret NAME` / `NAME KEY...` / `NAME --unset KEY` | List (masked), set or remove a dish's secrets |

## Recipes

A recipe is a directory with `recipe.toml` and an optional `provision.sh`:

```toml
# ~/.config/petribox/recipes/webshop/recipe.toml
description = "Rocky 9 with Node for the Webshop project"
image = "images:rockylinux/9"   # any Incus image, or a local alias
vm = true                       # false = system container
cpus = 2
memory = "4GiB"
disk = "20GiB"
user = "petri"                  # the dish user, created if missing
extras = ["ssh", "node"]        # see `petribox extras`
```

```bash
# ~/.config/petribox/recipes/webshop/provision.sh  (runs as root)
pkg_install nodejs npm
as_user 'npm config set prefix ~/.local'
```

`provision.sh` runs after the built-in [`_common.sh`](petribox/recipes/_common.sh)
and the extras. `_common.sh` waits for the network, creates the user with
passwordless sudo, and provides `pkg_update`, `pkg_install` (dnf, apt,
pacman or zypper), `as_user` (a command, or a script on stdin) and
`add_to_rc` (a line at the top of the user's `.bashrc`, and in `.zshenv`, so
non-interactive commands see it too). Recipes in `~/.config/petribox/recipes/`
override built-ins of the same name.

### Extras

An extra is a shell script in [`petribox/recipes/_extras/`](petribox/recipes/_extras)
that installs one thing, with the same helpers as `provision.sh`. Use them in
a recipe (`extras = [...]`, baked into the base) or for one dish
(`--extra NAME`, installed after the copy, or later with `petribox add`).
Recipe extras are installed once into the base, so every dish has them
at no cost; `--extra` and `add` install into that one dish each time. Add your own as
`~/.config/petribox/extras/NAME.sh`:

```bash
# description: what it installs (shown by `petribox extras`)
# needs: node          # extras to install first
as_user 'npm install -g some-agent && mise reshim'
```

Pin versions with `NAME@VERSION`, in a recipe or with `--extra`:
`extras = ["node@24.22.1", "codex@0.164.0", "uv@0.13.5"]`. The script gets
it as `$VERSION`; extras whose installer has no version option (`ssh`,
`podman`, `opencode`, `hermes`, `picoclaw`) refuse a pin rather than ignore
it. Pinned extras give the same tools on every build; the image itself and
its packages still move. When a dish must be identical for everyone, share
the built base instead:

```bash
incus publish pb-webshop/clean --alias webshop-2026-10   # you
incus image export webshop-2026-10 ./webshop             # a file to hand over
incus image import ./webshop.tar.gz --alias webshop      # them; recipe: image = "webshop"
```

The `ssh` extra authorises your `~/.ssh/id_ed25519.pub` (or ecdsa, rsa) for
the dish user, and `new` then prints the `ssh user@ip` line. The agent
extras (`claude-code`, `codex`, `opencode`, `pi`, `openclaw`, `hermes`,
`picoclaw`) run each project's own installer; `codex` is tested, the others
are not.

Built-in recipes: `rocky`, `debian`, `arch`, `kali` (VM, from Kali's own
QEMU image; see [Kali](#kali-as-a-vm)), `kali-container`, `omarchy`
(untested, see its `recipe.toml`).

Image quirks are handled when petribox can see them: an image whose metadata
says it needs Secure Boot off (Arch's VM image) gets `security.secureboot=false`,
and Arch's keyring is refreshed before the first install. Anything else an
image needs goes in the recipe's `config` table, e.g.
`config = { "security.secureboot" = "false" }`, or on one dish with
`incus config set NAME key=value`.

No cloud-init: the plain images run `incus exec` from the start, and a base is
built once and copied, so nothing needs to happen on first boot.

### Kali as a VM

Incus's image server has Kali only as a container. For a VM, use Kali's
official QEMU image:

```bash
# from https://cdimage.kali.org/current/ : kali-linux-YYYY.N-qemu-amd64.7z (check SHA256SUMS)
bsdtar -xf kali-linux-YYYY.N-qemu-amd64.7z
petribox import-image kali-linux-YYYY.N-qemu-amd64.qcow2 kali-qemu
petribox build kali          # stops at the agent; see below
```

The image boots with legacy BIOS (the recipe sets `security.csm=true`) and
ships neither the Incus agent nor a running SSH server, so the build stops
and asks for the one manual step below. The `clean` snapshot keeps the agent,
so this happens once per base, not per dish.

### Omarchy as a VM

Omarchy publishes an official VM image; the `omarchy` recipe uses it and
needs no manual step:

```bash
curl -fsSL https://nightly.omarchy.org/stable/latest.json    # vm.url, vm.sha256
curl -fLO <vm.url> && echo "<vm.sha256>  omarchy-X.Y.Z.qcow2" | sha256sum -c
petribox import-image omarchy-X.Y.Z.qcow2 omarchy-qemu
petribox build omarchy
```

The image has sshd but no Incus agent. With `agent_via_ssh = true` in a
recipe, the first boot of the base gets a one-off SSH key and sudo rule
through the VM firmware (a systemd credential, as Omarchy's own `vm-boot`
does); petribox logs in, installs the agent, then stops the VM, removes the
firmware entry and deletes the key and rule, and checks that they are gone.
It needs systemd 252 or newer and an sshd that starts by default (Kali's
image does not start sshd, hence its manual step). Updates go through
`omarchy update -y`, since Omarchy refuses a plain `pacman -Syu`.

### Images without an agent

`import-image` works for any distro's VM disk image, but `incus exec` needs
the Incus agent inside. Install it once from the graphical console:

```bash
incus console pb-kali --type=vga    # log in (Kali: kali / kali), open a terminal
sudo -i                             # the agent drive is readable by root only
mount /dev/disk/by-label/incus-agent /mnt   # "mounted read-only" is expected
cd /mnt && ./install.sh && cd / && umount /mnt
systemctl start incus-agent
```

Then finish the build from the host: `petribox build kali --resume`.

## Other platforms

`petribox export-recipe webshop --to vagrant` writes `webshop-vagrant/`
(`Vagrantfile` and `provision.sh`); `--to lima` writes `webshop.yaml` for
`limactl start ./webshop.yaml`. The provisioning script is the one
`petribox build` runs (`_common.sh`, extras, `provision.sh`), so the same
recipe gives the same tools. The image becomes the matching Vagrant box or
Lima template (Debian, Ubuntu, Rocky, Alma, Fedora, Arch; Kali for Vagrant
only); for anything else, set `vagrant_box = "..."` or `lima_template = "..."`
in the recipe.

What does not carry over: secrets (hand them in your own way), fast copies
of a base (each machine is set up from scratch), and containers (the export
is always a VM). The Vagrant user is `vagrant`; in Lima it is your own user
name. The Lima export uses Lima's image-only templates, so unlike Lima's
defaults your home directory is **not** mounted into the VM. Some boxes and
images are x86-only (Kali), which matters on Apple Silicon.

For building images for many targets at once (VirtualBox, VMware, QEMU,
cloud), use [Packer](https://developer.hashicorp.com/packer) with the same
`provision.sh`.

## Secrets and dotfiles

```toml
# ~/.config/petribox/config.toml
[secrets]
OPENROUTER_API_KEY = { cmd = "secret-tool lookup service openrouter" }

[dotfiles]
repo = "https://github.com/alice/dotfiles.git"
```

`--secret KEY` runs the command on the host (or asks with a hidden prompt if
there is none), and writes `export KEY=...` to `~/.config/petribox/env`
(mode 0600) in the dish over the stdin of `incus exec`. The shell rc sources
it. Values never appear in host argv or in the instance config, so copies of
the *base* and `incus config show` never contain them; an export of the dish
itself does, because the file is on its disk.

Think twice before handing a model API key to an agent at all: it can read
and send anything you give it. A proxy on the host that adds the key (for
example [LiteLLM](https://github.com/BerriAI/litellm) with a virtual key per
dish) keeps the real key out of the dish.

## Everything else is Incus

| Task | Command |
|---|---|
| Start, stop, delete | `incus start lab`, `incus stop lab`, `incus delete -f lab` (what `petribox start/stop/delete` run) |
| Snapshot and roll back | `incus snapshot create lab before-upgrade`, `incus snapshot restore lab before-upgrade` |
| Copy files in, out | `incus file push -r ./src lab/home/petri/`, `incus file pull -r lab/home/petri/out ./` |
| Forward a port to the host | `incus config device add lab web proxy listen=tcp:127.0.0.1:8080 connect=tcp:127.0.0.1:8080` |
| Graphical console (VMs) | `incus console lab --type=vga` (needs `remote-viewer`: `sudo pacman -S virt-viewer` or your distro's virt-viewer) |
| Export, import | `incus export lab lab.tar.gz`, `incus import lab.tar.gz` |
| Move to another Incus host | `incus remote add other https://other.example.org:8443`, `incus move lab other:` |
| Resize | `incus config set lab limits.cpu=4 limits.memory=8GiB` |
| Remove a base | `petribox delete pb-arch` or `incus delete -f pb-arch` (dishes are full copies and keep working); `petribox new --from arch` rebuilds it when needed |
| Remove an image | `incus image list`, `incus image delete kali-qemu` (images from `images:` are a cache Incus expires by itself) |

## When something fails

Every error ends with what to try: known problems (Secure Boot, idmap,
missing agent, no network, package keyrings, full disk, ...) get their fix,
and every error gets the general moves: the instance log
(`incus info --show-log NAME`), its screen (`incus console NAME --type=vga`),
a root shell (`incus exec NAME -- bash`), and where settings go (a recipe's
`config = {...}` or `incus config set NAME key=value`). A failed build keeps
the base: fix the recipe, then `petribox build RECIPE --resume` to run the
setup again on it, or `--rebuild` to start over.

## Host setup notes

- **ufw** blocks DHCP on the Incus bridge, so instances get no IPv4. Allow it:
  `sudo ufw allow in on incusbr0 && sudo ufw route allow in on incusbr0 && sudo ufw route allow out on incusbr0`
- **Containers** need subordinate ids for root. If `incus launch` says
  "System doesn't have a functional idmap setup":
  `echo 'root:1000000:1000000000' | sudo tee -a /etc/subuid /etc/subgid && sudo systemctl restart incus`
- **Docker** on the same host can drop forwarded bridge traffic; see the Incus
  docs on "Prevent connectivity issues with Incus and Docker".

## Tests

```bash
uv run --with pytest --with pyyaml pytest -q
```
