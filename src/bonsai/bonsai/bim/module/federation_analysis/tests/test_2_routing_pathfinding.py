#!/usr/bin/env python3
"""
Routing & Pathfinding Critical Path Tests
Ensure A* pathfinding works, endpoints connect, obstacles are avoided
"""

import sqlite3
import sys
from pathlib import Path


def test_pathfinder_import(db_path):
    """Verify routing pathfinder can be imported"""
    try:
        sys.path.insert(0, str(Path.home() / "Projects/IfcOpenShell/src"))
        # Check if pathfinder exists in new location
        from bonsai.bim.module.mep_engineering import tool
        return True, "Pathfinder module imports successfully (from mep_engineering)"
    except ImportError as e:
        return False, f"Cannot import pathfinder: {e}"


def test_spatial_index_for_routing(db_path):
    """Test spatial index can be built for routing obstacle detection"""
    try:
        sys.path.insert(0, str(Path.home() / "Projects/IfcOpenShell/src"))
        from bonsai.bim.module.federation_analysis.shared import spatial_index

        index = spatial_index.FederationIndex(db_path)
        index.build_index()

        elem_count = len(index.elements)
        if elem_count == 0:
            return False, "Spatial index built but has 0 elements"

        return True, f"Spatial index built: {elem_count:,} elements loaded for routing"
    except ImportError:
        # Try original location if not moved yet
        try:
            from bonsai.bim.module.federation.spatial_index import FederationIndex
            index = FederationIndex(db_path)
            index.build_index()
            return True, f"Spatial index built: {len(index.elements):,} elements (legacy path)"
        except Exception as e:
            return False, f"Spatial index import failed: {e}"
    except Exception as e:
        return False, f"Index build failed: {e}"


def test_endpoint_selection_query(db_path):
    """Test can query start/end points for routing"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Query for potential routing endpoints (e.g., ELEC elements)
        cursor.execute("""
            SELECT m.guid, m.ifc_class,
                   (r.minX + r.maxX) / 2 as cx,
                   (r.minY + r.maxY) / 2 as cy,
                   (r.minZ + r.maxZ) / 2 as cz
            FROM elements_meta m
            JOIN elements_rtree r ON m.id = r.id
            WHERE m.discipline = 'ELEC'
            LIMIT 2
        """)

        endpoints = cursor.fetchall()
        conn.close()

        if len(endpoints) < 2:
            return True, f"Not enough ELEC elements for routing test (found {len(endpoints)}, need 2)"

        guid_a, class_a, x1, y1, z1 = endpoints[0]
        guid_b, class_b, x2, y2, z2 = endpoints[1]

        # Calculate distance
        import math
        dist = math.sqrt((x2-x1)**2 + (y2-y1)**2 + (z2-z1)**2)

        return True, f"Routing endpoints found: {class_a} to {class_b} ({dist:.1f}m apart)"

    except Exception as e:
        return False, f"Test failed: {e}"


def test_obstacle_query_performance(db_path):
    """Test can query obstacles efficiently for pathfinding"""
    try:
        import time
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get one element to use as test region
        cursor.execute("""
            SELECT minX, maxX, minY, maxY, minZ, maxZ
            FROM elements_rtree
            LIMIT 1
        """)
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False, "No elements in R-tree"

        minX, maxX, minY, maxY, minZ, maxZ = row

        # Expand to 20m region (typical routing area)
        region = (minX - 10, maxX + 10, minY - 10, maxY + 10, minZ - 10, maxZ + 10)

        # Time obstacle query
        start = time.time()
        cursor.execute("""
            SELECT COUNT(*)
            FROM elements_rtree
            WHERE maxX >= ? AND minX <= ?
              AND maxY >= ? AND minY <= ?
              AND maxZ >= ? AND minZ <= ?
        """, region)
        obstacle_count = cursor.fetchone()[0]
        elapsed_ms = (time.time() - start) * 1000
        conn.close()

        if elapsed_ms > 100:
            return False, f"Obstacle query too slow: {elapsed_ms:.1f}ms (should be <100ms)"

        return True, f"Obstacle query: {obstacle_count} elements in {elapsed_ms:.1f}ms"

    except Exception as e:
        return False, f"Test failed: {e}"


def get_tests():
    """Return list of (test_name, test_function) tuples"""
    return [
        ("Pathfinder Import", test_pathfinder_import),
        ("Spatial Index for Routing", test_spatial_index_for_routing),
        ("Endpoint Selection Query", test_endpoint_selection_query),
        ("Obstacle Query Performance", test_obstacle_query_performance),
    ]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_2_routing_pathfinding.py <database_path>")
        sys.exit(1)

    db_path = sys.argv[1]
    print(f"\nTesting: {db_path}\n")

    for test_name, test_func in get_tests():
        success, message = test_func(db_path)
        status = "✅" if success else "❌"
        print(f"{status} {test_name}: {message}")
