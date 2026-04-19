# Bonsai - OpenBIM Blender Add-on
# Copyright (C) 2025 Your Engineering Firm
#
# S196: Shared mesh, material, and transform utilities.
# Used by FedRTreeLoadMesh, FedRTreeOvernight, and DirectStream.

import bpy
from mathutils import Matrix, Euler

# S201: centering offsets for meshes that were re-centered at load time.
# Key = geometry_hash, value = (dx, dy, dz) offset that was subtracted from verts.
# apply_transform() adds this back to the object's translation so visual position
# is unchanged but the selection bounding box is tight around the object origin.
_mesh_center_offsets = {}

_RECENTER_THRESH = 5.0  # metres — re-center meshes whose local center is > 5m from origin


def ensure_meshes(hashes, lib_db_path, lib_blend_path=None):
    """Load meshes by geometry_hash — BLOB tessellation with library.blend fallback.

    Returns dict: geometry_hash → bpy.types.Mesh (only newly created meshes).
    Already-cached meshes are skipped (caller can look them up via bpy.data.meshes.get).

    S201: After creation, re-centers meshes whose local bbox center is far from
    origin (> 5m). This prevents 100m+ selection bounding boxes in Blender caused
    by non-centered verts from the DAGCompiler extraction path. The centering
    offset is stored in _mesh_center_offsets and applied in apply_transform().
    """
    from .operator import _tessellate_from_blobs

    to_create = [h for h in hashes if bpy.data.meshes.get(h) is None]
    if not to_create:
        return {}

    created = {}

    # Primary: BLOB tessellation from component_library.db
    if lib_db_path:
        created = _tessellate_from_blobs(to_create, lib_db_path)

    # Fallback: library.blend
    if not created and lib_blend_path:
        from pathlib import Path
        if Path(lib_blend_path).exists():
            with bpy.data.libraries.load(lib_blend_path, link=False) as (data_from, data_to):
                available = set(data_from.meshes)
                data_to.meshes = [h for h in to_create if h in available]
            created = {m.name: m for m in data_to.meshes if m is not None}

    # S201: re-center meshes that are far from origin
    if created:
        _recenter_meshes(created)

    return created


def _recenter_meshes(created):
    """S201: shift vertices so mesh bbox center is at origin.
    Stores the offset in _mesh_center_offsets for apply_transform() to compensate."""
    import numpy as np

    for ghash, mesh in created.items():
        if ghash in _mesh_center_offsets:
            continue  # already handled
        if not mesh.vertices or len(mesh.vertices) < 3:
            continue

        # Read verts
        n = len(mesh.vertices)
        coords = [0.0] * (n * 3)
        mesh.vertices.foreach_get("co", coords)
        arr = __import__('array').array('f', coords)

        xs = arr[0::3]
        ys = arr[1::3]
        zs = arr[2::3]
        cx = (min(xs) + max(xs)) / 2.0
        cy = (min(ys) + max(ys)) / 2.0
        cz = (min(zs) + max(zs)) / 2.0

        if abs(cx) < _RECENTER_THRESH and abs(cy) < _RECENTER_THRESH and abs(cz) < _RECENTER_THRESH:
            continue  # already centered enough

        # Shift vertices
        for i in range(n):
            arr[i*3] -= cx
            arr[i*3+1] -= cy
            arr[i*3+2] -= cz

        mesh.vertices.foreach_set("co", arr)
        mesh.update()
        _mesh_center_offsets[ghash] = (cx, cy, cz)


def create_material(r, g, b, a, prefix="DS"):
    """Get or create a BSDF material with the given RGBA.

    Uses Principled BSDF node tree for correct rendering in all viewport modes.
    Materials are cached by RGBA key — shared across all objects with the same color.
    """
    mat_key = f"{prefix}_{r:.2f},{g:.2f},{b:.2f},{a:.2f}"
    mat = bpy.data.materials.get(mat_key)
    if mat is not None:
        return mat

    mat = bpy.data.materials.new(name=mat_key)
    mat.diffuse_color = (r, g, b, a)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    out_n = nodes.new('ShaderNodeOutputMaterial')
    bsdf = nodes.new('ShaderNodeBsdfPrincipled')
    if 'Base Color' in bsdf.inputs:
        bsdf.inputs['Base Color'].default_value = (r, g, b, 1.0)
    if 'Alpha' in bsdf.inputs:
        bsdf.inputs['Alpha'].default_value = a
    mat.node_tree.links.new(bsdf.outputs['BSDF'], out_n.inputs['Surface'])
    if a < 0.99:
        try:
            mat.blend_method = 'BLEND'
        except (AttributeError, TypeError):
            pass  # Blender 5.0+ handles via Alpha node
    return mat


def apply_material(obj, rgba_str, mat_name, disc, styles_cache, prefix="DS"):
    """Resolve material RGBA and apply to object.

    Uses surface_styles for lookup, falls back to rgba_str, then discipline color.
    Sets obj.color for viewport display and assigns BSDF material to slot 0.
    """
    from .operator import _resolve_material
    from .bbox_visualization import get_discipline_color

    final_rgba, _style_data = _resolve_material(mat_name, rgba_str, disc, styles_cache)

    if final_rgba:
        try:
            r, g, b, a = map(float, final_rgba.split(','))
        except Exception:
            r, g, b, a = 0.6, 0.6, 0.6, 1.0
    else:
        # Discipline-tinted fallback
        _dc = get_discipline_color(disc or 'OTHER')
        r, g, b, a = _dc[0] * 0.7, _dc[1] * 0.7, _dc[2] * 0.7, 1.0

    obj.color = (r, g, b, a)
    if len(obj.material_slots) > 0:
        mat = create_material(r, g, b, a, prefix)
        obj.material_slots[0].link = 'OBJECT'
        obj.material_slots[0].material = mat


def apply_transform(obj, transform, ox=0.0, oy=0.0, oz=0.0):
    """Apply translation + rotation from a transform tuple.

    transform: (center_x, center_y, center_z, rotation_x, rotation_y, rotation_z)
    ox, oy, oz: model offset to subtract.

    S201: if the mesh was re-centered at load time, the centering offset is added
    back to the translation so the visual position is unchanged but the selection
    bounding box is tight around the object origin.
    """
    cx, cy, cz = transform[0], transform[1], transform[2]
    rx = transform[3] or 0.0
    ry = transform[4] or 0.0
    rz = transform[5] or 0.0

    # S201: compensate for mesh re-centering
    ghash = obj.data.name if obj.data else None
    if ghash and ghash in _mesh_center_offsets:
        mcx, mcy, mcz = _mesh_center_offsets[ghash]
        cx += mcx
        cy += mcy
        cz += mcz

    loc_mat = Matrix.Translation((cx - ox, cy - oy, cz - oz))
    if rx or ry or rz:
        rot_mat = Euler((rx, ry, rz), 'XYZ').to_matrix().to_4x4()
        obj.matrix_basis = loc_mat @ rot_mat
    else:
        obj.matrix_basis = loc_mat
