# description: OpenSSH server; your host's public key is authorised for the dish user
if command -v pacman >/dev/null; then pkg_install openssh; else pkg_install openssh-server; fi
systemctl enable --now ssh 2>/dev/null || systemctl enable --now sshd
if [ -n "${PB_SSH_KEY:-}" ]; then
  home=$(getent passwd "$PB_USER" | cut -d: -f6)
  install -d -m 700 -o "$PB_USER" -g "$(id -gn "$PB_USER")" "$home/.ssh"
  grep -qxF "$PB_SSH_KEY" "$home/.ssh/authorized_keys" 2>/dev/null || echo "$PB_SSH_KEY" >> "$home/.ssh/authorized_keys"
  chown "$PB_USER": "$home/.ssh/authorized_keys" && chmod 600 "$home/.ssh/authorized_keys"
fi
