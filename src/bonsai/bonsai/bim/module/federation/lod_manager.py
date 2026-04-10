"""
S170 — LOD Manager: Distance-Based Mesh Loading + Discipline Lazy Load

Controls which GN template meshes are filled vs empty.
Empty templates = zero GPU cost (GN skips them).
Filled templates = visible instances.

Two levels:
  1. Discipline lazy load — only load templates for visible disciplines
  2. Distance-based — within visible disciplines, only load near camera

Data flow:
  camera position → KDTree query → nearby hashes → load/unload delta
"""

import os
import sqlite3
import struct
import time
from collections import defaultdict

# Optional: scipy for fast spatial queries. Falls back to brute-force if missing.
try:
    from scipy.spatial import cKDTree
    HAS_KDTREE = True
except ImportError:
    HAS_KDTREE = False


# ── Configuration ──────────────────────────────────────────────────────

LOD_RADIUS = 50.0          # metres — load templates within this radius
LOD_TIMER_INTERVAL = 0.5   # seconds between camera checks
LOD_BATCH_LIMIT = 500      # max templates to load/unload per tick (avoid stalls)
LOD_MIN_CAMERA_DELTA = 1.0 # metres — skip update if camera barely moved


class LODManager:
    """
    Manages template mesh loading based on discipline visibility and camera distance.

    Lifecycle:
        1. build_index(db_path)     — called once at cache creation / file open
        2. load_discipline(disc)    — called on discipline toggle ON
        3. unload_discipline(disc)  — called on discipline toggle OFF
        4. lod_tick()               — called every LOD_TIMER_INTERVAL by timer
        5. shutdown()               — called on unregister / file close
    """

    def __init__(self):
        # discipline -> set of geometry_hashes
        self.disc_hashes = defaultdict(set)
        # geometry_hash -> set of disciplines using it
        self.hash_discs = defaultdict(set)
        # geometry_hash -> (cx, cy, cz) centroid of all instances
        self.hash_centroids = {}
        # KDTree built from hash_centroids (if scipy available)
        self._tree = None
        self._tree_hashes = []   # ordered list parallel to tree points
        self._tree_points = None

        # State
        self.visible_disciplines = set()  # currently enabled disciplines
        self.loaded_hashes = set()         # hashes with mesh data loaded
        self.candidate_hashes = set()      # hashes eligible (visible disciplines)

        # Library path for fetching BLOBs
        self.library_path = None

        # Last camera position (to skip no-op ticks)
        self._last_camera_pos = None

        # Distance-based loading enabled
        self.distance_enabled = True
        self.radius = LOD_RADIUS

        self._built = False

    def build_index(self, db_path, library_path=None):
        """
        Build spatial index from federation database.
        Reads element_instances + elements_meta to map discipline -> geometry_hash -> centroid.

        Args:
            db_path: Path to federation _extracted.db
            library_path: Path to component_library.db (stored for BLOB fetches)
        """
        t0 = time.time()
        self.library_path = library_path

        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        # Accumulate positions per geometry_hash for centroid computation
        hash_positions = defaultdict(list)  # hash -> [(cx, cy, cz), ...]

        c.execute("""
            SELECT ei.geometry_hash, em.discipline,
                   et.center_x, et.center_y, et.center_z
            FROM element_instances ei
            JOIN elements_meta em ON ei.guid = em.guid
            LEFT JOIN element_transforms et ON ei.guid = et.guid
        """)
        for ghash, disc, cx, cy, cz in c.fetchall():
            disc = disc or 'Unknown'
            self.disc_hashes[disc].add(ghash)
            self.hash_discs[ghash].add(disc)
            if cx is not None and cy is not None and cz is not None:
                hash_positions[ghash].append((cx, cy, cz))

        conn.close()

        # Compute centroids per geometry_hash
        for ghash, positions in hash_positions.items():
            n = len(positions)
            cx = sum(p[0] for p in positions) / n
            cy = sum(p[1] for p in positions) / n
            cz = sum(p[2] for p in positions) / n
            self.hash_centroids[ghash] = (cx, cy, cz)

        # Build KDTree for fast radius queries
        if HAS_KDTREE and self.hash_centroids:
            self._tree_hashes = list(self.hash_centroids.keys())
            import numpy as np
            self._tree_points = np.array(
                [self.hash_centroids[h] for h in self._tree_hashes],
                dtype=np.float64)
            self._tree = cKDTree(self._tree_points)

        self._built = True
        elapsed = time.time() - t0
        print(f"[S170] LOD index: {len(self.hash_centroids):,} hash centroids, "
              f"{len(self.disc_hashes)} disciplines in {elapsed:.1f}s"
              f"{' (KDTree)' if self._tree else ' (brute-force)'}")

    def get_visible_hashes(self):
        """Return set of geometry_hashes reachable from visible disciplines."""
        result = set()
        for disc in self.visible_disciplines:
            result |= self.disc_hashes.get(disc, set())
        return result

    def load_discipline(self, discipline):
        """
        Mark discipline as visible and load its templates.
        Only loads hashes not already loaded by another visible discipline.

        Returns:
            set of newly loaded geometry_hashes
        """
        if discipline in self.visible_disciplines:
            return set()

        self.visible_disciplines.add(discipline)
        self.candidate_hashes = self.get_visible_hashes()

        # Determine which new hashes need loading
        new_hashes = self.disc_hashes.get(discipline, set()) - self.loaded_hashes

        if not self.distance_enabled:
            # No distance filter — load all new hashes
            return new_hashes
        else:
            # Distance filter will pick them up on next tick
            # Force an immediate tick
            return set()

    def unload_discipline(self, discipline):
        """
        Mark discipline as hidden and unload its exclusive templates.
        Only unloads hashes not shared with other visible disciplines.

        Returns:
            set of geometry_hashes to unload
        """
        if discipline not in self.visible_disciplines:
            return set()

        self.visible_disciplines.discard(discipline)
        self.candidate_hashes = self.get_visible_hashes()

        # Hashes that were in this discipline but NOT in any remaining visible discipline
        disc_only = self.disc_hashes.get(discipline, set()) - self.candidate_hashes
        to_unload = disc_only & self.loaded_hashes
        self.loaded_hashes -= to_unload
        return to_unload

    def get_nearby_hashes(self, camera_pos, radius=None):
        """
        Query hashes within radius of camera position.

        Args:
            camera_pos: (x, y, z) tuple
            radius: search radius in metres (default: self.radius)

        Returns:
            set of geometry_hashes within radius AND in candidate_hashes
        """
        if radius is None:
            radius = self.radius

        if not self.hash_centroids:
            return set()

        nearby = set()

        if self._tree is not None:
            # Fast KDTree query
            indices = self._tree.query_ball_point(camera_pos, radius)
            for i in indices:
                h = self._tree_hashes[i]
                if h in self.candidate_hashes:
                    nearby.add(h)
        else:
            # Brute-force fallback
            r2 = radius * radius
            cx, cy, cz = camera_pos
            for h in self.candidate_hashes:
                centroid = self.hash_centroids.get(h)
                if centroid:
                    dx = centroid[0] - cx
                    dy = centroid[1] - cy
                    dz = centroid[2] - cz
                    if dx*dx + dy*dy + dz*dz <= r2:
                        nearby.add(h)

        return nearby

    def compute_delta(self, camera_pos):
        """
        Compute load/unload sets for current camera position.

        Returns:
            (to_load, to_unload) — sets of geometry_hashes
        """
        if not self.distance_enabled:
            # No distance filter — all candidate hashes should be loaded
            to_load = self.candidate_hashes - self.loaded_hashes
            to_unload = self.loaded_hashes - self.candidate_hashes
            return to_load, to_unload

        nearby = self.get_nearby_hashes(camera_pos)
        to_load = nearby - self.loaded_hashes
        to_unload = self.loaded_hashes - nearby

        # Batch limit to avoid frame stalls
        if len(to_load) > LOD_BATCH_LIMIT:
            to_load = set(list(to_load)[:LOD_BATCH_LIMIT])
        if len(to_unload) > LOD_BATCH_LIMIT:
            to_unload = set(list(to_unload)[:LOD_BATCH_LIMIT])

        return to_load, to_unload

    def apply_delta(self, to_load, to_unload):
        """Update loaded_hashes tracking after mesh swap."""
        self.loaded_hashes |= to_load
        self.loaded_hashes -= to_unload

    def should_skip_tick(self, camera_pos):
        """Return True if camera hasn't moved enough to warrant a re-query."""
        if self._last_camera_pos is None:
            self._last_camera_pos = camera_pos
            return False
        dx = camera_pos[0] - self._last_camera_pos[0]
        dy = camera_pos[1] - self._last_camera_pos[1]
        dz = camera_pos[2] - self._last_camera_pos[2]
        dist2 = dx*dx + dy*dy + dz*dz
        if dist2 < LOD_MIN_CAMERA_DELTA * LOD_MIN_CAMERA_DELTA:
            return True
        self._last_camera_pos = camera_pos
        return False

    def shutdown(self):
        """Clean up references."""
        self._tree = None
        self._tree_hashes = []
        self._tree_points = None
        self.hash_centroids.clear()
        self.disc_hashes.clear()
        self.hash_discs.clear()
        self.loaded_hashes.clear()
        self.candidate_hashes.clear()
        self.visible_disciplines.clear()
        self._built = False


# ── Module-level singleton ─────────────────────────────────────────────

_manager = None


def get_manager():
    """Get or create the module-level LODManager singleton."""
    global _manager
    if _manager is None:
        _manager = LODManager()
    return _manager


def shutdown_manager():
    """Shutdown and release the singleton."""
    global _manager
    if _manager is not None:
        _manager.shutdown()
        _manager = None


# ── Blender integration helpers ────────────────────────────────────────

def fetch_blobs_from_library(library_path, hashes):
    """
    Fetch vertex/face BLOBs from component_library.db for given hashes.

    Returns:
        dict: geometry_hash -> (vertices_blob, faces_blob)
    """
    if not hashes or not library_path or not os.path.exists(library_path):
        return {}

    conn = sqlite3.connect(library_path, timeout=60)
    result = {}
    hash_list = list(hashes)
    BATCH = 5000
    for i in range(0, len(hash_list), BATCH):
        batch = hash_list[i:i + BATCH]
        placeholders = ','.join('?' * len(batch))
        rows = conn.execute(
            f"SELECT geometry_hash, vertices, faces "
            f"FROM component_geometries "
            f"WHERE geometry_hash IN ({placeholders})",
            batch).fetchall()
        for ghash, vblob, fblob in rows:
            result[ghash] = (vblob, fblob)
    conn.close()
    return result


def unpack_vertices(blob):
    """Unpack vertices from database BLOB."""
    if not blob:
        return []
    count = len(blob) // 12
    verts = []
    for i in range(count):
        offset = i * 12
        x, y, z = struct.unpack('fff', blob[offset:offset+12])
        verts.append((x, y, z))
    return verts


def unpack_faces(blob):
    """Unpack faces from database BLOB."""
    if not blob:
        return []
    count = len(blob) // 12
    faces = []
    for i in range(count):
        offset = i * 12
        v1, v2, v3 = struct.unpack('iii', blob[offset:offset+12])
        faces.append((v1, v2, v3))
    return faces


def bake_meshes_into_templates(template_objects, hashes_to_load, library_path):
    """
    Fill template mesh data from component_library.db BLOBs.

    Args:
        template_objects: dict geometry_hash -> bpy Mesh data-block
        hashes_to_load: set of geometry_hashes to fill
        library_path: path to component_library.db

    Returns:
        int: count of meshes actually filled
    """
    blobs = fetch_blobs_from_library(library_path, hashes_to_load)
    filled = 0
    for ghash in hashes_to_load:
        mesh = template_objects.get(ghash)
        if mesh is None:
            continue
        geo = blobs.get(ghash)
        if geo is None:
            continue
        verts = unpack_vertices(geo[0])
        faces = unpack_faces(geo[1])
        if verts:
            mesh.from_pydata(verts, [], faces)
            mesh.update()
            filled += 1
    return filled


def clear_meshes_from_templates(template_objects, hashes_to_unload):
    """
    Clear geometry from template meshes (makes GN instances invisible).

    Args:
        template_objects: dict geometry_hash -> bpy Mesh data-block
        hashes_to_unload: set of geometry_hashes to clear

    Returns:
        int: count of meshes actually cleared
    """
    cleared = 0
    for ghash in hashes_to_unload:
        mesh = template_objects.get(ghash)
        if mesh is None:
            continue
        if len(mesh.vertices) > 0:
            mesh.clear_geometry()
            cleared += 1
    return cleared


def get_template_mesh_map():
    """
    Build geometry_hash -> Mesh data-block map from _GN_Templates collection.

    Returns:
        dict or None if collection doesn't exist
    """
    try:
        import bpy
    except ImportError:
        return None

    templates = bpy.data.collections.get('_GN_Templates')
    if not templates:
        return None

    result = {}
    for obj in templates.objects:
        if obj.type == 'MESH' and obj.data:
            ghash = obj.data.get('geometry_hash')
            if ghash:
                result[ghash] = obj.data
    return result


def get_camera_position():
    """Get the active 3D viewport camera position."""
    try:
        import bpy
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                rv3d = area.spaces[0].region_3d
                pos = rv3d.view_matrix.inverted().translation
                return (pos.x, pos.y, pos.z)
    except Exception:
        pass
    return None


def lod_tick():
    """
    Timer callback: check camera position, load/unload template meshes.

    Returns:
        LOD_TIMER_INTERVAL to keep timer running, or None to stop.
    """
    mgr = get_manager()
    if not mgr._built:
        return LOD_TIMER_INTERVAL

    camera_pos = get_camera_position()
    if camera_pos is None:
        return LOD_TIMER_INTERVAL

    if mgr.should_skip_tick(camera_pos):
        return LOD_TIMER_INTERVAL

    to_load, to_unload = mgr.compute_delta(camera_pos)

    if not to_load and not to_unload:
        return LOD_TIMER_INTERVAL

    template_map = get_template_mesh_map()
    if template_map is None:
        return LOD_TIMER_INTERVAL

    t0 = time.time()

    if to_unload:
        cleared = clear_meshes_from_templates(template_map, to_unload)
        if cleared:
            print(f"[S170] LOD unload: {cleared} templates cleared")

    if to_load:
        filled = bake_meshes_into_templates(
            template_map, to_load, mgr.library_path)
        if filled:
            print(f"[S170] LOD load: {filled} templates filled")

    mgr.apply_delta(to_load, to_unload)

    elapsed = time.time() - t0
    if elapsed > 0.1:
        print(f"[S170] LOD tick: {elapsed:.2f}s "
              f"(load={len(to_load)}, unload={len(to_unload)})")

    return LOD_TIMER_INTERVAL


def start_lod_timer():
    """Register the LOD timer in Blender. Safe to call multiple times."""
    try:
        import bpy
        if not bpy.app.timers.is_registered(lod_tick):
            bpy.app.timers.register(lod_tick, first_interval=1.0, persistent=True)
            print("[S170] LOD timer registered")
    except Exception as e:
        print(f"[S170] Could not register LOD timer: {e}")


def stop_lod_timer():
    """Unregister the LOD timer."""
    try:
        import bpy
        if bpy.app.timers.is_registered(lod_tick):
            bpy.app.timers.unregister(lod_tick)
            print("[S170] LOD timer unregistered")
    except Exception:
        pass


def on_discipline_toggle(discipline, visible):
    """
    Called when a discipline collection visibility changes.

    Args:
        discipline: discipline name (e.g. 'ARC', 'MEP')
        visible: True if toggled ON, False if toggled OFF
    """
    mgr = get_manager()
    if not mgr._built:
        return

    template_map = get_template_mesh_map()
    if template_map is None:
        return

    t0 = time.time()

    if visible:
        new_hashes = mgr.load_discipline(discipline)
        if not mgr.distance_enabled and new_hashes:
            filled = bake_meshes_into_templates(
                template_map, new_hashes, mgr.library_path)
            mgr.apply_delta(new_hashes, set())
            print(f"[S170] Discipline ON '{discipline}': loaded {filled} templates")
        else:
            print(f"[S170] Discipline ON '{discipline}': "
                  f"{len(mgr.disc_hashes.get(discipline, set()))} hashes "
                  f"(distance filter will pick up nearby)")
    else:
        unload_hashes = mgr.unload_discipline(discipline)
        if unload_hashes:
            cleared = clear_meshes_from_templates(template_map, unload_hashes)
            print(f"[S170] Discipline OFF '{discipline}': cleared {cleared} templates")
        else:
            print(f"[S170] Discipline OFF '{discipline}': "
                  f"no exclusive templates to unload")

    elapsed = time.time() - t0
    if elapsed > 0.05:
        print(f"[S170] Discipline toggle: {elapsed:.2f}s")
