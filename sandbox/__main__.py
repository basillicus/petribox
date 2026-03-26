#!/usr/bin/env python3
"""
Sandbox CLI Entry Point
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from sandbox.cli import main

if __name__ == "__main__":
    main()
