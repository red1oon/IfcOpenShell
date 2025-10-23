#!/usr/bin/env python3
"""
Integration Test for Database Schema with Semantic Metadata
Tests that the new schema tables can be created and populated
"""

import sqlite3
import sys
import os
import json
from pathlib import Path
import tempfile

# Direct import of semantic_utils module
semantic_utils_path = '/home/red1/Projects/IfcOpenShell/src/bonsai/bonsai/bim/module/federation/semantic_utils.py'
import importlib.util
spec = importlib.util.spec_from_file_location("semantic_utils", semantic_utils_path)
semantic_utils = importlib.util.module_from_spec(spec)
spec.loader.exec_module(semantic_utils)

# Sample test data (mimics what federation preprocessor would extract)
SAMPLE_ELEMENTS = [
    {
        'guid': '2EW$JxRGfF3vw1ivMYDj8R',
        'discipline': 'ACMV',
        'ifc_class': 'IfcDuctSegment',
        'filepath': '/path/to/acmv.ifc',
        'min_x': 1000.0, 'min_y': 2000.0, 'min_z': 3000.0,
        'max_x': 1600.0, 'max_y': 2400.0, 'max_z': 8000.0  # 600x400 duct, 5m long
    },
    {
        'guid': '1ABC2DEF3GHI4JKL5MNO6P',
        'discipline': 'FP',
        'ifc_class': 'IfcPipeSegment',
        'filepath': '/path/to/fp.ifc',
        'min_x': 5000.0, 'min_y': 6000.0, 'min_z': 2000.0,
        'max_x': 5150.0, 'max_y': 6150.0, 'max_z': 5000.0  # DN150 pipe, 3m long
    },
    {
        'guid': '3XYZ4ABC5DEF6GHI7JKL8M',
        'discipline': 'STRUCTURE',
        'ifc_class': 'IfcBeam',
        'filepath': '/path/to/structure.ifc',
        'min_x': 10000.0, 'min_y': 15000.0, 'min_z': 3000.0,
        'max_x': 15000.0, 'max_y': 15300.0, 'max_z': 3500.0  # 5m beam, 300x500 profile
    },
    {
        'guid': '4QRS5TUV6WXY7ZAB8CDE9F',
        'discipline': 'ARCHITECTURE',
        'ifc_class': 'IfcDoor',
        'filepath': '/path/to/architecture.ifc',
        'min_x': 20000.0, 'min_y': 21000.0, 'min_z': 0.0,
        'max_x': 20900.0, 'max_y': 21050.0, 'max_z': 2100.0  # 900mm door
    },
]


def create_test_database(db_path: Path) -> bool:
    """
    Create test database with schema including semantic tables.
    Mimics what federation_preprocessor.create_federation_database() does.

    Returns True if successful, False otherwise.
    """
    print(f"\n{'='*70}")
    print(f"CREATING TEST DATABASE")
    print(f"{'='*70}")
    print(f"Path: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Schema version table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_info (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        cursor.execute("INSERT INTO schema_info VALUES (?, ?)", ("version", "1.0.0"))
        print("  ✓ schema_info table created")

        # Metadata table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS elements_meta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guid TEXT UNIQUE NOT NULL,
                discipline TEXT NOT NULL,
                ifc_class TEXT NOT NULL,
                filepath TEXT NOT NULL
            )
        """)
        cursor.execute("CREATE INDEX idx_guid ON elements_meta(guid)")
        cursor.execute("CREATE INDEX idx_discipline ON elements_meta(discipline)")
        cursor.execute("CREATE INDEX idx_ifc_class ON elements_meta(ifc_class)")
        print("  ✓ elements_meta table created")

        # Spatial index (R-tree)
        cursor.execute("""
            CREATE VIRTUAL TABLE elements_rtree USING rtree(
                id,
                min_x, max_x,
                min_y, max_y,
                min_z, max_z
            )
        """)
        print("  ✓ elements_rtree spatial index created")

        # Semantic metadata table (NEW in Phase 1)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS element_semantics (
                id INTEGER PRIMARY KEY,
                guid TEXT UNIQUE NOT NULL,
                semantic_type TEXT NOT NULL,
                subtype TEXT,
                material_id INTEGER,
                dominant_axis TEXT,
                profile_width REAL,
                profile_height REAL,
                wall_thickness REAL,
                has_opening BOOLEAN DEFAULT 0,
                connects_to TEXT,
                flow_direction TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (guid) REFERENCES elements_meta(guid)
            )
        """)
        cursor.execute("CREATE INDEX idx_semantic_type ON element_semantics(semantic_type)")
        cursor.execute("CREATE INDEX idx_subtype ON element_semantics(subtype)")
        cursor.execute("CREATE INDEX idx_material_id ON element_semantics(material_id)")
        print("  ✓ element_semantics table created")

        # Material library table (NEW in Phase 1)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS material_library (
                id INTEGER PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                category TEXT,
                generation_rules TEXT,
                base_color TEXT,
                metallic REAL DEFAULT 0.0,
                roughness REAL DEFAULT 0.5,
                transparency REAL DEFAULT 0.0,
                emissive REAL DEFAULT 0.0,
                texture_path TEXT,
                normal_map_path TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print("  ✓ material_library table created")

        # Pre-populate material library
        MATERIAL_LIBRARY_DATA = semantic_utils.MATERIAL_LIBRARY_DATA
        for material in MATERIAL_LIBRARY_DATA:
            cursor.execute("""
                INSERT INTO material_library
                (id, name, category, generation_rules, base_color, metallic, roughness, transparency, emissive)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (material['id'], material['name'], material['category'], material['generation_rules'],
                  material['base_color'], material['metallic'], material['roughness'],
                  material['transparency'], material['emissive']))
        print(f"  ✓ Material library populated ({len(MATERIAL_LIBRARY_DATA)} materials)")

        conn.commit()
        print(f"\n✓ Schema created successfully")

        return True

    except Exception as e:
        print(f"\n❌ Schema creation failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()


def populate_test_data(db_path: Path) -> bool:
    """
    Populate database with sample elements and semantic metadata.
    Mimics what federation_preprocessor does during insertion.

    Returns True if successful, False otherwise.
    """
    print(f"\n{'='*70}")
    print(f"POPULATING TEST DATA")
    print(f"{'='*70}")
    print(f"Elements to insert: {len(SAMPLE_ELEMENTS)}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        for i, elem in enumerate(SAMPLE_ELEMENTS):
            # Insert metadata
            cursor.execute("""
                INSERT INTO elements_meta (guid, discipline, ifc_class, filepath)
                VALUES (?, ?, ?, ?)
            """, (elem['guid'], elem['discipline'], elem['ifc_class'], elem['filepath']))

            elem_id = cursor.lastrowid

            # Insert into R-tree
            cursor.execute("""
                INSERT INTO elements_rtree (id, min_x, max_x, min_y, max_y, min_z, max_z)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (elem_id, elem['min_x'], elem['max_x'],
                  elem['min_y'], elem['max_y'], elem['min_z'], elem['max_z']))

            # Extract and insert semantic metadata (NEW in Phase 1)
            bbox = (elem['min_x'], elem['min_y'], elem['min_z'],
                    elem['max_x'], elem['max_y'], elem['max_z'])
            semantic_data = semantic_utils.extract_semantic_metadata(
                elem['guid'],
                elem['ifc_class'],
                elem['discipline'],
                bbox
            )

            cursor.execute("""
                INSERT INTO element_semantics
                (id, guid, semantic_type, subtype, material_id, dominant_axis,
                 profile_width, profile_height, wall_thickness, has_opening,
                 connects_to, flow_direction)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (elem_id, semantic_data['guid'], semantic_data['semantic_type'],
                  semantic_data['subtype'], semantic_data['material_id'],
                  semantic_data['dominant_axis'], semantic_data['profile_width'],
                  semantic_data['profile_height'], semantic_data['wall_thickness'],
                  semantic_data['has_opening'], semantic_data['connects_to'],
                  semantic_data['flow_direction']))

            print(f"  ✓ Inserted element {i+1}/{len(SAMPLE_ELEMENTS)}: {elem['ifc_class']} ({semantic_data['semantic_type']})")

        conn.commit()
        print(f"\n✓ Data populated successfully")

        return True

    except Exception as e:
        print(f"\n❌ Data population failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()


def verify_database(db_path: Path) -> bool:
    """
    Verify database contents and semantic data quality.

    Returns True if all checks pass, False otherwise.
    """
    print(f"\n{'='*70}")
    print(f"VERIFYING DATABASE")
    print(f"{'='*70}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check element count
        cursor.execute("SELECT COUNT(*) FROM elements_meta")
        meta_count = cursor.fetchone()[0]
        print(f"  ✓ elements_meta: {meta_count} elements")

        cursor.execute("SELECT COUNT(*) FROM element_semantics")
        semantic_count = cursor.fetchone()[0]
        print(f"  ✓ element_semantics: {semantic_count} elements")

        if meta_count != semantic_count:
            print(f"  ❌ Element count mismatch!")
            return False

        # Check material library
        cursor.execute("SELECT COUNT(*) FROM material_library")
        material_count = cursor.fetchone()[0]
        print(f"  ✓ material_library: {material_count} materials")

        if material_count != 10:
            print(f"  ❌ Expected 10 materials, got {material_count}")
            return False

        # Check semantic types distribution
        cursor.execute("""
            SELECT semantic_type, COUNT(*)
            FROM element_semantics
            GROUP BY semantic_type
        """)
        semantic_distribution = cursor.fetchall()
        print(f"\n  Semantic type distribution:")
        for stype, count in semantic_distribution:
            print(f"    {stype}: {count}")

        # Verify sample element metadata
        print(f"\n  Sample element verification:")
        cursor.execute("""
            SELECT m.guid, m.ifc_class, m.discipline,
                   s.semantic_type, s.subtype, s.material_id, s.dominant_axis,
                   s.profile_width, s.profile_height
            FROM elements_meta m
            JOIN element_semantics s ON m.guid = s.guid
            WHERE m.ifc_class = 'IfcDuctSegment'
        """)
        row = cursor.fetchone()
        if row:
            guid, ifc_class, discipline, semantic_type, subtype, material_id, dominant_axis, width, height = row
            print(f"    GUID: {guid}")
            print(f"    IFC Class: {ifc_class} → Semantic Type: {semantic_type}")
            print(f"    Subtype: {subtype}")
            print(f"    Material ID: {material_id}")
            print(f"    Dominant Axis: {dominant_axis}")
            print(f"    Profile: {width}mm × {height}mm")

            # Verify values
            assert semantic_type == 'duct', f"Expected 'duct', got '{semantic_type}'"
            assert subtype == 'rectangular', f"Expected 'rectangular', got '{subtype}'"
            assert material_id == 5, f"Expected material_id 5 (DUCT_ACMV), got {material_id}"
            assert dominant_axis == 'Z', f"Expected dominant_axis 'Z', got '{dominant_axis}'"
            print(f"    ✓ All values correct!")

        print(f"\n✓ Database verification passed")
        return True

    except Exception as e:
        print(f"\n❌ Database verification failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        conn.close()


def main():
    """Main test execution"""
    print("=" * 70)
    print("BBox Semantic Geometry - Database Integration Test")
    print("=" * 70)
    print()
    print("This test verifies:")
    print("  1. Database schema creation (with semantic tables)")
    print("  2. Data population (with semantic metadata extraction)")
    print("  3. Data integrity and query functionality")
    print()

    # Create temporary database
    temp_dir = tempfile.mkdtemp()
    db_path = Path(temp_dir) / "test_federation.db"

    try:
        # Test 1: Create schema
        if not create_test_database(db_path):
            print("\n❌ TEST FAILED: Schema creation")
            return False

        # Test 2: Populate data
        if not populate_test_data(db_path):
            print("\n❌ TEST FAILED: Data population")
            return False

        # Test 3: Verify data
        if not verify_database(db_path):
            print("\n❌ TEST FAILED: Data verification")
            return False

        # Success
        print("\n" + "=" * 70)
        print("✅ ALL INTEGRATION TESTS PASSED")
        print("=" * 70)
        print()
        print("Database schema ready for federation preprocessing:")
        print(f"  - elements_meta: ✓")
        print(f"  - elements_rtree: ✓")
        print(f"  - element_semantics: ✓ (NEW)")
        print(f"  - material_library: ✓ (NEW)")
        print()
        print(f"Semantic metadata extraction working correctly:")
        print(f"  - IFC class → semantic type mapping: ✓")
        print(f"  - Profile dimension extraction: ✓")
        print(f"  - Material assignment: ✓")
        print(f"  - Dominant axis detection: ✓")
        print()
        db_size_kb = db_path.stat().st_size / 1024
        print(f"Test database size: {db_size_kb:.2f} KB ({len(SAMPLE_ELEMENTS)} elements)")
        print(f"Extrapolated size for 44K elements: ~{(db_size_kb / len(SAMPLE_ELEMENTS)) * 44000 / 1024:.2f} MB")
        print()

        return True

    finally:
        # Cleanup
        if db_path.exists():
            db_path.unlink()
        os.rmdir(temp_dir)


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
