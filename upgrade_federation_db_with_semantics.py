#!/usr/bin/env python3
"""
Upgrade existing federation database with semantic metadata tables.
Adds semantic tables and populates them for existing elements.
"""

import sqlite3
import sys
from pathlib import Path

# Import semantic utils
sys.path.insert(0, '/home/red1/Projects/IfcOpenShell/src')
semantic_utils_path = '/home/red1/Projects/IfcOpenShell/src/bonsai/bonsai/bim/module/federation/semantic_utils.py'
import importlib.util
spec = importlib.util.spec_from_file_location("semantic_utils", semantic_utils_path)
semantic_utils = importlib.util.module_from_spec(spec)
spec.loader.exec_module(semantic_utils)


def upgrade_database(db_path: str):
    """Upgrade existing federation database with semantic tables"""

    print("=" * 70)
    print("UPGRADING FEDERATION DATABASE WITH SEMANTIC METADATA")
    print("=" * 70)
    print(f"Database: {db_path}\n")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if semantic tables already exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='element_semantics'")
    if cursor.fetchone():
        print("⚠️  Semantic tables already exist. Dropping and recreating...\n")
        cursor.execute("DROP TABLE IF EXISTS element_semantics")
        cursor.execute("DROP TABLE IF EXISTS material_library")
        conn.commit()

    # Create semantic tables
    print("Step 1: Creating semantic tables...")

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

    # Populate material library
    print("\nStep 2: Populating material library...")
    MATERIAL_LIBRARY_DATA = semantic_utils.MATERIAL_LIBRARY_DATA
    for material in MATERIAL_LIBRARY_DATA:
        cursor.execute("""
            INSERT INTO material_library
            (id, name, category, generation_rules, base_color, metallic, roughness, transparency, emissive)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (material['id'], material['name'], material['category'], material['generation_rules'],
              material['base_color'], material['metallic'], material['roughness'],
              material['transparency'], material['emissive']))
    print(f"  ✓ {len(MATERIAL_LIBRARY_DATA)} materials added")

    conn.commit()

    # Populate semantic metadata for existing elements
    print("\nStep 3: Extracting semantic metadata for existing elements...")

    cursor.execute("""
        SELECT m.id, m.guid, m.discipline, m.ifc_class,
               r.min_x, r.min_y, r.min_z, r.max_x, r.max_y, r.max_z
        FROM elements_meta m
        JOIN elements_rtree r ON m.id = r.id
    """)

    elements = cursor.fetchall()
    total = len(elements)
    print(f"  Processing {total:,} elements...")

    batch_size = 1000
    for i, elem in enumerate(elements):
        elem_id, guid, discipline, ifc_class, min_x, min_y, min_z, max_x, max_y, max_z = elem

        # Extract semantic metadata
        bbox = (min_x, min_y, min_z, max_x, max_y, max_z)
        semantic_data = semantic_utils.extract_semantic_metadata(guid, ifc_class, discipline, bbox)

        # Insert semantic metadata
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

        if (i + 1) % batch_size == 0:
            conn.commit()
            print(f"    {i+1:,}/{total:,} ({(i+1)/total*100:.1f}%)...")

    conn.commit()
    print(f"  ✓ All {total:,} elements processed")

    # Verification
    print("\nStep 4: Verification...")

    cursor.execute("SELECT COUNT(*) FROM element_semantics")
    semantic_count = cursor.fetchone()[0]
    print(f"  ✓ element_semantics: {semantic_count:,} rows")

    cursor.execute("""
        SELECT semantic_type, COUNT(*)
        FROM element_semantics
        GROUP BY semantic_type
        ORDER BY COUNT(*) DESC
    """)
    distribution = cursor.fetchall()
    print(f"\n  Semantic type distribution:")
    for stype, count in distribution:
        print(f"    {stype:15s}: {count:6,} elements")

    # Sample verification
    print(f"\n  Sample MEP element verification:")
    cursor.execute("""
        SELECT m.guid, m.ifc_class, m.discipline,
               s.semantic_type, s.subtype, s.material_id, s.dominant_axis,
               s.profile_width, s.profile_height
        FROM elements_meta m
        JOIN element_semantics s ON m.guid = s.guid
        WHERE s.semantic_type IN ('duct', 'pipe', 'conduit')
        LIMIT 3
    """)

    for row in cursor.fetchall():
        guid, ifc_class, discipline, sem_type, subtype, mat_id, axis, width, height = row
        print(f"\n    {ifc_class} ({discipline})")
        print(f"      Semantic: {sem_type} / {subtype}")
        print(f"      Material ID: {mat_id}")
        print(f"      Dominant Axis: {axis}")
        print(f"      Profile: {width:.0f}mm × {height:.0f}mm")

    # Database size
    conn.close()
    db_size_mb = Path(db_path).stat().st_size / (1024 * 1024)

    print(f"\n{'='*70}")
    print(f"✅ UPGRADE COMPLETE")
    print(f"{'='*70}")
    print(f"Database: {db_path}")
    print(f"Size: {db_size_mb:.2f} MB")
    print(f"Elements: {semantic_count:,} with semantic metadata")
    print(f"Materials: {len(MATERIAL_LIBRARY_DATA)}")
    print(f"{'='*70}\n")


if __name__ == '__main__':
    db_path = '/home/red1/Documents/bonsai/federation_index.db'

    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)

    # Backup first
    backup_path = f"{db_path}.backup_{Path().cwd().name}"
    print(f"Creating backup: {backup_path}")
    import shutil
    shutil.copy2(db_path, backup_path)
    print(f"✓ Backup created\n")

    try:
        upgrade_database(db_path)
        print("✅ Success! Database upgraded with semantic metadata.")
        print(f"\nBackup saved at: {backup_path}")
        print(f"Original DB updated: {db_path}")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error during upgrade: {e}")
        import traceback
        traceback.print_exc()
        print(f"\n⚠️  Restoring from backup...")
        shutil.copy2(backup_path, db_path)
        print(f"✓ Database restored from backup")
        sys.exit(1)
