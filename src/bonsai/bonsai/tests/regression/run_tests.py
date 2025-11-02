#!/usr/bin/env python3
"""
Fast Regression Test Runner (Python mode - no Blender)
Usage: python3 run_tests.py <database_path>
Trigger phrase: "test the db"
"""

import sys
import time
from pathlib import Path

# Import test modules
from test_1_schema import run_schema_tests
from test_2_coordinates import run_coordinate_tests
from test_3_routing import run_routing_tests
from test_4_materials import run_material_tests


def run_all_tests(db_path):
    """Run all Python-based regression tests"""
    tests = [
        ("Schema Integrity", run_schema_tests),
        ("Coordinate System", run_coordinate_tests),
        ("Routing Critical Path", run_routing_tests),
        ("Material Data Quality", run_material_tests),
    ]

    print("="*70)
    print("FEDERATION DATABASE REGRESSION TESTS (Python Mode)")
    print("="*70)
    print(f"Database: {db_path}")

    # Check database size
    db_size_mb = Path(db_path).stat().st_size / (1024 * 1024)
    print(f"Size: {db_size_mb:.1f} MB")
    print("="*70)

    start_time = time.time()
    results = []

    for name, test_func in tests:
        print(f"\n{'='*70}")
        print(f"Testing: {name}")
        print(f"{'='*70}")

        try:
            passed, failed = test_func(db_path)
            results.append((name, passed, failed))

            for test_name, success, message in passed + failed:
                status = "✓ PASS" if success else "✗ FAIL"
                print(f"  [{status}] {test_name}: {message}")

        except Exception as e:
            print(f"  [✗ CRASH] {name} crashed with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, [], [(name, False, str(e))]))

    # Summary
    elapsed = time.time() - start_time
    total_passed = sum(len(p) for _, p, _ in results)
    total_failed = sum(len(f) for _, _, f in results)

    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"Total: {total_passed + total_failed} tests")
    print(f"Passed: {total_passed} ✓")
    print(f"Failed: {total_failed} ✗")
    print(f"Time: {elapsed:.1f} seconds")
    print(f"{'='*70}")

    if total_failed > 0:
        print(f"\n❌ REGRESSION DETECTED - {total_failed} test(s) failed")
        print("\nFailed tests:")
        for cat_name, _, failed in results:
            for test_name, success, message in failed:
                print(f"  • {cat_name}: {test_name}")
                print(f"    └─ {message}")
        return 1
    else:
        print(f"\n✅ ALL TESTS PASSED")
        return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 run_tests.py <database_path>")
        print("\nOr use: ./run_tests.sh (auto-detects latest DB)")
        sys.exit(1)

    db_path = sys.argv[1]
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)

    sys.exit(run_all_tests(db_path))
