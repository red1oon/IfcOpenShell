"""
.blend Cache Manager for Federation Loading

Automatically prebakes database to .blend file for 10x faster loading.

Usage in operator:
    from . import blend_cache

    if blend_cache.should_use_cache(db_path):
        # Load from cache (fast!)
        blend_cache.load_from_cache(context, db_path)
    else:
        # Prebake and save (one-time)
        blend_cache.create_cache(context, db_path)
"""

import bpy
import os
import sqlite3
import struct
import time
import glob
import subprocess
import numpy as np
from pathlib import Path


GN_THRESHOLD = 50_000  # element count above which GN instances are used


# ── S169: Thin .blend — strip meshes on save, restore on open ────────

def _find_library_path():
    """Find component_library.db from root collection custom property."""
    root = bpy.data.collections.get('Federation_Cached')
    if not root:
        return None

    # Explicit path stored at cache creation time
    lib_path = root.get('library_path')
    if lib_path and os.path.exists(lib_path):
        return lib_path

    # Fallback: walk up from database_path
    db_path = root.get('database_path')
    if not db_path:
        return None
    search_dir = os.path.dirname(db_path)
    for _ in range(5):
        candidate = os.path.join(search_dir, 'library', 'component_library.db')
        if os.path.exists(candidate):
            return candidate
        search_dir = os.path.dirname(search_dir)
    return None


def strip_template_meshes():
    """save_pre: clear geometry from template meshes (GN and library-linked).

    GN path (_GN_Templates): clear_geometry() on local meshes.
    Library path (_Templates): swap linked meshes for empty stubs.
    The full hash is preserved in mesh['geometry_hash'] or obj['geometry_hash'].
    """
    _TAG = "[S174][STRIP]"
    t0 = time.time()
    count_gn = 0
    count_lib_tpl = 0
    count_lib_inst = 0

    # ── GN path (S169) + S175 Library-GN path ──
    for gn_col_name in ('_GN_Templates', '_LibGN_Templates'):
        gn_templates = bpy.data.collections.get(gn_col_name)
        if gn_templates:
            print(f"{_TAG} §STRIP_GN found {gn_col_name} ({len(gn_templates.objects)} objects)")
            for obj in gn_templates.objects:
                if obj.type == 'MESH' and obj.data and len(obj.data.vertices) > 0:
                    verts_before = len(obj.data.vertices)
                    obj.data.clear_geometry()
                    count_gn += 1
                    if count_gn <= 3:
                        print(f"{_TAG}   §FINE cleared {obj.name} ({verts_before} verts → 0)")
        else:
            print(f"{_TAG} §STRIP_GN {gn_col_name} not found — skip")

    # ── Library-linked path (S174) ──
    lib_templates = bpy.data.collections.get('_Templates')
    if lib_templates:
        print(f"{_TAG} §STRIP_LIB found _Templates ({len(lib_templates.objects)} objects)")
        for obj in lib_templates.objects:
            if obj.type == 'MESH' and obj.data and obj.data.library:
                ghash = obj.get('geometry_hash') or obj.data.name
                stub = bpy.data.meshes.new(f"stub_{ghash[:12]}")
                stub['geometry_hash'] = ghash
                old_name = obj.data.name
                obj.data = stub
                count_lib_tpl += 1
                if count_lib_tpl <= 3:
                    print(f"{_TAG}   §FINE template {obj.name}: "
                          f"{old_name} (linked) → {stub.name} (stub)")

        # Also swap instances (objects in discipline collections sharing linked meshes)
        parent = None
        for col in bpy.data.collections:
            if lib_templates.name in [c.name for c in col.children]:
                parent = col
                break
        if parent:
            disc_counts = {}
            for child_col in parent.children:
                if child_col.name.startswith('_'):
                    continue
                col_count = 0
                for obj in child_col.objects:
                    if obj.type == 'MESH' and obj.data and obj.data.library:
                        ghash = obj.get('geometry_hash') or obj.data.name
                        stub_name = f"stub_{ghash[:12]}"
                        stub = bpy.data.meshes.get(stub_name)
                        if not stub:
                            stub = bpy.data.meshes.new(stub_name)
                            stub['geometry_hash'] = ghash
                        obj.data = stub
                        count_lib_inst += 1
                        col_count += 1
                if col_count > 0:
                    disc_counts[child_col.name] = col_count
            for disc, cnt in disc_counts.items():
                print(f"{_TAG}   §FINE disc {disc}: {cnt} instances stubbed")
        else:
            print(f"{_TAG}   §FINE WARNING: no parent collection found for _Templates")
    else:
        print(f"{_TAG} §STRIP_LIB _Templates not found — skip")

    total = count_gn + count_lib_tpl + count_lib_inst
    elapsed = (time.time() - t0) * 1000
    print(f"{_TAG} §PROOF STRIP total={total} "
          f"(gn={count_gn} lib_tpl={count_lib_tpl} lib_inst={count_lib_inst}) "
          f"{elapsed:.0f}ms")
    return total


def restore_template_meshes():
    """save_post / load_post: restore meshes from library.blend or component_library.db.

    S174: Library-linked path — re-link from library.blend (instant, no BLOB reads).
    S170: GN path — re-bake from component_library.db with LOD filtering.
    S169: GN fallback — restore ALL templates if no LOD manager.
    """
    restored = 0

    # ── S175: Library-GN path — re-append from library.blend ──
    lib_gn_templates = bpy.data.collections.get('_LibGN_Templates')
    if lib_gn_templates:
        restored += _restore_library_gn_templates(lib_gn_templates)

    # ── Library-linked path (S174) — re-link from library.blend ──
    lib_templates = bpy.data.collections.get('_Templates')
    if lib_templates:
        restored += _restore_library_linked()
        return restored  # library path is self-contained

    # ── GN path (S169/S170) — re-bake from component_library.db ──
    templates = bpy.data.collections.get('_GN_Templates')
    if not templates:
        return restored

    # Check if LOD manager has state — if so, only restore loaded hashes
    lod_filter = None
    try:
        from . import lod_manager
        mgr = lod_manager.get_manager()
        if mgr._built and mgr.loaded_hashes:
            lod_filter = mgr.loaded_hashes
    except Exception:
        pass

    # Collect meshes that need geometry restored
    needs_restore = []
    for obj in templates.objects:
        if obj.type == 'MESH' and obj.data and len(obj.data.vertices) == 0:
            ghash = obj.data.get('geometry_hash')
            if ghash:
                # S170: skip hashes not in LOD loaded set
                if lod_filter is not None and ghash not in lod_filter:
                    continue
                needs_restore.append((obj.data, ghash))

    if not needs_restore:
        return 0

    lib_path = _find_library_path()
    if not lib_path:
        print("[S169] WARNING: cannot restore meshes — component_library.db not found")
        return 0

    # Batch-fetch from library
    t0 = time.time()
    print(f"  Opening library: {lib_path} (waiting up to 60s if locked...)")
    lib_conn = sqlite3.connect(lib_path, timeout=60)
    hash_to_geo = {}
    hashes = [h for _, h in needs_restore]
    BATCH = 5000
    for i in range(0, len(hashes), BATCH):
        batch = hashes[i:i + BATCH]
        placeholders = ','.join('?' * len(batch))
        rows = lib_conn.execute(
            f"SELECT geometry_hash, vertices, faces "
            f"FROM component_geometries "
            f"WHERE geometry_hash IN ({placeholders})",
            batch).fetchall()
        for ghash, vblob, fblob in rows:
            hash_to_geo[ghash] = (vblob, fblob)
    lib_conn.close()

    # Restore mesh data
    restored = 0
    for mesh, ghash in needs_restore:
        geo = hash_to_geo.get(ghash)
        if geo:
            verts = unpack_vertices(geo[0])
            faces = unpack_faces(geo[1])
            mesh.from_pydata(verts, [], faces)
            mesh.update()
            restored += 1

    elapsed = time.time() - t0
    scope = f"LOD-filtered ({len(lod_filter):,} eligible)" if lod_filter else "ALL"
    print(f"[S169] Restored {restored}/{len(needs_restore)} template meshes "
          f"from {os.path.basename(lib_path)} in {elapsed:.1f}s [{scope}]")
    return restored


def _restore_library_gn_templates(templates_col):
    """S175: Re-link meshes from library.blend for _LibGN_Templates.

    GN mode uses link=True (zero-copy). On save, clear_geometry() strips
    vertex data. On load/save_post, re-link from library.blend.
    """
    _TAG = "[S175][RESTORE_GN]"

    # Collect empty templates
    needs = []
    for obj in templates_col.objects:
        if obj.type == 'MESH' and obj.data and len(obj.data.vertices) == 0:
            ghash = obj.get('geometry_hash') or obj.data.get('geometry_hash')
            if ghash:
                needs.append((obj, ghash))

    if not needs:
        return 0

    # Find library.blend from parent collection metadata
    lib_blend_path = None
    for col in bpy.data.collections:
        if templates_col.name in [c.name for c in col.children]:
            lib_blend_path = col.get('library_blend_path')
            break

    if not lib_blend_path or not os.path.exists(lib_blend_path):
        # Fallback: search for library.blend
        lib_db_path = _find_library_path()
        if lib_db_path:
            candidate = os.path.join(os.path.dirname(lib_db_path), 'library.blend')
            if os.path.exists(candidate):
                lib_blend_path = candidate

    if not lib_blend_path or not os.path.exists(lib_blend_path):
        print(f"{_TAG} WARNING: library.blend not found — cannot restore GN templates")
        return 0

    t0 = time.time()
    needed_hashes = {ghash for _, ghash in needs}

    # Re-link (not append) — keeps zero-copy performance
    with bpy.data.libraries.load(lib_blend_path, link=True) as (data_from, data_to):
        to_link = [n for n in data_from.meshes if n in needed_hashes]
        data_to.meshes = to_link

    # Build hash → mesh lookup
    fresh = {}
    for mesh in data_to.meshes:
        if mesh is not None:
            fresh[mesh.name] = mesh

    # Swap empty meshes for fresh linked ones
    restored = 0
    for obj, ghash in needs:
        new_mesh = fresh.get(ghash)
        if new_mesh:
            old_mesh = obj.data
            obj.data = new_mesh
            # Remove orphan stub
            if old_mesh and old_mesh.users == 0:
                bpy.data.meshes.remove(old_mesh)
            restored += 1

    elapsed = time.time() - t0
    print(f"{_TAG} Restored {restored}/{len(needs)} GN templates "
          f"from library.blend (link=True) in {elapsed:.1f}s")
    return restored


def _restore_library_linked():
    """S174: Re-link meshes from library.blend after save or file open.

    Finds all objects with stub meshes (stub_* name, geometry_hash custom prop),
    re-links the original mesh from library.blend, and swaps back.

    Workflow: Open → R-tree visible (no meshes) → user clicks Library → full geometry.
    On save_post: re-link immediately so user sees no flicker.
    On load_post: leave as stubs — user clicks Library to re-link.
    """
    _TAG = "[S174][RESTORE]"

    # Find library.blend path from scene props
    lib_blend = None
    try:
        props = bpy.context.scene.BIMFederationProperties
        db_path = props.federation_database_path
        if db_path:
            db_dir = os.path.dirname(db_path)
            search = db_dir
            for _ in range(5):
                candidate = os.path.join(search, 'library', 'library.blend')
                if os.path.exists(candidate):
                    lib_blend = candidate
                    break
                search = os.path.dirname(search)
    except Exception:
        pass

    if not lib_blend:
        print(f"{_TAG} §FAIL library.blend not found — cannot restore")
        return 0

    print(f"{_TAG} §RESTORE_START library={lib_blend}")
    t0 = time.time()

    # Collect stubs that need re-linking
    stub_hashes = set()
    stub_objects = []  # (obj, geometry_hash)
    for obj in bpy.data.objects:
        if obj.type == 'MESH' and obj.data and obj.data.name.startswith('stub_'):
            ghash = obj.data.get('geometry_hash') or obj.get('geometry_hash')
            if ghash:
                stub_hashes.add(ghash)
                stub_objects.append((obj, ghash))

    if not stub_hashes:
        print(f"{_TAG} §RESTORE_SKIP no stub meshes found — nothing to restore")
        return 0

    print(f"{_TAG} §FINE {len(stub_objects):,} objects with {len(stub_hashes):,} "
          f"unique hashes need re-linking")

    # Re-link from library.blend
    t_link = time.time()
    with bpy.data.libraries.load(lib_blend, link=True) as (data_from, data_to):
        available = set(data_from.meshes)
        to_link = [name for name in data_from.meshes if name in stub_hashes]
        data_to.meshes = to_link
    t_link_elapsed = (time.time() - t_link) * 1000

    missing = stub_hashes - available
    print(f"{_TAG} §PROOF LINK_TIME {t_link_elapsed:.0f}ms for {len(to_link):,} meshes "
          f"({len(available):,} available in library)")
    if missing:
        print(f"{_TAG} §WARN {len(missing)} hashes not in library.blend")
        for h in list(missing)[:3]:
            print(f"{_TAG}   §FINE MISS {h[:16]}")

    # Build hash → linked mesh lookup
    mesh_by_hash = {}
    for mesh in data_to.meshes:
        if mesh is not None:
            mesh_by_hash[mesh.name] = mesh

    # Swap stubs back to linked meshes
    restored = 0
    orphans_removed = 0
    for obj, ghash in stub_objects:
        linked_mesh = mesh_by_hash.get(ghash)
        if linked_mesh:
            old_stub = obj.data
            obj.data = linked_mesh
            if old_stub and old_stub.users == 0:
                bpy.data.meshes.remove(old_stub)
                orphans_removed += 1
            restored += 1
            if restored <= 3:
                print(f"{_TAG}   §FINE [{restored}] {obj.name}: "
                      f"stub → {linked_mesh.name[:16]} "
                      f"({len(linked_mesh.vertices)} verts)")

    elapsed = (time.time() - t0) * 1000
    print(f"{_TAG} §PROOF RESTORE restored={restored:,}/{len(stub_objects):,} "
          f"orphans_cleaned={orphans_removed} {elapsed:.0f}ms")
    return restored


def cache_exists_in_db_folder(db_path: str) -> bool:
    """
    Check if ANY .blend file exists in the same folder as the database.

    Simple check: If any .blend exists → don't bake (user must delete to rebake)

    Args:
        db_path: Path to federation database

    Returns:
        True if any .blend file exists in database folder, False otherwise

    Example:
        >>> cache_exists_in_db_folder("/path/to/database.db")
        True  # Found: /path/to/something.blend
    """
    db_dir = os.path.dirname(db_path)
    blend_files = glob.glob(os.path.join(db_dir, "*.blend"))

    if blend_files:
        print(f"📦 Cache detected in {db_dir}:")
        for blend in blend_files:
            size_mb = os.path.getsize(blend) / (1024 * 1024)
            print(f"   - {os.path.basename(blend)} ({size_mb:.1f} MB)")
        return True

    print(f"ℹ️  No .blend cache found in {db_dir}")
    return False


def get_cache_path(db_path: str, mode: str = "full", auto_increment: bool = False) -> str:
    """
    Get .blend cache path for a database.

    Args:
        db_path: Path to database
        mode: Cache type - "solid" or "full" (default: "full")
        auto_increment: If True, auto-increment filename if exists (e.g., _1, _2, _3)

    Returns:
        Path to .blend cache file in same folder as database

    Example:
        /path/to/model.db, mode="full" → /path/to/model_full.blend
        /path/to/model.db, mode="solid" → /path/to/model_solid.blend
        /path/to/model.db, mode="full", auto_increment=True → /path/to/model_full_1.blend (if model_full.blend exists)
    """
    db_dir = os.path.dirname(db_path)
    db_name = os.path.splitext(os.path.basename(db_path))[0]

    # Base filename without increment
    cache_filename = f"{db_name}_{mode}.blend"
    cache_path = os.path.join(db_dir, cache_filename)

    # Auto-increment if requested and file exists
    if auto_increment and os.path.exists(cache_path):
        counter = 1
        while True:
            cache_filename = f"{db_name}_{mode}_{counter}.blend"
            cache_path = os.path.join(db_dir, cache_filename)
            if not os.path.exists(cache_path):
                break
            counter += 1

    return cache_path


def should_use_cache(db_path: str) -> bool:
    """
    Check if .blend cache exists and is fresh.

    Returns True if:
    - Cache file exists
    - Cache is newer than database (db hasn't changed)
    """
    cache_path = get_cache_path(db_path)

    if not os.path.exists(cache_path):
        return False

    # Check if database is newer than cache (cache is stale)
    db_mtime = os.path.getmtime(db_path)
    cache_mtime = os.path.getmtime(cache_path)

    return cache_mtime > db_mtime


def unpack_vertices(blob):
    """Unpack vertices from database BLOB"""
    if not blob:
        return []
    count = len(blob) // 12  # 3 floats (xyz) = 12 bytes
    vertices = []
    for i in range(count):
        offset = i * 12
        x, y, z = struct.unpack('fff', blob[offset:offset+12])
        vertices.append((x, y, z))
    return vertices


def unpack_faces(blob):
    """Unpack faces from database BLOB"""
    if not blob:
        return []
    count = len(blob) // 12  # 3 ints (triangle) = 12 bytes
    faces = []
    for i in range(count):
        offset = i * 12
        v1, v2, v3 = struct.unpack('iii', blob[offset:offset+12])
        faces.append((v1, v2, v3))
    return faces


def _get_element_count(db_path):
    """Quick element count without loading geometry."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='element_instances'")
    if c.fetchone():
        count = c.execute("SELECT COUNT(*) FROM element_instances").fetchone()[0]
    else:
        count = c.execute("SELECT COUNT(*) FROM elements_meta").fetchone()[0]
    conn.close()
    return count


def _get_ram_mb():
    """Current process RSS in MB (Linux)."""
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except Exception:
        return 0


def _build_instance_node_tree(name, template_coll):
    """
    GN tree: Points -> Instance on Points (Pick Instance from collection).
    Each point's 'instance_index' attribute selects which template mesh.
    """
    tree = bpy.data.node_groups.new(name, 'GeometryNodeTree')

    tree.interface.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    tree.interface.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')

    inp = tree.nodes.new('NodeGroupInput')
    out = tree.nodes.new('NodeGroupOutput')

    # Collection Info — provides all template meshes as indexable instances
    col_info = tree.nodes.new('GeometryNodeCollectionInfo')
    col_info.inputs['Collection'].default_value = template_coll
    col_info.inputs['Separate Children'].default_value = True
    col_info.inputs['Reset Children'].default_value = True

    # Instance on Points — places a template at each vertex
    iop = tree.nodes.new('GeometryNodeInstanceOnPoints')
    iop.inputs['Pick Instance'].default_value = True

    # Named Attribute — reads per-point 'instance_index' to pick template
    named_attr = tree.nodes.new('GeometryNodeInputNamedAttribute')
    named_attr.data_type = 'INT'
    named_attr.inputs['Name'].default_value = 'instance_index'

    # Named Attribute — reads per-point 'rotation' (Euler XYZ radians)
    rot_attr = tree.nodes.new('GeometryNodeInputNamedAttribute')
    rot_attr.data_type = 'FLOAT_VECTOR'
    rot_attr.inputs['Name'].default_value = 'rotation'

    # Euler to Rotation — Blender 5.0 Instance on Points expects Rotation type
    euler_to_rot = tree.nodes.new('FunctionNodeEulerToRotation')

    tree.links.new(inp.outputs[0], iop.inputs['Points'])
    tree.links.new(col_info.outputs['Instances'], iop.inputs['Instance'])
    tree.links.new(named_attr.outputs[0], iop.inputs['Instance Index'])
    tree.links.new(rot_attr.outputs[0], euler_to_rot.inputs[0])
    tree.links.new(euler_to_rot.outputs[0], iop.inputs['Rotation'])
    tree.links.new(iop.outputs['Instances'], out.inputs[0])

    return tree


def create_cache_gn_instances(context, db_path, mode="full", report_fn=None):
    """
    GN-instanced cache for large databases (>= GN_THRESHOLD elements).

    Creates ~13 GN objects (one per discipline) instead of 1M real objects.
    Each uses Instance on Points to place shared template meshes at element
    positions.  108K template meshes go into a hidden collection.

    Returns:
        Number of unique meshes created
    """
    cache_path = get_cache_path(db_path, mode=mode)
    log_path = os.path.join(os.path.dirname(db_path), "gn_cache_log.txt")
    t0 = time.time()
    log_lines = []

    def log(msg):
        elapsed = time.time() - t0
        line = f"[{int(elapsed)//60:02d}:{elapsed%60:04.1f}] {msg}"
        print(line)
        log_lines.append(line)

    def header(msg):
        print(msg)
        log_lines.append(msg)

    header("=" * 64)
    header("GN CACHE BUILD LOG")
    header("=" * 64)
    header(f"Date:     {time.strftime('%Y-%m-%d %H:%M:%S')}")
    header(f"Database: {db_path}")
    header(f"Cache:    {cache_path}")
    header(f"Mode:     GN instances (FULL)")
    header("")

    if report_fn:
        report_fn("Baking GN instance cache (one-time, ~5 min)...")

    # ── Phase 1: DB query ──────────────────────────────────────
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Check if base_geometries has actual vertex BLOBs (not just the column)
    # S168 hash-only mode: column exists but all values are NULL
    c.execute("PRAGMA table_info(base_geometries)")
    bg_cols = {r[1] for r in c.fetchall()}
    has_blobs = False
    if 'vertices' in bg_cols:
        row = c.execute("SELECT 1 FROM base_geometries WHERE vertices IS NOT NULL LIMIT 1").fetchone()
        has_blobs = row is not None

    lib_path = None  # S169: set when using component_library.db

    if has_blobs:
        # Legacy: BLOBs embedded in federation DB
        c.execute("""SELECT DISTINCT bg.geometry_hash, bg.vertices, bg.faces
                     FROM base_geometries bg
                     JOIN element_instances ei ON bg.geometry_hash = ei.geometry_hash
                     WHERE bg.vertices IS NOT NULL""")
        geom_rows = c.fetchall()
    else:
        # S168: BLOBs in component_library.db, federation DB has hashes only
        # Walk up from db_path looking for library/component_library.db
        lib_paths = []
        search_dir = os.path.dirname(db_path)
        for _ in range(5):  # max 5 levels up
            candidate = os.path.join(search_dir, 'library', 'component_library.db')
            lib_paths.append(candidate)
            search_dir = os.path.dirname(search_dir)
        # Also check same dir as DB
        lib_paths.append(os.path.join(os.path.dirname(db_path), 'component_library.db'))
        lib_path = None
        for lp in lib_paths:
            if os.path.exists(lp):
                lib_path = lp
                break

        if not lib_path:
            raise FileNotFoundError(
                "No component_library.db found for mesh BLOBs. "
                "Searched: " + ", ".join(lib_paths))

        log(f"MESH_SOURCE   {lib_path}")
        print(f"  Opening library: {lib_path} (waiting up to 60s if locked...)")
        lib_conn = sqlite3.connect(lib_path, timeout=60)
        lc = lib_conn.cursor()

        # Get hashes needed from federation DB
        c.execute("""SELECT DISTINCT ei.geometry_hash
                     FROM element_instances ei
                     JOIN base_geometries bg ON ei.geometry_hash = bg.geometry_hash""")
        needed_hashes = [r[0] for r in c.fetchall()]

        # Fetch BLOBs from library in batches
        geom_rows = []
        BATCH = 5000
        for i in range(0, len(needed_hashes), BATCH):
            batch = needed_hashes[i:i+BATCH]
            placeholders = ','.join('?' * len(batch))
            lc.execute(f"""SELECT geometry_hash, vertices, faces
                          FROM component_geometries
                          WHERE geometry_hash IN ({placeholders})""", batch)
            geom_rows.extend(lc.fetchall())

        lib_conn.close()
        log(f"MESH_SOURCE   {len(geom_rows):,} meshes from library "
            f"({len(needed_hashes):,} requested)")

    # Check if rotation columns exist in element_transforms
    c.execute("PRAGMA table_info(element_transforms)")
    et_cols = {r[1] for r in c.fetchall()}
    has_rotation = 'rotation_x' in et_cols

    # Check if building column exists in elements_meta
    c.execute("PRAGMA table_info(elements_meta)")
    em_cols = {r[1] for r in c.fetchall()}
    has_building = 'building' in em_cols

    rot_cols = "et.rotation_x, et.rotation_y, et.rotation_z," if has_rotation else ""
    bldg_col = "em.building," if has_building else ""

    c.execute(f"""
        SELECT ei.guid, em.discipline, ei.geometry_hash,
               et.center_x, et.center_y, et.center_z,
               em.material_name, em.material_rgba,
               {rot_cols}
               {bldg_col}
               em.ifc_class
        FROM element_instances ei
        JOIN elements_meta em ON ei.guid = em.guid
        LEFT JOIN element_transforms et ON ei.guid = et.guid
    """)
    element_rows = c.fetchall()
    conn.close()

    log(f"DB_QUERY      {len(element_rows):,} elements, "
        f"{len(geom_rows):,} unique geoms"
        f"{' (with rotation)' if has_rotation else ' (no rotation)'}"
        f" — RAM {_get_ram_mb():.0f} MB")

    # ── Phase 2: Create EMPTY template meshes (S170 lazy load) ──
    # Meshes are created with geometry_hash but NO vertex data.
    # Only ARC templates get filled immediately; rest loaded on demand
    # by lod_manager based on discipline visibility + camera distance.
    mesh_t0 = time.time()
    wm = context.window_manager
    wm.progress_begin(0, len(geom_rows))

    hash_to_index = {}
    baked_meshes = []   # ordered — index = Pick Instance index
    geom_hashes = []    # parallel list for material assignment
    hash_to_blobs = {}  # geometry_hash -> (verts_blob, faces_blob) for deferred fill

    for i, (geom_hash, verts_blob, faces_blob) in enumerate(geom_rows):
        mesh = bpy.data.meshes.new(f"T_{geom_hash[:8]}")
        # S169: store full hash for save_pre strip / load_post restore
        mesh['geometry_hash'] = geom_hash
        # S170: mesh starts EMPTY — filled later by discipline/distance LOD

        hash_to_index[geom_hash] = i
        baked_meshes.append(mesh)
        geom_hashes.append(geom_hash)
        hash_to_blobs[geom_hash] = (verts_blob, faces_blob)

        if (i + 1) % 20000 == 0:
            wm.progress_update(i + 1)

    wm.progress_end()
    mesh_time = time.time() - mesh_t0
    log(f"MESH_CREATE   {len(baked_meshes):,} empty templates in {mesh_time:.1f}s "
        f"— RAM {_get_ram_mb():.0f} MB")

    # ── Phase 3: Group elements by discipline ─────────────────────
    group_t0 = time.time()
    disc_positions = {}   # discipline -> list of (cx, cy, cz)
    disc_rotations = {}   # discipline -> list of (rx, ry, rz)
    disc_indices = {}     # discipline -> list of int
    hash_materials = {}   # geometry_hash -> (material_name, rgba, discipline)

    # Parse dynamic column offsets
    col = 8
    rot_off = col if has_rotation else None
    if has_rotation:
        col += 3

    skipped = 0
    for row in element_rows:
        guid, discipline, geom_hash, cx, cy, cz = row[:6]
        mat_name, mat_rgba = row[6], row[7]

        rx = row[rot_off] if rot_off is not None else 0.0
        ry = row[rot_off + 1] if rot_off is not None else 0.0
        rz = row[rot_off + 2] if rot_off is not None else 0.0

        disc = discipline or 'Unknown'
        idx = hash_to_index.get(geom_hash)
        if idx is None:
            skipped += 1
            continue

        disc_positions.setdefault(disc, []).append(
            (cx or 0.0, cy or 0.0, cz or 0.0))
        disc_rotations.setdefault(disc, []).append(
            (float(rx or 0.0), float(ry or 0.0), float(rz or 0.0)))
        disc_indices.setdefault(disc, []).append(idx)

        # First material wins per geometry hash
        if geom_hash not in hash_materials and mat_rgba:
            hash_materials[geom_hash] = (mat_name or "<Unnamed>",
                                         mat_rgba, disc)

    group_time = time.time() - group_t0
    log(f"GROUPING      {len(disc_positions)} disciplines, "
        f"{len(hash_materials):,} materials in {group_time:.1f}s"
        + (f" ({skipped:,} skipped)" if skipped else ""))

    # ── Phase 4: Template objects in hidden collection ─────────
    tmpl_t0 = time.time()

    from .stage2_tessellation_loader import get_or_create_db_material

    tmpl_coll = bpy.data.collections.new("_GN_Templates")
    context.scene.collection.children.link(tmpl_coll)

    mat_assigned = 0
    for i, mesh in enumerate(baked_meshes):
        obj = bpy.data.objects.new(mesh.name, mesh)

        # Assign material from first element using this geometry
        mat_info = hash_materials.get(geom_hashes[i])
        if mat_info:
            m_name, m_rgba, m_disc = mat_info
            material = get_or_create_db_material(m_name, m_rgba, m_disc)
            if len(obj.data.materials) == 0:
                obj.data.materials.append(None)
            obj.data.materials[0] = material
            mat_assigned += 1

        tmpl_coll.objects.link(obj)

    # Hide from viewport (but available for GN Collection Info)
    for lc in context.view_layer.layer_collection.children:
        if lc.name == tmpl_coll.name:
            lc.exclude = True
            break

    tmpl_time = time.time() - tmpl_t0
    log(f"TEMPLATES     {len(baked_meshes):,} objects, {mat_assigned:,} with materials "
        f"in {tmpl_time:.1f}s — RAM {_get_ram_mb():.0f} MB")

    # ── Phase 4b: S170 — Pre-fill ARC templates only ─────────────
    # Compute which geometry_hashes are used by ARC elements
    arc_hashes = set()
    for row in element_rows:
        disc = row[1] or 'Unknown'
        if disc == 'ARC':
            ghash = row[2]
            if ghash in hash_to_index:
                arc_hashes.add(ghash)

    fill_t0 = time.time()
    arc_filled = 0
    for ghash in arc_hashes:
        blobs = hash_to_blobs.get(ghash)
        if blobs:
            verts = unpack_vertices(blobs[0])
            faces = unpack_faces(blobs[1])
            if verts:
                idx = hash_to_index[ghash]
                baked_meshes[idx].from_pydata(verts, [], faces)
                baked_meshes[idx].update()
                arc_filled += 1

    # Free blob memory — LOD manager fetches from library on demand
    del hash_to_blobs

    fill_time = time.time() - fill_t0
    log(f"ARC_PREFILL   {arc_filled:,}/{len(arc_hashes):,} ARC templates filled "
        f"in {fill_time:.1f}s ({len(baked_meshes) - arc_filled:,} empty/deferred) "
        f"— RAM {_get_ram_mb():.0f} MB")

    # ── Phase 5: GN node tree + per-discipline objects ───────────
    gn_t0 = time.time()

    gn_tree = _build_instance_node_tree("GN_FedInstances", tmpl_coll)

    # Root collection
    if "Federation_Cached" in bpy.data.collections:
        bpy.data.collections.remove(bpy.data.collections["Federation_Cached"])

    root_coll = bpy.data.collections.new("Federation_Cached")
    root_coll['database_path'] = db_path
    # S169: store library path for load_post mesh restore
    if lib_path:
        root_coll['library_path'] = lib_path

    total_instances = 0
    for disc in sorted(disc_positions.keys(),
                       key=lambda d: -len(disc_positions[d])):
        pos_list = disc_positions[disc]
        rot_list = disc_rotations[disc]
        idx_list = disc_indices[disc]
        n = len(pos_list)

        # Point mesh — one vertex per element instance
        point_mesh = bpy.data.meshes.new(f"Points_{disc}")
        point_mesh.vertices.add(n)

        coords = np.array(pos_list, dtype=np.float32).ravel()
        point_mesh.vertices.foreach_set("co", coords)

        attr = point_mesh.attributes.new("instance_index", 'INT', 'POINT')
        attr.data.foreach_set("value", np.array(idx_list, dtype=np.int32))

        rot_attr = point_mesh.attributes.new("rotation", 'FLOAT_VECTOR', 'POINT')
        rot_attr.data.foreach_set("vector",
                                  np.array(rot_list, dtype=np.float32).ravel())
        point_mesh.update()

        # GN object with Instance on Points modifier
        obj = bpy.data.objects.new(f"Fed_{disc}", point_mesh)
        mod = obj.modifiers.new("GeometryNodes", 'NODES')
        mod.node_group = gn_tree

        disc_coll = bpy.data.collections.new(disc)
        disc_coll.objects.link(obj)
        root_coll.children.link(disc_coll)

        total_instances += n
        log(f"  GN_SETUP    {disc:8s} {n:>9,} instances")

    gn_time = time.time() - gn_t0
    log(f"GN_SETUP      {len(disc_positions)} objects, "
        f"{total_instances:,} instances in {gn_time:.1f}s "
        f"— RAM {_get_ram_mb():.0f} MB")

    # ── Phase 6: Link to scene ─────────────────────────────────
    link_t0 = time.time()
    context.scene.collection.children.link(root_coll)

    try:
        props = context.scene.BIMFederationProperties
        props.federation_database_path = str(db_path)
    except Exception:
        pass

    # Enable discipline legend if available
    try:
        from . import discipline_legend
        discipline_legend.enable_legend()
    except Exception:
        pass

    # Double view distance for large models
    try:
        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            space.clip_end = max(space.clip_end, 10000.0)
    except Exception:
        pass

    # Hide all non-ARC disciplines to speed up initial depsgraph evaluation.
    # User toggles other disciplines on as needed via Outliner.
    try:
        root_lc = None
        for lc in context.view_layer.layer_collection.children:
            if lc.name == "Federation_Cached":
                root_lc = lc
                break
        if root_lc and total_instances >= 100_000:
            hidden = 0
            for disc_lc in root_lc.children:
                if disc_lc.name != 'ARC':
                    disc_lc.exclude = True
                    hidden += 1
            log(f"VISIBILITY    ARC only — {hidden} non-ARC collections hidden "
                f"(toggle in Outliner)")
    except Exception as e:
        log(f"VISIBILITY    could not set: {e}")

    link_time = time.time() - link_t0
    log(f"SCENE_LINK    linked in {link_time:.2f}s")

    # ── Phase 7: No auto-save (S169) ─────────────────────────────
    # Meshes will be stripped by save_pre handler before any save.
    # User can Ctrl+S safely — .blend will be ~15 MB (no mesh BLOBs).
    log(f"VIEWPORT      ready — {total_instances:,} instances. "
        f"Save is safe (S169: meshes auto-stripped, ~15 MB).")

    # ── Phase 8: S170 — Initialize LOD manager ───────────────────
    try:
        from . import lod_manager
        mgr = lod_manager.get_manager()
        mgr.build_index(db_path, library_path=lib_path)
        # Mark ARC as visible (it's the only pre-filled discipline)
        mgr.visible_disciplines.add('ARC')
        # Track which hashes are already loaded (the ARC ones we pre-filled)
        mgr.loaded_hashes = set(arc_hashes)
        mgr.candidate_hashes = mgr.get_visible_hashes()
        # Enable distance-based loading for large models
        mgr.distance_enabled = (total_instances >= 100_000)
        log(f"LOD_INIT      {len(mgr.hash_centroids):,} centroids, "
            f"ARC visible ({len(arc_hashes):,} loaded), "
            f"distance={'ON' if mgr.distance_enabled else 'OFF'}")
        # Start LOD timer
        lod_manager.start_lod_timer()
    except Exception as e:
        log(f"LOD_INIT      WARN: {e}")

    # ── Phase 8b: S174 — Initialize DLOD (Distance LOD) handler ──
    try:
        from . import dlod_handler
        n_elements = sum(len(v) for v in disc_positions.values())
        n_hashes = len(hash_to_index)
        log(f"[S174][DLOD] §FINE dlod_init called with {n_elements} elements, "
            f"{n_hashes} unique hashes")
        dlod_handler.dlod_init(disc_positions, disc_indices, hash_to_index,
                               db_path=db_path)
        bbox_map = dlod_handler.build_bbox_proxies(tmpl_coll, hash_to_index,
                                                    db_path)
        n_proxies = len(bbox_map) if bbox_map else 0
        log(f"[S174][DLOD] §FINE build_bbox_proxies: {n_proxies} proxies built")
    except Exception as e:
        log(f"[S174][DLOD] §WARN DLOD init failed (non-fatal): {e}")

    # ── Summary ────────────────────────────────────────────────
    total_time = time.time() - t0
    log(f"DONE          {total_time:.1f}s ({total_time/60:.1f} min) "
        f"— peak RAM {_get_ram_mb():.0f} MB")

    header("")
    header("SUMMARY")
    header(f"  Elements:    {total_instances:,}")
    header(f"  Unique mesh: {len(baked_meshes):,}")
    header(f"  GN objects:  {len(disc_positions)} (1 per discipline)")
    header(f"  Templates:   {len(baked_meshes):,} (hidden collection)")
    header(f"  Outliner:    Federation_Cached → discipline collections")

    # ── S173: §PROOF BBOX_MATCH — do placed meshes match stored rtree bboxes?
    # No IFC needed. Compares: rot @ lib_mesh + centre vs rtree bbox.
    # This is what the viewport shows vs what the extraction computed.
    try:
        import os as _os
        import math as _m
        _log_level = _os.environ.get("BIM_LOG_LEVEL", "FINE").upper()
        if _log_level != "FINE":
            log(f"§PROOF BBOX_MATCH SKIPPED — BIM_LOG_LEVEL={_log_level}")
        else:
            # Find library: try lib_path, then search up from db_path
            _lib_path = lib_path
            if not _lib_path:
                for _p in Path(db_path).parents:
                    _candidate = _p / "library" / "component_library.db"
                    if _candidate.exists():
                        _lib_path = str(_candidate)
                        break
            if not _lib_path or not Path(_lib_path).exists():
                log(f"§PROOF BBOX_MATCH SKIPPED — library not found (searched from {db_path})")
            else:
                _vconn = sqlite3.connect(db_path)
                _lconn = sqlite3.connect(_lib_path)
                _samples = _vconn.execute("""
                    SELECT et.guid, et.center_x, et.center_y, et.center_z,
                           et.rotation_x, et.rotation_y, et.rotation_z,
                           ei.geometry_hash,
                           r.minX, r.maxX, r.minY, r.maxY, r.minZ, r.maxZ
                    FROM element_transforms et
                    JOIN element_instances ei ON ei.guid = et.guid
                    JOIN elements_meta em ON em.guid = et.guid
                    JOIN elements_rtree r ON r.id = em.id
                    ORDER BY RANDOM() LIMIT 30
                """).fetchall()
                _ok = _fail = 0
                _worst = 0.0
                _rot_nonzero = 0
                _pivot_worst = 0.0
                _pivot_fail = 0
                _mesh_src = "base_geometries" if has_blobs else "component_geometries"
                for _row in _samples:
                    _guid, _cx, _cy, _cz, _rx, _ry, _rz, _gh, \
                        _x0, _x1, _y0, _y1, _z0, _z1 = _row
                    has_rot = abs(_rx) > 1e-6 or abs(_ry) > 1e-6 or abs(_rz) > 1e-6
                    if has_rot:
                        _rot_nonzero += 1
                    _lr = _lconn.execute(
                        "SELECT vertices FROM component_geometries WHERE geometry_hash=?",
                        (_gh,)).fetchone()
                    if not _lr or not _lr[0]:
                        continue
                    _v = np.frombuffer(_lr[0], dtype=np.float32).reshape(-1, 3)

                    # P1: BBOX_MATCH — rot@corners+centre vs rtree
                    a, b, c = _rx, _ry, _rz
                    _R = np.array([
                        [_m.cos(b)*_m.cos(c), _m.sin(a)*_m.sin(b)*_m.cos(c)-_m.cos(a)*_m.sin(c), _m.cos(a)*_m.sin(b)*_m.cos(c)+_m.sin(a)*_m.sin(c)],
                        [_m.cos(b)*_m.sin(c), _m.sin(a)*_m.sin(b)*_m.sin(c)+_m.cos(a)*_m.cos(c), _m.cos(a)*_m.sin(b)*_m.sin(c)-_m.sin(a)*_m.cos(c)],
                        [-_m.sin(b),           _m.sin(a)*_m.cos(b),                                _m.cos(a)*_m.cos(b)]
                    ])
                    _lmin = _v.min(axis=0)
                    _lmax = _v.max(axis=0)
                    _corners = np.array([
                        [_lmin[0],_lmin[1],_lmin[2]], [_lmax[0],_lmin[1],_lmin[2]],
                        [_lmin[0],_lmax[1],_lmin[2]], [_lmax[0],_lmax[1],_lmin[2]],
                        [_lmin[0],_lmin[1],_lmax[2]], [_lmax[0],_lmin[1],_lmax[2]],
                        [_lmin[0],_lmax[1],_lmax[2]], [_lmax[0],_lmax[1],_lmax[2]],
                    ])
                    _wc = (_R @ _corners.T).T + np.array([_cx, _cy, _cz])
                    _wmin = _wc.min(axis=0)
                    _wmax = _wc.max(axis=0)
                    _err = max(abs(_wmin[0]-_x0), abs(_wmax[0]-_x1),
                               abs(_wmin[1]-_y0), abs(_wmax[1]-_y1),
                               abs(_wmin[2]-_z0), abs(_wmax[2]-_z1))
                    if _err > _worst:
                        _worst = _err
                    if _err > 0.01:
                        _fail += 1
                        if _fail <= 3:
                            log(f"  FAIL BBOX_MATCH {_guid[:16]} err={_err:.4f}m "
                                f"rot=({_rx:.3f},{_ry:.3f},{_rz:.3f})")
                    else:
                        _ok += 1

                    # P2: PIVOT_CHECK — mesh centroid offset from (0,0,0)
                    # GN Instance on Points rotates around mesh origin (0,0,0).
                    # If mesh verts are offset, rotation swings them → spikes.
                    if has_rot:
                        _centroid = _v.mean(axis=0)
                        _cdist = float(np.linalg.norm(_centroid))
                        if _cdist > _pivot_worst:
                            _pivot_worst = _cdist
                        if _cdist > 1.0:
                            _pivot_fail += 1
                            if _pivot_fail <= 3:
                                log(f"  WARN PIVOT {_guid[:16]} mesh_centroid="
                                    f"({_centroid[0]:.1f},{_centroid[1]:.1f},{_centroid[2]:.1f}) "
                                    f"offset={_cdist:.1f}m from origin — "
                                    f"GN rotation will swing by {_cdist:.1f}m")

                _vconn.close()
                _lconn.close()
                _tag = "PASS" if _fail == 0 and _ok > 0 else (
                    "FAIL" if _fail > 0 else "SKIP")
                log(f"§PROOF BBOX_MATCH {_tag}  {_ok} ok, {_fail} fail  "
                    f"worst={_worst:.4f}m  rotated={_rot_nonzero}/30  "
                    f"mesh_src={_mesh_src}  (rot@lib_mesh+centre vs rtree)")
                _ptag = "PASS" if _pivot_fail == 0 else "FAIL"
                log(f"§PROOF PIVOT_CHECK {_ptag}  {_pivot_fail} meshes with centroid >1m from origin  "
                    f"worst={_pivot_worst:.1f}m  "
                    f"(>0 means GN rotation will produce spikes)")
    except Exception as _e:
        log(f"§PROOF BBOX_MATCH ERROR — {_e}")

    header("=" * 64)

    # Write log file
    with open(log_path, 'w') as f:
        f.write('\n'.join(log_lines) + '\n')
    print(f"Log: {log_path}")

    if report_fn:
        report_fn(f"GN cache: {total_instances:,} instances in {total_time:.0f}s")

    return len(baked_meshes)


def create_cache(context, db_path: str, mode: str = "full", report_fn=None):
    """
    Create .blend cache from database.

    This is the one-time baking step (~70 seconds for 49K meshes).

    Args:
        context: Blender context
        db_path: Path to federation database
        mode: Cache type - "solid" or "full" (default: "full")
        report_fn: Optional callback for progress (report_fn(message))

    Returns:
        Number of meshes created
    """
    # Large DBs → GN instance path (13 objects instead of 1M)
    element_count = _get_element_count(db_path)
    if element_count >= GN_THRESHOLD:
        print(f"[CACHE] {element_count:,} elements >= {GN_THRESHOLD:,} threshold "
              f"— switching to GN instance path")
        return create_cache_gn_instances(context, db_path, mode, report_fn)

    cache_path = get_cache_path(db_path, mode=mode)

    if report_fn:
        report_fn(f"Baking {mode} cache (one-time, ~70 seconds)...")

    print(f"\n{'='*70}")
    print(f"CREATING .BLEND CACHE ({mode.upper()} MODE)")
    print(f"{'='*70}")
    print(f"Database: {db_path}")
    print(f"Cache:    {cache_path}")
    print(f"Mode:     {mode}")

    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check which schema this database uses (GI or legacy)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='base_geometries'")
    is_gi_schema = cursor.fetchone() is not None

    # Check if surface_styles table exists (enriched DBs have it)
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='surface_styles'")
    has_styles = cursor.fetchone() is not None
    if has_styles:
        print("  ✓ surface_styles table found — using rich PBR materials")

    if is_gi_schema:
        # New GI schema: base_geometries + element_instances
        # S169: ALWAYS fetch mesh BLOBs from component_library.db (single source of truth)
        lib_path = None
        search_dir = os.path.dirname(db_path)
        for _ in range(5):
            candidate = os.path.join(search_dir, 'library', 'component_library.db')
            if os.path.exists(candidate):
                lib_path = candidate
                break
            search_dir = os.path.dirname(search_dir)

        lib_mesh_map = {}
        if lib_path:
            print(f"  S169: Mesh source → {lib_path}")
            needed = [r[0] for r in cursor.execute(
                "SELECT DISTINCT ei.geometry_hash FROM element_instances ei")]
            print(f"  Opening library: {lib_path} (waiting up to 60s if locked...)")
            lib_conn = sqlite3.connect(lib_path, timeout=60)
            BATCH = 5000
            for i in range(0, len(needed), BATCH):
                batch = needed[i:i+BATCH]
                ph = ','.join('?' * len(batch))
                for row in lib_conn.execute(
                        f"SELECT geometry_hash, vertices, faces FROM component_geometries "
                        f"WHERE geometry_hash IN ({ph})", batch):
                    lib_mesh_map[row[0]] = (row[1], row[2])
            lib_conn.close()
            print(f"  S169: {len(lib_mesh_map)}/{len(needed)} meshes from library")
        else:
            raise FileNotFoundError(
                "component_library.db not found — cannot load meshes. "
                "Run extraction with --library first.")

        style_join = ""
        style_cols = "NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL"
        if has_styles:
            style_join = "LEFT JOIN surface_styles s ON em.material_name = s.style_name"
            style_cols = ("s.transparency, s.specular_ratio, s.specular_exponent, "
                         "s.specular_r, s.specular_g, s.specular_b, "
                         "s.reflectance_method, s.surface_r, s.surface_g, s.surface_b")

        # S169: Read rotation columns if present
        cursor.execute("PRAGMA table_info(element_transforms)")
        et_cols = {r[1] for r in cursor.fetchall()}
        has_rot = 'rotation_x' in et_cols
        rot_cols = ", et.rotation_x, et.rotation_y, et.rotation_z" if has_rot else ""

        cursor.execute(f"""
            SELECT ei.geometry_hash, NULL, NULL,
                   ei.guid, em.ifc_class, em.discipline,
                   et.center_x, et.center_y, et.center_z,
                   em.material_name, em.material_rgba,
                   {style_cols}
                   {rot_cols}
            FROM element_instances ei
            JOIN elements_meta em ON ei.guid = em.guid
            LEFT JOIN element_transforms et ON ei.guid = et.guid
            {style_join}
        """)
    else:
        # Legacy schema: element_geometry
        print("  Detected legacy schema (element_geometry)")
        if has_styles:
            cursor.execute("""
                SELECT DISTINCT eg.geometry_hash, eg.vertices, eg.faces,
                       em.guid, em.ifc_class, em.discipline,
                       et.center_x, et.center_y, et.center_z,
                       em.material_name, em.material_rgba,
                       s.transparency, s.specular_ratio, s.specular_exponent,
                       s.specular_r, s.specular_g, s.specular_b,
                       s.reflectance_method, s.surface_r, s.surface_g, s.surface_b
                FROM element_geometry eg
                JOIN elements_meta em ON eg.guid = em.guid
                LEFT JOIN element_transforms et ON eg.guid = et.guid
                LEFT JOIN surface_styles s ON em.material_name = s.style_name
                WHERE eg.geometry_hash IS NOT NULL
            """)
        else:
            cursor.execute("""
                SELECT DISTINCT eg.geometry_hash, eg.vertices, eg.faces,
                       em.guid, em.ifc_class, em.discipline,
                       et.center_x, et.center_y, et.center_z,
                       em.material_name, em.material_rgba,
                       NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
                FROM element_geometry eg
                JOIN elements_meta em ON eg.guid = em.guid
                LEFT JOIN element_transforms et ON eg.guid = et.guid
                WHERE eg.geometry_hash IS NOT NULL
            """)

    geom_data = cursor.fetchall()
    total = len(geom_data)

    print(f"Creating {total:,} unique geometries with discipline organization...")

    start_time = time.time()

    # Group geometries by geometry_hash (deduplicate)
    # Map: geometry_hash -> (vertices_blob, faces_blob, [(guid, ifc_class, discipline, transform), ...])
    unique_geoms = {}
    for row in geom_data:
        geom_hash, verts_blob, faces_blob, guid, ifc_class, discipline = row[:6]
        cx, cy, cz = row[6], row[7], row[8]
        transform = (cx, cy, cz) if cx is not None else None
        material_name = row[9] if len(row) > 9 else None
        material_rgba = row[10] if len(row) > 10 else None
        # Rich surface style columns
        style_transparency = row[11] if len(row) > 11 else None
        style_spec_ratio = row[12] if len(row) > 12 else None
        style_spec_exp = row[13] if len(row) > 13 else None
        style_spec_r = row[14] if len(row) > 14 else None
        style_spec_g = row[15] if len(row) > 15 else None
        style_spec_b = row[16] if len(row) > 16 else None
        style_refl_method = row[17] if len(row) > 17 else None
        style_surf_r = row[18] if len(row) > 18 else None
        style_surf_g = row[19] if len(row) > 19 else None
        style_surf_b = row[20] if len(row) > 20 else None

        # S169: Mesh BLOBs always from library — no bypass
        if geom_hash not in lib_mesh_map:
            raise RuntimeError(
                f"Geometry hash {geom_hash} not in component_library.db — "
                f"re-extract with --library to populate.")
        verts_blob, faces_blob = lib_mesh_map[geom_hash]

        if geom_hash not in unique_geoms:
            unique_geoms[geom_hash] = {
                'vertices': verts_blob,
                'faces': faces_blob,
                'elements': []
            }
        # S170: Parse rotation from dynamic columns (after style columns)
        rot_base = 21  # style columns end at index 20
        rx = float(row[rot_base] or 0.0) if has_rot and len(row) > rot_base else 0.0
        ry = float(row[rot_base + 1] or 0.0) if has_rot and len(row) > rot_base + 1 else 0.0
        rz = float(row[rot_base + 2] or 0.0) if has_rot and len(row) > rot_base + 2 else 0.0

        unique_geoms[geom_hash]['elements'].append({
            'guid': guid,
            'ifc_class': ifc_class or 'Unknown',
            'discipline': discipline or 'Unknown',
            'transform': transform,
            'rotation': (rx, ry, rz),
            'material_name': material_name,
            'material_rgba': material_rgba,
            'style_data': {
                'transparency': style_transparency,
                'specular_ratio': style_spec_ratio,
                'specular_exponent': style_spec_exp,
                'specular_r': style_spec_r,
                'specular_g': style_spec_g,
                'specular_b': style_spec_b,
                'reflectance_method': style_refl_method,
                'surface_r': style_surf_r,
                'surface_g': style_surf_g,
                'surface_b': style_surf_b,
            } if (style_transparency is not None or style_spec_exp is not None) else None
        })

    total_unique = len(unique_geoms)
    print(f"Found {total_unique:,} unique geometries")

    # Suppress viewport redraws during bake — saves ~0.75s per 1000 meshes
    wm = context.window_manager
    wm.progress_begin(0, total_unique)

    # Create meshes
    meshes = {}
    for i, (geom_hash, geom_info) in enumerate(unique_geoms.items()):
        vertices = unpack_vertices(geom_info['vertices'])
        faces = unpack_faces(geom_info['faces'])

        mesh = bpy.data.meshes.new(f"Mesh_{geom_hash[:8]}")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()

        # Store element info in mesh custom properties for later organization
        mesh['geometry_hash'] = geom_hash
        mesh['element_count'] = len(geom_info['elements'])

        meshes[geom_hash] = {
            'mesh': mesh,
            'elements': geom_info['elements']
        }

        # Progress updates (console only — NO report_fn, NO viewport redraw)
        if (i + 1) % 10000 == 0 or (i + 1) == total_unique:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            remaining = (total_unique - i - 1) / rate if rate > 0 else 0
            wm.progress_update(i + 1)
            print(f"  {i+1:,}/{total_unique:,} meshes ({rate:.1f}/s, {remaining:.1f}s remaining)")

    wm.progress_end()
    mesh_time = time.time() - start_time
    print(f"✓ Created {len(meshes):,} meshes in {mesh_time:.2f}s")

    # Create collection hierarchy: Federation_Cached -> Discipline -> IFC_Type -> Objects
    if "Federation_Cached" in bpy.data.collections:
        bpy.data.collections.remove(bpy.data.collections["Federation_Cached"])

    root_coll = bpy.data.collections.new("Federation_Cached")
    # NOTE: Do NOT link to scene yet — linking triggers depsgraph rebuild
    # per object.  We link AFTER all objects are created (single rebuild).

    # Store database path in root collection custom properties
    root_coll['database_path'] = db_path
    print(f"Stored database path in collection: {db_path}")

    discipline_collections = {}

    # Import material creator for rich PBR materials
    from .stage2_tessellation_loader import get_or_create_db_material

    # Create objects organized by discipline (with material assignment)
    print(f"Creating objects organized by discipline (with materials)...")
    obj_start = time.time()

    obj_count = 0
    mat_count = 0
    rot_applied = 0
    for i, (geom_hash, geom_info) in enumerate(meshes.items()):
        mesh = geom_info['mesh']
        elements = geom_info['elements']

        # Create objects for each element instance (to preserve discipline organization)
        for element in elements:
            discipline = element['discipline']
            ifc_class = element['ifc_class']
            guid = element['guid']

            # Get or create discipline collection (NOT linked to root yet)
            if discipline not in discipline_collections:
                disc_coll = bpy.data.collections.new(discipline)
                # Defer: root_coll.children.link(disc_coll) — done after loop
                discipline_collections[discipline] = disc_coll
            else:
                disc_coll = discipline_collections[discipline]

            # Create object (instance of shared mesh)
            obj = bpy.data.objects.new(f"{ifc_class}_{guid[:8]}", mesh)
            obj['guid'] = guid
            obj['ifc_class'] = ifc_class
            obj['discipline'] = discipline

            # Apply transform if available (GI databases store geometry at origin)
            transform = element.get('transform')
            if transform and all(t is not None for t in transform):
                obj.location = transform  # (center_x, center_y, center_z)

            # S170: Apply rotation (Euler XYZ radians from IFC placement matrix)
            rotation = element.get('rotation', (0, 0, 0))
            if any(r != 0 for r in rotation):
                obj.rotation_euler = rotation
                rot_applied += 1

            # Assign material from database (with rich surface styles if available)
            material_rgba = element.get('material_rgba')
            if material_rgba:
                material_name = element.get('material_name') or "<Unnamed>"
                style_data = element.get('style_data')
                material = get_or_create_db_material(
                    material_name, material_rgba, discipline,
                    style_data=style_data
                )
                # Ensure mesh has at least one material slot
                if len(obj.data.materials) == 0:
                    obj.data.materials.append(None)
                # Object-level material override (doesn't affect other instances)
                if len(obj.material_slots) > 0:
                    obj.material_slots[0].link = 'OBJECT'
                    obj.material_slots[0].material = material
                mat_count += 1

            disc_coll.objects.link(obj)
            obj_count += 1

        if (i + 1) % 1000 == 0:
            print(f"  {obj_count:,} objects created...")

    obj_time = time.time() - obj_start
    print(f"✓ Created {obj_count:,} objects in {len(discipline_collections)} disciplines in {obj_time:.2f}s")
    print(f"  Materials assigned: {mat_count:,} (unique Blender materials: {len(bpy.data.materials):,})")
    print(f"  §ROTATION applied: {rot_applied:,}/{obj_count:,} objects rotated")
    print(f"  Disciplines: {', '.join(sorted(discipline_collections.keys()))}")

    # NOW link all discipline collections to root, then root to scene
    # — single depsgraph rebuild for all objects
    link_start = time.time()
    for disc_name, disc_coll in discipline_collections.items():
        root_coll.children.link(disc_coll)
    context.scene.collection.children.link(root_coll)
    print(f"✓ Scene graph linked in {time.time() - link_start:.2f}s "
          f"({len(discipline_collections)} disciplines, single depsgraph rebuild)")

    # Store database path in scene properties (absolute path)
    props = context.scene.BIMFederationProperties
    props.federation_database_path = str(db_path)
    print(f"Stored database path in scene properties: {db_path}")

    # Enable discipline legend before saving (so it's active when .blend is opened)
    from . import discipline_legend
    discipline_legend.enable_legend()
    print(f"✓ Discipline legend enabled for cache")

    # Double the view distance so objects don't disappear at horizon (2x current clip distance)
    try:
        for cam in bpy.data.cameras:
            original_clip = cam.clip_end
            cam.clip_end = original_clip * 2.0

        for screen in bpy.data.screens:
            for area in screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            original_clip = space.clip_end
                            space.clip_end = original_clip * 2.0

        print(f"✓ Doubled view distance for better horizon visibility")
    except Exception as e:
        print(f"Warning: Could not adjust view distance: {e}")

    # Save .blend
    print(f"Saving cache to {cache_path}...")
    save_start = time.time()

    bpy.ops.wm.save_as_mainfile(filepath=cache_path)

    save_time = time.time() - save_start
    file_size_mb = os.path.getsize(cache_path) / (1024 * 1024)

    total_time = time.time() - start_time

    print(f"✓ Saved .blend cache in {save_time:.2f}s")
    print(f"  File size: {file_size_mb:.1f} MB")
    print(f"  Total time: {total_time:.2f}s")
    print(f"{'='*70}\n")

    if report_fn:
        report_fn(f"Cache created! ({total_time:.0f}s)")

    conn.close()

    return len(meshes)


def load_from_cache(context, db_path: str):
    """
    Load federation from .blend cache (fast!).

    This is 10x faster than loading from database (~15 seconds vs 3 minutes).

    Args:
        context: Blender context
        db_path: Path to federation database (cache path derived from this)

    Returns:
        Number of objects loaded
    """
    cache_path = get_cache_path(db_path)

    print(f"\n{'='*70}")
    print(f"LOADING FROM .BLEND CACHE (FAST!)")
    print(f"{'='*70}")
    print(f"Database: {db_path}")
    print(f"Cache:    {cache_path}")

    start_time = time.time()

    # Append collection from .blend
    with bpy.data.libraries.load(cache_path, link=False) as (data_from, data_to):
        # Load the Federation_Cached collection
        if "Federation_Cached" in data_from.collections:
            data_to.collections = ["Federation_Cached"]
        else:
            # Fallback: load all collections
            data_to.collections = data_from.collections

    # Link to scene
    obj_count = 0
    discipline_count = 0
    for coll in data_to.collections:
        context.scene.collection.children.link(coll)

        # Verify database path matches (stored in root collection)
        if 'database_path' in coll.keys():
            cached_db_path = coll['database_path']
            print(f"Cache created from: {cached_db_path}")
            if cached_db_path != db_path:
                print(f"⚠ Warning: Database path mismatch!")
                print(f"  Expected: {db_path}")
                print(f"  Cached:   {cached_db_path}")

        # Count objects and disciplines
        def count_objects_and_disciplines(c):
            count = len(c.objects)
            disc_count = len(c.children)  # Discipline collections are direct children
            for child in c.children:
                child_objs, _ = count_objects_and_disciplines(child)
                count += child_objs
            return count, disc_count

        objs, discs = count_objects_and_disciplines(coll)
        obj_count += objs
        discipline_count += discs

    elapsed = time.time() - start_time

    print(f"✓ Loaded {obj_count:,} objects in {discipline_count} disciplines in {elapsed:.2f}s")
    print(f"  10x faster than database loading!")
    print(f"{'='*70}\n")

    return obj_count


def start_background_baking(db_path: str, mode: str = "full", cache_path: str = None) -> str:
    """
    Start background cache baking in a separate Blender process (non-blocking).

    This launches a headless Blender instance that creates the cache while
    the user's viewport remains responsive.

    Args:
        db_path: Path to federation database
        mode: Cache type - "solid" or "full" (default: "full")
        cache_path: Optional explicit cache path (if None, auto-generated)

    Returns:
        Path to cache file being created

    Usage:
        cache_path = start_background_baking(db_path, mode="solid")
        # User's viewport stays responsive!
        # Check for completion: os.path.exists(f"{cache_path}.complete")
    """
    if cache_path is None:
        cache_path = get_cache_path(db_path, mode=mode)
    else:
        # Ensure it's a string, not Path
        cache_path = str(cache_path)

    # Get path to background baking script
    script_path = os.path.join(os.path.dirname(__file__), "bake_cache_background.py")

    # Get Blender executable path
    blender_path = bpy.app.binary_path

    # Output log path
    log_path = f"{cache_path}.log"

    print(f"\n{'='*70}")
    print(f"STARTING BACKGROUND CACHE BAKING")
    print(f"{'='*70}")
    print(f"Database:    {db_path}")
    print(f"Cache:       {cache_path}")
    print(f"Mode:        {mode}")
    print(f"Log:         {log_path}")
    print(f"Blender:     {blender_path}")
    print(f"Script:      {script_path}")

    # Launch headless Blender as subprocess
    cmd = [
        blender_path,
        '--background',           # No GUI
        '--python', script_path,  # Run baking script
        '--',                     # Separator for script args
        db_path,                  # Arg 1: Database path
        cache_path,               # Arg 2: Output .blend path
        mode                      # Arg 3: Cache mode
    ]

    print(f"\nCommand: {' '.join(cmd)}")
    print(f"\n🚀 Background baking started!")
    print(f"   Your viewport will remain responsive.")
    print(f"   Check progress: tail -f {log_path}")
    print(f"   Completion flag: {cache_path}.complete")
    print(f"{'='*70}\n")

    # Start subprocess (non-blocking!)
    with open(log_path, 'w') as log_file:
        subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=os.path.dirname(db_path)  # Run in database directory
        )

    return cache_path


def is_baking_in_progress(cache_path: str) -> bool:
    """
    Check if background baking is in progress.

    Returns:
        True if baking is running, False otherwise
    """
    # Check for completion or failure flags
    complete_flag = f"{cache_path}.complete"
    failed_flag = f"{cache_path}.failed"

    if os.path.exists(complete_flag):
        return False  # Baking complete

    if os.path.exists(failed_flag):
        return False  # Baking failed

    # Check if cache file exists (being written)
    # and log file exists (background process running)
    log_path = f"{cache_path}.log"

    if os.path.exists(log_path):
        # Log exists - check if it's recent (within last 10 seconds)
        log_age = time.time() - os.path.getmtime(log_path)
        if log_age < 10:
            return True  # Baking in progress

    return False  # No active baking


def get_baking_status(cache_path: str) -> dict:
    """
    Get status of background baking.

    Returns:
        dict with keys: 'status' (pending/running/complete/failed), 'message'
    """
    complete_flag = f"{cache_path}.complete"
    failed_flag = f"{cache_path}.failed"
    log_path = f"{cache_path}.log"

    if os.path.exists(complete_flag):
        return {
            'status': 'complete',
            'message': 'Cache ready!',
            'cache_path': cache_path
        }

    if os.path.exists(failed_flag):
        with open(failed_flag) as f:
            error_msg = f.read()
        return {
            'status': 'failed',
            'message': error_msg,
            'cache_path': cache_path
        }

    if is_baking_in_progress(cache_path):
        # Try to read last line of log for progress
        try:
            with open(log_path) as f:
                lines = f.readlines()
                last_line = lines[-1].strip() if lines else "Processing..."
        except:
            last_line = "Processing..."

        return {
            'status': 'running',
            'message': last_line,
            'cache_path': cache_path
        }

    return {
        'status': 'pending',
        'message': 'Not started',
        'cache_path': cache_path
    }
