#!/usr/bin/env python3
"""
Blender Staged Import - Import staged extraction output with actual geometry.

Creates walls, drains, openings, roof outline for proofing.

Run with: blender --background --python blender_staged_import.py -- <staged_extraction_FINAL.json> [output.blend]
Or open Blender and run from Text Editor.
"""

import sys
import json
import math
from pathlib import Path

try:
    import bpy
    import bmesh
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False
    print("Not in Blender. Run with: blender --python blender_staged_import.py -- <json> [output.blend]")


def clear_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    for col in bpy.data.collections:
        if col.name != "Collection":
            bpy.data.collections.remove(col)


def create_collection(name):
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def create_material(name, color):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    return mat


def create_wall(start, end, thickness, height, name, collection, is_interior=False):
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.sqrt(dx*dx + dy*dy)
    angle = math.atan2(dy, dx)
    cx = (start[0] + end[0]) / 2
    cy = (start[1] + end[1]) / 2
    cz = height / 2
    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz))
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (length, thickness, height)
    obj.rotation_euler = (0, 0, angle)
    if is_interior:
        mat = create_material("IntWall_Mat", (0.9, 0.85, 0.7, 1))
    else:
        mat = create_material("Wall_Mat", (0.8, 0.8, 0.75, 1))
    obj.data.materials.append(mat)
    for c in obj.users_collection:
        c.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


def create_drain(start, end, width, name, collection):
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.sqrt(dx*dx + dy*dy)
    angle = math.atan2(dy, dx)
    cx = (start[0] + end[0]) / 2
    cy = (start[1] + end[1]) / 2
    cz = -0.075
    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz))
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (length, width, 0.15)
    obj.rotation_euler = (0, 0, angle)
    mat = create_material("Drain_Mat", (0.4, 0.4, 0.4, 1))
    obj.data.materials.append(mat)
    for c in obj.users_collection:
        c.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


def create_door_marker(pos, width, height, name, collection, host_wall=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(pos[0], pos[1], height/2))
    obj = bpy.context.active_object
    obj.name = name
    # Rotate based on host wall orientation
    # Exterior: LEFT/RIGHT are vertical, FRONT/BACK are horizontal
    # Interior: INT_WALL_B/C/D are vertical, INT_WALL_ROW* are horizontal
    is_vertical = False
    if host_wall:
        if "LEFT" in host_wall or "RIGHT" in host_wall:
            is_vertical = True
        elif host_wall.startswith("INT_WALL_") and "ROW" not in host_wall:
            is_vertical = True
    if is_vertical:
        obj.scale = (0.05, width, height)  # rotated 90 deg
    else:
        obj.scale = (width, 0.05, height)  # default horizontal
    mat = create_material("Door_Mat", (0.6, 0.3, 0.1, 1))
    obj.data.materials.append(mat)
    for c in obj.users_collection:
        c.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


def create_window_marker(pos, width, height, sill, name, collection, host_wall=None):
    z = sill + height/2
    bpy.ops.mesh.primitive_cube_add(size=1, location=(pos[0], pos[1], z))
    obj = bpy.context.active_object
    obj.name = name
    # Rotate based on host wall orientation
    if host_wall and ("LEFT" in host_wall or "RIGHT" in host_wall):
        obj.scale = (0.05, width, height)  # rotated 90 deg
    else:
        obj.scale = (width, 0.05, height)  # default FRONT/BACK
    mat = create_material("Window_Mat", (0.3, 0.5, 0.8, 1))
    obj.data.materials.append(mat)
    for c in obj.users_collection:
        c.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


def create_roof_outline(bounds, eave_height, ridge_height, name, collection):
    min_x = bounds["min_x"]
    max_x = bounds["max_x"]
    min_y = bounds["min_y"]
    max_y = bounds["max_y"]
    mesh = bpy.data.meshes.new(name + "_mesh")
    obj = bpy.data.objects.new(name, mesh)
    bm = bmesh.new()
    v1 = bm.verts.new((min_x, min_y, eave_height))
    v2 = bm.verts.new((max_x, min_y, eave_height))
    v3 = bm.verts.new((max_x, max_y, eave_height))
    v4 = bm.verts.new((min_x, max_y, eave_height))
    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2
    v5 = bm.verts.new((cx, cy, ridge_height))
    bm.edges.new((v1, v2))
    bm.edges.new((v2, v3))
    bm.edges.new((v3, v4))
    bm.edges.new((v4, v1))
    bm.edges.new((v1, v5))
    bm.edges.new((v2, v5))
    bm.edges.new((v3, v5))
    bm.edges.new((v4, v5))
    bm.to_mesh(mesh)
    bm.free()
    collection.objects.link(obj)
    return obj


def create_porch(bounds, roof_height, columns, name, collection):
    min_x = bounds["min_x"]
    max_x = bounds["max_x"]
    min_y = bounds["min_y"]
    max_y = bounds["max_y"]
    cx = (min_x + max_x) / 2
    cy = (min_y + max_y) / 2
    width = max_x - min_x
    depth = max_y - min_y
    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, roof_height))
    obj = bpy.context.active_object
    obj.name = name + "_roof"
    obj.scale = (width, depth, 0.1)
    mat = create_material("Porch_Mat", (0.7, 0.5, 0.4, 1))
    obj.data.materials.append(mat)
    for c in obj.users_collection:
        c.objects.unlink(obj)
    collection.objects.link(obj)
    for col in columns:
        pos = col["position_m"]
        bpy.ops.mesh.primitive_cube_add(size=1, location=(pos[0], pos[1], roof_height/2))
        col_obj = bpy.context.active_object
        col_obj.name = col["id"]
        col_obj.scale = (0.15, 0.15, roof_height)
        col_obj.data.materials.append(mat)
        for c in col_obj.users_collection:
            c.objects.unlink(col_obj)
        collection.objects.link(col_obj)


def create_floor_slab(width, depth, collection):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(width/2, -depth/2, -0.075))
    obj = bpy.context.active_object
    obj.name = "Floor_Slab"
    obj.scale = (width, depth, 0.15)
    mat = create_material("Slab_Mat", (0.6, 0.6, 0.6, 1))
    obj.data.materials.append(mat)
    for c in obj.users_collection:
        c.objects.unlink(obj)
    collection.objects.link(obj)
    return obj


def import_staged(json_path, output_path=None):
    with open(json_path, 'r') as f:
        data = json.load(f)
    clear_scene()
    meta = data["metadata"]
    if "calibration" in meta:
        width = meta["calibration"]["real_width"]
        depth = meta["calibration"]["real_height"]
    else:
        width = meta.get("building_width_m", 11.2)
        depth = meta.get("building_depth_m", 8.5)
    drains_col = create_collection("Drains")
    walls_col = create_collection("Walls")
    int_walls_col = create_collection("Interior_Walls")
    doors_col = create_collection("Doors")
    int_doors_col = create_collection("Interior_Doors")
    windows_col = create_collection("Windows")
    roof_col = create_collection("Roof")
    slabs_col = create_collection("Slabs")
    create_floor_slab(width, depth, slabs_col)
    if "stage1_perimeter" in data:
        stage1 = data.get("stage1_perimeter")
        if stage1:
            for seg in stage1["drain_segments"]:
                create_drain(seg["start_m"], seg["end_m"], 0.15, seg["id"], drains_col)
        stage2 = data.get("stage2_exterior")
        if stage2:
            for wall in stage2["external_walls"]:
                create_wall(wall["start_m"], wall["end_m"], wall["thickness_m"], wall["height_m"], wall["id"], walls_col)
            for door in stage2["doors"]:
                create_door_marker(door["position_m"], door["width_m"], door["height_m"], door["id"], doors_col, door.get("host_wall"))
            for win in stage2["windows"]:
                create_window_marker(win["position_m"], win["width_m"], win["height_m"], win["sill_height_m"], win["id"], windows_col, win.get("host_wall"))
        stage3 = data.get("stage3_roof_porch")
        if stage3:
            roof = stage3["roof"]
            create_roof_outline(roof["bounds"], roof["eave_height_m"], roof["ridge_height_m"], roof["id"], roof_col)
            porch = stage3["porch"]
            create_porch(porch["bounds"], porch["roof_height_m"], porch["columns"], porch["id"], roof_col)
    else:
        for p in data.get("placements", []):
            ptype = p.get("type")
            name = p.get("name", "unnamed")
            if ptype == "drain":
                create_drain(p["start_point"], p["end_point"], 0.15, name, drains_col)
            elif ptype == "wall":
                is_int = p.get("is_interior", False)
                col = int_walls_col if is_int else walls_col
                create_wall(p["start_point"], p["end_point"], p["thickness"], p["height"], name, col, is_int)
            elif ptype == "door":
                is_int = p.get("is_interior", False)
                col = int_doors_col if is_int else doors_col
                create_door_marker(p["position"], p["width"], p["height"], name, col, p.get("host_wall"))
            elif ptype == "window":
                create_window_marker(p["position"], p["width"], p["height"], p["sill_height"], name, windows_col, p.get("host_wall"))
            elif ptype == "roof":
                create_roof_outline(p["bounds"], p["eave_height"], p["ridge_height"], name, roof_col)
            elif ptype == "porch":
                create_porch(p["bounds"], p["roof_height"], p["columns"], name, roof_col)
    print("Import complete")
    print(f"Building: {width}m x {depth}m")
    print(f"Placements: {len(data.get('placements', []))}")
    if output_path:
        bpy.ops.wm.save_as_mainfile(filepath=str(output_path))
        print(f"Saved: {output_path}")


def main():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    if len(argv) < 1:
        print("Usage: blender --python blender_staged_import.py -- <staged_extraction_FINAL.json> [output.blend]")
        return
    json_path = argv[0]
    output_path = argv[1] if len(argv) > 1 else None
    import_staged(json_path, output_path)


if __name__ == "__main__":
    if IN_BLENDER:
        main()
