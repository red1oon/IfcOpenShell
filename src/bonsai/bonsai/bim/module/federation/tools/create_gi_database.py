#!/usr/bin/env python3
"""
Geometry Instancing Database Creator
====================================

Creates a GI-enabled federation database with the correct schema:
- base_geometries: Deduplicated meshes (position-independent hashing)
- element_instances: Elements referencing base geometries
- element_transforms: Element world positions

Key Innovation:
- Vertices stored in WORLD SPACE (loader compatibility)
- Hashes computed on LOCAL SPACE (geometry deduplication)
- Result: ~7× memory reduction vs position-dependent hashing
"""

import sqlite3
import struct
import hashlib
from pathlib import Path

# Read from production DB, write GI-enabled version
SOURCE_DB = "/home/red1/Documents/bonsai/DatabaseFiles/enhanced_federation.db"
OUTPUT_DB = "/home/red1/Projects/IfcOpenShell/WORK_DIR/databases/enhanced_federation_GI.db"


def compute_local_hash(vertices_world, center):
    """
    Compute position-independent geometry hash.

    Transforms world-space vertices to local space for hashing,
    but original world vertices are stored unchanged.
    """
    # Transform to local space (relative to center)
    local_verts = [
        (v[0] - center[0], v[1] - center[1], v[2] - center[2])
        for v in vertices_world
    ]

    # Pack and hash local vertices
    packed = struct.pack(f'<{len(local_verts)*3}f', *[c for v in local_verts for c in v])
    return hashlib.sha256(packed).hexdigest()[:16]  # 16-char hash


def unpack_vertices(blob):
    """Unpack vertex BLOB to list of (x,y,z) tuples"""
    floats = struct.unpack(f'<{len(blob)//4}f', blob)
    return [(floats[i], floats[i+1], floats[i+2]) for i in range(0, len(floats), 3)]


def pack_vertices(vertices):
    """Pack list of (x,y,z) tuples to BLOB"""
    return struct.pack(f'<{len(vertices)*3}f', *[c for v in vertices for c in v])


def main():
    print("🚀 Creating GI-Enabled Federation Database")
    print("=" * 70)

    # Connect to source DB
    src_conn = sqlite3.connect(SOURCE_DB)
    src_cursor = src_conn.cursor()

    # Create output DB
    Path(OUTPUT_DB).unlink(missing_ok=True)
    dst_conn = sqlite3.connect(OUTPUT_DB)
    dst_cursor = dst_conn.cursor()

    # Create core GI schema (manual to avoid R-tree conflicts)
    dst_cursor.executescript("""
        CREATE TABLE base_geometries (
            geometry_hash TEXT PRIMARY KEY,
            vertices BLOB NOT NULL,
            faces BLOB NOT NULL,
            normals BLOB,
            vertex_count INTEGER NOT NULL,
            face_count INTEGER NOT NULL
        );

        CREATE TABLE element_instances (
            guid TEXT PRIMARY KEY,
            geometry_hash TEXT NOT NULL,
            FOREIGN KEY (geometry_hash) REFERENCES base_geometries(geometry_hash)
        );
    """)

    # Copy remaining schema from source (everything except geometry tables)
    for table_name in ['elements_meta', 'element_transforms', 'spatial_structure',
                       'element_properties', 'material_assignments', 'global_offset',
                       'clash_status', 'clash_groups', 'clash_group_members', 'clash_history',
                       'design_effort_estimates', 'discipline_rates',
                       'resolution_options', 'resolution_history',
                       'extraction_metadata', 'schema_version', 'simple_qto',
                       'construction_schedule']:
        src_cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        row = src_cursor.fetchone()
        if row and row[0]:
            dst_cursor.execute(row[0])

    # Create R-tree spatial index (CRITICAL: camelCase to match production schema!)
    dst_cursor.execute("""
        CREATE VIRTUAL TABLE elements_rtree USING rtree(
            id,
            minX, maxX,
            minY, maxY,
            minZ, maxZ
        )
    """)

    # Copy all tables EXCEPT base_geometries, element_instances, and elements_rtree (we'll rebuild these)
    tables_to_copy = [
        'elements_meta', 'element_transforms',
        'spatial_structure', 'element_properties', 'global_offset',
        'material_assignments', 'clash_status', 'clash_groups',
        'clash_group_members', 'clash_history',
        'design_effort_estimates', 'discipline_rates',
        'resolution_options', 'resolution_history',
        'extraction_metadata', 'schema_version',
        'simple_qto',  # 5D QTO table
        'construction_schedule'  # 4D schedule
    ]

    print("\n📋 Copying non-geometry tables...")
    for table in tables_to_copy:
        try:
            src_cursor.execute(f"SELECT * FROM {table}")
            rows = src_cursor.fetchall()
            if rows:
                placeholders = ','.join(['?' for _ in range(len(rows[0]))])
                dst_cursor.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)
                print(f"  ✓ {table}: {len(rows):,} rows")
        except sqlite3.OperationalError:
            print(f"  ⊘ {table}: Not found (skipping)")

    dst_conn.commit()

    # Copy R-tree spatial index data
    print("\n🗺️  Copying spatial index...")
    src_cursor.execute("SELECT * FROM elements_rtree")
    rtree_data = src_cursor.fetchall()
    if rtree_data:
        dst_cursor.executemany(
            "INSERT INTO elements_rtree VALUES (?, ?, ?, ?, ?, ?, ?)",
            rtree_data
        )
        print(f"  ✓ elements_rtree: {len(rtree_data):,} spatial entries")
    dst_conn.commit()

    # Rebuild base_geometries with GI hashing
    print("\n🔨 Rebuilding base_geometries with position-independent hashing...")

    src_cursor.execute("""
        SELECT ei.guid, bg.vertices, bg.faces, bg.normals,
               et.center_x, et.center_y, et.center_z
        FROM element_instances ei
        JOIN base_geometries bg ON ei.geometry_hash = bg.geometry_hash
        JOIN element_transforms et ON ei.guid = et.guid
    """)

    elements = src_cursor.fetchall()
    print(f"  Processing {len(elements):,} elements...")

    # Track unique geometries and element->geometry mapping
    geometry_map = {}  # local_hash -> (vertices_blob, faces_blob, normals_blob, counts)
    instance_map = {}  # guid -> local_hash

    for i, (guid, verts_blob, faces_blob, normals_blob, cx, cy, cz) in enumerate(elements):
        if (i + 1) % 5000 == 0:
            print(f"    Processed {i+1:,} elements...")

        # Unpack world-space vertices
        verts_world = unpack_vertices(verts_blob)
        center = (cx, cy, cz)

        # Transform to local space (centered at origin for true GI)
        verts_local = [
            (v[0] - center[0], v[1] - center[1], v[2] - center[2])
            for v in verts_world
        ]
        verts_local_blob = pack_vertices(verts_local)

        # Compute position-independent hash
        local_hash = compute_local_hash(verts_world, center)

        # Store unique geometry with LOCAL-space vertices (centered at origin)
        # Transforms will be applied when creating Blender objects
        if local_hash not in geometry_map:
            geometry_map[local_hash] = (verts_local_blob, faces_blob, normals_blob, len(verts_local),
                                       len(faces_blob) // 12 if faces_blob else 0)

        # Map element to geometry
        instance_map[guid] = local_hash

    print(f"\n📊 Geometry Instancing Results:")
    print(f"  Total elements: {len(elements):,}")
    print(f"  Unique geometries: {len(geometry_map):,}")
    print(f"  Instancing ratio: {len(elements) / len(geometry_map):.2f}×")
    print(f"  Memory saved: {(1 - len(geometry_map)/len(elements)) * 100:.1f}%")

    # Insert unique geometries
    print("\n💾 Writing base_geometries...")
    for local_hash, (verts_blob, faces_blob, normals_blob, vert_count, face_count) in geometry_map.items():
        dst_cursor.execute("""
            INSERT INTO base_geometries (geometry_hash, vertices, faces, normals, vertex_count, face_count)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (local_hash, verts_blob, faces_blob, normals_blob, vert_count, face_count))

    # Insert element instances
    print("💾 Writing element_instances...")
    for guid, local_hash in instance_map.items():
        dst_cursor.execute("""
            INSERT INTO element_instances (guid, geometry_hash)
            VALUES (?, ?)
        """, (guid, local_hash))

    dst_conn.commit()

    # Final stats
    db_size = Path(OUTPUT_DB).stat().st_size / 1024 / 1024
    print(f"\n✅ SUCCESS!")
    print(f"  Database: {OUTPUT_DB}")
    print(f"  Size: {db_size:.1f} MB")
    print(f"  Geometry reduction: {len(elements) - len(geometry_map):,} duplicates removed")

    src_conn.close()
    dst_conn.close()


if __name__ == "__main__":
    main()
