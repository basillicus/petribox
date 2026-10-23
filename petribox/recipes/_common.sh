# Shared start of every provisioning run, as root. The extras and the
# recipe's provision.sh are appended after this and can use the helpers.
# Safe to run again on an instance that already has it.
set -euo pipefail
: "${PB_USER:?PB_USER is not set}"

# The agent can be up before the network is.
for _ in $(seq 60); do getent hosts example.org >/dev/null 2>&1 && break; sleep 2; done
getent hosts example.org >/dev/null 2>&1 || { echo "no network/DNS in the instance" >&2; exit 1; }

# Omarchy (Arch-based) refuses plain `pacman -Syu` and updates through its
# own tool, which also handles its keyrings and migrations.
is_omarchy() { [ -d /usr/share/omarchy ] && command -v omarchy-update >/dev/null; }

pkg_update() {
  if is_omarchy; then as_user 'omarchy-update -y'
  elif command -v dnf >/dev/null; then dnf -y upgrade
  elif command -v apt-get >/dev/null; then apt-get update -q && DEBIAN_FRONTEND=noninteractive apt-get -yq full-upgrade
  elif command -v pacman >/dev/null; then pacman -Syu --noconfirm
  elif command -v zypper >/dev/null; then zypper -n dup
  fi
}
pkg_install() {
  if command -v dnf >/dev/null; then dnf -y install "$@"
  elif command -v apt-get >/dev/null; then DEBIAN_FRONTEND=noninteractive apt-get -yq install "$@"
  elif command -v pacman >/dev/null; then
    # Only what is missing; a fresh image may have no package databases yet
    # (Omarchy's), and -Sy alone is allowed where -Syu is not.
    local missing=() p
    for p in "$@"; do pacman -Qq "$p" >/dev/null 2>&1 || missing+=("$p"); done
    [ ${#missing[@]} -eq 0 ] && return 0
    ls /var/lib/pacman/sync/*.db >/dev/null 2>&1 || pacman -Sy --noconfirm
    pacman -S --noconfirm --needed "${missing[@]}"
  elif command -v zypper >/dev/null; then zypper -n install "$@"
  fi
}

# Package lists first: apt cannot install anything before an update.
command -v apt-get >/dev/null && apt-get update -q
# Arch: the image's keyring can be older than today's packagers' keys, and
# installing without a full upgrade is unsupported. Refresh both, once.
if command -v pacman >/dev/null && ! is_omarchy; then
  [ -d /etc/pacman.d/gnupg ] || pacman-key --init
  pacman-key --populate archlinux >/dev/null
  pacman -Sy --noconfirm --needed archlinux-keyring
  pacman -Su --noconfirm
fi
pkg_install sudo curl git

# The dish user: uid 1000 when free, passwordless sudo, no password login.
if ! id "$PB_USER" >/dev/null 2>&1; then
  useradd -m -s /bin/bash -u 1000 "$PB_USER" 2>/dev/null || useradd -m -s /bin/bash "$PB_USER"
fi
# verifypw/listpw=any: `sudo -v` and `sudo -l` need no password either, even
# when the image has its own password rule for the user (Omarchy does).
printf '%s\n' "$PB_USER ALL=(ALL) NOPASSWD:ALL" \
  "Defaults:$PB_USER verifypw=any, listpw=any" > /etc/sudoers.d/90-petribox
chmod 0440 /etc/sudoers.d/90-petribox
visudo -cq || { echo "sudoers check failed" >&2; rm -f /etc/sudoers.d/90-petribox; exit 1; }

# Run commands as the dish user in a login shell, with ~/.local/bin and the
# mise shims on PATH: `as_user 'cmd ...'`, or a script on stdin (heredoc).
as_user() {
  local path='export PATH="$HOME/.local/bin:$HOME/.local/share/mise/shims:$PATH"'
  if [ $# -gt 0 ]; then su - "$PB_USER" -c "$path; $*" </dev/null
  else su - "$PB_USER" -c "$path; bash -s"
  fi
}

# Put a line at the top of the dish user's ~/.bashrc (above the "not
# interactive? stop here" check of Debian-family rc files) and in ~/.zshenv
# when zsh is installed, so commands run through `petribox shell` or ssh see it.
add_to_rc() {
  local home rc
  home=$(getent passwd "$PB_USER" | cut -d: -f6)
  for rc in "$home/.bashrc" "$home/.zshenv"; do
    [ "$rc" = "$home/.zshenv" ] && ! command -v zsh >/dev/null && continue
    grep -qxF "$1" "$rc" 2>/dev/null && continue
    { echo "$1"; cat "$rc" 2>/dev/null; } > "$rc.petribox" && mv "$rc.petribox" "$rc"
    chown "$PB_USER": "$rc"
  done
}
