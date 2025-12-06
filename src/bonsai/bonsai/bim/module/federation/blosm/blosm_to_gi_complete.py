#!/usr/bin/env python3
"""
Complete BLOSM to GI Database Converter
========================================
Converts any BLOSM blend file to GI federation database in one step.

Usage:
    ~/blender-4.5.0/blender --background YOUR_BLOSM.blend \
        --python blosm_to_gi_complete.py -- \
        --output OUTPUT_NAME \
        [--water-only] [--no-buildings] [--no-roads]

Examples:
    # Convert everything
    blender --background klang.blend --python blosm_to_gi_complete.py -- --output klang_full

    # Water only
    blender --background klang.blend --python blosm_to_gi_complete.py -- --output klang_river --water-only

    # No buildings
    blender --background klang.blend --python blosm_to_gi_complete.py -- --output klang_no_buildings --no-buildings
"""
import sys
import os
import sqlite3
import tempfile
from pathlib import Path
import argparse

# Parse arguments (after --)
argv = sys.argv
if "--" in argv:
    argv = argv[argv.index("--") + 1:]
else:
    argv = []

parser = argparse.ArgumentParser(description="Convert BLOSM blend to GI database")
parser.add_argument("--output", required=True, help="Output database name (without .db extension)")
parser.add_argument("--water-only", action="store_true", help="Export water/rivers only")
parser.add_argument("--no-buildings", action="store_true", help="Skip buildings")
parser.add_argument("--no-roads", action="store_true", help="Skip roads")
parser.add_argument("--no-terrain", action="store_true", help="Skip terrain")
args = parser.parse_args(argv)

# Output paths
WORK_DIR = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER")
OUTPUT_IFC = WORK_DIR / "output" / f"{args.output}.ifc"
OUTPUT_DB = WORK_DIR / f"{args.output}.db"

# Filter configuration
FILTERS = {
    'water': not args.water_only,  # If water-only, only water passes
    'building': not args.water_only and not args.no_buildings,
    'road': not args.water_only and not args.no_roads,
    'terrain': not args.water_only and not args.no_terrain
}

print("\n" + "="*70)
print("BLOSM TO GI DATABASE - COMPLETE CONVERTER")
print("="*70)
print(f"\nOutput database: {OUTPUT_DB}")
print(f"Intermediate IFC: {OUTPUT_IFC}")
print(f"\nFilters:")
for elem_type, enabled in FILTERS.items():
    status = "✓ ENABLED" if enabled else "✗ DISABLED"
    print(f"  {elem_type.upper():12s}: {status}")

# ============================================================================
# STAGE 1: BLEND → IFC
# ============================================================================

import bpy
import bmesh

# Add ifcopenshell
wheel_dir = Path.home() / ".config/blender/4.5/extensions/blender_org/bonsai/wheels"
if wheel_dir.exists():
    sys.path.insert(0, str(wheel_dir))

try:
    import ifcopenshell
    import ifcopenshell.api
except ImportError as e:
    print(f"\n✗ ERROR: Failed to import ifcopenshell: {e}")
    sys.exit(1)

# Classification
CLASSIFICATION = {
    'water': ('IfcGeographicElement', 'USERDEFINED', 'WATER'),
    'building': ('IfcBuildingElementProxy', 'USERDEFINED', 'BUILDING'),
    'road': ('IfcBuildingElementProxy', 'USERDEFINED', 'ROAD'),
    'terrain': ('IfcGeographicElement', 'TERRAIN', 'TERRAIN'),
}

def classify_object(name):
    name_lower = name.lower()
    for key in CLASSIFICATION:
        if key in name_lower:
            return key
    return None

def get_scene_offset():
    """Calculate offset to center scene near origin"""
    all_locations = []
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and obj.data.vertices:
            matrix = obj.matrix_world
            xs = [matrix @ v.co for v in obj.data.vertices]
            avg_x = sum(v.x for v in xs) / len(xs)
            avg_y = sum(v.y for v in xs) / len(xs)
            avg_z = sum(v.z for v in xs) / len(xs)
            all_locations.append((avg_x, avg_y, avg_z))
    
    if all_locations:
        avg_x = sum(loc[0] for loc in all_locations) / len(all_locations)
        avg_y = sum(loc[1] for loc in all_locations) / len(all_locations)
        avg_z = sum(loc[2] for loc in all_locations) / len(all_locations)
        
        if abs(avg_x) > 1000 or abs(avg_y) > 1000:
            print(f"  Applying offset: ({-avg_x:.2f}, {-avg_y:.2f}, {-avg_z:.2f})")
            return (-avg_x, -avg_y, -avg_z)
    
    return (0, 0, 0)

def extract_mesh_geometry(obj, offset):
    """Extract and triangulate mesh geometry"""
    mesh_data = obj.data if 'water' in obj.name.lower() else obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    
    bm = bmesh.new()
    bm.from_mesh(mesh_data)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    
    matrix = obj.matrix_world
    vertices = []
    for v in bm.verts:
        world_co = matrix @ v.co
        vertices.append((
            world_co.x + offset[0],
            world_co.y + offset[1],
            world_co.z + offset[2]
        ))
    
    faces = [[v.index for v in f.verts] for f in bm.faces]
    bm.free()
    
    return vertices, faces

print("\n" + "="*70)
print("STAGE 1: BLEND → IFC")
print("="*70)

offset = get_scene_offset()

# Create IFC
ifc = ifcopenshell.api.run("project.create_file", version="IFC4")
project = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcProject", name="BLOSM Import")
ifcopenshell.api.run("unit.assign_unit", ifc, length={"is_metric": True, "raw": "METERS"})

model_context = ifcopenshell.api.run("context.add_context", ifc, context_type="Model")
body_context = ifcopenshell.api.run("context.add_context", ifc, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=model_context)

site = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcSite", name="BLOSM Site")
building = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcBuilding", name="Context")
storey = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcBuildingStorey", name="Ground")

ifcopenshell.api.run("aggregate.assign_object", ifc, products=[site], relating_object=project)
ifcopenshell.api.run("aggregate.assign_object", ifc, products=[building], relating_object=site)
ifcopenshell.api.run("aggregate.assign_object", ifc, products=[storey], relating_object=building)

stats = {'water': 0, 'building': 0, 'road': 0, 'terrain': 0, 'skipped': 0}

for obj in bpy.data.objects:
    if obj.type != 'MESH' or not obj.data.vertices or not obj.data.polygons:
        continue
    if obj.name in ['Camera', 'Light', 'Cube'] or obj.name.startswith('profile_'):
        continue
    
    category = classify_object(obj.name)
    if not category:
        stats['skipped'] += 1
        continue
    
    if not FILTERS[category]:
        print(f"  ⊘ Skipping {category}: {obj.name}")
        stats['skipped'] += 1
        continue
    
    ifc_class, predefined_type, object_type = CLASSIFICATION[category]
    
    try:
        vertices, faces = extract_mesh_geometry(obj, offset)
        if not vertices or not faces:
            stats['skipped'] += 1
            continue
        
        # Add thickness to water
        if category == 'water':
            original_vert_count = len(vertices)
            bottom_verts = [(v[0], v[1], v[2] - 0.05) for v in vertices]
            vertices.extend(bottom_verts)
            
            new_faces = []
            for face in faces:
                bottom_face = [i + original_vert_count for i in reversed(face)]
                new_faces.append(bottom_face)
                for i in range(len(face)):
                    next_i = (i + 1) % len(face)
                    t1, t2 = face[i], face[next_i]
                    b1, b2 = t1 + original_vert_count, t2 + original_vert_count
                    new_faces.append([t1, t2, b2])
                    new_faces.append([t1, b2, b1])
            faces.extend(new_faces)
        
        element = ifcopenshell.api.run("root.create_entity", ifc, ifc_class=ifc_class, name=obj.name)
        if hasattr(element, 'PredefinedType'):
            element.PredefinedType = predefined_type
        if hasattr(element, 'ObjectType'):
            element.ObjectType = object_type
        
        representation = ifcopenshell.api.run("geometry.add_mesh_representation", ifc, context=body_context, vertices=[vertices], faces=[faces])
        ifcopenshell.api.run("geometry.assign_representation", ifc, product=element, representation=representation)
        
        container = site if category in ['water', 'terrain'] else storey
        ifcopenshell.api.run("spatial.assign_container", ifc, products=[element], relating_structure=container)
        
        stats[category] += 1
        print(f"  ✓ {category.upper()}: {obj.name} ({len(vertices)} verts, {len(faces)} faces)")
    
    except Exception as e:
        print(f"  ✗ ERROR: {obj.name}: {e}")
        stats['skipped'] += 1

OUTPUT_IFC.parent.mkdir(parents=True, exist_ok=True)
ifc.write(str(OUTPUT_IFC))

print(f"\n✓ IFC saved: {OUTPUT_IFC}")
print(f"  Water: {stats['water']}, Buildings: {stats['building']}, Roads: {stats['road']}, Terrain: {stats['terrain']}, Skipped: {stats['skipped']}")

# ============================================================================
# STAGE 2: IFC → GI DATABASE
# ============================================================================

print("\n" + "="*70)
print("STAGE 2: IFC → GI DATABASE")
print("="*70)

import numpy as np
import hashlib

try:
    import ifcopenshell.geom
except ImportError:
    print("✗ ERROR: ifcopenshell.geom not available")
    sys.exit(1)

def create_database_schema(cursor):
    cursor.execute("CREATE TABLE IF NOT EXISTS schema_info (key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute("INSERT OR REPLACE INTO schema_info VALUES ('version', '1.0')")
    cursor.execute("INSERT OR REPLACE INTO schema_info VALUES ('source', 'BLOSM OSM Import')")
    
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
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS element_transforms (
            guid TEXT PRIMARY KEY,
            center_x REAL, center_y REAL, center_z REAL,
            bbox_min_x REAL, bbox_min_y REAL, bbox_min_z REAL,
            bbox_max_x REAL, bbox_max_y REAL, bbox_max_z REAL,
            rotation_matrix TEXT,
            FOREIGN KEY (guid) REFERENCES elements_meta(guid)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS site_context (
            discipline TEXT PRIMARY KEY,
            site_offset_x REAL, site_offset_y REAL, site_offset_z REAL,
            ref_latitude REAL, ref_longitude REAL, ref_elevation REAL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS global_offset (
            offset_x REAL NOT NULL, offset_y REAL NOT NULL, offset_z REAL NOT NULL,
            extent_x REAL, extent_y REAL, extent_z REAL
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO global_offset (offset_x, offset_y, offset_z) VALUES (0.0, 0.0, 0.0)")
    
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS elements_rtree USING rtree(
            id, minX, maxX, minY, maxY, minZ, maxZ
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS base_geometries (
            geometry_hash TEXT PRIMARY KEY,
            vertices BLOB NOT NULL, faces BLOB NOT NULL, normals BLOB,
            vertex_count INTEGER NOT NULL, face_count INTEGER NOT NULL
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS element_instances (
            guid TEXT PRIMARY KEY,
            geometry_hash TEXT NOT NULL,
            FOREIGN KEY (geometry_hash) REFERENCES base_geometries(geometry_hash)
        )
    """)
    
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_guid ON elements_meta(guid)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_class ON elements_meta(ifc_class)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_discipline ON elements_meta(discipline)")

if OUTPUT_DB.exists():
    OUTPUT_DB.unlink()

conn = sqlite3.connect(str(OUTPUT_DB))
cursor = conn.cursor()
create_database_schema(cursor)

ifc_file = ifcopenshell.open(str(OUTPUT_IFC))
settings = ifcopenshell.geom.settings()
settings.set(settings.USE_WORLD_COORDS, True)

GEOMETRIC_CLASSES = {"IfcGeographicElement", "IfcBuildingElementProxy", "IfcWall", "IfcBeam", "IfcColumn", "IfcSlab", "IfcDoor", "IfcWindow", "IfcRoof"}

elements = [elem for elem in ifc_file.by_type("IfcProduct") if elem.is_a() in GEOMETRIC_CLASSES]
print(f"\nFound {len(elements)} geometric elements")

inserted_count = 0

for elem in elements:
    try:
        shape = ifcopenshell.geom.create_shape(settings, elem)
        
        verts = shape.geometry.verts
        faces_list = shape.geometry.faces
        if not verts or not faces_list:
            continue
        
        vertices = np.array(verts, dtype=np.float32).reshape(-1, 3)
        faces = np.array(faces_list, dtype=np.int32).reshape(-1, 3)
        
        geom_data = vertices.tobytes() + faces.tobytes()
        geometry_hash = hashlib.sha256(geom_data).hexdigest()[:16]
        
        coords = vertices
        bbox = {
            'min_x': float(np.min(coords[:, 0])), 'max_x': float(np.max(coords[:, 0])),
            'min_y': float(np.min(coords[:, 1])), 'max_y': float(np.max(coords[:, 1])),
            'min_z': float(np.min(coords[:, 2])), 'max_z': float(np.max(coords[:, 2])),
        }
        center = {
            'x': (bbox['min_x'] + bbox['max_x']) / 2,
            'y': (bbox['min_y'] + bbox['max_y']) / 2,
            'z': (bbox['min_z'] + bbox['max_z']) / 2,
        }
        
        discipline = "GEO" if elem.is_a("IfcGeographicElement") else "ARC"
        
        cursor.execute("""
            INSERT INTO elements_meta (guid, discipline, ifc_class, name, object_type, predefined_type)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (elem.GlobalId, discipline, elem.is_a(), elem.Name, getattr(elem, 'ObjectType', None), getattr(elem, 'PredefinedType', None)))
        
        elem_id = cursor.lastrowid
        
        cursor.execute("""
            INSERT INTO element_transforms (guid, center_x, center_y, center_z,
                bbox_min_x, bbox_min_y, bbox_min_z, bbox_max_x, bbox_max_y, bbox_max_z)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (elem.GlobalId, center['x'], center['y'], center['z'],
              bbox['min_x'], bbox['min_y'], bbox['min_z'], bbox['max_x'], bbox['max_y'], bbox['max_z']))
        
        cursor.execute("""
            INSERT INTO elements_rtree (id, minX, maxX, minY, maxY, minZ, maxZ)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (elem_id, bbox['min_x'], bbox['max_x'], bbox['min_y'], bbox['max_y'], bbox['min_z'], bbox['max_z']))
        
        cursor.execute("SELECT geometry_hash FROM base_geometries WHERE geometry_hash = ?", (geometry_hash,))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO base_geometries (geometry_hash, vertices, faces, normals, vertex_count, face_count)
                VALUES (?, ?, ?, NULL, ?, ?)
            """, (geometry_hash, vertices.tobytes(), faces.tobytes(), len(vertices), len(faces)))
        
        cursor.execute("""
            INSERT INTO element_instances (guid, geometry_hash)
            VALUES (?, ?)
        """, (elem.GlobalId, geometry_hash))
        
        inserted_count += 1
        print(f"  ✓ {elem.is_a()}: {elem.Name}")
    
    except Exception as e:
        print(f"  ✗ {elem.Name}: {e}")

conn.commit()
conn.close()

db_size = OUTPUT_DB.stat().st_size / 1024

print("\n" + "="*70)
print("✅ CONVERSION COMPLETE")
print("="*70)
print(f"\nDatabase: {OUTPUT_DB}")
print(f"Elements: {inserted_count}")
print(f"Size: {db_size:.1f} KB")
print("\nReady to load in Bonsai Federation!")
print("="*70)
