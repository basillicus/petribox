#!/usr/bin/env bash
# Sandbox CLI Wrapper Script
# Place this in your PATH (e.g., ~/bin/sandbox) to use the sandbox command

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SANDBOX_DIR="$(dirname "$SCRIPT_DIR")"

# Run the Python module
exec python3 -m sandbox "$@"
