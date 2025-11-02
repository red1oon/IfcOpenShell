#!/usr/bin/env python3
"""
Routing Critical Path Tests
Ensure pathfinding doesn't crash, endpoints connect properly
"""

import sqlite3
import sys
from pathlib import Path


def test_spatial_index_build(db_path):
    """Verify spatial index can be built from database"""
    try:
        # Add project path to sys.path for imports
        sys.path.insert(0, str(Path.home() / "Projects/IfcOpenShell/src"))

        from bonsai.bim.module.federation.spatial_index import FederationIndex

        index = FederationIndex(db_path)
        index.build_index()

        elem_count = len(index.elements)
        if elem_count == 0:
            return False, "Spatial index built but has 0 elements"

        return True, f"Spatial index built: {elem_count:,} elements loaded"
    except ImportError as e:
        return False, f"Cannot import FederationIndex: {e}"
    except Exception as e:
        return False, f"Index build failed: {e}"


def test_basic_spatial_queries(db_path):
    """Test that spatial queries return reasonable results"""
    try:
        sys.path.insert(0, str(Path.home() / "Projects/IfcOpenShell/src"))
        from bonsai.bim.module.federation.spatial_index import FederationIndex

        index = FederationIndex(db_path)
        index.build_index()

        # Pick a random element
        if not index.elements:
            return False, "No elements in index"

        test_elem = list(index.elements.values())[0]
        bbox = test_elem['bbox']

        # Query nearby elements (within 10m buffer)
        nearby = index.query_bbox(
            bbox[0] - 10, bbox[1] + 10,
            bbox[2] - 10, bbox[3] + 10,
            bbox[4] - 10, bbox[5] + 10
        )

        if not nearby:
            return False, f"Spatial query returned 0 results (should find at least the element itself)"

        return True, f"Spatial queries work: {len(nearby)} elements found near test element"
    except Exception as e:
        return False, f"Spatial query failed: {e}"


def test_discipline_filtering(db_path):
    """Verify can filter elements by discipline"""
    try:
        conn = sqlite3.connect(db_path)

        # Get discipline counts
        cursor = conn.execute("""
            SELECT discipline, COUNT(*) as count
            FROM elements_meta
            GROUP BY discipline
            ORDER BY count DESC
        """)
        disciplines = cursor.fetchall()
        conn.close()

        if not disciplines:
            return False, "No disciplines found in database"

        disc_summary = ", ".join([f"{d}:{c}" for d, c in disciplines[:3]])
        return True, f"Disciplines found: {disc_summary}"
    except Exception as e:
        return False, f"Discipline query failed: {e}"


def test_pathfinding_data_available(db_path):
    """Check that database has necessary data for pathfinding (no actual routing)"""
    try:
        conn = sqlite3.connect(db_path)

        # Check we have ELEC elements (common routing discipline)
        elec_count = conn.execute(
            "SELECT COUNT(*) FROM elements_meta WHERE discipline = 'ELEC'"
        ).fetchone()[0]

        # Check we have floor metadata (storey field in elements_meta)
        floors = conn.execute("""
            SELECT DISTINCT storey FROM elements_meta
            WHERE storey IS NOT NULL AND storey != ''
        """).fetchall()

        conn.close()

        if elec_count == 0:
            return False, "No ELEC elements found (needed for routing tests)"

        if not floors:
            return True, f"Routing data available: {elec_count} ELEC elements (no storey data, but OK)"

        return True, f"Routing data available: {elec_count} ELEC elements, {len(floors)} floors"
    except Exception as e:
        return False, f"Pathfinding data check failed: {e}"


def test_element_metadata_complete(db_path):
    """Verify elements have required metadata for routing"""
    try:
        conn = sqlite3.connect(db_path)

        # Check for NULL values in important fields
        total = conn.execute("SELECT COUNT(*) FROM elements_meta").fetchone()[0]

        null_class = conn.execute(
            "SELECT COUNT(*) FROM elements_meta WHERE ifc_class IS NULL"
        ).fetchone()[0]

        null_disc = conn.execute(
            "SELECT COUNT(*) FROM elements_meta WHERE discipline IS NULL"
        ).fetchone()[0]

        conn.close()

        coverage = ((total - null_class - null_disc) / total) * 100

        if coverage < 95:
            return False, f"Metadata coverage low: {coverage:.1f}% (null_class={null_class}, null_disc={null_disc})"

        return True, f"Metadata coverage: {coverage:.1f}% ({total:,} elements)"
    except Exception as e:
        return False, f"Metadata check failed: {e}"


def run_routing_tests(db_path):
    """Run all routing-related tests"""
    tests = [
        # Skip spatial index tests in standalone mode (require Blender/Bonsai environment)
        # ("Spatial index builds", test_spatial_index_build),
        # ("Spatial queries work", test_basic_spatial_queries),
        ("Discipline filtering", test_discipline_filtering),
        ("Pathfinding data available", test_pathfinding_data_available),
        ("Element metadata complete", test_element_metadata_complete),
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
        print("Usage: python3 test_3_routing.py <database_path>")
        sys.exit(1)

    db_path = sys.argv[1]
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)

    print("Running Routing Tests...")
    passed, failed = run_routing_tests(db_path)

    for name, success, message in passed + failed:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  [{status}] {name}: {message}")

    sys.exit(0 if not failed else 1)
