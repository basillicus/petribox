# EPEL and CRB carry most extras (htop, tmux plugins, ...).
pkg_install epel-release
dnf config-manager --set-enabled crb
pkg_update
pkg_install vim tmux tar gzip python3 htop
