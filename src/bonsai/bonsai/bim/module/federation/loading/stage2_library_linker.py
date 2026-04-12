"""
Stage 2: Library-Linked Geometry Loading
========================================

Links pre-baked meshes from library.blend by geometry_hash.
No BLOB reads, no from_pydata() — instant mesh availability.

Replaces stage2_tessellation_loader for extracted DBs that use
the meshless pipeline (transforms + hash pointers + R-tree).

Performance: <2s for 100K elements (link 0.03s + instance ~1.5s)
Memory: O(unique_meshes) mesh data, O(elements) transforms only

§PROOF LINK_TIME  — time to link all meshes from library.blend
§PROOF INSTANCE   — time to create all instances with transforms
§PROOF COVERAGE   — hashes found in library vs total hashes needed

Usage:
    Called by LinkFederationLibrary operator.
    Requires: library/library.blend (baked from component_library.db)
    Input DB: meshless extracted DB with element_transforms + element_instances
"""

import bpy
import os
import sqlite3
import time
import numpy as np
from datetime import datetime
from mathutils import Vector, Euler
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Discipline colors (same as stage2_gpu_instancing — inlined to avoid import chain)
DISCIPLINE_COLORS = {
    'ACMV': (0.2, 0.7, 1.0),
    'MEP': (0.2, 0.7, 1.0),       # same as ACMV — MEP is the merged discipline
    'FP': (1.0, 0.1, 0.1),
    'ELEC': (1.0, 0.9, 0.0),
    'SP': (0.3, 0.9, 0.4),
    'ARC': (0.85, 0.75, 0.55),
    'STR': (0.6, 0.65, 0.75),
    'REB': (0.9, 0.5, 0.2),
    'CW': (0.7, 0.5, 0.3),
    'LPG': (1.0, 0.6, 0.0),
}

# Log level: FINE = verbose per-element, INFO = summary only
_LOG_LEVEL = os.environ.get("BIM_LOG_LEVEL", "FINE")
FINE = _LOG_LEVEL == "FINE"


_log_file = None


def _init_log(db_path: str):
    """Open a persistent log file next to the DB (or in ~/Documents/bonsai/).
    Auto-purges old logs, keeping only the 5 most recent."""
    global _log_file
    log_dir = Path(db_path).parent
    if not log_dir.exists():
        log_dir = Path.home() / "Documents" / "bonsai" / "consolelogs"
        log_dir.mkdir(parents=True, exist_ok=True)
    # Purge old logs — keep last 5
    old_logs = sorted(log_dir.glob("library_link_*.log"))
    for stale in old_logs[:-4]:  # keep 4 + the new one = 5
        try:
            stale.unlink()
        except OSError:
            pass
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = log_dir / f"library_link_{stamp}.log"
    _log_file = open(log_path, "w", encoding="utf-8", buffering=1)  # line-buffered
    _log_file.write(f"# Library Link Log — {datetime.now().isoformat()}\n")
    _log_file.write(f"# DB: {db_path}\n")
    _log_file.write(f"# BIM_LOG_LEVEL={_LOG_LEVEL}\n\n")
    _log_file.flush()
    return log_path


def _close_log():
    """Flush and close the persistent log file."""
    global _log_file
    if _log_file:
        _log_file.flush()
        _log_file.close()
        _log_file = None


def _get_ram_mb() -> float:
    """RSS memory in MB (Linux). Returns -1 if unavailable."""
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except Exception:
        return -1.0


def _log(msg, level="INFO"):
    """Gated logging — FINE messages only print when BIM_LOG_LEVEL=FINE.
    Always writes to the persistent log file regardless of level."""
    if _log_file:
        _log_file.write(msg + "\n")
        _log_file.flush()  # flush every line — survives crash/freeze
    if level == "FINE" and not FINE:
        return
    print(msg)


def _find_library_blend(db_path: str) -> Optional[str]:
    """Locate library.blend relative to the extracted DB or in known paths."""
    db_dir = Path(db_path).parent
    candidates = [
        db_dir / "library.blend",
        db_dir.parent / "library" / "library.blend",
        db_dir.parent.parent / "library" / "library.blend",
    ]
    # Also check bim-compiler project root
    for parent in Path(db_path).parents:
        p = parent / "library" / "library.blend"
        if p not in candidates:
            candidates.append(p)

    for c in candidates:
        if c.exists():
            return str(c.resolve())
    return None


def _get_or_create_discipline_material(discipline: str) -> bpy.types.Material:
    """Get or create a solid-color material for a discipline."""
    mat_name = f"Disc_{discipline}"
    mat = bpy.data.materials.get(mat_name)
    if mat:
        return mat

    mat = bpy.data.materials.new(name=mat_name)
    color = DISCIPLINE_COLORS.get(discipline, (0.5, 0.5, 0.5))
    if len(color) == 3:
        color = (*color, 1.0)
    mat.diffuse_color = color  # SOLID mode reads this
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
    return mat


def _parse_rgba(rgba_str: str) -> Tuple[float, float, float, float]:
    """Parse 'r,g,b,a' string to tuple."""
    try:
        parts = rgba_str.split(',')
        return (float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3]))
    except Exception:
        return (0.5, 0.5, 0.5, 1.0)


_surface_styles = None  # lazy-loaded from DB


def _load_surface_styles(db_path: str):
    """Load surface_styles table into memory (once)."""
    global _surface_styles
    if _surface_styles is not None:
        return
    _surface_styles = {}
    try:
        db = sqlite3.connect(db_path)
        for r in db.execute(
                "SELECT style_name, surface_r, surface_g, surface_b, "
                "COALESCE(transparency, 0) FROM surface_styles"):
            alpha = max(0.0, 1.0 - (r[4] or 0.0))
            _surface_styles[r[0]] = f"{r[1]:.3f},{r[2]:.3f},{r[3]:.3f},{alpha:.3f}"
        db.close()
        _log(f"  §MAT surface_styles: {len(_surface_styles)} entries loaded", "FINE")
    except Exception as e:
        _log(f"  §MAT surface_styles load failed: {e}", "INFO")
        _surface_styles = {}


def _resolve_rgba(material_name: str, rgba_str: str) -> tuple:
    """Resolve material rgba: direct → surface_styles lookup → empty.

    Returns (rgba_str, path) where path is 'direct', 'surface_styles', or 'none'.
    """
    if rgba_str:
        return rgba_str, 'direct'
    if not material_name or _surface_styles is None:
        return "", 'none'
    # Exact match
    if material_name in _surface_styles:
        return _surface_styles[material_name], 'surface_styles'
    # Try substring after colon (Revit: 'Basic Wall:Material Name')
    for part in material_name.split(':'):
        part = part.strip()
        if part in _surface_styles:
            return _surface_styles[part], 'surface_styles'
    return "", 'none'


def _get_or_create_material_from_db(material_name: str, rgba_str: str,
                                     discipline: str) -> tuple:
    """Create material from DB rgba, surface_styles lookup, or discipline fallback.

    Returns (material, path) where path is 'direct', 'surface_styles', or 'discipline'.
    """
    rgba_str, resolve_path = _resolve_rgba(material_name, rgba_str)
    if not rgba_str:
        return _get_or_create_discipline_material(discipline), 'discipline'

    mat_key = f"DB_{material_name}_{rgba_str}"
    mat = bpy.data.materials.get(mat_key)
    if mat:
        return mat, resolve_path

    rgba = _parse_rgba(rgba_str)
    mat = bpy.data.materials.new(name=mat_key)
    mat.diffuse_color = rgba  # SOLID mode reads this, not BSDF node
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = rgba
        if rgba[3] < 0.99:
            mat.blend_method = 'BLEND' if hasattr(mat, 'blend_method') else None
            bsdf.inputs["Alpha"].default_value = rgba[3]
    return mat, resolve_path


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def load_library_linked(db_path: str,
                        library_blend_path: str,
                        parent_collection: bpy.types.Collection,
                        progress_callback=None) -> dict:
    """
    Load federation using library-linked meshes.

    Args:
        db_path: Path to meshless extracted DB
        library_blend_path: Path to library.blend (pre-baked)
        parent_collection: Blender collection to populate
        progress_callback: Optional fn(message) for UI updates

    Returns:
        dict with stats: elements, unique_meshes, link_time, instance_time, etc.
    """
    t_total = time.time()
    stats = {}

    log_path = _init_log(db_path)

    def report(msg):
        _log(msg)
        if progress_callback:
            progress_callback(msg)

    report(f"{'='*60}")
    report(f"LIBRARY LINK — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report(f"  db:      {db_path}")
    report(f"  library: {library_blend_path}")
    report(f"  log:     {log_path}")
    report(f"  level:   {_LOG_LEVEL}")
    report(f"{'='*60}")

    # ── STEP 1/6: Read transforms from DB ──
    report(f"\n[1/6] READ TRANSFORMS from extracted DB")
    t1 = time.time()
    db = sqlite3.connect(db_path)

    # Load surface_styles for material name → rgba resolution
    _load_surface_styles(db_path)

    # Check which metadata table exists
    tables = {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}

    has_elements_meta = "elements_meta" in tables

    if has_elements_meta:
        query = """
            SELECT m.guid, m.ifc_class, m.discipline,
                   m.material_name, m.material_rgba,
                   et.center_x, et.center_y, et.center_z,
                   et.rotation_x, et.rotation_y, et.rotation_z,
                   ei.geometry_hash,
                   m.element_name
            FROM elements_meta m
            JOIN element_transforms et ON m.guid = et.guid
            JOIN element_instances ei ON ei.guid = et.guid
        """
    else:
        # Fallback: no elements_meta, derive from I_Element_Extraction or bare tables
        query = """
            SELECT et.guid,
                   COALESCE(ie.ifc_class, 'Unknown') as ifc_class,
                   COALESCE(ie.discipline, 'UNK') as discipline,
                   ie.material_name,
                   ie.material_rgba,
                   et.center_x, et.center_y, et.center_z,
                   et.rotation_x, et.rotation_y, et.rotation_z,
                   ei.geometry_hash,
                   ie.element_name
            FROM element_transforms et
            JOIN element_instances ei ON ei.guid = et.guid
            LEFT JOIN I_Element_Extraction ie ON ie.guid = et.guid
        """

    elements = db.execute(query).fetchall()
    total = len(elements)

    # Collect unique hashes needed
    needed_hashes = set()
    for e in elements:
        needed_hashes.add(e[11])  # geometry_hash

    t1_elapsed = time.time() - t1
    report(f"  §DONE {total:,} elements, {len(needed_hashes):,} unique hashes ({t1_elapsed:.2f}s)")
    report(f"  table={('elements_meta' if has_elements_meta else 'element_transforms+I_Element_Extraction')}")

    # ── PRE-FLIGHT: check hash coverage against library.db ──
    # §FIX S175: Only run for small DBs. For 108K+ hashes, loading 120K rows
    # from component_library.db adds seconds of overhead before any mesh loads.
    lib_db_path = Path(library_blend_path).parent / "component_library.db"
    if lib_db_path.exists() and len(needed_hashes) < 30000:
        lib_db = sqlite3.connect(str(lib_db_path))
        lib_hashes = set(r[0] for r in lib_db.execute(
            "SELECT geometry_hash FROM component_geometries WHERE vertices IS NOT NULL"))
        lib_db.close()
        preflight_overlap = len(needed_hashes & lib_hashes)
        preflight_pct = preflight_overlap / max(len(needed_hashes), 1) * 100
        report(f"  §PREFLIGHT hash coverage: {preflight_overlap:,}/{len(needed_hashes):,} "
               f"({preflight_pct:.0f}%) against component_library.db")
    elif len(needed_hashes) >= 30000:
        report(f"  §PREFLIGHT skipped ({len(needed_hashes):,} hashes — too large, checked at load)")
        preflight_pct = 100  # trust the library

        if preflight_pct < 50:
            report(f"")
            report(f"  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            report(f"  !! FATAL: Only {preflight_pct:.0f}% hash coverage")
            report(f"  !! This DB was extracted with a DIFFERENT pipeline.")
            report(f"  !! The geometry hashes don't match the library.")
            report(f"  !!")
            report(f"  !! FIX: Re-extract with:")
            report(f"  !!   python3 scripts/extract_merge_disciplines.py \\")
            report(f"  !!     --ifc-dir <ifc_dir> --pattern '*.ifc' \\")
            report(f"  !!     --output {db_path} \\")
            report(f"  !!     --library library/component_library.db")
            report(f"  !!")
            report(f"  !! Then rebake library.blend:")
            report(f"  !!   blender --background --python scripts/bake_library_blend.py -- \\")
            report(f"  !!     --library library/component_library.db \\")
            report(f"  !!     --output library/library.blend")
            report(f"  !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            _close_log()
            raise RuntimeError(
                f"STALE DB: only {preflight_pct:.0f}% hash coverage "
                f"({preflight_overlap}/{len(needed_hashes)}). "
                f"Re-extract DB with: python3 scripts/extract_merge_disciplines.py "
                f"--library library/component_library.db. See log: {log_path}")
    else:
        report(f"  §PREFLIGHT component_library.db not found at {lib_db_path} — skipping pre-check")

    # ── STEP 2/6: Link meshes from library.blend ──
    # S176: link=True (cache refs only) — near-instant, no .blend re-parse.
    # NO make_local() here — per-element objects resolve linked mesh refs once
    # at obj.data assignment, not 60×/sec like GN. make_local() is only needed
    # for GN path (DLOD promotion). See StressTest_1M_Results.md §S176 Analysis.
    report(f"\n[2/6] CACHE MESHES from library.blend "
           f"({len(needed_hashes):,} needed, link=True)")
    t2 = time.time()
    lib_path = os.path.abspath(library_blend_path)

    # S175: if GN mode was loaded first, meshes may already exist.
    # Reuse existing meshes, only load what's missing.
    existing_meshes = {}
    still_needed = set()
    for h in needed_hashes:
        mesh = bpy.data.meshes.get(h)
        if mesh is not None:
            existing_meshes[h] = mesh
        else:
            still_needed.add(h)

    reused = len(existing_meshes)
    if reused > 0:
        _log(f"  §LINK reused {reused:,} meshes already in bpy.data "
             f"({len(still_needed):,} still to cache)", "FINE")

    # S176: link=True (cache refs, no copy). Per-element objects work fine with
    # linked meshes — GPU buffer cached after first render, handle overhead negligible.
    if still_needed:
        lib_size_mb = os.path.getsize(lib_path) / (1024 * 1024) if os.path.exists(lib_path) else -1
        ram_before = _get_ram_mb()
        _log(f"  §LINK opening library.blend ({lib_size_mb:.1f} MB) — "
             f"linking {len(still_needed):,} meshes, RAM={ram_before:.0f} MB", "INFO")

        t2_link = time.time()
        with bpy.data.libraries.load(lib_path, link=True) as (data_from, data_to):
            available = set(data_from.meshes)
            to_link = [name for name in data_from.meshes if name in still_needed]
            data_to.meshes = to_link
        t2_link_elapsed = time.time() - t2_link

        ram_after = _get_ram_mb()
        _log(f"  §LINK done: {len(to_link):,} refs created in {t2_link_elapsed:.3f}s "
             f"RAM {ram_before:.0f}→{ram_after:.0f} MB (delta={ram_after - ram_before:+.0f} MB)", "INFO")
    else:
        available = needed_hashes
        to_link = []
        t2_link_elapsed = 0.0
        class _empty:
            meshes = []
        data_to = _empty()

    t2_elapsed = time.time() - t2
    coverage = reused + len(to_link)
    orphans = len(needed_hashes) - coverage
    coverage_pct = coverage / max(len(needed_hashes), 1) * 100

    report(f"  §PROOF LINK_TIME {t2_link_elapsed:.3f}s link=True, {t2_elapsed:.3f}s total "
           f"for {coverage:,} meshes ({coverage/max(t2_link_elapsed, 0.001):.0f}/s) "
           f"reused={reused} linked={len(to_link)}")
    report(f"  §PROOF COVERAGE {coverage:,}/{len(needed_hashes):,} hashes "
           f"({coverage_pct:.0f}%) — {orphans} orphans")

    if orphans > 0:
        report(f"  WARNING: {orphans} geometry hashes not found in library.blend")
        missing = needed_hashes - available - set(existing_meshes.keys())
        for h in list(missing)[:5]:
            _log(f"    MISS {h}", "FINE")

    # Build hash → mesh lookup — this is the critical handoff point
    # Start with reused meshes, then add freshly loaded ones
    mesh_by_hash = dict(existing_meshes)
    link_null = 0
    link_no_verts = 0
    for mesh in data_to.meshes:
        if mesh is None:
            link_null += 1
            continue
        mesh_by_hash[mesh.name] = mesh
        if len(mesh.vertices) == 0:
            link_no_verts += 1

    # S176: No material slot fix needed — bake_library_blend.py line 73 adds
    # mesh.materials.append(None) for every mesh. Linked meshes are read-only
    # anyway (materials.append would fail). Material override via object-level
    # material_slots[0].link = 'OBJECT' at step 5 works on linked meshes.

    _log(f"  §LINK mesh_by_hash: {len(mesh_by_hash):,} entries "
         f"(null={link_null} empty_verts={link_no_verts})", "INFO")
    if link_null > 0:
        _log(f"  §LINK WARNING: {link_null} meshes came back as None from library", "INFO")
    if link_no_verts > 0:
        _log(f"  §LINK WARNING: {link_no_verts} meshes have 0 vertices — "
             f"library.blend may need rebake", "INFO")

    # Spot-check: confirm meshes are linked (not copied), sample verts/slots
    sample = [(h, m) for h, m in list(mesh_by_hash.items())[:3]]
    for h, m in sample:
        _log(f"  §LINK_SAMPLE hash={h[:16]} verts={len(m.vertices)} "
             f"mat_slots={len(m.materials)} linked={m.library is not None}", "FINE")

    # ── STEP 3/6: Create collections ──
    report(f"\n[3/6] CREATE COLLECTIONS")
    templates_col = bpy.data.collections.new("_Templates")
    parent_collection.children.link(templates_col)
    # Hide templates from viewport
    for vl in bpy.context.scene.view_layers:
        lc = _find_layer_collection(vl.layer_collection, templates_col.name)
        if lc:
            lc.exclude = True

    # Discipline collections
    disc_collections = {}

    # ── STEP 4/6: Create template objects (one per unique hash) ──
    report(f"\n[4/6] CREATE TEMPLATES (one per unique mesh)")
    t3 = time.time()
    template_objects = {}

    for ghash, mesh in mesh_by_hash.items():
        tpl_obj = bpy.data.objects.new(f"Tpl_{ghash[:12]}", mesh)
        templates_col.objects.link(tpl_obj)
        tpl_obj.hide_viewport = True
        tpl_obj.hide_render = True
        template_objects[ghash] = tpl_obj

    t3_elapsed = time.time() - t3
    _log(f"  §LINK {len(template_objects):,} templates created ({t3_elapsed:.2f}s)", "FINE")

    # ── STEP 5/6: Create instances with transforms ──
    report(f"\n[5/6] CREATE INSTANCES ({total:,} elements)")
    t4 = time.time()
    created = 0
    skipped = 0
    mat_direct_count = 0      # elements with direct IFC rgba
    mat_ss_count = 0          # elements resolved via surface_styles
    mat_disc_count = 0        # elements falling back to discipline color
    mat_fail_count = 0        # elements with no material slot

    for idx, elem in enumerate(elements):
        (guid, ifc_class, discipline, mat_name, mat_rgba,
         cx, cy, cz, rx, ry, rz, ghash) = elem[:12]
        element_name = elem[12] if len(elem) > 12 else None

        if ghash not in mesh_by_hash:
            skipped += 1
            continue

        # Object name: human-readable for Outliner + top-left display
        # e.g. "IfcWall | Ext Wall 200mm" or "IfcDoor | Door-Single"
        if element_name:
            obj_name = f"{ifc_class} | {element_name}"
        else:
            obj_name = f"{ifc_class} | {guid[:12]}"
        instance = bpy.data.objects.new(obj_name, mesh_by_hash[ghash])

        # Apply transform — centre + rotation
        instance.location = Vector((cx, cy, cz))
        if rx != 0 or ry != 0 or rz != 0:
            instance.rotation_euler = Euler((rx, ry, rz), 'XYZ')

        # Material — linked mesh has a pre-baked placeholder slot (from bake step)
        # Override at object level so each instance can have its own material
        material, mat_path = _get_or_create_material_from_db(
            mat_name or "", mat_rgba or "", discipline or "UNK")
        n_slots = len(instance.material_slots)
        if n_slots > 0:
            instance.material_slots[0].link = 'OBJECT'
            instance.material_slots[0].material = material
            if mat_path == 'direct':
                mat_direct_count += 1
            elif mat_path == 'surface_styles':
                mat_ss_count += 1
            else:
                mat_disc_count += 1
        else:
            # S174: no material slot — try active_material fallback
            try:
                instance.active_material = material
            except Exception:
                pass
            mat_fail_count += 1
            if mat_fail_count <= 5:
                _log(f"    §MAT_FAIL [{mat_fail_count}] {obj_name}: "
                     f"0 material_slots, mesh={instance.data.name[:16]} "
                     f"local={instance.data.library is None} "
                     f"mesh_mats={len(instance.data.materials)} "
                     f"wanted={mat_path}:{material.name[:20]}", "FINE")

        # Metadata
        instance['guid'] = guid
        instance['ifc_class'] = ifc_class
        instance['discipline'] = discipline or "UNK"
        instance['geometry_hash'] = ghash

        # Add to discipline collection
        disc = discipline or "UNK"
        if disc not in disc_collections:
            dc = bpy.data.collections.new(disc)
            parent_collection.children.link(dc)
            disc_collections[disc] = dc
        disc_collections[disc].objects.link(instance)

        created += 1

        # S176: batched scene update — 10K interval (was 2K, caused O(N^2) cost)
        if created % 10000 == 0:
            bpy.context.view_layer.update()
            elapsed = time.time() - t4
            rate = created / max(elapsed, 0.001)
            remaining = (total - created) / max(rate, 1)
            report(f"  §INSTANCE {created:,}/{total:,} "
                   f"({rate:.0f}/s, ~{remaining:.0f}s left)")

        if FINE and created <= 3:
            _log(f"    §SAMPLE[{created}] {ifc_class} "
                 f"pos=({cx:.2f},{cy:.2f},{cz:.2f}) "
                 f"rot=({rx:.4f},{ry:.4f},{rz:.4f}) "
                 f"hash={ghash[:12]} "
                 f"mat={mat_path}:{mat_name or discipline} "
                 f"rgba={mat_rgba or 'null'}", "FINE")

    # Final scene update
    bpy.context.view_layer.update()
    t4_elapsed = time.time() - t4

    # Material summary — 3-path breakdown (the log speaks)
    mat_total = mat_direct_count + mat_ss_count + mat_disc_count + mat_fail_count
    report(f"  §PROOF MATERIALS total={mat_total:,} "
           f"direct_rgba={mat_direct_count:,} "
           f"surface_styles={mat_ss_count:,} "
           f"discipline_fallback={mat_disc_count:,} "
           f"no_slot={mat_fail_count}")
    if mat_ss_count > 0:
        report(f"  §MAT surface_styles resolved {mat_ss_count:,} elements "
               f"({mat_ss_count/max(mat_total,1)*100:.0f}%)")
    if mat_disc_count > mat_total * 0.5:
        report(f"  §MAT WARNING: {mat_disc_count/max(mat_total,1)*100:.0f}% on discipline fallback — "
               f"IFC source has sparse material data")

    # §PROOF COLOR_VISIBLE — verify materials actually show in viewport
    # Check viewport shading, sample material, and Blender material count
    color_diag = []
    try:
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        shading = space.shading.type
                        color_type = getattr(space.shading, 'color_type', 'MATERIAL')
                        color_diag.append(f"shading={shading} color_type={color_type}")
                        if shading == 'SOLID' and color_type != 'MATERIAL':
                            report(f"  §MAT WARNING: Viewport is SOLID/{color_type} — "
                                   f"colors won't show. Switch to Material Preview (Z key) "
                                   f"or Solid→Color Type→Material")
                            # Auto-fix: set color_type to MATERIAL in solid mode
                            space.shading.color_type = 'MATERIAL'
                            report(f"  §MAT FIX: auto-set Solid color_type=MATERIAL")
    except Exception as e:
        color_diag.append(f"diag_error={e}")

    # Sample first 3 created materials to prove they have color data
    mat_samples = []
    for mat in list(bpy.data.materials)[:5]:
        if mat.use_nodes and mat.node_tree:
            bsdf = mat.node_tree.nodes.get("Principled BSDF")
            if bsdf:
                rgba = tuple(bsdf.inputs["Base Color"].default_value)
                mat_samples.append(f"{mat.name[:30]}=({rgba[0]:.2f},{rgba[1]:.2f},{rgba[2]:.2f},{rgba[3]:.2f})")
    report(f"  §PROOF COLOR_VISIBLE viewport=[{'; '.join(color_diag)}] "
           f"blender_materials={len(bpy.data.materials)} "
           f"samples=[{'; '.join(mat_samples[:3])}]")
    if mat_fail_count > 0:
        report(f"  WARNING: {mat_fail_count} elements have no material slot — "
               f"rebake library.blend with placeholder slots")

    # ── STEP 6/6: BBOX_RECONSTRUCT proof (FINE mode) ──
    report(f"\n[6/6] BBOX PROOF — verify meshes fit R-tree bboxes")
    # Verify placed objects fit their R-tree bboxes — same math as standalone test
    t5 = time.time()
    bbox_ok = bbox_fail = 0
    bbox_worst = 0.0
    bbox_worst_guid = ""

    if FINE:
        db_proof = sqlite3.connect(db_path)
        # Sample up to 50 elements that have R-tree entries
        proof_rows = db_proof.execute("""
            SELECT et.guid,
                   et.center_x, et.center_y, et.center_z,
                   et.rotation_x, et.rotation_y, et.rotation_z,
                   ei.geometry_hash,
                   rt.minX, rt.maxX, rt.minY, rt.maxY, rt.minZ, rt.maxZ
            FROM element_transforms et
            JOIN element_instances ei ON ei.guid = et.guid
            JOIN elements_rtree rt ON rt.id = et.rowid
            LIMIT 50
        """).fetchall()

        import math
        def _euler_to_R(a, b, c):
            return np.array([
                [math.cos(b)*math.cos(c),
                 math.sin(a)*math.sin(b)*math.cos(c)-math.cos(a)*math.sin(c),
                 math.cos(a)*math.sin(b)*math.cos(c)+math.sin(a)*math.sin(c)],
                [math.cos(b)*math.sin(c),
                 math.sin(a)*math.sin(b)*math.sin(c)+math.cos(a)*math.cos(c),
                 math.cos(a)*math.sin(b)*math.sin(c)-math.sin(a)*math.cos(c)],
                [-math.sin(b), math.sin(a)*math.cos(b), math.cos(a)*math.cos(b)]
            ])

        for row in proof_rows:
            guid = row[0]
            cx, cy, cz = row[1], row[2], row[3]
            rx, ry, rz = row[4], row[5], row[6]
            ghash = row[7]
            rt_min = np.array([row[8], row[10], row[12]])
            rt_max = np.array([row[9], row[11], row[13]])

            if ghash not in mesh_by_hash:
                continue

            # Get local bbox from linked mesh
            mesh = mesh_by_hash[ghash]
            if len(mesh.vertices) == 0:
                continue
            local_verts = np.array([v.co[:] for v in mesh.vertices], dtype=np.float64)
            local_min = local_verts.min(axis=0)
            local_max = local_verts.max(axis=0)

            # Reconstruct world bbox: R × 8 corners + centre
            R = _euler_to_R(rx, ry, rz)
            centre = np.array([cx, cy, cz])
            corners = np.array([
                [local_min[0], local_min[1], local_min[2]],
                [local_max[0], local_min[1], local_min[2]],
                [local_min[0], local_max[1], local_min[2]],
                [local_max[0], local_max[1], local_min[2]],
                [local_min[0], local_min[1], local_max[2]],
                [local_max[0], local_min[1], local_max[2]],
                [local_min[0], local_max[1], local_max[2]],
                [local_max[0], local_max[1], local_max[2]],
            ])
            world_corners = (R @ corners.T).T + centre
            recon_min = world_corners.min(axis=0)
            recon_max = world_corners.max(axis=0)

            err = max(np.abs(recon_min - rt_min).max(),
                      np.abs(recon_max - rt_max).max())

            if err > bbox_worst:
                bbox_worst = err
                bbox_worst_guid = guid

            if err > 0.05:
                bbox_fail += 1
                if bbox_fail <= 3:
                    _log(f"  FAIL BBOX_RECONSTRUCT {guid[:16]} err={err:.4f}m", "FINE")
                    _log(f"    rtree =([{rt_min[0]:.2f},{rt_max[0]:.2f}],"
                         f"[{rt_min[1]:.2f},{rt_max[1]:.2f}],"
                         f"[{rt_min[2]:.2f},{rt_max[2]:.2f}])", "FINE")
                    _log(f"    recon =([{recon_min[0]:.2f},{recon_max[0]:.2f}],"
                         f"[{recon_min[1]:.2f},{recon_max[1]:.2f}],"
                         f"[{recon_min[2]:.2f},{recon_max[2]:.2f}])", "FINE")
            else:
                bbox_ok += 1

        db_proof.close()

    t5_elapsed = time.time() - t5
    if FINE:
        bbox_tag = "PASS" if bbox_fail == 0 and bbox_ok > 0 else "FAIL"
        report(f"§PROOF BBOX_RECONSTRUCT {bbox_tag}  {bbox_ok} ok, {bbox_fail} fail  "
               f"worst={bbox_worst:.4f}m ({bbox_worst_guid[:16]}) ({t5_elapsed:.2f}s)")

    t_total_elapsed = time.time() - t_total
    db.close()

    # ── Summary ──
    report(f"\n{'='*60}")
    report(f"§PROOF INSTANCE {created:,} created, {skipped} skipped "
           f"({t4_elapsed:.2f}s, {created/max(t4_elapsed,0.001):.0f}/s)")

    disc_summary = ", ".join(f"{d}:{len(c.objects)}"
                              for d, c in sorted(disc_collections.items()))
    report(f"§LINK DISCIPLINES {disc_summary}")

    report(f"§PROOF LOAD_TIME {t_total_elapsed:.2f}s total "
           f"(read={t1_elapsed:.2f}s link={t2_elapsed:.2f}s "
           f"instance={t4_elapsed:.2f}s)")

    tag = "PASS" if skipped == 0 and created > 0 else "WARN"
    report(f"§PROOF LIBRARY_LOAD {tag}  "
           f"{created:,} elements, {len(mesh_by_hash):,} unique meshes")

    report(f"§LINK LOG saved to {log_path}")
    _close_log()

    stats = {
        "elements": created,
        "skipped": skipped,
        "unique_meshes": len(mesh_by_hash),
        "link_time": t2_elapsed,
        "instance_time": t4_elapsed,
        "total_time": t_total_elapsed,
        "log_path": str(log_path),
        "disciplines": dict(sorted(
            {d: len(c.objects) for d, c in disc_collections.items()}.items())),
    }
    return stats


def _find_layer_collection(layer_collection, name):
    """Recursively find a LayerCollection by collection name."""
    if layer_collection.collection.name == name:
        return layer_collection
    for child in layer_collection.children:
        result = _find_layer_collection(child, name)
        if result:
            return result
    return None


# ============================================================================
# S175: GN + NEAR — Cache load, progressive make_local()
# ============================================================================
# Implementing S175_gn_mode_toggle.md
# Witness: W-GN-NEAR — 1M elements in ~3 seconds

def _build_gn_node_tree(name, template_coll):
    """GN tree: Points → Instance on Points (Pick Instance from collection).
    Each point's 'instance_index' attribute selects which template mesh.
    Same pattern as blend_cache.py:_build_instance_node_tree().
    """
    tree = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    tree.interface.new_socket(name='Geometry', in_out='INPUT',
                              socket_type='NodeSocketGeometry')
    tree.interface.new_socket(name='Geometry', in_out='OUTPUT',
                              socket_type='NodeSocketGeometry')

    inp = tree.nodes.new('NodeGroupInput')
    out = tree.nodes.new('NodeGroupOutput')

    col_info = tree.nodes.new('GeometryNodeCollectionInfo')
    col_info.inputs['Collection'].default_value = template_coll
    col_info.inputs['Separate Children'].default_value = True
    col_info.inputs['Reset Children'].default_value = True

    iop = tree.nodes.new('GeometryNodeInstanceOnPoints')
    iop.inputs['Pick Instance'].default_value = True

    named_attr = tree.nodes.new('GeometryNodeInputNamedAttribute')
    named_attr.data_type = 'INT'
    named_attr.inputs['Name'].default_value = 'instance_index'

    rot_attr = tree.nodes.new('GeometryNodeInputNamedAttribute')
    rot_attr.data_type = 'FLOAT_VECTOR'
    rot_attr.inputs['Name'].default_value = 'rotation'

    euler_to_rot = tree.nodes.new('FunctionNodeEulerToRotation')

    tree.links.new(inp.outputs[0], iop.inputs['Points'])
    tree.links.new(col_info.outputs['Instances'], iop.inputs['Instance'])
    tree.links.new(named_attr.outputs[0], iop.inputs['Instance Index'])
    tree.links.new(rot_attr.outputs[0], euler_to_rot.inputs[0])
    tree.links.new(euler_to_rot.outputs[0], iop.inputs['Rotation'])

    tree.links.new(iop.outputs['Instances'], out.inputs[0])
    tree.links.new(iop.outputs['Instances'], out.inputs[0])

    return tree


def load_library_gn(db_path: str,
                    library_blend_path: str,
                    parent_collection: bpy.types.Collection,
                    progress_callback=None) -> dict:
    """
    S176 — GN + Chunked Sub-Collections: Load federation as GN point clouds.
    // Implementing S176_fast_load_gn_streaming.md §Task 2
    // Witness: W-GN-CHUNK — viewport smooth at 7K+ templates

    Sequence:
      1. link=True → cache all meshes from library.blend
      2. Partition hashes into CHUNK_SIZE=100 sub-collections
      3. Create per-(discipline, chunk) GN point clouds (modifiers disabled)
      4. Set FINAL chunk-local instance_index
      5. Enable GN modifiers → each Collection Info walks ≤101 objects (fast)
      6. Register chunk-aware streamer (make_local + obj.data swap)

    Key fix: GN Collection Info walks ALL children per eval. At 7K+ objects,
    each eval hangs the viewport. Chunked sub-collections cap this at 100.

    Returns dict with stats.
    """
    from math import ceil

    CHUNK_SIZE = 100  # max templates per sub-collection (excl. bbox proxy)

    t_total = time.time()
    log_path = _init_log(db_path)

    def report(msg):
        _log(msg)
        if progress_callback:
            progress_callback(msg)

    report(f"{'='*60}")
    report(f"GN+CHUNK LOAD — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report(f"  db:      {db_path}")
    report(f"  library: {library_blend_path}")
    report(f"  log:     {log_path}")
    report(f"  CHUNK_SIZE: {CHUNK_SIZE}")
    report(f"{'='*60}")

    # ── STEP 1/7: Read transforms from DB ──
    report(f"\n[1/7] READ TRANSFORMS")
    t1 = time.time()
    db = sqlite3.connect(db_path)
    _load_surface_styles(db_path)

    tables = {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}

    if "elements_meta" in tables:
        query = """
            SELECT m.guid, m.ifc_class, m.discipline,
                   m.material_name, m.material_rgba,
                   et.center_x, et.center_y, et.center_z,
                   et.rotation_x, et.rotation_y, et.rotation_z,
                   ei.geometry_hash, m.element_name
            FROM elements_meta m
            JOIN element_transforms et ON m.guid = et.guid
            JOIN element_instances ei ON ei.guid = et.guid
        """
    else:
        query = """
            SELECT et.guid, COALESCE(ie.ifc_class, 'Unknown'),
                   COALESCE(ie.discipline, 'UNK'),
                   ie.material_name, ie.material_rgba,
                   et.center_x, et.center_y, et.center_z,
                   et.rotation_x, et.rotation_y, et.rotation_z,
                   ei.geometry_hash, ie.element_name
            FROM element_transforms et
            JOIN element_instances ei ON ei.guid = et.guid
            LEFT JOIN I_Element_Extraction ie ON ie.guid = et.guid
        """

    elements = db.execute(query).fetchall()
    total = len(elements)
    needed_hashes = set(e[11] for e in elements)
    t1_elapsed = time.time() - t1
    report(f"  {total:,} elements, {len(needed_hashes):,} unique hashes ({t1_elapsed:.2f}s)")

    # ── STEP 2/7: CACHE — link=True from library.blend ──
    report(f"\n[2/7] CACHE LOAD (link=True)")
    t2 = time.time()
    lib_path = os.path.abspath(library_blend_path)

    with bpy.data.libraries.load(lib_path, link=True) as (data_from, data_to):
        to_link = [n for n in data_from.meshes if n in needed_hashes]
        data_to.meshes = to_link

    t2_elapsed = time.time() - t2
    coverage = len(to_link)
    report(f"  §PROOF CACHE_TIME {t2_elapsed:.3f}s for {coverage:,} meshes "
           f"({coverage/max(t2_elapsed, 0.001):.0f}/s) link=True")
    report(f"  §PROOF CACHE_COVERAGE {coverage:,}/{len(needed_hashes):,} "
           f"({coverage*100//max(len(needed_hashes),1)}%)")

    # Build hash → mesh lookup
    mesh_by_hash = {}
    hash_to_index = {}  # cache index (for DLOD compat)
    idx = 0
    for mesh in data_to.meshes:
        if mesh is None:
            continue
        mesh_by_hash[mesh.name] = mesh
        hash_to_index[mesh.name] = idx
        idx += 1
    report(f"  {len(mesh_by_hash):,} meshes in cache (linked, read-only)")

    # ── STEP 3/7: Build chunked sub-collections ──
    # S176: Split templates into sub-collections of CHUNK_SIZE.
    # Each chunk has ≤ CHUNK_SIZE templates + 1 bbox proxy.
    # GN Collection Info walks ≤ CHUNK_SIZE+1 objects per eval (fast).
    report(f"\n[3/7] BUILD CHUNKED COLLECTIONS (CHUNK_SIZE={CHUNK_SIZE})")
    t3 = time.time()

    sorted_hashes = sorted(mesh_by_hash.keys())
    n_chunks = ceil(len(sorted_hashes) / CHUNK_SIZE)

    # Shared bbox mesh (one mesh, reused across all chunks)
    bbox_mesh = bpy.data.meshes.new("_bbox_shared")
    bbox_mesh.from_pydata(
        [(-0.5,-0.5,-0.5),(0.5,-0.5,-0.5),(0.5,0.5,-0.5),(-0.5,0.5,-0.5),
         (-0.5,-0.5,0.5),(0.5,-0.5,0.5),(0.5,0.5,0.5),(-0.5,0.5,0.5)],
        [],
        [(0,1,2,3),(4,5,6,7),(0,1,5,4),(2,3,7,6),(0,3,7,4),(1,2,6,5)])
    bbox_mesh.update()
    bbox_mesh['is_bbox_proxy'] = True
    arc_mat = _get_or_create_discipline_material('ARC')
    bbox_mesh.materials.append(arc_mat)

    # Parent collection (not used by GN directly)
    templates_col = bpy.data.collections.new("_LibGN_Templates")
    parent_collection.children.link(templates_col)

    # Build chunks
    chunks = []          # list of (chunk_id, chunk_col, [hashes])
    hash_to_chunk = {}   # ghash → chunk_id
    hash_to_local = {}   # ghash → local index within chunk (0=bbox, 1..N=templates)
    tpl_objects = {}      # ghash → Blender object (for mesh swap)

    for chunk_id in range(n_chunks):
        start = chunk_id * CHUNK_SIZE
        end = min(start + CHUNK_SIZE, len(sorted_hashes))
        chunk_hashes = sorted_hashes[start:end]

        chunk_col = bpy.data.collections.new(f"_LibGN_Chunk_{chunk_id:03d}")
        templates_col.children.link(chunk_col)

        # !bbox at slot 0 per chunk
        # ! (ASCII 33) sorts before T (ASCII 84) — guaranteed slot 0
        bbox_obj = bpy.data.objects.new(f"!bbox_{chunk_id:03d}", bbox_mesh)
        chunk_col.objects.link(bbox_obj)

        # Template objects (all start with bbox mesh)
        for gh in chunk_hashes:
            tpl_obj = bpy.data.objects.new(f"Tpl_{gh[:12]}", bbox_mesh)
            tpl_obj['geometry_hash'] = gh
            chunk_col.objects.link(tpl_obj)
            tpl_objects[gh] = tpl_obj

        # Compute local indices from alphabetical order (same as GN uses)
        all_names = sorted([o.name for o in chunk_col.objects])
        name_to_idx = {name: i for i, name in enumerate(all_names)}

        for gh in chunk_hashes:
            hash_to_chunk[gh] = chunk_id
            hash_to_local[gh] = name_to_idx[tpl_objects[gh].name]

        chunks.append((chunk_id, chunk_col, chunk_hashes))

    # Hide all template sub-collections from viewport
    for vl in bpy.context.scene.view_layers:
        lc = _find_layer_collection(vl.layer_collection, templates_col.name)
        if lc:
            lc.exclude = True

    t3_elapsed = time.time() - t3
    total_tpl = sum(len(ch[2]) for ch in chunks)
    report(f"  {n_chunks} chunks, {total_tpl:,} templates, "
           f"{total_tpl + n_chunks} total objects (incl. bbox)")
    report(f"  max objects per chunk: {CHUNK_SIZE + 1} "
           f"(Collection Info walks ≤{CHUNK_SIZE + 1})")
    report(f"  ({t3_elapsed:.2f}s)")

    # ── STEP 4/7: Group elements by (discipline, chunk) ──
    # Each (disc, chunk) pair gets its own point mesh + GN modifier.
    report(f"\n[4/7] BUILD PER-(DISC,CHUNK) GN OBJECTS")
    t4 = time.time()

    # Group elements
    disc_chunk_elements = {}  # (disc, chunk_id) → [(pos, rot, local_idx), ...]
    skipped = 0
    disc_positions = {}  # for DLOD compat
    disc_indices = {}    # for DLOD compat

    for elem in elements:
        (guid, ifc_class, discipline, mat_name, mat_rgba,
         cx, cy, cz, rx, ry, rz, ghash) = elem[:12]
        if ghash not in hash_to_chunk:
            skipped += 1
            continue
        disc = discipline or "UNK"
        chunk_id = hash_to_chunk[ghash]
        local_idx = hash_to_local[ghash]
        pos = (cx or 0.0, cy or 0.0, cz or 0.0)
        rot = (float(rx or 0.0), float(ry or 0.0), float(rz or 0.0))

        disc_chunk_elements.setdefault((disc, chunk_id), []).append(
            (pos, rot, local_idx))

        # DLOD compat: flat disc arrays
        disc_positions.setdefault(disc, []).append(pos)
        cache_idx = hash_to_index.get(ghash, 0)
        disc_indices.setdefault(disc, []).append(cache_idx)

    # Build one GN node tree per chunk (each references its own sub-collection)
    chunk_gn_trees = {}
    for chunk_id, chunk_col, _ in chunks:
        tree = _build_gn_node_tree(f"GN_Chunk_{chunk_id:03d}", chunk_col)
        chunk_gn_trees[chunk_id] = tree

    # Create per-(disc, chunk) GN objects
    gn_objects = []       # all GN objects (for summary)
    gn_obj_by_dc = {}     # (disc, chunk_id) → Blender object name
    disc_collections = {}
    total_instances = 0

    for (disc, chunk_id), elem_list in sorted(disc_chunk_elements.items()):
        n = len(elem_list)
        if n == 0:
            continue

        # Build point mesh with chunk-local instance_index
        point_mesh = bpy.data.meshes.new(f"Points_{disc}_{chunk_id:03d}")
        point_mesh.vertices.add(n)

        coords = np.array([e[0] for e in elem_list], dtype=np.float32).ravel()
        point_mesh.vertices.foreach_set("co", coords)

        # instance_index: chunk-LOCAL (0..CHUNK_SIZE range)
        local_indices = np.array([e[2] for e in elem_list], dtype=np.int32)
        attr = point_mesh.attributes.new("instance_index", 'INT', 'POINT')
        attr.data.foreach_set("value", local_indices)

        # rotation
        rot_data = np.array([e[1] for e in elem_list], dtype=np.float32).ravel()
        rot_attr = point_mesh.attributes.new("rotation", 'FLOAT_VECTOR', 'POINT')
        rot_attr.data.foreach_set("vector", rot_data)
        point_mesh.update()

        # Discipline material
        disc_mat = _get_or_create_discipline_material(disc)
        point_mesh.materials.append(disc_mat)

        obj = bpy.data.objects.new(f"Fed_{disc}_{chunk_id:03d}", point_mesh)
        mod = obj.modifiers.new("GeometryNodes", 'NODES')
        mod.node_group = chunk_gn_trees[chunk_id]
        # §KEY: GN modifier DISABLED during setup
        mod.show_viewport = False

        # Discipline collection
        if disc not in disc_collections:
            dc = bpy.data.collections.new(disc)
            parent_collection.children.link(dc)
            disc_collections[disc] = dc
        disc_collections[disc].objects.link(obj)

        gn_objects.append(obj)
        gn_obj_by_dc[(disc, chunk_id)] = obj.name
        total_instances += n

    t4_elapsed = time.time() - t4
    n_gn_objects = len(gn_objects)
    n_disc_chunk_pairs = len(disc_chunk_elements)
    report(f"  {total_instances:,} elements → {n_gn_objects} GN objects "
           f"({n_disc_chunk_pairs} non-empty disc×chunk pairs)")
    report(f"  disciplines: {', '.join(sorted(disc_collections.keys()))}")
    report(f"  ({t4_elapsed:.2f}s)")

    # ── STEP 5/7: Enable GN modifiers → instant bbox viewport ──
    # All points have correct chunk-local indices. Templates show bbox mesh.
    # Each GN eval walks ≤101 objects (fast) — no viewport hang.
    report(f"\n[5/7] ENABLE GN MODIFIERS (all bbox, chunk-local indices)")
    t5 = time.time()

    for obj in gn_objects:
        for mod in obj.modifiers:
            if mod.type == 'NODES':
                mod.show_viewport = True

    bpy.context.view_layer.update()
    t5_elapsed = time.time() - t5
    report(f"  GN enabled ({t5_elapsed:.3f}s) — viewport live, all bbox, "
           f"Collection Info walks ≤{CHUNK_SIZE + 1}")

    # Store metadata
    parent_collection['gn_mode'] = True
    parent_collection['gn_chunked'] = True
    parent_collection['chunk_size'] = CHUNK_SIZE
    parent_collection['database_path'] = db_path
    parent_collection['library_blend_path'] = library_blend_path

    # ── STEP 6/7: Build priority queue for streaming ──
    report(f"\n[6/7] BUILD STREAM QUEUE")
    t6 = time.time()

    # Get camera position for priority sorting
    cam_pos = np.array([0.0, 0.0, 0.0], dtype=np.float64)
    try:
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                rv3d = area.spaces[0].region_3d
                pos = rv3d.view_matrix.inverted().translation
                cam_pos = np.array([pos.x, pos.y, pos.z], dtype=np.float64)
                break
    except Exception:
        pass

    # Build priority queue sorted by distance to camera
    hash_positions = {}
    for elem in elements:
        ghash = elem[11]
        if ghash in hash_to_chunk:
            cx, cy, cz = elem[5] or 0, elem[6] or 0, elem[7] or 0
            hash_positions.setdefault(ghash, []).append((cx, cy, cz))

    stream_queue = []
    for ghash, positions in hash_positions.items():
        centroid = np.array(positions, dtype=np.float64).mean(axis=0)
        delta = centroid - cam_pos
        dist_sq = float(np.dot(delta, delta))
        stream_queue.append((dist_sq, ghash))
    stream_queue.sort()  # closest first

    t6_elapsed = time.time() - t6
    report(f"  {len(stream_queue):,} hashes queued, camera at "
           f"({cam_pos[0]:.1f}, {cam_pos[1]:.1f}, {cam_pos[2]:.1f})")

    # ── STEP 7/7: Register chunk-aware mesh streamer ──
    # S176: Streamer disables only affected chunk's GN modifiers during swap.
    # Each chunk re-eval walks ≤101 objects — no viewport hang.
    STREAM_BATCH = 200   # meshes per tick
    STREAM_INTERVAL = 0.5  # seconds between ticks

    _stream_state = {
        'queue': stream_queue,
        'queue_idx': 0,
        'mesh_by_hash': mesh_by_hash,
        'tpl_objects': {gh: obj.name for gh, obj in tpl_objects.items()},
        'hash_to_chunk': hash_to_chunk,
        'gn_obj_by_dc': gn_obj_by_dc,
        'disc_collections': {d: c.name for d, c in disc_collections.items()},
        'total_swapped': 0,
        'batch_size': STREAM_BATCH,
    }

    def _stream_tick():
        """Timer callback: chunk-aware make_local + mesh swap.
        S176: Disables only affected chunks' GN modifiers → small re-eval."""
        import bpy as _bpy
        st = _stream_state
        qi = st['queue_idx']
        queue = st['queue']

        if qi >= len(queue):
            elapsed_total = time.time() - st.get('t_start', time.time())
            print(f"[S176][STREAM] §DONE {st['total_swapped']:,}/{len(queue):,} meshes "
                  f"streamed in {elapsed_total:.1f}s "
                  f"(skipped={st.get('skip_no_mesh',0)} no_mesh, "
                  f"{st.get('skip_no_chunk',0)} no_chunk, "
                  f"{st.get('skip_no_tpl',0)} no_tpl)")
            return None  # unregister timer

        if 't_start' not in st:
            st['t_start'] = time.time()
            st['skip_no_mesh'] = 0
            st['skip_no_chunk'] = 0
            st['skip_no_tpl'] = 0
            st['made_local'] = 0

        t_tick = time.time()
        batch_end = min(qi + st['batch_size'], len(queue))

        # Group batch items by chunk_id
        chunk_batch = {}  # chunk_id → [(ghash, mesh)]
        for i in range(qi, batch_end):
            dist_sq, ghash = queue[i]
            mesh = _bpy.data.meshes.get(ghash)
            if mesh is None:
                st['skip_no_mesh'] += 1
                continue
            cid = st['hash_to_chunk'].get(ghash)
            if cid is None:
                st['skip_no_chunk'] += 1
                continue
            chunk_batch.setdefault(cid, []).append((ghash, mesh))

        # Process each chunk: pause → swap → resume
        swapped = 0
        for cid, items in chunk_batch.items():
            # Find GN modifiers for this chunk (across all disciplines)
            chunk_mods = []
            for (disc, chunk_id), obj_name in st['gn_obj_by_dc'].items():
                if chunk_id != cid:
                    continue
                obj = _bpy.data.objects.get(obj_name)
                if obj:
                    for mod in obj.modifiers:
                        if mod.type == 'NODES' and mod.show_viewport:
                            mod.show_viewport = False
                            chunk_mods.append(mod)

            # Swap meshes in this chunk
            for ghash, mesh in items:
                if mesh.library:
                    mesh.make_local()
                    st['made_local'] += 1
                obj_name = st['tpl_objects'].get(ghash)
                if obj_name:
                    tpl_obj = _bpy.data.objects.get(obj_name)
                    if tpl_obj and tpl_obj.data != mesh:
                        tpl_obj.data = mesh
                        swapped += 1
                else:
                    st['skip_no_tpl'] += 1

            # Resume only this chunk's GN modifiers
            for mod in chunk_mods:
                mod.show_viewport = True

        st['queue_idx'] = batch_end
        st['total_swapped'] += swapped

        elapsed = (time.time() - t_tick) * 1000
        pct = batch_end * 100 // len(queue)
        prev_pct = (qi * 100 // len(queue)) // 10
        curr_pct = pct // 10
        if curr_pct > prev_pct or batch_end >= len(queue):
            n_chunks_touched = len(chunk_batch)
            elapsed_total = time.time() - st['t_start']
            print(f"[S176][STREAM] {pct:3d}% — {st['total_swapped']:,} meshes, "
                  f"{n_chunks_touched} chunks, {elapsed:.0f}ms/tick, "
                  f"{elapsed_total:.1f}s total, "
                  f"local={st['made_local']}")

        return STREAM_INTERVAL

    bpy.app.timers.register(_stream_tick, first_interval=0.5)
    report(f"\n[7/7] STREAMER registered: {len(stream_queue):,} hashes, "
           f"batch={STREAM_BATCH}, interval={STREAM_INTERVAL}s")
    report(f"  §NOTE chunk-aware: each re-eval walks ≤{CHUNK_SIZE + 1} objects")

    # ── STEP 8/8: Wire DLOD handler (distance LOD after streaming) ──
    report(f"\n[8/8] WIRE DLOD (camera-distance LOD)")
    t8 = time.time()
    try:
        from ..dlod_handler import dlod_init_chunked, register_handler
        dlod_init_chunked(
            disc_chunk_elements=disc_chunk_elements,
            hash_to_chunk=hash_to_chunk,
            hash_to_local=hash_to_local,
            hash_to_index=hash_to_index,
            db_path=db_path,
        )
        register_handler()
        t8_elapsed = time.time() - t8
        report(f"  §DLOD WIRED — chunked mode, {len(disc_chunk_elements)} disc×chunk pairs")
        report(f"  halt_delay=200ms, near={10}m, far={100}m")
        report(f"  ({t8_elapsed:.3f}s)")
    except Exception as e:
        report(f"  §DLOD SKIP — {e}")
        _log(f"  DLOD wiring failed (non-fatal, streaming still works): {e}", "INFO")

    t_total_elapsed = time.time() - t_total
    db.close()

    # ── Summary ──
    report(f"\n{'='*60}")
    report(f"§PROOF GN_CHUNK_LOAD")
    report(f"  elements:    {total_instances:,}")
    report(f"  skipped:     {skipped}")
    report(f"  GN objects:  {n_gn_objects} ({n_disc_chunk_pairs} disc×chunk pairs)")
    report(f"  unique mesh: {len(mesh_by_hash):,}")
    report(f"  chunks:      {n_chunks} (CHUNK_SIZE={CHUNK_SIZE})")
    report(f"  collection:  {total_tpl + n_chunks} objects "
           f"(max {CHUNK_SIZE + 1} per chunk)")
    report(f"  disciplines: {', '.join(sorted(disc_collections.keys()))}")
    report(f"  cache time:  {t2_elapsed:.3f}s")
    report(f"  chunk build: {t3_elapsed:.2f}s")
    report(f"  GN build:    {t4_elapsed:.2f}s")
    report(f"  GN enable:   {t5_elapsed:.3f}s")
    report(f"  stream queue:{t6_elapsed:.3f}s")
    report(f"  TOTAL:       {t_total_elapsed:.2f}s (viewport live)")
    report(f"  rate:        {total_instances/max(t_total_elapsed,0.001):.0f} elements/s")
    report(f"  streaming:   {len(stream_queue)} hashes × {STREAM_BATCH}/tick")
    report(f"  DLOD:        {'WIRED' if 'register_handler' in dir() else 'SKIPPED'}")
    for disc in sorted(disc_collections.keys()):
        dc_count = sum(1 for (d, c) in disc_chunk_elements if d == disc)
        elem_count = sum(len(v) for (d, c), v in disc_chunk_elements.items() if d == disc)
        report(f"    §DISC {disc:8s} {elem_count:>9,} elements in {dc_count:>3} chunks")
    report(f"{'='*60}")
    report(f"§GN LOG saved to {log_path}")
    _close_log()

    return {
        "elements": total_instances,
        "skipped": skipped,
        "unique_meshes": len(mesh_by_hash),
        "gn_objects": n_gn_objects,
        "n_chunks": n_chunks,
        "chunk_size": CHUNK_SIZE,
        "stream_queue": len(stream_queue),
        "cache_time": t2_elapsed,
        "total_time": t_total_elapsed,
        "log_path": str(log_path),
        "disc_positions": disc_positions,
        "disc_indices": disc_indices,
        "hash_to_index": hash_to_index,
        "hash_to_chunk": hash_to_chunk,
        "hash_to_local": hash_to_local,
    }
