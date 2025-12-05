#!/usr/bin/env python3
"""
Diagnose BLOSM coordinate ranges before IFC export
Run: ~/blender-4.5.0/blender --background klang_buildings_blosm.blend --python diagnose_coords.py
"""
import bpy
import bmesh
from mathutils import Vector

print("\n" + "="*70)
print("BLOSM COORDINATE DIAGNOSTIC")
print("="*70)

def get_world_bounds(obj):
    """Get world-space bounding box of mesh object"""
    if obj.type != 'MESH' or not obj.data.vertices:
        return None

    # Get world coordinates of all vertices
    matrix = obj.matrix_world
    world_verts = [matrix @ v.co for v in obj.data.vertices]

    xs = [v.x for v in world_verts]
    ys = [v.y for v in world_verts]
    zs = [v.z for v in world_verts]

    return {
        'min': Vector((min(xs), min(ys), min(zs))),
        'max': Vector((max(xs), max(ys), max(zs))),
        'center': Vector(((min(xs)+max(xs))/2, (min(ys)+max(ys))/2, (min(zs)+max(zs))/2)),
        'size': Vector((max(xs)-min(xs), max(ys)-min(ys), max(zs)-min(zs)))
    }

# Analyze all mesh objects
print("\n[1] Object Location Analysis")
print("-" * 50)

all_bounds = []
issues = []

for obj in bpy.data.objects:
    if obj.type not in ['MESH', 'CURVE']:
        continue
    if obj.name in ['Camera', 'Light', 'Cube']:
        continue

    # Check object location
    loc = obj.location

    # Flag potential issues
    if abs(loc.x) > 10000 or abs(loc.y) > 10000:
        issues.append(f"LARGE COORDS: {obj.name} at ({loc.x:.1f}, {loc.y:.1f}, {loc.z:.1f})")

    if obj.type == 'MESH' and obj.data.vertices:
        bounds = get_world_bounds(obj)
        if bounds:
            all_bounds.append((obj.name, bounds))

            # Check for microscopic geometry
            size = bounds['size']
            if size.x < 0.01 and size.y < 0.01 and size.z < 0.01:
                issues.append(f"MICROSCOPIC: {obj.name} size ({size.x:.4f}, {size.y:.4f}, {size.z:.4f})")

            # Check for extreme coordinates
            if abs(bounds['center'].x) > 100000 or abs(bounds['center'].y) > 100000:
                issues.append(f"EXTREME POSITION: {obj.name} center at {bounds['center']}")

# Print sample of objects
print(f"\nAnalyzed {len(all_bounds)} mesh objects")
print("\nSample objects (first 5):")
for name, bounds in all_bounds[:5]:
    print(f"  {name}:")
    print(f"    Center: ({bounds['center'].x:.2f}, {bounds['center'].y:.2f}, {bounds['center'].z:.2f})")
    print(f"    Size:   ({bounds['size'].x:.2f} x {bounds['size'].y:.2f} x {bounds['size'].z:.2f})")

# Calculate scene bounds
if all_bounds:
    all_min_x = min(b['min'].x for _, b in all_bounds)
    all_max_x = max(b['max'].x for _, b in all_bounds)
    all_min_y = min(b['min'].y for _, b in all_bounds)
    all_max_y = max(b['max'].y for _, b in all_bounds)
    all_min_z = min(b['min'].z for _, b in all_bounds)
    all_max_z = max(b['max'].z for _, b in all_bounds)

    scene_center = Vector((
        (all_min_x + all_max_x) / 2,
        (all_min_y + all_max_y) / 2,
        (all_min_z + all_max_z) / 2
    ))
    scene_size = Vector((
        all_max_x - all_min_x,
        all_max_y - all_min_y,
        all_max_z - all_min_z
    ))

    print(f"\n[2] SCENE BOUNDS")
    print("-" * 50)
    print(f"X: {all_min_x:.2f} to {all_max_x:.2f} ({scene_size.x:.2f}m)")
    print(f"Y: {all_min_y:.2f} to {all_max_y:.2f} ({scene_size.y:.2f}m)")
    print(f"Z: {all_min_z:.2f} to {all_max_z:.2f} ({scene_size.z:.2f}m)")
    print(f"\nScene center: ({scene_center.x:.2f}, {scene_center.y:.2f}, {scene_center.z:.2f})")
    print(f"Scene extent: {scene_size.x:.2f} x {scene_size.y:.2f} x {scene_size.z:.2f} meters")

    # DIAGNOSIS
    print(f"\n[3] DIAGNOSIS")
    print("-" * 50)

    if abs(scene_center.x) > 10000 or abs(scene_center.y) > 10000:
        print("WARNING: LARGE OFFSET DETECTED!")
        print(f"   Scene is centered at ({scene_center.x:.0f}, {scene_center.y:.0f})")
        print("   This may cause precision issues in IFC viewers")
        print(f"\n   RECOMMENDED: Apply offset of ({-scene_center.x:.2f}, {-scene_center.y:.2f}, {-scene_center.z:.2f})")
        print("   Or use IfcMapConversion to store georeference")
    else:
        print("OK: Coordinates are in reasonable range (< 10km from origin)")

    if scene_size.x > 5000 or scene_size.y > 5000:
        print(f"\nWARNING: LARGE SCENE: {scene_size.x:.0f} x {scene_size.y:.0f} meters")
        print("   Some IFC viewers may have clipping issues")

    if scene_size.x < 1 and scene_size.y < 1:
        print(f"\nWARNING: VERY SMALL SCENE: {scene_size.x:.4f} x {scene_size.y:.4f} meters")
        print("   Objects may appear microscopic - check BLOSM import scale")

# Print issues
if issues:
    print(f"\n[4] ISSUES FOUND ({len(issues)})")
    print("-" * 50)
    for issue in issues[:10]:
        print(f"  * {issue}")
    if len(issues) > 10:
        print(f"  ... and {len(issues) - 10} more")
else:
    print("\nOK: No coordinate issues detected")

print("\n" + "="*70)
