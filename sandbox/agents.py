"""
Agent configurations for sandbox VMs.

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
        "mise_packages": ["python@3.12", "node@20"],
        "packages": ["git", "curl"],
        "repo": "https://github.com/NousResearch/hermes-agent",
        "setup_command": "hermes setup",
        "setup_notes": "Interactive setup - run in the VM terminal",
    },
    "openclaw": {
        "name": "OpenClaw",
        "description": "THE AI THAT ACTUALLY DOES THINGS. Clears your inbox, sends emails, manages your calendar, checks you in for flights. All from WhatsApp, Telegram, or any chat app you already use.",
        "install_script": "curl -fsSL https://openclaw.ai/install.sh | bash",
        "alt_install": "npm i -g openclaw",
        "mise_packages": ["node@20"],
        "packages": ["git", "curl"],
        "repo": None,
        "setup_command": "openclaw onboard",
        "setup_notes": "Interactive onboarding - run in the VM terminal",
    },
    "zeroclaw": {
        "name": "ZeroClaw",
        "description": "Personal AI Assistant. Zero overhead. Zero compromise. 100% Rust. 100% Agnostic. Runs on $10 hardware with <5MB RAM - 99% less memory than OpenClaw and 98% cheaper than a Mac mini!",
        "install_script": "git clone https://github.com/zeroclaw-labs/zeroclaw.git ~/zeroclaw && cd ~/zeroclaw && ./install.sh",
        "mise_packages": ["rust"],
        "packages": ["git", "curl", "build-essential"],
        "repo": "https://github.com/zeroclaw-labs/zeroclaw",
        "setup_command": './install.sh --api-key "sk-..." --provider openrouter',
        "setup_notes": "Non-interactive setup with API key, or use env vars: ZEROCLAW_API_KEY and ZEROCLAW_PROVIDER",
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
