"""
Federation Visualization Helper
================================

Helper functions to visualize elements from federation database without IFC files.

Replaces IFC-based visualization with database-driven procedural shapes.
"""

import bpy
import bmesh
from mathutils import Vector, Euler
from typing import Optional, Tuple
import sqlite3


def find_or_create_element_from_database(
    guid: str,
    db_path: str,
    collection: bpy.types.Collection
) -> Optional[bpy.types.Object]:
    """
    Find element in scene or create from database (NO IFC NEEDED!).

    Workflow:
    1. Check if object already exists in scene (Stage 2 loading)
    2. If not, query database for element metadata
    3. Create procedural shape from database bbox
    4. Return Blender object ready for visualization

    Args:
        guid: Element GUID to find/create
        db_path: Path to federation database
        collection: Collection to add object to (if creating)

    Returns:
        Blender object, or None if element not found in database
    """
    # Step 1: Check if element already loaded in scene
    for obj in bpy.data.objects:
        if obj.get('federation_guid') == guid or obj.name == guid:
            return obj

    # Step 2: Element not in scene - create from database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Query element metadata and bbox
        cursor.execute("""
            SELECT
                m.guid, m.ifc_class, m.discipline,
                r.min_x, r.min_y, r.min_z,
                r.max_x, r.max_y, r.max_z
            FROM elements_meta m
            JOIN elements_rtree r ON m.id = r.id
            WHERE m.guid = ?
        """, (guid,))

        result = cursor.fetchone()

        if not result:
            print(f"⚠ Element {guid} not found in database")
            return None

        guid, ifc_class, discipline, min_x, min_y, min_z, max_x, max_y, max_z = result

        # Step 3: Create procedural shape from bbox
        obj = create_procedural_shape_from_bbox(
            guid=guid,
            ifc_class=ifc_class,
            discipline=discipline,
            bbox=(min_x, min_y, min_z, max_x, max_y, max_z),
            collection=collection
        )

        return obj

    finally:
        conn.close()


def create_procedural_shape_from_bbox(
    guid: str,
    ifc_class: str,
    discipline: str,
    bbox: Tuple[float, float, float, float, float, float],
    collection: bpy.types.Collection
) -> bpy.types.Object:
    """
    Create simple procedural shape from bounding box.

    Fast visualization for clash/routing views.
    Uses semantic inference to create appropriate shape.

    Args:
        guid: Element GUID
        ifc_class: IFC class name
        discipline: Discipline name
        bbox: (min_x, min_y, min_z, max_x, max_y, max_z) in mm
        collection: Collection to add object to

    Returns:
        Blender object with procedural shape
    """
    from ..federation import semantic_utils
    from . import shape_templates

    min_x, min_y, min_z, max_x, max_y, max_z = bbox

    # Convert mm to meters
    min_x, min_y, min_z = min_x / 1000.0, min_y / 1000.0, min_z / 1000.0
    max_x, max_y, max_z = max_x / 1000.0, max_y / 1000.0, max_z / 1000.0

    # Calculate dimensions and center
    width = max_x - min_x
    depth = max_y - min_y
    height = max_z - min_z
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    center_z = (min_z + max_z) / 2.0

    # Infer semantic type
    semantic_type = semantic_utils.get_semantic_type(ifc_class)

    # Create appropriate shape
    bm = None

    if semantic_type in ['pipe', 'conduit']:
        # Cylinder
        radius = max(width, depth) / 2.0
        bm = shape_templates.create_cylinder_basic(
            radius=max(radius, 0.01),
            length=max(height, 0.01),
            segments=8
        )
    else:
        # Box (walls, ducts, beams, equipment, etc.)
        bm = shape_templates.create_box_basic(
            width=max(width, 0.01),
            height=max(depth, 0.01),
            length=max(height, 0.01)
        )

    # Convert BMesh to mesh
    mesh = shape_templates.bmesh_to_mesh(bm, name=f"Viz_{guid}")

    # Create object
    obj = bpy.data.objects.new(guid, mesh)
    obj.location = Vector((center_x, center_y, center_z))

    # Store metadata
    obj["federation_guid"] = guid
    obj["federation_ifc_class"] = ifc_class
    obj["federation_discipline"] = discipline
    obj["federation_viz_temp"] = True  # Mark as temporary visualization

    # Add to collection
    collection.objects.link(obj)

    return obj


def get_clash_elements_for_visualization(
    guid_a: str,
    guid_b: str,
    db_path: str
) -> Tuple[Optional[bpy.types.Object], Optional[bpy.types.Object]]:
    """
    Get or create both clash elements for visualization.

    Creates temporary visualization collection if needed.

    Args:
        guid_a: GUID of first clash element
        guid_b: GUID of second clash element
        db_path: Path to federation database

    Returns:
        Tuple of (obj_a, obj_b), either may be None if not found
    """
    # Get or create temporary visualization collection
    viz_coll_name = "Clash_Visualization"
    if viz_coll_name in bpy.data.collections:
        viz_coll = bpy.data.collections[viz_coll_name]
    else:
        viz_coll = bpy.data.collections.new(viz_coll_name)
        bpy.context.scene.collection.children.link(viz_coll)

    # Find or create both elements
    obj_a = find_or_create_element_from_database(guid_a, db_path, viz_coll)
    obj_b = find_or_create_element_from_database(guid_b, db_path, viz_coll)

    return obj_a, obj_b


def cleanup_temp_visualization_objects():
    """
    Remove temporary visualization objects created for clash/route viewing.

    Call this when user is done viewing clashes to clean up scene.
    """
    viz_coll_name = "Clash_Visualization"
    if viz_coll_name in bpy.data.collections:
        viz_coll = bpy.data.collections[viz_coll_name]

        # Remove all objects marked as temporary
        for obj in list(viz_coll.objects):
            if obj.get("federation_viz_temp"):
                bpy.data.objects.remove(obj, do_unlink=True)

        # Remove collection if empty
        if len(viz_coll.objects) == 0:
            bpy.data.collections.remove(viz_coll)
