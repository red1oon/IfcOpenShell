#!/usr/bin/env python3
"""
Test Suite for BBox Semantic Geometry - Phase 1
Tests semantic type mapping, profile extraction, and material assignment
"""

import sys
import os

# Add module to path
sys.path.insert(0, '/home/red1/Projects/IfcOpenShell/src')

import unittest
from bonsai.bonsai.bim.module.federation.semantic_utils import (
    get_semantic_type,
    determine_dominant_axis,
    extract_profile_dimensions,
    get_material_id,
    extract_semantic_metadata,
    SEMANTIC_TYPE_MAPPING,
    MATERIAL_LIBRARY_DATA
)


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
        self.assertEqual(get_semantic_type('IfcMember'), 'beam')  # Members treated as beams

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
    """Test dominant axis determination for linear elements"""

    def test_vertical_element(self):
        """Test vertical column (Z-dominant)"""
        # Column: 0.5m x 0.5m x 3m (tall in Z)
        bbox = (0, 0, 0, 500, 500, 3000)
        axis = determine_dominant_axis(bbox)
        self.assertEqual(axis, 'Z')

    def test_horizontal_x_element(self):
        """Test horizontal beam along X"""
        # Beam: 5m x 0.3m x 0.5m (long in X)
        bbox = (0, 0, 0, 5000, 300, 500)
        axis = determine_dominant_axis(bbox)
        self.assertEqual(axis, 'X')

    def test_horizontal_y_element(self):
        """Test horizontal duct along Y"""
        # Duct: 0.4m x 10m x 0.3m (long in Y)
        bbox = (0, 0, 0, 400, 10000, 300)
        axis = determine_dominant_axis(bbox)
        self.assertEqual(axis, 'Y')

    def test_cubic_element(self):
        """Test cubic element (no clear dominant axis)"""
        # Equipment: 1m x 1m x 1m
        bbox = (0, 0, 0, 1000, 1000, 1000)
        axis = determine_dominant_axis(bbox)
        self.assertIsNone(axis)


class TestProfileDimensionExtraction(unittest.TestCase):
    """Test profile dimension extraction from bounding boxes"""

    def test_rectangular_duct(self):
        """Test rectangular duct profile (600x400mm)"""
        # Duct: 600mm x 400mm x 5000mm (long in Z)
        bbox = (0, 0, 0, 600, 400, 5000)
        width, height = extract_profile_dimensions(bbox, 'duct', 'Z')
        self.assertEqual(width, 400)  # Smallest dimension
        self.assertEqual(height, 600)  # Second smallest

    def test_circular_pipe(self):
        """Test circular pipe profile (DN150mm)"""
        # Pipe: 150mm diameter x 3000mm long
        bbox = (0, 0, 0, 150, 150, 3000)
        width, height = extract_profile_dimensions(bbox, 'pipe', 'Z')
        self.assertEqual(width, 150)
        self.assertEqual(height, 150)  # Same for circular

    def test_i_beam_profile(self):
        """Test I-beam profile (300x200mm)"""
        # Beam: 300mm x 200mm x 5000mm
        bbox = (0, 0, 0, 300, 200, 5000)
        width, height = extract_profile_dimensions(bbox, 'beam', 'Z')
        self.assertEqual(width, 200)  # Smallest
        self.assertEqual(height, 300)  # Second smallest


class TestMaterialAssignment(unittest.TestCase):
    """Test material library ID assignment"""

    def test_mep_materials(self):
        """Test MEP material assignment by discipline"""
        self.assertEqual(get_material_id('duct', 'ACMV'), 5)  # DUCT_ACMV
        self.assertEqual(get_material_id('pipe', 'FP'), 6)  # PIPE_FP (red)
        self.assertEqual(get_material_id('pipe', 'PLUMBING'), 8)  # PIPE_PLUMBING (blue)
        self.assertEqual(get_material_id('conduit', 'ELEC'), 9)  # CONDUIT_ELEC (yellow)

    def test_architectural_materials(self):
        """Test architectural material assignment"""
        self.assertEqual(get_material_id('door', 'ARCHITECTURE'), 1)  # DOOR_WOOD
        self.assertEqual(get_material_id('window', 'ARCHITECTURE'), 2)  # WINDOW_GLASS

    def test_structural_materials(self):
        """Test structural material assignment"""
        self.assertEqual(get_material_id('slab', 'STRUCTURE'), 3)  # CONCRETE_SLAB
        self.assertEqual(get_material_id('beam', 'STRUCTURE'), 4)  # STEEL_BEAM

    def test_fallback_material(self):
        """Test fallback to generic equipment"""
        self.assertEqual(get_material_id('unknown_type', 'UNKNOWN'), 10)  # GENERIC


class TestFullSemanticExtraction(unittest.TestCase):
    """Test complete semantic metadata extraction"""

    def test_duct_extraction(self):
        """Test full semantic extraction for ACMV duct"""
        guid = '2EW$JxRGfF3vw1ivMYDj8R'
        ifc_class = 'IfcDuctSegment'
        discipline = 'ACMV'
        bbox = (0, 0, 0, 600, 400, 5000)  # 600x400mm duct, 5m long

        metadata = extract_semantic_metadata(guid, ifc_class, discipline, bbox)

        self.assertEqual(metadata['guid'], guid)
        self.assertEqual(metadata['semantic_type'], 'duct')
        self.assertEqual(metadata['subtype'], 'rectangular')
        self.assertEqual(metadata['material_id'], 5)  # DUCT_ACMV
        self.assertEqual(metadata['dominant_axis'], 'Z')
        self.assertEqual(metadata['profile_width'], 400)
        self.assertEqual(metadata['profile_height'], 600)

    def test_pipe_extraction(self):
        """Test full semantic extraction for FP pipe"""
        guid = '1ABC2DEF3GHI4JKL5MNO6P'
        ifc_class = 'IfcPipeSegment'
        discipline = 'FP'
        bbox = (0, 0, 0, 150, 150, 3000)  # DN150 pipe, 3m long

        metadata = extract_semantic_metadata(guid, ifc_class, discipline, bbox)

        self.assertEqual(metadata['guid'], guid)
        self.assertEqual(metadata['semantic_type'], 'pipe')
        self.assertEqual(metadata['subtype'], 'circular')
        self.assertEqual(metadata['material_id'], 6)  # PIPE_FP (red)
        self.assertEqual(metadata['dominant_axis'], 'Z')
        self.assertEqual(metadata['profile_width'], 150)
        self.assertEqual(metadata['profile_height'], 150)


class TestMaterialLibraryData(unittest.TestCase):
    """Test material library data structure"""

    def test_material_library_completeness(self):
        """Test that all 10 materials are defined"""
        self.assertEqual(len(MATERIAL_LIBRARY_DATA), 10)

        # Check required materials exist
        material_names = [m['name'] for m in MATERIAL_LIBRARY_DATA]
        required_materials = [
            'DOOR_WOOD', 'WINDOW_GLASS', 'CONCRETE_SLAB', 'STEEL_BEAM',
            'DUCT_ACMV', 'PIPE_FP', 'WALL_GENERIC', 'PIPE_PLUMBING',
            'CONDUIT_ELEC', 'GENERIC_EQUIPMENT'
        ]

        for required in required_materials:
            self.assertIn(required, material_names)

    def test_material_properties(self):
        """Test material properties are valid"""
        for material in MATERIAL_LIBRARY_DATA:
            self.assertIn('id', material)
            self.assertIn('name', material)
            self.assertIn('category', material)
            self.assertIn('base_color', material)
            self.assertIn('metallic', material)
            self.assertIn('roughness', material)
            self.assertIn('transparency', material)

            # Check value ranges
            self.assertGreaterEqual(material['metallic'], 0.0)
            self.assertLessEqual(material['metallic'], 1.0)
            self.assertGreaterEqual(material['roughness'], 0.0)
            self.assertLessEqual(material['roughness'], 1.0)
            self.assertGreaterEqual(material['transparency'], 0.0)
            self.assertLessEqual(material['transparency'], 1.0)


def run_tests():
    """Run all tests and return results"""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestSemanticTypeMapping))
    suite.addTests(loader.loadTestsFromTestCase(TestDominantAxisDetection))
    suite.addTests(loader.loadTestsFromTestCase(TestProfileDimensionExtraction))
    suite.addTests(loader.loadTestsFromTestCase(TestMaterialAssignment))
    suite.addTests(loader.loadTestsFromTestCase(TestFullSemanticExtraction))
    suite.addTests(loader.loadTestsFromTestCase(TestMaterialLibraryData))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result


if __name__ == '__main__':
    print("=" * 70)
    print("BBox Semantic Geometry - Phase 1 Test Suite")
    print("=" * 70)
    print()

    result = run_tests()

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
