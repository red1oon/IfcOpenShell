#!/usr/bin/env python3
"""
Database Schema Integrity Tests
Catches R-tree camelCase regression, column count mismatches
"""

import sqlite3
import sys
from pathlib import Path


def test_rtree_schema(db_path):
    """Verify R-tree uses camelCase (Oct 31 standard, commit 0a60f31d1)"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("PRAGMA table_info(elements_rtree)")
        columns = [row[1] for row in cursor.fetchall()]
        conn.close()

        expected = ['minX', 'maxX', 'minY', 'maxY', 'minZ', 'maxZ']
        missing = [col for col in expected if col not in columns]

        if missing:
            return False, f"Missing camelCase columns: {missing}. Found: {columns}"

        return True, f"R-tree schema correct: {', '.join(expected)}"
    except Exception as e:
        return False, f"Error checking R-tree schema: {e}"


def test_critical_tables_exist(db_path):
    """Verify critical tables exist"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        required = ['elements_meta', 'base_geometries', 'element_transforms', 'elements_rtree']
        missing = [t for t in required if t not in tables]

        if missing:
            return False, f"Missing tables: {missing}"

        return True, f"All critical tables exist ({len(required)}/{len(required)})"
    except Exception as e:
        return False, f"Error checking tables: {e}"


def test_column_counts(db_path):
    """Verify column counts match expected schema"""
    try:
        conn = sqlite3.connect(db_path)

        # elements_meta should have 11 columns (id, guid, discipline, ifc_class, etc.)
        cursor = conn.execute("PRAGMA table_info(elements_meta)")
        meta_cols = len(cursor.fetchall())

        # base_geometries should have 6 columns (geometry_hash, vertices, faces, etc.)
        cursor = conn.execute("PRAGMA table_info(base_geometries)")
        geom_cols = len(cursor.fetchall())

        conn.close()

        issues = []
        if meta_cols != 11:
            issues.append(f"elements_meta has {meta_cols} cols (expected 11)")
        if geom_cols != 6:
            issues.append(f"base_geometries has {geom_cols} cols (expected 6)")

        if issues:
            return False, "; ".join(issues)

        return True, f"Column counts correct: meta={meta_cols}, geom={geom_cols}"
    except Exception as e:
        return False, f"Error checking columns: {e}"


def test_no_null_violations(db_path):
    """Check for NULL values in critical columns"""
    try:
        conn = sqlite3.connect(db_path)

        # Check id (primary key, should never be NULL)
        null_ids = conn.execute(
            "SELECT COUNT(*) FROM elements_meta WHERE id IS NULL"
        ).fetchone()[0]

        # Check guid (should never be NULL)
        null_guid = conn.execute(
            "SELECT COUNT(*) FROM elements_meta WHERE guid IS NULL"
        ).fetchone()[0]

        # Check discipline (should never be NULL)
        null_disc = conn.execute(
            "SELECT COUNT(*) FROM elements_meta WHERE discipline IS NULL"
        ).fetchone()[0]

        conn.close()

        if null_ids > 0 or null_guid > 0 or null_disc > 0:
            return False, f"NULL violations: id={null_ids}, guid={null_guid}, discipline={null_disc}"

        return True, "No NULL violations in critical columns"
    except Exception as e:
        return False, f"Error checking NULLs: {e}"


def test_global_offset_table(db_path):
    """Verify global_offset table exists and has data"""
    try:
        conn = sqlite3.connect(db_path)

        # Check table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='global_offset'"
        )
        if not cursor.fetchone():
            conn.close()
            return False, "global_offset table missing"

        # Check has data (should be 1 row with 6 values: minX,minY,minZ,maxX,maxY,maxZ)
        cursor = conn.execute("SELECT * FROM global_offset LIMIT 1")
        row = cursor.fetchone()

        conn.close()

        if not row:
            return False, "global_offset table empty"

        if len(row) != 6:
            return False, f"global_offset has {len(row)} values (expected 6: minX,minY,minZ,maxX,maxY,maxZ)"

        return True, f"Global offset present: ({row[0]:.2f}, {row[1]:.2f}, {row[2]:.2f}) to ({row[3]:.2f}, {row[4]:.2f}, {row[5]:.2f})"
    except Exception as e:
        return False, f"Error checking global_offset: {e}"


def run_schema_tests(db_path):
    """Run all schema integrity tests"""
    tests = [
        ("R-tree camelCase schema", test_rtree_schema),
        ("Critical tables exist", test_critical_tables_exist),
        ("Column counts", test_column_counts),
        ("No NULL violations", test_no_null_violations),
        ("Global offset table", test_global_offset_table),
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
    if len(sys.argv) < 2:
        print("Usage: python3 test_1_schema.py <database_path>")
        sys.exit(1)

    db_path = sys.argv[1]
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)

    print("Running Schema Integrity Tests...")
    passed, failed = run_schema_tests(db_path)

    for name, success, message in passed + failed:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  [{status}] {name}: {message}")

    sys.exit(0 if not failed else 1)
