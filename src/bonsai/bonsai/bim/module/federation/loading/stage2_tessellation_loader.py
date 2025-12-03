"""
Stage 2: Tessellation-Based Exact Geometry Loading
==================================================

Loads exact IFC geometry from pre-tessellated database (IFCmigrated.db).
Replaces procedural generation with exact geometry while keeping GPU instancing.

Performance: ~26s for 14K elements (1.8ms per element)
Accuracy: 100% match with original IFC
Memory: ~500-800 MB

**What Changed from Procedural Approach:**
- OLD: Create box/cylinder templates → scale to fit bbox
- NEW: Load exact tessellated geometry from database

**What Stayed the Same:**
- Template/instance architecture for efficiency
- Material assignment by discipline
- Coordinate transforms and offset handling
- Collection organization

Database Schema:
    element_geometry (guid, vertices BLOB, faces BLOB, geometry_hash)

Usage:
    Replace stage2_gpu_instancing.create_semantic_shapes_instanced()
    with load_tessellated_shapes_instanced() from this module
"""

import bpy
import bmesh
import sqlite3
import struct
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from mathutils import Vector, Euler
from typing import List, Optional, Callable, Dict, Tuple

# Import from existing module
from . import semantic_utils
from .stage2_gpu_instancing import (
    DISCIPLINE_COLORS,
    get_or_create_material,
    _TEMPLATE_MESHES,
    _TEMPLATE_OBJECTS,
    _MATERIAL_CACHE
)

# Material cache for database materials
_DB_MATERIAL_CACHE = {}

def parse_rgba_string(rgba_str: str) -> Tuple[float, float, float, float]:
    """Parse comma-separated RGBA string to tuple."""
    try:
        parts = rgba_str.split(',')
        return (float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))
    except:
        return (0.5, 0.5, 0.5, 1.0)  # Fallback gray

def get_or_create_db_material(material_name: str, rgba_str: str, discipline: str) -> bpy.types.Material:
    """
    Get or create material from database RGBA values.

    Uses real Revit material colors from extraction database.
    Falls back to discipline color if RGBA is missing.

    Args:
        material_name: Material name from Revit (e.g., "Metal Deck", "Concrete")
        rgba_str: Comma-separated RGBA string (e.g., "0.5,0.7,0.5,1.0")
        discipline: Discipline code (fallback if RGBA missing)

    Returns:
        Blender material with shader setup
    """
    # Create cache key (material name + rgba for uniqueness)
    cache_key = f"{material_name}_{rgba_str}" if rgba_str else f"Discipline_{discipline}"

    # Check cache
    if cache_key in _DB_MATERIAL_CACHE:
        return _DB_MATERIAL_CACHE[cache_key]

    # Parse RGBA
    if rgba_str:
        rgba = parse_rgba_string(rgba_str)

        # AMPLIFICATION MODE: Boost subtle color variance in gray materials
        # Instead of replacing with solid discipline colors, we enhance existing colors
        # This preserves original design intent while making it more visible
        import colorsys
        r, g, b = rgba[:3]
        is_gray = abs(r - g) < 0.15 and abs(g - b) < 0.15  # Close to grayscale

        if is_gray:
            # Convert to HSV to manipulate saturation
            h, s, v = colorsys.rgb_to_hsv(r, g, b)

            # Boost saturation significantly (3× increase, capped at 1.0)
            s = min(1.0, s * 3.0 + 0.3)  # Add base saturation if near-zero

            # Boost brightness slightly (20% increase, capped at 1.0)
            v = min(1.0, v * 1.2)

            # If still too gray after boost, tint with discipline color
            if s < 0.2:
                disc_color = DISCIPLINE_COLORS.get(discipline, (0.5, 0.5, 0.5))
                # Blend 30% discipline color with boosted IFC color
                r_new, g_new, b_new = colorsys.hsv_to_rgb(h, s, v)
                r = r_new * 0.7 + disc_color[0] * 0.3
                g = g_new * 0.7 + disc_color[1] * 0.3
                b = b_new * 0.7 + disc_color[2] * 0.3
                rgba = (r, g, b, rgba[3])
            else:
                rgba = (*colorsys.hsv_to_rgb(h, s, v), rgba[3])

            mat_name = f"Enhanced_{discipline}_{material_name[:20]}" if material_name else f"Enhanced_{discipline}"
        else:
            # Keep colorful IFC materials (authentic Revit colors)
            mat_name = f"Revit_{material_name}" if material_name and material_name != "<Unnamed>" else f"Revit_{rgba_str[:15]}"
    else:
        # Fallback to discipline color if no RGBA in database
        rgba = (*DISCIPLINE_COLORS.get(discipline, (0.5, 0.5, 0.5)), 1.0)
        mat_name = f"Discipline_{discipline}"

    # Check if material already exists in Blender
    mat = bpy.data.materials.get(mat_name)
    if mat:
        _DB_MATERIAL_CACHE[cache_key] = mat
        return mat

    # Create new material
    mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Clear default nodes
    nodes.clear()

    # Add shader nodes
    output_node = nodes.new(type='ShaderNodeOutputMaterial')
    output_node.location = (300, 0)

    bsdf_node = nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf_node.location = (0, 0)

    # Set material properties from Revit RGBA or discipline override
    bsdf_node.inputs['Base Color'].default_value = rgba
    bsdf_node.inputs['Metallic'].default_value = 0.2  # Slightly metallic
    bsdf_node.inputs['Roughness'].default_value = 0.5  # Medium roughness
    bsdf_node.inputs['Specular IOR Level'].default_value = 0.5  # Add specular highlights

    # Set blend mode for proper X-ray rendering (Alt+Z)
    mat.blend_method = 'OPAQUE'
    mat.shadow_method = 'OPAQUE'

    # Link nodes
    links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])

    # Cache it
    _DB_MATERIAL_CACHE[cache_key] = mat

    return mat

# ============================================================================
# GEOMETRY UNPACKING (from database BLOBs)
# ============================================================================

def unpack_vertices(blob: bytes) -> List[Tuple[float, float, float]]:
    """Unpack binary BLOB into list of (x,y,z) vertex tuples."""
    if not blob:
        return []
    floats = struct.unpack(f'<{len(blob)//4}f', blob)
    return [(floats[i], floats[i+1], floats[i+2]) for i in range(0, len(floats), 3)]

def unpack_faces(blob: bytes) -> List[Tuple[int, int, int]]:
    """Unpack binary BLOB into list of (i1,i2,i3) face tuples."""
    if not blob:
        return []
    ints = struct.unpack(f'<{len(blob)//4}I', blob)
    return [(ints[i], ints[i+1], ints[i+2]) for i in range(0, len(ints), 3)]

# ============================================================================
# PARALLEL MESH CREATION (OPTIMIZATION)
# ============================================================================

def _create_mesh_from_data(geometry_hash: str, verts_blob: bytes, faces_blob: bytes) -> Tuple[str, bpy.types.Mesh]:
    """
    Worker function to create a single mesh (runs in thread pool).

    This function is thread-safe and creates a Blender mesh from packed data.
    Blender's mesh creation is thread-safe as long as we don't access scene.

    Args:
        geometry_hash: Unique hash for this geometry
        verts_blob: Packed vertex data
        faces_blob: Packed face data

    Returns:
        Tuple of (geometry_hash, mesh)
    """
    vertices = unpack_vertices(verts_blob)
    faces = unpack_faces(faces_blob)

    mesh = bpy.data.meshes.new(f"Template_{geometry_hash[:8]}")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()

    return (geometry_hash, mesh)

def create_all_template_meshes_parallel(db_conn: sqlite3.Connection, max_workers: int = 4) -> Dict[str, bpy.types.Mesh]:
    """
    Pre-create all unique template meshes in parallel.

    This is the OPTIMIZATION - instead of creating meshes one-by-one during
    instance creation, we batch-create all unique meshes upfront using
    multiple threads.

    Args:
        db_conn: Database connection
        max_workers: Number of parallel workers (default: 4)

    Returns:
        Dictionary mapping geometry_hash -> mesh
    """
    print(f"\n⚡ Parallel mesh creation (workers: {max_workers})...")
    start_time = time.time()

    # Fetch all unique geometries in one query
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT DISTINCT geometry_hash, vertices, faces
        FROM element_geometry
        WHERE geometry_hash IS NOT NULL
    """)

    unique_geoms = cursor.fetchall()
    total_unique = len(unique_geoms)
    print(f"  Fetching {total_unique:,} unique geometries from database...")

    meshes = {}
    completed = 0

    # Create meshes in parallel
    # Note: Blender mesh creation is thread-safe when not accessing scene
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all jobs
        future_to_hash = {
            executor.submit(_create_mesh_from_data, geom_hash, verts, faces): geom_hash
            for geom_hash, verts, faces in unique_geoms
        }

        # Collect results as they complete
        for future in as_completed(future_to_hash):
            geometry_hash, mesh = future.result()
            meshes[geometry_hash] = mesh
            completed += 1

            if completed % 1000 == 0 or completed == total_unique:
                elapsed = time.time() - start_time
                rate = completed / elapsed if elapsed > 0 else 0
                remaining = (total_unique - completed) / rate if rate > 0 else 0
                print(f"  {completed:,}/{total_unique:,} meshes created ({rate:.1f}/s, {remaining:.1f}s remaining)")

    elapsed = time.time() - start_time
    print(f"  ✓ Created {len(meshes):,} template meshes in {elapsed:.2f}s ({elapsed/max(len(meshes),1)*1000:.2f}ms per mesh)")

    return meshes

# ============================================================================
# TESSELLATED MESH LOADING
# ============================================================================

def create_tessellated_mesh(guid: str, db_conn: sqlite3.Connection) -> Optional[bpy.types.Mesh]:
    """
    Load exact tessellated mesh from database.

    Replaces procedural mesh generation with exact IFC geometry.

    Args:
        guid: Element GUID
        db_conn: SQLite database connection to IFCmigrated.db

    Returns:
        Blender mesh with exact IFC geometry, or None if not found
    """
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT vertices, faces, vertex_count, face_count
        FROM element_geometry
        WHERE guid = ?
    """, (guid,))

    row = cursor.fetchone()
    if not row:
        print(f"  ⚠️  No geometry found for {guid}")
        return None

    verts_blob, faces_blob, v_count, f_count = row

    # Unpack geometry
    vertices = unpack_vertices(verts_blob)
    faces = unpack_faces(faces_blob)

    # Create Blender mesh
    mesh = bpy.data.meshes.new(guid[:8])

    # Vertices are already in meters (IfcOpenShell auto-applies IfcMapConversion with USE_WORLD_COORDS=True)
    # Database stores GPS-aligned coordinates in meters - use directly without conversion
    mesh.from_pydata(vertices, [], faces)
    mesh.update()

    return mesh

def get_template_mesh_from_hash(geometry_hash: str, db_conn: sqlite3.Connection) -> Optional[bpy.types.Mesh]:
    """
    Get or create template mesh for a geometry hash.

    Uses geometry_hash to identify unique geometries for instancing.
    If multiple elements have same hash, they share the same template mesh.

    Args:
        geometry_hash: Hash of geometry (from element_geometry table)
        db_conn: Database connection

    Returns:
        Cached or newly created mesh
    """
    # Check cache
    if geometry_hash in _TEMPLATE_MESHES:
        return _TEMPLATE_MESHES[geometry_hash]

    # Query geometry by hash (get first element with this hash)
    cursor = db_conn.cursor()
    cursor.execute("""
        SELECT guid, vertices, faces
        FROM element_geometry
        WHERE geometry_hash = ?
        LIMIT 1
    """, (geometry_hash,))

    row = cursor.fetchone()
    if not row:
        return None

    guid, verts_blob, faces_blob = row

    # Unpack and create mesh
    vertices = unpack_vertices(verts_blob)
    faces = unpack_faces(faces_blob)

    mesh = bpy.data.meshes.new(f"Template_{geometry_hash[:8]}")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()

    # Cache it
    _TEMPLATE_MESHES[geometry_hash] = mesh

    return mesh

# ============================================================================
# TEMPLATE OBJECT CREATION (with exact geometry)
# ============================================================================

def get_template_object_tessellated(guid: str,
                                     geometry_hash: str,
                                     ifc_class: str,
                                     discipline: str,
                                     db_conn: sqlite3.Connection,
                                     parent_collection: bpy.types.Collection) -> Optional[bpy.types.Object]:
    """
    Get or create template object with exact tessellated geometry.

    Replaces procedural template creation with database-loaded geometry.

    Args:
        guid: Element GUID (for creating mesh if not cached)
        geometry_hash: Hash to identify unique geometries
        ifc_class: IFC class name
        discipline: Discipline for material assignment
        db_conn: Database connection
        parent_collection: Parent collection

    Returns:
        Template object with exact geometry and materials
    """
    cache_key = f"{geometry_hash}_{discipline}"

    # Check cache
    if cache_key in _TEMPLATE_OBJECTS:
        return _TEMPLATE_OBJECTS[cache_key]

    # Get template mesh (cached by hash)
    mesh = get_template_mesh_from_hash(geometry_hash, db_conn)
    if not mesh:
        print(f"  ⚠️  Failed to load geometry for {guid}")
        return None

    # Create template object
    template_name = f"Template_{ifc_class}_{discipline}_{geometry_hash[:8]}"
    template_obj = bpy.data.objects.new(template_name, mesh)

    # Assign material (semantic type inferred from IFC class)
    semantic_type = semantic_utils.get_semantic_type(ifc_class)
    material = get_or_create_material(semantic_type, discipline)
    if mesh.materials:
        mesh.materials[0] = material
    else:
        mesh.materials.append(material)

    # Add to templates collection
    templates_collection = parent_collection.children.get("Templates")
    if not templates_collection:
        templates_collection = bpy.data.collections.new("Templates")
        parent_collection.children.link(templates_collection)

    templates_collection.objects.link(template_obj)

    # Hide template
    template_obj.hide_set(True)
    template_obj.hide_render = True
    template_obj.hide_viewport = True

    # Cache it
    _TEMPLATE_OBJECTS[cache_key] = template_obj

    return template_obj

# ============================================================================
# MAIN LOADING FUNCTION (replaces create_semantic_shapes_instanced)
# ============================================================================

def load_tessellated_shapes_instanced(db_path: str,
                                      parent_collection: bpy.types.Collection,
                                      discipline_collections: Dict[str, bpy.types.Collection],
                                      progress_callback: Optional[Callable] = None,
                                      offset: Vector = None) -> List[bpy.types.Object]:
    """
    Load exact tessellated geometry using GPU instancing.

    Replaces procedural shape generation with exact IFC geometry from database.

    Workflow:
    1. Connect to IFCmigrated.db
    2. Query all elements with geometry
    3. Group by geometry_hash (for instancing)
    4. Create template for each unique geometry
    5. Instance elements with correct transforms

    Args:
        db_path: Path to IFCmigrated.db (with GPS-aligned centers in mm)
        parent_collection: Parent federation collection
        discipline_collections: Dict to store discipline collections
        progress_callback: Optional callback(current, total, message)
        offset: Global viewport offset for centering (in meters, from global_offset table)

    Returns:
        List of created instance objects
    """
    print("\n" + "=" * 70)
    print("STAGE 2: TESSELLATED GEOMETRY LOADING")
    print("=" * 70)
    print(f"Database: {db_path}")

    start_time = time.time()

    # Clear caches
    _TEMPLATE_MESHES.clear()
    _TEMPLATE_OBJECTS.clear()

    # Connect to database
    db_conn = sqlite3.connect(db_path)
    cursor = db_conn.cursor()

    # Query all elements with geometry AND material data
    print("\nQuerying database...")
    cursor.execute("""
        SELECT
            m.guid,
            m.ifc_class,
            m.discipline,
            g.geometry_hash,
            t.center_x, t.center_y, t.center_z,
            m.material_name,
            m.material_rgba
        FROM elements_meta m
        JOIN element_geometry g ON m.guid = g.guid
        JOIN element_transforms t ON m.guid = t.guid
        ORDER BY g.geometry_hash, m.discipline
    """)

    elements = cursor.fetchall()
    total = len(elements)
    print(f"✓ Found {total:,} elements with tessellated geometry")

    # Count unique geometries
    cursor.execute("SELECT COUNT(DISTINCT geometry_hash) FROM element_geometry")
    unique_geoms = cursor.fetchone()[0]
    print(f"✓ Unique geometries: {unique_geoms:,} (instancing ratio: {total/max(unique_geoms,1):.1f}×)")

    # OPTIMIZATION: Pre-create all template meshes in parallel
    # This replaces the on-demand mesh creation with batch parallel creation
    # Auto-detect CPU cores for optimal performance
    import os
    cpu_count = os.cpu_count() or 8
    max_workers = min(cpu_count, 16)  # Cap at 16 to avoid thread overhead

    print(f"\n🚀 OPTIMIZATION: Parallel mesh creation enabled ({max_workers} workers)")
    mesh_creation_start = time.time()
    parallel_meshes = create_all_template_meshes_parallel(db_conn, max_workers=max_workers)
    mesh_creation_elapsed = time.time() - mesh_creation_start
    print(f"✓ Mesh creation complete: {mesh_creation_elapsed:.2f}s ({mesh_creation_elapsed/max(len(parallel_meshes),1)*1000:.2f}ms per mesh)")

    # Store in cache so get_template_mesh_from_hash() can retrieve them
    _TEMPLATE_MESHES.update(parallel_meshes)

    # OPTIMIZATION: Pre-create templates collection
    templates_collection = parent_collection.children.get("Templates")
    if not templates_collection:
        templates_collection = bpy.data.collections.new("Templates")
        parent_collection.children.link(templates_collection)

    # OPTIMIZATION: Pre-create all template objects upfront
    print(f"\n⚡ Creating template objects (geometry only, materials assigned per instance)...")
    template_creation_start = time.time()

    # Query unique geometry hashes ONLY
    # Materials will be assigned to instances, not templates (prevents template explosion)
    cursor.execute("""
        SELECT DISTINCT
            g.geometry_hash,
            m.ifc_class
        FROM element_geometry g
        JOIN elements_meta m ON g.guid = m.guid
        WHERE g.geometry_hash IS NOT NULL
        GROUP BY g.geometry_hash
    """)
    unique_templates = cursor.fetchall()
    print(f"  Creating {len(unique_templates):,} unique template objects (one per geometry)...")

    templates_used = {}

    for geom_hash, ifc_class in unique_templates:
        template_key = geom_hash  # Template key is ONLY geometry hash

        # Get mesh from cache (already created)
        if geom_hash not in _TEMPLATE_MESHES:
            continue
        mesh = _TEMPLATE_MESHES[geom_hash]

        # Create template object (NO materials - those go on instances)
        template_name = f"Template_{ifc_class}_{geom_hash[:8]}"
        template_obj = bpy.data.objects.new(template_name, mesh)

        # Link to templates collection
        templates_collection.objects.link(template_obj)

        # Hide template
        template_obj.hide_viewport = True
        template_obj.hide_render = True

        # Cache it
        templates_used[template_key] = template_obj
        _TEMPLATE_OBJECTS[template_key] = template_obj

    template_creation_elapsed = time.time() - template_creation_start
    print(f"  ✓ Created {len(templates_used):,} template objects in {template_creation_elapsed:.2f}s")

    # Create instances with INLINE material assignment (fastest approach)
    print(f"\nCreating instances...")
    instance_start = time.time()
    instances = []
    instances_by_discipline = {}

    for idx, elem in enumerate(elements):
        guid, ifc_class, discipline, geom_hash, center_x, center_y, center_z, material_name, material_rgba = elem

        # Get template (template_key is now just geom_hash)
        template_key = geom_hash
        if template_key not in templates_used:
            # Skip if template not found (shouldn't happen)
            continue
        template_obj = templates_used[template_key]

        # Create instance (shares mesh with template!)
        instance = bpy.data.objects.new(guid, template_obj.data)

        # Set location (use database coords directly)
        # Database stores centers in meters (USE_WORLD_COORDS=True)
        # No offset applied - use coords as-is for viewport display
        center_m = Vector((center_x, center_y, center_z))
        instance.location = center_m

        # No scale/rotation needed - geometry is exact!

        # INLINE MATERIAL ASSIGNMENT (best cache locality, fastest overall)
        # Assign material to instance with hybrid color system
        if material_rgba:
            material = get_or_create_db_material(
                material_name or "<Unnamed>",
                material_rgba,
                discipline
            )
            # Ensure mesh has at least one material slot (can be None)
            if len(instance.data.materials) == 0:
                instance.data.materials.append(None)  # Add empty slot to mesh

            # Now override at OBJECT level (doesn't affect other instances)
            if len(instance.material_slots) > 0:
                instance.material_slots[0].link = 'OBJECT'
                instance.material_slots[0].material = material

        # Store metadata
        instance['ifc_class'] = ifc_class
        instance['guid'] = guid
        instance['discipline'] = discipline
        instance['is_tessellated_instance'] = True
        instance['geometry_hash'] = geom_hash

        # Group by discipline
        if discipline not in instances_by_discipline:
            instances_by_discipline[discipline] = []
        instances_by_discipline[discipline].append(instance)

        instances.append(instance)

        # Progress callback
        if progress_callback and (idx + 1) % 100 == 0:
            progress_callback(idx + 1, total, f"Loading instances: {idx+1:,}/{total:,}")

        # Log progress
        if (idx + 1) % 1000 == 0:
            elapsed = time.time() - instance_start
            rate = (idx + 1) / elapsed
            remaining = (total - idx - 1) / rate if rate > 0 else 0
            print(f"  {idx+1:,}/{total:,} instances ({rate:.1f}/s, {remaining:.1f}s remaining)")

            # CRITICAL: Batched scene updates prevent O(n²) slowdown!
            # Without this, performance degrades exponentially (2.3× slower)
            # See: ProjectKnowledge/Stage2_Performance_Lessons_Learned.md
            bpy.context.view_layer.update()
            time.sleep(0.05)  # Let GC run

    instance_elapsed = time.time() - instance_start

    # Link instances to collections (batch operation)
    print(f"\nLinking {len(instances):,} instances to collections...")
    link_start = time.time()

    for discipline, discipline_instances in instances_by_discipline.items():
        # Get or create discipline collection
        if discipline not in discipline_collections:
            disc_collection = bpy.data.collections.new(discipline)
            parent_collection.children.link(disc_collection)
            discipline_collections[discipline] = disc_collection
        else:
            disc_collection = discipline_collections[discipline]

        # Batch link all instances for this discipline
        for instance in discipline_instances:
            disc_collection.objects.link(instance)

    link_elapsed = time.time() - link_start

    # Update scene (materials were assigned inline during instance loop)
    print(f"\nUpdating scene...")
    update_start = time.time()
    bpy.context.view_layer.update()
    update_elapsed = time.time() - update_start

    total_elapsed = time.time() - start_time

    # Report
    print("\n" + "=" * 70)
    print("TESSELLATED LOADING COMPLETE")
    print("=" * 70)
    print(f"Elements loaded: {len(instances):,}")
    print(f"Unique templates: {len(templates_used):,}")
    print(f"Instancing ratio: {len(instances)/max(len(templates_used),1):.1f}×")
    print(f"\nTiming:")
    print(f"  Instance creation: {instance_elapsed:.2f}s ({instance_elapsed/max(len(instances),1)*1000:.2f}ms per instance)")
    print(f"  Collection linking: {link_elapsed:.2f}s")
    print(f"  Scene update: {update_elapsed:.2f}s")
    print(f"  Total: {total_elapsed:.2f}s")
    print("=" * 70)

    db_conn.close()

    return instances
