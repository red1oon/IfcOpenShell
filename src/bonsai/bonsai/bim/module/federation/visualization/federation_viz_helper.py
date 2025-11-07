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
import math


def get_model_offset() -> Vector:
    """
    Get model offset to convert IFC coords to Blender coords.

    Uses cached offset from MEP routing if available, otherwise falls back
    to Bonsai georeference properties.

    Returns:
        Vector with (x, y, z) offset in meters
    """
    # Try MEP cached offset first (most reliable)
    cached = bpy.context.scene.get("MEP_cached_offset")
    if cached:
        return Vector(cached)

    # Fallback to georeference properties
    try:
        props = bpy.context.scene.BIMGeoreferenceProperties
        offset = Vector((
            props.model_offset_x or 0.0,
            props.model_offset_y or 0.0,
            props.model_offset_z or 0.0
        ))
        # Check if offset is actually set (not all zeros)
        if offset.length > 0.01:
            return offset
    except Exception:
        pass

    # No offset available - assume zero (objects at IFC world coords)
    print("⚠️  Warning: No coordinate offset available - using IFC world coordinates")
    return Vector((0, 0, 0))


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
                r.minX, r.minY, r.minZ,
                r.maxX, r.maxY, r.maxZ
            FROM elements_meta m
            JOIN elements_rtree r ON m.id = r.id
            WHERE m.guid = ?
        """, (guid,))

        result = cursor.fetchone()

        if not result:
            print(f"⚠ Element {guid} not found in database")
            return None

        guid, ifc_class, discipline, min_x, min_y, min_z, max_x, max_y, max_z = result

        # Step 3: Try to load tessellated geometry first, fallback to bbox
        # Load tessellated geometry directly (simplified - no vertex_count needed)
        try:
            from bonsai.bim.module.federation.stage2_tessellation_loader import unpack_vertices, unpack_faces

            cursor.execute("""
                SELECT vertices, faces
                FROM element_geometry
                WHERE guid = ?
            """, (guid,))

            geom_row = cursor.fetchone()

            if geom_row:
                verts_blob, faces_blob = geom_row

                # Unpack geometry
                vertices = unpack_vertices(verts_blob)
                faces = unpack_faces(faces_blob)

                # CRITICAL: Calculate GPS center from BBOX (elements_rtree has correct values)
                # element_transforms.center is (0,0,0) for all elements - NOT GPS position
                bbox_center_gps = Vector(((min_x + max_x) / 2.0, (min_y + max_y) / 2.0, (min_z + max_z) / 2.0))

                # Transform mesh vertices from GPS to local (relative to bbox center)
                vertices_local = [(v[0] - bbox_center_gps.x, v[1] - bbox_center_gps.y, v[2] - bbox_center_gps.z) for v in vertices]

                # Create Blender mesh with LOCAL vertices
                mesh = bpy.data.meshes.new(guid[:8])
                mesh.from_pydata(vertices_local, [], faces)
                mesh.update()

                # Create object
                obj = bpy.data.objects.new(guid, mesh)

                # Position object: bbox_center - offset
                # Get global offset (single-row table, no id column)
                cursor.execute("SELECT offset_x, offset_y, offset_z FROM global_offset LIMIT 1")
                offset_row = cursor.fetchone()

                if offset_row:
                    offset_x, offset_y, offset_z = offset_row
                    offset = Vector((offset_x, offset_y, offset_z))
                    obj.location = bbox_center_gps - offset
                else:
                    # No offset available - use bbox center as-is
                    obj.location = bbox_center_gps

                # Store metadata
                obj["federation_guid"] = guid
                obj["federation_ifc_class"] = ifc_class
                obj["federation_discipline"] = discipline
                obj["federation_viz_temp"] = True

                # Add to collection
                collection.objects.link(obj)

                print(f"  ✓ Loaded tessellated geometry for {guid} ({len(vertices)} verts, {len(faces)} faces)")
                return obj

        except Exception as e:
            print(f"  ⚠️  Could not load tessellated mesh for {guid}: {e}")
            # Fall through to bbox creation

        # Fallback: Create procedural shape from bbox
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
        bbox: (min_x, min_y, min_z, max_x, max_y, max_z) in meters (IFC world coords)
        collection: Collection to add object to

    Returns:
        Blender object with procedural shape
    """
    from bonsai.bim.module.federation import semantic_utils
    from . import shape_templates

    min_x, min_y, min_z, max_x, max_y, max_z = bbox

    # Database stores meters in IFC world coordinates (GPS space)
    # We need to apply coordinate offset to convert to Blender scene space

    # Calculate dimensions (these don't change with offset)
    width = max_x - min_x
    depth = max_y - min_y
    height = max_z - min_z

    # Calculate center in IFC world coordinates
    ifc_center_x = (min_x + max_x) / 2.0
    ifc_center_y = (min_y + max_y) / 2.0
    ifc_center_z = (min_z + max_z) / 2.0

    # CRITICAL: Apply coordinate offset to convert IFC coords to Blender coords
    # This matches the gizmo coordinate conversion pattern
    offset = get_model_offset()
    center_x = ifc_center_x - offset.x
    center_y = ifc_center_y - offset.y
    center_z = ifc_center_z - offset.z

    # CRITICAL: Validate bbox dimensions to prevent degenerate geometry
    min_dim = 0.01  # 1cm minimum
    if width < min_dim or depth < min_dim or height < min_dim:
        print(f"⚠️  Warning: Small bbox for {guid}: {width:.3f}x{depth:.3f}x{height:.3f}")
        width = max(width, min_dim)
        depth = max(depth, min_dim)
        height = max(height, min_dim)

    # Validate center coordinates (catch NaN/Inf)
    if not (math.isfinite(center_x) and math.isfinite(center_y) and math.isfinite(center_z)):
        print(f"✗ ERROR: Invalid center coords for {guid}: ({center_x}, {center_y}, {center_z})")
        return None

    try:
        # Infer semantic type
        semantic_type = semantic_utils.get_semantic_type(ifc_class)

        # Create appropriate shape
        bm = None

        if semantic_type in ['pipe', 'conduit']:
            # Cylinder
            radius = max(width, depth) / 2.0
            bm = shape_templates.create_cylinder_basic(
                radius=max(radius, min_dim),
                length=max(height, min_dim),
                segments=8
            )
        else:
            # Box (walls, ducts, beams, equipment, etc.)
            bm = shape_templates.create_box_basic(
                width=max(width, min_dim),
                height=max(depth, min_dim),
                length=max(height, min_dim)
            )

        # Convert BMesh to mesh
        if bm is None:
            print(f"✗ ERROR: Failed to create bmesh for {guid}")
            return None

        mesh = shape_templates.bmesh_to_mesh(bm, name=f"Viz_{guid}")

        if mesh is None:
            print(f"✗ ERROR: Failed to convert bmesh to mesh for {guid}")
            return None

        # Create object
        obj = bpy.data.objects.new(guid, mesh)
        obj.location = Vector((center_x, center_y, center_z))

    except Exception as e:
        print(f"✗ ERROR: Failed to create object for {guid}: {e}")
        import traceback
        traceback.print_exc()
        return None

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

        # Remove all objects in the collection (regardless of property)
        for obj in list(viz_coll.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

        # Remove the collection itself
        bpy.data.collections.remove(viz_coll)

    # Also remove any stray objects with "Clash_" prefix not in collection
    for obj in list(bpy.data.objects):
        if obj.name.startswith("Clash_"):
            bpy.data.objects.remove(obj, do_unlink=True)
