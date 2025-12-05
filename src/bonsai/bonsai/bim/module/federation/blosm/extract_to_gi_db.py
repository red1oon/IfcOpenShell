#!/usr/bin/env python3
"""
Extract single IFC file to GI (Geographic Information) database
Simplified version for BLOSM river IFC
"""
import sys
import os
import sqlite3
from pathlib import Path

# Add ifcopenshell from Blender's Bonsai
wheel_dir = Path.home() / ".config/blender/4.5/extensions/.local/lib/python3.11/site-packages"
if wheel_dir.exists():
    sys.path.insert(0, str(wheel_dir))

try:
    import ifcopenshell
    import ifcopenshell.geom
    import numpy as np
except ImportError as e:
    print(f"ERROR: Could not import required modules: {e}")
    print("This script should be run with Blender's Python or with ifcopenshell installed")
    sys.exit(1)

# Input/Output
IFC_FILE = "/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/output/klang_river_500m_crop.ifc"
DB_FILE = "/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/databases/klang_river_gi.db"

# Geometric classes to include
GEOMETRIC_CLASSES = {
    "IfcGeographicElement", "IfcBuildingElementProxy",
    "IfcWall", "IfcBeam", "IfcColumn", "IfcSlab",
    "IfcDoor", "IfcWindow", "IfcRoof"
}

def create_database_schema(cursor):
    """Create GI database schema"""
    print("\n[1] Creating database schema...")

    # Schema version
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_info (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cursor.execute("INSERT OR REPLACE INTO schema_info VALUES ('version', '1.0')")
    cursor.execute("INSERT OR REPLACE INTO schema_info VALUES ('source', 'BLOSM OSM Import')")

    # Main elements table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS elements_meta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guid TEXT UNIQUE NOT NULL,
            discipline TEXT NOT NULL,
            ifc_class TEXT NOT NULL,
            name TEXT,
            description TEXT,
            object_type TEXT,
            predefined_type TEXT,
            material TEXT
        )
    """)

    # Geometry transformations
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS element_transforms (
            guid TEXT PRIMARY KEY,
            center_x REAL,
            center_y REAL,
            center_z REAL,
            bbox_min_x REAL,
            bbox_min_y REAL,
            bbox_min_z REAL,
            bbox_max_x REAL,
            bbox_max_y REAL,
            bbox_max_z REAL,
            rotation_matrix TEXT,
            FOREIGN KEY (guid) REFERENCES elements_meta(guid)
        )
    """)

    # Spatial context
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS site_context (
            discipline TEXT PRIMARY KEY,
            site_offset_x REAL,
            site_offset_y REAL,
            site_offset_z REAL,
            ref_latitude REAL,
            ref_longitude REAL,
            ref_elevation REAL
        )
    """)

    # Global offset table (for viewport coordinate queries)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS global_offset (
            offset_x REAL NOT NULL,
            offset_y REAL NOT NULL,
            offset_z REAL NOT NULL,
            extent_x REAL,
            extent_y REAL,
            extent_z REAL
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO global_offset (offset_x, offset_y, offset_z) VALUES (0.0, 0.0, 0.0)")

    # R-tree spatial index (CRITICAL for federation queries)
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS elements_rtree USING rtree(
            id,
            minX, maxX,
            minY, maxY,
            minZ, maxZ
        )
    """)

    # GI Schema: Base geometries (shared mesh data)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS base_geometries (
            geometry_hash TEXT PRIMARY KEY,
            vertices BLOB NOT NULL,
            faces BLOB NOT NULL,
            normals BLOB,
            vertex_count INTEGER NOT NULL,
            face_count INTEGER NOT NULL
        )
    """)

    # GI Schema: Element instances (links elements to geometry)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS element_instances (
            guid TEXT PRIMARY KEY,
            geometry_hash TEXT NOT NULL,
            FOREIGN KEY (geometry_hash) REFERENCES base_geometries(geometry_hash)
        )
    """)

    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_guid ON elements_meta(guid)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_class ON elements_meta(ifc_class)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_discipline ON elements_meta(discipline)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_geometry_hash ON element_instances(geometry_hash)")

    print("  ✓ Schema created (with R-tree + GI tables)")

def calculate_bbox(shape):
    """Calculate bounding box from shape geometry"""
    try:
        verts = shape.geometry.verts
        if not verts:
            return None

        # Group into xyz triplets
        coords = np.array(verts).reshape(-1, 3)

        bbox = {
            'min_x': float(np.min(coords[:, 0])),
            'min_y': float(np.min(coords[:, 1])),
            'min_z': float(np.min(coords[:, 2])),
            'max_x': float(np.max(coords[:, 0])),
            'max_y': float(np.max(coords[:, 1])),
            'max_z': float(np.max(coords[:, 2])),
        }

        # Calculate center
        bbox['center_x'] = (bbox['min_x'] + bbox['max_x']) / 2
        bbox['center_y'] = (bbox['min_y'] + bbox['max_y']) / 2
        bbox['center_z'] = (bbox['min_z'] + bbox['max_z']) / 2

        return bbox
    except Exception as e:
        print(f"    Warning: Could not calculate bbox: {e}")
        return None

def store_geometry_gi(cursor, guid, shape):
    """Store geometry in GI tables (base_geometries + element_instances)"""
    import hashlib
    import struct

    try:
        # Extract geometry data
        verts = shape.geometry.verts
        faces_list = shape.geometry.faces

        if not verts or not faces_list:
            return None

        # Convert to numpy arrays
        vertices = np.array(verts, dtype=np.float32).reshape(-1, 3)
        faces = np.array(faces_list, dtype=np.int32).reshape(-1, 3)

        # Calculate geometry hash
        geom_data = vertices.tobytes() + faces.tobytes()
        geometry_hash = hashlib.sha256(geom_data).hexdigest()[:16]

        # Check if geometry already exists (instancing)
        cursor.execute("SELECT geometry_hash FROM base_geometries WHERE geometry_hash = ?", (geometry_hash,))
        if not cursor.fetchone():
            # Store new base geometry
            cursor.execute("""
                INSERT INTO base_geometries
                (geometry_hash, vertices, faces, normals, vertex_count, face_count)
                VALUES (?, ?, ?, NULL, ?, ?)
            """, (
                geometry_hash,
                vertices.tobytes(),
                faces.tobytes(),
                len(vertices),
                len(faces)
            ))

        # Link element to geometry
        cursor.execute("""
            INSERT OR REPLACE INTO element_instances (guid, geometry_hash)
            VALUES (?, ?)
        """, (guid, geometry_hash))

        return geometry_hash

    except Exception as e:
        print(f"    Warning: Could not store GI geometry: {e}")
        return None

def extract_elements(ifc_file, cursor, discipline="GEO"):
    """Extract elements from IFC and populate database"""
    print(f"\n[2] Extracting elements from IFC...")

    ifc = ifcopenshell.open(ifc_file)
    print(f"  IFC Schema: {ifc.schema}")

    # Setup geometry settings
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)

    # Get all geometric products
    products = []
    for ifc_class in GEOMETRIC_CLASSES:
        products.extend(ifc.by_type(ifc_class))

    print(f"  Found {len(products)} geometric elements")

    # Process each element
    inserted = 0
    skipped = 0

    for i, element in enumerate(products):
        if (i + 1) % 10 == 0:
            print(f"  Processing {i+1}/{len(products)}...", end='\r')

        try:
            guid = element.GlobalId
            ifc_class = element.is_a()
            name = getattr(element, 'Name', None) or f"{ifc_class}_{guid[:8]}"
            description = getattr(element, 'Description', None)
            object_type = getattr(element, 'ObjectType', None)
            predefined_type = getattr(element, 'PredefinedType', None)

            # Get material
            material = None
            if hasattr(element, 'HasAssociations'):
                for rel in element.HasAssociations:
                    if rel.is_a('IfcRelAssociatesMaterial'):
                        mat = rel.RelatingMaterial
                        if hasattr(mat, 'Name'):
                            material = mat.Name
                        break

            # Insert metadata
            cursor.execute("""
                INSERT OR IGNORE INTO elements_meta
                (guid, discipline, ifc_class, name, description, object_type, predefined_type, material)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (guid, discipline, ifc_class, name, description, object_type, predefined_type, material))

            # Get the element ID
            cursor.execute("SELECT id FROM elements_meta WHERE guid = ?", (guid,))
            element_id = cursor.fetchone()[0]

            # Try to get geometry and calculate bbox
            try:
                shape = ifcopenshell.geom.create_shape(settings, element)

                # Store in GI tables
                store_geometry_gi(cursor, guid, shape)

                # Calculate bbox
                bbox = calculate_bbox(shape)

                if bbox:
                    cursor.execute("""
                        INSERT OR REPLACE INTO element_transforms
                        (guid, center_x, center_y, center_z,
                         bbox_min_x, bbox_min_y, bbox_min_z,
                         bbox_max_x, bbox_max_y, bbox_max_z)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        guid,
                        bbox['center_x'], bbox['center_y'], bbox['center_z'],
                        bbox['min_x'], bbox['min_y'], bbox['min_z'],
                        bbox['max_x'], bbox['max_y'], bbox['max_z']
                    ))

                    # Insert into R-tree spatial index
                    cursor.execute("""
                        INSERT INTO elements_rtree
                        (id, minX, maxX, minY, maxY, minZ, maxZ)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        element_id,
                        bbox['min_x'], bbox['max_x'],
                        bbox['min_y'], bbox['max_y'],
                        bbox['min_z'], bbox['max_z']
                    ))
            except Exception as e:
                # Element has no geometry representation, skip transform
                pass

            inserted += 1

        except Exception as e:
            print(f"    Warning: Error processing {element.GlobalId}: {e}")
            skipped += 1

    print(f"\n  ✓ Processed {len(products)} elements")
    print(f"    Inserted: {inserted}")
    print(f"    Skipped:  {skipped}")

    return inserted

def extract_site_context(ifc_file, cursor, discipline="GEO"):
    """Extract site context from IFC"""
    print(f"\n[3] Extracting site context...")

    ifc = ifcopenshell.open(ifc_file)

    # Get site placement
    sites = ifc.by_type("IfcSite")
    if sites:
        site = sites[0]
        offset_x, offset_y, offset_z = 0.0, 0.0, 0.0

        if site.ObjectPlacement:
            try:
                placement = site.ObjectPlacement
                if hasattr(placement, 'RelativePlacement'):
                    rel_placement = placement.RelativePlacement
                    if hasattr(rel_placement, 'Location'):
                        loc = rel_placement.Location
                        if hasattr(loc, 'Coordinates'):
                            coords = loc.Coordinates
                            offset_x = coords[0] if len(coords) > 0 else 0.0
                            offset_y = coords[1] if len(coords) > 1 else 0.0
                            offset_z = coords[2] if len(coords) > 2 else 0.0
            except Exception as e:
                print(f"    Warning: Could not extract site placement: {e}")

        # Check for georeferencing
        ref_lat, ref_lon, ref_elev = None, None, None
        if hasattr(site, 'RefLatitude') and site.RefLatitude:
            ref_lat = site.RefLatitude
        if hasattr(site, 'RefLongitude') and site.RefLongitude:
            ref_lon = site.RefLongitude
        if hasattr(site, 'RefElevation') and site.RefElevation:
            ref_elev = site.RefElevation

        cursor.execute("""
            INSERT OR REPLACE INTO site_context
            (discipline, site_offset_x, site_offset_y, site_offset_z,
             ref_latitude, ref_longitude, ref_elevation)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (discipline, offset_x, offset_y, offset_z, ref_lat, ref_lon, ref_elev))

        print(f"  ✓ Site offset: ({offset_x:.2f}, {offset_y:.2f}, {offset_z:.2f})")
        if ref_lat or ref_lon:
            print(f"    Georeferenced: Lat={ref_lat}, Lon={ref_lon}")
    else:
        print("  ✓ No site found, using defaults")

def main():
    print("="*60)
    print("EXTRACT IFC TO GI DATABASE")
    print("="*60)
    print(f"\nInput:  {IFC_FILE}")
    print(f"Output: {DB_FILE}")

    # Check input exists
    if not os.path.exists(IFC_FILE):
        print(f"\n✗ ERROR: Input file not found: {IFC_FILE}")
        return 1

    # Create output directory
    Path(DB_FILE).parent.mkdir(parents=True, exist_ok=True)

    # Remove old database
    if os.path.exists(DB_FILE):
        print(f"\n⚠  Removing existing database...")
        os.remove(DB_FILE)

    # Create database
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        # Create schema
        create_database_schema(cursor)

        # Extract elements
        count = extract_elements(IFC_FILE, cursor, discipline="GEO")

        # Extract site context
        extract_site_context(IFC_FILE, cursor, discipline="GEO")

        # Commit
        conn.commit()

        # Verify
        cursor.execute("SELECT COUNT(*) FROM elements_meta")
        total = cursor.fetchone()[0]

        print("\n" + "="*60)
        print("SUCCESS")
        print("="*60)
        print(f"Database: {DB_FILE}")
        print(f"Elements: {total}")

        # Show breakdown
        cursor.execute("SELECT ifc_class, COUNT(*) FROM elements_meta GROUP BY ifc_class")
        print("\nBreakdown by class:")
        for ifc_class, count in cursor.fetchall():
            print(f"  {ifc_class}: {count}")

        db_size = os.path.getsize(DB_FILE) / 1024
        print(f"\nDatabase size: {db_size:.1f} KB")

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        conn.close()

    print("\n" + "="*60)
    return 0

if __name__ == "__main__":
    sys.exit(main())
