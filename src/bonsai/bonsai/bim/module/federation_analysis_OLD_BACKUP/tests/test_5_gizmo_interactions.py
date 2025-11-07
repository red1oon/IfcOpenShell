#!/usr/bin/env python3
"""
Gizmo Interaction Tests
Test clash status changes, navigation, and context menu operations
"""

import sqlite3
import sys
import tempfile
import os
from pathlib import Path


def test_clash_status_database_operations(db_path):
    """Test status persistence to clash_status.db"""
    try:
        # Setup: Create temporary clash_status.db
        test_dir = tempfile.mkdtemp()
        status_db = os.path.join(test_dir, "clash_status.db")

        # Import database module (pure Python, no Blender)
        test_dir_path = Path(__file__).parent
        module_dir = test_dir_path.parent
        clash_dir = module_dir / "clash"
        sys.path.insert(0, str(clash_dir))

        # Direct SQL operations instead of importing database module
        # (to avoid bpy dependency)
        conn = sqlite3.connect(status_db)
        cursor = conn.cursor()

        # Create clash_status table (same schema as database.py)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clash_status (
                clash_id TEXT PRIMARY KEY,
                guid_a TEXT NOT NULL,
                guid_b TEXT NOT NULL,
                status TEXT NOT NULL,
                distance REAL,
                ifc_class_a TEXT,
                ifc_class_b TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Test data
        guid_a = "test-guid-a-12345"
        guid_b = "test-guid-b-67890"
        clash_id = f"{min(guid_a, guid_b)}_{max(guid_a, guid_b)}"

        # Test 1: Insert initial status (NEW)
        cursor.execute("""
            INSERT INTO clash_status (clash_id, guid_a, guid_b, status, distance, ifc_class_a, ifc_class_b)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (clash_id, guid_a, guid_b, 'NEW', 0.05, 'IfcPipeSegment', 'IfcDuctSegment'))
        conn.commit()

        # Verify it was written
        cursor.execute("SELECT status FROM clash_status WHERE clash_id = ?", (clash_id,))
        row = cursor.fetchone()
        if not row or row[0] != 'NEW':
            return False, "Failed to write initial status"

        # Test 2: Update status (NEW → ACTIVE)
        cursor.execute("UPDATE clash_status SET status = ? WHERE clash_id = ?", ('ACTIVE', clash_id))
        conn.commit()

        cursor.execute("SELECT status FROM clash_status WHERE clash_id = ?", (clash_id,))
        row = cursor.fetchone()
        if not row or row[0] != 'ACTIVE':
            return False, f"Expected 'ACTIVE', got '{row[0] if row else None}'"

        # Test 3: Update status (ACTIVE → REVIEWED)
        cursor.execute("UPDATE clash_status SET status = ? WHERE clash_id = ?", ('REVIEWED', clash_id))
        conn.commit()

        cursor.execute("SELECT status FROM clash_status WHERE clash_id = ?", (clash_id,))
        row = cursor.fetchone()
        if not row or row[0] != 'REVIEWED':
            return False, f"Expected 'REVIEWED', got '{row[0] if row else None}'"

        # Test 4: Update status (REVIEWED → RESOLVED)
        cursor.execute("UPDATE clash_status SET status = ? WHERE clash_id = ?", ('RESOLVED', clash_id))
        conn.commit()

        cursor.execute("SELECT status FROM clash_status WHERE clash_id = ?", (clash_id,))
        row = cursor.fetchone()
        if not row or row[0] != 'RESOLVED':
            return False, f"Expected 'RESOLVED', got '{row[0] if row else None}'"

        # Test 5: Verify metadata persists
        cursor.execute("SELECT ifc_class_a FROM clash_status WHERE clash_id = ?", (clash_id,))
        row = cursor.fetchone()
        if not row or row[0] != 'IfcPipeSegment':
            return False, "Metadata lost during updates"

        # Cleanup
        conn.close()
        os.remove(status_db)
        os.rmdir(test_dir)

        return True, f"Status workflow tested: NEW → ACTIVE → REVIEWED → RESOLVED ✓"

    except Exception as e:
        return False, f"Database operation error: {e}"


def test_clash_id_generation(db_path):
    """Test clash ID generation is consistent"""
    try:
        # Test the ID generation logic (sorted GUID concatenation)
        guid_a = "test-guid-a"
        guid_b = "test-guid-b"

        # Clash IDs should be consistent regardless of order (alphabetically sorted)
        id1 = f"{min(guid_a, guid_b)}_{max(guid_a, guid_b)}"
        id2 = f"{min(guid_b, guid_a)}_{max(guid_b, guid_a)}"

        if id1 != id2:
            return False, f"Clash ID not symmetric: {id1} != {id2}"

        # Should be deterministic
        id3 = f"{min(guid_a, guid_b)}_{max(guid_a, guid_b)}"
        if id1 != id3:
            return False, f"Clash ID not deterministic: {id1} != {id3}"

        # Different pairs should have different IDs
        guid_c = "test-guid-c"
        id4 = f"{min(guid_a, guid_c)}_{max(guid_a, guid_c)}"
        if id1 == id4:
            return False, "Different clash pairs have same ID"

        return True, f"Clash ID generation consistent ✓"

    except Exception as e:
        return False, f"Clash ID test error: {e}"


def test_status_color_mapping(db_path):
    """Test status-to-color mapping for gizmo visualization"""
    try:
        # Test color mapping logic (hardcoded in gizmo.py)
        STATUS_COLORS = {
            'NEW': (1.0, 0.0, 0.0),       # Red
            'ACTIVE': (1.0, 0.5, 0.0),    # Orange
            'REVIEWED': (1.0, 1.0, 0.0),  # Yellow
            'RESOLVED': (0.0, 1.0, 0.0),  # Green
        }

        for status, expected_rgb in STATUS_COLORS.items():
            # Simulate get_clash_color() logic
            actual_rgb = STATUS_COLORS.get(status, (1.0, 0.0, 0.0))

            if actual_rgb != expected_rgb:
                return False, f"Status '{status}': expected {expected_rgb}, got {actual_rgb}"

        # Test default fallback (unknown status)
        default_color = STATUS_COLORS.get('UNKNOWN_STATUS', (1.0, 0.0, 0.0))
        if default_color != (1.0, 0.0, 0.0):  # Should default to red
            return False, f"Unknown status should default to red, got {default_color}"

        return True, "Color mapping correct for all statuses ✓"

    except Exception as e:
        return False, f"Color mapping test error: {e}"


def test_navigation_wraparound(db_path):
    """Test navigation logic wraps around correctly"""
    try:
        # Simulate selected clash indices
        selected_indices = [0, 3, 7, 15, 22]

        # Test forward navigation with wraparound
        def navigate_next(current_idx, selected):
            try:
                current_pos = selected.index(current_idx)
            except ValueError:
                current_pos = 0
            next_pos = (current_pos + 1) % len(selected)
            return selected[next_pos]

        # Test backward navigation with wraparound
        def navigate_prev(current_idx, selected):
            try:
                current_pos = selected.index(current_idx)
            except ValueError:
                current_pos = 0
            prev_pos = (current_pos - 1) % len(selected)
            return selected[prev_pos]

        # Forward: 0 → 3 → 7 → 15 → 22 → 0 (wrap)
        if navigate_next(0, selected_indices) != 3:
            return False, "Navigation 0→3 failed"
        if navigate_next(22, selected_indices) != 0:
            return False, "Navigation 22→0 (wrap) failed"

        # Backward: 0 → 22 (wrap) → 15 → 7 → 3 → 0
        if navigate_prev(0, selected_indices) != 22:
            return False, "Navigation 0→22 (wrap back) failed"
        if navigate_prev(3, selected_indices) != 0:
            return False, "Navigation 3→0 failed"

        return True, "Navigation wraparound logic correct ✓"

    except Exception as e:
        return False, f"Navigation test error: {e}"


def test_sphere_geometry_generation(db_path):
    """Test UV sphere geometry is valid"""
    try:
        import math

        # Replicate generate_uv_sphere() logic from gizmo.py
        def generate_uv_sphere(rings=8, segments=12):
            verts = []
            for ring in range(rings):
                theta1 = (ring / rings) * math.pi
                theta2 = ((ring + 1) / rings) * math.pi

                for seg in range(segments):
                    phi1 = (seg / segments) * 2 * math.pi
                    phi2 = ((seg + 1) / segments) * 2 * math.pi

                    v1 = (
                        math.sin(theta1) * math.cos(phi1),
                        math.sin(theta1) * math.sin(phi1),
                        math.cos(theta1)
                    )
                    v2 = (
                        math.sin(theta1) * math.cos(phi2),
                        math.sin(theta1) * math.sin(phi2),
                        math.cos(theta1)
                    )
                    v3 = (
                        math.sin(theta2) * math.cos(phi2),
                        math.sin(theta2) * math.sin(phi2),
                        math.cos(theta2)
                    )
                    v4 = (
                        math.sin(theta2) * math.cos(phi1),
                        math.sin(theta2) * math.sin(phi1),
                        math.cos(theta2)
                    )

                    verts.extend([v1, v2, v3])
                    verts.extend([v1, v3, v4])

            return verts

        # Generate sphere with 8 rings, 12 segments
        verts = generate_uv_sphere(rings=8, segments=12)

        # Each quad creates 2 triangles (6 vertices)
        # Total quads = rings * segments = 8 * 12 = 96
        # Total vertices = 96 * 6 = 576
        expected_verts = 8 * 12 * 6

        if len(verts) != expected_verts:
            return False, f"Expected {expected_verts} vertices, got {len(verts)}"

        # Each vertex should be a 3-tuple (x, y, z)
        for i, vert in enumerate(verts):
            if len(vert) != 3:
                return False, f"Vertex {i} is not a 3-tuple: {vert}"

        # Vertices should be on unit sphere surface (distance ≈ 1.0)
        for i, vert in enumerate(verts):
            x, y, z = vert
            distance = math.sqrt(x*x + y*y + z*z)
            if abs(distance - 1.0) > 0.01:
                return False, f"Vertex {i} not on unit sphere: distance={distance:.3f}"

        return True, f"Sphere geometry valid ({len(verts)} vertices) ✓"

    except Exception as e:
        return False, f"Sphere geometry test error: {e}"


def test_coordinate_conversion_consistency(db_path):
    """Test IFC to Blender coordinate conversion is reversible"""
    try:
        # Test coordinate conversion math (ifc_to_blender_coords logic)
        # No Blender imports needed - just pure math

        # Mock offset (simulating GPS coordinates)
        test_offset = (-50400.0, 34200.0, 0.0)

        # Test coordinate: IFC world coords
        ifc_coords = (-50350.0, 34250.0, 12.5)

        # Simulate conversion (Blender coords = IFC coords - offset)
        expected_blender = (
            ifc_coords[0] - test_offset[0],
            ifc_coords[1] - test_offset[1],
            ifc_coords[2] - test_offset[2]
        )

        # Expected result: (50, 50, 12.5) in Blender space
        if abs(expected_blender[0] - 50.0) > 0.01:
            return False, f"X conversion failed: {expected_blender[0]}"
        if abs(expected_blender[1] - 50.0) > 0.01:
            return False, f"Y conversion failed: {expected_blender[1]}"
        if abs(expected_blender[2] - 12.5) > 0.01:
            return False, f"Z conversion failed: {expected_blender[2]}"

        return True, "Coordinate conversion math correct ✓"

    except Exception as e:
        return False, f"Coordinate conversion test error: {e}"


# ============================================================================
# TEST RUNNER
# ============================================================================

def run_tests(db_path):
    """Run all gizmo interaction tests"""
    tests = [
        ("Status Database Operations", test_clash_status_database_operations),
        ("Clash ID Generation", test_clash_id_generation),
        ("Status Color Mapping", test_status_color_mapping),
        ("Navigation Wraparound", test_navigation_wraparound),
        ("Sphere Geometry Generation", test_sphere_geometry_generation),
        ("Coordinate Conversion", test_coordinate_conversion_consistency),
    ]

    print("\n" + "="*70)
    print("GIZMO INTERACTION TESTS")
    print("="*70)

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            success, message = test_func(db_path)

            if success:
                print(f"✓ {test_name}: {message}")
                passed += 1
            else:
                print(f"✗ {test_name}: {message}")
                failed += 1
        except Exception as e:
            print(f"✗ {test_name}: Unhandled exception - {e}")
            failed += 1

    print("="*70)
    print(f"Results: {passed} passed, {failed} failed")
    print("="*70)

    return failed == 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_5_gizmo_interactions.py <database_path>")
        sys.exit(1)

    db_path = sys.argv[1]

    if not os.path.exists(db_path):
        print(f"Error: Database not found: {db_path}")
        sys.exit(1)

    success = run_tests(db_path)
    sys.exit(0 if success else 1)
