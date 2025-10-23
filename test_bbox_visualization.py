#!/usr/bin/env python3
"""
Test script for bbox_visualization module (Phase 2)
Tests the core logic without requiring Blender to be running
"""

import sqlite3
import sys
from pathlib import Path

# Mock the bpy and gpu modules BEFORE importing bbox_visualization
class MockVector:
    def __init__(self, coords):
        self.x, self.y, self.z = coords

class MockBpy:
    class context:
        class scene:
            @staticmethod
            def get(key):
                return None

class MockGPU:
    class state:
        @staticmethod
        def blend_set(mode):
            pass

        @staticmethod
        def line_width_set(width):
            pass

    class shader:
        @staticmethod
        def from_builtin(name):
            return type('obj', (object,), {
                'bind': lambda: None,
                'uniform_float': lambda *args: None
            })()

    class types:
        class GPUBatch:
            def draw(self, shader):
                pass

def batch_for_shader(shader, mode, data):
    """Mock batch_for_shader function"""
    return MockGPU.types.GPUBatch()

# Set up all mocks before importing
sys.modules['bpy'] = MockBpy()
sys.modules['gpu'] = MockGPU()
sys.modules['gpu.state'] = MockGPU.state
sys.modules['gpu.shader'] = MockGPU.shader
sys.modules['gpu.types'] = MockGPU.types
sys.modules['gpu_extras'] = type('obj', (object,), {})()
sys.modules['gpu_extras.batch'] = type('obj', (object,), {'batch_for_shader': batch_for_shader})()
sys.modules['mathutils'] = type('obj', (object,), {'Vector': MockVector, 'Matrix': type})()

# Import bbox_visualization module after mocks are set up
sys.path.insert(0, '/home/red1/Projects/IfcOpenShell/src')
bbox_viz_path = '/home/red1/Projects/IfcOpenShell/src/bonsai/bonsai/bim/module/clash/bbox_visualization.py'

import importlib.util
spec = importlib.util.spec_from_file_location("bbox_visualization", bbox_viz_path)
bbox_visualization = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bbox_visualization)

# Test database path
DB_PATH = "/home/red1/Documents/bonsai/federation_index.db"


def test_create_bbox_edges():
    """Test: BBox edge creation"""
    print("\n" + "="*70)
    print("TEST 1: BBox Edge Creation")
    print("="*70)

    # Test bbox: 1m x 2m x 3m box
    bbox = (0.0, 0.0, 0.0, 1000.0, 2000.0, 3000.0)

    vertices = bbox_visualization.create_bbox_edges(bbox)

    # Should create 24 vertices (12 edges * 2 vertices each)
    assert len(vertices) == 24, f"Expected 24 vertices, got {len(vertices)}"

    # Verify all vertices are Vector objects
    for v in vertices:
        assert hasattr(v, 'x') and hasattr(v, 'y') and hasattr(v, 'z'), "Invalid vertex format"

    print(f"  ✓ Created {len(vertices)} vertices (12 edges)")
    print(f"  ✓ All vertices have x, y, z coordinates")
    print("  ✓ Edge creation test PASSED")


def test_load_federation_bboxes():
    """Test: Load bboxes from database"""
    print("\n" + "="*70)
    print("TEST 2: Load Federation BBoxes from Database")
    print("="*70)

    if not Path(DB_PATH).exists():
        print(f"  ⚠️  Database not found: {DB_PATH}")
        print("  ⏭️  Skipping database test")
        return

    # Load all bboxes (no limit)
    discipline_bboxes = bbox_visualization.load_federation_bboxes(DB_PATH, limit=None)

    assert isinstance(discipline_bboxes, dict), "Expected dict of discipline → bboxes"
    assert len(discipline_bboxes) > 0, "No disciplines found in database"

    total_elements = sum(len(bboxes) for bboxes in discipline_bboxes.values())

    print(f"  ✓ Loaded {len(discipline_bboxes)} disciplines")
    print(f"  ✓ Total elements: {total_elements:,}")

    # Verify structure
    for discipline, bbox_list in discipline_bboxes.items():
        assert isinstance(bbox_list, list), f"Expected list for discipline {discipline}"
        assert len(bbox_list) > 0, f"No elements for discipline {discipline}"

        # Verify first bbox structure
        bbox, guid = bbox_list[0]
        assert len(bbox) == 6, f"Expected 6 values in bbox, got {len(bbox)}"
        assert isinstance(guid, str), f"Expected string GUID, got {type(guid)}"

        print(f"    {discipline}: {len(bbox_list):,} elements")

    print("  ✓ Database loading test PASSED")


def test_load_limited_bboxes():
    """Test: Load limited number of bboxes"""
    print("\n" + "="*70)
    print("TEST 3: Load Limited BBoxes (100 elements)")
    print("="*70)

    if not Path(DB_PATH).exists():
        print(f"  ⚠️  Database not found: {DB_PATH}")
        print("  ⏭️  Skipping database test")
        return

    # Load only 100 elements
    limit = 100
    discipline_bboxes = bbox_visualization.load_federation_bboxes(DB_PATH, limit=limit)

    total_elements = sum(len(bboxes) for bboxes in discipline_bboxes.values())

    assert total_elements <= limit, f"Expected max {limit} elements, got {total_elements}"

    print(f"  ✓ Loaded {total_elements} elements (limit: {limit})")
    print("  ✓ Limit test PASSED")


def test_discipline_colors():
    """Test: Verify discipline color mapping exists"""
    print("\n" + "="*70)
    print("TEST 4: Discipline Color Mapping")
    print("="*70)

    expected_disciplines = ['ACMV', 'FP', 'ELEC', 'CW', 'SP', 'ARC', 'STR', 'DEFAULT']

    for discipline in expected_disciplines:
        color = bbox_visualization.DISCIPLINE_COLORS.get(discipline)
        assert color is not None, f"Missing color for discipline: {discipline}"
        assert len(color) == 4, f"Color should be RGBA tuple for {discipline}"

        # Verify color values are in 0-1 range
        for val in color:
            assert 0.0 <= val <= 1.0, f"Color value out of range for {discipline}"

    print(f"  ✓ Found colors for {len(expected_disciplines)} disciplines")
    print(f"  ✓ All colors are valid RGBA tuples")
    print("  ✓ Color mapping test PASSED")


def test_get_model_offset():
    """Test: Model offset retrieval"""
    print("\n" + "="*70)
    print("TEST 5: Model Offset Retrieval")
    print("="*70)

    offset = bbox_visualization.get_model_offset()

    assert hasattr(offset, 'x') and hasattr(offset, 'y') and hasattr(offset, 'z'), \
        "Offset should be a Vector with x, y, z"

    print(f"  ✓ Offset retrieved: ({offset.x:.1f}, {offset.y:.1f}, {offset.z:.1f})")
    print("  ✓ Model offset test PASSED")


def main():
    """Run all tests"""
    print("="*70)
    print("BBox Visualization Module Test Suite (Phase 2)")
    print("="*70)
    print(f"Database: {DB_PATH}")
    print(f"Exists: {Path(DB_PATH).exists()}")

    tests = [
        test_create_bbox_edges,
        test_discipline_colors,
        test_get_model_offset,
        test_load_federation_bboxes,
        test_load_limited_bboxes,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"\n  ❌ TEST FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"\n  ❌ TEST ERROR: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    print(f"  Passed: {passed}/{len(tests)}")
    print(f"  Failed: {failed}/{len(tests)}")

    if failed == 0:
        print("\n✅ ALL TESTS PASSED")
        return 0
    else:
        print(f"\n❌ {failed} TEST(S) FAILED")
        return 1


if __name__ == '__main__':
    sys.exit(main())
