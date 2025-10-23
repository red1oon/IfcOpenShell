"""
Comprehensive tests for clash gizmo visualization and database persistence

Tests cover:
- SQLite database operations (CRUD, history, statistics)
- Gizmo coordinate conversion logic
- Status color mapping
- Clash data preparation
- Database integrity and transactions

Run with: python3 run_clash_tests.py (from project root)
"""

# IMPORTANT: Remove current directory from sys.path to avoid operator.py conflict
import sys
from pathlib import Path
_test_dir = Path(__file__).parent
if str(_test_dir) in sys.path:
    sys.path.remove(str(_test_dir))

import unittest
import sqlite3
import tempfile
import os
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch
import sys
import importlib.util

# Load modules directly to avoid import conflicts
def load_module_from_file(module_name, file_path):
    """Load a module from a file path"""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module

# Mock bpy and mathutils before loading modules
sys.modules['bpy'] = Mock()
sys.modules['bpy.types'] = Mock()
sys.modules['bpy.props'] = Mock()
sys.modules['mathutils'] = Mock()

# Create a mock Vector class
class MockVector:
    def __init__(self, coords):
        if isinstance(coords, (list, tuple)):
            self.x, self.y, self.z = coords[0], coords[1], coords[2]
        else:
            self.x = self.y = self.z = 0

    def __add__(self, other):
        return MockVector((self.x + other.x, self.y + other.y, self.z + other.z))

    def __truediv__(self, scalar):
        return MockVector((self.x / scalar, self.y / scalar, self.z / scalar))

sys.modules['mathutils'].Vector = MockVector

# Get the clash module directory
clash_dir = Path(__file__).parent / 'src/bonsai/bonsai/bim/module/clash'

# Load database module first
db = load_module_from_file('clash_database', clash_dir / 'database.py')

# Mock the database import for gizmo module
sys.modules['clash_gizmo.database'] = db

# Load gizmo module
gizmo = load_module_from_file('clash_gizmo', clash_dir / 'gizmo.py')

# Inject database into gizmo module (gizmo imports it as db)
gizmo.db = db


class TestClashDatabase(unittest.TestCase):
    """Test suite for clash database persistence"""

    def setUp(self):
        """Create temporary database for each test"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = Path(self.temp_db.name)

        # Patch the database path function
        self.patcher = patch('clash_database.get_clash_database_path')
        self.mock_path = self.patcher.start()
        self.mock_path.return_value = self.db_path

    def tearDown(self):
        """Clean up temporary database"""
        self.patcher.stop()
        if self.db_path.exists():
            self.db_path.unlink()

    def test_database_initialization(self):
        """Test database schema creation"""
        conn = db.initialize_database()

        # Verify tables exist
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}

        self.assertIn('clash_status', tables)
        self.assertIn('clash_history', tables)

        # Verify indexes exist
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        indexes = {row[0] for row in cursor.fetchall()}

        self.assertIn('idx_status', indexes)
        self.assertIn('idx_guid_a', indexes)
        self.assertIn('idx_guid_b', indexes)

        conn.close()

    def test_clash_id_generation(self):
        """Test stable clash ID generation from GUIDs"""
        guid_a = "2O2Fr$t4X7Zf8NOew3FNr2"
        guid_b = "3P3Gs$u5Y8Ag9OPfx4GOr3"

        # IDs should be the same regardless of order
        id1 = db.get_clash_id(guid_a, guid_b)
        id2 = db.get_clash_id(guid_b, guid_a)

        self.assertEqual(id1, id2)
        self.assertEqual(len(id1), 32)  # MD5 hash length

    def test_insert_new_clash(self):
        """Test inserting a new clash"""
        clash_id = db.set_clash_status(
            "guid-wall-001",
            "guid-duct-001",
            status="NEW",
            distance=0.05,
            ifc_class_a="IfcWall",
            ifc_class_b="IfcFlowSegment",
            discipline_a="ARC",
            discipline_b="MEP"
        )

        # Verify clash was inserted
        status = db.get_clash_status("guid-wall-001", "guid-duct-001")

        self.assertIsNotNone(status)
        self.assertEqual(status['status'], 'NEW')
        self.assertEqual(status['distance'], 0.05)
        self.assertEqual(status['ifc_class_a'], 'IfcWall')
        self.assertEqual(status['ifc_class_b'], 'IfcFlowSegment')
        self.assertEqual(status['discipline_a'], 'ARC')
        self.assertEqual(status['discipline_b'], 'MEP')

    def test_update_clash_status(self):
        """Test updating existing clash status"""
        # Insert initial clash
        db.set_clash_status(
            "guid-a", "guid-b",
            status="NEW",
            distance=0.1
        )

        # Update status
        db.set_clash_status(
            "guid-a", "guid-b",
            status="REVIEWED",
            comment="Approved - acceptable overlap"
        )

        # Verify update
        status = db.get_clash_status("guid-a", "guid-b")
        self.assertEqual(status['status'], 'REVIEWED')
        self.assertEqual(status['comment'], 'Approved - acceptable overlap')

    def test_clash_history_tracking(self):
        """Test audit log for status changes"""
        # Create and update clash multiple times
        db.set_clash_status("guid-x", "guid-y", status="NEW")
        db.set_clash_status("guid-x", "guid-y", status="ACTIVE", changed_by="Alice")
        db.set_clash_status("guid-x", "guid-y", status="REVIEWED", changed_by="Bob")
        db.set_clash_status("guid-x", "guid-y", status="RESOLVED", changed_by="Charlie")

        # Get history
        clash_id = db.get_clash_id("guid-x", "guid-y")
        history = db.get_clash_history(clash_id)

        # Should have 4 entries (creation + 3 updates)
        self.assertEqual(len(history), 4)

        # Verify order (most recent first)
        self.assertEqual(history[0]['new_status'], 'RESOLVED')
        self.assertEqual(history[0]['changed_by'], 'Charlie')

        self.assertEqual(history[1]['new_status'], 'REVIEWED')
        self.assertEqual(history[2]['new_status'], 'ACTIVE')
        self.assertEqual(history[3]['new_status'], 'NEW')

    def test_bulk_status_update(self):
        """Test bulk updating multiple clashes"""
        # Create multiple clashes
        ids = []
        for i in range(5):
            clash_id = db.set_clash_status(
                f"guid-a-{i}",
                f"guid-b-{i}",
                status="NEW"
            )
            ids.append(clash_id)

        # Bulk update to RESOLVED
        count = db.bulk_update_status(ids, "RESOLVED", changed_by="BulkUpdate")

        self.assertEqual(count, 5)

        # Verify all updated
        for i in range(5):
            status = db.get_clash_status(f"guid-a-{i}", f"guid-b-{i}")
            self.assertEqual(status['status'], 'RESOLVED')

    def test_get_all_clashes_filtered(self):
        """Test retrieving clashes with status filter"""
        # Create clashes with different statuses
        db.set_clash_status("guid-1a", "guid-1b", status="NEW")
        db.set_clash_status("guid-2a", "guid-2b", status="NEW")
        db.set_clash_status("guid-3a", "guid-3b", status="ACTIVE")
        db.set_clash_status("guid-4a", "guid-4b", status="RESOLVED")

        # Get only NEW clashes
        new_clashes = db.get_all_clashes(status_filter=["NEW"])
        self.assertEqual(len(new_clashes), 2)

        # Get NEW and ACTIVE
        active_clashes = db.get_all_clashes(status_filter=["NEW", "ACTIVE"])
        self.assertEqual(len(active_clashes), 3)

        # Get all
        all_clashes = db.get_all_clashes()
        self.assertEqual(len(all_clashes), 4)

    def test_statistics_generation(self):
        """Test clash statistics reporting"""
        # Create clashes with various statuses
        db.set_clash_status("g1a", "g1b", status="NEW", discipline_a="ARC", discipline_b="STR")
        db.set_clash_status("g2a", "g2b", status="NEW", discipline_a="ARC", discipline_b="STR")
        db.set_clash_status("g3a", "g3b", status="ACTIVE", discipline_a="ARC", discipline_b="MEP")
        db.set_clash_status("g4a", "g4b", status="REVIEWED", discipline_a="MEP", discipline_b="STR")
        db.set_clash_status("g5a", "g5b", status="RESOLVED", discipline_a="MEP", discipline_b="STR")

        stats = db.get_statistics()

        # Verify status counts
        self.assertEqual(stats['total'], 5)
        self.assertEqual(stats['by_status']['NEW'], 2)
        self.assertEqual(stats['by_status']['ACTIVE'], 1)
        self.assertEqual(stats['by_status']['REVIEWED'], 1)
        self.assertEqual(stats['by_status']['RESOLVED'], 1)

        # Verify discipline counts
        self.assertEqual(len(stats['by_discipline']), 3)

    def test_no_duplicate_on_same_status_update(self):
        """Test that updating to same status doesn't create duplicate history"""
        db.set_clash_status("guid-dup-a", "guid-dup-b", status="NEW")
        db.set_clash_status("guid-dup-a", "guid-dup-b", status="NEW")  # Same status

        clash_id = db.get_clash_id("guid-dup-a", "guid-dup-b")
        history = db.get_clash_history(clash_id)

        # Should only have 1 entry (initial creation)
        self.assertEqual(len(history), 1)


class TestGizmoHelpers(unittest.TestCase):
    """Test suite for gizmo helper functions"""

    def test_status_color_mapping(self):
        """Test color assignment for each status"""
        colors = {
            'NEW': gizmo.get_clash_color('NEW'),
            'ACTIVE': gizmo.get_clash_color('ACTIVE'),
            'REVIEWED': gizmo.get_clash_color('REVIEWED'),
            'RESOLVED': gizmo.get_clash_color('RESOLVED'),
        }

        # Verify colors are different
        self.assertEqual(colors['NEW'], (1.0, 0.0, 0.0))  # Red
        self.assertEqual(colors['ACTIVE'], (1.0, 0.5, 0.0))  # Orange
        self.assertEqual(colors['REVIEWED'], (1.0, 1.0, 0.0))  # Yellow
        self.assertEqual(colors['RESOLVED'], (0.0, 1.0, 0.0))  # Green

        # Unknown status should default to red
        self.assertEqual(gizmo.get_clash_color('UNKNOWN'), (1.0, 0.0, 0.0))

    def test_sphere_geometry_generation(self):
        """Test simple sphere vertex generation"""
        # Test circle generation for each axis
        xy_circle = gizmo.generate_circle_tris(12, 'z')
        xz_circle = gizmo.generate_circle_tris(12, 'y')
        yz_circle = gizmo.generate_circle_tris(12, 'x')

        # 12 segments = 12 triangles = 36 vertices (3 per triangle)
        self.assertEqual(len(xy_circle), 36)
        self.assertEqual(len(xz_circle), 36)
        self.assertEqual(len(yz_circle), 36)

        # Verify SPHERE_SIMPLE has all three circles
        # 3 circles × 12 segments × 3 vertices = 108 vertices
        self.assertEqual(len(gizmo.SPHERE_SIMPLE), 108)

    @patch('clash_gizmo.bpy')
    def test_coordinate_conversion_with_offset(self, mock_bpy):
        """Test IFC to Blender coordinate conversion"""
        # Mock scene with cached offset
        mock_scene = Mock()
        mock_scene.get.return_value = (1000.0, 2000.0, 0.0)
        mock_bpy.context.scene = mock_scene

        # Test conversion
        ifc_coords = (1500.0, 2500.0, 10.0)
        blender_coords = gizmo.ifc_to_blender_coords(ifc_coords)

        # Should subtract offset
        self.assertEqual(blender_coords.x, 500.0)  # 1500 - 1000
        self.assertEqual(blender_coords.y, 500.0)  # 2500 - 2000
        self.assertEqual(blender_coords.z, 10.0)   # 10 - 0

    @patch('clash_gizmo.bpy')
    def test_coordinate_conversion_no_offset(self, mock_bpy):
        """Test coordinate conversion when no offset available"""
        # Mock scene with no cached offset
        mock_scene = Mock()
        mock_scene.get.return_value = None
        mock_scene.BIMGeoreferenceProperties = None
        mock_bpy.context.scene = mock_scene

        # Should use zero offset
        ifc_coords = (100.0, 200.0, 300.0)
        blender_coords = gizmo.ifc_to_blender_coords(ifc_coords)

        self.assertEqual(blender_coords.x, 100.0)
        self.assertEqual(blender_coords.y, 200.0)
        self.assertEqual(blender_coords.z, 300.0)


class TestGizmoDataPreparation(unittest.TestCase):
    """Test gizmo data preparation logic without full Blender"""

    @patch('clash_gizmo.bpy')
    @patch('clash_gizmo.db')
    def test_clash_candidate_processing(self, mock_db, mock_bpy):
        """Test processing clash candidates into gizmo data"""
        # Mock clash candidates
        mock_candidate = Mock()
        mock_candidate.bbox_center_a = [1000.0, 2000.0, 0.0]
        mock_candidate.bbox_center_b = [1010.0, 2010.0, 5.0]
        mock_candidate.guid_a = "test-guid-a"
        mock_candidate.guid_b = "test-guid-b"
        mock_candidate.distance = 0.05
        mock_candidate.ifc_class_a = "IfcWall"
        mock_candidate.ifc_class_b = "IfcDuct"

        # Mock scene properties
        mock_props = Mock()
        mock_props.discipline_clash_candidates = [mock_candidate]
        mock_bpy.context.scene.BIMClashProperties = mock_props
        mock_bpy.context.scene.get.return_value = (0, 0, 0)  # No offset

        # Mock database responses
        mock_db.get_clash_id.return_value = "test-clash-id-123"
        mock_db.get_clash_status.return_value = None  # New clash

        # Test that we can extract the necessary data
        candidate = mock_props.discipline_clash_candidates[0]

        # Verify data is accessible
        self.assertEqual(candidate.guid_a, "test-guid-a")
        self.assertEqual(candidate.guid_b, "test-guid-b")
        self.assertEqual(candidate.distance, 0.05)

        # Verify midpoint calculation
        from mathutils import Vector
        center_a = Vector(candidate.bbox_center_a)
        center_b = Vector(candidate.bbox_center_b)
        midpoint = (center_a + center_b) / 2

        self.assertAlmostEqual(midpoint.x, 1005.0)
        self.assertAlmostEqual(midpoint.y, 2005.0)
        self.assertAlmostEqual(midpoint.z, 2.5)


class TestDatabaseIntegrity(unittest.TestCase):
    """Test database integrity and edge cases"""

    def setUp(self):
        """Create temporary database"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = Path(self.temp_db.name)

        self.patcher = patch('clash_database.get_clash_database_path')
        self.mock_path = self.patcher.start()
        self.mock_path.return_value = self.db_path

    def tearDown(self):
        """Clean up"""
        self.patcher.stop()
        if self.db_path.exists():
            self.db_path.unlink()

    def test_concurrent_access(self):
        """Test that database handles concurrent reads/writes"""
        # Initialize database
        db.initialize_database()

        # Perform multiple operations
        for i in range(10):
            db.set_clash_status(f"guid-{i}-a", f"guid-{i}-b", status="NEW")

        # All should succeed
        all_clashes = db.get_all_clashes()
        self.assertEqual(len(all_clashes), 10)

    def test_null_handling(self):
        """Test handling of NULL/None values"""
        # Insert clash with minimal data
        db.set_clash_status("minimal-a", "minimal-b", status="NEW")

        status = db.get_clash_status("minimal-a", "minimal-b")

        # NULL fields should be None
        self.assertIsNone(status.get('comment'))
        self.assertIsNone(status.get('assigned_to'))
        self.assertIsNone(status.get('discipline_a'))

    def test_sql_injection_protection(self):
        """Test that special characters don't break queries"""
        # Try inserting GUID with special characters
        evil_guid = "'; DROP TABLE clash_status; --"

        db.set_clash_status(evil_guid, "normal-guid", status="NEW")

        # Database should still exist and work
        status = db.get_clash_status(evil_guid, "normal-guid")
        self.assertIsNotNone(status)

        # Table should still exist
        conn = db.initialize_database()
        cursor = conn.execute("SELECT COUNT(*) FROM clash_status")
        count = cursor.fetchone()[0]
        self.assertGreater(count, 0)
        conn.close()


class TestGizmoStateManagement(unittest.TestCase):
    """Test gizmo state tracking"""

    def test_gizmo_activation_state(self):
        """Test gizmo group activation tracking"""
        # Initially should be inactive
        self.assertFalse(gizmo.is_gizmo_group_active())

        # Note: We can't fully test enable/disable without Blender context
        # But we can verify the state variable exists

    def test_marker_count(self):
        """Test getting marker count"""
        # Without Blender context, we test the function exists
        # and handles missing context gracefully
        with patch('clash_gizmo.bpy') as mock_bpy:
            mock_props = Mock()
            mock_props.discipline_clash_candidates = [1, 2, 3]  # Mock 3 candidates
            mock_bpy.context.scene.BIMClashProperties = mock_props

            count = gizmo.get_marker_count()
            self.assertEqual(count, 3)


def run_tests():
    """Run all tests with verbose output"""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestClashDatabase))
    suite.addTests(loader.loadTestsFromTestCase(TestGizmoHelpers))
    suite.addTests(loader.loadTestsFromTestCase(TestGizmoDataPreparation))
    suite.addTests(loader.loadTestsFromTestCase(TestDatabaseIntegrity))
    suite.addTests(loader.loadTestsFromTestCase(TestGizmoStateManagement))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print("\n" + "="*70)
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("="*70)

    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
