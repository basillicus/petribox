# Shared start of every recipe's provisioning. Runs as root via `bash -s`;
# the recipe's provision.sh is appended after this and can use the helpers.
set -euo pipefail
: "${PB_USER:?PB_USER is not set}"

# The agent can be up before the network is.
for _ in $(seq 60); do getent hosts example.org >/dev/null 2>&1 && break; sleep 2; done
getent hosts example.org >/dev/null 2>&1 || { echo "no network/DNS in the instance" >&2; exit 1; }

pkg_update() {
  if command -v dnf >/dev/null; then dnf -y upgrade
  elif command -v apt-get >/dev/null; then apt-get update -q && DEBIAN_FRONTEND=noninteractive apt-get -yq full-upgrade
  elif command -v pacman >/dev/null; then pacman -Syu --noconfirm
  fi
}
pkg_install() {
  if command -v dnf >/dev/null; then dnf -y install "$@"
  elif command -v apt-get >/dev/null; then DEBIAN_FRONTEND=noninteractive apt-get -yq install "$@"
  elif command -v pacman >/dev/null; then pacman -S --noconfirm --needed "$@"
  fi
}

# Package lists first: apt cannot install anything before an update.
command -v apt-get >/dev/null && apt-get update -q
pkg_install sudo curl git

# The dish user: uid 1000 when free, passwordless sudo, no password login.
if ! id "$PB_USER" >/dev/null 2>&1; then
  useradd -m -s /bin/bash -u 1000 "$PB_USER" 2>/dev/null || useradd -m -s /bin/bash "$PB_USER"
fi
echo "$PB_USER ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/90-petribox
chmod 0440 /etc/sudoers.d/90-petribox

# Run a command as the dish user, in a login shell.
as_user() { su - "$PB_USER" -c "$*"; }
