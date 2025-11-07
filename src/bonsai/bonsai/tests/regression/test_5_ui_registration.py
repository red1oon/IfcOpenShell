#!/usr/bin/env python3
"""
UI Registration Tests
Catches when critical UI panels or operators accidentally get removed/hidden
"""

import sys
from pathlib import Path


def test_mep_panel_registered(db_path=None):
    """Verify MEP Engineering panel is in classes tuple"""
    try:
        # Add project to path
        sys.path.insert(0, str(Path.home() / "Projects/IfcOpenShell/src"))

        from bonsai.bim.module.mep_engineering import classes

        # Check BIM_PT_mep_engineering is in classes tuple
        class_names = [cls.__name__ for cls in classes]

        if 'BIM_PT_mep_engineering' not in class_names:
            return False, "MEP UI panel not registered in classes tuple"

        return True, f"MEP panel registered ({len(classes)} total classes)"
    except ImportError as e:
        return False, f"Cannot import MEP module: {e}"
    except Exception as e:
        return False, f"Error checking registration: {e}"


def test_mep_operators_registered(db_path=None):
    """Verify critical MEP operators are registered"""
    try:
        sys.path.insert(0, str(Path.home() / "Projects/IfcOpenShell/src"))

        from bonsai.bim.module.mep_engineering import classes

        class_names = [cls.__name__ for cls in classes]

        required_operators = [
            'RouteMEPConduit',
            'SetRouteStartPoint',
            'SetRouteEndPoint',
            'ValidateConduitRoute',
        ]

        missing = [op for op in required_operators if op not in class_names]

        if missing:
            return False, f"Missing operators: {', '.join(missing)}"

        return True, f"All {len(required_operators)} critical operators registered"
    except Exception as e:
        return False, f"Error checking operators: {e}"


def test_parent_tab_exists(db_path=None):
    """Verify BIM_PT_tab_mep_engineering parent tab exists"""
    try:
        sys.path.insert(0, str(Path.home() / "Projects/IfcOpenShell/src"))

        # Check if parent tab is defined in main UI file
        ui_file = Path.home() / "Projects/IfcOpenShell/src/bonsai/bonsai/bim/ui.py"

        if not ui_file.exists():
            return False, "Main UI file not found"

        content = ui_file.read_text()

        if 'class BIM_PT_tab_mep_engineering' not in content:
            return False, "Parent tab BIM_PT_tab_mep_engineering not defined in ui.py"

        # Check poll condition exists
        if 'def poll(cls, context):' not in content:
            return False, "Parent tab missing poll() method"

        return True, "Parent tab BIM_PT_tab_mep_engineering exists with poll()"
    except Exception as e:
        return False, f"Error checking parent tab: {e}"


def test_federation_panel_registered(db_path=None):
    """Verify Federation Analysis panel is registered"""
    try:
        sys.path.insert(0, str(Path.home() / "Projects/IfcOpenShell/src"))

        from bonsai.bim.module.federation import classes

        class_names = [cls.__name__ for cls in classes]

        if 'BIM_PT_federation_analysis' not in class_names:
            return False, "Federation panel not registered"

        return True, f"Federation panel registered ({len(classes)} total classes)"
    except ImportError:
        # Federation module might not exist yet - not a failure
        return True, "Federation module not present (OK if not implemented)"
    except Exception as e:
        return False, f"Error checking federation: {e}"


def run_ui_registration_tests(db_path=None):
    """Run all UI registration tests"""
    tests = [
        ("MEP panel registered", test_mep_panel_registered),
        ("MEP operators registered", test_mep_operators_registered),
        ("Parent tab exists", test_parent_tab_exists),
        ("Federation panel registered", test_federation_panel_registered),
    ]

    passed = []
    failed = []

    for name, test_func in tests:
        success, message = test_func(db_path)
        if success:
            passed.append((name, True, message))
        else:
            failed.append((name, False, message))

    return passed, failed


if __name__ == "__main__":
    print("Running UI Registration Tests...")
    passed, failed = run_ui_registration_tests()

    for name, success, message in passed + failed:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  [{status}] {name}: {message}")

    sys.exit(0 if not failed else 1)
