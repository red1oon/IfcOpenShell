"""
3D Viewport Visualization for Resolution Preview
=================================================

Creates ghost geometry, arrows, and markers to show proposed clash resolutions
in the Blender viewport before user applies them.

Visual Elements:
- Red ghost: Current element position (50% transparent)
- Green ghost: Proposed new position (50% transparent)
- Yellow arrow: Movement vector
- Cyan spheres: Clash points that will be resolved

Part of: Intelligent Clash Adjustment System - Phase 1.5/2
"""

import bpy
import json
from mathutils import Vector
from typing import List, Tuple, Dict, Optional


def create_ghost_box(bbox: dict, color: tuple, name: str, offset: Vector = None) -> bpy.types.Object:
    """
    Create transparent procedural box for preview.

    Args:
        bbox: Dict with 'minX', 'maxX', 'minY', 'maxY', 'minZ', 'maxZ'
        color: RGBA tuple (r, g, b, a) where 0.0-1.0
        name: Object name (should start with "PREVIEW_")
        offset: Optional coordinate offset to apply

    Returns:
        Blender object
    """
    # Calculate dimensions
    dims = Vector((
        bbox['maxX'] - bbox['minX'],
        bbox['maxY'] - bbox['minY'],
        bbox['maxZ'] - bbox['minZ']
    ))

    center = Vector((
        (bbox['minX'] + bbox['maxX']) / 2,
        (bbox['minY'] + bbox['maxY']) / 2,
        (bbox['minZ'] + bbox['maxZ']) / 2
    ))

    # Apply offset if provided
    if offset:
        center += offset

    # Create cube mesh
    bpy.ops.mesh.primitive_cube_add(size=1, location=center)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = dims / 2  # Cube is 2x2x2 by default

    # Create material with transparency
    mat = bpy.data.materials.new(name=f"{name}_Material")
    mat.use_nodes = True
    mat.blend_method = 'BLEND'  # Enable transparency

    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs['Base Color'].default_value = color[:3] + (1.0,)  # RGB + full alpha for color
    bsdf.inputs['Alpha'].default_value = color[3]  # Transparency
    bsdf.inputs['Roughness'].default_value = 0.3  # Slight glossiness

    # Add emission for green boxes (proposed position) - better visibility
    if "Proposed" in name:
        # Blender 4.2 vs 4.5 compatibility - BRIGHT GREEN GLOW
        if 'Emission Color' in bsdf.inputs:
            bsdf.inputs['Emission Color'].default_value = (0.0, 1.0, 0.0, 1.0)  # Pure green glow
        elif 'Emission' in bsdf.inputs:
            bsdf.inputs['Emission'].default_value = (0.0, 1.0, 0.0, 1.0)  # Pure green glow

        if 'Emission Strength' in bsdf.inputs:
            bsdf.inputs['Emission Strength'].default_value = 0.6  # Strong glow for visibility

    obj.data.materials.append(mat)
    obj.show_wire = True  # Show wireframe overlay for clarity

    return obj


def create_arrow(start: Vector, end: Vector, color: tuple, name: str = "PREVIEW_Arrow") -> bpy.types.Object:
    """
    Create arrow showing movement vector using curve object.

    Args:
        start: Start point (current position center)
        end: End point (proposed position center)
        color: RGB tuple (r, g, b)
        name: Object name

    Returns:
        Blender curve object
    """
    # Calculate distance to determine arrow thickness
    distance = (end - start).length
    thickness = max(0.05, distance * 0.02)  # 2% of distance, min 5cm

    # Create curve
    curve_data = bpy.data.curves.new(name=name, type='CURVE')
    curve_data.dimensions = '3D'
    curve_data.bevel_depth = thickness  # Arrow thickness

    # Create spline
    spline = curve_data.splines.new('POLY')
    spline.points.add(1)  # Need 2 points total (add 1 to default 1)

    spline.points[0].co = (start.x, start.y, start.z, 1)
    spline.points[1].co = (end.x, end.y, end.z, 1)

    # Create object
    obj = bpy.data.objects.new(name, curve_data)
    bpy.context.collection.objects.link(obj)

    # Material with emission for visibility
    mat = bpy.data.materials.new(name=f"{name}_Material")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs['Base Color'].default_value = color[:3] + (1.0,)

    # Handle different Blender versions (Emission vs Emission Color)
    if 'Emission Color' in bsdf.inputs:
        bsdf.inputs['Emission Color'].default_value = color[:3] + (1.0,)
        bsdf.inputs['Emission Strength'].default_value = 0.5
    elif 'Emission' in bsdf.inputs:
        bsdf.inputs['Emission'].default_value = color[:3] + (1.0,)
        bsdf.inputs['Emission Strength'].default_value = 0.5

    obj.data.materials.append(mat)

    return obj


def create_sphere(location: Vector, radius: float, color: tuple, name: str) -> bpy.types.Object:
    """
    Create clash point marker sphere.

    Args:
        location: 3D position for sphere
        radius: Sphere radius (typically 0.1-0.2 meters)
        color: RGBA tuple
        name: Object name (should start with "PREVIEW_")

    Returns:
        Blender sphere object
    """
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=location, segments=16, ring_count=8)
    obj = bpy.context.active_object
    obj.name = name

    # Material with transparency and slight glow
    mat = bpy.data.materials.new(name=f"{name}_Material")
    mat.use_nodes = True
    mat.blend_method = 'BLEND'

    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs['Base Color'].default_value = color[:3] + (1.0,)
    bsdf.inputs['Alpha'].default_value = color[3]

    # Blender 4.2 vs 4.5 compatibility
    if 'Emission Color' in bsdf.inputs:
        bsdf.inputs['Emission Color'].default_value = color[:3] + (1.0,)
    elif 'Emission' in bsdf.inputs:
        bsdf.inputs['Emission'].default_value = color[:3] + (1.0,)

    if 'Emission Strength' in bsdf.inputs:
        bsdf.inputs['Emission Strength'].default_value = 0.3  # Subtle glow

    obj.data.materials.append(mat)

    return obj


def create_wireframe_box(bbox: dict, color: tuple, name: str) -> bpy.types.Object:
    """
    Create wireframe bounding box for clearance zones.

    Args:
        bbox: Dict with min/max coordinates
        color: RGBA tuple
        name: Object name

    Returns:
        Blender wireframe object
    """
    # Create vertices for bbox corners
    vertices = [
        (bbox['minX'], bbox['minY'], bbox['minZ']),
        (bbox['maxX'], bbox['minY'], bbox['minZ']),
        (bbox['maxX'], bbox['maxY'], bbox['minZ']),
        (bbox['minX'], bbox['maxY'], bbox['minZ']),
        (bbox['minX'], bbox['minY'], bbox['maxZ']),
        (bbox['maxX'], bbox['minY'], bbox['maxZ']),
        (bbox['maxX'], bbox['maxY'], bbox['maxZ']),
        (bbox['minX'], bbox['maxY'], bbox['maxZ']),
    ]

    # Create edges for wireframe
    edges = [
        (0, 1), (1, 2), (2, 3), (3, 0),  # Bottom face
        (4, 5), (5, 6), (6, 7), (7, 4),  # Top face
        (0, 4), (1, 5), (2, 6), (3, 7),  # Vertical edges
    ]

    # Create mesh
    mesh = bpy.data.meshes.new(name=f"{name}_Mesh")
    mesh.from_pydata(vertices, edges, [])
    mesh.update()

    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)

    # Material
    mat = bpy.data.materials.new(name=f"{name}_Material")
    mat.use_nodes = True
    mat.blend_method = 'BLEND'

    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs['Base Color'].default_value = color[:3] + (1.0,)
    bsdf.inputs['Alpha'].default_value = color[3]

    obj.data.materials.append(mat)
    obj.display_type = 'WIRE'  # Force wireframe display

    return obj


def clear_preview_objects(keep_resolved: bool = False):
    """
    Remove all preview visualization objects from scene.

    Args:
        keep_resolved: If True, keep green "Proposed" box to show resolved state

    Deletes any object whose name starts with "PREVIEW_" or "RESOLVED_"
    """
    for obj in list(bpy.data.objects):
        if obj.name.startswith("PREVIEW_"):
            # If keep_resolved=True, preserve only the green proposed position box
            if keep_resolved and "Proposed" in obj.name:
                # Change to solid green (100% opaque) to indicate resolution applied
                if obj.data and obj.data.materials:
                    mat = obj.data.materials[0]
                    if mat.use_nodes:
                        bsdf = mat.node_tree.nodes.get("Principled BSDF")
                        if bsdf:
                            bsdf.inputs['Base Color'].default_value = (0.0, 1.0, 0.0, 1.0)  # PURE bright green
                            bsdf.inputs['Alpha'].default_value = 1.0  # Fully opaque

                            # Blender 4.2 vs 4.5 compatibility - BRIGHT GREEN for resolved state
                            if 'Emission Color' in bsdf.inputs:
                                bsdf.inputs['Emission Color'].default_value = (0.0, 1.0, 0.0, 1.0)
                            elif 'Emission' in bsdf.inputs:
                                bsdf.inputs['Emission'].default_value = (0.0, 1.0, 0.0, 1.0)

                            if 'Emission Strength' in bsdf.inputs:
                                bsdf.inputs['Emission Strength'].default_value = 0.8  # Very strong glow
                # Rename to indicate it's the resolved state
                obj.name = obj.name.replace("PREVIEW_", "RESOLVED_")
                continue  # Don't delete this one

            # Delete all other preview objects
            bpy.data.objects.remove(obj, do_unlink=True)

        # Also clear RESOLVED_ objects when user manually clears
        elif obj.name.startswith("RESOLVED_"):
            bpy.data.objects.remove(obj, do_unlink=True)


def zoom_to_objects(objects: List[bpy.types.Object]):
    """
    Zoom viewport to frame all specified objects.

    Args:
        objects: List of Blender objects to frame
    """
    if not objects:
        return

    # Deselect all
    bpy.ops.object.select_all(action='DESELECT')

    # Select preview objects
    for obj in objects:
        if obj and obj.name in bpy.data.objects:
            obj.select_set(True)

    # Frame selected in all 3D viewports
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for region in area.regions:
                if region.type == 'WINDOW':
                    with bpy.context.temp_override(area=area, region=region):
                        try:
                            bpy.ops.view3d.view_selected()
                        except Exception as e:
                            print(f"Warning: Could not zoom viewport: {e}")
                    break


def get_bbox_center(bbox: dict) -> Vector:
    """
    Calculate center point of bounding box.

    Args:
        bbox: Dict with min/max coordinates

    Returns:
        Center point as Vector
    """
    return Vector((
        (bbox['minX'] + bbox['maxX']) / 2,
        (bbox['minY'] + bbox['maxY']) / 2,
        (bbox['minZ'] + bbox['maxZ']) / 2
    ))


def apply_offset_to_bbox(bbox: dict, offset: List[float]) -> dict:
    """
    Apply XYZ offset to bounding box.

    Args:
        bbox: Original bbox
        offset: [dx, dy, dz] in meters

    Returns:
        New bbox with offset applied
    """
    return {
        'minX': bbox['minX'] + offset[0],
        'maxX': bbox['maxX'] + offset[0],
        'minY': bbox['minY'] + offset[1],
        'maxY': bbox['maxY'] + offset[1],
        'minZ': bbox['minZ'] + offset[2],
        'maxZ': bbox['maxZ'] + offset[2],
    }


def create_small_marker(location: Vector, color: tuple, name: str) -> bpy.types.Object:
    """
    Create small sphere marker for clashing elements.

    Args:
        location: 3D position
        color: RGBA tuple
        name: Object name

    Returns:
        Small sphere object (10cm radius)
    """
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.1, location=location, segments=8, ring_count=6)
    obj = bpy.context.active_object
    obj.name = name

    mat = bpy.data.materials.new(name=f"{name}_Material")
    mat.use_nodes = True
    mat.blend_method = 'BLEND'

    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs['Base Color'].default_value = color[:3] + (1.0,)
    bsdf.inputs['Alpha'].default_value = color[3]

    # Blender 4.2 vs 4.5 compatibility
    if 'Emission Color' in bsdf.inputs:
        bsdf.inputs['Emission Color'].default_value = color[:3] + (1.0,)
    elif 'Emission' in bsdf.inputs:
        bsdf.inputs['Emission'].default_value = color[:3] + (1.0,)

    if 'Emission Strength' in bsdf.inputs:
        bsdf.inputs['Emission Strength'].default_value = 0.5

    obj.data.materials.append(mat)

    return obj


def create_line(start: Vector, end: Vector, color: tuple, name: str) -> bpy.types.Object:
    """
    Create thin line connecting cascade element to clash.

    Args:
        start: Start point
        end: End point
        color: RGB tuple
        name: Object name

    Returns:
        Line curve object
    """
    curve_data = bpy.data.curves.new(name=name, type='CURVE')
    curve_data.dimensions = '3D'
    curve_data.bevel_depth = 0.02  # 2cm thickness

    spline = curve_data.splines.new('POLY')
    spline.points.add(1)
    spline.points[0].co = (start.x, start.y, start.z, 1)
    spline.points[1].co = (end.x, end.y, end.z, 1)

    obj = bpy.data.objects.new(name, curve_data)
    bpy.context.collection.objects.link(obj)

    mat = bpy.data.materials.new(name=f"{name}_Material")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs['Base Color'].default_value = color[:3] + (1.0,)
    bsdf.inputs['Alpha'].default_value = 0.5
    mat.blend_method = 'BLEND'

    obj.data.materials.append(mat)

    return obj


def create_resolution_preview(bbox: dict, offset: List[float],
                             clash_points: List[Vector] = None,
                             coordinate_offset: Vector = None,
                             clashing_elements: List[Dict] = None) -> Dict[str, bpy.types.Object]:
    """
    Create complete resolution preview visualization.

    This is the main entry point for creating preview geometry.

    Args:
        bbox: Original element bounding box
        offset: [dx, dy, dz] proposed movement
        clash_points: Optional list of clash locations to highlight
        coordinate_offset: Optional global coordinate offset (for GPS coords)
        clashing_elements: Optional list of dicts with 'bbox' and 'discipline' for each clashing element

    Returns:
        Dict mapping object names to created objects
    """
    created_objects = {}

    # Clear any existing preview
    clear_preview_objects()

    # Apply coordinate offset if provided
    coord_offset = coordinate_offset if coordinate_offset else Vector((0, 0, 0))

    # 1. Create current position ghost (RED, 50% transparent)
    ghost_current = create_ghost_box(
        bbox,
        color=(1.0, 0.2, 0.2, 0.5),  # Red, 50% transparent
        name="PREVIEW_Current",
        offset=coord_offset
    )
    created_objects['current'] = ghost_current

    # 2. Create proposed position ghost (BRIGHT GREEN, highly visible)
    new_bbox = apply_offset_to_bbox(bbox, offset)
    ghost_proposed = create_ghost_box(
        new_bbox,
        color=(0.0, 1.0, 0.0, 0.8),  # Pure bright green, 80% opaque
        name="PREVIEW_Proposed",
        offset=coord_offset
    )
    created_objects['proposed'] = ghost_proposed

    # 3. Movement arrow REMOVED - user found it confusing
    # (Arrow was yellow line showing direction - not needed with red→green visual)

    # 4. Create clash point markers (CYAN spheres, 70% transparent)
    if clash_points:
        for i, point in enumerate(clash_points):
            point_with_offset = point + coord_offset
            sphere = create_sphere(
                point_with_offset,
                radius=0.15,  # 15cm radius
                color=(0.0, 1.0, 1.0, 0.7),  # Cyan, 70% opacity
                name=f"PREVIEW_Clash_{i}"
            )
            created_objects[f'clash_{i}'] = sphere

    # 5. Show all affected clashing elements (orange spheres only, no connecting lines)
    if clashing_elements:
        # Discipline color mapping (orange tones for affected elements)
        discipline_colors = {
            'ARC': (1.0, 0.6, 0.2, 0.8),  # Orange
            'STR': (1.0, 0.4, 0.0, 0.8),  # Deep orange
            'MEP': (1.0, 0.8, 0.0, 0.8),  # Yellow-orange
            'ELEC': (1.0, 0.7, 0.3, 0.8), # Light orange
            'PP': (0.9, 0.5, 0.1, 0.8),   # Brown-orange
            'FP': (1.0, 0.3, 0.0, 0.8),   # Red-orange
        }
        default_color = (1.0, 0.65, 0.0, 0.8)  # Standard orange

        for i, elem in enumerate(clashing_elements):
            elem_bbox = elem['bbox']
            elem_discipline = elem.get('discipline', 'UNKNOWN')
            color = discipline_colors.get(elem_discipline, default_color)

            # Get center of clashing element
            elem_center = Vector((
                (elem_bbox['minX'] + elem_bbox['maxX']) / 2,
                (elem_bbox['minY'] + elem_bbox['maxY']) / 2,
                (elem_bbox['minZ'] + elem_bbox['maxZ']) / 2
            )) + coord_offset

            # Create small marker sphere (orange to show affected elements)
            marker = create_small_marker(
                elem_center,
                color,
                name=f"PREVIEW_ClashElement_{i}"
            )
            created_objects[f'clash_elem_{i}'] = marker

    # 6. Zoom viewport to show both positions
    zoom_to_objects([ghost_current, ghost_proposed])

    return created_objects


if __name__ == "__main__":
    """
    Test visualization with sample data
    """
    print("Testing 3D visualization...")

    # Clear any existing previews
    clear_preview_objects()

    # Sample bbox (10m cube at origin)
    test_bbox = {
        'minX': 0.0, 'maxX': 10.0,
        'minY': 0.0, 'maxY': 10.0,
        'minZ': 0.0, 'maxZ': 10.0,
    }

    # Sample offset (move 5m in +X, 3m in +Z)
    test_offset = [5.0, 0.0, 3.0]

    # Sample clash points
    test_clash_points = [
        Vector((8.0, 5.0, 5.0)),
        Vector((9.0, 6.0, 7.0)),
        Vector((7.0, 4.0, 6.0)),
    ]

    # Create preview
    objects = create_resolution_preview(test_bbox, test_offset, test_clash_points)

    print(f"✓ Created {len(objects)} preview objects:")
    for name, obj in objects.items():
        print(f"  - {name}: {obj.name}")

    print("\nPreview visualization complete. Check 3D viewport.")
