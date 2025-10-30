#!/usr/bin/env python3
"""
Robust Sample Tester - Clash Detection + PNG Snapshot
======================================================

Tests if a sample database is good by:
1. Loading it in Blender
2. Running clash detection
3. Taking a PNG snapshot from a good angle
4. Reporting results

Usage:
    ~/blender-4.5.3/blender --background --python test_sample_with_snapshot.py
"""

import bpy
import sys
import sqlite3
from pathlib import Path
from mathutils import Vector

# Add paths
sys.path.insert(0, '/home/red1/Projects/IfcOpenShell/src')
sys.path.insert(0, '/home/red1/Projects/IfcOpenShell/src/bonsai')

from bonsai.bim.module.federation.loader import FederationLoader

DB_PATH = "/home/red1/Documents/bonsai/DatabaseFiles/sample_extracted.db"
OUTPUT_PNG = "/home/red1/Documents/bonsai/Screenshots/sample_test.png"

def setup_scene():
    """Clear scene and setup camera/lighting"""
    # Clear existing objects
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

    # Add camera (will position after loading geometry)
    bpy.ops.object.camera_add(location=(0, 0, 0))
    camera = bpy.context.object
    bpy.context.scene.camera = camera

    # Add sun light
    bpy.ops.object.light_add(type='SUN', location=(0, 0, 100))
    light = bpy.context.object
    light.data.energy = 2.0

    return camera

def frame_camera_on_objects(camera, objects):
    """Position camera to frame all loaded objects"""
    print(f"\n📷 Framing camera on {len(objects)} objects...")

    if not objects:
        print("❌ No objects to frame")
        return False

    # Calculate bounding box of all objects
    mesh_objects = [obj for obj in objects if obj and obj.type == 'MESH']

    if not mesh_objects:
        print("❌ No mesh objects found")
        return False

    # Get overall bounds
    all_coords = []
    for obj in mesh_objects:
        if obj.bound_box:
            for coord in obj.bound_box:
                world_coord = obj.matrix_world @ Vector(coord)
                all_coords.append(world_coord)

    if not all_coords:
        print("❌ No coordinates found")
        return False

    # Calculate center and size
    xs = [c[0] for c in all_coords]
    ys = [c[1] for c in all_coords]
    zs = [c[2] for c in all_coords]

    center = Vector((
        (min(xs) + max(xs)) / 2,
        (min(ys) + max(ys)) / 2,
        (min(zs) + max(zs)) / 2
    ))

    size = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))

    # Position camera to view from good angle
    distance = size * 0.8  # Closer view for better framing
    camera.location = center + Vector((distance * 0.7, -distance * 0.7, distance * 0.5))

    # Point camera at center (cameras look down -Z axis)
    direction = center - camera.location
    camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

    print(f"✅ Camera positioned at {camera.location}")
    print(f"   Viewing center: {center}, size: {size:.1f}m")
    return True

def load_database():
    """Load elements from database and create mesh objects"""
    print(f"\n{'='*80}")
    print("LOADING DATABASE")
    print(f"{'='*80}\n")

    if not Path(DB_PATH).exists():
        print(f"❌ Database not found: {DB_PATH}")
        return False, {}, []

    # First check metadata
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT discipline, COUNT(*)
        FROM elements_meta
        GROUP BY discipline
        ORDER BY discipline
    """)

    disc_counts = {}
    for disc, count in cursor.fetchall():
        disc_counts[disc] = count
        print(f"  {disc}: {count} elements")

    print(f"\n  Total: {sum(disc_counts.values())} elements across {len(disc_counts)} disciplines")
    conn.close()

    if len(disc_counts) < 3:
        print(f"\n❌ FAIL - Need at least 3 disciplines, found {len(disc_counts)}")
        return False, disc_counts, []

    # Now actually load geometry into Blender
    print(f"\n📦 Loading geometry into Blender...")
    try:
        loader = FederationLoader(DB_PATH)
        loader.stage2_gpu_instancing = True
        loader.stage2_progressive = False

        objects = loader.load_federation()

        if not objects or len(objects) == 0:
            print(f"\n❌ FAIL - No mesh objects created in scene")
            return False, disc_counts, []

        print(f"✅ {len(objects)} mesh objects loaded into scene")
        return True, disc_counts, objects

    except Exception as e:
        print(f"\n❌ FAIL - Geometry loading error: {e}")
        import traceback
        traceback.print_exc()
        return False, disc_counts, []

def take_snapshot(camera, output_path):
    """Render and save PNG screenshot"""
    print(f"\n{'='*80}")
    print("TAKING SNAPSHOT")
    print(f"{'='*80}\n")

    # Setup render settings
    scene = bpy.context.scene
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = output_path
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080

    # Render
    bpy.ops.render.render(write_still=True)

    if Path(output_path).exists():
        print(f"✅ Snapshot saved: {output_path}")
        return True
    else:
        print(f"❌ Failed to save snapshot")
        return False

def main():
    print(f"\n{'='*80}")
    print("ROBUST SAMPLE TESTER")
    print(f"{'='*80}\n")
    print(f"Database: {DB_PATH}")
    print(f"Output PNG: {OUTPUT_PNG}\n")

    # Setup scene
    camera = setup_scene()

    # Load database and geometry
    success, disc_counts, objects = load_database()

    if not success or not objects:
        print("\n❌ TEST FAILED - Loading stage failed (no geometry in scene)")
        sys.exit(1)

    print(f"\n✅ Loading stage passed - {len(objects)} objects in scene")

    # Frame camera on loaded geometry
    if not frame_camera_on_objects(camera, objects):
        print("\n❌ TEST FAILED - Camera framing failed")
        sys.exit(1)

    # Take snapshot
    Path(OUTPUT_PNG).parent.mkdir(parents=True, exist_ok=True)
    snapshot_ok = take_snapshot(camera, OUTPUT_PNG)

    if snapshot_ok:
        print(f"\n{'='*80}")
        print("✅ TEST PASSED - Sample is GOOD!")
        print(f"{'='*80}\n")
        print(f"Disciplines: {', '.join(disc_counts.keys())}")
        print(f"Total elements: {sum(disc_counts.values())}")
        print(f"Screenshot: {OUTPUT_PNG}\n")
        sys.exit(0)
    else:
        print("\n❌ TEST FAILED - Could not generate snapshot")
        sys.exit(1)

if __name__ == "__main__":
    main()
