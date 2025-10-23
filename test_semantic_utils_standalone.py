#!/usr/bin/env python3
"""
Standalone Test Suite for semantic_utils.py
Tests without requiring Blender/bpy dependencies
"""

import sys
import os
import unittest

# Direct import of semantic_utils module
semantic_utils_path = '/home/red1/Projects/IfcOpenShell/src/bonsai/bonsai/bim/module/federation/semantic_utils.py'

# Load module directly
import importlib.util
spec = importlib.util.spec_from_file_location("semantic_utils", semantic_utils_path)
semantic_utils = importlib.util.module_from_spec(spec)
spec.loader.exec_module(semantic_utils)

# Import functions
get_semantic_type = semantic_utils.get_semantic_type
determine_dominant_axis = semantic_utils.determine_dominant_axis
extract_profile_dimensions = semantic_utils.extract_profile_dimensions
get_material_id = semantic_utils.get_material_id
extract_semantic_metadata = semantic_utils.extract_semantic_metadata
MATERIAL_LIBRARY_DATA = semantic_utils.MATERIAL_LIBRARY_DATA


class TestSemanticTypeMapping(unittest.TestCase):
    """Test IFC class to semantic type mapping"""

    def test_architectural_types(self):
        """Test architecture class mapping"""
        self.assertEqual(get_semantic_type('IfcDoor'), 'door')
        self.assertEqual(get_semantic_type('IfcDoorStandardCase'), 'door')
        self.assertEqual(get_semantic_type('IfcWindow'), 'window')
        self.assertEqual(get_semantic_type('IfcWall'), 'wall')
        self.assertEqual(get_semantic_type('IfcSlab'), 'slab')

    def test_structural_types(self):
        """Test structure class mapping"""
        self.assertEqual(get_semantic_type('IfcBeam'), 'beam')
        self.assertEqual(get_semantic_type('IfcColumn'), 'column')
        self.assertEqual(get_semantic_type('IfcMember'), 'beam')

    def test_mep_types(self):
        """Test MEP class mapping"""
        self.assertEqual(get_semantic_type('IfcDuctSegment'), 'duct')
        self.assertEqual(get_semantic_type('IfcPipeSegment'), 'pipe')
        self.assertEqual(get_semantic_type('IfcCableCarrierSegment'), 'conduit')
        self.assertEqual(get_semantic_type('IfcAirTerminal'), 'equipment')

    def test_fallback_default(self):
        """Test unknown classes fallback to equipment"""
        self.assertEqual(get_semantic_type('IfcUnknownClass'), 'equipment')
        self.assertEqual(get_semantic_type('IfcBuildingElementProxy'), 'equipment')


class TestDominantAxisDetection(unittest.TestCase):
    """Test dominant axis determination"""

    def test_vertical_element(self):
        """Test vertical column (Z-dominant)"""
        bbox = (0, 0, 0, 500, 500, 3000)
        axis = determine_dominant_axis(bbox)
        self.assertEqual(axis, 'Z')

    def test_horizontal_x_element(self):
        """Test horizontal beam along X"""
        bbox = (0, 0, 0, 5000, 300, 500)
        axis = determine_dominant_axis(bbox)
        self.assertEqual(axis, 'X')

    def test_horizontal_y_element(self):
        """Test horizontal duct along Y"""
        bbox = (0, 0, 0, 400, 10000, 300)
        axis = determine_dominant_axis(bbox)
        self.assertEqual(axis, 'Y')

    def test_cubic_element(self):
        """Test cubic element (no clear dominant axis)"""
        bbox = (0, 0, 0, 1000, 1000, 1000)
        axis = determine_dominant_axis(bbox)
        self.assertIsNone(axis)


class TestProfileDimensionExtraction(unittest.TestCase):
    """Test profile dimension extraction"""

    def test_rectangular_duct(self):
        """Test rectangular duct profile"""
        bbox = (0, 0, 0, 600, 400, 5000)
        width, height = extract_profile_dimensions(bbox, 'duct', 'Z')
        self.assertEqual(width, 400)
        self.assertEqual(height, 600)

    def test_circular_pipe(self):
        """Test circular pipe profile"""
        bbox = (0, 0, 0, 150, 150, 3000)
        width, height = extract_profile_dimensions(bbox, 'pipe', 'Z')
        self.assertEqual(width, 150)
        self.assertEqual(height, 150)


class TestMaterialAssignment(unittest.TestCase):
    """Test material library ID assignment"""

    def test_mep_materials(self):
        """Test MEP material assignment"""
        self.assertEqual(get_material_id('duct', 'ACMV'), 5)
        self.assertEqual(get_material_id('pipe', 'FP'), 6)
        self.assertEqual(get_material_id('pipe', 'PLUMBING'), 8)
        self.assertEqual(get_material_id('conduit', 'ELEC'), 9)

    def test_fallback_material(self):
        """Test fallback to generic equipment"""
        self.assertEqual(get_material_id('unknown_type', 'UNKNOWN'), 10)


class TestFullSemanticExtraction(unittest.TestCase):
    """Test complete semantic metadata extraction"""

    def test_duct_extraction(self):
        """Test full semantic extraction for ACMV duct"""
        guid = '2EW$JxRGfF3vw1ivMYDj8R'
        ifc_class = 'IfcDuctSegment'
        discipline = 'ACMV'
        bbox = (0, 0, 0, 600, 400, 5000)

        metadata = extract_semantic_metadata(guid, ifc_class, discipline, bbox)

        self.assertEqual(metadata['guid'], guid)
        self.assertEqual(metadata['semantic_type'], 'duct')
        self.assertEqual(metadata['subtype'], 'rectangular')
        self.assertEqual(metadata['material_id'], 5)
        self.assertEqual(metadata['dominant_axis'], 'Z')
        self.assertEqual(metadata['profile_width'], 400)
        self.assertEqual(metadata['profile_height'], 600)


class TestMaterialLibraryData(unittest.TestCase):
    """Test material library data structure"""

    def test_material_library_completeness(self):
        """Test that all 10 materials are defined"""
        self.assertEqual(len(MATERIAL_LIBRARY_DATA), 10)

        material_names = [m['name'] for m in MATERIAL_LIBRARY_DATA]
        required_materials = [
            'DOOR_WOOD', 'WINDOW_GLASS', 'CONCRETE_SLAB', 'STEEL_BEAM',
            'DUCT_ACMV', 'PIPE_FP', 'WALL_GENERIC', 'PIPE_PLUMBING',
            'CONDUIT_ELEC', 'GENERIC_EQUIPMENT'
        ]

        for required in required_materials:
            self.assertIn(required, material_names)


if __name__ == '__main__':
    print("=" * 70)
    print("BBox Semantic Geometry - Phase 1 Test Suite")
    print("Testing semantic_utils.py (standalone, no bpy dependency)")
    print("=" * 70)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestSemanticTypeMapping))
    suite.addTests(loader.loadTestsFromTestCase(TestDominantAxisDetection))
    suite.addTests(loader.loadTestsFromTestCase(TestProfileDimensionExtraction))
    suite.addTests(loader.loadTestsFromTestCase(TestMaterialAssignment))
    suite.addTests(loader.loadTestsFromTestCase(TestFullSemanticExtraction))
    suite.addTests(loader.loadTestsFromTestCase(TestMaterialLibraryData))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("=" * 70)

    if result.wasSuccessful():
        print("✅ ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED")
        sys.exit(1)
