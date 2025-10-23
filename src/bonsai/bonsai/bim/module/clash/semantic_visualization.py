"""
Semantic Geometry Visualization - Database-Driven Procedural Geometry
Phase 3: Query element_semantics table and generate template-based meshes

NO IFC FILES - All geometry generated from semantic metadata in database.
"""

import bpy
import sqlite3
from pathlib import Path
from mathutils import Vector
from typing import List, Tuple, Dict, Optional
from . import shape_templates


# Global state for visualization
_semantic_objects = []  # List of created Blender objects
_is_enabled = False
_detail_level = 'basic'  # 'basic' or 'detailed'


def get_model_offset(db_path: str) -> Vector:
    """
    Get coordinate offset from cached MEP offset or calculate from database.

    Args:
        db_path: Path to federation database

    Returns:
        Offset vector to center elements at origin
    """
    # Try cached offset first
    cached = bpy.context.scene.get("MEP_cached_offset")
    if cached:
        return Vector(cached)

    # Calculate from database bounds
    if Path(db_path).exists():
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT MIN(min_x), MIN(min_y), MIN(min_z),
                       MAX(max_x), MAX(max_y), MAX(max_z)
                FROM elements_rtree
            """)
            bounds = cursor.fetchone()
            conn.close()

            if bounds and all(b is not None for b in bounds):
                center_x = (bounds[0] + bounds[3]) / 2
                center_y = (bounds[1] + bounds[4]) / 2
                center_z = (bounds[2] + bounds[5]) / 2

                offset = Vector((center_x, center_y, center_z))
                bpy.context.scene["MEP_cached_offset"] = (offset.x, offset.y, offset.z)
                return offset
        except Exception as e:
            print(f"Warning: Could not calculate offset: {e}")

    return Vector((0, 0, 0))


def query_semantic_elements(db_path: str, limit: Optional[int] = None) -> List[Dict]:
    """
    Query federation database for elements with semantic metadata.

    Args:
        db_path: Path to federation database
        limit: Optional limit on number of elements

    Returns:
        List of dicts with element data:
        {
            'guid': str,
            'ifc_class': str,
            'discipline': str,
            'profile_type': str,  # Inferred from bbox aspect ratio
            'width': float, 'height': float, 'radius': float, 'length': float,
            'bbox': (min_x, min_y, min_z, max_x, max_y, max_z),
            'bbox_center': (x, y, z)
        }
    """
    if not Path(db_path).exists():
        print(f"Database not found: {db_path}")
        return []

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Query elements with semantic metadata + bbox
    # NOTE: Actual schema has semantic_type, profile_width, profile_height (not profile_type, width, height)
    query = """
        SELECT
            m.guid,
            m.ifc_class,
            m.discipline,
            s.semantic_type,
            s.profile_width,
            s.profile_height,
            r.min_x, r.min_y, r.min_z,
            r.max_x, r.max_y, r.max_z
        FROM elements_meta m
        JOIN elements_rtree r ON m.id = r.id
        LEFT JOIN element_semantics s ON m.guid = s.guid
        WHERE s.semantic_type IS NOT NULL
    """

    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    print(f"\nQueried {len(rows):,} elements with semantic metadata from database")

    # Parse results
    elements = []
    for row in rows:
        guid, ifc_class, discipline, semantic_type, profile_width, profile_height = row[:6]
        bbox = tuple(row[6:12])

        # Calculate bbox center
        bbox_center = (
            (bbox[0] + bbox[3]) / 2,
            (bbox[1] + bbox[4]) / 2,
            (bbox[2] + bbox[5]) / 2
        )

        # Calculate bbox dimensions
        bbox_width = bbox[3] - bbox[0]
        bbox_height = bbox[4] - bbox[1]
        bbox_length = bbox[5] - bbox[2]
        length = max(bbox_width, bbox_height, bbox_length)  # Longest dimension

        # Infer profile type from bbox aspect ratio (circular vs rectangular)
        # Use cross-section dimensions (2 smallest)
        dims = sorted([bbox_width, bbox_height, bbox_length])
        cross_dim1, cross_dim2 = dims[0], dims[1]

        if cross_dim1 > 0:
            aspect_ratio = cross_dim2 / cross_dim1
            # If aspect ratio close to 1:1, likely circular
            profile_type = 'CIRCULAR' if 0.8 <= aspect_ratio <= 1.2 else 'RECTANGULAR'
        else:
            profile_type = 'RECTANGULAR'  # Default fallback

        # Use profile dimensions from semantics if available, else from bbox
        width = profile_width if profile_width else cross_dim2
        height = profile_height if profile_height else cross_dim1

        # Calculate radius for circular profiles (average of width and height / 2)
        radius = (width + height) / 4 if profile_type == 'CIRCULAR' else None

        elements.append({
            'guid': guid,
            'ifc_class': ifc_class,
            'discipline': discipline,
            'profile_type': profile_type,  # Inferred
            'width': width,
            'height': height,
            'radius': radius,  # Calculated
            'length': length,
            'bbox': bbox,
            'bbox_center': bbox_center
        })

    return elements


def create_element_object(element: Dict, offset: Vector, detail_level: str = 'basic') -> Optional[bpy.types.Object]:
    """
    Create Blender object from element semantic data.

    Args:
        element: Element data dict from query_semantic_elements()
        offset: Coordinate offset to apply
        detail_level: 'basic' (Semantic Proxies) or 'detailed' (Full Geometry)

    Returns:
        Blender object, or None if creation failed
    """
    # Extract dimensions
    dimensions = {
        'width': element.get('width'),
        'height': element.get('height'),
        'radius': element.get('radius'),
        'length': element.get('length')
    }

    # Generate geometry using shape templates
    bm = shape_templates.create_shape_from_semantics(
        element['ifc_class'],
        element['profile_type'],
        dimensions,
        detail_level=detail_level
    )

    if bm is None:
        # Unsupported shape type
        return None

    # Convert BMesh to mesh
    mesh_name = f"{element['ifc_class']}_{element['guid'][:8]}"
    mesh = shape_templates.bmesh_to_mesh(bm, mesh_name)

    # Create object
    obj = bpy.data.objects.new(mesh_name, mesh)

    # Position at bbox center (with offset applied)
    center = element['bbox_center']
    obj.location = (
        center[0] - offset.x,
        center[1] - offset.y,
        center[2] - offset.z
    )

    # Assign material based on discipline
    mat = shape_templates.create_material_for_discipline(element['discipline'])
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

    # Store metadata as custom properties
    obj["federation_guid"] = element['guid']
    obj["ifc_class"] = element['ifc_class']
    obj["discipline"] = element['discipline']

    return obj


def enable_semantic_visualization(db_path: str, detail_level: str = 'basic',
                                  limit: Optional[int] = None,
                                  batch_size: int = 1000) -> Tuple[bool, str]:
    """
    Enable semantic geometry visualization.

    Args:
        db_path: Path to federation database
        detail_level: 'basic' (Semantic Proxies) or 'detailed' (Full Geometry)
        limit: Optional limit on elements (for testing)
        batch_size: Number of elements to create per batch (for progress reporting)

    Returns:
        (success: bool, message: str)
    """
    global _semantic_objects, _is_enabled, _detail_level

    # Disable first if already enabled
    if _is_enabled:
        disable_semantic_visualization()

    print(f"\n{'='*70}")
    print(f"ENABLING SEMANTIC VISUALIZATION ({detail_level.upper()})")
    print(f"{'='*70}")

    # Get coordinate offset
    offset = get_model_offset(db_path)
    print(f"Using coordinate offset: ({offset.x:.1f}, {offset.y:.1f}, {offset.z:.1f})")

    # Query elements with semantic metadata
    print(f"\nQuerying elements with semantic metadata...")
    elements = query_semantic_elements(db_path, limit)

    if not elements:
        return False, "No elements with semantic metadata found in database"

    print(f"Found {len(elements):,} elements with semantics")

    # Create collection
    collection_name = f"Federation_{detail_level.capitalize()}"
    if collection_name in bpy.data.collections:
        collection = bpy.data.collections[collection_name]
        # Clear existing objects
        for obj in list(collection.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
    else:
        collection = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(collection)

    # Create objects in batches
    print(f"\nGenerating procedural geometry ({detail_level} level)...")
    _semantic_objects = []
    created_count = 0
    failed_count = 0

    for i, element in enumerate(elements):
        # Progress reporting every batch_size elements
        if i % batch_size == 0 and i > 0:
            print(f"  Progress: {i:,} / {len(elements):,} elements ({(i/len(elements)*100):.1f}%)")

        # Create object
        obj = create_element_object(element, offset, detail_level)

        if obj:
            collection.objects.link(obj)
            _semantic_objects.append(obj)
            created_count += 1
        else:
            failed_count += 1

    _is_enabled = True
    _detail_level = detail_level

    # Frame viewport to show elements
    print(f"\nFraming viewport...")
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.region_3d.view_distance = 300.0
                        space.region_3d.view_location = (0.0, 0.0, 0.0)
                area.tag_redraw()

    print(f"\n{'='*70}")
    print(f"✅ SEMANTIC VISUALIZATION ENABLED ({detail_level.upper()})")
    print(f"{'='*70}")
    print(f"Elements created: {created_count:,}")
    print(f"Elements failed: {failed_count:,}")
    print(f"Collection: {collection_name}")
    print(f"Detail level: {detail_level}")
    print(f"{'='*70}\n")

    return True, f"Created {created_count:,} procedural objects ({detail_level} level)"


def disable_semantic_visualization() -> Tuple[bool, str]:
    """
    Disable semantic visualization and remove objects.

    Returns:
        (success: bool, message: str)
    """
    global _semantic_objects, _is_enabled, _detail_level

    if not _is_enabled:
        return True, "Semantic visualization not enabled"

    print(f"Disabling semantic visualization ({_detail_level})...")

    # Remove collections
    for collection_name in ["Federation_Basic", "Federation_Detailed"]:
        if collection_name in bpy.data.collections:
            collection = bpy.data.collections[collection_name]

            # Remove objects
            for obj in list(collection.objects):
                bpy.data.objects.remove(obj, do_unlink=True)

            # Remove collection
            bpy.data.collections.remove(collection)

    _semantic_objects.clear()
    _is_enabled = False
    _detail_level = 'basic'

    # Force viewport redraw
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

    print("Semantic visualization disabled")
    return True, "Semantic visualization disabled"


def is_semantic_visualization_enabled() -> bool:
    """Check if semantic visualization is currently enabled"""
    global _is_enabled
    return _is_enabled


def get_current_detail_level() -> str:
    """Get current detail level ('basic' or 'detailed')"""
    global _detail_level
    return _detail_level
