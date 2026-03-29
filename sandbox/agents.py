"""
Agent configurations for sandbox VMs.

Each agent defines:
- install_script: Command to install the agent
- mise_packages: Language runtimes needed
- packages: System packages needed
- description: What the agent does
"""

AGENTS = {
    "hermes": {
        "name": "Hermes Agent",
        "description": "AI agent by NousResearch for autonomous task execution",
        "install_script": "curl -fsSL https://raw.githubusercontent.com/NousResearch/hermes-agent/main/scripts/install.sh | bash",
        "mise_packages": ["python@3.12", "node@20"],
        "packages": ["git", "curl"],
        "repo": "https://github.com/NousResearch/hermes-agent",
    },
    "openclaw": {
        "name": "OpenClaw",
        "description": "Open-source AI coding assistant",
        "install_script": None,
        "mise_packages": ["python@3.12", "node@20"],
        "packages": ["git", "curl"],
        "repo": None,
    },
    "zeroclaw": {
        "name": "ZeroClaw",
        "description": "Research-focused AI assistant",
        "install_script": None,
        "mise_packages": ["python@3.12"],
        "packages": ["git", "curl"],
        "repo": None,
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
