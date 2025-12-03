"""
BBox Wireframe Visualization for Federation Elements
Phase 2: BBox Semantic Geometry System

Renders federation elements as colored wireframe bounding boxes using GPU batch drawing.
Enables instant loading of 44K+ elements with <10MB memory usage.
"""

import bpy
import gpu
import sqlite3
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, Matrix
from pathlib import Path
from typing import List, Tuple, Optional, Dict

# Discipline colors (from federation module)
DISCIPLINE_COLORS = {
    'ACMV': (0.0, 0.75, 1.0, 1.0),      # Cyan/Blue
    'FP': (1.0, 0.0, 0.0, 1.0),          # Red
    'ELEC': (1.0, 1.0, 0.0, 1.0),        # Yellow
    'PLUMB': (0.0, 0.4, 1.0, 1.0),       # Dark Blue (water)
    'GAS': (0.8, 0.0, 0.8, 1.0),         # Purple/Magenta
    'ICT': (0.0, 1.0, 0.0, 1.0),         # Green (data/comms)
    'FURN': (0.6, 0.4, 0.2, 1.0),        # Brown/wood (furniture)
    'CW': (0.0, 1.0, 1.0, 1.0),          # Cyan
    'SP': (1.0, 0.5, 0.0, 1.0),          # Orange
    'ARC': (0.5, 0.5, 0.5, 0.7),         # Gray
    'ARCHITECTURE': (0.5, 0.5, 0.5, 0.7),
    'STR': (0.6, 0.4, 0.2, 1.0),         # Brown (concrete)
    'STRUCTURE': (0.6, 0.4, 0.2, 1.0),
    'REB': (0.9, 0.5, 0.2, 1.0),         # Rust/orange (reinforcement)
    'DEFAULT': (0.7, 0.7, 0.7, 0.5),     # Light gray
}

# Global state for visualization
_bbox_batches = {}
_draw_handler = None
_is_enabled = False
_discipline_visibility = {}  # Set by legend when disciplines are toggled


def create_bbox_edges(bbox: Tuple[float, float, float, float, float, float]) -> List[Vector]:
    """
    Create the 12 edges of a bounding box as line segments.

    Args:
        bbox: (min_x, min_y, min_z, max_x, max_y, max_z)

    Returns:
        List of 24 vertices (12 edges * 2 vertices each)
    """
    min_x, min_y, min_z, max_x, max_y, max_z = bbox

    # 8 corners of the bbox
    corners = [
        Vector((min_x, min_y, min_z)),  # 0: bottom-front-left
        Vector((max_x, min_y, min_z)),  # 1: bottom-front-right
        Vector((max_x, max_y, min_z)),  # 2: bottom-back-right
        Vector((min_x, max_y, min_z)),  # 3: bottom-back-left
        Vector((min_x, min_y, max_z)),  # 4: top-front-left
        Vector((max_x, min_y, max_z)),  # 5: top-front-right
        Vector((max_x, max_y, max_z)),  # 6: top-back-right
        Vector((min_x, max_y, max_z)),  # 7: top-back-left
    ]

    # 12 edges (each edge = 2 vertices)
    edges = [
        # Bottom face (4 edges)
        (corners[0], corners[1]),
        (corners[1], corners[2]),
        (corners[2], corners[3]),
        (corners[3], corners[0]),
        # Top face (4 edges)
        (corners[4], corners[5]),
        (corners[5], corners[6]),
        (corners[6], corners[7]),
        (corners[7], corners[4]),
        # Vertical edges (4 edges)
        (corners[0], corners[4]),
        (corners[1], corners[5]),
        (corners[2], corners[6]),
        (corners[3], corners[7]),
    ]

    # Flatten to list of vertices
    vertices = []
    for edge in edges:
        vertices.extend(edge)

    return vertices


def get_model_offset(db_path: str = None) -> Vector:
    """
    Get coordinate offset to convert IFC world coords to Blender scene coords.

    Apollo 13 Approach: Read pre-calculated offset from site_context (already in meters)

    Priority:
    1. Cached MEP offset from scene properties
    2. Pre-calculated offset from site_context table (Apollo 13)
    3. Fallback to zero offset
    """
    # Try MEP cached offset first
    cached = bpy.context.scene.get("MEP_cached_offset")
    if cached:
        return Vector(cached)

    # If database path provided, read pre-calculated offset from site_context (Apollo 13)
    if db_path and Path(db_path).exists():
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Apollo 13: Read pre-calculated federation offset (already in meters!)
            cursor.execute("""
                SELECT offset_x, offset_y, offset_z
                FROM site_context
                LIMIT 1
            """)
            site_offset = cursor.fetchone()
            conn.close()

            if site_offset and all(v is not None for v in site_offset):
                # Offset is already in meters from preprocessing
                offset = Vector((site_offset[0], site_offset[1], site_offset[2]))
                print(f"  Calculated offset from database: ({offset.x:.1f}, {offset.y:.1f}, {offset.z:.1f})")

                # Cache it for future use
                bpy.context.scene["MEP_cached_offset"] = (offset.x, offset.y, offset.z)

                return offset
        except Exception as e:
            print(f"  Warning: Could not read offset from site_context: {e}")

        # Try global_offset table as fallback
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                SELECT offset_x, offset_y, offset_z
                FROM global_offset
                LIMIT 1
            """)
            global_offset = cursor.fetchone()
            conn.close()

            if global_offset and all(v is not None for v in global_offset):
                offset = Vector((global_offset[0], global_offset[1], global_offset[2]))
                print(f"  Using global_offset from database: ({offset.x:.1f}, {offset.y:.1f}, {offset.z:.1f})")

                # Cache it for future use
                bpy.context.scene["MEP_cached_offset"] = (offset.x, offset.y, offset.z)

                return offset
        except Exception as e:
            print(f"  Warning: Could not read offset from global_offset: {e}")

    # Fallback: assume zero offset (IFC world coords = Blender coords)
    return Vector((0, 0, 0))


def load_federation_bboxes(db_path: str, limit: Optional[int] = None) -> Dict[str, List[Tuple]]:
    """
    Load bounding boxes from federation database, grouped by discipline.

    Args:
        db_path: Path to federation database
        limit: Optional limit on number of elements (for testing)

    Returns:
        Dict mapping discipline to list of (bbox, guid) tuples
    """
    if not Path(db_path).exists():
        print(f"Federation database not found: {db_path}")
        return {}

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Query bboxes with discipline
    query = """
        SELECT m.discipline, r.minX, r.minY, r.minZ, r.maxX, r.maxY, r.maxZ, m.guid
        FROM elements_meta m
        JOIN elements_rtree r ON m.id = r.id
    """
    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    # Group by discipline
    discipline_bboxes = {}
    for row in rows:
        discipline = row[0]
        # Database already has meters (site-local coordinates), no conversion needed
        bbox = tuple(row[1:7])  # min_x, min_y, min_z, max_x, max_y, max_z (already in meters)
        guid = row[7]

        if discipline not in discipline_bboxes:
            discipline_bboxes[discipline] = []

        discipline_bboxes[discipline].append((bbox, guid))

    return discipline_bboxes


def create_discipline_batches(discipline_bboxes: Dict[str, List[Tuple]], offset: Vector) -> Dict[str, gpu.types.GPUBatch]:
    """
    Create GPU batches for each discipline's bounding boxes.

    Args:
        discipline_bboxes: Dict mapping discipline to list of (bbox, guid) tuples
        offset: Coordinate offset to apply

    Returns:
        Dict mapping discipline to GPU batch
    """
    batches = {}
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')

    for discipline, bbox_list in discipline_bboxes.items():
        if not bbox_list:
            continue

        # Collect all vertices for this discipline
        all_vertices = []
        for bbox, guid in bbox_list:
            # Database coords are already viewport-relative (offset applied during federation)
            # NO coordinate conversion needed - use directly
            edges = create_bbox_edges(bbox)
            all_vertices.extend(edges)

        if all_vertices:
            # Create batch for this discipline
            batch = batch_for_shader(shader, 'LINES', {"pos": all_vertices})
            batches[discipline] = batch
            print(f"  Created batch for {discipline}: {len(bbox_list):,} elements, {len(all_vertices)} vertices")

    return batches


def draw_bboxes():
    """Draw callback function for viewport rendering"""
    global _bbox_batches, _is_enabled, _discipline_visibility

    if not _is_enabled or not _bbox_batches:
        return

    # Enable blending for transparent colors
    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(1.0)

    shader = gpu.shader.from_builtin('UNIFORM_COLOR')

    # Draw each discipline's batch with its color (skip hidden ones)
    for discipline, batch in _bbox_batches.items():
        # Check visibility (default to visible if not set)
        if not _discipline_visibility.get(discipline, True):
            continue  # Skip this discipline

        color = DISCIPLINE_COLORS.get(discipline, DISCIPLINE_COLORS['DEFAULT'])
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)

    # Restore state
    gpu.state.blend_set('NONE')


def enable_bbox_visualization(db_path: str, limit: Optional[int] = None) -> Tuple[bool, str]:
    """
    Enable bounding box visualization in viewport.

    Args:
        db_path: Path to federation database
        limit: Optional limit for testing (None = all elements)

    Returns:
        (success: bool, message: str)
    """
    global _bbox_batches, _draw_handler, _is_enabled

    # Disable first if already enabled
    if _is_enabled:
        disable_bbox_visualization()

    print(f"\n{'='*70}")
    print(f"ENABLING BBOX VISUALIZATION")
    print(f"{'='*70}")
    print(f"Database: {db_path}")
    if limit:
        print(f"Limit: {limit} elements (testing mode)")

    # Load bboxes from database
    print(f"\nLoading bounding boxes from federation database...")
    discipline_bboxes = load_federation_bboxes(db_path, limit)

    if not discipline_bboxes:
        return False, "No bounding boxes loaded from database"

    total_elements = sum(len(bboxes) for bboxes in discipline_bboxes.values())
    print(f"Loaded {total_elements:,} elements across {len(discipline_bboxes)} disciplines")

    # DEBUG: Show sample bbox coordinates from database
    print(f"\n🔍 DEBUG: Sample bounding boxes from database:")
    for discipline, bbox_list in list(discipline_bboxes.items())[:3]:
        if bbox_list:
            bbox, guid = bbox_list[0]
            print(f"   {discipline}: minXYZ=({bbox[0]:.2f}, {bbox[1]:.2f}, {bbox[2]:.2f}) maxXYZ=({bbox[3]:.2f}, {bbox[4]:.2f}, {bbox[5]:.2f})")

    # Calculate actual bbox range from loaded data
    all_min_x = min(bbox[0] for bboxes in discipline_bboxes.values() for bbox, _ in bboxes)
    all_max_x = max(bbox[3] for bboxes in discipline_bboxes.values() for bbox, _ in bboxes)
    all_min_y = min(bbox[1] for bboxes in discipline_bboxes.values() for bbox, _ in bboxes)
    all_max_y = max(bbox[4] for bboxes in discipline_bboxes.values() for bbox, _ in bboxes)
    all_min_z = min(bbox[2] for bboxes in discipline_bboxes.values() for bbox, _ in bboxes)
    all_max_z = max(bbox[5] for bboxes in discipline_bboxes.values() for bbox, _ in bboxes)

    extent_x = all_max_x - all_min_x
    extent_y = all_max_y - all_min_y
    extent_z = all_max_z - all_min_z

    print(f"\n🔍 DEBUG: Loaded bbox extents:")
    print(f"   X: {all_min_x:.2f} to {all_max_x:.2f} (extent: {extent_x:.2f}m = {extent_x/1000:.2f}km)")
    print(f"   Y: {all_min_y:.2f} to {all_max_y:.2f} (extent: {extent_y:.2f}m = {extent_y/1000:.2f}km)")
    print(f"   Z: {all_min_z:.2f} to {all_max_z:.2f} (extent: {extent_z:.2f}m)")

    # Get coordinate offset (auto-calculate from database if not cached)
    offset = get_model_offset(db_path)
    print(f"\n🔍 DEBUG: Coordinate offset: ({offset.x:.1f}, {offset.y:.1f}, {offset.z:.1f})")

    # DEBUG: Show what coordinates will be after offset
    print(f"\n🔍 DEBUG: After applying offset, Blender coordinates will be:")
    blender_min_x = all_min_x - offset.x
    blender_max_x = all_max_x - offset.x
    blender_min_y = all_min_y - offset.y
    blender_max_y = all_max_y - offset.y
    blender_min_z = all_min_z - offset.z
    blender_max_z = all_max_z - offset.z
    print(f"   X: {blender_min_x:.2f} to {blender_max_x:.2f} (extent: {blender_max_x - blender_min_x:.2f}m)")
    print(f"   Y: {blender_min_y:.2f} to {blender_max_y:.2f} (extent: {blender_max_y - blender_min_y:.2f}m)")
    print(f"   Z: {blender_min_z:.2f} to {blender_max_z:.2f} (extent: {blender_max_z - blender_min_z:.2f}m)")
    print(f"   Center: ({(blender_min_x + blender_max_x)/2:.2f}, {(blender_min_y + blender_max_y)/2:.2f}, {(blender_min_z + blender_max_z)/2:.2f})")

    # Create GPU batches
    print(f"\nCreating GPU batches...")
    _bbox_batches = create_discipline_batches(discipline_bboxes, offset)

    if not _bbox_batches:
        return False, "Failed to create GPU batches"

    # Register draw handler
    _draw_handler = bpy.types.SpaceView3D.draw_handler_add(
        draw_bboxes, (), 'WINDOW', 'POST_VIEW'
    )
    _is_enabled = True

    # Auto-frame viewport to show bboxes
    # Calculate overall bbox from all elements
    if discipline_bboxes:
        all_coords = []
        for bboxes_list in discipline_bboxes.values():
            for bbox, _ in bboxes_list:
                # Use database coords directly (no offset)
                all_coords.extend([
                    (bbox[0], bbox[1], bbox[2]),
                    (bbox[3], bbox[4], bbox[5])
                ])

        if all_coords:
            # Calculate center and size
            import numpy as np
            coords_array = np.array(all_coords)
            center = coords_array.mean(axis=0)
            bbox_size = coords_array.max(axis=0) - coords_array.min(axis=0)
            max_dim = max(bbox_size)

            # Frame viewport
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            space = area.spaces[0]
                            # Set view location and distance
                            space.region_3d.view_location = center
                            space.region_3d.view_distance = max_dim * 1.5
                            break

            print(f"Viewport: Framed to center ({center[0]:.1f}, {center[1]:.1f}, {center[2]:.1f})")

    print(f"\n{'='*70}")
    print(f"✅ BBOX VISUALIZATION ENABLED")
    print(f"{'='*70}")
    print(f"Elements rendered: {total_elements:,}")
    print(f"Disciplines: {', '.join(_bbox_batches.keys())}")
    print(f"GPU batches: {len(_bbox_batches)}")
    print(f"Viewport: Building centered near origin (no auto-framing)")
    print(f"{'='*70}\n")

    return True, f"Rendering {total_elements:,} elements as wireframe bboxes"


def disable_bbox_visualization() -> Tuple[bool, str]:
    """
    Disable bounding box visualization.

    Returns:
        (success: bool, message: str)
    """
    global _bbox_batches, _draw_handler, _is_enabled

    if not _is_enabled:
        return True, "BBox visualization not enabled"

    # Remove draw handler
    if _draw_handler:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handler, 'WINDOW')
        _draw_handler = None

    # Clear batches
    _bbox_batches.clear()
    _is_enabled = False

    # Force viewport redraw
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

    print("BBox visualization disabled")
    return True, "BBox visualization disabled"


def is_bbox_visualization_enabled() -> bool:
    """Check if BBox visualization is currently enabled"""
    global _is_enabled
    return _is_enabled
