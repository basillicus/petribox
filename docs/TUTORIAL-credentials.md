# Tutorial: give an agent a dish and the credentials it needs

This walks through a full run: install petribox, create a dish, hand it a token,
clone a private repository inside it, and clean up. Along the way it shows what
petribox does at each step, so you can see what your agent can and cannot reach.

Examples use a private repository `alice/webshop` and a dish called `work`.

## 0. What a dish protects, and what it doesn't

A dish is a VM (or container). The agent inside it runs as an ordinary user.

| The agent **can** | The agent **cannot** |
|---|---|
| Read every file in the dish, including every key you give it | Read your host files, except directories you `petribox mount` |
| Use those keys from anywhere, and send them out over the network | Reach your password manager, SSH agent or browser sessions |
| Reach the internet and the host's bridge address | Reach services bound to the host's `127.0.0.1` |

So "secure" here doesn't mean hiding a key from the agent that needs it. It means:

1. **Give the least you can.** Mount a repo and push from the host yourself, instead
   of giving the agent a push token. Mount a model cache read-only instead of giving
   it a download token.
2. **Make what you give cheap to lose.** Scoped, short-lived tokens. API keys with a
   spending limit, one per dish.
3. **Keep it from leaking further.** Petribox never puts values in cloud-init
   user-data, in `incus config`, or in process arguments on the host.

## 1. Install petribox

```bash
uv tool install git+https://github.com/<owner>/petribox   # or: pipx install git+...
petribox initial-setup
```

`initial-setup` checks Incus, your group membership, VM host tools and the
**host firewall**. Read step 4 of its output. If you run `ufw` or `firewalld`,
add the bridge rules it prints *before* creating dishes. Without them the dish
never gets an IP address and nothing installs (see Troubleshooting).

## 2. Create a dish with the tools your project needs

Read the project's README for its requirements, then put them in a config file:

```yaml
# work.yaml
packages: [bubblewrap, socat]   # from the distro (Rocky Linux 9 by default)
mise_packages: [ripgrep]        # from mise: newer tools, or ones not in the base repos
```

```bash
petribox create work --preset minimal --config work.yaml
```

What happens:

1. `incus init` defines the VM from the cached image. The very first run downloads
   about 1 GB. The image server rebuilds images daily and Incus refreshes its cache
   in the background, so an occasional create is slower.
2. First boot runs **cloud-init**: creates the user, installs packages, mise, tools,
   and any `--agent`. This takes 1–3 minutes.
3. Petribox writes your env vars and secrets (step 3) once the user exists.

Check that the first boot really worked before going further:

```bash
petribox status work                                 # must show an IP
petribox connect work -- cloud-init status --long    # must say "done", not "error"
petribox connect work -- getent hosts github.com     # DNS works
```

> Why the packages/mise split: ripgrep lives in EPEL on Rocky. Cloud-init installs
> `packages` *before* EPEL is enabled, so asking for it there would fail the whole
> package step. Tools that mise provides avoid that problem.

## 3. Hand the dish a credential

Three ways. All of them end up in the same place.

```bash
# a) Hidden prompt: paste the value, nothing is echoed or saved to shell history
petribox env set work GITHUB_TOKEN

# b) Plain text: fine for throwaway tokens, but it lands in your shell history
#    (a leading space skips history if HISTCONTROL contains ignorespace)
petribox env set work GITHUB_TOKEN github_pat_xxx

# c) From your secret store: no typing, nothing pasted anywhere
#    ~/.config/petribox/config.toml
#      [secrets]
#      OPENAI_API_KEY = { cmd = "secret-tool lookup service openai" }
petribox env set work OPENAI_API_KEY
petribox create other --secret OPENAI_API_KEY        # also works at create time
```

For (c), the command runs **on the host**. `secret-tool` talks to any Secret
Service provider: KeePassXC (only the groups you expose under *Database settings →
Secret Service Integration*), GNOME Keyring or KWallet. `pass`, `op read` and
`bw get` work too. The dish only ever receives the value, never access to the store.

### Where the value lands, and how to verify it

```bash
petribox env list work                                       # values masked
petribox connect work -- ls -l .config/petribox/env          # -rw------- owned by the dish user
petribox connect work -- grep petribox/env .bashrc           # sourced by new shells
incus config show work | grep -c github_pat                  # 0: not in the instance config
```

The value travels over the stdin of `incus exec`. That's why it never shows up in
`ps` on the host, nor in the instance config that `incus config show`, snapshots
and exports carry.

> **Don't paste tokens into an AI chat.** If you run commands through an assistant
> (for example a `!` shell escape), anything you type ends up in its transcript.
> Use your own terminal for (a) and (b).

## 4. Example: clone and install a private GitHub repository

**Create the token** at GitHub → Settings → Developer settings → *Fine-grained
tokens*:

- Repository access: **Only select repositories** → `alice/webshop`
- Permissions: **Contents: Read-only** (add more only if the agent must push or
  open PRs)
- Expiration: as short as the task (e.g. 7 days)

**Push it into the dish** (step 3a), then inside the dish (`petribox connect work`)
tell git to read it from the environment:

```bash
git config --global credential.https://github.com.helper \
  '!f() { echo username=x-access-token; echo "password=$GITHUB_TOKEN"; }; f'
git clone https://github.com/alice/webshop
```

Why a credential helper instead of `https://<token>@github.com/...`: a URL with
the token gets saved in `.git/config`, shell history and error messages. The
helper reads the variable at the moment git asks, so the token stays in one
file. `gh` and `huggingface-cli` read `GITHUB_TOKEN` / `HF_TOKEN` from the
environment by themselves.

Then follow the project's own install steps inside the dish.

**When you're done:**

```bash
petribox env unset work GITHUB_TOKEN     # or: --all
```

…and revoke or let the token expire on GitHub. Expiry is the cleanup that works
even if you forget.

### Alternative that needs no token at all

If you only want the agent to *work on* the code:

```bash
git clone https://github.com/alice/webshop ~/src/webshop     # on the host, your credentials
petribox mount work ~/src/webshop /src/webshop
```

The agent edits `/src/webshop`. You review the diff on the host and push yourself.

## 5. Hugging Face

Public models need no token. To avoid both the token and the repeated
multi-GB download, share the host cache. Treat it as read-only for the agent:

```bash
petribox mount work ~/.cache/huggingface /home/petri/.cache/huggingface
```

For gated models, create a **fine-grained, read-only** token limited to those
repos and pass it as `HF_TOKEN` (step 3).

## 6. LLM API keys

Two levels, depending on how much you run.

**Simple: one key per dish.** OpenAI, Anthropic and OpenRouter let you create
many keys, each with its own spending limit. Give every dish its own key. If it
leaks, revoke that one key.

**Gateway: the real key never enters the dish.** Run an LLM gateway such as
[LiteLLM proxy](https://docs.litellm.ai/docs/simple_proxy) on the host, listening
only on the Incus bridge address (`ip -4 addr show incusbr0`). It involves three
kinds of keys:

| Key | Held by | Can |
|---|---|---|
| Provider keys (real OpenAI/OpenRouter/... keys) | the gateway only | make upstream calls |
| Gateway master key | the host only, **never a dish** | create, limit and revoke virtual keys |
| Virtual keys | one per dish or app | call allowed models within a budget |

Create a virtual key and give it to the dish:

```bash
curl -s http://<bridge-ip>:4000/key/generate \
  -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H 'Content-Type: application/json' \
  -d '{"key_alias": "dish-work", "max_budget": 5, "budget_duration": "30d", "models": ["openrouter/*"]}'
petribox env set work OPENAI_API_KEY             # paste the "key" from the response
petribox env set work OPENAI_BASE_URL http://<bridge-ip>:4000
```

The same gateway serves every other app on your machine. Keep a spending limit on
the provider accounts as well: budgets are counted after each response, so
parallel requests can overshoot a little, and the provider limit is your backstop.

## 7. Before you export or share a dish

`petribox export` copies the dish's disk, so the env file goes with it. Petribox
warns you and prints the cleanup:

```bash
petribox env unset work --all
petribox down work && petribox export work -o work.tar.gz
```

Snapshots taken earlier still contain the old file.

## 8. Troubleshooting

**Dish has no IPv4; cloud-init says `Could not resolve host`.** The host firewall
drops DHCP and DNS on the bridge. You'll see `status: error` in
`cloud-init status --long`, and `/var/log/cloud-init-output.log` shows every
download failing. For ufw:

```bash
sudo ufw allow in on incusbr0
sudo ufw route allow in on incusbr0
sudo ufw route allow out on incusbr0
```

Then delete and recreate the dish. Cloud-init runs only on the first boot, so a
restart won't redo the failed steps.

**`petribox create` hangs with no output, from a script or in the background.**
Older petribox versions let `incus init` inherit stdin. When stdin isn't a
terminal, `incus init` waits to read instance YAML from it. Upgrade petribox, or
run it with `< /dev/null`.

**First create is slow.** It downloads the base image (about 1 GB). Later creates
reuse the cache, until Incus refreshes it with the image server's newer daily build.

**Containers fail with `System doesn't have a functional idmap setup`.** The host
has no subordinate UID/GID ranges for Incus. Use VMs (the default), or add ranges
for root in `/etc/subuid` and `/etc/subgid` and restart Incus.

**Seeing what cloud-init did:**

```bash
petribox connect work -- cloud-init status --long
petribox connect work -- tail -50 /var/log/cloud-init-output.log
```

## Cheat sheet

```bash
petribox create work --preset minimal --config work.yaml [--secret KEY] [--env K=V]
petribox env set work KEY [VALUE] [--from-cmd "cmd"]   # no VALUE: config.toml, else hidden prompt
petribox env list work [--show]
petribox env unset work KEY | --all
petribox mount work HOST_DIR DISH_DIR                  # share instead of giving credentials
```
