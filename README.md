# petribox

Sandboxes ("dishes") on [Incus](https://linuxcontainers.org/incus/), built
from recipes. A recipe is a plain Incus image plus a provisioning script.
petribox does four things on top of Incus:

1. **build**: image → provisioned base instance → `clean` snapshot
2. **new**: copy that snapshot into a dish (optionally ephemeral)
3. **secrets**: resolve values on the host, hand them in over stdin
4. **dotfiles**: apply your [chezmoi](https://www.chezmoi.io/) repo in each new dish

Everything else is plain `incus` (see [the cheat sheet](#everything-else-is-incus)).
Linux hosts only, since that's where Incus runs. On macOS or Windows use
[Vagrant](https://developer.hashicorp.com/vagrant) or [Lima](https://lima-vm.io/).

## Quick start

```bash
uv tool install .            # or: pipx install .
petribox recipes             # what can be built
petribox build rocky         # once per recipe; takes a few minutes
petribox new lab --from rocky
petribox shell lab
```

Throwaway dish that deletes itself when it stops:

```bash
petribox new try1 --from debian --ephemeral
incus stop try1              # gone
```

## Commands

| Command | What it does |
|---|---|
| `petribox recipes` | List recipes and whether their base is built |
| `petribox build RECIPE [--rebuild]` | Create `pb-RECIPE` from the image, run `_common.sh` + `provision.sh` as root, stop it, snapshot `clean` |
| `petribox new NAME --from RECIPE [--ephemeral] [--secret KEY]... [--cpus N] [--memory 8GiB] [--no-dotfiles]` | `incus copy pb-RECIPE/clean NAME`, start, hand in secrets, apply dotfiles |
| `petribox shell NAME [CMD...]` | Login shell (or one command) as the dish user |
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
```

```bash
# ~/.config/petribox/recipes/webshop/provision.sh  (runs as root)
pkg_install nodejs npm
as_user 'npm config set prefix ~/.local'
```

`provision.sh` runs after the built-in [`_common.sh`](petribox/recipes/_common.sh),
which waits for the network, creates the user with passwordless sudo, and
provides `pkg_update`, `pkg_install` (dnf, apt or pacman) and `as_user`.
Recipes in `~/.config/petribox/recipes/` override built-ins of the same name.

Built-in recipes: `rocky`, `debian`, `arch`, `kali` (VM, from Kali's own
QEMU image; see [Kali](#kali-as-a-vm)), `kali-container`, `omarchy`
(untested, see its `recipe.toml`).

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

### Images without an agent

`import-image` works for any distro's VM disk image, but `incus exec` needs
the Incus agent inside. Install it once from the graphical console:

```bash
incus console pb-kali --type=vga    # log in (Kali: kali / kali), open a terminal
sudo mount -t 9p config /mnt        # if that fails: sudo mount /dev/disk/by-label/incus-agent /mnt
cd /mnt && sudo ./install.sh && cd / && sudo umount /mnt
sudo systemctl start incus-agent
```

Then finish the build from the host: `petribox build kali --resume`.

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
| List, start, stop, delete | `incus list`, `incus start lab`, `incus stop lab`, `incus delete -f lab` |
| Snapshot and roll back | `incus snapshot create lab before-upgrade`, `incus snapshot restore lab before-upgrade` |
| Share a host folder | `incus config device add lab src disk source=$PWD path=/home/petri/src shift=true` |
| Forward a port to the host | `incus config device add lab web proxy listen=tcp:127.0.0.1:8080 connect=tcp:127.0.0.1:8080` |
| Graphical console (VMs) | `incus console lab --type=vga` (needs `remote-viewer`: `sudo pacman -S virt-viewer` or your distro's virt-viewer) |
| Export, import | `incus export lab lab.tar.gz`, `incus import lab.tar.gz` |
| Move to another Incus host | `incus remote add other https://other.example.org:8443`, `incus move lab other:` |
| Resize | `incus config set lab limits.cpu=4 limits.memory=8GiB` |

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
uv run --with pytest pytest -q
```
