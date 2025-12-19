#!/usr/bin/env python3
"""
Survey to Blender Converter
===========================
Converts JSON survey data to .blend file with pre-loaded reference image

TESTED & WORKING: December 2025 - 688 points, pixel-perfect alignment

Usage:
    blender --background --python survey_to_blend.py -- survey.json survey.png output.blend

IMPORTANT: Always use --background flag! User opens .blend file manually.

================================================================================
CRITICAL BUG FIXES - DO NOT REVERT THESE PATTERNS:
================================================================================

BUG #1: BLENDER IMAGE SCALE (Most Critical!)
    Blender normalizes image empty to longest dimension (1.0 x aspect_ratio).
    Setting scale=(width, height) applies aspect ratio TWICE -> Y compressed.

    WRONG:  empty.scale = (world_width, world_height, 1.0)
    RIGHT:  empty.scale = (world_width, world_width, 1.0)  # Width for BOTH!

    Why: If image is 9934x7017 (aspect 1.416):
         - Blender normalizes to 1.0 x 0.706
         - scale=(420, 297) gives: 420 x (0.706 * 297) = 420 x 209.7  WRONG!
         - scale=(420, 420) gives: 420 x (0.706 * 420) = 420 x 296.8  CORRECT!

BUG #2: IMAGE ANCHOR POINT
    Default anchor is center (-0.5, -0.5), causing massive offset.

    RIGHT:  empty.empty_image_offset = (0, 0)  # Bottom-left
            empty.location = (0, 0, Z_HEIGHT)

BUG #3: Y-AXIS FLIP
    Image Y=0 is top, Blender Y=0 is bottom. Must flip.

    RIGHT:  x_world = px * scale
            y_world = (image_height - py) * scale

================================================================================
"""

import bpy
import json
import sys
from pathlib import Path
from mathutils import Vector


def clear_scene():
    """Clear default Blender scene"""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

    # Remove default collections
    for collection in bpy.data.collections:
        bpy.data.collections.remove(collection)


def create_reference_image(image_path: str, width: float, height: float, center_x: float = None, center_y: float = None):
    """Create reference image as Empty. See docstring at top for requirements."""
    print(f"📐 Adding reference image: {Path(image_path).name}")

    abs_path = str(Path(image_path).absolute())
    img = bpy.data.images.load(abs_path)

    pos_x = center_x if center_x is not None else width / 2
    pos_y = center_y if center_y is not None else height / 2

    # Z MUST be exactly 40.000
    # Position at origin (0, 0) with bottom-left anchor
    bpy.ops.object.empty_add(type='IMAGE', location=(0, 0, 40.000))
    empty = bpy.context.active_object
    empty.name = "Survey_Reference_Image"
    empty.data = img
    empty.empty_image_side = 'FRONT'

    # CRITICAL: Set image offset to (0, 0) for bottom-left anchor
    # Default (-0.5, -0.5) causes massive offset!
    empty.empty_image_offset = (0, 0)

    # CORRECT scaling: display_size=1.0, scale=(width, width, 1.0)
    # Blender normalizes image to 1.0 in larger dimension (preserving aspect)
    # So Y becomes (img_h/img_w) * scale_y. To get true height, scale_y must = width
    empty.empty_display_size = 1.0
    empty.scale = (width, width, 1.0)  # Both use width to preserve aspect after normalization

    empty.lock_location = (False, False, False)
    empty.lock_rotation = (True, True, True)
    empty.lock_scale = (True, True, True)

    print(f"✓ Image at Z=40.000, size: {width:.1f}m × {height:.1f}m, origin: (0, 0), offset: (0, 0)")
    return empty


def pixel_to_world(px: float, py: float, pz: float, image_height: float, scale: float, affine_transform=None, y_scale_factor: float = 1.0):
    """
    Convert pixel coordinates to world coordinates.

    If affine_transform is provided (2x3 matrix), uses it for auto-calibrated
    conversion that corrects scale, rotation, and shear.
    Otherwise falls back to simple linear transform.

    y_scale_factor: Optional multiplier for Y scale (1.0 = normal, 1.1 = 10% stretch)
    """
    if affine_transform is not None:
        # Use affine transform: [x, y] = A @ [px, py, 1]
        import numpy as np
        A = np.array(affine_transform)
        pt = np.array([px, py, 1])
        result = A @ pt
        x, y = result[0], result[1]
    else:
        # Fallback: simple linear transform
        y_flipped = image_height - py
        x = px * scale
        y = y_flipped * scale * y_scale_factor

    z = pz  # Already in meters
    return (x, y, z)


def is_valid_elevation(z: float) -> bool:
    """Validate elevation is in reasonable range (40-50m for this survey)"""
    return z is not None and 40.0 <= z <= 50.0


# Uncertain value handling
UNCERTAIN_PLACEHOLDER = 41.000  # Z value for completely uncertain readings (XX.XXX)

def parse_elevation_value(value_str: str, uncertain_log: list = None) -> tuple:
    """
    Parse elevation value, handling uncertain digits marked with 'X'.

    Args:
        value_str: Elevation string, e.g., "43.125" or "43.12X" or "XX.XXX"
        uncertain_log: Optional list to append uncertain values for review

    Returns:
        tuple: (z_value, is_uncertain)
        - z_value: Float elevation or None if invalid
        - is_uncertain: True if value contains X placeholders
    """
    if value_str is None:
        return (None, False)

    value_str = str(value_str).strip().upper()

    # Check for X placeholders (uncertain digits)
    if 'X' in value_str:
        # Completely uncertain
        if value_str == "XX.XXX" or value_str.count('X') >= 4:
            if uncertain_log is not None:
                uncertain_log.append({
                    "original": value_str,
                    "z": UNCERTAIN_PLACEHOLDER,
                    "reason": "Completely unreadable"
                })
            return (UNCERTAIN_PLACEHOLDER, True)

        # Partially uncertain - replace X with 0 for estimation
        estimated_str = value_str.replace('X', '0')
        try:
            z = float(estimated_str)
            if is_valid_elevation(z):
                if uncertain_log is not None:
                    uncertain_log.append({
                        "original": value_str,
                        "z": z,
                        "reason": f"Uncertain digit(s)"
                    })
                return (z, True)
        except ValueError:
            pass
        return (None, True)

    # Standard numeric value
    try:
        z = float(value_str)
        if is_valid_elevation(z):
            return (z, False)
    except (ValueError, TypeError):
        pass

    return (None, False)


def create_survey_point(data: dict, point_type: str, image_height: float, scale: float, affine_transform=None, y_scale_factor: float = 1.0):
    """Create a survey point as a mesh with custom properties"""

    # Validate elevation format
    if not is_valid_elevation(data.get('z')):
        return None

    # Convert coordinates
    x, y, z = pixel_to_world(data['x'], data['y'], data['z'], image_height, scale, affine_transform, y_scale_factor)

    # Create small sphere to represent point (0.05m = 5cm for fine alignment)
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=0.05,
        segments=8,
        ring_count=6,
        location=(x, y, z)
    )

    point_obj = bpy.context.active_object
    point_obj.name = f"{point_type}_{data['z']:.3f}"  # Name by Z value for easy Outliner search

    # Add custom properties for survey data
    point_obj["SurveyPointType"] = point_type
    point_obj["PointID"] = data['id']
    point_obj["Elevation"] = data['z']
    point_obj["PixelX"] = data['x']
    point_obj["PixelY"] = data['y']
    point_obj["Label"] = data.get('label', '')
    point_obj["Type"] = data.get('type', '')

    # Color coding by type
    mat = bpy.data.materials.new(name=f"Mat_{point_type}")
    mat.use_nodes = True
    principled = mat.node_tree.nodes.get('Principled BSDF')

    if point_type == "GroundElevation":
        principled.inputs['Base Color'].default_value = (0.2, 0.8, 0.2, 1.0)  # Green
    elif point_type == "InvertLevel":
        principled.inputs['Base Color'].default_value = (0.2, 0.2, 0.8, 1.0)  # Blue
    elif point_type == "Infrastructure":
        principled.inputs['Base Color'].default_value = (0.8, 0.2, 0.2, 1.0)  # Red

    point_obj.data.materials.append(mat)

    return point_obj


def create_text_label(text: str, location: tuple, name: str):
    """Create 3D text label at location"""
    bpy.ops.object.text_add(location=location)
    text_obj = bpy.context.active_object
    text_obj.name = name
    text_obj.data.body = text
    text_obj.data.size = 1.2  # 4x larger for visibility
    text_obj.data.extrude = 0.02

    # Rotate to face up
    text_obj.rotation_euler = (1.5708, 0, 0)  # 90 degrees in radians

    # Offset slightly above point
    text_obj.location.z += 0.15

    return text_obj


def convert_survey_to_blend(json_path: str, image_path: str, output_blend: str):
    """Main conversion function"""

    print(f"\nConverting survey to Blender scene\n")
    print(f"   JSON: {Path(json_path).name}")
    print(f"   Image: {Path(image_path).name}\n")

    # Track uncertain values for debug log
    uncertain_log = []
    rejected_count = 0
    valid_count = 0

    # Load JSON
    with open(json_path, 'r') as f:
        data = json.load(f)

    # Extract metadata
    meta = data.get('metadata', {})
    image_width = meta.get('image_dimensions', {}).get('width', 0)
    image_height = meta.get('image_dimensions', {}).get('height', 0)
    scale = meta.get('scale', 0.1)
    affine_transform = meta.get('affine_transform')  # 2x3 matrix for auto-calibration
    y_scale_factor = meta.get('y_scale_factor', 1.0)  # Optional Y stretch factor

    if affine_transform:
        print(f"   Using affine transform for auto-calibration")
    else:
        print(f"   Using simple linear transform (no affine calibration)")
    if y_scale_factor != 1.0:
        print(f"   Y scale factor: {y_scale_factor} ({(y_scale_factor-1)*100:+.0f}% stretch)")

    # Calculate world dimensions from ACTUAL IMAGE (not point bounds)
    # This preserves correct aspect ratio and positioning
    world_width = image_width * scale
    world_height = image_height * scale * y_scale_factor

    # Center at image center (not point bbox center)
    bounds_center_x = world_width / 2
    bounds_center_y = world_height / 2

    print(f"   Image size: {image_width} × {image_height} pixels")
    print(f"   World size: {world_width:.1f}m × {world_height:.1f}m (scale={scale})")

    # Log point distribution for reference (but don't use for sizing)
    points = data.get('ground_elevations', [])
    if points:
        valid_coords = []
        for pt in points:
            if is_valid_elevation(pt.get('z')):
                x, y, z = pixel_to_world(pt['x'], pt['y'], pt['z'], image_height, scale, affine_transform, y_scale_factor)
                valid_coords.append((x, y))

        if valid_coords:
            min_x = min(c[0] for c in valid_coords)
            max_x = max(c[0] for c in valid_coords)
            min_y = min(c[1] for c in valid_coords)
            max_y = max(c[1] for c in valid_coords)
            print(f"   Points bounds: X[{min_x:.1f}, {max_x:.1f}] Y[{min_y:.1f}, {max_y:.1f}]")

    # Clear scene
    clear_scene()

    # Create collections for organization
    ground_col = bpy.data.collections.new("Ground_Elevations")
    invert_col = bpy.data.collections.new("Invert_Levels")
    infra_col = bpy.data.collections.new("Infrastructure")
    labels_col = bpy.data.collections.new("Labels")

    bpy.context.scene.collection.children.link(ground_col)
    bpy.context.scene.collection.children.link(invert_col)
    bpy.context.scene.collection.children.link(infra_col)
    bpy.context.scene.collection.children.link(labels_col)

    # Add reference image at Z=40.0, fitted to points bounds
    ref_image = create_reference_image(image_path, world_width, world_height, bounds_center_x, bounds_center_y)

    # Create survey points
    count = 0

    # Ground elevations - ONLY valid XX.XXX elevations (40.0-50.0m range)
    for point in data.get('ground_elevations', []):
        # Parse elevation with uncertain value handling
        z_raw = point.get('z')
        z_value, is_uncertain = parse_elevation_value(z_raw, uncertain_log)

        if z_value is None:
            rejected_count += 1
            continue

        # Update point with validated z
        point_copy = point.copy()
        point_copy['z'] = z_value

        obj = create_survey_point(point_copy, "GroundElevation", image_height, scale, affine_transform, y_scale_factor)
        if obj:  # Only if validation passed
            ground_col.objects.link(obj)
            bpy.context.scene.collection.objects.unlink(obj)
            count += 1
            valid_count += 1

            # Mark uncertain points with special property
            if is_uncertain:
                obj["Uncertain"] = True
                obj["OriginalValue"] = str(z_raw)

            # Add text label (elevation only, no other text)
            x, y, z = pixel_to_world(point_copy['x'], point_copy['y'], point_copy['z'], image_height, scale, affine_transform, y_scale_factor)
            # Show original value with X if uncertain
            label_text = str(z_raw) if is_uncertain else f"{z_value:.3f}"

            text_obj = create_text_label(label_text, (x, y, z), f"Label_{point['id']}")
            labels_col.objects.link(text_obj)
            bpy.context.scene.collection.objects.unlink(text_obj)

    # Skip invert levels and infrastructure - not needed for export

    print(f"Created {count} survey point objects")
    print(f"   Valid: {valid_count}, Rejected: {rejected_count}, Uncertain: {len(uncertain_log)}")

    # Set up camera view
    bpy.ops.object.camera_add(location=(world_width/2, world_height/2, 100))
    camera = bpy.context.active_object
    camera.rotation_euler = (0, 0, 0)
    bpy.context.scene.camera = camera

    # Set viewport shading to solid with texture
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.type = 'SOLID'

    # Save blend file
    bpy.ops.wm.save_as_mainfile(filepath=output_blend)
    print(f"\nSaved: {output_blend}")
    print(f"  Size: {Path(output_blend).stat().st_size / 1024:.1f} KB")

    # Generate debug log if there are uncertain values
    if uncertain_log:
        debug_log_path = str(Path(output_blend).with_suffix('.debug.log'))
        with open(debug_log_path, 'w') as f:
            f.write("=" * 60 + "\n")
            f.write("ELEVATION EXTRACTION DEBUG LOG\n")
            f.write("=" * 60 + "\n\n")
            f.write(f"SUMMARY:\n")
            f.write(f"  Valid values: {valid_count}\n")
            f.write(f"  Uncertain values (NEED REVIEW): {len(uncertain_log)}\n")
            f.write(f"  Rejected values: {rejected_count}\n\n")
            f.write("-" * 60 + "\n")
            f.write(f"UNCERTAIN VALUES - MANUAL REVIEW REQUIRED\n")
            f.write("-" * 60 + "\n")
            for i, item in enumerate(uncertain_log, 1):
                f.write(f"\n{i}. Original: {item['original']}\n")
                f.write(f"   Estimated Z: {item['z']:.3f}m\n")
                f.write(f"   Reason: {item['reason']}\n")
            f.write("\n" + "=" * 60 + "\n")
        print(f"\n[!] {len(uncertain_log)} uncertain values need review!")
        print(f"    See: {debug_log_path}")

    print(f"\nConversion complete!")
    print(f"\nNext steps:")
    print(f"   1. Open {Path(output_blend).name} in Blender")
    if uncertain_log:
        print(f"   2. Review {len(uncertain_log)} uncertain points (marked with X)")
    print(f"   3. File > Export > Industry Foundation Classes (.ifc)")
    print(f"   4. File > Export > AutoCAD DXF (.dxf)")


def main():
    """Parse command line arguments and run conversion"""

    # Get arguments after --
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        print("Usage: blender --background --python survey_to_blend.py -- <json_file> <image_file> [output.blend]")
        sys.exit(1)

    if len(argv) < 2:
        print("Error: Need JSON file and image file")
        sys.exit(1)

    json_path = argv[0]
    image_path = argv[1]
    output_blend = argv[2] if len(argv) > 2 else str(Path(json_path).with_suffix('.blend'))

    convert_survey_to_blend(json_path, image_path, output_blend)


if __name__ == "__main__":
    main()
