# description: uv, for Python versions, packages and tools
as_user "command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/${VERSION:+$VERSION/}install.sh | sh"
