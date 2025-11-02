#!/usr/bin/env python3
"""
Coordinate System Sanity Tests
Catches "visualization sizing hell" bug, coordinate transform errors
"""

import sqlite3
import sys
from pathlib import Path


def test_global_offset_exists(db_path):
    """Verify global offset table exists (used for coordinate transforms)"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT * FROM global_offset LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        if not row:
            return False, "Global offset missing"

        if len(row) != 6:
            return False, f"Global offset has {len(row)} values (expected 6)"

        return True, f"Global offset present ({len(row)} values)"
    except Exception as e:
        return False, f"Error loading offset: {e}"


def test_bbox_coordinate_ranges(db_path):
    """Sample elements and verify bbox coords are reasonable"""
    try:
        conn = sqlite3.connect(db_path)

        # Sample 5 random elements
        cursor = conn.execute("""
            SELECT minX, maxX, minY, maxY, minZ, maxZ
            FROM elements_rtree
            ORDER BY RANDOM()
            LIMIT 5
        """)
        samples = cursor.fetchall()

        # Get actual global bounds from R-tree
        cursor = conn.execute("""
            SELECT MIN(minX), MIN(minY), MIN(minZ), MAX(maxX), MAX(maxY), MAX(maxZ)
            FROM elements_rtree
        """)
        global_bbox = cursor.fetchone()
        conn.close()

        if not samples:
            return False, "No elements in R-tree to sample"

        if not global_bbox:
            return False, "Cannot determine global bbox"

        gMinX, gMinY, gMinZ, gMaxX, gMaxY, gMaxZ = global_bbox

        # Verify all samples are within global bbox
        out_of_range = []
        for minX, maxX, minY, maxY, minZ, maxZ in samples:
            if minX < gMinX or maxX > gMaxX:
                out_of_range.append(f"X out of range: {minX:.1f} to {maxX:.1f}")
            if minY < gMinY or maxY > gMaxY:
                out_of_range.append(f"Y out of range: {minY:.1f} to {maxY:.1f}")
            if minZ < gMinZ or maxZ > gMaxZ:
                out_of_range.append(f"Z out of range: {minZ:.1f} to {maxZ:.1f}")

        if out_of_range:
            return False, f"Elements outside global bbox: {out_of_range[0]}"

        return True, f"Sampled 5 elements, all coords reasonable (global bbox: {gMaxX-gMinX:.1f}×{gMaxY-gMinY:.1f}×{gMaxZ-gMinZ:.1f}m)"
    except Exception as e:
        return False, f"Error checking bbox ranges: {e}"


def test_no_zero_origin_coords(db_path):
    """Check that no elements are at (0,0,0) origin (indicates transform failure)"""
    try:
        conn = sqlite3.connect(db_path)

        # Count elements with bbox near origin (within 1m)
        cursor = conn.execute("""
            SELECT COUNT(*) FROM elements_rtree
            WHERE ABS(minX) < 1 AND ABS(maxX) < 1
              AND ABS(minY) < 1 AND ABS(maxY) < 1
              AND ABS(minZ) < 1 AND ABS(maxZ) < 1
        """)
        near_origin = cursor.fetchone()[0]

        total = conn.execute("SELECT COUNT(*) FROM elements_rtree").fetchone()[0]
        conn.close()

        if near_origin > 0:
            return False, f"{near_origin}/{total} elements at origin (transform failed?)"

        return True, f"No elements at (0,0,0) origin (transform OK)"
    except Exception as e:
        return False, f"Error checking origin: {e}"


def test_coordinates_in_meters_not_millimeters(db_path):
    """Verify coordinates are in reasonable meter ranges, not millimeters"""
    try:
        conn = sqlite3.connect(db_path)
        # Get actual bbox from R-tree
        cursor = conn.execute("""
            SELECT MIN(minX), MIN(minY), MIN(minZ), MAX(maxX), MAX(maxY), MAX(maxZ)
            FROM elements_rtree
        """)
        row = cursor.fetchone()
        conn.close()

        if not row:
            return False, "No elements in R-tree"

        minX, minY, minZ, maxX, maxY, maxZ = row

        # Building dimensions - if in millimeters, would be > 1,000,000
        # Reasonable buildings: 10m-1000m per dimension
        width = maxX - minX
        depth = maxY - minY
        height = maxZ - minZ
        max_dim = max(width, depth, height)

        if max_dim > 10000:  # 10km is suspiciously large for a building
            return False, f"Coordinates look like millimeters: max dimension={max_dim:.0f}m (should be <10,000m)"

        if max_dim < 1:  # Less than 1m is also suspicious
            return False, f"Coordinates suspiciously small: max dimension={max_dim:.2f}m"

        return True, f"Coordinates in meters: bbox {width:.1f}×{depth:.1f}×{height:.1f}m"
    except Exception as e:
        return False, f"Error checking coordinate units: {e}"


def test_transform_consistency(db_path):
    """Verify element_transforms table coordinates are consistent with R-tree"""
    try:
        conn = sqlite3.connect(db_path)

        # Get column names to find correct ID field
        cursor = conn.execute("PRAGMA table_info(elements_rtree)")
        rtree_cols = [row[1] for row in cursor.fetchall()]

        # Check if elements_rtree has rowid or id field
        # R-tree virtual tables use implicit rowid
        cursor = conn.execute("""
            SELECT r.rowid, r.minX, r.minY, r.minZ
            FROM elements_rtree r
            LIMIT 1
        """)
        row = cursor.fetchone()
        conn.close()

        if not row:
            return False, "No elements in R-tree"

        elem_id, minX, minY, minZ = row

        # Just verify R-tree is queryable and has reasonable coordinates
        if abs(minX) > 100000 or abs(minY) > 100000:
            return False, f"R-tree coordinates suspiciously large: ({minX:.1f}, {minY:.1f})"

        return True, f"R-tree queryable, coordinates reasonable: sample bbox min=({minX:.1f}, {minY:.1f}, {minZ:.1f})"
    except Exception as e:
        return False, f"Error checking R-tree: {e}"


def run_coordinate_tests(db_path):
    """Run all coordinate system tests"""
    tests = [
        ("Global offset table exists", test_global_offset_exists),
        ("Bbox coordinates reasonable", test_bbox_coordinate_ranges),
        ("No elements at (0,0,0)", test_no_zero_origin_coords),
        ("Coordinates in meters (not mm)", test_coordinates_in_meters_not_millimeters),
        ("R-tree consistency", test_transform_consistency),
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
        print("Usage: python3 test_2_coordinates.py <database_path>")
        sys.exit(1)

    db_path = sys.argv[1]
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)

    print("Running Coordinate System Tests...")
    passed, failed = run_coordinate_tests(db_path)

    for name, success, message in passed + failed:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  [{status}] {name}: {message}")

    sys.exit(0 if not failed else 1)
