"""
BBox Wireframe Visualization for Federation Elements
Phase 2: BBox Semantic Geometry System

Renders federation elements as colored wireframe bounding boxes using GPU batch drawing.
Enables instant loading of 44K+ elements with <10MB memory usage.
"""

import bpy
import gpu
import re as _re
import sqlite3
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, Matrix
from pathlib import Path
from typing import List, Tuple, Optional, Dict

# Discipline colors (from federation module)
DISCIPLINE_COLORS = {
    'ACMV': (0.0, 0.75, 1.0, 1.0),      # Cyan/Blue
    'FP': (1.0, 0.0, 0.0, 1.0),          # Red
    'ELEC': (1.0, 0.85, 0.0, 1.0),       # Amber (distinct from yellow highlights)
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
    'MEP': (0.0, 0.85, 0.7, 1.0),        # Teal
    'HVAC': (0.2, 0.6, 0.9, 1.0),        # Sky blue
    'VENT': (0.4, 0.9, 0.6, 1.0),        # Mint green
    'HEAT': (0.95, 0.35, 0.15, 1.0),     # Warm orange-red
    'SANI': (0.3, 0.5, 0.9, 1.0),        # Steel blue
    'DRAIN': (0.15, 0.35, 0.7, 1.0),     # Deep blue
    'LIFT': (0.7, 0.3, 0.7, 1.0),        # Violet
    'CONV': (0.85, 0.65, 0.2, 1.0),      # Gold
    'SEC': (0.9, 0.2, 0.5, 1.0),         # Pink-red
    'LIGHT': (1.0, 0.95, 0.4, 1.0),      # Bright yellow
    # Coastal Oasis river restoration disciplines
    'GEO': (0.15, 0.4, 0.65, 0.5),       # Blue water (semi-transparent)
    'BOOM': (0.95, 0.55, 0.1, 1.0),      # High-viz orange (boom barriers)
    'FAC': (0.6, 0.6, 0.6, 1.0),         # Concrete gray (facilities)
    'IOT': (0.2, 0.8, 0.3, 1.0),         # Monitoring green (IoT sensors)
    'DEFAULT': (0.7, 0.7, 0.7, 0.5),     # Light gray
}

# S191: auto-generate diverse colors for unknown disciplines
# Uses golden-angle hue spacing for maximum visual separation
_auto_color_cache = {}

def get_discipline_color(disc):
    """Get color for a discipline — known or auto-generated."""
    if disc in DISCIPLINE_COLORS:
        return DISCIPLINE_COLORS[disc]
    if disc in _auto_color_cache:
        return _auto_color_cache[disc]
    # Generate from name hash — golden angle ensures diverse hues
    import colorsys
    h = (hash(disc) * 0.618033988749895) % 1.0  # golden ratio
    s = 0.7 + (hash(disc + '_s') % 30) / 100  # 0.7-1.0 saturation
    v = 0.8 + (hash(disc + '_v') % 20) / 100  # 0.8-1.0 value (bright)
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    color = (r, g, b, 1.0)
    _auto_color_cache[disc] = color
    return color

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

# S180: Stingy Mesh Loader state
_loaded_collections = {}     # label → [object_names]
_loaded_guids = set()        # S185: all guids that have been meshed (dedup across presses)
_library_blend_cache = None  # absolute path to library.blend, resolved at RTree load
_library_db_cache = None     # S189: absolute path to component_library.db (BLOB source)

# S183: Building storey list — populated by FedRTreeCountBuilding
_building_storeys = []       # storeys for active building, from last count query
_building_storey_bboxes = {} # S186-s2: storey → {bbox, count} pre-computed at count time

# S186: Drill-down state
_active_storey = ""          # currently drilled-into storey (empty = all)
_search_suggestions = []     # 5 random meaningful search terms, populated at load
_building_class_groups = []  # [{ifc_class, count}] — fallback breakdown when no storeys
_active_disc_filter = ""     # S187: currently filtered discipline (empty = none)
_disc_class_groups = []      # S187: [{ifc_class, count}] — types within active disc filter
_has_building_column = False # True if elements_meta has 'building' column (multi-building DB)
_single_building_name = ""   # synthetic building name for single-building DBs
_building_disc_counts = {}   # discipline → count (dynamic, replaces hardcoded 5 props)
_building_total_all = 0      # S186-s2: building-level total (not storey-scoped) for pre-warm threshold
_prewarmed_discs = set()     # S186: disciplines already pre-warmed (per-disc lazy warm)
_overnight_running = False   # S186: True while overnight loader is active
_overnight_paused = False    # S186: True while paused (modal stays alive)
_overnight_progress = ""     # S186: status text for UI display
_overnight_placed = 0        # S186: total elements placed so far
_overnight_total = 0         # S186: total elements to place
_overnight_shortcut_factor = 0  # S186-s2: 0 = not shown, >0 = live ×N multiplier for SHORT-CUT button
_overnight_shortcut_eta = ""   # S186-s2: offline ETA string for display on SHORT-CUT button

# S186-s2: Offline bake handoff state
_baking_buildings = {}       # building_name → {process, start_time, total, offline_eta, baked_path, db_path}
_bake_offer_shown = set()    # buildings that already saw the offer (don't re-show)
_bake_queue = []             # S188: buildings waiting to bake, sorted smallest-first
_MAX_BAKE_WORKERS = 4        # S188: max concurrent bake subprocesses
_CHUNK_THRESHOLD = 100000    # S189: split into chunks above this element count
_bake_done = {}              # S189: building_name → baked_path (completed, ready to reopen)
_baked_on_disk = None        # S196: set of building names with _baked.blend on disk (lazy)
_linking_active = False      # S191: True during save_post linking (HUD shows DO NOT CLOSE)
_merge_done_path = ""        # S189: path to merged session .blend (ready to reopen)

# S193: DLOD auto-linker state
_building_centres = {}       # building_name → (cx, cy, cz) in Blender coords
_baked_files = {}            # building_name → [Path, ...] (baked .blend files on disk)
_dlod_linked = {}            # building_name → True (currently auto-linked by DLOD)
_dlod_blacklist = set()      # buildings user manually shredded — don't auto-relink
_dlod_eye_pos = None         # (x,y,z) updated every frame by draw handler
_dlod_draw_handler = None    # draw handler for eye position tracking
_dlod_enabled = False        # True when auto-stream is active
_DLOD_RADIUS = 300           # metres — link within this distance
_DLOD_HYSTERESIS = 50        # unlink at radius + hysteresis to prevent thrashing
_DLOD_ELEMENT_BUDGET = 250000  # max total elements across all linked buildings
_DLOD_MAX_BUILDING = 10000     # skip auto-link for buildings above this (use manual MESH)
_building_element_counts = {}  # building_name → element count
_dlod_linked_elements = 0      # current total elements in linked buildings

# S195: Direct DB streaming state
_direct_stream_enabled = False   # True when direct-stream timer is active
_direct_stream_guids = set()     # guids currently in viewport (for dedup + removal)
_direct_stream_objects = {}      # guid → bpy.types.Object (for distance-based removal)
_direct_stream_buildings = {}    # building_name → set(guid) (track per-building)
_DIRECT_STREAM_RADIUS = 300      # metres — stream buildings within this distance
_DIRECT_STREAM_BUDGET = 200000   # max total elements — user shreds manually when needed
_DIRECT_STREAM_BATCH = 500       # elements per tick
_DIRECT_STREAM_SHELL_DISCS = {'ARC', 'STR'}  # shell disciplines — streamed first
_DIRECT_STREAM_NEAR = 50         # metres — within this, stream all disciplines
_direct_stream_disc_phase = {}   # building_name → 'envelope'|'envelope_done'|'shell'|'shell_done'|'detail'|'done'
_direct_stream_active_bld = None # building currently being streamed — finish before switching
_direct_stream_last_bld = None   # last building that was streamed (for HUD when paused)
# S197: camera-settle — halt streaming while user navigates
_direct_stream_cam_last = None   # (x, y, z) last camera position for settle detection
_direct_stream_cam_still_t = 0.0 # time.time() when camera last became still
_DIRECT_STREAM_SETTLE_S = 1.0   # seconds camera must be still before streaming resumes
_DIRECT_STREAM_CAM_THRESH = 2.0 # metres — movement beyond this = user is navigating
_direct_stream_bld_index = {}    # building_name → counter (e.g. "01") for Outliner labels
_direct_stream_free_indices = [] # recycled counters from shredded buildings
_direct_stream_next_index = 1    # next counter to assign if no free indices
_direct_stream_disc_totals = {}  # building_name → {disc: count} — total per discipline from DB
_direct_stream_disc_loaded = {}  # building_name → {disc: count} — loaded so far per discipline
_direct_stream_shred_blacklist = []  # last 3 shredded buildings — don't re-stream immediately
_direct_stream_auto_shred = False  # True = auto-shred furthest building when lagging
_direct_stream_lag_history = []    # last N tick_ms values for budget tuning
_DIRECT_STREAM_LAG_TARGET = 1500   # ms — target max tick time (user feels lag above this)
# S198: Envelope-first streaming
_direct_stream_bld_bbox = {}  # building_name → (minX, maxX, minY, maxY, minZ, maxZ)
_DIRECT_STREAM_ENVELOPE_CLASSES = (
    'IfcWall', 'IfcWallStandardCase', 'IfcRoof', 'IfcSlab',
    'IfcCurtainWall', 'IfcPlate', 'IfcDoor', 'IfcWindow', 'IfcCovering',
    'IfcRailing', 'IfcMember', 'IfcBeam', 'IfcColumn', 'IfcBuildingElementProxy',
)
_DIRECT_STREAM_MERGE_MIN = 20   # min elements in group to trigger merge
_DIRECT_STREAM_MERGE_VOL = 2.0  # max avg bbox volume (m³) for merge

# S182: Progressive load state
LOAD_DISC_ORDER = ['ARC', 'STR', 'MEP', 'ELEC', 'FP']
_load_progress = {}          # building → {'disc_idx': int, 'offset': int, 'exhausted': bool}


# S185: Pre-warm — background-link ALL building meshes in one shot
def _prewarm_building_meshes():
    """One-shot timer: link ALL geometry hashes for active building from library.blend.
    Fires 0.5s after cockpit drill-in. Single library.blend open (~3s) loads
    every unique mesh for the building. After this, +MESH never opens the file."""
    import bpy
    import sqlite3
    import time
    building = _active_building
    if not building or not _db_path_cache or not _library_blend_cache:
        return None
    # S185: show wait cursor during pre-warm
    for window in bpy.context.window_manager.windows:
        window.cursor_set('WAIT')
    t0 = time.time()
    conn = sqlite3.connect(_db_path_cache)
    if _has_building_column:
        hashes = [r[0] for r in conn.execute(
            "SELECT DISTINCT i.geometry_hash FROM elements_meta m "
            "JOIN element_instances i ON m.guid = i.guid "
            "WHERE m.building = ? AND i.geometry_hash IS NOT NULL",
            (building,)
        ).fetchall()]
    else:
        hashes = [r[0] for r in conn.execute(
            "SELECT DISTINCT i.geometry_hash FROM elements_meta m "
            "JOIN element_instances i ON m.guid = i.guid "
            "WHERE i.geometry_hash IS NOT NULL"
        ).fetchall()]
    conn.close()
    already = {m.name for m in bpy.data.meshes}
    to_link = [h for h in hashes if h not in already]
    if to_link:
        from pathlib import Path
        if not Path(_library_blend_cache).exists():
            for window in bpy.context.window_manager.windows:
                window.cursor_set('DEFAULT')
            return None
        with bpy.data.libraries.load(_library_blend_cache, link=True) as (df, dt):
            available = set(df.meshes)
            dt.meshes = [h for h in to_link if h in available]
        elapsed_ms = (time.time() - t0) * 1000
        print(f"[S185] §PROOF PREWARM building={building} "
              f"linked={len(to_link)}/{len(hashes)} unique hashes {elapsed_ms:.0f}ms")
    else:
        print(f"[S185] §PROOF PREWARM building={building} "
              f"all {len(hashes)} already cached")
    for window in bpy.context.window_manager.windows:
        window.cursor_set('DEFAULT')
    return None  # one-shot, done


def prewarm_discipline(discipline: str):
    """S186: Link all geometry hashes for ONE discipline from library.blend.
    Called on first +DISC press. One library.blend open, scoped to discipline.
    After this, subsequent presses for the same discipline are instant (link=0ms)."""
    import bpy
    import sqlite3
    import time
    building = _active_building
    if not building or not _db_path_cache or not _library_blend_cache:
        return
    if discipline in _prewarmed_discs:
        return  # already done
    for window in bpy.context.window_manager.windows:
        window.cursor_set('WAIT')
    t0 = time.time()
    conn = sqlite3.connect(_db_path_cache)
    bld_clause = "m.building = ? AND" if _has_building_column else ""
    bld_params = (building,) if _has_building_column else ()
    hashes = [r[0] for r in conn.execute(f"""
        SELECT DISTINCT i.geometry_hash FROM elements_meta m
        JOIN element_instances i ON m.guid = i.guid
        WHERE {bld_clause} m.discipline = ? AND i.geometry_hash IS NOT NULL
    """, bld_params + (discipline,)).fetchall()]
    conn.close()
    already = {m.name for m in bpy.data.meshes}
    to_link = [h for h in hashes if h not in already]
    if to_link:
        from pathlib import Path
        if not Path(_library_blend_cache).exists():
            for window in bpy.context.window_manager.windows:
                window.cursor_set('DEFAULT')
            return
        with bpy.data.libraries.load(_library_blend_cache, link=True) as (df, dt):
            available = set(df.meshes)
            dt.meshes = [h for h in to_link if h in available]
    _prewarmed_discs.add(discipline)
    elapsed_ms = (time.time() - t0) * 1000
    print(f"[S186] §PROOF PREWARM_DISC disc={discipline} building={building} "
          f"linked={len(to_link)}/{len(hashes)} hashes {elapsed_ms:.0f}ms")
    for window in bpy.context.window_manager.windows:
        window.cursor_set('DEFAULT')


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


def load_federation_bboxes(db_path: str, limit: Optional[int] = None,
                          progress_cb=None) -> Dict[str, List[Tuple]]:
    """
    Load bounding boxes from federation database, grouped by discipline.

    Args:
        db_path: Path to federation database
        limit: Optional limit on number of elements (for testing)
        progress_cb: Optional callback(current, total) for progress reporting

    Returns:
        Dict mapping discipline to list of (bbox, guid) tuples
    """
    if not Path(db_path).exists():
        print(f"Federation database not found: {db_path}")
        return {}

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # S185: get total count first for progress reporting
    if progress_cb:
        count_q = "SELECT COUNT(*) FROM elements_meta"
        total = cursor.execute(count_q).fetchone()[0]
        progress_cb(0, total)

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
    for i, row in enumerate(rows):
        discipline = row[0]
        bbox = tuple(row[1:7])
        guid = row[7]

        if discipline not in discipline_bboxes:
            discipline_bboxes[discipline] = []

        discipline_bboxes[discipline].append((bbox, guid))

        # S185: progress callback every 100K rows
        if progress_cb and i % 100000 == 0 and i > 0:
            progress_cb(i, len(rows))

    if progress_cb:
        progress_cb(len(rows), len(rows))

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


def _dlod_track_eye():
    """POST_VIEW draw callback — runs every frame, updates eye position for DLOD."""
    global _dlod_eye_pos
    try:
        rv3d = bpy.context.region_data
        if rv3d:
            eye = rv3d.view_matrix.inverted().translation
            _dlod_eye_pos = (eye.x, eye.y, eye.z)
    except Exception:
        pass


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
        # S198: aggressive bbox fade — gone by 40%, stays gone until new building starts
        _has_ds = bool(_direct_stream_buildings)
        if _has_ds:
            _ab = _direct_stream_active_bld
            if _ab:
                _ab_done = len(_direct_stream_buildings.get(_ab, set()))
                # Use ARC+STR total (envelope) not all disciplines
                _ab_disc = _direct_stream_disc_totals.get(_ab, {})
                _ab_total = sum(_ab_disc.get(d, 0) for d in ('ARC', 'STR')) or _building_element_counts.get(_ab, 1) or 1
                _pct = min(_ab_done / _ab_total, 1.0)
                if _pct < 0.05:
                    alpha = 0.10  # brief flash at start of new building
                else:
                    # Gone by 40% progress
                    alpha = max(0.01, 0.10 * max(0.0, (0.4 - _pct) / 0.4))
            else:
                # Done or flying — stay invisible
                alpha = 0.01
            color = (color[0], color[1], color[2], alpha)
        elif _active_building:
            if _loaded_collections:
                alpha = 0.15
            else:
                alpha = 0.25
            color = (color[0], color[1], color[2], alpha)
        shader.bind()
        shader.uniform_float("color", color)
        batch.draw(shader)

    # Draw search-result highlights in yellow
    # S187: thin line for single-element focus, thicker for multi-element results
    if _highlighted_bboxes:
        hi_verts = []
        for hb in _highlighted_bboxes:
            hi_verts.extend(create_bbox_edges(hb))
        if hi_verts:
            hi_batch = batch_for_shader(shader, 'LINES', {"pos": hi_verts})
            shader.bind()
            gpu.state.blend_set('ALPHA')
            shader.uniform_float("color", (1.0, 1.0, 0.3, 0.35))
            gpu.state.line_width_set(1.0)
            hi_batch.draw(shader)
            gpu.state.line_width_set(1.0)

    # Draw last-picked element in white — semi-transparent (X-ray feel, not a cage)
    if _selected_element.get('bbox'):
        sel_verts = create_bbox_edges(_selected_element['bbox'])
        sel_batch = batch_for_shader(shader, 'LINES', {"pos": sel_verts})
        shader.bind()
        gpu.state.blend_set('ALPHA')
        shader.uniform_float("color", (1.0, 1.0, 1.0, 0.35))
        gpu.state.line_width_set(2.0)
        sel_batch.draw(shader)
        gpu.state.line_width_set(1.0)

    gpu.state.blend_set('NONE')


def _find_library_blend(db_path: str) -> Optional[str]:
    """Locate library.blend by walking up from db_path (up to 5 levels).

    Tries: <parent>/library/library.blend at each level.
    Returns absolute path string, or None if not found.
    """
    search = Path(db_path).parent
    for _ in range(5):
        candidate = search / 'library' / 'library.blend'
        if candidate.exists():
            return str(candidate)
        search = search.parent
    return None


def enable_bbox_visualization(db_path: str, limit: Optional[int] = None) -> Tuple[bool, str]:
    """
    Enable bounding box visualization in viewport.

    Args:
        db_path: Path to federation database
        limit: Optional limit for testing (None = all elements)

    Returns:
        (success: bool, message: str)
    """
    global _bbox_batches, _draw_handler, _is_enabled, _db_path_cache, _disc_proxy_objects, _model_offset, _library_blend_cache, _library_db_cache

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
    # S186: detect building column (single vs multi-building DB)
    global _has_building_column, _single_building_name
    try:
        _tc = sqlite3.connect(db_path)
        cols = [r[1] for r in _tc.execute("PRAGMA table_info(elements_meta)").fetchall()]
        _has_building_column = 'building' in cols
        if not _has_building_column:
            # Derive name from DB filename (e.g. LTU_AHouse_extracted.db → LTU_AHouse)
            _single_building_name = Path(db_path).stem.replace('_extracted', '').replace('_fine_disc', '')
        _tc.close()
    except Exception:
        _has_building_column = False
    print(f"[S186] §CACHE has_building_col={_has_building_column} single='{_single_building_name}'")
    # S186: populate search suggestions
    _populate_search_suggestions(db_path)
    # S180: resolve library.blend once at load time
    _library_blend_cache = _find_library_blend(db_path)
    if _library_blend_cache:
        print(f"[RTree] §CACHE library_blend='{Path(_library_blend_cache).name}'")
    else:
        print("[RTree] §CACHE library_blend=NOT_FOUND (legacy bake unavailable)")

    # S189: resolve component_library.db independently (BLOB tessellation source)
    _library_db_cache = None
    _db_candidates = []
    if _library_blend_cache:
        _db_candidates.append(Path(_library_blend_cache).parent / "component_library.db")
    for _anc in Path(db_path).resolve().parents:
        _db_candidates.append(_anc / "library" / "component_library.db")
    for _dbc in _db_candidates:
        if _dbc.exists():
            _library_db_cache = str(_dbc.resolve())
            break
    if _library_db_cache:
        print(f"[S189] §CACHE library_db='{Path(_library_db_cache).name}' "
              f"path={_library_db_cache}")
    else:
        print("[S189] §CACHE library_db=NOT_FOUND (BLOB path unavailable)")

    # S193: Cache building centres for DLOD auto-linker
    _building_centres.clear()
    _building_element_counts.clear()
    try:
        _bc_conn = sqlite3.connect(db_path)
        _bc_rows = _bc_conn.execute(
            "SELECT m.building, COUNT(*), "
            "  (MIN(r.minX)+MAX(r.maxX))/2, (MIN(r.minY)+MAX(r.maxY))/2, "
            "  (MIN(r.minZ)+MAX(r.maxZ))/2 "
            "FROM elements_rtree r JOIN elements_meta m ON r.id = m.rowid "
            "GROUP BY m.building"
        ).fetchall() if _has_building_column else []
        _bc_conn.close()
        for _bld, _cnt, _cx, _cy, _cz in _bc_rows:
            if _bld:
                _building_centres[_bld] = (_cx, _cy, _cz)  # raw IFC coords, same as R-tree
                _building_element_counts[_bld] = _cnt
        print(f"[S193] §CACHE building_centres={len(_building_centres)} "
              f"total_elements={sum(_building_element_counts.values()):,}")
    except Exception as _bce:
        print(f"[S193] §CACHE building_centres WARN: {_bce}")

    # S193: Scan baked/ for existing files
    _baked_files.clear()
    _dlod_linked.clear()
    _dlod_blacklist.clear()
    try:
        for _anc in Path(db_path).resolve().parents:
            _br = _anc / "DAGCompiler" / "baked"
            if _br.exists():
                import re as _re_bk
                for _sub in _br.iterdir():
                    if _sub.is_dir() and _sub.name != "temp":
                        for _bf in _sub.glob("*.blend"):
                            _bn = _re_bk.sub(r'(_baked|_chunk\d+)$', '', _bf.stem)
                            _baked_files.setdefault(_bn, []).append(_bf)
                break
        print(f"[S193] §CACHE baked_files={len(_baked_files)} buildings")
    except Exception as _bfe:
        print(f"[S193] §CACHE baked_files WARN: {_bfe}")

    # S178: Create Outliner discipline collections + proxy objects
    # Each proxy empty: eye icon in Outliner → hide_viewport → GPU skips that batch
    # S186: name the parent collection after the project so user knows what's loaded
    _disc_proxy_objects.clear()
    project_name = Path(db_path).stem.replace('_extracted', '').replace('_fine_disc', '').replace('_backup_coarse_disc', '')
    rtree_col_name = f"{project_name}_RTree"
    parent_rtree = bpy.data.collections.get(rtree_col_name)
    if parent_rtree is None:
        # Remove old generic name if exists
        old = bpy.data.collections.get("Federation_RTree")
        if old:
            old.name = rtree_col_name
            parent_rtree = old
        else:
            parent_rtree = bpy.data.collections.new(rtree_col_name)
    if rtree_col_name not in {c.name for c in bpy.context.scene.collection.children}:
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

            # Frame viewport + auto clip for model extent
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            space = area.spaces[0]
                            # Set view location and distance
                            space.region_3d.view_location = center
                            space.region_3d.view_distance = max_dim * 1.5
                            # S185: auto clip — fit to model extent so user
                            # never needs to manually set View End Clip.
                            # clip_start stays small (0.1m) so close-up viewing works.
                            space.clip_end = max(max_dim * 4.0, 5000.0)
                            space.clip_start = 0.1
                            break

            print(f"Viewport: Framed to center ({center[0]:.1f}, {center[1]:.1f}, {center[2]:.1f}) "
                  f"clip_end={max(max_dim * 4.0, 5000.0):.0f}")

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


# ── S186: Search suggestions ──────────────────────────────────────────────

def _populate_search_suggestions(db_path: str):
    """S187: Build clickable quick-pick buttons for idle panel.

    Strategy: top 3 IFC classes by count (most useful to click),
    top 2 disciplines, 1 building (if multi-building), and '*' (show all).
    Deterministic — no random shuffle, most popular first.
    """
    global _search_suggestions
    _search_suggestions.clear()
    try:
        conn = sqlite3.connect(db_path)
        # Top IFC classes by frequency — deterministic, most popular first
        classes = [r[0] for r in conn.execute(
            "SELECT ifc_class FROM elements_meta "
            "WHERE ifc_class IS NOT NULL "
            "GROUP BY ifc_class ORDER BY COUNT(*) DESC LIMIT 10"
        ).fetchall()]
        seen = set()
        for c in classes:
            short = c.replace('Ifc', '').replace('StandardCase', '')
            if short and short not in seen:
                _search_suggestions.append(short)
                seen.add(short)
            if len(_search_suggestions) >= 3:
                break
        # Top 2 disciplines by count
        discs = [r[0] for r in conn.execute(
            "SELECT discipline, COUNT(*) as cnt FROM elements_meta "
            "WHERE discipline IS NOT NULL "
            "GROUP BY discipline ORDER BY cnt DESC LIMIT 2"
        ).fetchall()]
        for d in discs:
            if d not in seen:
                _search_suggestions.append(d)
                seen.add(d)
        # All unique building types (if multi-building DB), deduped by base name
        if _has_building_column:
            buildings = [r[0] for r in conn.execute(
                "SELECT building FROM elements_meta "
                "WHERE building IS NOT NULL AND building != '' "
                "GROUP BY building ORDER BY COUNT(*) DESC"
            ).fetchall()]
            bases_ordered = []
            bases_seen = set()
            for b in buildings:
                base = _re.sub(r'^[TS]\d+_(\d+_)?', '', b)
                if base and base not in bases_seen and base not in seen:
                    bases_ordered.append(base)
                    bases_seen.add(base)
            _search_suggestions.extend(bases_ordered)
        # Always add '*' — show all buildings
        _search_suggestions.append("*")
        conn.close()
        print(f"[S187] §SUGGESTIONS {_search_suggestions}")
    except Exception as e:
        print(f"[S187] §SUGGESTIONS ERROR {e}")


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
    # S186: wildcard support — * maps to SQL % for LIKE patterns
    # '*' alone → all buildings; 'duct*' → starts with; '*door' → ends with
    is_wildcard_all = (term == '*')
    if '*' in term:
        like = term.replace('*', '%')
    else:
        like = f"%{term}%"
    print(f"[RTree] §SEARCH term='{term}' like='{like}' db='{Path(_db_path_cache).name}'")

    try:
        conn = sqlite3.connect(_db_path_cache)
        cur = conn.cursor()

        # One row per building: envelope bbox of all matching elements + match count.
        # LIMIT 500 to survive tile-heavy sandboxes (43 tiles × 25 buildings).
        # Python dedup (below) collapses tiles to base types, caps display at 10.
        if not _has_building_column:
            # S186: single-building DB — no building column, synthesise building name
            bld_name = _single_building_name or Path(_db_path_cache).stem
            if is_wildcard_all:
                cur.execute("""
                    SELECT ? AS building,
                           MIN(m.guid), MIN(m.element_name),
                           MIN(m.discipline), MIN(m.ifc_class),
                           MIN(r.minX), MIN(r.minY), MIN(r.minZ),
                           MAX(r.maxX), MAX(r.maxY), MAX(r.maxZ),
                           COUNT(*) AS match_count
                    FROM elements_meta m
                    JOIN elements_rtree r ON m.id = r.id
                """, (bld_name,))
            else:
                cur.execute("""
                    SELECT ? AS building,
                           MIN(m.guid), MIN(m.element_name),
                           MIN(m.discipline), MIN(m.ifc_class),
                           MIN(r.minX), MIN(r.minY), MIN(r.minZ),
                           MAX(r.maxX), MAX(r.maxY), MAX(r.maxZ),
                           COUNT(*) AS match_count
                    FROM elements_meta m
                    JOIN elements_rtree r ON m.id = r.id
                    WHERE m.element_name LIKE ?
                       OR m.guid        =    ?
                       OR m.discipline  =    ?
                       OR m.ifc_class   LIKE ?
                """, (bld_name, like, term, term.upper(), like))
        elif is_wildcard_all:
            # S186: bare '*' — list all buildings, no element filter
            cur.execute("""
                SELECT m.building,
                       MIN(m.guid)          AS guid,
                       MIN(m.element_name)  AS element_name,
                       MIN(m.discipline)    AS discipline,
                       MIN(m.ifc_class)     AS ifc_class,
                       MIN(r.minX) AS mnX, MIN(r.minY) AS mnY, MIN(r.minZ) AS mnZ,
                       MAX(r.maxX) AS mxX, MAX(r.maxY) AS mxY, MAX(r.maxZ) AS mxZ,
                       COUNT(*)    AS match_count
                FROM elements_meta m
                JOIN elements_rtree r ON m.id = r.id
                GROUP BY m.building
                ORDER BY match_count DESC
                LIMIT 500
            """)
        else:
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
                LIMIT 500
            """, (like, term, term.upper(), like, like))

        rows = cur.fetchall()
        conn.close()

        # S182: deduplicate by base building type (strip T\d+_ tile prefix).
        # When a city has 18 tiles of LTU_AHouse, show one entry not 10.
        # Fly to the tile with most matches (already first by ORDER BY match_count DESC).
        def _building_base(name):
            # Strip tile prefix: T0_, T12_, S0_0_, S31_0_, etc.
            return _re.sub(r'^[TS]\d+_(\d+_)?', '', name)

        seen_base = set()
        tile_counts = {}   # base → total tile count across all rows
        for row in rows:
            base = _building_base(row[0])
            tile_counts[base] = tile_counts.get(base, 0) + 1

        deduped_rows = []
        for row in rows:
            base = _building_base(row[0])
            if base not in seen_base:
                seen_base.add(base)
                deduped_rows.append((row, tile_counts[base]))
            if len(deduped_rows) == 10:
                break

        print(f"[RTree] §SEARCH raw_buildings={len(rows)} deduped={len(deduped_rows)} "
              f"counts={[r[0][11] for r in deduped_rows]}")

        for (building, guid, name, disc, ifc_class, mnX, mnY, mnZ, mxX, mxY, mxZ, count), n_tiles in deduped_rows:
            bbox = (mnX, mnY, mnZ, mxX, mxY, mxZ)
            # S189z: skip building envelope highlight only for single-building DBs
            # (no building column = whole scene IS the building, no selection needed)
            if _has_building_column:
                _highlighted_bboxes.append(bbox)
            entry = {'guid': guid, 'name': name, 'disc': disc,
                     'ifc_class': ifc_class, 'bbox': bbox,
                     'building': building, 'count': count,
                     'tile_count': n_tiles}
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
    """Fly viewport to a specific building result by index in _search_results.

    If the building has multiple tiles (tile_count > 1), fly to the tile whose
    centre is nearest to the current camera position rather than the highest-count tile.
    """
    if result_index < 0 or result_index >= len(_search_results):
        return False
    r = _search_results[result_index]
    ox = _model_offset.x if _model_offset else 0.0
    oy = _model_offset.y if _model_offset else 0.0
    oz = _model_offset.z if _model_offset else 0.0

    # Resolve target bbox — nearest tile if this is a multi-tile building type
    bbox = r['bbox']
    n_tiles = r.get('tile_count', 1)
    building_base = _re.sub(r'^T\d+_', '', r['building']) if n_tiles > 1 else None

    if n_tiles > 1 and _db_path_cache:
        # Find camera position in IFC coords
        cam_blender = None
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                cam_blender = area.spaces[0].region_3d.view_location
                break
        if cam_blender:
            cam_ifc_x = cam_blender.x + ox
            cam_ifc_y = cam_blender.y + oy
            # Query all tiles of this building type, pick nearest centre
            try:
                import sqlite3 as _sq
                conn = _sq.connect(_db_path_cache)
                tiles = conn.execute("""
                    SELECT building,
                           (MIN(r.minX)+MAX(r.maxX))/2 AS cx,
                           (MIN(r.minY)+MAX(r.maxY))/2 AS cy,
                           (MIN(r.minZ)+MAX(r.maxZ))/2 AS cz,
                           MIN(r.minX), MIN(r.minY), MIN(r.minZ),
                           MAX(r.maxX), MAX(r.maxY), MAX(r.maxZ)
                    FROM elements_meta m
                    JOIN elements_rtree r ON m.id = r.id
                    WHERE m.building LIKE ?
                    GROUP BY m.building
                """, (f"%{building_base}",)).fetchall()
                conn.close()
                if tiles:
                    best = min(tiles, key=lambda t: (t[1]-cam_ifc_x)**2 + (t[2]-cam_ifc_y)**2)
                    bbox = (best[4], best[5], best[6], best[7], best[8], best[9])
                    # Update active building to the nearest tile
                    global _active_building
                    _active_building = best[0]
                    print(f"[RTree] §FLY_NEAREST base='{building_base}' nearest='{best[0]}' "
                          f"tiles={len(tiles)}")
            except Exception as e:
                print(f"[RTree] §FLY_NEAREST_FAIL {e} — falling back to search result bbox")

    cx_ifc = (bbox[0] + bbox[3]) / 2
    cy_ifc = (bbox[1] + bbox[4]) / 2
    cz_ifc = (bbox[2] + bbox[5]) / 2
    cx, cy, cz = cx_ifc - ox, cy_ifc - oy, cz_ifc - oz
    diag = ((bbox[3]-bbox[0])**2 + (bbox[4]-bbox[1])**2 + (bbox[5]-bbox[2])**2) ** 0.5
    view_dist = max(diag * 0.8, 10.0)  # S189z: closer (was size*1.5)
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces[0].region_3d.view_location = Vector((cx, cy, cz))
            area.spaces[0].region_3d.view_distance = view_dist
            area.tag_redraw()
            break
    print(f"[RTree] §FLY building='{r['building']}' dist={view_dist:.0f}m "
          f"blender=({cx:.1f},{cy:.1f},{cz:.1f})")
    return True


def fetch_building_elements(building: str, search_term: str) -> list:
    """Drill-down L2: fetch top 10 individual elements in building matching term.

    Highlights each element bbox in yellow. Clears L1 highlights.
    Returns list of element dicts for the UI list.
    """
    global _highlighted_bboxes, _building_elements, _active_building, _model_offset, _selected_element

    if not _db_path_cache or not Path(_db_path_cache).exists():
        return []

    _highlighted_bboxes.clear()
    _building_elements.clear()
    _active_building = building
    # Clear stale selected element — its white bbox would mislead if from a previous search
    _selected_element.clear()

    term = search_term.strip()
    # S186: wildcard support — * → %, bare * matches all elements
    is_wildcard_all = (term == '*')
    if '*' in term:
        like = term.replace('*', '%')
    else:
        like = f"%{term}%"

    try:
        conn = sqlite3.connect(_db_path_cache)
        cur = conn.cursor()
        # S186: building filter only when DB has building column
        bld_clause = "m.building = ? AND" if _has_building_column else ""
        bld_params = (building,) if _has_building_column else ()
        if is_wildcard_all:
            cur.execute(f"""
                SELECT m.guid, m.element_name, m.discipline, m.ifc_class, m.storey,
                       r.minX, r.minY, r.minZ, r.maxX, r.maxY, r.maxZ
                FROM elements_meta m
                JOIN elements_rtree r ON m.id = r.id
                {"WHERE m.building = ?" if _has_building_column else ""}
                LIMIT 50
            """, bld_params)
        else:
            cur.execute(f"""
                SELECT m.guid, m.element_name, m.discipline, m.ifc_class, m.storey,
                       r.minX, r.minY, r.minZ, r.maxX, r.maxY, r.maxZ
                FROM elements_meta m
                JOIN elements_rtree r ON m.id = r.id
                WHERE {bld_clause}
                      (m.element_name LIKE ?
                    OR m.ifc_class   LIKE ?
                    OR m.discipline  =    ?)
                LIMIT 50
            """, bld_params + (like, like, term.upper()))
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


def fly_to_storey(storey: str, context) -> bool:
    """S186-s2: Drill into a storey — fly to its bbox centroid, set _active_storey.
    Bbox comes from _building_storey_bboxes cache (pre-computed at count_building time).
    Only the top-10 element list hits the DB (no rtree JOIN — instant)."""
    global _active_storey, _highlighted_bboxes, _building_elements, _selected_element

    building = _active_building
    if not building or not _db_path_cache:
        return False

    # S186-s2: read bbox from cache — no rtree JOIN
    cached = _building_storey_bboxes.get(storey)
    if not cached:
        print(f"[S186] §FLY_STOREY no cached bbox for storey='{storey}'")
        return False

    _active_storey = storey
    _highlighted_bboxes.clear()
    _building_elements.clear()
    _selected_element.clear()

    bbox = cached['bbox']
    cnt = cached['count']
    # S187: don't highlight the storey envelope — individual element bboxes
    # below are sufficient and the envelope overlaps them, looking heavy

    # Top 10 elements — rtree JOIN for bbox (needed by fly_to_element)
    try:
        conn = sqlite3.connect(_db_path_cache)
        if _has_building_column:
            bld_where = "m.building = ? AND"
            bld_p = (building,)
        else:
            bld_where = ""
            bld_p = ()
        elems = conn.execute(f"""
            SELECT m.guid, m.element_name, m.discipline, m.ifc_class, m.storey,
                   r.minX, r.minY, r.minZ, r.maxX, r.maxY, r.maxZ
            FROM elements_meta m
            JOIN elements_rtree r ON m.id = r.id
            WHERE {bld_where} m.storey = ?
            LIMIT 50
        """, bld_p + (storey,)).fetchall()
        conn.close()
    except Exception as e:
        print(f"[S186] §FLY_STOREY ERROR {e}")
        elems = []

    for guid, name, disc, ifc_class, st, mnX, mnY, mnZ, mxX, mxY, mxZ in elems:
        elem_bbox = (mnX, mnY, mnZ, mxX, mxY, mxZ)
        _building_elements.append({'guid': guid, 'name': name, 'disc': disc,
                                   'ifc_class': ifc_class, 'storey': st or '',
                                   'bbox': elem_bbox})
        _highlighted_bboxes.append(elem_bbox)  # S188b: show yellow bbox per element

    # Fly to storey centroid
    off = _model_offset
    ox = off.x if off else 0.0
    oy = off.y if off else 0.0
    oz = off.z if off else 0.0
    cx = (bbox[0] + bbox[3]) / 2 - ox
    cy = (bbox[1] + bbox[4]) / 2 - oy
    cz = (bbox[2] + bbox[5]) / 2 - oz
    size = max(bbox[3]-bbox[0], bbox[4]-bbox[1], bbox[5]-bbox[2], 10.0)

    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            space = area.spaces[0]
            space.region_3d.view_location = Vector((cx, cy, cz))
            space.region_3d.view_distance = size * 1.2
            area.tag_redraw()
            break

    print(f"[S186] §PROOF FLY_STOREY bld={building} storey='{storey}' "
          f"elements={cnt} blender=({cx:.1f},{cy:.1f},{cz:.1f}) [cached]")
    return True


def clear_storey():
    """S186: Go back from storey to building level."""
    global _active_storey
    _active_storey = ""


def fly_to_element(elem_index: int, context) -> bool:
    """Fly viewport to a specific element from L2 list. Highlights only this element."""
    global _selected_element, _highlighted_bboxes

    if elem_index < 0 or elem_index >= len(_building_elements):
        return False

    e = _building_elements[elem_index]
    bbox = e['bbox']

    # S187: Focus — show only this element's bbox, clear the crowd
    _highlighted_bboxes.clear()
    _highlighted_bboxes.append(bbox)

    cx_ifc = (bbox[0] + bbox[3]) / 2
    cy_ifc = (bbox[1] + bbox[4]) / 2
    cz_ifc = (bbox[2] + bbox[5]) / 2
    ox = _model_offset.x if _model_offset else 0.0
    oy = _model_offset.y if _model_offset else 0.0
    oz = _model_offset.z if _model_offset else 0.0
    cx, cy, cz = cx_ifc - ox, cy_ifc - oy, cz_ifc - oz
    diag = ((bbox[3]-bbox[0])**2 + (bbox[4]-bbox[1])**2 + (bbox[5]-bbox[2])**2) ** 0.5
    view_dist = max(diag * 2.0, 2.0)  # S189z: closer inspection (was size*6)

    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces[0].region_3d.view_location = Vector((cx, cy, cz))
            area.spaces[0].region_3d.view_distance = view_dist
            area.tag_redraw()
            break

    _selected_element = {**e, 't': 0}
    print(f"[RTree] §ELEMENT guid={e['guid'][:12]} class={e['ifc_class']} "
          f"storey='{e['storey']}' dist={view_dist:.1f}m")
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

    # ── Pass 1: building envelope slab test (highlighted search results) ──
    # Clicking a yellow building envelope triggers L2 drill-down, same as N-panel click.
    if _highlighted_bboxes and _search_results:
        ox, oy, oz = ifc_origin.x, ifc_origin.y, ifc_origin.z
        dx, dy, dz = ray_dir.x, ray_dir.y, ray_dir.z
        best_t_env = float('inf')
        best_env_idx = -1
        for i, (mnX, mnY, mnZ, mxX, mxY, mxZ) in enumerate(_highlighted_bboxes):
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
            if t_min <= t_max and t_min < best_t_env and t_min > 0:
                best_t_env = t_min
                best_env_idx = i

        if best_env_idx >= 0 and best_env_idx < len(_search_results):
            r = _search_results[best_env_idx]
            building = r.get('building', '')
            print(f"[RTree] §PROOF PICK_ENVELOPE building={building} t={best_t_env:.1f}m")
            return {'type': 'building', 'building': building,
                    'name': building, 'disc': '', 'ifc_class': '', 'guid': ''}

    # ── Pass 2: individual element SQL query (fall-through) ──
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
    print(f"[RTree] §PROOF PICK_ELEMENT guid={guid[:12]} disc={disc} class={ifc_class} "
          f"t={best_t:.1f}m candidates={len(candidates)}")
    return _selected_element
