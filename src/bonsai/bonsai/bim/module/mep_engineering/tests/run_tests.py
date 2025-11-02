#!/usr/bin/env python3
"""
MEP Engineering Module Test Runner
===================================

Simple test runner for MEP routing tests.
Usage: python3 run_tests.py [database_path]
"""

import sys
from pathlib import Path

# Import module tests
from test_routing import run_routing_tests


def run_all_tests(db_path=None):
    """Run all MEP engineering module tests"""
    print("="*70)
    print("MEP ENGINEERING MODULE TESTS")
    print("="*70)
    if db_path:
        print(f"Database: {db_path}")
    print()

    # Run routing tests
    passed, failed = run_routing_tests(db_path)

    # Display results
    for name, success, message in passed + failed:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  [{status}] {name}: {message}")

    total = len(passed) + len(failed)
    print(f"\nTotal: {len(passed)}/{total} tests passed")

    return 0 if not failed else 1


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else None
    sys.exit(run_all_tests(db_path))
