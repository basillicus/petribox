# description: opencode, terminal coding agent
as_user 'command -v opencode >/dev/null || curl -fsSL https://opencode.ai/install | bash'
add_to_rc 'export PATH="$HOME/.opencode/bin:$PATH"'
