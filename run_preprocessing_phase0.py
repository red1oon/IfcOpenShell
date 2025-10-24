#!/usr/bin/env python3
"""
Standalone script to run federation preprocessing with Phase 0 changes
"""

import sys
import os
from pathlib import Path

# Add Bonsai module to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Now import and run the preprocessing
from bonsai.bonsai.bim.module.federation.federation_preprocessor import main

if __name__ == "__main__":
    print("=" * 80)
    print("RUNNING FEDERATION PREPROCESSING - PHASE 0")
    print("=" * 80)
    print()

    main()
