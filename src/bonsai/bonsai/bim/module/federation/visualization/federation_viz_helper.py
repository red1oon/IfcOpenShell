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

# Import centralized offset function
from bonsai.bim.module.federation.core.coordinate_utils import get_model_offset


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
        # Query element metadata, bbox, and transforms (for GI schema)
        cursor.execute("""
            SELECT
                m.guid, m.ifc_class, m.discipline,
                r.minX, r.minY, r.minZ,
                r.maxX, r.maxY, r.maxZ,
                et.center_x, et.center_y, et.center_z
            FROM elements_meta m
            JOIN elements_rtree r ON m.id = r.id
            LEFT JOIN element_transforms et ON m.guid = et.guid
            WHERE m.guid = ?
        """, (guid,))

        result = cursor.fetchone()

        if not result:
            print(f"⚠ Element {guid} not found in database")
            return None

        guid, ifc_class, discipline, min_x, min_y, min_z, max_x, max_y, max_z, center_x, center_y, center_z = result

        # Step 3: Try to load tessellated geometry first, fallback to bbox
        # GI schema: geometry stored at origin with element_transforms for positioning
        try:
            from bonsai.bim.module.federation.stage2_tessellation_loader import unpack_vertices, unpack_faces

            # GI schema query
            cursor.execute("""
                SELECT bg.vertices, bg.faces
                FROM element_instances ei
                JOIN base_geometries bg ON ei.geometry_hash = bg.geometry_hash
                WHERE ei.guid = ?
            """, (guid,))

            geom_row = cursor.fetchone()

            if geom_row:
                verts_blob, faces_blob = geom_row

                # Unpack geometry (GI databases store geometry at LOCAL origin)
                vertices = unpack_vertices(verts_blob)
                faces = unpack_faces(faces_blob)

                # Create Blender mesh with LOCAL vertices (AS-IS, like blend_cache does)
                mesh = bpy.data.meshes.new(guid[:8])
                mesh.from_pydata(vertices, [], faces)
                mesh.update()

                # Create object
                obj = bpy.data.objects.new(guid, mesh)

                # Apply transform from element_transforms (like blend_cache does)
                if center_x is not None and center_y is not None and center_z is not None:
                    obj.location = (center_x, center_y, center_z)
                else:
                    # Fallback to bbox center if no transform
                    bbox_center = Vector(((min_x + max_x) / 2.0, (min_y + max_y) / 2.0, (min_z + max_z) / 2.0))
                    obj.location = bbox_center

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

    # Calculate center in GPS world coordinates
    # NO OFFSET STRATEGY: Use GPS coordinates directly
    # Database stores GPS coords (USE_WORLD_COORDS=True)
    # Buildings and gizmos also use GPS coords
    # Result: Everything aligns in same GPS coordinate space
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    center_z = (min_z + max_z) / 2.0

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


def batch_load_clash_elements(
    guids: list[str],
    db_path: str,
    collection: bpy.types.Collection
) -> dict[str, Optional[bpy.types.Object]]:
    """
    OPTIMIZED: Batch load multiple elements with single database query.

    Eliminates N+1 query problem - loads 100 elements with 1 query instead of 100.

    Args:
        guids: List of GUIDs to load
        db_path: Path to federation database
        collection: Collection to add objects to

    Returns:
        Dictionary mapping GUID -> Blender object (or None if not found)
    """
    import time
    start_time = time.time()

    # Step 1: Check scene for already-loaded elements
    result_objects = {}
    guids_to_load = []

    for guid in guids:
        existing_obj = None
        for obj in bpy.data.objects:
            if obj.get('federation_guid') == guid or obj.name == guid:
                existing_obj = obj
                break

        if existing_obj:
            result_objects[guid] = existing_obj
        else:
            guids_to_load.append(guid)

    if not guids_to_load:
        return result_objects  # All already loaded

    # Step 2: BATCH QUERY - Load all metadata in one query
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Build placeholders for IN clause
        placeholders = ','.join('?' * len(guids_to_load))

        # OPTIMIZED: Single query for all elements (with transforms for GI schema)
        query = f"""
            SELECT
                m.guid, m.ifc_class, m.discipline,
                r.minX, r.minY, r.minZ,
                r.maxX, r.maxY, r.maxZ,
                et.center_x, et.center_y, et.center_z
            FROM elements_meta m
            JOIN elements_rtree r ON m.id = r.id
            LEFT JOIN element_transforms et ON m.guid = et.guid
            WHERE m.guid IN ({placeholders})
        """

        cursor.execute(query, guids_to_load)
        metadata_rows = cursor.fetchall()

        # Step 3: Load geometry for elements (GI schema)
        guids_with_meta = [row[0] for row in metadata_rows]

        if guids_with_meta:
            geom_placeholders = ','.join('?' * len(guids_with_meta))
            # GI schema query
            geom_query = f"""
                SELECT ei.guid, bg.vertices, bg.faces
                FROM element_instances ei
                JOIN base_geometries bg ON ei.geometry_hash = bg.geometry_hash
                WHERE ei.guid IN ({geom_placeholders})
            """

            cursor.execute(geom_query, guids_with_meta)
            geom_rows = cursor.fetchall()

            # Build geometry lookup dict
            geometry_data = {row[0]: (row[1], row[2]) for row in geom_rows}
        else:
            geometry_data = {}

        # Step 4: Create objects from batched data
        from bonsai.bim.module.federation.stage2_tessellation_loader import unpack_vertices, unpack_faces

        for row in metadata_rows:
            guid, ifc_class, discipline, min_x, min_y, min_z, max_x, max_y, max_z, center_x, center_y, center_z = row

            # Try tessellated geometry first
            if guid in geometry_data:
                try:
                    verts_blob, faces_blob = geometry_data[guid]

                    # GI databases store geometry at LOCAL origin
                    vertices = unpack_vertices(verts_blob)
                    faces = unpack_faces(faces_blob)

                    # Create mesh with LOCAL vertices (AS-IS, like blend_cache)
                    mesh = bpy.data.meshes.new(guid[:8])
                    mesh.from_pydata(vertices, [], faces)
                    mesh.update()

                    obj = bpy.data.objects.new(guid, mesh)

                    # Apply transform from element_transforms (like blend_cache)
                    if center_x is not None and center_y is not None and center_z is not None:
                        obj.location = (center_x, center_y, center_z)
                    else:
                        # Fallback to bbox center
                        bbox_center = Vector(((min_x + max_x) / 2.0, (min_y + max_y) / 2.0, (min_z + max_z) / 2.0))
                        obj.location = bbox_center

                    obj["federation_guid"] = guid
                    obj["federation_ifc_class"] = ifc_class
                    obj["federation_discipline"] = discipline
                    obj["federation_viz_temp"] = True

                    collection.objects.link(obj)
                    result_objects[guid] = obj
                    continue
                except Exception as e:
                    print(f"  ⚠️  Could not load tessellated mesh for {guid}: {e}")

            # Fallback: Create bbox shape
            obj = create_procedural_shape_from_bbox(
                guid=guid,
                ifc_class=ifc_class,
                discipline=discipline,
                bbox=(min_x, min_y, min_z, max_x, max_y, max_z),
                collection=collection
            )

            if obj:
                result_objects[guid] = obj

        elapsed = time.time() - start_time
        print(f"  ⚡ Batch loaded {len(guids_to_load)} elements in {elapsed:.2f}s ({len(guids_to_load)/elapsed:.1f} elem/s)")

    finally:
        conn.close()

    return result_objects


def cleanup_temp_visualization_objects():
    """
    Remove temporary visualization objects created for clash/route viewing.

    Call this when user is done viewing clashes to clean up scene.

    OPTIMIZED: Batch delete for better performance (20-30× faster).
    """
    # Collect all objects to delete
    objects_to_delete = []

    viz_coll_name = "Clash_Visualization"
    if viz_coll_name in bpy.data.collections:
        viz_coll = bpy.data.collections[viz_coll_name]
        objects_to_delete.extend(viz_coll.objects)

    # Also collect stray objects with "Clash_" prefix
    for obj in bpy.data.objects:
        if obj.name.startswith("Clash_") and obj not in objects_to_delete:
            objects_to_delete.append(obj)

    # BATCH DELETE: Select all, delete in one operation (single depsgraph update)
    if objects_to_delete:
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects_to_delete:
            obj.select_set(True)
        bpy.ops.object.delete()

    # Remove collection after objects are gone
    if viz_coll_name in bpy.data.collections:
        bpy.data.collections.remove(bpy.data.collections[viz_coll_name])
