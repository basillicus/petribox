# description: PicoClaw, lightweight Go assistant (setup: picoclaw onboard)
as_user <<'SCRIPT'
set -e
mkdir -p ~/.local/bin && cd "$(mktemp -d)"
curl -fsSL https://github.com/sipeed/picoclaw/releases/latest/download/picoclaw_Linux_x86_64.tar.gz | tar -xz
install -m 755 picoclaw ~/.local/bin/picoclaw
SCRIPT
