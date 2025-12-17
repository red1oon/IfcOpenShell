#!/usr/bin/env python3
"""
Survey to Blender Converter
Converts JSON survey data to .blend file with pre-loaded reference image

Usage:
    blender --background --python survey_to_blend.py -- TopoSurvey_refined.json TopoSurvey.png
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


def create_reference_image(image_path: str, width: float, height: float):
    """Create reference image as Empty at origin"""
    print(f"📐 Adding reference image: {Path(image_path).name}")

    # Load image with absolute path
    abs_path = str(Path(image_path).absolute())
    img = bpy.data.images.load(abs_path)

    # Create empty with image at Z=40m (below typical elevations)
    bpy.ops.object.empty_add(type='IMAGE', location=(width/2, height/2, 40.0))
    empty = bpy.context.active_object
    empty.name = "Survey_Reference_Image"
    empty.data = img
    empty.empty_display_size = max(width, height)
    empty.empty_image_side = 'FRONT'

    # Scale to match world dimensions
    empty.scale = (width / img.size[0], height / img.size[1], 1.0)

    # Allow position adjustment, but lock rotation/scale to maintain alignment
    empty.lock_location = (False, False, False)  # Unlock all movement
    empty.lock_rotation = (True, True, True)     # Lock rotation
    empty.lock_scale = (True, True, True)        # Lock scale

    print(f"✓ Image loaded: {width:.1f}m × {height:.1f}m")
    return empty


def pixel_to_world(px: float, py: float, pz: float, image_height: float, scale: float):
    """Convert pixel coordinates to world coordinates"""
    # Flip Y axis (image origin top-left, Blender origin bottom-left)
    y_flipped = image_height - py

    x = px * scale
    y = y_flipped * scale
    z = pz  # Already in meters

    return (x, y, z)


def is_valid_elevation(z: float) -> bool:
    """Validate elevation is in reasonable range (40-50m for this survey)"""
    return z is not None and 40.0 <= z <= 50.0


def create_survey_point(data: dict, point_type: str, image_height: float, scale: float):
    """Create a survey point as a mesh with custom properties"""

    # Validate elevation format
    if not is_valid_elevation(data.get('z')):
        return None

    # Convert coordinates
    x, y, z = pixel_to_world(data['x'], data['y'], data['z'], image_height, scale)

    # Create small sphere to represent point
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=0.3,
        location=(x, y, z)
    )

    point_obj = bpy.context.active_object
    point_obj.name = f"{point_type}_{data['id']}"

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
    text_obj.data.size = 2.0
    text_obj.data.extrude = 0.1

    # Rotate to face up
    text_obj.rotation_euler = (1.5708, 0, 0)  # 90 degrees in radians

    # Offset slightly above point
    text_obj.location.z += 1.0

    return text_obj


def convert_survey_to_blend(json_path: str, image_path: str, output_blend: str):
    """Main conversion function"""

    print(f"\n🔄 Converting survey to Blender scene\n")
    print(f"   JSON: {Path(json_path).name}")
    print(f"   Image: {Path(image_path).name}\n")

    # Load JSON
    with open(json_path, 'r') as f:
        data = json.load(f)

    # Extract metadata
    meta = data.get('metadata', {})
    image_width = meta.get('image_dimensions', {}).get('width', 0)
    image_height = meta.get('image_dimensions', {}).get('height', 0)
    scale = meta.get('scale', 0.1)

    # Calculate world dimensions
    world_width = image_width * scale
    world_height = image_height * scale

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

    # Add reference image
    ref_image = create_reference_image(image_path, world_width, world_height)

    # Create survey points
    count = 0

    # Ground elevations - ONLY valid XX.XXX elevations
    for point in data.get('ground_elevations', []):
        obj = create_survey_point(point, "GroundElevation", image_height, scale)
        if obj:  # Only if validation passed
            ground_col.objects.link(obj)
            bpy.context.scene.collection.objects.unlink(obj)
            count += 1

            # Add text label (elevation only, no other text)
            x, y, z = pixel_to_world(point['x'], point['y'], point['z'], image_height, scale)
            label_text = f"{point['z']:.3f}"

            text_obj = create_text_label(label_text, (x, y, z), f"Label_{point['id']}")
            labels_col.objects.link(text_obj)
            bpy.context.scene.collection.objects.unlink(text_obj)

    # Skip invert levels and infrastructure - not needed for export

    print(f"✓ Created {count} survey point objects")

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
    print(f"\n✓ Saved: {output_blend}")
    print(f"  Size: {Path(output_blend).stat().st_size / 1024:.1f} KB")

    print(f"\n✅ Conversion complete!")
    print(f"\n📝 Next steps:")
    print(f"   1. Open {Path(output_blend).name} in Blender")
    print(f"   2. Review alignment and adjust points if needed")
    print(f"   3. File → Export → Industry Foundation Classes (.ifc)")
    print(f"   4. File → Export → AutoCAD DXF (.dxf)")


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
