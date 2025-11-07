#!/usr/bin/env python3
"""
Federation Analysis Add-on Test Suite
======================================

Run all unit tests for the federation_analysis add-on module.

Usage:
    python3 run_tests.py <database_path>

Example:
    cd ~/Projects/IfcOpenShell/src/bonsai/bonsai/bim/module/federation_analysis/tests
    python3 run_tests.py ~/Documents/bonsai/DatabaseFiles/sample_extracted_v3.db
"""

import sys
import sqlite3
from pathlib import Path

# Add project path for imports
sys.path.insert(0, str(Path.home() / "Projects/IfcOpenShell/src"))

# Import test modules
import test_1_clash_detection
import test_2_routing_pathfinding
import test_3_visualization_shapes
import test_4_database_queries


def run_all_tests(db_path):
    """Run all regression tests for federation_analysis add-on"""

    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        return False

    print(f"\n{'='*70}")
    print(f"FEDERATION ANALYSIS ADD-ON TEST SUITE")
    print(f"{'='*70}")
    print(f"Database: {db_path}")
    print(f"Size: {Path(db_path).stat().st_size / 1024 / 1024:.1f} MB")

    # Get element count
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM elements_meta")
        elem_count = cursor.fetchone()[0]
        conn.close()
        print(f"Elements: {elem_count:,}")
    except Exception as e:
        print(f"⚠️  Cannot read database: {e}")
        return False

    print(f"{'='*70}\n")

    # Test suites
    test_suites = [
        ("Clash Detection", test_1_clash_detection.get_tests()),
        ("Routing & Pathfinding", test_2_routing_pathfinding.get_tests()),
        ("Visualization & Shapes", test_3_visualization_shapes.get_tests()),
        ("Database Queries", test_4_database_queries.get_tests()),
    ]

    total_tests = 0
    passed_tests = 0
    failed_tests = []

    for suite_name, tests in test_suites:
        print(f"\n{'='*70}")
        print(f"{suite_name}")
        print(f"{'='*70}")

        for test_name, test_func in tests:
            total_tests += 1
            try:
                success, message = test_func(db_path)
                if success:
                    print(f"✅ {test_name}: {message}")
                    passed_tests += 1
                else:
                    print(f"❌ {test_name}: {message}")
                    failed_tests.append((suite_name, test_name, message))
            except Exception as e:
                print(f"💥 {test_name}: CRASHED - {e}")
                failed_tests.append((suite_name, test_name, f"Exception: {e}"))

    # Summary
    print(f"\n{'='*70}")
    print(f"TEST SUMMARY")
    print(f"{'='*70}")
    print(f"Total:  {total_tests}")
    print(f"Passed: {passed_tests} ({passed_tests/total_tests*100:.1f}%)")
    print(f"Failed: {len(failed_tests)}")

    if failed_tests:
        print(f"\n{'='*70}")
        print(f"FAILED TESTS")
        print(f"{'='*70}")
        for suite, name, msg in failed_tests:
            print(f"❌ [{suite}] {name}")
            print(f"   {msg}")

    print(f"\n{'='*70}\n")

    return len(failed_tests) == 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 run_tests.py <database_path>")
        print(f"\nExample:")
        print(f"  python3 run_tests.py ~/Documents/bonsai/DatabaseFiles/sample_extracted_v3.db")
        sys.exit(1)

    db_path = sys.argv[1]
    success = run_all_tests(db_path)
    sys.exit(0 if success else 1)
