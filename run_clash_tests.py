#!/usr/bin/env python3
"""
Wrapper script to run clash tests safely
Avoids name conflicts by running from project root
"""

import sys
import subprocess
from pathlib import Path

# Get absolute path to test file
test_file = Path(__file__).parent / "src/bonsai/bonsai/bim/module/clash/test_gizmo_and_database.py"

# Run with python from project root (outside clash module)
result = subprocess.run(
    [sys.executable, str(test_file)],
    cwd=str(Path(__file__).parent),
    capture_output=False
)

sys.exit(result.returncode)
