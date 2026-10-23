# Demo recordings

The GIFs in the main README are made from the asciinema casts here. Play a
cast in your terminal (text you can copy, at any speed):

```bash
asciinema play docs/demo/quickstart.cast
asciinema play -s 2 docs/demo/tutorial.cast   # all scenes, twice as fast
```

| Cast | Shows |
|---|---|
| `quickstart.cast` | recipes, a dish from a built base, a command in it, list, stop |
| `wizard.cast` | `petribox new` with no arguments: the questions and the printed command |
| `daily.cast` | add an extra, hand in a secret, share a folder, SSH in, delete |
| `tutorial.cast` | the three above, one after the other |

## Recording again

`record.py` types the commands and answers the prompts; they run for real.
Record in a separate Incus project, with a separate config and home, so
the casts show neither your instances nor your paths:

```bash
D=$(mktemp -d)                       # keep the path short and neutral
incus project create demo -c features.images=false -c features.profiles=false \
  -c features.storage.volumes=false
mkdir -p "$D/incus" "$D/config/petribox/recipes/webshop" "$D/home/.ssh" "$D/home/webshop/src"
cp ~/.config/incus/config.yml "$D/incus/"
sed -i 's|addr: unix://|addr: unix://\n    project: demo|' "$D/incus/config.yml"
ssh-keygen -q -t ed25519 -N "" -C demo -f "$D/home/.ssh/id_ed25519"
cat > "$D/config/petribox/recipes/webshop/recipe.toml" <<'EOF'
description = "Webshop dev VM: Debian 13 with Node, uv and SSH"
image = "images:debian/13"
extras = ["node", "uv", "ssh"]
EOF
echo 'console.log("hello from the host")' > "$D/home/webshop/src/app.js"

export HOME=$D/home XDG_CONFIG_HOME=$D/config INCUS_CONF=$D/incus
cd "$D/home/webshop"
petribox build webshop               # off camera: the casts start from a built base
uv run --with pexpect /path/to/petribox/docs/demo/record.py      # or: record.py wizard
```

Instance names in the scenes (`shop1`, `shop-try`, `shop-web`, `pb-webshop`) must not be
taken in any other project on the same network: Incus gives every instance
a DNS name on its bridge.

Then the combined cast and the GIFs ([agg](https://github.com/asciinema/agg)):

```bash
cd docs/demo
asciinema cat quickstart.cast wizard.cast daily.cast > tutorial.cast
for c in quickstart wizard daily; do agg --speed 1.5 --font-size 14 $c.cast $c.gif; done
```

Clean up: `incus delete -f pb-webshop --project demo && incus project delete demo`.
