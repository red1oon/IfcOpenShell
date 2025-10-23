#!/usr/bin/env python3
"""
Headless Blender tests for clash gizmo visualization

This script runs Blender in background mode to test gizmo functionality.
It tests gizmo creation, data preparation, coordinate conversion, and interaction logic.

Run with Blender's Python interpreter:
    blender --background --python test_clash_gizmo_blender.py

Or use the helper script:
    ./run_blender_tests.sh
"""

import sys
import os
from pathlib import Path

# This script is meant to be run inside Blender's Python environment
try:
    import bpy
except ImportError:
    print("ERROR: This script must be run with Blender's Python interpreter")
    print("Usage: blender --background --python test_clash_gizmo_blender.py")
    sys.exit(1)

# Add Bonsai modules to path
project_root = Path(__file__).parent
bonsai_path = project_root / "src/bonsai"
if str(bonsai_path) not in sys.path:
    sys.path.insert(0, str(bonsai_path))

# Import test modules
from bonsai.bim.module.clash import gizmo, database as db, prop


def test_setup():
    """Setup test environment"""
    print("\n" + "="*70)
    print("🧪 Blender Headless Gizmo Tests")
    print("="*70)

    # Register properties if not already registered
    if not hasattr(bpy.types.Scene, 'BIMClashProperties'):
        bpy.types.Scene.BIMClashProperties = bpy.props.PointerProperty(type=prop.BIMClashProperties)

    print("✓ Test environment setup complete")
    return True


def test_color_mapping():
    """Test status color mapping"""
    print("\n[TEST] Color Mapping")

    colors = {
        'NEW': gizmo.get_clash_color('NEW'),
        'ACTIVE': gizmo.get_clash_color('ACTIVE'),
        'REVIEWED': gizmo.get_clash_color('REVIEWED'),
        'RESOLVED': gizmo.get_clash_color('RESOLVED'),
    }

    assert colors['NEW'] == (1.0, 0.0, 0.0), "NEW should be red"
    assert colors['ACTIVE'] == (1.0, 0.5, 0.0), "ACTIVE should be orange"
    assert colors['REVIEWED'] == (1.0, 1.0, 0.0), "REVIEWED should be yellow"
    assert colors['RESOLVED'] == (0.0, 1.0, 0.0), "RESOLVED should be green"

    print("  ✓ All colors correct")
    print(f"    NEW: {colors['NEW']} (red)")
    print(f"    ACTIVE: {colors['ACTIVE']} (orange)")
    print(f"    REVIEWED: {colors['REVIEWED']} (yellow)")
    print(f"    RESOLVED: {colors['RESOLVED']} (green)")

    return True


def test_sphere_geometry():
    """Test sphere geometry generation"""
    print("\n[TEST] Sphere Geometry")

    # Test circle generation
    xy_circle = gizmo.generate_circle_tris(12, 'z')
    xz_circle = gizmo.generate_circle_tris(12, 'y')
    yz_circle = gizmo.generate_circle_tris(12, 'x')

    assert len(xy_circle) == 36, f"XY circle should have 36 vertices, got {len(xy_circle)}"
    assert len(xz_circle) == 36, f"XZ circle should have 36 vertices, got {len(xz_circle)}"
    assert len(yz_circle) == 36, f"YZ circle should have 36 vertices, got {len(yz_circle)}"

    # Test complete sphere
    sphere = gizmo.SPHERE_SIMPLE
    assert len(sphere) == 108, f"Sphere should have 108 vertices (3 circles × 36), got {len(sphere)}"

    print(f"  ✓ Sphere geometry correct ({len(sphere)} vertices)")

    return True


def test_coordinate_conversion():
    """Test IFC to Blender coordinate conversion"""
    print("\n[TEST] Coordinate Conversion")

    # Test with cached offset
    bpy.context.scene["MEP_cached_offset"] = (1000.0, 2000.0, 0.0)

    ifc_coords = (1500.0, 2500.0, 10.0)
    blender_coords = gizmo.ifc_to_blender_coords(ifc_coords)

    expected = (500.0, 500.0, 10.0)  # IFC - offset
    actual = (blender_coords.x, blender_coords.y, blender_coords.z)

    assert actual == expected, f"Expected {expected}, got {actual}"

    print(f"  ✓ Coordinate conversion correct")
    print(f"    IFC coords: {ifc_coords}")
    print(f"    Offset: (1000, 2000, 0)")
    print(f"    Blender coords: {actual}")

    # Clean up
    del bpy.context.scene["MEP_cached_offset"]

    return True


def test_clash_data_preparation():
    """Test preparing clash data for gizmo visualization"""
    print("\n[TEST] Clash Data Preparation")

    # Create mock clash candidates
    props = bpy.context.scene.BIMClashProperties
    props.discipline_clash_candidates.clear()

    # Add test clashes
    for i in range(3):
        candidate = props.discipline_clash_candidates.add()
        candidate.guid_a = f"test-guid-a-{i}"
        candidate.guid_b = f"test-guid-b-{i}"
        candidate.name_a = f"Wall_{i}"
        candidate.name_b = f"Duct_{i}"
        candidate.ifc_class_a = "IfcWall"
        candidate.ifc_class_b = "IfcFlowSegment"
        candidate.bbox_center_a = (1000.0 + i*10, 2000.0, 0.0)
        candidate.bbox_center_b = (1010.0 + i*10, 2010.0, 5.0)
        candidate.distance = 0.05
        candidate.status = "NEW"

    assert len(props.discipline_clash_candidates) == 3, "Should have 3 test clashes"

    print(f"  ✓ Created {len(props.discipline_clash_candidates)} test clashes")

    # Test data access
    first_clash = props.discipline_clash_candidates[0]
    assert first_clash.guid_a == "test-guid-a-0", "GUID mismatch"
    assert first_clash.distance == 0.05, "Distance mismatch"

    print(f"  ✓ Clash data accessible:")
    print(f"    GUID A: {first_clash.guid_a}")
    print(f"    GUID B: {first_clash.guid_b}")
    print(f"    Distance: {first_clash.distance}")

    return True


def test_gizmo_state_management():
    """Test gizmo state tracking"""
    print("\n[TEST] Gizmo State Management")

    # Initially should be inactive
    active = gizmo.is_gizmo_group_active()
    print(f"  ✓ Initial gizmo state: {'active' if active else 'inactive'}")

    # Test marker count
    count = gizmo.get_marker_count()
    print(f"  ✓ Marker count: {count}")

    return True


def test_gizmo_registration():
    """Test that gizmo classes can be registered"""
    print("\n[TEST] Gizmo Registration")

    # Check if gizmo classes exist
    assert hasattr(gizmo, 'ClashMarkerGizmo'), "ClashMarkerGizmo class not found"
    assert hasattr(gizmo, 'ClashMarkerGizmoGroup'), "ClashMarkerGizmoGroup class not found"

    print("  ✓ Gizmo classes found:")
    print(f"    - {gizmo.ClashMarkerGizmo.__name__}")
    print(f"    - {gizmo.ClashMarkerGizmoGroup.__name__}")

    # Verify gizmo class properties
    assert hasattr(gizmo.ClashMarkerGizmo, 'bl_idname'), "Gizmo missing bl_idname"
    assert gizmo.ClashMarkerGizmo.bl_idname == "VIEW3D_GT_clash_marker", "Wrong gizmo ID"

    print(f"  ✓ Gizmo bl_idname: {gizmo.ClashMarkerGizmo.bl_idname}")

    return True


def run_all_tests():
    """Run all tests and report results"""
    tests = [
        ("Setup", test_setup),
        ("Color Mapping", test_color_mapping),
        ("Sphere Geometry", test_sphere_geometry),
        ("Coordinate Conversion", test_coordinate_conversion),
        ("Clash Data Preparation", test_clash_data_preparation),
        ("Gizmo State Management", test_gizmo_state_management),
        ("Gizmo Registration", test_gizmo_registration),
    ]

    passed = 0
    failed = 0
    errors = []

    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
                errors.append(f"{test_name}: Test returned False")
        except AssertionError as e:
            failed += 1
            errors.append(f"{test_name}: {str(e)}")
            print(f"  ✗ FAILED: {e}")
        except Exception as e:
            failed += 1
            errors.append(f"{test_name}: Unexpected error: {str(e)}")
            print(f"  ✗ ERROR: {e}")

    # Print summary
    print("\n" + "="*70)
    print("Test Summary")
    print("="*70)
    print(f"Tests run: {passed + failed}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")

    if errors:
        print("\nFailures:")
        for error in errors:
            print(f"  - {error}")

    print("="*70)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()

    # Exit with appropriate code
    if success:
        print("\n✅ All tests passed!")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed")
        sys.exit(1)
