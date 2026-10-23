# description: mise, the tool and runtime version manager
as_user "command -v mise >/dev/null || curl -fsSL https://mise.run | ${VERSION:+MISE_VERSION=v$VERSION} sh"
# Shims rather than `mise activate`: they also work in non-interactive shells.
add_to_rc 'export PATH="$HOME/.local/bin:$HOME/.local/share/mise/shims:$PATH"'
