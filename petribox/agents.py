"""
Agent configurations for petribox dishes.

Each agent defines:
- name: Display name
- description: What the agent does
- install_script: Command to install the agent (or None for manual)
- mise_packages: Language runtimes needed
- packages: System packages needed
- repo: Git repository URL (optional)
- setup_command: Command user runs after installation to configure
"""

AGENTS = {
    "hermes": {
        "name": "Hermes Agent",
        "description": "AI agent by NousResearch for autonomous task execution",
        "install_script": "curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash",
        "mise_packages": ["python@3.12", "node@24"],
        "packages": ["git", "curl"],
        "repo": "https://github.com/NousResearch/hermes-agent",
        "setup_command": "hermes setup",
        "setup_notes": "Interactive setup — run in the dish terminal",
    },
    "openclaw": {
        "name": "OpenClaw",
        "description": "Autonomous AI that handles email, calendar, and tasks from any chat app.",
        "install_script": "curl -fsSL https://openclaw.ai/install.sh | bash",
        "alt_install": "npm i -g openclaw",
        "mise_packages": ["node@24"],
        "packages": ["git", "curl"],
        "repo": None,
        "setup_command": "openclaw onboard",
        "setup_notes": "Interactive onboarding — run in the dish terminal",
    },
    "nemoclaw": {
        "name": "NemoClaw",
        "description": "NVIDIA's secure OpenClaw wrapper: network policy enforcement, routed inference, and operator approval workflows. Requires NVIDIA_API_KEY.",
        "install_script": "curl -fsSL https://www.nvidia.com/nemoclaw.sh | NEMOCLAW_ACCEPT_THIRD_PARTY_SOFTWARE=1 bash",
        "mise_packages": ["node@20"],
        "packages": ["git", "curl", "docker"],
        "repo": "https://github.com/NVIDIA/NemoClaw",
        "required_env": ["NVIDIA_API_KEY"],
        "setup_command": "nemoclaw init",
        "setup_notes": "Requires NVIDIA_API_KEY set in the environment before running",
    },
    "nullclaw": {
        "name": "NullClaw",
        "description": "678 KB static Zig binary AI agent. Boots in <8ms, uses ~1 MB RAM. Zero runtime dependencies.",
        "install_script": (
            # Prefer brew (works on Linux too); fall back to building from source via mise+zig.
            "if command -v brew >/dev/null 2>&1; then "
            "  brew install nullclaw; "
            "else "
            "  ~/.local/bin/mise use -g zig@latest && "
            "  git clone https://github.com/nullclaw/nullclaw.git ~/nullclaw && "
            "  cd ~/nullclaw && ~/.local/share/mise/shims/zig build -Doptimize=ReleaseSmall && "
            "  cp ./zig-out/bin/nullclaw ~/.local/bin/; "
            "fi"
        ),
        "mise_packages": [],
        "packages": ["git", "curl"],
        "repo": "https://github.com/nullclaw/nullclaw",
        "setup_command": "nullclaw --help",
        "setup_notes": "Static binary, no setup needed beyond installation",
    },
    "picoclaw": {
        "name": "PicoClaw",
        "description": "Ultra-lightweight Go AI assistant (~10 MB). Runs on Raspberry Pi, RISC-V, edge devices. 16+ chat integrations, MCP support, web UI.",
        "install_script": (
            "curl -fsSL https://github.com/sipeed/picoclaw/releases/latest/download/picoclaw_Linux_x86_64.tar.gz "
            "-o /tmp/picoclaw.tar.gz && "
            "tar -xzf /tmp/picoclaw.tar.gz -C /tmp && "
            "mv /tmp/picoclaw ~/.local/bin/picoclaw && "
            "chmod +x ~/.local/bin/picoclaw && "
            "rm /tmp/picoclaw.tar.gz"
        ),
        "mise_packages": [],
        "packages": ["curl", "tar"],
        "repo": "https://github.com/sipeed/picoclaw",
        "setup_command": "picoclaw onboard",
        "setup_notes": "Run 'picoclaw onboard' for first-time setup. Configure at ~/.picoclaw/config.json",
    },
    "loong": {
        "name": "Loong",
        "description": "Rust framework for building vertical AI agents. 42+ providers, 25+ channels (Slack, Lark, Discord). Extensible and transparent.",
        "install_script": "curl -fsSL https://raw.githubusercontent.com/eastreams/loong/dev/scripts/install.sh | bash -s -- --onboard",
        "mise_packages": ["rust"],
        "packages": ["git", "curl", "gcc", "gcc-c++", "make"],
        "repo": "https://github.com/eastreams/loong",
        "required_env": ["OPENAI_API_KEY"],
        "setup_command": "loong doctor --fix",
        "setup_notes": "Run 'loong' for interactive TUI, or 'loong ask --message ...' for one-shot queries",
    },
    "pi": {
        "name": "Pi Coding Agent",
        "description": "Minimal extensible terminal coding agent (TypeScript). No forced workflow — customise via plugins, prompt templates, and skills. Supports 20+ LLM providers.",
        "install_script": "npm install -g --ignore-scripts @earendil-works/pi-coding-agent",
        "alt_install": "curl -fsSL https://pi.dev/install.sh | sh",
        "mise_packages": ["node@24"],
        "packages": ["git", "curl"],
        "repo": "https://github.com/earendil-works/pi",
        "required_env": ["ANTHROPIC_API_KEY"],
        "setup_command": "pi --help",
        "setup_notes": "Set ANTHROPIC_API_KEY (or OPENAI_API_KEY) before running. Use /login for OAuth (Claude Pro, GitHub Copilot)",
    },
    "zeroclaw": {
        "name": "ZeroClaw",
        "description": "Rust-based personal AI assistant. <5 MB RAM, provider-agnostic.",
        "install_script": "git clone https://github.com/zeroclaw-labs/zeroclaw.git ~/zeroclaw && cd ~/zeroclaw && ./install.sh",
        "mise_packages": ["rust"],
        "packages": ["git", "curl", "gcc", "gcc-c++", "make"],
        "repo": "https://github.com/zeroclaw-labs/zeroclaw",
        "required_env": ["ZEROCLAW_API_KEY", "ZEROCLAW_PROVIDER"],
        "setup_command": './zeroclaw --api-key "sk-..." --provider openrouter',
        "setup_notes": "Set ZEROCLAW_API_KEY and ZEROCLAW_PROVIDER in the environment",
    },
}


def get_agent_config(agent_name: str) -> dict:
    """Get configuration for a specific agent"""
    if agent_name not in AGENTS:
        raise ValueError(f"Unknown agent: {agent_name}. Available: {list(AGENTS.keys())}")
    return AGENTS[agent_name]


def list_agents() -> dict:
    """Return all available agents"""
    return AGENTS
