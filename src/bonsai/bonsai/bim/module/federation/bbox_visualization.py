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
    # Coastal Oasis river restoration disciplines
    'GEO': (0.15, 0.4, 0.65, 0.5),       # Blue water (semi-transparent)
    'BOOM': (0.95, 0.55, 0.1, 1.0),      # High-viz orange (boom barriers)
    'FAC': (0.6, 0.6, 0.6, 1.0),         # Concrete gray (facilities)
    'IOT': (0.2, 0.8, 0.3, 1.0),         # Monitoring green (IoT sensors)
    'DEFAULT': (0.7, 0.7, 0.7, 0.5),     # Light gray
}

# Global state for visualization
_bbox_batches = {}
_draw_handler = None
_is_enabled = False
_discipline_visibility = {}  # Set by legend when disciplines are toggled
_color_override = None       # Set by BIM Designer to grey-out in Design Mode

# S178: Outliner discipline proxy objects + search/pick state
_disc_proxy_objects = {}     # disc → object name (Outliner eye = hide_viewport)
_db_path_cache = None        # stored at load time for pick/search queries
_model_offset = None         # Vector — IFC→Blender offset, stored at load time
_highlighted_bboxes = []     # [(minX,minY,minZ,maxX,maxY,maxZ)] yellow highlight
_selected_element = {}       # last picked: {guid, name, disc, ifc_class, bbox}
_search_results = []         # full list of building results from last search (L1)
_building_elements = []      # elements within selected building matching term (L2)
_active_building = ""        # currently drilled-into building


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
    global _disc_proxy_objects, _highlighted_bboxes, _selected_element

    if not _is_enabled or not _bbox_batches:
        return

    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(1.0)
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')

    # Draw each discipline's batch — skip if hidden via Outliner proxy eye icon
    for discipline, batch in _bbox_batches.items():
        # Outliner eye icon: use hide_get() — respects collection eye toggle hierarchy.
        # (hide_viewport is the monitor icon, NOT the eye icon — wrong property)
        proxy_name = _disc_proxy_objects.get(discipline)
        if proxy_name:
            proxy = bpy.data.objects.get(proxy_name)
            if proxy and proxy.hide_get():
                continue
        # Legacy legend dict (on-screen toggle still works)
        if not _discipline_visibility.get(discipline, True):
            continue

        color = _color_override if _color_override else DISCIPLINE_COLORS.get(discipline, DISCIPLINE_COLORS['DEFAULT'])
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)

    # Draw search-result highlights in yellow (thick)
    if _highlighted_bboxes:
        hi_verts = []
        for hb in _highlighted_bboxes:
            hi_verts.extend(create_bbox_edges(hb))
        if hi_verts:
            hi_batch = batch_for_shader(shader, 'LINES', {"pos": hi_verts})
            shader.bind()
            shader.uniform_float("color", (1.0, 1.0, 0.0, 1.0))
            gpu.state.line_width_set(3.0)
            hi_batch.draw(shader)
            gpu.state.line_width_set(1.0)

    # Draw last-picked element in white (thicker)
    if _selected_element.get('bbox'):
        sel_verts = create_bbox_edges(_selected_element['bbox'])
        sel_batch = batch_for_shader(shader, 'LINES', {"pos": sel_verts})
        shader.bind()
        shader.uniform_float("color", (1.0, 1.0, 1.0, 1.0))
        gpu.state.line_width_set(4.0)
        sel_batch.draw(shader)
        gpu.state.line_width_set(1.0)

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
    global _bbox_batches, _draw_handler, _is_enabled, _db_path_cache, _disc_proxy_objects, _model_offset

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
    _db_path_cache = db_path
    _model_offset = offset
    print(f"[RTree] §CACHE db='{Path(db_path).name}' offset=({offset.x:.1f},{offset.y:.1f},{offset.z:.1f})")

    # S178: Create Outliner discipline collections + proxy objects
    # Each proxy empty: eye icon in Outliner → hide_viewport → GPU skips that batch
    _disc_proxy_objects.clear()
    parent_rtree = bpy.data.collections.get("Federation_RTree")
    if parent_rtree is None:
        parent_rtree = bpy.data.collections.new("Federation_RTree")
    if "Federation_RTree" not in {c.name for c in bpy.context.scene.collection.children}:
        bpy.context.scene.collection.children.link(parent_rtree)

    for disc in sorted(_bbox_batches.keys()):
        col_name = f"RTree_{disc}"
        disc_col = bpy.data.collections.get(col_name) or bpy.data.collections.new(col_name)
        if col_name not in {c.name for c in parent_rtree.children}:
            parent_rtree.children.link(disc_col)
        # One empty per discipline — eye icon controls hide_viewport
        obj_name = f"● {disc}"
        proxy = bpy.data.objects.get(obj_name) or bpy.data.objects.new(obj_name, None)
        proxy['federation_rtree_disc'] = disc
        proxy.hide_render = True
        proxy.empty_display_type = 'SPHERE'
        proxy.empty_display_size = 0.5
        rgba = DISCIPLINE_COLORS.get(disc, DISCIPLINE_COLORS['DEFAULT'])
        proxy.color = rgba  # viewport display color
        if obj_name not in {o.name for o in disc_col.objects}:
            disc_col.objects.link(proxy)
        _disc_proxy_objects[disc] = obj_name
        print(f"  §OUTLINER RTree_{disc} — proxy '{obj_name}' (eye=hide)")

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

    # Clear batches and search state
    _bbox_batches.clear()
    _highlighted_bboxes.clear()
    _selected_element.clear()
    _is_enabled = False

    # Remove discipline proxy objects + collections
    for obj_name in _disc_proxy_objects.values():
        obj = bpy.data.objects.get(obj_name)
        if obj:
            bpy.data.objects.remove(obj, do_unlink=True)
    _disc_proxy_objects.clear()
    parent_rtree = bpy.data.collections.get("Federation_RTree")
    if parent_rtree:
        for child in list(parent_rtree.children):
            bpy.data.collections.remove(child)
        bpy.data.collections.remove(parent_rtree)

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


def set_color_override(color: Optional[Tuple[float, float, float, float]]) -> None:
    """Override all discipline colors with a single color (e.g. grey for Design Mode).

    Called by BIM Designer's design_bbox module to mute existing Federation
    bboxes when entering Design Mode. Pass None to clear the override.
    """
    global _color_override
    _color_override = color


def clear_color_override() -> None:
    """Remove the color override — restore original discipline colors."""
    global _color_override
    _color_override = None


# ── S178: Search + Navigate ────────────────────────────────────────────────────

def navigate_to_element(search_term: str, context) -> dict:
    """Search elements across all buildings. Returns 1 representative per building.

    - Searches: element_name, guid, discipline, ifc_class, building name
    - Groups by building → 1 bbox (envelope of all matches) per building
    - Flies to the building with the most matches
    - Highlights one bbox per building (up to 10 buildings) in yellow
    """
    global _highlighted_bboxes, _db_path_cache, _model_offset, _search_results

    if not _db_path_cache:
        print("[RTree] §SEARCH FAIL _db_path_cache is None — load R-Tree first")
        return {}
    if not Path(_db_path_cache).exists():
        print(f"[RTree] §SEARCH FAIL db not found: {_db_path_cache}")
        return {}

    _highlighted_bboxes.clear()
    _search_results.clear()
    results = []
    term = search_term.strip()
    like = f"%{term}%"
    print(f"[RTree] §SEARCH term='{term}' db='{Path(_db_path_cache).name}'")

    try:
        conn = sqlite3.connect(_db_path_cache)
        cur = conn.cursor()

        # One row per building: envelope bbox of all matching elements + match count.
        # Sorted by match_count DESC so the richest building is flown to first.
        cur.execute("""
            SELECT m.building,
                   MIN(m.guid)          AS guid,
                   MIN(m.element_name)  AS element_name,
                   m.discipline,
                   m.ifc_class,
                   MIN(r.minX) AS mnX, MIN(r.minY) AS mnY, MIN(r.minZ) AS mnZ,
                   MAX(r.maxX) AS mxX, MAX(r.maxY) AS mxY, MAX(r.maxZ) AS mxZ,
                   COUNT(*)    AS match_count
            FROM elements_meta m
            JOIN elements_rtree r ON m.id = r.id
            WHERE m.element_name LIKE ?
               OR m.guid        =    ?
               OR m.discipline  =    ?
               OR m.ifc_class   LIKE ?
               OR m.building    LIKE ?
            GROUP BY m.building
            ORDER BY match_count DESC
            LIMIT 10
        """, (like, term, term.upper(), like, like))

        rows = cur.fetchall()
        conn.close()
        print(f"[RTree] §SEARCH buildings={len(rows)} "
              f"counts={[r[11] for r in rows]}")

        for building, guid, name, disc, ifc_class, mnX, mnY, mnZ, mxX, mxY, mxZ, count in rows:
            bbox = (mnX, mnY, mnZ, mxX, mxY, mxZ)
            _highlighted_bboxes.append(bbox)
            entry = {'guid': guid, 'name': name, 'disc': disc,
                     'ifc_class': ifc_class, 'bbox': bbox,
                     'building': building, 'count': count}
            results.append(entry)
            _search_results.append(entry)

    except Exception as e:
        print(f"[RTree] §SEARCH ERROR {e}")
        return {}

    if not results:
        print(f"[RTree] §SEARCH MISS — no buildings matched '{term}'")
        return {}

    # Fly to the building with most matches (first row after ORDER BY count DESC).
    # IFC coords → Blender coords: subtract model offset.
    first = results[0]['bbox']
    cx_ifc = (first[0] + first[3]) / 2
    cy_ifc = (first[1] + first[4]) / 2
    cz_ifc = (first[2] + first[5]) / 2
    ox = _model_offset.x if _model_offset else 0.0
    oy = _model_offset.y if _model_offset else 0.0
    oz = _model_offset.z if _model_offset else 0.0
    cx, cy, cz = cx_ifc - ox, cy_ifc - oy, cz_ifc - oz
    # view_distance: fit the building envelope, not a single element
    size = max(first[3]-first[0], first[4]-first[1], first[5]-first[2], 10.0)

    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            space = area.spaces[0]
            space.region_3d.view_location = Vector((cx, cy, cz))
            space.region_3d.view_distance = size * 1.5
            area.tag_redraw()
            break

    print(f"[RTree] §PROOF NAVIGATE buildings={len(results)} term='{search_term}' "
          f"best='{results[0]['building']}' count={results[0]['count']} "
          f"blender=({cx:.1f},{cy:.1f},{cz:.1f})")
    return results[0]


def fly_to_result(result_index: int, context) -> bool:
    """Fly viewport to a specific building result by index in _search_results."""
    if result_index < 0 or result_index >= len(_search_results):
        return False
    r = _search_results[result_index]
    bbox = r['bbox']
    cx_ifc = (bbox[0] + bbox[3]) / 2
    cy_ifc = (bbox[1] + bbox[4]) / 2
    cz_ifc = (bbox[2] + bbox[5]) / 2
    ox = _model_offset.x if _model_offset else 0.0
    oy = _model_offset.y if _model_offset else 0.0
    oz = _model_offset.z if _model_offset else 0.0
    cx, cy, cz = cx_ifc - ox, cy_ifc - oy, cz_ifc - oz
    size = max(bbox[3]-bbox[0], bbox[4]-bbox[1], bbox[5]-bbox[2], 10.0)
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces[0].region_3d.view_location = Vector((cx, cy, cz))
            area.spaces[0].region_3d.view_distance = size * 1.5
            area.tag_redraw()
            break
    print(f"[RTree] §FLY building='{r['building']}' blender=({cx:.1f},{cy:.1f},{cz:.1f})")
    return True


def fetch_building_elements(building: str, search_term: str) -> list:
    """Drill-down L2: fetch top 10 individual elements in building matching term.

    Highlights each element bbox in yellow. Clears L1 highlights.
    Returns list of element dicts for the UI list.
    """
    global _highlighted_bboxes, _building_elements, _active_building, _model_offset

    if not _db_path_cache or not Path(_db_path_cache).exists():
        return []

    _highlighted_bboxes.clear()
    _building_elements.clear()
    _active_building = building

    term = search_term.strip()
    like = f"%{term}%"

    try:
        conn = sqlite3.connect(_db_path_cache)
        cur = conn.cursor()
        cur.execute("""
            SELECT m.guid, m.element_name, m.discipline, m.ifc_class, m.storey,
                   r.minX, r.minY, r.minZ, r.maxX, r.maxY, r.maxZ
            FROM elements_meta m
            JOIN elements_rtree r ON m.id = r.id
            WHERE m.building = ?
              AND (m.element_name LIKE ?
                OR m.ifc_class   LIKE ?
                OR m.discipline  =    ?)
            LIMIT 10
        """, (building, like, like, term.upper()))
        rows = cur.fetchall()
        conn.close()
    except Exception as e:
        print(f"[RTree] §L2 ERROR {e}")
        return []

    for guid, name, disc, ifc_class, storey, mnX, mnY, mnZ, mxX, mxY, mxZ in rows:
        bbox = (mnX, mnY, mnZ, mxX, mxY, mxZ)
        _highlighted_bboxes.append(bbox)
        _building_elements.append({'guid': guid, 'name': name, 'disc': disc,
                                   'ifc_class': ifc_class, 'storey': storey or '',
                                   'bbox': bbox})

    print(f"[RTree] §L2 building='{building}' term='{term}' elements={len(_building_elements)}")
    return _building_elements


def fly_to_element(elem_index: int, context) -> bool:
    """Fly viewport to a specific element from L2 list. Highlights it white."""
    global _selected_element

    if elem_index < 0 or elem_index >= len(_building_elements):
        return False

    e = _building_elements[elem_index]
    bbox = e['bbox']
    cx_ifc = (bbox[0] + bbox[3]) / 2
    cy_ifc = (bbox[1] + bbox[4]) / 2
    cz_ifc = (bbox[2] + bbox[5]) / 2
    ox = _model_offset.x if _model_offset else 0.0
    oy = _model_offset.y if _model_offset else 0.0
    oz = _model_offset.z if _model_offset else 0.0
    cx, cy, cz = cx_ifc - ox, cy_ifc - oy, cz_ifc - oz
    size = max(bbox[3]-bbox[0], bbox[4]-bbox[1], bbox[5]-bbox[2], 0.5)

    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces[0].region_3d.view_location = Vector((cx, cy, cz))
            area.spaces[0].region_3d.view_distance = max(size * 6.0, 5.0)
            area.tag_redraw()
            break

    _selected_element = {**e, 't': 0}
    print(f"[RTree] §ELEMENT guid={e['guid'][:12]} class={e['ifc_class']} storey='{e['storey']}'")
    return True


def pick_element_at_ray(ray_origin: Vector, ray_dir: Vector) -> dict:
    """Find the element whose bbox the given world-space ray passes through.

    Uses R-tree spatial pre-filter then precise ray-AABB test.
    Returns element info dict or {} if nothing hit.
    Updates _selected_element global (drawn white in viewport).
    """
    global _selected_element, _db_path_cache, _model_offset

    # ── Diagnostic guards ──
    if not _db_path_cache:
        print("[RTree] §PICK FAIL _db_path_cache is None — load R-Tree first")
        return {}
    if not Path(_db_path_cache).exists():
        print(f"[RTree] §PICK FAIL db not found: {_db_path_cache}")
        return {}

    # Ray is in Blender space; R-tree stores IFC coords.
    # Translate ray origin into IFC space by adding the model offset.
    off = _model_offset if _model_offset else Vector((0, 0, 0))
    ifc_origin = ray_origin + off

    print(f"[RTree] §PICK ray_blender=({ray_origin.x:.1f},{ray_origin.y:.1f},{ray_origin.z:.1f}) "
          f"offset=({off.x:.1f},{off.y:.1f},{off.z:.1f}) "
          f"ray_ifc=({ifc_origin.x:.1f},{ifc_origin.y:.1f},{ifc_origin.z:.1f})")

    # Build coarse bounding box around the IFC-space ray for SQL pre-filter.
    # Sample points along ray: t = 0.5 .. 500m (direction unchanged — it's unit vec)
    pts = [ifc_origin + ray_dir * t for t in (0.5, 5, 50, 200, 500)]
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    zs = [p.z for p in pts]
    margin = 2.0  # metres pick tolerance
    q_mnX, q_mxX = min(xs) - margin, max(xs) + margin
    q_mnY, q_mxY = min(ys) - margin, max(ys) + margin
    q_mnZ, q_mxZ = min(zs) - margin, max(zs) + margin

    print(f"[RTree] §PICK sql_box X=[{q_mnX:.1f},{q_mxX:.1f}] Y=[{q_mnY:.1f},{q_mxY:.1f}] Z=[{q_mnZ:.1f},{q_mxZ:.1f}]")

    try:
        conn = sqlite3.connect(_db_path_cache)
        cur = conn.cursor()
        cur.execute("""
            SELECT m.guid, m.element_name, m.discipline, m.ifc_class,
                   r.minX, r.minY, r.minZ, r.maxX, r.maxY, r.maxZ
            FROM elements_meta m
            JOIN elements_rtree r ON m.id = r.id
            WHERE r.minX <= ? AND r.maxX >= ?
              AND r.minY <= ? AND r.maxY >= ?
              AND r.minZ <= ? AND r.maxZ >= ?
            LIMIT 200
        """, (q_mxX, q_mnX, q_mxY, q_mnY, q_mxZ, q_mnZ))
        candidates = cur.fetchall()
        conn.close()
        print(f"[RTree] §PICK candidates={len(candidates)}")
    except Exception as e:
        print(f"[RTree] §PICK SQL ERROR {e}")
        return {}

    if not candidates:
        print("[RTree] §PICK MISS — 0 candidates from spatial pre-filter")
        return {}

    # Precise ray-AABB test (slab method) in IFC space — find closest hit
    best_t = float('inf')
    best = None
    ox, oy, oz = ifc_origin.x, ifc_origin.y, ifc_origin.z
    dx, dy, dz = ray_dir.x, ray_dir.y, ray_dir.z

    for guid, name, disc, ifc_class, mnX, mnY, mnZ, mxX, mxY, mxZ in candidates:
        t_min, t_max = -float('inf'), float('inf')
        for o_ax, d_ax, lo, hi in ((ox, dx, mnX, mxX),
                                    (oy, dy, mnY, mxY),
                                    (oz, dz, mnZ, mxZ)):
            if abs(d_ax) < 1e-9:
                if o_ax < lo or o_ax > hi:
                    t_min = float('inf')
                    break
            else:
                t1, t2 = (lo - o_ax) / d_ax, (hi - o_ax) / d_ax
                if t1 > t2:
                    t1, t2 = t2, t1
                t_min = max(t_min, t1)
                t_max = min(t_max, t2)
                if t_min > t_max:
                    break

        if t_min <= t_max and t_min < best_t and t_min > 0:
            best_t = t_min
            best = (guid, name, disc, ifc_class, (mnX, mnY, mnZ, mxX, mxY, mxZ))

    if best is None:
        print(f"[RTree] §PICK MISS — slab test: {len(candidates)} candidates, 0 hits")
        return {}

    guid, name, disc, ifc_class, bbox = best
    _selected_element = {'guid': guid, 'name': name, 'disc': disc,
                         'ifc_class': ifc_class, 'bbox': bbox, 't': best_t}
    print(f"[RTree] §PROOF PICK guid={guid[:12]} disc={disc} class={ifc_class} "
          f"t={best_t:.1f}m candidates={len(candidates)}")
    return _selected_element
