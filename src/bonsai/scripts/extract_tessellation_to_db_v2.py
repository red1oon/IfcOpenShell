#!/usr/bin/env python3
"""
Enhanced Tessellation Extraction Script - IFC4 with Full Metadata
==================================================================

Extracts ALL tessellated geometry from IFC4 files with comprehensive metadata:
- All geometry types (not filtered subset)
- Material assignments with colors
- Element properties (Psets)
- Spatial hierarchy (building/storey/space)
- Enhanced database schema with metadata tables

Usage:
    PYTHONPATH=/home/red1/Projects/IfcOpenShell/src python3 extract_tessellation_to_db_v2.py

    # Test on small file first:
    PYTHONPATH=/home/red1/Projects/IfcOpenShell/src python3 extract_tessellation_to_db_v2.py --test
"""

import sys
import time
import sqlite3
import struct
import hashlib
import argparse
from pathlib import Path
from typing import Tuple, List, Dict, Optional

# Add IfcOpenShell path
sys.path.insert(0, '/home/red1/Projects/IfcOpenShell/src')

import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
import ifcopenshell.util.placement

# ============================================================================
# CONFIGURATION
# ============================================================================

IFC4_FILES = [
    "/home/red1/Documents/bonsai/PythonLibs/Terminal_1_IFC4/Terminal 1 IFC4/SJTII-ARC-A-TER1-00-R0-Clean.ifc",
    "/home/red1/Documents/bonsai/PythonLibs/Terminal_1_IFC4/Terminal 1 IFC4/SJTII-STR-S-TER1-00-R0-Clean.ifc",
    "/home/red1/Documents/bonsai/PythonLibs/Terminal_1_IFC4/Terminal 1 IFC4/SJTII-ACMV-A-TER1-00-R0-Clean.ifc",
    "/home/red1/Documents/bonsai/PythonLibs/Terminal_1_IFC4/Terminal 1 IFC4/SJTII-ELEC-A-TER1-00-R0-Clean.ifc",
    "/home/red1/Documents/bonsai/PythonLibs/Terminal_1_IFC4/Terminal 1 IFC4/SJTII-FP-A-TER1-00-R0-Clean.ifc",
    "/home/red1/Documents/bonsai/PythonLibs/Terminal_1_IFC4/Terminal 1 IFC4/SJTII-LPG-A-TER1-00-RO-Clean.ifc",
    "/home/red1/Documents/bonsai/PythonLibs/Terminal_1_IFC4/Terminal 1 IFC4/SJTII-SP-A-TER1-00-R0-Clean.ifc",
    "/home/red1/Documents/bonsai/PythonLibs/Terminal_1_IFC4/Terminal 1 IFC4/SJTII-CW-A-TER1-00-R0-Clean.ifc",
]

TEST_FILE = "/home/red1/Documents/bonsai/PythonLibs/Terminal_1_IFC4/Terminal 1 IFC4/SJTII-LPG-A-TER1-00-RO-Clean.ifc"

DISCIPLINE_MAP = {
    "ARC": "ARC",
    "STR": "STR",
    "CW": "CW",
    "FP": "FP",
    "SP": "SP",
    "ACMV": "ACMV",
    "ELEC": "ELEC",
    "LPG": "LPG"
}

# Discipline colors (RGBA)
DISCIPLINE_COLORS = {
    "ARC": (0.5, 0.7, 0.5, 1.0),      # Green
    "STR": (0.4, 0.4, 0.8, 1.0),      # Blue
    "CW": (0.6, 0.8, 0.9, 1.0),       # Light blue
    "FP": (0.9, 0.3, 0.3, 1.0),       # Red
    "SP": (0.5, 0.5, 0.9, 1.0),       # Light purple
    "ACMV": (0.9, 0.7, 0.3, 1.0),     # Orange
    "ELEC": (0.9, 0.9, 0.3, 1.0),     # Yellow
    "LPG": (0.7, 0.5, 0.3, 1.0),      # Brown
}

DB_PATH = "/home/red1/Documents/bonsai/DatabaseFiles/IFCmigrated_IFC4_v2.db"
LOG_FILE = "/home/red1/Documents/bonsai/consolelogs/extraction_IFC4_v2.log"
SPATIAL_FILTER = None  # Set by --sample mode (deprecated - use skip_offset instead)
SKIP_OFFSET = 0  # Number of elements to skip before starting extraction
MAX_ELEMENTS = None  # Maximum elements to extract (None = unlimited)
TIMEOUT_SECONDS = None  # Time limit for extraction (None = unlimited)
STOREY_FILTER = None  # Extract only elements from specific IfcBuildingStorey

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def log(message: str):
    """Log to console and file."""
    print(message)
    with open(LOG_FILE, 'a') as f:
        f.write(f"{message}\n")

def pack_vertices(vertices: List[Tuple[float, float, float]]) -> bytes:
    """Pack list of (x,y,z) tuples into binary BLOB."""
    return struct.pack(f'<{len(vertices)*3}f', *[coord for v in vertices for coord in v])

def pack_faces(faces: List[Tuple[int, int, int]]) -> bytes:
    """Pack list of (i1,i2,i3) tuples into binary BLOB."""
    return struct.pack(f'<{len(faces)*3}I', *[idx for f in faces for idx in f])

def compute_geometry_hash(vertices: List[Tuple[float, float, float]],
                          faces: List[Tuple[int, int, int]]) -> str:
    """Compute hash of geometry for instancing detection."""
    data = pack_vertices(vertices) + pack_faces(faces)
    return hashlib.sha256(data).hexdigest()[:16]

def get_discipline_from_path(filepath: str) -> str:
    """Extract discipline from IFC filename."""
    filename = Path(filepath).stem
    for key, value in DISCIPLINE_MAP.items():
        if key in filename:
            return value
    return "UNKNOWN"

def get_bbox(vertices: List[Tuple[float, float, float]]) -> Tuple[float, ...]:
    """Calculate bounding box from vertices."""
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    zs = [v[2] for v in vertices]
    return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))

def rgba_to_string(rgba: Tuple[float, float, float, float]) -> str:
    """Convert RGBA tuple to string."""
    return f"{rgba[0]:.3f},{rgba[1]:.3f},{rgba[2]:.3f},{rgba[3]:.3f}"

# ============================================================================
# DATABASE SCHEMA CREATION
# ============================================================================

def create_enhanced_schema(conn: sqlite3.Connection):
    """Create enhanced database schema with metadata tables."""
    cursor = conn.cursor()

    log("\n" + "="*80)
    log("Creating Enhanced Database Schema")
    log("="*80)

    # Core metadata table (enhanced)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS elements_meta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guid TEXT UNIQUE NOT NULL,
            discipline TEXT NOT NULL,
            ifc_class TEXT NOT NULL,
            filepath TEXT,
            element_name TEXT,
            element_type TEXT,
            element_description TEXT,
            storey TEXT,
            material_name TEXT,
            material_rgba TEXT
        )
    """)

    # Geometry table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS element_geometry (
            guid TEXT PRIMARY KEY,
            vertices BLOB NOT NULL,
            faces BLOB NOT NULL,
            normals BLOB,
            vertex_count INTEGER NOT NULL,
            face_count INTEGER NOT NULL,
            geometry_hash TEXT NOT NULL,
            FOREIGN KEY (guid) REFERENCES elements_meta(guid)
        )
    """)

    # R-tree spatial index (millimeters)
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS elements_rtree USING rtree(
            id INTEGER PRIMARY KEY,
            min_x REAL, max_x REAL,
            min_y REAL, max_y REAL,
            min_z REAL, max_z REAL
        )
    """)

    # Transforms table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS element_transforms (
            guid TEXT PRIMARY KEY,
            center_x REAL NOT NULL,
            center_y REAL NOT NULL,
            center_z REAL NOT NULL,
            transform_source TEXT DEFAULT 'tessellation',
            FOREIGN KEY (guid) REFERENCES elements_meta(guid)
        )
    """)

    # Global offset table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS global_offset (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            offset_x REAL NOT NULL,
            offset_y REAL NOT NULL,
            offset_z REAL NOT NULL,
            unit TEXT DEFAULT 'METERS',
            notes TEXT
        )
    """)

    # Property sets table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS element_properties (
            guid TEXT NOT NULL,
            pset_name TEXT NOT NULL,
            property_name TEXT NOT NULL,
            property_value TEXT NOT NULL,
            property_type TEXT,
            PRIMARY KEY (guid, pset_name, property_name),
            FOREIGN KEY (guid) REFERENCES elements_meta(guid)
        )
    """)

    # Material assignments table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS material_assignments (
            guid TEXT PRIMARY KEY,
            material_name TEXT NOT NULL,
            material_rgba TEXT,
            material_category TEXT,
            FOREIGN KEY (guid) REFERENCES elements_meta(guid)
        )
    """)

    # Spatial structure table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS spatial_structure (
            guid TEXT PRIMARY KEY,
            building TEXT,
            storey TEXT,
            space TEXT,
            elevation REAL,
            FOREIGN KEY (guid) REFERENCES elements_meta(guid)
        )
    """)

    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_discipline ON elements_meta(discipline)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_ifc_class ON elements_meta(ifc_class)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_geometry_hash ON element_geometry(geometry_hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pset_name ON element_properties(pset_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_storey ON spatial_structure(storey)")

    conn.commit()
    log("✓ Enhanced schema created successfully")

# ============================================================================
# METADATA EXTRACTION
# ============================================================================

def extract_element_metadata(element, ifc_file) -> Dict[str, str]:
    """Extract Name, Type, Description from IFC element."""
    metadata = {
        'name': getattr(element, 'Name', '') or '',
        'description': getattr(element, 'Description', '') or '',
        'element_type': ''
    }

    # Get element type
    try:
        for rel in getattr(element, 'IsDefinedBy', []):
            if rel.is_a('IfcRelDefinesByType'):
                type_obj = rel.RelatingType
                metadata['element_type'] = getattr(type_obj, 'Name', '') or ''
                break
    except:
        pass

    return metadata

def extract_material(element, discipline: str, ifc_file) -> Dict[str, str]:
    """Extract material name and color from IFC element."""
    material_data = {
        'name': 'Default',
        'rgba': rgba_to_string(DISCIPLINE_COLORS.get(discipline, (0.7, 0.7, 0.7, 1.0))),
        'category': 'Unknown'
    }

    try:
        # Try to get material from associations
        for rel in getattr(element, 'HasAssociations', []):
            if rel.is_a('IfcRelAssociatesMaterial'):
                mat = rel.RelatingMaterial

                # Get material name
                if mat.is_a('IfcMaterial'):
                    material_data['name'] = mat.Name or 'Unnamed'
                elif mat.is_a('IfcMaterialLayerSetUsage'):
                    if hasattr(mat, 'ForLayerSet') and mat.ForLayerSet:
                        material_data['name'] = getattr(mat.ForLayerSet, 'LayerSetName', 'Unnamed') or 'Unnamed'
                elif mat.is_a('IfcMaterialLayerSet'):
                    material_data['name'] = getattr(mat, 'LayerSetName', 'Unnamed') or 'Unnamed'
                elif mat.is_a('IfcMaterialList'):
                    if mat.Materials:
                        material_data['name'] = mat.Materials[0].Name or 'Unnamed'

                break
    except Exception as e:
        # Fallback to discipline color
        pass

    return material_data

def extract_properties(element, ifc_file) -> List[Dict[str, str]]:
    """Extract all property sets from element."""
    props = []

    try:
        for rel in getattr(element, 'IsDefinedBy', []):
            if rel.is_a('IfcRelDefinesByProperties'):
                pset = rel.RelatingPropertyDefinition

                if pset.is_a('IfcPropertySet'):
                    pset_name = pset.Name or 'Unnamed'

                    for prop in getattr(pset, 'HasProperties', []):
                        if prop.is_a('IfcPropertySingleValue'):
                            try:
                                value = prop.NominalValue
                                if value:
                                    props.append({
                                        'pset_name': pset_name,
                                        'property_name': prop.Name or 'Unnamed',
                                        'property_value': str(value.wrappedValue) if hasattr(value, 'wrappedValue') else str(value),
                                        'property_type': value.is_a() if hasattr(value, 'is_a') else 'Unknown'
                                    })
                            except:
                                continue
    except:
        pass

    return props

def extract_spatial_location(element, ifc_file) -> Dict[str, Optional[str]]:
    """Extract building/storey/space hierarchy."""
    spatial = {
        'building': None,
        'storey': None,
        'space': None,
        'elevation': None
    }

    try:
        for rel in getattr(element, 'ContainedInStructure', []):
            container = rel.RelatingStructure

            if container.is_a('IfcBuildingStorey'):
                spatial['storey'] = container.Name or 'Unnamed'
                spatial['elevation'] = getattr(container, 'Elevation', None)

                # Get parent building
                for parent_rel in getattr(container, 'Decomposes', []):
                    parent = parent_rel.RelatingObject
                    if parent.is_a('IfcBuilding'):
                        spatial['building'] = parent.Name or 'Unnamed'
                        break
            elif container.is_a('IfcSpace'):
                spatial['space'] = container.Name or 'Unnamed'
    except:
        pass

    return spatial

# ============================================================================
# GEOMETRY EXTRACTION
# ============================================================================

def extract_from_ifc(ifc_path: str, discipline: str, conn: sqlite3.Connection) -> Tuple[int, int]:
    """Extract tessellation + metadata from single IFC file."""
    log(f"\n{'='*80}")
    log(f"Processing: {Path(ifc_path).name}")
    log(f"Discipline: {discipline}")
    log(f"{'='*80}")

    start_time = time.time()

    # Open IFC
    log(f"Opening IFC file...")
    ifc_file = ifcopenshell.open(ifc_path)
    schema = ifc_file.wrapped_data.schema_name()
    log(f"IFC Schema: {schema}")

    # Get ALL IfcProduct elements (no filtering!)
    elements = ifc_file.by_type("IfcProduct")
    log(f"Found {len(elements)} IfcProduct elements")

    # Setup geometry settings
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)

    cursor = conn.cursor()
    processed = 0
    skipped = 0
    no_geometry = 0
    element_index = 0  # Track position in element stream (for skip logic)

    # Excluded types (spatial containers, not physical elements)
    excluded_types = {
        'IfcSite', 'IfcBuilding', 'IfcBuildingStorey', 'IfcSpace',
        'IfcOpeningElement', 'IfcProject', 'IfcSpatialZone'
    }

    for i, element in enumerate(elements):
        try:
            guid = element.GlobalId
            ifc_class = element.is_a()

            # Skip spatial containers
            if ifc_class in excluded_types:
                no_geometry += 1
                continue

            # STOREY FILTERING: Check if element belongs to target storey
            if STOREY_FILTER:
                # Get element's storey
                element_storey = None
                for rel in getattr(element, 'ContainedInStructure', []):
                    if hasattr(rel, 'RelatingStructure'):
                        structure = rel.RelatingStructure
                        if structure.is_a("IfcBuildingStorey"):
                            element_storey = structure.Name or structure.LongName
                            break

                # Skip if not in target storey
                if element_storey != STOREY_FILTER:
                    skipped += 1
                    continue

            # Skip if already processed
            cursor.execute("SELECT guid FROM elements_meta WHERE guid = ?", (guid,))
            if cursor.fetchone():
                skipped += 1
                continue

            # Try to get geometry
            try:
                shape = ifcopenshell.geom.create_shape(settings, element)
            except:
                # Element has no geometry
                no_geometry += 1
                continue

            # Extract vertices
            verts_flat = shape.geometry.verts
            vertices = [(verts_flat[j], verts_flat[j+1], verts_flat[j+2])
                       for j in range(0, len(verts_flat), 3)]

            # Extract faces
            faces_flat = shape.geometry.faces
            faces = [(faces_flat[j], faces_flat[j+1], faces_flat[j+2])
                    for j in range(0, len(faces_flat), 3)]

            if not vertices or not faces:
                no_geometry += 1
                continue

            # Extract normals
            normals_flat = shape.geometry.normals if hasattr(shape.geometry, 'normals') else []
            normals = [(normals_flat[j], normals_flat[j+1], normals_flat[j+2])
                      for j in range(0, len(normals_flat), 3)] if normals_flat else []

            # Calculate bounding box
            bbox = get_bbox(vertices)
            center = (
                (bbox[0] + bbox[1]) / 2,
                (bbox[2] + bbox[3]) / 2,
                (bbox[4] + bbox[5]) / 2
            )

            # SKIP-BASED SAMPLING: Skip first N elements, then extract up to max
            element_index += 1

            # Check timeout (if set)
            if TIMEOUT_SECONDS and (time.time() - start_time) > TIMEOUT_SECONDS:
                log(f"  ⏱️ Timeout reached ({TIMEOUT_SECONDS}s), stopping extraction for {discipline}")
                break

            # Skip elements before skip_offset
            if SKIP_OFFSET > 0 and element_index <= SKIP_OFFSET:
                skipped += 1
                continue

            # Stop if we've reached max_elements limit
            if MAX_ELEMENTS and processed >= MAX_ELEMENTS:
                log(f"  ⚠️ Reached max_elements limit ({MAX_ELEMENTS}), stopping extraction for {discipline}")
                break

            # CRITICAL: Transform vertices to be relative to center
            # This ensures geometry can be instanced correctly with instance.location = center
            vertices = [(v[0] - center[0], v[1] - center[1], v[2] - center[2]) for v in vertices]

            # Extract metadata
            metadata = extract_element_metadata(element, ifc_file)
            material = extract_material(element, discipline, ifc_file)
            properties = extract_properties(element, ifc_file)
            spatial = extract_spatial_location(element, ifc_file)

            # Pack geometry
            vertices_blob = pack_vertices(vertices)
            faces_blob = pack_faces(faces)
            normals_blob = pack_vertices(normals) if normals else None
            geom_hash = compute_geometry_hash(vertices, faces)

            # Insert metadata
            cursor.execute("""
                INSERT OR IGNORE INTO elements_meta
                (guid, discipline, ifc_class, filepath, element_name, element_type,
                 element_description, storey, material_name, material_rgba)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (guid, discipline, ifc_class, ifc_path,
                  metadata['name'], metadata['element_type'], metadata['description'],
                  spatial['storey'], material['name'], material['rgba']))

            elem_id = cursor.lastrowid

            # Insert geometry
            cursor.execute("""
                INSERT OR REPLACE INTO element_geometry
                (guid, vertices, faces, normals, vertex_count, face_count, geometry_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (guid, vertices_blob, faces_blob, normals_blob,
                  len(vertices), len(faces), geom_hash))

            # Insert into R-tree (convert to mm)
            cursor.execute("""
                INSERT OR REPLACE INTO elements_rtree
                (id, min_x, max_x, min_y, max_y, min_z, max_z)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (elem_id,
                  bbox[0]*1000, bbox[1]*1000,
                  bbox[2]*1000, bbox[3]*1000,
                  bbox[4]*1000, bbox[5]*1000))

            # Insert transform
            cursor.execute("""
                INSERT OR REPLACE INTO element_transforms
                (guid, center_x, center_y, center_z, transform_source)
                VALUES (?, ?, ?, ?, 'tessellation')
            """, (guid, center[0], center[1], center[2]))

            # Insert material assignment
            cursor.execute("""
                INSERT OR REPLACE INTO material_assignments
                (guid, material_name, material_rgba, material_category)
                VALUES (?, ?, ?, ?)
            """, (guid, material['name'], material['rgba'], material['category']))

            # Insert spatial structure
            cursor.execute("""
                INSERT OR REPLACE INTO spatial_structure
                (guid, building, storey, space, elevation)
                VALUES (?, ?, ?, ?, ?)
            """, (guid, spatial['building'], spatial['storey'],
                  spatial['space'], spatial['elevation']))

            # Insert properties
            for prop in properties:
                cursor.execute("""
                    INSERT OR REPLACE INTO element_properties
                    (guid, pset_name, property_name, property_value, property_type)
                    VALUES (?, ?, ?, ?, ?)
                """, (guid, prop['pset_name'], prop['property_name'],
                      prop['property_value'], prop['property_type']))

            processed += 1

            if processed % 100 == 0:
                conn.commit()
                log(f"  Processed {processed} elements (skipped {no_geometry} without geometry)...")

        except Exception as e:
            log(f"  ⚠️  Error processing {element.GlobalId} ({element.is_a()}): {e}")
            skipped += 1
            continue

    conn.commit()
    elapsed = time.time() - start_time

    log(f"\n✓ Extraction complete for {discipline}:")
    log(f"  Processed: {processed} elements")
    log(f"  No geometry: {no_geometry} elements")
    log(f"  Errors: {skipped} elements")
    log(f"  Time: {elapsed:.2f}s ({elapsed/max(processed,1)*1000:.1f}ms per element)")

    return processed, skipped

# ============================================================================
# POST-PROCESSING
# ============================================================================

def calculate_global_offset(conn: sqlite3.Connection):
    """Calculate and store global offset from all elements."""
    cursor = conn.cursor()

    log("\n" + "="*80)
    log("Calculating Global Offset")
    log("="*80)

    # Get global bbox from R-tree (in millimeters)
    cursor.execute("""
        SELECT
            MIN(min_x) as gmin_x, MAX(max_x) as gmax_x,
            MIN(min_y) as gmin_y, MAX(max_y) as gmax_y,
            MIN(min_z) as gmin_z, MAX(max_z) as gmax_z
        FROM elements_rtree
    """)

    row = cursor.fetchone()

    if not row or not all(row):
        log("⚠️  No elements in R-tree, cannot calculate offset")
        return

    # Convert to meters
    gmin_x, gmax_x, gmin_y, gmax_y, gmin_z, gmax_z = [v/1000.0 for v in row]

    # Calculate center
    offset_x = (gmin_x + gmax_x) / 2
    offset_y = (gmin_y + gmax_y) / 2
    offset_z = gmin_z  # Use minimum Z (ground level)

    # Store in global_offset table
    cursor.execute("""
        INSERT OR REPLACE INTO global_offset (id, offset_x, offset_y, offset_z, unit, notes)
        VALUES (1, ?, ?, ?, 'METERS', 'Calculated from IFC4 tessellation bounding box')
    """, (offset_x, offset_y, offset_z))

    conn.commit()

    log(f"✓ Global offset calculated:")
    log(f"  Offset: ({offset_x:.2f}, {offset_y:.2f}, {offset_z:.2f}) meters")
    log(f"  Model extent: {gmax_x - gmin_x:.2f} × {gmax_y - gmin_y:.2f} × {gmax_z - gmin_z:.2f} meters")

def print_statistics(conn: sqlite3.Connection):
    """Print database statistics."""
    cursor = conn.cursor()

    log("\n" + "="*80)
    log("DATABASE STATISTICS")
    log("="*80)

    # Element counts by discipline
    cursor.execute("""
        SELECT discipline, COUNT(*) as count
        FROM elements_meta
        GROUP BY discipline
        ORDER BY discipline
    """)

    log("\nElements by discipline:")
    total_elements = 0
    for discipline, count in cursor.fetchall():
        log(f"  {discipline:6s}: {count:5,d} elements")
        total_elements += count
    log(f"  {'TOTAL':6s}: {total_elements:5,d} elements")

    # Geometry statistics
    cursor.execute("SELECT COUNT(*) FROM element_geometry")
    geom_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(DISTINCT geometry_hash) FROM element_geometry")
    unique_geoms = cursor.fetchone()[0]

    cursor.execute("SELECT SUM(LENGTH(vertices) + LENGTH(faces)) FROM element_geometry")
    total_size = cursor.fetchone()[0] or 0

    log(f"\nGeometry statistics:")
    log(f"  Total geometries: {geom_count:,}")
    log(f"  Unique geometries: {unique_geoms:,}")
    log(f"  Instances: {geom_count - unique_geoms:,} ({(geom_count-unique_geoms)/max(geom_count,1)*100:.1f}%)")
    log(f"  Geometry size: {total_size / 1024 / 1024:.2f} MB")

    # Material coverage
    cursor.execute("SELECT COUNT(*) FROM material_assignments")
    mat_count = cursor.fetchone()[0]
    log(f"\nMetadata coverage:")
    log(f"  Materials: {mat_count:,} ({mat_count/max(total_elements,1)*100:.1f}%)")

    # Property coverage
    cursor.execute("SELECT COUNT(DISTINCT guid) FROM element_properties")
    prop_count = cursor.fetchone()[0]
    log(f"  Properties: {prop_count:,} ({prop_count/max(total_elements,1)*100:.1f}%)")

    # Spatial coverage
    cursor.execute("SELECT COUNT(*) FROM spatial_structure WHERE storey IS NOT NULL")
    spatial_count = cursor.fetchone()[0]
    log(f"  Spatial: {spatial_count:,} ({spatial_count/max(total_elements,1)*100:.1f}%)")

    # Database size
    db_size = Path(DB_PATH).stat().st_size
    log(f"\nDatabase size: {db_size / 1024 / 1024:.2f} MB")
    log(f"Storage per element: {db_size / max(total_elements,1) / 1024:.2f} KB")

# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main extraction process."""
    parser = argparse.ArgumentParser(description='Extract IFC4 tessellation with metadata')
    parser.add_argument('--test', action='store_true', help='Test on small LPG file only')
    parser.add_argument('--sample', action='store_true', help='Extract sample using sample_config.json')
    parser.add_argument('--output', type=str, help='Output database path (overrides default)')
    args = parser.parse_args()

    # Override DB_PATH if --output specified
    global DB_PATH
    if args.output:
        DB_PATH = args.output

    # Clear log file
    Path(LOG_FILE).write_text("")

    log("="*80)
    log("ENHANCED TESSELLATION EXTRACTION - IFC4 with Full Metadata")
    log("="*80)
    log(f"\nDatabase: {DB_PATH}")
    log(f"Log: {LOG_FILE}")

    if args.test:
        log(f"\n⚠️  TEST MODE - Processing LPG file only")
        files_to_process = [TEST_FILE]
    elif args.sample:
        # Load sample config
        sample_config_path = Path.home() / "Documents" / "bonsai" / "Scripts" / "sample_config.json"
        if not sample_config_path.exists():
            log(f"❌ ERROR: sample_config.json not found at {sample_config_path}")
            log("   Create sample_config.json with extraction parameters")
            return 1

        import json
        with open(sample_config_path) as f:
            sample_config = json.load(f)

        sample_params = sample_config.get('sample_extraction', {})
        extraction_mode = sample_params.get('extraction_mode', 'skip')

        if extraction_mode == 'storey':
            log(f"\n⚠️  SAMPLE MODE - Storey-based extraction")
            storey_name = sample_params.get('storey_name')
            max_elements = sample_params.get('max_elements', 800)

            log(f"   Config: {sample_config_path}")
            log(f"   Storey: {storey_name}")
            log(f"   Max elements: {max_elements}")

            files_to_process = IFC4_FILES

            # Store sampling parameters globally
            global STOREY_FILTER, MAX_ELEMENTS
            STOREY_FILTER = storey_name
            MAX_ELEMENTS = max_elements

        else:  # skip mode
            log(f"\n⚠️  SAMPLE MODE - Skip-based progressive sampling")
            skip_offset = sample_params.get('skip_offset', 0)
            max_elements = sample_params.get('max_elements', 800)
            timeout_seconds = sample_params.get('timeout_seconds', 300)

            log(f"   Config: {sample_config_path}")
            log(f"   Skip offset: {skip_offset}")
            log(f"   Max elements: {max_elements}")
            log(f"   Timeout: {timeout_seconds}s ({timeout_seconds/60:.1f} minutes)")

            files_to_process = IFC4_FILES

            # Store sampling parameters globally
            global SKIP_OFFSET, TIMEOUT_SECONDS
            SKIP_OFFSET = skip_offset
            MAX_ELEMENTS = max_elements
            TIMEOUT_SECONDS = timeout_seconds
    else:
        log(f"IFC Files: {len(IFC4_FILES)}")
        files_to_process = IFC4_FILES

    overall_start = time.time()
    total_processed = 0
    total_skipped = 0

    # Connect to database
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")

    try:
        # Create enhanced schema
        create_enhanced_schema(conn)

        # Process each IFC file
        for ifc_path in files_to_process:
            if not Path(ifc_path).exists():
                log(f"\n⚠️  File not found: {ifc_path}")
                continue

            discipline = get_discipline_from_path(ifc_path)
            processed, skipped = extract_from_ifc(ifc_path, discipline, conn)
            total_processed += processed
            total_skipped += skipped

        # Calculate global offset
        calculate_global_offset(conn)

        # Print statistics
        print_statistics(conn)

        overall_elapsed = time.time() - overall_start

        log("\n" + "="*80)
        log("EXTRACTION COMPLETE!")
        log("="*80)
        log(f"\nTotal time: {overall_elapsed:.2f}s ({overall_elapsed/60:.1f} minutes)")
        log(f"Average: {overall_elapsed/max(total_processed,1)*1000:.1f}ms per element")
        log("\n✅ SUCCESS - IFCmigrated_IFC4_v2.db ready for use!")
        log(f"📊 Log saved to: {LOG_FILE}")

    except Exception as e:
        log(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        conn.close()

    return 0

if __name__ == "__main__":
    sys.exit(main())
