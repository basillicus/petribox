"""
Configuration presets - the single source of truth.

Previously duplicated (and divergent) across commands.py and tui.py. Each preset
carries recommended resources (used as TUI/CLI defaults) plus the package config
(system packages, mise runtimes, pip packages) folded into cloud-init.
"""

from __future__ import annotations

PRESETS: dict[str, dict] = {
    "minimal": {
        "description": "Basic tools (vim, python3, git, curl)",
        "ram": 2048,
        "cpus": 1,
        "disk": 15,
        "packages": ["vim", "python3", "git", "curl"],
    },
    "dev": {
        "description": "General development (gcc, make, node@24 via mise)",
        "ram": 4096,
        "cpus": 2,
        "disk": 25,
        "packages": ["vim", "python3", "git", "curl", "wget", "gcc", "make"],
        "mise_packages": ["node@24"],
    },
    "ai-researcher": {
        "description": "ML/AI work (python@3.12, Jupyter, numpy, pandas, sklearn)",
        "ram": 8192,
        "cpus": 4,
        "disk": 40,
        "packages": ["vim", "python3", "python3-pip", "git", "curl", "wget", "gcc", "tmux"],
        "mise_packages": ["python@3.12"],
        "pip_packages": ["jupyterlab", "numpy", "pandas", "matplotlib", "scikit-learn"],
    },
    "agentic": {
        "description": "Agentic AI (python@3.12 + node@24, LangChain, Docker)",
        "ram": 8192,
        "cpus": 4,
        "disk": 50,
        "packages": ["vim", "python3", "python3-pip", "git", "curl", "wget", "tmux", "docker"],
        "mise_packages": ["python@3.12", "node@24"],
        "pip_packages": ["jupyterlab", "langchain", "langgraph", "pydantic", "httpx"],
    },
}

PRESET_NAMES = list(PRESETS.keys())

# Keys that describe software to install (as opposed to resource sizing).
_PACKAGE_KEYS = ("packages", "mise_packages", "pip_packages", "runcmd", "environment")


def get_preset(name: str) -> dict:
    """Return a copy of a preset (list values copied too), or {} if unknown."""
    preset = PRESETS.get(name, {})
    return {k: (list(v) if isinstance(v, list) else v) for k, v in preset.items()}


def package_config(name: str) -> dict:
    """Return only the install-related portion of a preset (for cloud-init)."""
    preset = PRESETS.get(name, {})
    return {k: list(v) for k, v in preset.items() if k in _PACKAGE_KEYS}


def merge_config(base: dict, override: dict) -> dict:
    """Merge two package configs, unioning list fields while preserving order."""
    result = {k: list(v) if isinstance(v, list) else v for k, v in base.items()}
    for key, value in override.items():
        if isinstance(value, list) and isinstance(result.get(key), list):
            for item in value:
                if item not in result[key]:
                    result[key].append(item)
        else:
            result[key] = value
    return result
