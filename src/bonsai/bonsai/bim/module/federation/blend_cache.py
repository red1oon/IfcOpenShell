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
from pathlib import Path


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

    if is_gi_schema:
        # New GI schema: base_geometries + element_instances
        print("  Detected GI schema (base_geometries + element_instances)")
        cursor.execute("""
            SELECT bg.geometry_hash, bg.vertices, bg.faces,
                   ei.guid, em.ifc_class, em.discipline,
                   et.center_x, et.center_y, et.center_z
            FROM base_geometries bg
            JOIN element_instances ei ON bg.geometry_hash = ei.geometry_hash
            JOIN elements_meta em ON ei.guid = em.guid
            LEFT JOIN element_transforms et ON ei.guid = et.guid
        """)
    else:
        # Legacy schema: element_geometry
        print("  Detected legacy schema (element_geometry)")
        cursor.execute("""
            SELECT DISTINCT eg.geometry_hash, eg.vertices, eg.faces,
                   em.guid, em.ifc_class, em.discipline,
                   et.center_x, et.center_y, et.center_z
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
        if len(row) == 9:  # With transforms
            geom_hash, verts_blob, faces_blob, guid, ifc_class, discipline, cx, cy, cz = row
            transform = (cx, cy, cz) if cx is not None else None
        else:  # Legacy without transforms
            geom_hash, verts_blob, faces_blob, guid, ifc_class, discipline = row
            transform = None

        if geom_hash not in unique_geoms:
            unique_geoms[geom_hash] = {
                'vertices': verts_blob,
                'faces': faces_blob,
                'elements': []
            }
        unique_geoms[geom_hash]['elements'].append({
            'guid': guid,
            'ifc_class': ifc_class or 'Unknown',
            'discipline': discipline or 'Unknown',
            'transform': transform
        })

    total_unique = len(unique_geoms)
    print(f"Found {total_unique:,} unique geometries")

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

        # Progress updates
        if (i + 1) % 1000 == 0 or (i + 1) == total_unique:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            remaining = (total_unique - i - 1) / rate if rate > 0 else 0

            if report_fn:
                report_fn(f"Baking cache: {i+1:,}/{total_unique:,} meshes ({int(remaining)}s remaining)")

            print(f"  {i+1:,}/{total_unique:,} meshes ({rate:.1f}/s, {remaining:.1f}s remaining)")

    mesh_time = time.time() - start_time
    print(f"✓ Created {len(meshes):,} meshes in {mesh_time:.2f}s")

    # Create collection hierarchy: Federation_Cached -> Discipline -> IFC_Type -> Objects
    if "Federation_Cached" in bpy.data.collections:
        bpy.data.collections.remove(bpy.data.collections["Federation_Cached"])

    root_coll = bpy.data.collections.new("Federation_Cached")
    context.scene.collection.children.link(root_coll)

    # Store database path in root collection custom properties
    root_coll['database_path'] = db_path
    print(f"Stored database path in collection: {db_path}")

    discipline_collections = {}

    # Create objects organized by discipline
    print(f"Creating objects organized by discipline...")
    obj_start = time.time()

    obj_count = 0
    for i, (geom_hash, geom_info) in enumerate(meshes.items()):
        mesh = geom_info['mesh']
        elements = geom_info['elements']

        # Create objects for each element instance (to preserve discipline organization)
        for element in elements:
            discipline = element['discipline']
            ifc_class = element['ifc_class']
            guid = element['guid']

            # Get or create discipline collection
            if discipline not in discipline_collections:
                disc_coll = bpy.data.collections.new(discipline)
                root_coll.children.link(disc_coll)
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

            disc_coll.objects.link(obj)
            obj_count += 1

        if (i + 1) % 1000 == 0:
            print(f"  {obj_count:,} objects created...")

    obj_time = time.time() - obj_start
    print(f"✓ Created {obj_count:,} objects in {len(discipline_collections)} disciplines in {obj_time:.2f}s")
    print(f"  Disciplines: {', '.join(sorted(discipline_collections.keys()))}")

    # Store database path in scene properties (absolute path)
    props = context.scene.BIMFederationProperties
    props.federation_database_path = str(db_path)
    print(f"Stored database path in scene properties: {db_path}")

    # Enable discipline legend before saving (so it's active when .blend is opened)
    from . import discipline_legend
    discipline_legend.enable_legend()
    print(f"✓ Discipline legend enabled for cache")

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
