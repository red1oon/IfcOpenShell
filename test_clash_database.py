#!/usr/bin/env python3
"""
Standalone tests for clash database persistence

These tests can run without Blender and test the SQLite database logic.
For full gizmo viewport tests, see test_clash_gizmo_blender.py (requires Blender)

Run with: python3 test_clash_database.py
"""

import unittest
import sqlite3
import tempfile
import sys
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch
import importlib.util

# Mock bpy before loading database module
sys.modules['bpy'] = Mock()
sys.modules['bpy.context'] = Mock()

# Load database module
def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module

clash_dir = Path(__file__).parent / 'src/bonsai/bonsai/bim/module/clash'
db = load_module('clash_database', clash_dir / 'database.py')


class TestClashDatabase(unittest.TestCase):
    """Test suite for clash database persistence"""

    def setUp(self):
        """Create temporary database for each test"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = Path(self.temp_db.name)

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

        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row[0] for row in cursor.fetchall()}

        self.assertIn('clash_status', tables)
        self.assertIn('clash_history', tables)

        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
        indexes = {row[0] for row in cursor.fetchall()}

        self.assertIn('idx_status', indexes)
        self.assertIn('idx_guid_a', indexes)

        conn.close()
        print("✓ Database schema initialized correctly")

    def test_clash_id_generation(self):
        """Test stable clash ID generation"""
        guid_a = "2O2Fr$t4X7Zf8NOew3FNr2"
        guid_b = "3P3Gs$u5Y8Ag9OPfx4GOr3"

        id1 = db.get_clash_id(guid_a, guid_b)
        id2 = db.get_clash_id(guid_b, guid_a)

        self.assertEqual(id1, id2)
        self.assertEqual(len(id1), 32)
        print(f"✓ Clash ID generation: {id1}")

    def test_insert_and_retrieve_clash(self):
        """Test inserting and retrieving a clash"""
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

        status = db.get_clash_status("guid-wall-001", "guid-duct-001")

        self.assertIsNotNone(status)
        self.assertEqual(status['status'], 'NEW')
        self.assertEqual(status['distance'], 0.05)
        self.assertEqual(status['ifc_class_a'], 'IfcWall')
        print(f"✓ Inserted clash: {clash_id[:8]}... (status={status['status']})")

    def test_update_clash_status(self):
        """Test updating existing clash"""
        db.set_clash_status("guid-a", "guid-b", status="NEW", distance=0.1)
        db.set_clash_status("guid-a", "guid-b", status="REVIEWED", comment="Approved")

        status = db.get_clash_status("guid-a", "guid-b")
        self.assertEqual(status['status'], 'REVIEWED')
        self.assertEqual(status['comment'], 'Approved')
        print(f"✓ Updated clash status: NEW → REVIEWED")

    def test_clash_history_tracking(self):
        """Test audit log"""
        db.set_clash_status("guid-x", "guid-y", status="NEW")
        db.set_clash_status("guid-x", "guid-y", status="ACTIVE", changed_by="Alice")
        db.set_clash_status("guid-x", "guid-y", status="REVIEWED", changed_by="Bob")
        db.set_clash_status("guid-x", "guid-y", status="RESOLVED", changed_by="Charlie")

        clash_id = db.get_clash_id("guid-x", "guid-y")
        history = db.get_clash_history(clash_id)

        self.assertEqual(len(history), 4)
        self.assertEqual(history[0]['new_status'], 'RESOLVED')
        self.assertEqual(history[0]['changed_by'], 'Charlie')
        print(f"✓ Clash history: {len(history)} status changes tracked")

    def test_bulk_status_update(self):
        """Test bulk updating"""
        ids = []
        for i in range(5):
            clash_id = db.set_clash_status(f"guid-a-{i}", f"guid-b-{i}", status="NEW")
            ids.append(clash_id)

        count = db.bulk_update_status(ids, "RESOLVED", changed_by="BulkUpdate")

        self.assertEqual(count, 5)
        print(f"✓ Bulk updated {count} clashes")

    def test_statistics(self):
        """Test statistics generation"""
        db.set_clash_status("g1a", "g1b", status="NEW", discipline_a="ARC", discipline_b="STR")
        db.set_clash_status("g2a", "g2b", status="NEW", discipline_a="ARC", discipline_b="STR")
        db.set_clash_status("g3a", "g3b", status="ACTIVE", discipline_a="ARC", discipline_b="MEP")
        db.set_clash_status("g4a", "g4b", status="REVIEWED", discipline_a="MEP", discipline_b="STR")
        db.set_clash_status("g5a", "g5b", status="RESOLVED", discipline_a="MEP", discipline_b="STR")

        stats = db.get_statistics()

        self.assertEqual(stats['total'], 5)
        self.assertEqual(stats['by_status']['NEW'], 2)
        print(f"✓ Statistics: {stats['total']} total, {stats['by_status']}")

    def test_sql_injection_protection(self):
        """Test special character handling"""
        evil_guid = "'; DROP TABLE clash_status; --"

        db.set_clash_status(evil_guid, "normal-guid", status="NEW")
        status = db.get_clash_status(evil_guid, "normal-guid")

        self.assertIsNotNone(status)
        print(f"✓ SQL injection protection working")


def run_tests():
    """Run all database tests"""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromTestCase(TestClashDatabase)

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print("\n" + "="*70)
    print(f"Database Tests Complete")
    print(f"Tests run: {result.testsRun}")
    print(f"Successes: {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures: {len(result.failures)}")
    print(f"Errors: {len(result.errors)}")
    print("="*70)

    return result.wasSuccessful()


if __name__ == "__main__":
    print("\n🧪 Testing Clash Database Module\n")
    success = run_tests()
    sys.exit(0 if success else 1)
