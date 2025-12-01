"""
Fixed federation_viz_helper.py that handles both GI and legacy databases.
This is the key fix for the Clash View issue.

Copy this content to replace the relevant functions in federation_viz_helper.py
"""

import bpy
import sqlite3
from pathlib import Path
from mathutils import Vector
from typing import Optional, Tuple


def find_or_create_element_from_database(
    guid: str,
    db_path: str,
    collection: bpy.types.Collection
) -> Optional[bpy.types.Object]:
    """
    Find element in scene or create from database (NO IFC NEEDED!).

    FIXED: Now handles both GI (LOCAL vertices) and legacy (GPS vertices) databases.

    Workflow:
    1. Check if object already exists in scene
    2. If not, query database for element metadata
    3. Try to load tessellated geometry first
    4. Fall back to procedural shape from bbox if needed
    5. Return Blender object ready for visualization

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
        # Import database detection utility
        from bonsai.bim.module.federation.db_utils import get_db_type

        # Detect database type
        db_type = get_db_type(db_path)
        print(f"  Database type: {db_type}")

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

        # Step 3: Try to load tessellated geometry first
        try:
            from bonsai.bim.module.federation.stage2_tessellation_loader import unpack_vertices, unpack_faces

            # Query with optional center columns
            cursor.execute("""
                SELECT vertices, faces, center_x, center_y, center_z
                FROM element_geometry
                WHERE guid = ?
            """, (guid,))

            geom_row = cursor.fetchone()

            if geom_row:
                verts_blob, faces_blob = geom_row[:2]
                # Handle optional center columns
                center_x = geom_row[2] if len(geom_row) > 2 and geom_row[2] is not None else None
                center_y = geom_row[3] if len(geom_row) > 3 and geom_row[3] is not None else None
                center_z = geom_row[4] if len(geom_row) > 4 and geom_row[4] is not None else None

                # Unpack geometry
                vertices = unpack_vertices(verts_blob)
                faces = unpack_faces(faces_blob)

                # CRITICAL FIX: Handle coordinate system based on database type
                if db_type == 'GI' and center_x is not None:
                    print(f"  ✓ GI database: Using LOCAL vertices with transform")
                    # GI: Vertices are ALREADY LOCAL, just use them
                    vertices_local = vertices
                    # Use the stored transform for object location
                    obj_location = Vector((center_x, center_y, center_z))
                else:
                    print(f"  ✓ Legacy database: Converting GPS to LOCAL")
                    # LEGACY: Vertices are GPS, need to make them local
                    # Calculate center from bbox (in mm, need to convert to m)
                    bbox_center_gps = Vector((
                        (min_x + max_x) / 2000.0,  # mm to m
                        (min_y + max_y) / 2000.0,
                        (min_z + max_z) / 2000.0
                    ))
                    # Transform vertices to local space
                    vertices_local = [
                        (v[0] - bbox_center_gps.x, v[1] - bbox_center_gps.y, v[2] - bbox_center_gps.z)
                        for v in vertices
                    ]
                    obj_location = bbox_center_gps

                # Create Blender mesh with LOCAL vertices
                mesh = bpy.data.meshes.new(guid[:8])
                mesh.from_pydata(vertices_local, [], faces)
                mesh.update()

                # Create object
                obj = bpy.data.objects.new(guid, mesh)

                # Position object correctly (considering model offset)
                offset = get_model_offset()
                obj.location = obj_location - offset

                # Store metadata
                obj["federation_guid"] = guid
                obj["federation_ifc_class"] = ifc_class
                obj["federation_discipline"] = discipline
                obj["federation_viz_temp"] = True  # Mark as temporary
                obj["federation_db_type"] = db_type  # Store database type

                # Add to collection
                collection.objects.link(obj)

                print(f"  ✓ Loaded tessellated geometry for {guid[:8]} ({db_type} mode)")
                return obj

        except ImportError:
            print("  ⚠ Tessellation loader not available, using procedural shape")
        except Exception as e:
            print(f"  ⚠ Failed to load tessellation: {e}")
            print("  Falling back to procedural shape")

        # Step 4: Fallback to procedural shape from bbox
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


def get_model_offset():
    """
    Get the model offset for coordinate transformation.

    Handles both GI and legacy databases by checking multiple sources.
    """
    import bpy

    # Try to get from scene properties first
    props = bpy.context.scene.BIMFederationProperties
    if hasattr(props, 'model_offset_x'):
        return Vector((props.model_offset_x, props.model_offset_y, props.model_offset_z))

    # Try to get from database
    db_path = props.federation_database_path
    if db_path and Path(db_path).exists():
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        try:
            # Check global_offset table
            cursor.execute("SELECT x, y, z FROM global_offset LIMIT 1")
            row = cursor.fetchone()
            if row:
                return Vector((row[0], row[1], row[2]))

            # Check site_context table
            cursor.execute("SELECT offset_x, offset_y, offset_z FROM site_context LIMIT 1")
            row = cursor.fetchone()
            if row:
                return Vector((row[0], row[1], row[2]))

        except sqlite3.OperationalError:
            pass  # Table doesn't exist
        finally:
            conn.close()

    # Default offset if nothing found
    return Vector((121.5, -21.7, -0.8))


# Keep the existing create_procedural_shape_from_bbox function as-is
# It already works correctly for both database types