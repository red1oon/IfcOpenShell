#!/usr/bin/env python3
"""
Database Query Critical Path Tests
Ensure database helpers work correctly
"""

import sqlite3
import sys
from pathlib import Path


def test_database_module_import(db_path):
    """Verify database helper module can be imported"""
    try:
        sys.path.insert(0, str(Path.home() / "Projects/IfcOpenShell/src"))
        from bonsai.bim.module.federation_analysis.clash import database
        return True, "Database module imports successfully"
    except ImportError as e:
        return False, f"Cannot import database module: {e}"


def test_element_by_guid_query(db_path):
    """Test can query element by GUID"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get a test GUID
        cursor.execute("SELECT guid FROM elements_meta LIMIT 1")
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False, "No elements in database"

        test_guid = row[0]

        # Query element by GUID
        cursor.execute("""
            SELECT m.ifc_class, m.discipline,
                   r.minX, r.maxX, r.minY, r.maxY, r.minZ, r.maxZ
            FROM elements_meta m
            JOIN elements_rtree r ON m.id = r.id
            WHERE m.guid = ?
        """, (test_guid,))

        result = cursor.fetchone()
        conn.close()

        if not result:
            return False, f"GUID query returned no results for {test_guid}"

        ifc_class, discipline = result[0], result[1]
        return True, f"GUID query works: {ifc_class} ({discipline})"

    except Exception as e:
        return False, f"Test failed: {e}"


def test_bbox_center_calculation(db_path):
    """Test bbox center calculation from database"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Query bbox
        cursor.execute("""
            SELECT minX, maxX, minY, maxY, minZ, maxZ
            FROM elements_rtree
            LIMIT 1
        """)
        row = cursor.fetchone()
        conn.close()

        if not row:
            return False, "No bbox data in database"

        minX, maxX, minY, maxY, minZ, maxZ = row

        # Calculate center
        cx = (minX + maxX) / 2
        cy = (minY + maxY) / 2
        cz = (minZ + maxZ) / 2

        # Validate center is within bbox
        if not (minX <= cx <= maxX and minY <= cy <= maxY and minZ <= cz <= maxZ):
            return False, f"Calculated center ({cx}, {cy}, {cz}) outside bbox"

        return True, f"Bbox center calculation: ({cx:.1f}, {cy:.1f}, {cz:.1f})"

    except Exception as e:
        return False, f"Test failed: {e}"


def test_coordinate_offset_query(db_path):
    """Test can query coordinate offset from database"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if coordinate_offset table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='coordinate_offset'")
        if not cursor.fetchone():
            conn.close()
            return True, "coordinate_offset table not found (optional feature)"

        # Query offset
        cursor.execute("SELECT offset_x, offset_y, offset_z FROM coordinate_offset LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        if not row:
            return True, "coordinate_offset table empty (offset will be calculated from elements)"

        offset_x, offset_y, offset_z = row
        return True, f"Coordinate offset: ({offset_x:.1f}, {offset_y:.1f}, {offset_z:.1f})"

    except Exception as e:
        return False, f"Test failed: {e}"


def test_discipline_filter_query(db_path):
    """Test discipline filtering query performance"""
    try:
        import time
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get first discipline
        cursor.execute("SELECT DISTINCT discipline FROM elements_meta WHERE discipline IS NOT NULL LIMIT 1")
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False, "No disciplines found in database"

        test_discipline = row[0]

        # Time discipline filter query
        start = time.time()
        cursor.execute("""
            SELECT COUNT(*)
            FROM elements_meta
            WHERE discipline = ?
        """, (test_discipline,))
        count = cursor.fetchone()[0]
        elapsed_ms = (time.time() - start) * 1000
        conn.close()

        if elapsed_ms > 50:
            return False, f"Discipline filter too slow: {elapsed_ms:.1f}ms (should be <50ms)"

        return True, f"Discipline filter: {count} elements ({test_discipline}) in {elapsed_ms:.1f}ms"

    except Exception as e:
        return False, f"Test failed: {e}"


def get_tests():
    """Return list of (test_name, test_function) tuples"""
    return [
        ("Database Module Import", test_database_module_import),
        ("Element by GUID Query", test_element_by_guid_query),
        ("Bbox Center Calculation", test_bbox_center_calculation),
        ("Coordinate Offset Query", test_coordinate_offset_query),
        ("Discipline Filter Query", test_discipline_filter_query),
    ]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_4_database_queries.py <database_path>")
        sys.exit(1)

    db_path = sys.argv[1]
    print(f"\nTesting: {db_path}\n")

    for test_name, test_func in get_tests():
        success, message = test_func(db_path)
        status = "✅" if success else "❌"
        print(f"{status} {test_name}: {message}")
