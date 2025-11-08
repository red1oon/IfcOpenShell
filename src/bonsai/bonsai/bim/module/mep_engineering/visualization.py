# ============================================================================
# FILE: src/bonsai/bonsai/bim/module/mep_engineering/visualization.py
# PURPOSE: Visual debugging tools for MEP conduit routing
# ============================================================================
# 
# This module creates temporary Blender objects to visualize:
# - Start/end points (colored spheres)
# - Obstacle bounding boxes (semi-transparent cubes)
# - Clearance zones (wireframe boxes)
# 
# All objects are prefixed with "MEP Debug" for easy cleanup.
# Does not modify Bonsai core - uses standard Blender API only.
# ============================================================================

import bpy
import bmesh
from mathutils import Vector
from typing import List, Tuple, Optional


def _get_or_create_debug_collection():
    """Get or create the MEP Debug collection to organize all debug objects"""
    collection_name = "MEP_Debug"
    if collection_name not in bpy.data.collections:
        collection = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(collection)
    else:
        collection = bpy.data.collections[collection_name]
    return collection


def create_debug_sphere(
    location: Tuple[float, float, float],
    radius: float,
    color: Tuple[float, float, float, float],
    name: str
) -> bpy.types.Object:
    """
    Create a colored sphere at specified location

    Args:
        location: (x, y, z) position in meters
        radius: Sphere radius in meters
        color: (r, g, b, a) color with alpha (0-1 range)
        name: Object name (will be prefixed with "MEP Debug ")

    Returns:
        Created Blender object
    """
    # Create sphere mesh
    mesh = bpy.data.meshes.new(f"MEP Debug {name}")
    obj = bpy.data.objects.new(f"MEP Debug {name}", mesh)

    # Link to MEP Debug collection (keeps Outliner organized)
    collection = _get_or_create_debug_collection()
    collection.objects.link(obj)
    
    # Generate sphere geometry using bmesh
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=radius)
    bm.to_mesh(mesh)
    bm.free()
    
    # Set location
    obj.location = location
    
    # Create and assign material
    mat = bpy.data.materials.new(name=f"MEP Debug Material {name}")
    mat.diffuse_color = color
    mat.use_nodes = False  # Simple material
    
    if color[3] < 1.0:  # Has transparency
        mat.blend_method = 'OPAQUE'
        mat.show_transparent_back = False
    
    obj.data.materials.append(mat)
    
    return obj


def create_obstacle_box(
    bbox: Tuple[float, float, float, float, float, float],
    color: Tuple[float, float, float, float],
    name: str,
    wireframe: bool = False
) -> bpy.types.Object:
    """
    Create a box representing an obstacle's bounding box
    
    Args:
        bbox: (min_x, min_y, min_z, max_x, max_y, max_z) in meters
        color: (r, g, b, a) color with alpha
        name: Object name (will be prefixed with "MEP Debug ")
        wireframe: If True, display as wireframe only
        
    Returns:
        Created Blender object
    """
    min_x, min_y, min_z, max_x, max_y, max_z = bbox
    
    # Calculate dimensions and center
    width = max_x - min_x
    depth = max_y - min_y
    height = max_z - min_z
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    center_z = (min_z + max_z) / 2
    
    # Create cube mesh
    mesh = bpy.data.meshes.new(f"MEP Debug {name}")
    obj = bpy.data.objects.new(f"MEP Debug {name}", mesh)

    # Link to MEP Debug collection (keeps Outliner organized)
    collection = _get_or_create_debug_collection()
    collection.objects.link(obj)
    
    # Generate cube geometry
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(mesh)
    bm.free()
    
    # Position and scale
    obj.location = (center_x, center_y, center_z)
    obj.scale = (width / 2, depth / 2, height / 2)
    
    # Create and assign material
    # Create and assign material with emission
    mat = bpy.data.materials.new(name=f"MEP Debug Material {name}")
    mat.use_nodes = True  # Enable nodes for emission
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Clear default nodes
    nodes.clear()

    # Add shader nodes
    output = nodes.new('ShaderNodeOutputMaterial')
    emission = nodes.new('ShaderNodeEmission')

    # Set emission color and strength
    emission.inputs['Color'].default_value = color
    emission.inputs['Strength'].default_value = 5.0  # Bright glow

    # Connect emission to output
    links.new(emission.outputs['Emission'], output.inputs['Surface'])
    
    if color[3] < 1.0 or wireframe:  # Transparent or wireframe
        mat.blend_method = 'OPAQUE'
        mat.show_transparent_back = False
    
    obj.data.materials.append(mat)
    
    # Set display mode
    if wireframe:
        obj.display_type = 'WIRE'
    
    return obj


def create_clearance_zone(
    bbox: Tuple[float, float, float, float, float, float],
    clearance: float,
    name: str
) -> bpy.types.Object:
    """
    Create a wireframe box showing clearance zone around obstacle
    ...
    """
    # Expand bbox by clearance (XY only, not Z - electrical fixtures don't need vertical clearance)
    expanded_bbox = (
        bbox[0] - clearance,  # min_x - inflate
        bbox[1] - clearance,  # min_y - inflate
        bbox[2],              # min_z - DON'T inflate
        bbox[3] + clearance,  # max_x - inflate
        bbox[4] + clearance,  # max_y - inflate
        bbox[5]               # max_z - DON'T inflate
    )
    
    # Yellow wireframe for clearance zones
    yellow_color = (1.0, 1.0, 0.0, 0.3)
    
    return create_obstacle_box(
        expanded_bbox,
        yellow_color,
        f"Clearance {name}",
        wireframe=True
    )


def create_corridor_visualization(
    start: Tuple[float, float, float],
    end: Tuple[float, float, float],
    buffer: float
) -> bpy.types.Object:
    """
    Create a box showing the routing corridor search space
    
    Args:
        start: Start point (x, y, z)
        end: End point (x, y, z)
        buffer: Corridor buffer distance in meters
        
    Returns:
        Created Blender object
    """
    # Calculate corridor bounding box
    min_x = min(start[0], end[0]) - buffer
    max_x = max(start[0], end[0]) + buffer
    min_y = min(start[1], end[1]) - buffer
    max_y = max(start[1], end[1]) + buffer
    min_z = min(start[2], end[2]) - buffer
    max_z = max(start[2], end[2]) + buffer
    
    corridor_bbox = (min_x, min_y, min_z, max_x, max_y, max_z)
    
    # Cyan wireframe for corridor
    cyan_color = (0.0, 1.0, 1.0, 0.2)
    
    return create_obstacle_box(
        corridor_bbox,
        cyan_color,
        "Corridor",
        wireframe=True
    )

def clear_debug_objects():
    """
    Remove all MEP debug visualization objects from the scene
    OPTIMIZED: Batch deletion with view layer override to prevent UI updates
    """
    import time
    start_time = time.time()

    # Collect all objects to remove
    objects_to_remove = []

    # FAST PATH: If using collection, get all objects from it
    collection_name = "MEP_Debug"
    if collection_name in bpy.data.collections:
        collection = bpy.data.collections[collection_name]
        objects_to_remove.extend(list(collection.objects))

    # FALLBACK: Add any stray objects not in collection (legacy cleanup)
    for obj in bpy.data.objects:
        if obj.name.startswith("MEP Debug") and obj not in objects_to_remove:
            objects_to_remove.append(obj)

    if not objects_to_remove:
        print("✓ No debug objects to clear")
        return

    count = len(objects_to_remove)

    # OPTIMIZATION: Use data API batch removal (avoids operator overhead)
    # Remove objects with do_unlink=True
    with bpy.context.temp_override():
        for obj in objects_to_remove:
            bpy.data.objects.remove(obj, do_unlink=True)

    # Remove collection if it exists
    if collection_name in bpy.data.collections:
        bpy.data.collections.remove(bpy.data.collections[collection_name])

    # Batch purge orphaned data (very fast - no depsgraph involvement)
    for mesh in bpy.data.meshes:
        if mesh.name.startswith("MEP Debug") and mesh.users == 0:
            bpy.data.meshes.remove(mesh)

    for material in bpy.data.materials:
        if material.name.startswith("MEP Debug") and material.users == 0:
            bpy.data.materials.remove(material)

    for curve in bpy.data.curves:
        if "MEP Debug" in curve.name and curve.users == 0:
            bpy.data.curves.remove(curve)

    elapsed = time.time() - start_time
    print(f"✓ Cleared {count} debug objects in {elapsed:.3f}s")

def navigate_to_view() -> bool:
    """
    Smoothly animate viewport to focus on currently selected objects with X-ray mode
    """
    import bpy
    
    # FIRST: Trigger the animation BEFORE changing anything
    success = False
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for region in area.regions:
                if region.type == 'WINDOW':
                    override = {'area': area, 'region': region}
                    with bpy.context.temp_override(**override):
                        bpy.ops.view3d.view_selected('INVOKE_DEFAULT', use_all_regions=False)
                    success = True
                    print(f"🎬 Viewport animated to selection")
                    break
            break
    
    # THEN: Enable X-ray mode (doesn't interrupt animation)
    if success:
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                if space.type == 'VIEW_3D':
                    if not space.shading.show_xray:
                        bpy.context.scene["MEP_saved_xray_alpha"] = -1.0
                    else:
                        bpy.context.scene["MEP_saved_xray_alpha"] = space.shading.xray_alpha
                    
                    space.shading.show_xray = True
                    space.shading.xray_alpha = 0.3
                    print(f"✅ X-ray mode: ON (30% opacity)")
                    break
    
    return success

def focus_on_obstacles() -> bool:
    """
    Select all MEP debug obstacle objects for viewport focus
    
    Returns:
        True if objects selected successfully
    """
    import bpy
    
    # Deselect everything
    bpy.ops.object.select_all(action='DESELECT')
    
    # Select all MEP Debug objects
    selected_count = 0
    for obj in bpy.data.objects:
        if obj.name.startswith("MEP Debug"):
            obj.select_set(True)
            selected_count += 1
            
            # Set first as active
            if selected_count == 1:
                bpy.context.view_layer.objects.active = obj
    
    print(f"✅ Selected {selected_count} debug objects")
    return selected_count > 0

def focus_on_path() -> bool:
    """
    Focus viewport on IFC conduit segments
    Selects only the newly created conduit route
    
    Returns:
        True if successful, False if no conduit found
    """
    import bpy
    
    # Retrieve stored conduit element IDs (created in last routing operation)
    if "MEP_last_conduit_ids" not in bpy.context.scene:
        print("✗ No conduit IDs found - route conduit first")
        return False
    
    import json
    conduit_ids = json.loads(bpy.context.scene["MEP_last_conduit_ids"])
    
    if not conduit_ids:
        print("✗ No conduit elements stored")
        return False
    
    # Find objects matching the stored GlobalIds
    conduit_objects = []
    for obj in bpy.data.objects:
        # Check if object has IFC data with matching GlobalId
        if hasattr(obj, 'BIMObjectProperties'):
            ifc_definition_id = obj.BIMObjectProperties.ifc_definition_id
            if ifc_definition_id:
                # Get IFC element
                import bonsai.tool as tool
                ifc_file = tool.Ifc.get()
                if ifc_file:
                    try:
                        element = ifc_file.by_id(ifc_definition_id)
                        if hasattr(element, 'GlobalId') and element.GlobalId in conduit_ids:
                            conduit_objects.append(obj)
                    except:
                        pass
    
    if not conduit_objects:
        print(f"✗ No Blender objects found for {len(conduit_ids)} conduit IDs")
        return False
    
    # Deselect everything
    bpy.ops.object.select_all(action='DESELECT')
    
    # Select only the new conduit objects
    for obj in conduit_objects:
        obj.select_set(True)
    
    # Set first as active
    bpy.context.view_layer.objects.active = conduit_objects[0]
    
    # Hide MEP debug obstacles (keep start/end spheres)
    for obj in bpy.data.objects:
        if obj.name.startswith("MEP Debug"):
            if "Start Point" not in obj.name and "End Point" not in obj.name:
                obj.hide_set(True)
     
    print(f"✅ Focused on {len(conduit_objects)} conduit elements")
    
    # NOW ANIMATE VIEWPORT TO SELECTED CONDUITS
    navigate_to_view()  # This will animate to the selected conduits
    return True

def visualize_routing_scenario(
    start: Tuple[float, float, float],
    end: Tuple[float, float, float],
    obstacles: List[Tuple[float, float, float, float, float, float]],
    clearance: float,
    waypoints: Optional[List[Tuple[float, float, float]]] = None,
    show_clearance_zones: bool = True,
    show_corridor: bool = True
) -> dict:
    """
    Complete visualization of a routing scenario
    
    Args:
        start: Start point (x, y, z) in IFC coordinates
        end: End point (x, y, z) in IFC coordinates
        obstacles: List of obstacle bboxes (min_x, min_y, min_z, max_x, max_y, max_z)
        clearance: Clearance distance in meters
        waypoints: Optional list of route waypoints
        show_clearance_zones: Show clearance zones around obstacles
        show_corridor: Show routing corridor
        
    Returns:
        Dictionary of created Blender objects
    """
    # Use cached offset from routing operator
    import bpy
    cached = bpy.context.scene.get("MEP_cached_offset")
    if cached:
        offset_x, offset_y, offset_z = cached
        print(f"📍 Using cached offset: ({offset_x:.1f}, {offset_y:.1f}, {offset_z:.1f})")
    else:
        offset_x = offset_y = offset_z = 0.0
        print(f"⚠️  No cached offset found")    
    # Apply offset to all coordinates (currently zero)
    start = (start[0] - offset_x, start[1] - offset_y, start[2] - offset_z)
    end = (end[0] - offset_x, end[1] - offset_y, end[2] - offset_z)
    
    # Apply offset to obstacles
    offset_obstacles = []
    for bbox in obstacles:
        offset_bbox = (
            bbox[0] - offset_x, bbox[1] - offset_y, bbox[2] - offset_z,
            bbox[3] - offset_x, bbox[4] - offset_y, bbox[5] - offset_z
        )
        offset_obstacles.append(offset_bbox)
    
    obstacles = offset_obstacles
    
    # Rest of function continues as before...
    created_objects = {}
    
    # Start point (green sphere)
    created_objects['start'] = create_debug_sphere(
        start,
        radius=0.5,
        color=(0.0, 1.0, 0.0, 1.0),  # Green
        name="Start Point"
    )
    
    # End point (red sphere)
    created_objects['end'] = create_debug_sphere(
        end,
        radius=0.5,
        color=(1.0, 0.0, 0.0, 1.0),  # Red
        name="End Point"
    )
    
    # Corridor (optional)
    if show_corridor:
        buffer = clearance * 3  # Corridor is wider than clearance
        created_objects['corridor'] = create_corridor_visualization(
            start, end, buffer
        )
    
    # Obstacles and clearance zones
    created_objects['obstacles'] = []
    created_objects['clearances'] = []
    
    for i, bbox in enumerate(obstacles):
        # Obstacle box (semi-transparent red)
        obs_obj = create_obstacle_box(
            bbox,
            color=(1.0, 0.0, 0.0, 0.3),  # Red, 30% opacity
            name=f"Obstacle {i+1}",
            wireframe=True
        )
        created_objects['obstacles'].append(obs_obj)
        
        # Clearance zone (optional, yellow wireframe)
        if show_clearance_zones:
            clear_obj = create_clearance_zone(
                bbox,
                clearance,
                name=f"{i+1}"
            )
            created_objects['clearances'].append(clear_obj)
    
    # Waypoint path visualization (NEW!)
    if waypoints and len(waypoints) > 1:
        # Apply offset to waypoints
        offset_waypoints = []
        for wp in waypoints:
            offset_wp = (wp[0] - offset_x, wp[1] - offset_y, wp[2] - offset_z)
            offset_waypoints.append(offset_wp)

        # Create curve object for the path
        import bpy
        curve_data = bpy.data.curves.new(name="MEP Debug Path", type='CURVE')
        curve_data.dimensions = '3D'
        curve_data.resolution_u = 2

        # Create polyline from waypoints
        polyline = curve_data.splines.new('POLY')
        polyline.points.add(len(offset_waypoints) - 1)  # -1 because spline has 1 point by default

        for i, point in enumerate(offset_waypoints):
            x, y, z = point
            polyline.points[i].co = (x, y, z, 1.0)  # homogeneous coordinates

        # Create object from curve
        path_obj = bpy.data.objects.new("MEP Debug Path", curve_data)
        collection = _get_or_create_debug_collection()
        collection.objects.link(path_obj)

        # Set material (bright cyan for visibility)
        mat = bpy.data.materials.new(name="MEP Debug Path Material")
        mat.diffuse_color = (0.0, 1.0, 1.0, 1.0)  # Cyan
        mat.use_nodes = False
        path_obj.data.materials.append(mat)

        # Make it thick enough to see
        curve_data.bevel_depth = 0.05  # 5cm diameter tube
        curve_data.bevel_resolution = 4

        created_objects['path'] = path_obj
        print(f"  - Path: {len(waypoints)} waypoints (cyan tube)")

    print(f"✓ Visualization created:")
    print(f"  - Start/End points: 2 spheres")
    print(f"  - Obstacles: {len(obstacles)} boxes")
    if show_clearance_zones:
        print(f"  - Clearance zones: {len(obstacles)} wireframes")
    if show_corridor:
        print(f"  - Corridor: 1 wireframe box")

    return created_objects