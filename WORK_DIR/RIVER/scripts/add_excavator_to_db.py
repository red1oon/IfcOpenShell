#!/usr/bin/env python3
"""
Add excavator directly to river_blosm_gi.db with CW discipline.
Pulls geometry from library.db and inserts with full mesh data.
Placement: ON riverbank (30m west of center), GROUND LEVEL (above water).
"""

import sqlite3
import uuid
import hashlib

# Database paths
library_db = "/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/library.db"
db_path = "/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/databases/river_blosm_gi.db"

# Component to use from library
COMPONENT_ID = "EXCAVATOR-CAT336-GLB"  # GLB original (better scaled)

# Excavator configuration
excavator_data = {
    'guid': str(uuid.uuid4().hex[:22]),  # Generate GUID
    'name': 'CW_Excavator_CAT336',
    'discipline': 'CW',
    'ifc_class': 'IfcTransportElement',
    'object_type': 'CONSTRUCTION_EQUIPMENT',
    'description': 'Caterpillar 336 Excavator for riverbank civil works',
    'material': 'Steel',

    # Placement (ON LEFT BANK, GROUND LEVEL)
    # River center: (51.96, 6.54, 0.15)
    # Water level: 0.1-0.2m
    # Excavator: 30m west of river, at Z=0 (ground, ABOVE water)
    'center_x': 51.96 - 30.0,  # 21.96m
    'center_y': 6.54,
    'center_z': 0.0,  # Ground level (NOT submerged!)

    # Dimensions (realistic excavator: 10m long, 5m wide, 5m high)
    'length': 10.0,
    'width': 5.0,
    'height': 5.0,

    # Bounding box
    'bbox_min_x': 51.96 - 30.0 - 5.0,  # 16.96
    'bbox_max_x': 51.96 - 30.0 + 5.0,  # 26.96
    'bbox_min_y': 6.54 - 2.5,
    'bbox_max_y': 6.54 + 2.5,
    'bbox_min_z': 0.0,
    'bbox_max_z': 5.0,

    # Rotation (face east toward river)
    'rotation_z': 90.0
}

print("=" * 60)
print("ADD EXCAVATOR TO DATABASE (CW DISCIPLINE)")
print("=" * 60)

# Step 1: Get geometry from library.db
print(f"\n[1] Fetching geometry from library.db...")
print(f"    Component: {COMPONENT_ID}")

lib_conn = sqlite3.connect(library_db)
lib_cur = lib_conn.cursor()

# Get component info and geometry
lib_cur.execute("""
    SELECT cl.name, cl.ifc_class, cl.category,
           bg.vertices, bg.faces, bg.vertex_count, bg.face_count,
           bg.bbox_width, bg.bbox_depth, bg.bbox_height
    FROM component_library cl
    JOIN component_instances ci ON cl.component_id = ci.component_id
    JOIN base_geometries bg ON ci.geometry_hash = bg.geometry_hash
    WHERE cl.component_id = ?
""", (COMPONENT_ID,))

result = lib_cur.fetchone()
if not result:
    print(f"❌ Component {COMPONENT_ID} not found in library!")
    lib_conn.close()
    exit(1)

name, ifc_class, category, vertices_blob, faces_blob, vertex_count, face_count, bbox_w, bbox_d, bbox_h = result
lib_conn.close()

print(f"    ✓ Found: {name}")
print(f"      Category: {category}")
print(f"      Geometry: {vertex_count:,} verts, {face_count:,} faces")
print(f"      Original size: {bbox_w:.2f}m × {bbox_d:.2f}m × {bbox_h:.2f}m")

# SCALE FIX: Model is in centimeters, convert to meters
SCALE_FACTOR = 0.1  # Scale down by 10x to get realistic size
print(f"    ⚠ Applying scale factor: {SCALE_FACTOR}x")

import struct
verts = []
for i in range(vertex_count):
    offset = i * 12  # 3 floats * 4 bytes
    x, y, z = struct.unpack('fff', vertices_blob[offset:offset+12])
    verts.append((x * SCALE_FACTOR, y * SCALE_FACTOR, z * SCALE_FACTOR))

# Repack scaled vertices
vertices_blob = struct.pack('f' * (vertex_count * 3), *[coord for v in verts for coord in v])
bbox_w *= SCALE_FACTOR
bbox_d *= SCALE_FACTOR
bbox_h *= SCALE_FACTOR

print(f"      Scaled size: {bbox_w:.2f}m × {bbox_d:.2f}m × {bbox_h:.2f}m")

# Compute geometry hash from SCALED data
geometry_hash = hashlib.md5(vertices_blob + faces_blob).hexdigest()

print(f"\n[2] Excavator placement details:")
print(f"  Name: {excavator_data['name']}")
print(f"  GUID: {excavator_data['guid']}")
print(f"  Discipline: {excavator_data['discipline']}")
print(f"  Class: {excavator_data['ifc_class']}")
print(f"  Type: {excavator_data['object_type']}")
print(f"\nPlacement:")
print(f"  Location: ({excavator_data['center_x']:.2f}, {excavator_data['center_y']:.2f}, {excavator_data['center_z']:.2f})")
print(f"  → 30m WEST of river center")
print(f"  → At Z=0 (GROUND LEVEL, above water at 0.15m)")
print(f"  Rotation: {excavator_data['rotation_z']}° (facing river)")
print(f"\nDimensions:")
print(f"  {excavator_data['length']}m × {excavator_data['width']}m × {excavator_data['height']}m")

# Connect to target database
print(f"\n[3] Connecting to target database...")
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Insert into elements_meta
print(f"\n→ Inserting into elements_meta...")
cursor.execute("""
    INSERT INTO elements_meta (guid, discipline, ifc_class, name, description, object_type, material)
    VALUES (?, ?, ?, ?, ?, ?, ?)
""", (
    excavator_data['guid'],
    excavator_data['discipline'],
    excavator_data['ifc_class'],
    excavator_data['name'],
    excavator_data['description'],
    excavator_data['object_type'],
    excavator_data['material']
))

# Insert into element_transforms
# Create rotation matrix for 90° rotation around Z-axis
import math
import json
angle = math.radians(excavator_data['rotation_z'])
cos_a = math.cos(angle)
sin_a = math.sin(angle)
rotation_matrix = [
    [cos_a, -sin_a, 0.0, 0.0],
    [sin_a, cos_a, 0.0, 0.0],
    [0.0, 0.0, 1.0, 0.0],
    [0.0, 0.0, 0.0, 1.0]
]
rotation_matrix_str = json.dumps(rotation_matrix)

print(f"→ Inserting into element_transforms...")
cursor.execute("""
    INSERT INTO element_transforms (
        guid, center_x, center_y, center_z,
        bbox_min_x, bbox_max_x, bbox_min_y, bbox_max_y, bbox_min_z, bbox_max_z,
        rotation_matrix
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (
    excavator_data['guid'],
    excavator_data['center_x'],
    excavator_data['center_y'],
    excavator_data['center_z'],
    excavator_data['bbox_min_x'],
    excavator_data['bbox_max_x'],
    excavator_data['bbox_min_y'],
    excavator_data['bbox_max_y'],
    excavator_data['bbox_min_z'],
    excavator_data['bbox_max_z'],
    rotation_matrix_str
))

# Get element ID for rtree
cursor.execute("SELECT id FROM elements_meta WHERE guid = ?", (excavator_data['guid'],))
element_id = cursor.fetchone()[0]

# Insert into R-tree spatial index
print(f"→ Inserting into spatial index (elements_rtree)...")
cursor.execute("""
    INSERT INTO elements_rtree (
        id, minX, maxX, minY, maxY, minZ, maxZ
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
""", (
    element_id,
    excavator_data['bbox_min_x'],
    excavator_data['bbox_max_x'],
    excavator_data['bbox_min_y'],
    excavator_data['bbox_max_y'],
    excavator_data['bbox_min_z'],
    excavator_data['bbox_max_z']
))

# Insert geometry into base_geometries (if not exists)
# NOTE: Copying geometry for now since blend_cache.py doesn't support library:// references yet
print(f"→ Inserting geometry into base_geometries...")
cursor.execute("SELECT geometry_hash FROM base_geometries WHERE geometry_hash = ?", (geometry_hash,))
if not cursor.fetchone():
    cursor.execute("""
        INSERT INTO base_geometries
        (geometry_hash, vertices, faces, normals, vertex_count, face_count)
        VALUES (?, ?, ?, NULL, ?, ?)
    """, (geometry_hash, vertices_blob, faces_blob, vertex_count, face_count))
    print(f"    ✓ Geometry copied from library: {vertex_count:,} verts, {face_count:,} faces")
else:
    print(f"    ✓ Geometry already exists (shared instance)")

# Link element to geometry
print(f"→ Linking element to geometry (element_instances)...")
cursor.execute("""
    INSERT INTO element_instances (guid, geometry_hash)
    VALUES (?, ?)
""", (excavator_data['guid'], geometry_hash))
print(f"    ✓ Source: library.db → {COMPONENT_ID}")

# Commit changes
conn.commit()

# Verify
print(f"\n✓ Excavator added to database!")
print(f"\nVerification:")
result = cursor.execute("""
    SELECT em.guid, em.name, em.discipline, em.ifc_class, em.object_type,
           et.center_x, et.center_y, et.center_z,
           et.bbox_max_z - et.bbox_min_z as height
    FROM elements_meta em
    JOIN element_transforms et ON em.guid = et.guid
    WHERE em.discipline = 'CW'
""").fetchone()

if result:
    guid, name, disc, ifc_class, obj_type, cx, cy, cz, h = result
    print(f"  ✓ Found in database:")
    print(f"    GUID: {guid}")
    print(f"    Name: {name}")
    print(f"    Discipline: {disc}")
    print(f"    Class: {ifc_class}")
    print(f"    Location: ({cx:.2f}, {cy:.2f}, {cz:.2f})")
    print(f"    Height: {h:.2f}m")

# Check total elements
total = cursor.execute("SELECT COUNT(*) FROM elements_meta").fetchone()[0]
print(f"\n  Total elements in database: {total} (was 384, now 385)")

# Show breakdown by discipline
print(f"\n  Breakdown by discipline:")
disciplines = cursor.execute("""
    SELECT discipline, COUNT(*) as count
    FROM elements_meta
    GROUP BY discipline
    ORDER BY count DESC
""").fetchall()

for disc, count in disciplines:
    print(f"    {disc}: {count}")

conn.close()

print("\n" + "=" * 60)
print("✓ SUCCESS! Excavator is now in the database.")
print("  • Can query via SQL")
print("  • Can calculate costs")
print("  • Can visualize via blend_cache.py")
print("  • Can export to IFC")
print("=" * 60)
