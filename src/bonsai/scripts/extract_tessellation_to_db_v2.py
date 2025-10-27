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
import json
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

# NO PER-FILE COORDINATE OFFSETS NEEDED!
# IFC files from the BIM coordinator are ALREADY COORDINATED
# All disciplines share the same local origin (verified by check_all_discipline_coords.py)
# - All element coords within ±0.15m of origin
# - Disciplines overlap correctly in 3D space
# IfcMapConversion is metadata only - DO NOT apply to geometry!
# Reference: COORDINATE_SYSTEM_DEFINITIVE_GUIDE.md

DB_PATH = "/home/red1/Documents/bonsai/DatabaseFiles/IFCmigrated_IFC4_v2.db"
LOG_FILE = "/home/red1/Documents/bonsai/consolelogs/extraction_IFC4_v2.log"

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

    # Per-file coordinate offsets (for multi-discipline alignment)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS file_offsets (
            filepath TEXT PRIMARY KEY,
            discipline TEXT NOT NULL,
            offset_x REAL NOT NULL,
            offset_y REAL NOT NULL,
            offset_z REAL NOT NULL,
            reference_discipline TEXT DEFAULT 'ARC',
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

def extract_from_ifc(ifc_path: str, discipline: str, conn: sqlite3.Connection, max_elements: int = None, spatial_filter: dict = None) -> Tuple[int, int]:
    """Extract tessellation + metadata from single IFC file."""
    log(f"\n{'='*80}")
    log(f"Processing: {Path(ifc_path).name}")
    log(f"Discipline: {discipline}")
    if max_elements:
        log(f"⚠️  LIMITED MODE: Extracting up to {max_elements} elements only")
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

            # Calculate bounding box from IFC world coordinates (in METERS - GPS scale)
            # IfcOpenShell with USE_WORLD_COORDS=True returns geometry in METERS, not millimeters!
            # Reference: merged_federated.ifc analysis showed X: -50448 to -50407m (GPS coordinates)
            bbox = get_bbox(vertices)
            center_m = (
                (bbox[0] + bbox[1]) / 2,  # X center in METERS
                (bbox[2] + bbox[3]) / 2,  # Y center in METERS
                (bbox[4] + bbox[5]) / 2   # Z center in METERS
            )

            # Store coordinates as-is in METERS (GPS scale)
            # Database will contain GPS-scale coordinates matching merged_federated.ifc ground truth
            # Expected values: X ~-50427m, Y ~34192m, Z ~3-29m
            center = center_m  # Use GPS coordinates as-is from IFC (in METERS)

            # Apply spatial filter if provided
            if spatial_filter:
                if not (spatial_filter['min_x'] <= center[0] <= spatial_filter['max_x'] and
                        spatial_filter['min_y'] <= center[1] <= spatial_filter['max_y'] and
                        spatial_filter['min_z'] <= center[2] <= spatial_filter['max_z']):
                    # Element outside spatial filter - skip it
                    continue

            # Transform vertices to element-local coordinates (standard template/instance pattern)
            # This allows mesh data to be shared between identical geometries (instancing)
            # Subtract the ALIGNED center (not project center) to ensure vertices are relative to aligned position
            vertices = [(v[0] - center[0], v[1] - center[1], v[2] - center[2]) for v in vertices]

            # Recalculate bbox based on aligned center + local vertex extents
            local_bbox = get_bbox(vertices)
            aligned_bbox = (
                center[0] + local_bbox[0],  # min_x
                center[0] + local_bbox[1],  # max_x
                center[1] + local_bbox[2],  # min_y
                center[1] + local_bbox[3],  # max_y
                center[2] + local_bbox[4],  # min_z
                center[2] + local_bbox[5]   # max_z
            )

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

            # Insert into R-tree (using GPS-aligned bbox in mm)
            # This ensures spatial queries work correctly across all aligned disciplines
            cursor.execute("""
                INSERT OR REPLACE INTO elements_rtree
                (id, min_x, max_x, min_y, max_y, min_z, max_z)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (elem_id,
                  aligned_bbox[0], aligned_bbox[1],
                  aligned_bbox[2], aligned_bbox[3],
                  aligned_bbox[4], aligned_bbox[5]))

            # Insert transform (using GPS-aligned center - in mm)
            # This center already includes the discipline alignment offset
            # At load time, only global_offset needs to be subtracted for viewport display
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

            # Check if we've reached the limit
            if max_elements and processed >= max_elements:
                log(f"  Reached limit of {max_elements} elements, stopping...")
                break

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

    # Database stores coordinates in METERS (GPS scale) - NO conversion needed!
    # IfcOpenShell with USE_WORLD_COORDS=True returns meters directly
    # Expected values: X ~-50427m, Y ~34192m, Z ~3-29m (GPS coordinates)
    gmin_x, gmax_x, gmin_y, gmax_y, gmin_z, gmax_z = row

    # Calculate GPS-scale offset to position building in viewport
    # This offset will bring the GPS coordinates (~-50km, ~34km) back near origin
    # Expected offset: X ~-50427m, Y ~34192m, Z ~3m
    # After offset, building appears near viewport origin (0, 0, 0)
    offset_x = (gmin_x + gmax_x) / 2  # Center X (GPS scale)
    offset_y = (gmin_y + gmax_y) / 2  # Center Y (GPS scale)
    offset_z = gmin_z  # Use ground level for Z

    # Store in global_offset table (GPS-scale offset in METERS)
    cursor.execute("""
        INSERT OR REPLACE INTO global_offset (id, offset_x, offset_y, offset_z, unit, notes)
        VALUES (1, ?, ?, ?, 'METERS', 'GPS-scale viewport offset - matches merged_federated.ifc ground truth')
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
    parser.add_argument('--light', action='store_true', help='Light test: extract ~30 elements from ALL disciplines')
    parser.add_argument('--mini', action='store_true', help='Mini test: extract ~10-15 elements from ALL disciplines (fastest)')
    parser.add_argument('--sample', action='store_true', help='Sample extraction: varied elements per discipline (~200 total) based on sample_config.json')
    args = parser.parse_args()

    # Determine database path based on mode
    global DB_PATH
    if args.mini or args.light or args.sample:
        DB_PATH = "/home/red1/Documents/bonsai/DatabaseFiles/sample_extracted.db"

    # Clear log file
    Path(LOG_FILE).write_text("")

    log("="*80)
    log("ENHANCED TESSELLATION EXTRACTION - IFC4 with Full Metadata")
    log("="*80)
    log(f"\nDatabase: {DB_PATH}")
    log(f"Log: {LOG_FILE}")

    # Determine mode
    max_elements_per_file = None
    discipline_limits = {}  # For --sample mode
    spatial_filter = None  # For spatial filtering

    if args.sample:
        # Load JSON config
        config_path = Path(__file__).parent / "sample_config.json"
        if not config_path.exists():
            log(f"❌ ERROR: sample_config.json not found at {config_path}")
            return

        with open(config_path, 'r') as f:
            config = json.load(f)

        sample_config = config['sample_extraction']
        log(f"\n⚠️  SAMPLE MODE - Custom extraction based on sample_config.json")
        log(f"   Total target: ~{sample_config['total_target']} elements")

        # Check if spatial filtering is enabled
        if 'spatial_filter' in sample_config:
            spatial_filter = sample_config['spatial_filter']
            log(f"   Spatial filter ENABLED:")
            log(f"     X: {spatial_filter['min_x']:.1f} to {spatial_filter['max_x']:.1f} meters")
            log(f"     Y: {spatial_filter['min_y']:.1f} to {spatial_filter['max_y']:.1f} meters")
            log(f"     Z: {spatial_filter['min_z']:.1f} to {spatial_filter['max_z']:.1f} meters")
            log(f"     Note: {spatial_filter.get('note', 'N/A')}")

        log(f"   Per-discipline settings:")
        for disc, disc_config in sample_config['disciplines'].items():
            max_elem = disc_config.get('max_elements')
            discipline_limits[disc] = max_elem
            if max_elem is None:
                log(f"     {disc:6s}: ALL elements in region - {disc_config.get('note', 'N/A')}")
            else:
                log(f"     {disc:6s}: {max_elem:3d} elements max - {disc_config.get('rationale', 'N/A')}")

        files_to_process = IFC4_FILES

    elif args.mini:
        log(f"\n⚠️  MINI MODE - Extracting ~10-15 elements from ALL 8 disciplines")
        log(f"   Purpose: Ultra-fast test to verify alignment and fit in one common space")
        log(f"   Validation: 1) Alignment to origin like ORIGINAL_IFC.png (few meters away, not at origin)")
        log(f"              2) All disciplines placed correctly with proper dimensions and fit")
        files_to_process = IFC4_FILES
        max_elements_per_file = 12  # ~12 elements * 8 disciplines = ~96 total
    elif args.light:
        log(f"\n⚠️  LIGHT MODE - Extracting ~30 elements from ALL 8 disciplines")
        log(f"   Purpose: Fast validation test with all disciplines in common 3D space")
        files_to_process = IFC4_FILES
        max_elements_per_file = 30
    elif args.test:
        log(f"\n⚠️  TEST MODE - Processing LPG file only")
        files_to_process = [TEST_FILE]
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

            # Determine max_elements for this discipline
            if discipline_limits:
                # Sample mode - use discipline-specific limit
                discipline_max = discipline_limits.get(discipline, max_elements_per_file)
            else:
                # Other modes - use uniform limit
                discipline_max = max_elements_per_file

            processed, skipped = extract_from_ifc(ifc_path, discipline, conn, max_elements=discipline_max, spatial_filter=spatial_filter)
            total_processed += processed
            total_skipped += skipped

            # Record that NO offset was applied (files already coordinated)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO file_offsets
                (filepath, discipline, offset_x, offset_y, offset_z, reference_discipline, notes)
                VALUES (?, ?, ?, ?, ?, 'NONE', 'IFC files already coordinated by BIM coordinator - no per-file offsets applied')
            """, (ifc_path, discipline, 0.0, 0.0, 0.0))
            conn.commit()

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
