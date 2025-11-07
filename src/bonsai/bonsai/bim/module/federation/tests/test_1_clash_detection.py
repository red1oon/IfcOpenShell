#!/usr/bin/env python3
"""
Clash Detection Critical Path Tests
Ensure R-tree queries work, clashes can be detected, discipline filtering works
"""

import sqlite3
import sys
from pathlib import Path


def test_clash_detector_import(db_path):
    """Verify clash detector module can be imported"""
    try:
        # Try importing from parent directory structure
        test_dir = Path(__file__).parent
        module_dir = test_dir.parent
        sys.path.insert(0, str(module_dir))

        from clash import detector
        return True, "Clash detector module imports successfully"
    except ImportError as e:
        return False, f"Cannot import clash detector: {e}"
    except Exception as e:
        return False, f"Import error: {e}"


def test_rtree_spatial_query(db_path):
    """Test R-tree spatial queries for clash detection"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check R-tree table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='elements_rtree'")
        if not cursor.fetchone():
            conn.close()
            return False, "elements_rtree table not found"

        # Check camelCase schema (Oct 31 standard)
        cursor.execute("PRAGMA table_info(elements_rtree)")
        columns = {row[1] for row in cursor.fetchall()}
        expected = {'id', 'minX', 'maxX', 'minY', 'maxY', 'minZ', 'maxZ'}

        if expected.issubset(columns):
            schema_ok = True
        else:
            missing = expected - columns
            conn.close()
            return False, f"R-tree schema missing columns: {missing}"

        # Test bbox query
        cursor.execute("""
            SELECT id, minX, maxX, minY, maxY, minZ, maxZ
            FROM elements_rtree
            LIMIT 1
        """)
        row = cursor.fetchone()

        if not row:
            conn.close()
            return False, "R-tree has no data"

        test_id, minX, maxX, minY, maxY, minZ, maxZ = row

        # Query overlapping elements (expand bbox by 0.1m)
        cursor.execute("""
            SELECT COUNT(*)
            FROM elements_rtree
            WHERE maxX >= ? AND minX <= ?
              AND maxY >= ? AND minY <= ?
              AND maxZ >= ? AND minZ <= ?
        """, (minX - 0.1, maxX + 0.1, minY - 0.1, maxY + 0.1, minZ - 0.1, maxZ + 0.1))

        overlap_count = cursor.fetchone()[0]
        conn.close()

        if overlap_count == 0:
            return False, "R-tree spatial query returned 0 results (should find at least test element)"

        return True, f"R-tree queries work: {overlap_count} overlaps found for test element"

    except sqlite3.Error as e:
        return False, f"Database error: {e}"
    except Exception as e:
        return False, f"Test failed: {e}"


def test_discipline_clash_candidates(db_path):
    """Test cross-discipline clash candidate generation"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get two different disciplines
        cursor.execute("""
            SELECT DISTINCT discipline
            FROM elements_meta
            WHERE discipline IS NOT NULL
            ORDER BY discipline
            LIMIT 2
        """)
        disciplines = cursor.fetchall()

        if len(disciplines) < 2:
            conn.close()
            return False, f"Need at least 2 disciplines for testing (found {len(disciplines)})"

        disc_a, disc_b = disciplines[0][0], disciplines[1][0]

        # Query potential clashes between disciplines
        cursor.execute("""
            SELECT COUNT(*)
            FROM elements_meta m1
            JOIN elements_rtree r1 ON m1.id = r1.id
            JOIN elements_meta m2 ON m2.discipline = ?
            JOIN elements_rtree r2 ON m2.id = r2.id
            WHERE m1.discipline = ?
              AND m1.id != m2.id
              AND r1.maxX >= r2.minX AND r1.minX <= r2.maxX
              AND r1.maxY >= r2.minY AND r1.minY <= r2.maxY
              AND r1.maxZ >= r2.minZ AND r1.minZ <= r2.maxZ
            LIMIT 100
        """, (disc_b, disc_a))

        clash_count = cursor.fetchone()[0]
        conn.close()

        if clash_count == 0:
            return True, f"No clashes between {disc_a} and {disc_b} (valid result)"

        return True, f"Cross-discipline clash candidates: {clash_count} potential clashes ({disc_a} vs {disc_b})"

    except sqlite3.Error as e:
        return False, f"Database error: {e}"
    except Exception as e:
        return False, f"Test failed: {e}"


def test_guid_lookup_performance(db_path):
    """Test GUID lookup speed (critical for clash details)"""
    try:
        import time
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get 10 random GUIDs
        cursor.execute("SELECT guid FROM elements_meta LIMIT 10")
        guids = [row[0] for row in cursor.fetchall()]

        if not guids:
            conn.close()
            return False, "No GUIDs found in database"

        # Time GUID lookups
        start = time.time()
        for guid in guids:
            cursor.execute("""
                SELECT m.ifc_class, r.minX, r.maxX, r.minY, r.maxY, r.minZ, r.maxZ
                FROM elements_meta m
                JOIN elements_rtree r ON m.id = r.id
                WHERE m.guid = ?
            """, (guid,))
            row = cursor.fetchone()
            if not row:
                conn.close()
                return False, f"GUID lookup failed for {guid}"

        elapsed = time.time() - start
        conn.close()

        avg_time_ms = (elapsed / len(guids)) * 1000

        if avg_time_ms > 10:
            return False, f"GUID lookups too slow: {avg_time_ms:.2f}ms average (should be <10ms)"

        return True, f"GUID lookup performance: {avg_time_ms:.2f}ms average ({len(guids)} lookups)"

    except Exception as e:
        return False, f"Test failed: {e}"


def get_tests():
    """Return list of (test_name, test_function) tuples"""
    return [
        ("Clash Detector Import", test_clash_detector_import),
        ("R-tree Spatial Query", test_rtree_spatial_query),
        ("Discipline Clash Candidates", test_discipline_clash_candidates),
        ("GUID Lookup Performance", test_guid_lookup_performance),
    ]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_1_clash_detection.py <database_path>")
        sys.exit(1)

    db_path = sys.argv[1]
    print(f"\nTesting: {db_path}\n")

    for test_name, test_func in get_tests():
        success, message = test_func(db_path)
        status = "✅" if success else "❌"
        print(f"{status} {test_name}: {message}")
