#!/usr/bin/env python3
"""
Blender Import - Step 4 of 2D-to-3D Pipeline

Creates Blender model from placements JSON.
Includes reference floor plan image with CRITICAL scale fix.

Run with: blender --background --python blender_import.py -- <args>

CRITICAL BUG FIXES APPLIED:
1. Image scale: Use (width, width, 1) NOT (width, height, 1)
2. Image anchor: Set empty_image_offset = (0, 0)
3. Y-flip already applied in floor_plan_parser.py
"""

import sys
import json
from pathlib import Path

# Check if running in Blender
try:
    import bpy
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False
    print("WARNING: Not running in Blender. This script must be run with:")
    print('  blender --background --python blender_import.py -- <placements.json> <image.png> <output.blend>')


def clear_scene():
    """Remove all objects from scene."""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()


def create_reference_image(image_path: str, world_width: float, z_height: float = 0.0):
    """
    Create floor plan reference image with CORRECT scaling.

    CRITICAL BUG FIX:
    Blender's empty_display_size=1.0 normalizes image to longest dimension.
    Setting scale=(width, height) applies aspect ratio TWICE → Y compressed!

    CORRECT: Use (world_width, world_width, 1.0) - Blender handles aspect internally.
    """
    bpy.ops.object.empty_add(type='IMAGE', location=(0, 0, z_height))
    empty = bpy.context.active_object
    empty.name = "Floor_Plan_Reference"

    # Load image
    img = bpy.data.images.load(str(image_path))
    empty.data = img

    # CRITICAL SETTINGS
    empty.empty_display_size = 1.0

    # CRITICAL: Bottom-left anchor, NOT default (-0.5, -0.5)
    empty.empty_image_offset = (0, 0)

    # CRITICAL: Use world_width for BOTH X and Y!
    # Blender's internal aspect ratio handles the rest.
    # DO NOT "FIX" THIS to use (width, height) - it will break!
    empty.scale = (world_width, world_width, 1.0)

    print(f"Created reference image: {world_width:.2f}m wide at Z={z_height}")

    return empty


def create_marker(name: str, location: tuple, color: tuple = (1, 0, 0, 1), size: float = 0.1):
    """Create a simple sphere marker at location."""
    bpy.ops.mesh.primitive_uv_sphere_add(radius=size, location=location)
    obj = bpy.context.active_object
    obj.name = name

    # Create material with color
    mat = bpy.data.materials.new(name=f"Mat_{name}")
    mat.diffuse_color = color
    obj.data.materials.append(mat)

    return obj


def create_door_marker(placement: dict):
    """Create door marker (red)."""
    pos = placement["position"]
    return create_marker(
        placement["name"],
        (pos[0], pos[1], pos[2]),
        color=(0.8, 0.2, 0.1, 1),  # Red
        size=0.15
    )


def create_window_marker(placement: dict):
    """Create window marker (blue)."""
    pos = placement["position"]
    return create_marker(
        placement["name"],
        (pos[0], pos[1], pos[2]),
        color=(0.1, 0.4, 0.9, 1),  # Blue
        size=0.12
    )


def create_fixture_marker(placement: dict):
    """Create fixture marker (yellow/green based on type)."""
    pos = placement["position"]
    fixture_type = placement.get("type", "generic")

    if fixture_type == "fan_point":
        color = (0.2, 0.8, 0.3, 1)  # Green
    elif fixture_type == "switch":
        color = (0.9, 0.8, 0.1, 1)  # Yellow
    else:
        color = (0.5, 0.5, 0.5, 1)  # Gray

    return create_marker(
        placement["name"],
        (pos[0], pos[1], pos[2]),
        color=color,
        size=0.08
    )


def create_collection(name: str) -> 'bpy.types.Collection':
    """Create or get a collection."""
    if name in bpy.data.collections:
        return bpy.data.collections[name]

    collection = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(collection)
    return collection


def import_placements(placements_path: str, image_path: str = None, output_path: str = None):
    """
    Import placements JSON and create Blender model.

    Args:
        placements_path: Path to placements JSON from floor_plan_parser.py
        image_path: Path to floor plan PNG (optional, for reference)
        output_path: Path to save .blend file
    """
    # Load placements
    with open(placements_path, 'r', encoding='utf-8') as f:
        placements = json.load(f)

    # Clear scene
    clear_scene()

    # Get calibration data
    calibration = placements["metadata"].get("calibration", {})
    world_width = calibration.get("real_width", 11.2)

    # Create reference image if provided
    if image_path and Path(image_path).exists():
        create_reference_image(image_path, world_width, z_height=0.0)

    # Create collections
    doors_col = create_collection("Doors")
    windows_col = create_collection("Windows")
    fixtures_col = create_collection("Fixtures")

    # Create door markers
    for door in placements.get("doors", []):
        obj = create_door_marker(door)
        # Move to collection
        bpy.context.scene.collection.objects.unlink(obj)
        doors_col.objects.link(obj)

    # Create window markers
    for window in placements.get("windows", []):
        obj = create_window_marker(window)
        bpy.context.scene.collection.objects.unlink(obj)
        windows_col.objects.link(obj)

    # Create fixture markers
    for fixture in placements.get("fixtures", []):
        obj = create_fixture_marker(fixture)
        bpy.context.scene.collection.objects.unlink(obj)
        fixtures_col.objects.link(obj)

    # Summary
    print("")
    print("=" * 50)
    print("BLENDER IMPORT COMPLETE")
    print("=" * 50)
    print(f"  Doors: {len(placements.get('doors', []))}")
    print(f"  Windows: {len(placements.get('windows', []))}")
    print(f"  Fixtures: {len(placements.get('fixtures', []))}")
    print("=" * 50)

    # Save
    if output_path:
        bpy.ops.wm.save_as_mainfile(filepath=str(output_path))
        print(f"\nSaved to: {output_path}")


def main():
    """CLI entry point for Blender."""
    # Get arguments after '--'
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []

    if len(argv) < 1:
        print("Usage: blender --background --python blender_import.py -- <placements.json> [image.png] [output.blend]")
        print("")
        print("Example:")
        print('  blender --background --python blender_import.py -- ../OUTPUT/placements.json ../CACHE/page1.png ../OUTPUT/TB-LKTN_HOUSE.blend')
        sys.exit(1)

    placements_path = argv[0]
    image_path = argv[1] if len(argv) > 1 else None
    output_path = argv[2] if len(argv) > 2 else None

    import_placements(placements_path, image_path, output_path)


if __name__ == "__main__":
    if IN_BLENDER:
        main()
