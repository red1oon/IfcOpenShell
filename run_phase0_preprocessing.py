#!/usr/bin/env python3
"""
Wrapper script to run Phase 0 preprocessing outside the federation module directory
This avoids circular import issues with operator.py
"""

import sys
from pathlib import Path

# Add src to path before importing any modules
sys.path.insert(0, str(Path(__file__).parent / "src"))

if __name__ == "__main__":
    # Now import after path is set
    from bonsai.bonsai.bim.module.federation import federation_preprocessor

    # Override sys.argv to pass arguments
    sys.argv = [
        "federation_preprocessor.py",
        "--files",
        "/home/red1/Documents/bonsai/PythonLibs/IFC/SJTII-ARC-A-TER1-00-R0.ifc",
        "/home/red1/Documents/bonsai/PythonLibs/IFC/SJTII-STR-S-TER1-00-R1.ifc",
        "/home/red1/Documents/bonsai/PythonLibs/IFC/SJTII-CW-A-TER1-00-R0.ifc",
        "/home/red1/Documents/bonsai/PythonLibs/IFC/SJTII-ELEC-A-TER1-00-R0.ifc",
        "/home/red1/Documents/bonsai/PythonLibs/IFC/SJTII-ACMV-A-TER1-00-R0.ifc",
        "/home/red1/Documents/bonsai/PythonLibs/IFC/SJTII-FP-A-TER1-00-R0.ifc",
        "/home/red1/Documents/bonsai/PythonLibs/IFC/SJTII-SP-A-TER1-00-R0.ifc",
        "--disciplines", "ARC", "STR", "CW", "ELEC", "ACMV", "FP", "SP",
        "--output", "/home/red1/Documents/bonsai/federation_index.db"
    ]

    # Run the main function
    exit(federation_preprocessor.main())
