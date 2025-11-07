"""
Instant Object Highlighting for Clash Resolution Preview
=========================================================

POC: Instead of creating new objects, just highlight existing ones.

Benefits:
- INSTANT (no object creation)
- No GPU instancing needed
- Shows actual geometry (not just boxes)
- Leverages whatever user already loaded (bbox/solid/full)

Approach:
1. Find existing objects by GUID
2. Change their viewport color + material
3. Store original colors for restoration
4. On Clear → restore originals
"""

import bpy
from mathutils import Vector
from typing import List, Dict, Optional, Tuple


def get_or_create_preview_collection() -> bpy.types.Collection:
    """
    Get or create 'Clash_Preview' collection for Outliner organization.

    Returns:
        Collection for preview objects
    """
    coll_name = "Clash_Preview"

    if coll_name in bpy.data.collections:
        return bpy.data.collections[coll_name]

    # Create new collection
    preview_coll = bpy.data.collections.new(coll_name)
    bpy.context.scene.collection.children.link(preview_coll)

    return preview_coll


def find_object_by_guid(guid: str) -> Optional[bpy.types.Object]:
    """
    Find object in scene by GUID.

    Checks multiple possible storage locations:
    - obj.name == guid
    - obj['federation_guid'] == guid
    - obj.get('guid') == guid (Bonsai IFC objects)
    """
    print(f"  🔍 Searching for GUID: {guid}")
    found_objects = []

    for obj in bpy.data.objects:
        # Check direct name match
        if obj.name == guid:
            print(f"    ✓ Found by name: {obj.name}")
            return obj

        # Check custom properties
        if obj.get('federation_guid') == guid:
            print(f"    ✓ Found by federation_guid: {obj.name}")
            return obj

        if obj.get('guid') == guid:
            print(f"    ✓ Found by guid property: {obj.name}")
            return obj

        # Debug: Collect objects that have federation_guid for diagnostics
        if obj.get('federation_guid'):
            found_objects.append((obj.name, obj.get('federation_guid')))

    # Debug: Show what GUIDs are available
    print(f"    ✗ Not found! Available GUIDs in scene: {len(found_objects)}")
    if found_objects and len(found_objects) < 10:
        for name, obj_guid in found_objects[:5]:
            print(f"      - {name}: {obj_guid}")

    return None


def store_original_appearance(obj: bpy.types.Object):
    """
    Store original appearance before highlighting.
    Stores in custom properties for later restoration.
    """
    # Store viewport color
    obj["CLASH_ORIGINAL_COLOR"] = tuple(obj.color)

    # Store material
    if obj.active_material:
        obj["CLASH_ORIGINAL_MATERIAL"] = obj.active_material.name
    else:
        obj["CLASH_ORIGINAL_MATERIAL"] = None

    # Store visibility flags
    obj["CLASH_ORIGINAL_HIDE_RENDER"] = obj.hide_render
    obj["CLASH_ORIGINAL_HIDE_VIEWPORT"] = obj.hide_viewport


def restore_original_appearance(obj: bpy.types.Object):
    """Restore object's original appearance."""
    if "CLASH_ORIGINAL_COLOR" in obj:
        obj.color = obj["CLASH_ORIGINAL_COLOR"]
        del obj["CLASH_ORIGINAL_COLOR"]

    if "CLASH_ORIGINAL_MATERIAL" in obj:
        mat_name = obj["CLASH_ORIGINAL_MATERIAL"]
        if mat_name and mat_name in bpy.data.materials:
            obj.active_material = bpy.data.materials[mat_name]
        del obj["CLASH_ORIGINAL_MATERIAL"]

    if "CLASH_ORIGINAL_HIDE_RENDER" in obj:
        obj.hide_render = obj["CLASH_ORIGINAL_HIDE_RENDER"]
        del obj["CLASH_ORIGINAL_HIDE_RENDER"]

    if "CLASH_ORIGINAL_HIDE_VIEWPORT" in obj:
        obj.hide_viewport = obj["CLASH_ORIGINAL_HIDE_VIEWPORT"]
        del obj["CLASH_ORIGINAL_HIDE_VIEWPORT"]


def get_or_create_highlight_material(name: str, color: Tuple[float, float, float, float]) -> bpy.types.Material:
    """
    Get or create a highlight material for clash visualization.

    Works in ALL viewport shading modes:
    - Solid: Uses diffuse color
    - Material Preview: Uses emission for glow
    - Rendered: Full shader
    """
    mat_name = f"CLASH_HIGHLIGHT_{name}"
    mat = bpy.data.materials.get(mat_name)

    if not mat:
        mat = bpy.data.materials.new(mat_name)
        mat.use_nodes = True
        mat.blend_method = 'BLEND'

        # Set diffuse color for Solid mode
        mat.diffuse_color = color

        # Setup nodes for Material Preview mode
        nodes = mat.node_tree.nodes
        bsdf = nodes.get("Principled BSDF")

        if bsdf:
            bsdf.inputs['Base Color'].default_value = color
            bsdf.inputs['Alpha'].default_value = color[3]

            # Add emission for better visibility
            if 'Emission Color' in bsdf.inputs:
                bsdf.inputs['Emission Color'].default_value = color
                bsdf.inputs['Emission Strength'].default_value = 0.3
            elif 'Emission' in bsdf.inputs:
                bsdf.inputs['Emission'].default_value = color
                bsdf.inputs['Emission Strength'].default_value = 0.3

    return mat


def highlight_object(obj: bpy.types.Object, color: Tuple[float, float, float, float], label: str):
    """
    Highlight object with color (works in all viewport modes).

    Args:
        obj: Object to highlight
        color: RGBA color tuple
        label: Label for tracking (e.g., "current", "proposed", "clash")
    """
    # Store original appearance first
    store_original_appearance(obj)

    # Set viewport color (works in Solid mode)
    obj.color = color

    # Create/assign highlight material (works in Material Preview mode)
    mat = get_or_create_highlight_material(label, color)
    obj.active_material = mat

    # Mark as highlighted for tracking
    obj["CLASH_HIGHLIGHTED"] = label

    # Make sure it's visible
    obj.hide_viewport = False
    obj.hide_render = False

    # Select it
    obj.select_set(True)


def highlight_cascade_element(
    cascade_guid: str,
    offset: List[float],
    color_current: Tuple[float, float, float, float] = (1.0, 0.0, 0.0, 0.8),
    color_proposed: Tuple[float, float, float, float] = (0.0, 1.0, 0.0, 0.8)
) -> Dict[str, bpy.types.Object]:
    """
    Highlight cascade element showing current (red) and proposed (green) positions.

    Strategy:
    1. Find existing object
    2. Highlight it red (current position)
    3. Duplicate it and move to proposed position (green)

    Args:
        cascade_guid: GUID of cascade element
        offset: [dx, dy, dz] movement offset
        color_current: Red color for current position
        color_proposed: Green color for proposed position

    Returns:
        Dict with 'current' and 'proposed' objects
    """
    result = {}

    # Find cascade element
    cascade_obj = find_object_by_guid(cascade_guid)

    if not cascade_obj:
        print(f"⚠️  Cascade element {cascade_guid} not found in scene")
        return result

    # Highlight current position (RED)
    highlight_object(cascade_obj, color_current, "current")
    result['current'] = cascade_obj

    # Duplicate for proposed position (GREEN)
    proposed_obj = cascade_obj.copy()
    if cascade_obj.data:
        proposed_obj.data = cascade_obj.data.copy()

    proposed_obj.name = f"PREVIEW_Proposed_{cascade_guid[:8]}"

    # Link to scene (add to special preview collection for Outliner organization)
    preview_collection = get_or_create_preview_collection()
    preview_collection.objects.link(proposed_obj)

    # Move to proposed position
    proposed_obj.location += Vector(offset)

    # Match original's display type (solid, not wireframe)
    proposed_obj.display_type = cascade_obj.display_type

    # Highlight green
    highlight_object(proposed_obj, color_proposed, "proposed")
    result['proposed'] = proposed_obj

    # No wireframe overlay - green color is clear enough

    return result


def highlight_clashing_elements(
    clashing_guids: List[str],
    color: Tuple[float, float, float, float] = (1.0, 0.5, 0.0, 0.9)
) -> List[bpy.types.Object]:
    """
    Highlight all clashing elements (orange).

    Args:
        clashing_guids: List of GUIDs for clashing elements
        color: Orange color for clashing elements

    Returns:
        List of highlighted objects
    """
    highlighted = []

    for guid in clashing_guids:
        obj = find_object_by_guid(guid)

        if obj:
            highlight_object(obj, color, "clash")
            highlighted.append(obj)
        else:
            print(f"⚠️  Clashing element {guid} not found in scene")

    return highlighted


def clear_all_highlights():
    """
    Clear all clash highlights and restore original appearance.
    """
    for obj in bpy.data.objects:
        # Restore highlighted objects
        if "CLASH_HIGHLIGHTED" in obj:
            restore_original_appearance(obj)
            obj.select_set(False)
            del obj["CLASH_HIGHLIGHTED"]

        # Remove duplicated proposed objects
        if obj.name.startswith("PREVIEW_Proposed_"):
            bpy.data.objects.remove(obj, do_unlink=True)

    # Remove preview collection from Outliner
    if "Clash_Preview" in bpy.data.collections:
        coll = bpy.data.collections["Clash_Preview"]
        bpy.data.collections.remove(coll)


def apply_resolution_highlights():
    """
    Convert preview highlights to "applied" state:
    - Restore current (red) element to original appearance
    - Keep proposed (green) element, make it solid and opaque
    - Restore clashing (orange) elements to original appearance

    This shows user: "Resolution applied, green shows new position"
    """
    for obj in bpy.data.objects:
        if "CLASH_HIGHLIGHTED" not in obj:
            continue

        label = obj["CLASH_HIGHLIGHTED"]

        if label == "current":
            # Restore original element
            restore_original_appearance(obj)
            obj.select_set(False)
            del obj["CLASH_HIGHLIGHTED"]

        elif label == "proposed":
            # Keep proposed element but make it solid/opaque (resolved state)
            # Change to solid bright green (no transparency)
            obj.color = (0.0, 1.0, 0.0, 1.0)

            # Update material to solid green
            mat = get_or_create_highlight_material("resolved", (0.0, 1.0, 0.0, 1.0))
            obj.active_material = mat

            # Change label to indicate it's now "resolved"
            obj["CLASH_HIGHLIGHTED"] = "resolved"

        elif label == "clash":
            # Restore clashing elements
            restore_original_appearance(obj)
            obj.select_set(False)
            del obj["CLASH_HIGHLIGHTED"]


def highlight_resolution_preview(
    cascade_guid: str,
    offset: List[float],
    clashing_guids: List[str]
) -> Dict:
    """
    Main entry point: Highlight clash resolution preview.

    INSTANT approach:
    - No object creation (except one duplicate for proposed)
    - Just color existing objects
    - Works with whatever user loaded (bbox/solid/full)

    Args:
        cascade_guid: Cascade element GUID
        offset: [dx, dy, dz] movement offset
        clashing_guids: List of clashing element GUIDs

    Returns:
        Dict with 'current', 'proposed', and 'clashing' objects
    """
    result = {}

    print(f"\n=== INSTANT HIGHLIGHT POC ===")
    print(f"Cascade element: {cascade_guid}")
    print(f"Movement offset: {offset}")
    print(f"Clashing elements: {len(clashing_guids)}")

    # Clear any previous highlights
    clear_all_highlights()

    # Deselect all first
    bpy.ops.object.select_all(action='DESELECT')

    # Highlight cascade element (red + green)
    cascade_result = highlight_cascade_element(cascade_guid, offset)
    result.update(cascade_result)

    # Highlight clashing elements (orange)
    clashing_objs = highlight_clashing_elements(clashing_guids)
    result['clashing'] = clashing_objs

    print(f"Highlighted: {len(result)} object groups")
    print(f"  Current: {'✓' if 'current' in result else '✗'}")
    print(f"  Proposed: {'✓' if 'proposed' in result else '✗'}")
    print(f"  Clashing: {len(clashing_objs)} elements")
    print("="*30 + "\n")

    # Zoom to highlighted objects
    all_objs = [result.get('current'), result.get('proposed')] + clashing_objs
    all_objs = [obj for obj in all_objs if obj]

    if all_objs:
        for obj in all_objs:
            obj.select_set(True)

        # Zoom to selection
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        with bpy.context.temp_override(area=area, region=region):
                            try:
                                bpy.ops.view3d.view_selected()
                                break
                            except Exception as e:
                                print(f"Could not zoom viewport: {e}")
                break

    return result
