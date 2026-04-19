# Bonsai - OpenBIM Blender Add-on
# Copyright (C) 2025 Your Engineering Firm
#
# This file is part of Bonsai.
#
# Bonsai is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
S195/S196: Direct DB Streaming — tessellate from BLOBs, no .blend files.

Extracted from operator.py (S196 refactor).
State variables live in bbox_visualization.py (shared with HUD).
Helper functions (_load_surface_styles, _resolve_material, _tessellate_from_blobs)
imported from operator.py.
"""

import bpy
import os

from .operator import _load_surface_styles, _tessellate_from_blobs
from .mesh_utils import ensure_meshes, apply_material, apply_transform

# S197: dedicated log file for Direct Stream diagnostics
_DS_LOG = os.path.expanduser("~/Documents/bonsai/consolelogs/direct_stream.log")
os.makedirs(os.path.dirname(_DS_LOG), exist_ok=True)

def _ds_log(msg):
    """Append to DS log file and print to stdout."""
    print(msg)
    try:
        with open(_DS_LOG, 'a', encoding='utf-8') as f:
            f.write(msg + '\n')
    except Exception:
        pass


def _bld_label(bld_name):
    """S197: get or assign a numbered Outliner label like '01_Clinic'."""
    from . import bbox_visualization as bv
    idx = bv._direct_stream_bld_index.get(bld_name)
    if idx is not None:
        return f"{idx:02d}_{bld_name}"
    # Assign: reuse freed index or increment
    if bv._direct_stream_free_indices:
        bv._direct_stream_free_indices.sort()
        idx = bv._direct_stream_free_indices.pop(0)
    else:
        idx = bv._direct_stream_next_index
        bv._direct_stream_next_index += 1
    bv._direct_stream_bld_index[bld_name] = idx
    return f"{idx:02d}_{bld_name}"


def _free_bld_label(bld_name):
    """S197: recycle a building's index for reuse."""
    from . import bbox_visualization as bv
    idx = bv._direct_stream_bld_index.pop(bld_name, None)
    if idx is not None:
        bv._direct_stream_free_indices.append(idx)


def _direct_stream_remove_building(bld_name):
    """Remove all direct-streamed objects for a building.
    S197: batch_remove() for objects, then remove collections top-down."""
    import bpy as _bpy
    from . import bbox_visualization as bv
    import time

    t0 = time.time()
    guids = bv._direct_stream_buildings.pop(bld_name, set())
    bv._direct_stream_disc_phase.pop(bld_name, None)
    if bv._direct_stream_active_bld == bld_name:
        bv._direct_stream_active_bld = None
    # S197: clear phase offsets so building re-streams from row 0
    _offsets = getattr(_direct_stream_tick, '_phase_offsets', {})
    for key in [k for k in _offsets if k.startswith(bld_name + '_')]:
        del _offsets[key]
    count = len(guids)

    # Drop tracking refs (fast — just dict/set ops)
    objs_to_remove = []
    for guid in guids:
        obj = bv._direct_stream_objects.pop(guid, None)
        if obj:
            objs_to_remove.append(obj)
        bv._direct_stream_guids.discard(guid)

    # S197: batch_remove all objects in one C call — orders of magnitude faster
    if objs_to_remove:
        _bpy.data.batch_remove(objs_to_remove)

    # Remove collection hierarchy (now empty)
    col_label = _bld_label(bld_name)
    col = _bpy.data.collections.get(col_label)
    if col:
        cols_to_remove = []
        for disc_col in list(col.children):
            for batch_col in list(disc_col.children):
                cols_to_remove.append(batch_col)
            cols_to_remove.append(disc_col)
        scene_col = _bpy.context.scene.collection
        if col.name in {c.name for c in scene_col.children}:
            scene_col.children.unlink(col)
        cols_to_remove.append(col)
        _bpy.data.batch_remove(cols_to_remove)
    bv._direct_stream_disc_loaded.pop(bld_name, None)
    _free_bld_label(bld_name)  # S197: recycle index for reuse
    # S197: blacklist last 3 shredded — don't re-stream immediately
    if bld_name not in bv._direct_stream_shred_blacklist:
        bv._direct_stream_shred_blacklist.append(bld_name)
    if len(bv._direct_stream_shred_blacklist) > 3:
        bv._direct_stream_shred_blacklist.pop(0)

    elapsed_ms = (time.time() - t0) * 1000
    if count:
        print(f"[S195] §DS_UNLINK {bld_name} removed={count:,} unlink_ms={elapsed_ms:.0f}ms")
    return count


def _is_camera_inside_bbox(bld, cx, cy, cz):
    """S198: check if camera is inside building ARC/STR bounding box (generous margin)."""
    from . import bbox_visualization as bv
    bbox = bv._direct_stream_bld_bbox.get(bld)
    if not bbox:
        return False
    minX, maxX, minY, maxY, minZ, maxZ = bbox
    margin = 20  # metres — generous, user doesn't need to be literally inside
    return (minX - margin <= cx <= maxX + margin and
            minY - margin <= cy <= maxY + margin and
            minZ <= cz <= maxZ + 10)  # +10m above roof


def _merge_envelope_group(group_elements, xform, ox, oy, oz):
    """S198: merge a group of small elements into one combined mesh (world-space verts).

    Returns (all_verts, all_faces, merged_guids) or (None, None, []).
    """
    import bpy as _bpy
    from mathutils import Matrix, Euler

    all_verts = []
    all_faces = []
    vert_offset = 0
    merged_guids = []

    for guid, ghash, *_ in group_elements:
        mesh = _bpy.data.meshes.get(ghash)
        if not mesh or mesh.vertices is None or len(mesh.vertices) == 0:
            continue
        tr = xform.get(guid)
        if not tr:
            continue

        cx, cy, cz = tr[0] - ox, tr[1] - oy, tr[2] - oz
        rx = tr[3] or 0.0
        ry = tr[4] or 0.0
        rz = tr[5] or 0.0
        loc_mat = Matrix.Translation((cx, cy, cz))
        if rx or ry or rz:
            rot_mat = Euler((rx, ry, rz), 'XYZ').to_matrix().to_4x4()
            mat = loc_mat @ rot_mat
        else:
            mat = loc_mat

        for v in mesh.vertices:
            wv = mat @ v.co
            all_verts.append((wv.x, wv.y, wv.z))

        for p in mesh.polygons:
            all_faces.append(tuple(vi + vert_offset for vi in p.vertices))

        vert_offset += len(mesh.vertices)
        merged_guids.append(guid)

    if not all_verts:
        return None, None, []
    return all_verts, all_faces, merged_guids


# S198: animated camera pan state
_anim_pan_active = False
_anim_pan_start = None      # Vector — start view_location
_anim_pan_end = None        # Vector — target view_location
_anim_pan_start_dist = 0    # start view_distance
_anim_pan_end_dist = 0      # target view_distance
_anim_pan_start_rot = None  # Quaternion — start view_rotation
_anim_pan_end_rot = None    # Quaternion — target view_rotation
_anim_pan_frame = 0         # current frame (0..N)
_anim_pan_frames = 15       # total frames (~450ms at 30ms/frame)
_anim_pan_clip = 5000.0     # clip_end to set
_anim_pan_done_time = 0.0   # time.time() when animation finished — pause before streaming
_ANIM_PAN_HOLD_S = 0.8     # seconds to hold after fly-to before streaming starts
# S198: cinematic auto-pilot — dramatic fly-in if user idle after DS start
_ds_start_time = 0.0
_ds_autopilot_fired = False


def _anim_pan_tick():
    """Timer: smooth camera fly-to with location + distance + rotation interpolation."""
    import bpy as _bpy
    import math
    from . import bbox_visualization as bv
    global _anim_pan_active, _anim_pan_frame

    if not _anim_pan_active:
        return None  # unregister

    _anim_pan_frame += 1
    if _anim_pan_frame == 1:
        print(f"[S198] §ANIM_START frames={_anim_pan_frames}")
    if _anim_pan_frame == _anim_pan_frames:
        print(f"[S198] §ANIM_END frame={_anim_pan_frame}")
    t = _anim_pan_frame / _anim_pan_frames
    # Ease-out cubic: 1 - (1-t)^3 — fast start, gentle landing
    t_ease = 1.0 - (1.0 - t) ** 3

    for _area in _bpy.context.screen.areas:
        if _area.type == 'VIEW_3D':
            _r3d = _area.spaces[0].region_3d
            _r3d.view_location = _anim_pan_start.lerp(_anim_pan_end, t_ease)
            _r3d.view_distance = _anim_pan_start_dist + (
                _anim_pan_end_dist - _anim_pan_start_dist) * t_ease
            # Slerp rotation for smooth orbit feel
            if _anim_pan_start_rot and _anim_pan_end_rot:
                _r3d.view_rotation = _anim_pan_start_rot.slerp(
                    _anim_pan_end_rot, t_ease)
            _area.spaces[0].clip_end = max(_anim_pan_clip, _anim_pan_end_dist * 10)
            _area.tag_redraw()
            break

    if _anim_pan_frame >= _anim_pan_frames:
        _anim_pan_active = False
        import time as _t2
        global _anim_pan_done_time
        _anim_pan_done_time = _t2.time()
        # Snap to exact final values
        for _area in _bpy.context.screen.areas:
            if _area.type == 'VIEW_3D':
                _r3d = _area.spaces[0].region_3d
                _r3d.view_location = _anim_pan_end.copy()
                _r3d.view_distance = _anim_pan_end_dist
                if _anim_pan_end_rot:
                    _r3d.view_rotation = _anim_pan_end_rot.copy()
                _area.tag_redraw()
                break
        # Update cam snapshot so settle-halt doesn't trigger
        _off2 = bv._model_offset
        _ox = _off2.x if _off2 else 0.0
        _oy = _off2.y if _off2 else 0.0
        _oz = _off2.z if _off2 else 0.0
        for _area in _bpy.context.screen.areas:
            if _area.type == 'VIEW_3D':
                _vl = _area.spaces[0].region_3d.view_location
                bv._direct_stream_cam_last = (_vl.x + _ox, _vl.y + _oy, _vl.z + _oz)
                break
        import time
        bv._direct_stream_cam_still_t = time.time()
        return None  # unregister

    return 0.03  # ~33fps — next frame in 30ms


def _start_anim_pan(start_loc, target_loc, start_dist, target_dist, clip_end,
                     start_rot=None, end_rot=None, frames=None):
    """Kick off animated camera fly-to with optional rotation and custom frame count."""
    import bpy as _bpy
    global _anim_pan_active, _anim_pan_start, _anim_pan_end
    global _anim_pan_start_dist, _anim_pan_end_dist, _anim_pan_frame, _anim_pan_clip
    global _anim_pan_start_rot, _anim_pan_end_rot, _anim_pan_frames

    _anim_pan_active = True
    _anim_pan_start = start_loc.copy()
    _anim_pan_end = target_loc.copy()
    _anim_pan_start_dist = start_dist
    _anim_pan_end_dist = target_dist
    _anim_pan_start_rot = start_rot.copy() if start_rot else None
    _anim_pan_end_rot = end_rot.copy() if end_rot else None
    _anim_pan_frame = 0
    _anim_pan_frames = frames or 15  # custom frame count for distant autopilot
    _anim_pan_clip = clip_end
    if not _bpy.app.timers.is_registered(_anim_pan_tick):
        _bpy.app.timers.register(_anim_pan_tick, first_interval=0.03)


def _direct_stream_tick():
    """Timer: stream elements from DB BLOBs based on camera distance.
    No .blend files. No libraries.load(). Pure SQL + from_pydata().
    S198: envelope-first streaming with small-element merging."""
    import math
    import time
    import sqlite3
    import bpy as _bpy
    from mathutils import Quaternion
    from . import bbox_visualization as bv

    # S198: don't stream while camera is animating — let fly-to complete first
    if _anim_pan_active:
        return 0.1  # fast poll so animation is smooth
    # Brief hold after animation — user sees building wireframe before streaming
    global _anim_pan_done_time
    if _anim_pan_done_time:
        _hold_elapsed = time.time() - _anim_pan_done_time
        if _hold_elapsed < _ANIM_PAN_HOLD_S:
            return 0.2
        _anim_pan_done_time = 0.0  # clear — one-shot hold

    if not bv._direct_stream_enabled:
        # Auto-shred while paused: clean up buildings one per tick, furthest first
        if bv._direct_stream_auto_shred and bv._direct_stream_buildings:
            _farthest = None
            _farthest_dist = 0
            cam = bv._dlod_eye_pos
            if cam:
                _off = bv._model_offset
                cx = cam[0] + (_off.x if _off else 0.0)
                cy = cam[1] + (_off.y if _off else 0.0)
                cz = cam[2] + (_off.z if _off else 0.0)
                for _sb in list(bv._direct_stream_buildings.keys()):
                    _sc = bv._building_centres.get(_sb)
                    if _sc:
                        _sd = math.sqrt((cx-_sc[0])**2 + (cy-_sc[1])**2)
                        if _sd > _farthest_dist:
                            _farthest_dist = _sd
                            _farthest = _sb
            else:
                # No eye pos — just pick any
                _farthest = next(iter(bv._direct_stream_buildings))
            if _farthest:
                print(f"[S195] §AUTO_SHRED_IDLE {_farthest} dist={_farthest_dist:.0f}m")
                _direct_stream_remove_building(_farthest)
            return 2.0  # slower interval while cleaning up
        return None  # unregister — nothing to do

    if not bv._building_centres or not bv._db_path_cache:
        return 2.0

    # ── Camera position — DO NOT CHANGE ──
    # MUST use _dlod_eye_pos (view_matrix.inverted().translation) = actual camera eye.
    # DO NOT use view_location — that's the orbit pivot, can be underground.
    # Blender→IFC: ADD offset (blender = ifc - offset → ifc = blender + offset).
    # DO NOT use minus — that mirrors the position and picks wrong buildings.
    # XY-only distance below — camera Z varies with orbit angle, irrelevant for "nearest".
    if not bv._dlod_eye_pos:
        return 1.0
    cam = bv._dlod_eye_pos
    _off = bv._model_offset
    if _off:
        cx, cy, cz = cam[0] + _off.x, cam[1] + _off.y, cam[2] + _off.z
    else:
        cx, cy, cz = cam

    # ── S197: Camera-settle detection ──
    # If user is moving the camera, halt streaming until 1s after they stop.
    _now = time.time()
    _cam_pos = (cx, cy, cz)
    _prev = bv._direct_stream_cam_last
    if _prev:
        _cam_delta = math.sqrt(
            (_cam_pos[0]-_prev[0])**2 + (_cam_pos[1]-_prev[1])**2 +
            (_cam_pos[2]-_prev[2])**2)
        if _cam_delta > bv._DIRECT_STREAM_CAM_THRESH:
            # User is navigating — record new position, reset settle timer
            bv._direct_stream_cam_last = _cam_pos
            bv._direct_stream_cam_still_t = _now
            return 0.3  # check again soon but don't stream
        # Camera is still — check if settled long enough
        if (_now - bv._direct_stream_cam_still_t) < bv._DIRECT_STREAM_SETTLE_S:
            return 0.3  # still settling — wait
    else:
        # First tick — snapshot camera position, don't stream yet
        bv._direct_stream_cam_last = _cam_pos
        bv._direct_stream_cam_still_t = _now
        return 0.5  # let settle timer start before first building selection
    # Camera settled — proceed with streaming
    bv._direct_stream_cam_last = _cam_pos

    # ── S198: Autopilot — if idle 5s, dramatic fly-to nearest unfinished building ──
    _idle_s = _now - bv._direct_stream_cam_still_t
    if _idle_s >= 5.0 and not bv._direct_stream_active_bld and bv._building_centres:
        # S198: skip similar buildings — extract base type from name
        # T0_Duplex, T1_Duplex, T2_Duplex → base "Duplex"
        # S0_0_SampleHouse → base "SampleHouse"
        import re as _re
        def _base_type(name):
            """Strip tile/slot prefixes AND trailing _N/_Federated to get archetype."""
            name = _re.sub(r'^[ST]\d+_(\d+_)?', '', name)
            name = _re.sub(r'(_\d+|_Federated)$', '', name)
            return name

        _visited_types = set()
        for _vb in bv._direct_stream_buildings:
            _visited_types.add(_base_type(_vb))

        # Find nearest building with unfinished envelope, prefer novel type
        _ap_best = None
        _ap_dist = float('inf')
        _ap_novel = None   # best novel (different type) candidate
        _ap_novel_dist = float('inf')
        for _b, _bc in bv._building_centres.items():
            _ph = bv._direct_stream_disc_phase.get(_b, 'envelope')
            if _ph in ('done', 'envelope_done', 'shell_done'):
                continue
            if _b in bv._direct_stream_shred_blacklist:
                continue
            _d = math.sqrt((cx - _bc[0])**2 + (cy - _bc[1])**2)
            _bt = _base_type(_b)
            if _bt not in _visited_types and _d < _ap_novel_dist:
                _ap_novel_dist = _d
                _ap_novel = _b
            if _d < _ap_dist:
                _ap_dist = _d
                _ap_best = _b
        # S198: if user parked near a building (<100m), stream THAT one — respect user position.
        # Only prefer novel type when user is far from all buildings (autopilot touring).
        if _ap_novel and _ap_dist > 100:
            _ap_best = _ap_novel
            _ap_dist = _ap_novel_dist
        if _ap_best:
            # S198: ALWAYS fly-to — even nearby buildings. Camera must center the building.
            _bc = bv._building_centres[_ap_best]
            _off2 = bv._model_offset
            _bx = _bc[0] - (_off2.x if _off2 else 0.0)
            _by = _bc[1] - (_off2.y if _off2 else 0.0)
            _bz = _bc[2] - (_off2.z if _off2 else 0.0)
            _bld_h = 10
            _bbox = bv._direct_stream_bld_bbox.get(_ap_best)
            if _bbox:
                _bld_h = max(10, _bbox[5] - _bbox[4])
            _dx, _dy, _dz = _bld_h * 2, _bld_h * 2, _bld_h  # fallback
            if _bbox:
                _dx = _bbox[1] - _bbox[0]
                _dy = _bbox[3] - _bbox[2]
                _dz = _bbox[5] - _bbox[4]
            _target_dist = max(60, min(600, max(_dz * 3.5, max(_dx, _dy) * 0.6)))
            _pivot_z = _bld_h * 0.45
            from mathutils import Vector
            _tgt = Vector((_bx, _by, _bz + _pivot_z))
            _clip = max(5000, _target_dist * 10)
            # Frame count: nearby=15 (quick), far=45 (dramatic)
            _n_frames = max(15, min(45, int(_ap_dist / 20)))
            for _area in _bpy.context.screen.areas:
                if _area.type == 'VIEW_3D':
                    _r3d = _area.spaces[0].region_3d
                    _cur_loc = Vector(_r3d.view_location)
                    _cur_dist = _r3d.view_distance
                    _cur_rot = _r3d.view_rotation.copy()
                    import random as _rnd
                    _orb = 0.0
                    _nice_rot = Quaternion((0.8460, 0.4404,
                                            -0.1389 + _orb, -0.2667 + _orb))
                    _nice_rot.normalize()
                    _start_anim_pan(_cur_loc, _tgt, _cur_dist, _target_dist, _clip,
                                    _cur_rot, _nice_rot, frames=_n_frames)
                    break
            bv._direct_stream_active_bld = _ap_best
            bv._direct_stream_last_bld = _ap_best
            bv._direct_stream_cam_still_t = _now
            _ds_log(f"[S198] §DS_AUTOPILOT {_ap_best} dist={_ap_dist:.0f}m frames={_n_frames}")
            return 0.3  # let animation play

    # ── Streaming logic ──
    current_count = len(bv._direct_stream_guids)
    if current_count >= bv._DIRECT_STREAM_BUDGET:
        return 2.0  # at budget — idle

    # S197: XY distance only — camera Z varies wildly with orbit angle,
    # all buildings are on the ground plane so Z is irrelevant for "nearest"
    _bld_dists = {}
    for _b, centre in bv._building_centres.items():
        _bld_dists[_b] = math.sqrt(
            (cx - centre[0])**2 + (cy - centre[1])**2)

    # ── Pause active building if user moved out of range ──
    # S198: shell/detail phases require camera inside bbox — pause if user flies out
    _active = bv._direct_stream_active_bld
    if _active:
        _active_dist = _bld_dists.get(_active, 999)
        _active_phase = bv._direct_stream_disc_phase.get(_active, 'envelope')
        if _active_dist > bv._DIRECT_STREAM_RADIUS:
            print(f"[S195] §DS_PAUSE {_active} dist={_active_dist:.0f}m — out of range")
            bv._direct_stream_active_bld = None
        elif _active_phase in ('shell', 'detail') and not _is_camera_inside_bbox(_active, cx, cy, cz):
            _ds_log(f"[S198] §DS_PAUSE {_active} phase={_active_phase} — camera left bbox")
            bv._direct_stream_active_bld = None

    # ── S198: envelope_done → shell transition on camera-inside-bbox ──
    for _b in list(bv._direct_stream_disc_phase.keys()):
        if bv._direct_stream_disc_phase.get(_b) == 'envelope_done':
            if _is_camera_inside_bbox(_b, cx, cy, cz):
                bv._direct_stream_disc_phase[_b] = 'shell'
                _ds_log(f"[S198] §DS_ENTER {_b} — camera inside bbox, transitioning to SHELL")

    # ── Detail streaming: camera must be INSIDE building bbox ──
    # S198: interior disciplines (MEP, ELEC, FP, ACMV…) only visible from inside.
    # Distance alone is not enough — camera must pass the bbox-inside check.
    bld = None
    phase = None
    for _b, _d in _bld_dists.items():
        _ph = bv._direct_stream_disc_phase.get(_b)
        if _ph == 'done':
            continue
        _inside = _is_camera_inside_bbox(_b, cx, cy, cz)
        if not _inside:
            continue
        # Camera is inside this building — advance phases
        if _ph == 'envelope_done':
            bv._direct_stream_disc_phase[_b] = 'shell'
            _ph = 'shell'
            _ds_log(f"[S198] §DS_ENTER {_b} — camera inside bbox, forcing SHELL")
        if _ph == 'shell_done':
            bv._direct_stream_disc_phase[_b] = 'detail'
            _ph = 'detail'
            _ds_log(f"[S198] §DS_DETAIL_START {_b} — camera inside bbox, streaming interior discs")
        if _ph == 'detail':
            already = len(bv._direct_stream_buildings.get(_b, set()))
            total = bv._building_element_counts.get(_b, 0)
            if already < total:
                bld = _b
                phase = 'detail'
                break

    # ── Shell streaming (locked): finish current before switching ──
    if not bld:
        bld = bv._direct_stream_active_bld
        if not bld:
            # S197: get camera forward vector for "in-sight" scoring
            _cam_fwd = None
            for _area in _bpy.context.screen.areas:
                if _area.type == 'VIEW_3D':
                    _r3d = _area.spaces[0].region_3d
                    from mathutils import Vector
                    _cam_fwd = _r3d.view_rotation @ Vector((0, 0, -1))
                    break

            # S197: adjacency — prefer buildings near the last streamed one
            _last_centre = None
            _last = bv._direct_stream_last_bld
            if _last and _last in bv._building_centres:
                _last_centre = bv._building_centres[_last]

            _candidates = []
            for _b, _d in _bld_dists.items():
                if _d < bv._DIRECT_STREAM_RADIUS:
                    # Skip recently shredded (blacklist max 3)
                    if _b in bv._direct_stream_shred_blacklist:
                        continue
                    _ph = bv._direct_stream_disc_phase.get(_b, 'envelope')
                    # S198: shell requires camera inside bbox — envelope streams from outside
                    if _ph == 'shell' and not _is_camera_inside_bbox(_b, cx, cy, cz):
                        continue
                    if _ph in ('envelope', 'shell'):
                        already = len(bv._direct_stream_buildings.get(_b, set()))
                        total = bv._building_element_counts.get(_b, 0)
                        if already < total:
                            _bc = bv._building_centres[_b]
                            # Forward scoring (XY only)
                            _dir_x, _dir_y = _bc[0]-cx, _bc[1]-cy
                            _norm = max(_d, 0.1)
                            if _cam_fwd:
                                _dot = (_dir_x*_cam_fwd.x + _dir_y*_cam_fwd.y) / _norm
                            else:
                                _dot = 0
                            # Adjacency bonus: buildings near last streamed score lower
                            _adj = 0
                            if _last_centre:
                                _adj_d = math.sqrt((_bc[0]-_last_centre[0])**2 +
                                                   (_bc[1]-_last_centre[1])**2)
                                _adj = min(_adj_d, 100)  # cap at 100m
                            # Score: distance + adjacency, minus forward bonus
                            _score = _d * 0.3 + _adj * 0.7 - _dot * 50
                            _candidates.append((_score, _d, _b))
            if not _candidates:
                return 1.0
            _candidates.sort()
            # S197: debug — log camera pos + top 3 candidates on first pick
            if not bv._direct_stream_buildings:
                _top3 = _candidates[:3]
                _ds_log(f"[S197] §DS_PICK cam_eye=({cam[0]:.0f},{cam[1]:.0f},{cam[2]:.0f}) "
                      f"cam_ifc=({cx:.0f},{cy:.0f},{cz:.0f}) "
                      f"offset=({_off.x:.0f},{_off.y:.0f},{_off.z:.0f})" if _off else
                      f"[S197] §DS_PICK cam_eye=({cam[0]:.0f},{cam[1]:.0f},{cam[2]:.0f}) "
                      f"cam_ifc=({cx:.0f},{cy:.0f},{cz:.0f}) offset=None")
                for _sc, _sd, _sb in _top3:
                    _bc = bv._building_centres[_sb]
                    _ds_log(f"[S197] §DS_CANDIDATE {_sb} score={_sc:.0f} dist={_sd:.0f}m "
                          f"centre=({_bc[0]:.0f},{_bc[1]:.0f},{_bc[2]:.0f})")
            _, _, bld = _candidates[0]
            bv._direct_stream_active_bld = bld
            bv._direct_stream_last_bld = bld
            # Query disc totals for HUD bars
            if bld not in bv._direct_stream_disc_totals:
                try:
                    _dc = sqlite3.connect(bv._db_path_cache)
                    _bc = "m.building = ? AND" if bv._has_building_column else ""
                    _bp = (bld,) if bv._has_building_column else ()
                    _dr = _dc.execute(f"""
                        SELECT m.discipline, COUNT(*)
                        FROM elements_meta m
                        JOIN element_instances i ON m.guid = i.guid
                        WHERE {_bc} i.geometry_hash IS NOT NULL
                          AND m.ifc_class != 'IfcOpeningElement'
                        GROUP BY m.discipline
                    """, _bp).fetchall()
                    bv._direct_stream_disc_totals[bld] = {d: c for d, c in _dr}
                    _dc.close()
                except Exception:
                    pass
            _dtot = bv._direct_stream_disc_totals.get(bld, {})
            _disc_str = ' '.join(f"{d}={c:,}" for d, c in sorted(_dtot.items()))
            _ds_log(f"[S195] §DS_START {bld} "
                  f"elements={bv._building_element_counts.get(bld, 0):,} [{_disc_str}]")
            # S197: cinematic camera — pan view_location, preserve rotation feel
            _centre = bv._building_centres.get(bld)
            if _centre:
                _off2 = bv._model_offset
                _bx = _centre[0] - (_off2.x if _off2 else 0.0)
                _by = _centre[1] - (_off2.y if _off2 else 0.0)
                _bz = _centre[2] - (_off2.z if _off2 else 0.0)
                _el_count = bv._building_element_counts.get(bld, 0)
                _target_dist = max(40, min(200, _el_count ** 0.35))
                _bld_height = 10
                try:
                    _ext_conn = sqlite3.connect(bv._db_path_cache)
                    _ext_bc = "m.building = ? AND" if bv._has_building_column else ""
                    _ext_bp = (bld,) if bv._has_building_column else ()
                    # S197: bbox from STR/ARC only — tight building envelope
                    _ext_row = _ext_conn.execute(f"""
                        SELECT MAX(r.maxX)-MIN(r.minX),
                               MAX(r.maxY)-MIN(r.minY),
                               MAX(r.maxZ)-MIN(r.minZ)
                        FROM elements_rtree r
                        JOIN elements_meta m ON r.id = m.rowid
                        WHERE {_ext_bc} m.discipline IN ('ARC','STR')
                    """, _ext_bp).fetchone()
                    _ext_conn.close()
                    if _ext_row and _ext_row[0]:
                        _dx, _dy, _dz = _ext_row
                        _bld_height = _dz or 10
                        _diag = math.sqrt(_dx**2 + _dy**2 + _dz**2)
                        _target_dist = max(60, min(600, max(_dz * 3.5, max(_dx, _dy) * 0.6)))
                except Exception:
                    pass
                _pivot_z_offset = _bld_height * 0.45
                # S198: animated camera pan — 5 frames ease-out cubic (~150ms)
                from mathutils import Vector
                _tgt = Vector((_bx, _by, _bz + _pivot_z_offset))
                _clip = max(5000, _target_dist * 10)
                # S198: nice isometric target — ~30° elevation, slight orbit offset
                # Standard isometric: (0.8460, 0.4404, -0.1389, -0.2667)
                # Offset by ~25° orbit for cinematic variety
                import random as _rnd
                _orbit_offset = 0.0  # slight random orbit variety
                _nice_rot = Quaternion((0.8460, 0.4404,
                                        -0.1389 + _orbit_offset,
                                        -0.2667 + _orbit_offset))
                _nice_rot.normalize()
                _is_first = len(bv._direct_stream_buildings) == 0
                for _area in _bpy.context.screen.areas:
                    if _area.type == 'VIEW_3D':
                        _r3d = _area.spaces[0].region_3d
                        _cur_loc = Vector(_r3d.view_location)
                        _cur_dist = _r3d.view_distance
                        _cur_rot = _r3d.view_rotation.copy()
                        if _is_first:
                            # First building: fly in with rotation to nice angle
                            _start_anim_pan(_cur_loc, _tgt, _cur_dist, _target_dist, _clip,
                                            _cur_rot, _nice_rot)
                        else:
                            # Subsequent: orbit sweep to next building
                            _fwd = _r3d.view_rotation @ Vector((0, 0, -1))
                            _to_bld = _tgt - _cur_loc
                            _dot = _fwd.dot(_to_bld.normalized()) if _to_bld.length > 0.1 else 1.0
                            if _dot < 0.2:
                                _tgt = _tgt.copy()
                                _tgt.z += _bld_height * 0.5
                            _start_anim_pan(_cur_loc, _tgt, _cur_dist, _target_dist, _clip,
                                            _cur_rot, _nice_rot)
                        break
                # Update cam snapshot so settle-halt doesn't fire during animation
                _ox = _off2.x if _off2 else 0.0
                _oy = _off2.y if _off2 else 0.0
                _oz = _off2.z if _off2 else 0.0
                bv._direct_stream_cam_last = (_bx + _ox, _by + _oy, _bz + _pivot_z_offset + _oz)
                bv._direct_stream_cam_still_t = _now
                _ds_log(f"[S198] §DS_FLY {bld} centre=({_bx:.0f},{_by:.0f},{_bz:.0f}) "
                      f"dist={_target_dist:.0f}m anim={_anim_pan_active} frames={_anim_pan_frames}")
            # S198: let fly-to animation play before streaming starts — return IMMEDIATELY
            if _anim_pan_active:
                _ds_log(f"[S198] §DS_FLY_HOLD — animation active, deferring stream")
                return 0.1
        # S198: use building's current phase (envelope for new, shell if transitioned)
        phase = bv._direct_stream_disc_phase.get(bld, 'envelope')

    dist_nearest = _bld_dists.get(bld, 999)

    # Query next batch of elements for this building
    t0 = time.time()
    db_path = bv._db_path_cache
    lib_db = bv._library_db_cache
    if not lib_db:
        return 2.0

    # S195: Adaptive batching — 1000 when meshes pre-cached, 500 default
    _last_new = getattr(_direct_stream_tick, '_last_hashes_new', 0)
    _last_ms = getattr(_direct_stream_tick, '_last_tick_ms', 0)
    if _last_new == 0 and _last_ms < 1500:
        batch = 1000  # all meshes pre-cached — placement only
    else:
        batch = bv._DIRECT_STREAM_BATCH  # default 500

    budget_left = bv._DIRECT_STREAM_BUDGET - current_count
    if budget_left <= 0:
        return 1.0
    batch = min(batch, budget_left)

    # Track offset per building+phase (shell and detail have different queries)
    _offset_key = f"{bld}_{phase}"
    _phase_offsets = getattr(_direct_stream_tick, '_phase_offsets', {})
    offset = _phase_offsets.get(_offset_key, 0)

    try:
        conn = sqlite3.connect(db_path)
        bld_clause = "m.building = ? AND" if bv._has_building_column else ""
        bld_params = (bld,) if bv._has_building_column else ()
        _shell = tuple(bv._DIRECT_STREAM_SHELL_DISCS)
        # ── S198: ENVELOPE — exterior shell of ARC+STR only ──
        # Two filters: (1) exclude known interior classes, (2) bbox shell proximity
        # Elements must be near the building's outer boundary to be visible from outside.
        if phase == 'envelope':
            disc_clause = f"AND m.discipline IN ({','.join('?' * len(_shell))})"
            disc_params = _shell

            # Bbox shell filter: elements within margin of building boundary
            # S198: bbox shell proximity — fixed 5m depth for exterior shell
            # Only applied to buildings >30m in both X and Y (small buildings stream all)
            _bbox = bv._direct_stream_bld_bbox.get(bld)
            _shell_clause = ""
            _shell_params = ()
            if _bbox:
                _mnx, _mxx, _mny, _mxy, _mnz, _mxz = _bbox
                _dx = _mxx - _mnx
                _dy = _mxy - _mny
                if _dx > 30 and _dy > 30:
                    _margin = 5.0  # 5m = typical facade-to-interior depth
                    _inner_mnx = _mnx + _margin
                    _inner_mxx = _mxx - _margin
                    _inner_mny = _mny + _margin
                    _inner_mxy = _mxy - _margin
                    _inner_mxz = _mxz - _margin
                    _inner_mnz = _mnz + _margin
                    # Element is "exterior" if any face within 5m of building boundary
                    _shell_clause = ("AND (r.minX < ? OR r.maxX > ? "
                                     "OR r.minY < ? OR r.maxY > ? "
                                     "OR r.maxZ > ? OR r.minZ < ?)")
                    _shell_params = (_inner_mnx, _inner_mxx,
                                     _inner_mny, _inner_mxy,
                                     _inner_mxz, _inner_mnz)

            _interior_classes = ('IfcFurnishingElement', 'IfcFurniture',
                                 'IfcSystemFurnitureElement')
            _interior_clause = f"AND m.ifc_class NOT IN ({','.join('?' * len(_interior_classes))})"

            rows = conn.execute(f"""
                SELECT m.guid, i.geometry_hash, m.material_rgba, m.element_name,
                       m.material_name, m.discipline, m.ifc_class
                FROM elements_meta m
                JOIN element_instances i ON m.guid = i.guid
                JOIN elements_rtree r ON r.id = m.rowid
                WHERE {bld_clause} i.geometry_hash IS NOT NULL
                  AND m.ifc_class != 'IfcOpeningElement'
                  {disc_clause}
                  {_interior_clause}
                  {_shell_clause}
                ORDER BY (r.maxX-r.minX)*(r.maxY-r.minY)*(r.maxZ-r.minZ) DESC
                LIMIT ? OFFSET ?
            """, bld_params + disc_params + _interior_classes + _shell_params + (batch, offset)).fetchall()

            elements = []
            unique_hashes = set()
            _merge_classes = {'IfcPlate', 'IfcCovering'}  # homogeneous roof tiles — merge
            for row in rows:
                guid, ghash, rgba, ename = row[0], row[1], row[2], row[3]
                mat_name, disc, ifc_class = row[4], row[5], row[6]
                if guid in bv._direct_stream_guids:
                    continue
                obj_name = f"{(ename or '')[:50]}_{guid[:8]}" if ename else guid[:12]
                elements.append((guid, ghash, rgba, ename, obj_name, mat_name, disc, ifc_class))
                unique_hashes.add(ghash)

            if not elements:
                conn.close()
                already = len(bv._direct_stream_buildings.get(bld, set()))
                bv._direct_stream_disc_phase[bld] = 'envelope_done'
                bv._direct_stream_active_bld = None
                _ds_log(f"[S198] §DS_ENVELOPE_DONE {bld} envelope={already} elements — holding")
                return 1.0

            # Transforms
            all_guids = [e[0] for e in elements]
            xform = {}
            for ci in range(0, len(all_guids), 999):
                chunk = all_guids[ci:ci+999]
                _ph2 = ','.join('?' * len(chunk))
                for r in conn.execute(f"""
                    SELECT guid, center_x, center_y, center_z,
                           rotation_x, rotation_y, rotation_z
                    FROM element_transforms WHERE guid IN ({_ph2})
                """, chunk).fetchall():
                    xform[r[0]] = r[1:]
            conn.close()

            ensure_meshes(list(unique_hashes), lib_db)
            styles = _load_surface_styles(db_path)

            ox = _off.x if _off else 0.0
            oy = _off.y if _off else 0.0
            oz = _off.z if _off else 0.0

            bld_col_label = _bld_label(bld)
            bld_col = _bpy.data.collections.get(bld_col_label)
            _new_bld_col = False
            if bld_col is None:
                bld_col = _bpy.data.collections.new(bld_col_label)
                _new_bld_col = True

            _disc_cols = {}
            _batch_cols = {}
            _new_disc_cols = []
            placed = 0

            def _env_get_col(disc_key):
                if disc_key not in _disc_cols:
                    _dc_label = f"{_bld_label(bld)}_{disc_key}"
                    _dc = _bpy.data.collections.get(_dc_label)
                    if _dc is None:
                        _dc = _bpy.data.collections.new(_dc_label)
                        _new_disc_cols.append(_dc)
                    _disc_cols[disc_key] = _dc
                    _bn = len(_dc.children)
                    _bc = _bpy.data.collections.new(f"DS_{bld}_{disc_key}_{_bn}")
                    _batch_cols[disc_key] = (_bc, 0)
                _bc, _bc_count = _batch_cols[disc_key]
                if _bc_count >= 1000:
                    _disc_cols[disc_key].children.link(_bc)
                    _bn = len(_disc_cols[disc_key].children)
                    _bc = _bpy.data.collections.new(f"DS_{bld}_{disc_key}_{_bn}")
                    _bc_count = 0
                    _batch_cols[disc_key] = (_bc, _bc_count)
                return _bc

            # S198: separate merge candidates (IfcPlate/IfcCovering) from individuals
            _to_merge = {}  # ifc_class → [elements]
            _individuals = []
            for el in elements:
                if el[7] in _merge_classes:  # ifc_class
                    _to_merge.setdefault(el[7], []).append(el)
                else:
                    _individuals.append(el)

            # Merge homogeneous roof groups (>20 same-class elements)
            for _mc, _group in _to_merge.items():
                if len(_group) > 20:
                    verts, faces, merged_guids = _merge_envelope_group(
                        _group, xform, ox, oy, oz)
                    if verts:
                        mesh_name = f"{_mc}_roof_merged"
                        merged_mesh = _bpy.data.meshes.new(mesh_name)
                        merged_mesh.from_pydata(verts, [], faces)
                        obj = _bpy.data.objects.new(mesh_name, merged_mesh)
                        disc_key = _group[0][6] or 'ARC'
                        col = _env_get_col(disc_key)
                        col.objects.link(obj)
                        apply_material(obj, _group[0][2], _group[0][5], _group[0][6], styles)
                        for mg in merged_guids:
                            bv._direct_stream_guids.add(mg)
                            bv._direct_stream_objects[mg] = obj
                            bv._direct_stream_buildings.setdefault(bld, set()).add(mg)
                        _dl = bv._direct_stream_disc_loaded.setdefault(bld, {})
                        _dl[disc_key] = _dl.get(disc_key, 0) + len(merged_guids)
                        _bc_cur, _bc_cnt = _batch_cols[disc_key]
                        _batch_cols[disc_key] = (_bc_cur, _bc_cnt + 1)
                        placed += 1
                        _ds_log(f"[S198] §DS_MERGE {bld} class={_mc} "
                                f"elements={len(merged_guids)} → 1 mesh")
                        continue
                # <20 or merge failed — stream individually
                _individuals.extend(_group)

            # Individual elements (full material + identity)
            for el in _individuals:
                guid, ghash, rgba, ename, obj_name, mat_name, disc = el[:7]
                mesh = _bpy.data.meshes.get(ghash)
                if not mesh:
                    continue
                tr = xform.get(guid)
                if not tr:
                    continue
                disc_key = disc or 'OTHER'
                col = _env_get_col(disc_key)
                obj = _bpy.data.objects.new(obj_name, mesh)
                col.objects.link(obj)
                apply_material(obj, rgba, mat_name, disc, styles)
                apply_transform(obj, tr, ox, oy, oz)
                bv._direct_stream_guids.add(guid)
                bv._direct_stream_objects[guid] = obj
                bv._direct_stream_buildings.setdefault(bld, set()).add(guid)
                _dl = bv._direct_stream_disc_loaded.setdefault(bld, {})
                _dl[disc_key] = _dl.get(disc_key, 0) + 1
                _bc_cur, _bc_cnt = _batch_cols[disc_key]
                _batch_cols[disc_key] = (_bc_cur, _bc_cnt + 1)
                placed += 1

            # Deferred linking
            for _dk, (_bc_final, _bc_cnt) in _batch_cols.items():
                if _bc_cnt > 0:
                    _disc_cols[_dk].children.link(_bc_final)
                else:
                    _bpy.data.collections.remove(_bc_final)
            for _ndc in _new_disc_cols:
                bld_col.children.link(_ndc)
            if _new_bld_col:
                _bpy.context.scene.collection.children.link(bld_col)

            # Advance offset — transition to envelope_done when exhausted
            _phase_offsets[_offset_key] = offset + batch
            _direct_stream_tick._phase_offsets = _phase_offsets

            elapsed_ms = (time.time() - t0) * 1000
            _direct_stream_tick._last_hashes_new = len(unique_hashes)
            _direct_stream_tick._last_tick_ms = elapsed_ms
            total = len(bv._direct_stream_guids)
            print(f"[S198] §DS_ENVELOPE {bld} batch={batch} placed={placed} "
                  f"total={total:,}/{bv._DIRECT_STREAM_BUDGET:,} tick_ms={elapsed_ms:.0f}ms")

        # ── SHELL / DETAIL phase (S195 logic) ──
        else:
            disc_clause = ""
            disc_params = ()
            if phase == 'shell':
                disc_clause = f"AND m.discipline IN ({','.join('?' * len(_shell))})"
                disc_params = _shell
            elif phase == 'detail':
                disc_clause = f"AND m.discipline NOT IN ({','.join('?' * len(_shell))})"
                disc_params = _shell

            rows = conn.execute(f"""
                SELECT m.guid, i.geometry_hash, m.material_rgba, m.element_name,
                       m.material_name, m.discipline
                FROM elements_meta m
                JOIN element_instances i ON m.guid = i.guid
                JOIN elements_rtree r ON r.id = m.rowid
                WHERE {bld_clause} i.geometry_hash IS NOT NULL
                  AND m.ifc_class != 'IfcOpeningElement'
                  {disc_clause}
                ORDER BY (r.maxX-r.minX)*(r.maxY-r.minY)*(r.maxZ-r.minZ) DESC
                LIMIT ? OFFSET ?
            """, bld_params + disc_params + (batch, offset)).fetchall()

            elements = []
            unique_hashes = set()
            for row in rows:
                guid, ghash, rgba, ename = row[0], row[1], row[2], row[3]
                mat_name, disc = row[4], row[5]
                if guid in bv._direct_stream_guids:
                    continue
                obj_name = f"{(ename or '')[:50]}_{guid[:8]}" if ename else guid[:12]
                elements.append((guid, ghash, rgba, ename, obj_name, mat_name, disc))
                unique_hashes.add(ghash)

            if not elements:
                conn.close()
                if phase == 'shell':
                    already = len(bv._direct_stream_buildings.get(bld, set()))
                    bv._direct_stream_disc_phase[bld] = 'shell_done'
                    bv._direct_stream_active_bld = None
                    print(f"[S195] §DS_SHELL_DONE {bld} arc_str={already:,} — releasing lock")
                else:
                    already = len(bv._direct_stream_buildings.get(bld, set()))
                    bv._direct_stream_disc_phase[bld] = 'done'
                    print(f"[S195] §DS_DETAIL_DONE {bld} elements={already:,}")
                return 1.0

            all_guids = [e[0] for e in elements]
            xform = {}
            for ci in range(0, len(all_guids), 999):
                chunk = all_guids[ci:ci+999]
                _ph2 = ','.join('?' * len(chunk))
                for r in conn.execute(f"""
                    SELECT guid, center_x, center_y, center_z,
                           rotation_x, rotation_y, rotation_z
                    FROM element_transforms WHERE guid IN ({_ph2})
                """, chunk).fetchall():
                    xform[r[0]] = r[1:]
            conn.close()

            ensure_meshes(list(unique_hashes), lib_db)
            styles = _load_surface_styles(db_path)

            bld_col_label = _bld_label(bld)
            bld_col = _bpy.data.collections.get(bld_col_label)
            _new_bld_col = False
            if bld_col is None:
                bld_col = _bpy.data.collections.new(bld_col_label)
                _new_bld_col = True

            _disc_cols = {}
            _batch_cols = {}
            _new_disc_cols = []

            ox = _off.x if _off else 0.0
            oy = _off.y if _off else 0.0
            oz = _off.z if _off else 0.0

            placed = 0
            for guid, ghash, rgba, ename, obj_name, mat_name, disc in elements:
                mesh = _bpy.data.meshes.get(ghash)
                if not mesh:
                    continue
                tr = xform.get(guid)
                if not tr:
                    continue
                disc_key = disc or 'OTHER'
                if disc_key not in _disc_cols:
                    _dc_label = f"{_bld_label(bld)}_{disc_key}"
                    _dc = _bpy.data.collections.get(_dc_label)
                    if _dc is None:
                        _dc = _bpy.data.collections.new(_dc_label)
                        _new_disc_cols.append(_dc)
                    _disc_cols[disc_key] = _dc
                    _bn = len(_dc.children)
                    _bc = _bpy.data.collections.new(f"DS_{bld}_{disc_key}_{_bn}")
                    _batch_cols[disc_key] = (_bc, 0)
                _bc, _bc_count = _batch_cols[disc_key]
                if _bc_count >= 1000:
                    _disc_cols[disc_key].children.link(_bc)
                    _bn = len(_disc_cols[disc_key].children)
                    _bc = _bpy.data.collections.new(f"DS_{bld}_{disc_key}_{_bn}")
                    _bc_count = 0
                _bc.objects.link(_bpy.data.objects.new(obj_name, mesh))
                obj = _bc.objects[-1]
                apply_material(obj, rgba, mat_name, disc, styles)
                apply_transform(obj, tr, ox, oy, oz)

                bv._direct_stream_guids.add(guid)
                bv._direct_stream_objects[guid] = obj
                bv._direct_stream_buildings.setdefault(bld, set()).add(guid)
                _dl = bv._direct_stream_disc_loaded.setdefault(bld, {})
                _dl[disc_key] = _dl.get(disc_key, 0) + 1
                _batch_cols[disc_key] = (_bc, _bc_count + 1)
                placed += 1

            for _dk, (_bc_final, _bc_cnt) in _batch_cols.items():
                if _bc_cnt > 0:
                    _disc_cols[_dk].children.link(_bc_final)
                else:
                    _bpy.data.collections.remove(_bc_final)
            for _ndc in _new_disc_cols:
                bld_col.children.link(_ndc)
            if _new_bld_col:
                _bpy.context.scene.collection.children.link(bld_col)

            _phase_offsets[_offset_key] = offset + batch
            _direct_stream_tick._phase_offsets = _phase_offsets

            elapsed_ms = (time.time() - t0) * 1000
            _direct_stream_tick._last_hashes_new = len(unique_hashes)
            _direct_stream_tick._last_tick_ms = elapsed_ms
            total = len(bv._direct_stream_guids)
            print(f"[S195] §DS_TICK {bld} phase={phase} batch={batch} placed={placed} "
                  f"total={total:,}/{bv._DIRECT_STREAM_BUDGET:,} "
                  f"hashes_unique={len(unique_hashes)} tick_ms={elapsed_ms:.0f}ms")

            if bv._direct_stream_auto_shred and elapsed_ms > bv._DIRECT_STREAM_LAG_TARGET:
                _streamed = list(bv._direct_stream_buildings.keys())
                if len(_streamed) > 1:
                    _farthest = None
                    _farthest_dist = 0
                    for _sb in _streamed:
                        if _sb == bld:
                            continue
                        _sc = bv._building_centres.get(_sb)
                        if _sc:
                            _sd = math.sqrt((cx-_sc[0])**2 + (cy-_sc[1])**2)
                            if _sd > _farthest_dist:
                                _farthest_dist = _sd
                                _farthest = _sb
                    if _farthest:
                        print(f"[S195] §AUTO_SHRED {_farthest} dist={_farthest_dist:.0f}m "
                              f"tick_ms={elapsed_ms:.0f}ms")
                        _direct_stream_remove_building(_farthest)

    except Exception as e:
        print(f"[S195] §DS_ERROR {e}")

    # S196: force viewport redraw so HUD stays in sync with streaming
    try:
        for _area in _bpy.context.screen.areas:
            if _area.type == 'VIEW_3D':
                _area.tag_redraw()
                break
    except Exception:
        pass

    return 1.0  # re-check every 1 second


class FedRTreeDirectStream(bpy.types.Operator):
    """S195 POC: Toggle direct DB streaming — tessellate from BLOBs, no .blend files."""
    bl_idname = "bim.fed_rtree_direct_stream"
    bl_label = "Direct Stream"
    bl_options = {'REGISTER'}

    def execute(self, context):
        from . import bbox_visualization as bv
        from pathlib import Path as _P
        import sqlite3

        # ── Bootstrap: resolve DB path (no Preview required) ──
        _db = bv._db_path_cache or ""
        if not _db:
            try:
                _db = context.scene.BIMFederationProperties.federation_database_path or ""
            except Exception:
                pass
            if _db:
                _db = bpy.path.abspath(_db)

        if not _db or not _P(_db).exists():
            self.report({'WARNING'}, "Set federation database path first")
            return {'CANCELLED'}

        # Cache DB path (same as Preview would)
        if not bv._db_path_cache:
            bv._db_path_cache = _db
            _ds_log(f"[S195] §BOOTSTRAP db_path={_db}")

        # ── Bootstrap: model offset from DB ──
        if bv._model_offset is None:
            bv._model_offset = bv.get_model_offset(_db)
            print(f"[S195] §BOOTSTRAP model_offset="
                  f"({bv._model_offset.x:.1f}, {bv._model_offset.y:.1f}, {bv._model_offset.z:.1f})"
                  if bv._model_offset else "[S195] §BOOTSTRAP model_offset=None")

        # ── Bootstrap: has_building_column ──
        if not bv._has_building_column:
            try:
                _conn = sqlite3.connect(_db)
                _cols = [r[1] for r in _conn.execute(
                    "PRAGMA table_info(elements_meta)").fetchall()]
                bv._has_building_column = 'building' in _cols
                _conn.close()
                print(f"[S195] §BOOTSTRAP has_building_col={bv._has_building_column}")
            except Exception:
                pass

        # ── Bootstrap: library DB ──
        if not bv._library_db_cache:
            for _anc in _P(_db).resolve().parents:
                _ldb = _anc / "library" / "component_library.db"
                if _ldb.exists():
                    bv._library_db_cache = str(_ldb)
                    print(f"[S195] §BOOTSTRAP library_db={_ldb.name}")
                    break
        if not bv._library_db_cache:
            self.report({'WARNING'}, "No component_library.db found")
            return {'CANCELLED'}

        # ── Bootstrap: building centres (STR/ARC bbox only) + element counts ──
        if not bv._building_centres:
            try:
                _conn = sqlite3.connect(_db)
                if bv._has_building_column:
                    # S197: centre from STR/ARC only — MEP/ELEC extend far beyond envelope
                    _rows = _conn.execute(
                        "SELECT m.building, COUNT(*), "
                        "  (MIN(r.minX)+MAX(r.maxX))/2, (MIN(r.minY)+MAX(r.maxY))/2, "
                        "  (MIN(r.minZ)+MAX(r.maxZ))/2 "
                        "FROM elements_rtree r JOIN elements_meta m ON r.id = m.rowid "
                        "WHERE m.discipline IN ('ARC','STR') "
                        "GROUP BY m.building"
                    ).fetchall()
                    for _bld, _cnt, _cx, _cy, _cz in _rows:
                        if _bld:
                            bv._building_centres[_bld] = (_cx, _cy, _cz)
                    # Element counts include ALL disciplines (for progress tracking)
                    _cnt_rows = _conn.execute(
                        "SELECT m.building, COUNT(*) "
                        "FROM elements_meta m JOIN element_instances i ON m.guid = i.guid "
                        "WHERE i.geometry_hash IS NOT NULL "
                        "  AND m.ifc_class != 'IfcOpeningElement' "
                        "GROUP BY m.building"
                    ).fetchall()
                    for _bld, _cnt in _cnt_rows:
                        if _bld:
                            bv._building_element_counts[_bld] = _cnt
                else:
                    _bld_name = _P(_db).stem.replace('_extracted', '')
                    _row = _conn.execute(
                        "SELECT COUNT(*), "
                        "  (MIN(r.minX)+MAX(r.maxX))/2, (MIN(r.minY)+MAX(r.maxY))/2, "
                        "  (MIN(r.minZ)+MAX(r.maxZ))/2 "
                        "FROM elements_rtree r JOIN elements_meta m ON r.id = m.rowid "
                        "WHERE m.discipline IN ('ARC','STR')"
                    ).fetchone()
                    if _row and _row[0]:
                        bv._building_centres[_bld_name] = (_row[1], _row[2], _row[3])
                    _cnt_row = _conn.execute(
                        "SELECT COUNT(*) FROM elements_meta m "
                        "JOIN element_instances i ON m.guid = i.guid "
                        "WHERE i.geometry_hash IS NOT NULL "
                        "  AND m.ifc_class != 'IfcOpeningElement'"
                    ).fetchone()
                    if _cnt_row:
                        bv._building_element_counts[_bld_name] = _cnt_row[0]
                _conn.close()
                # S198: query full ARC/STR bboxes for camera-inside-bbox check
                if bv._has_building_column:
                    _bbox_rows = _conn.execute(
                        "SELECT m.building, MIN(r.minX), MAX(r.maxX), "
                        "  MIN(r.minY), MAX(r.maxY), MIN(r.minZ), MAX(r.maxZ) "
                        "FROM elements_rtree r JOIN elements_meta m ON r.id = m.rowid "
                        "WHERE m.discipline IN ('ARC','STR') "
                        "GROUP BY m.building"
                    ).fetchall()
                    for _bld, _mnx, _mxx, _mny, _mxy, _mnz, _mxz in _bbox_rows:
                        if _bld:
                            bv._direct_stream_bld_bbox[_bld] = (
                                _mnx, _mxx, _mny, _mxy, _mnz, _mxz)
                else:
                    _bb_row = _conn.execute(
                        "SELECT MIN(r.minX), MAX(r.maxX), "
                        "  MIN(r.minY), MAX(r.maxY), MIN(r.minZ), MAX(r.maxZ) "
                        "FROM elements_rtree r JOIN elements_meta m ON r.id = m.rowid "
                        "WHERE m.discipline IN ('ARC','STR')"
                    ).fetchone()
                    if _bb_row and _bb_row[0]:
                        bv._direct_stream_bld_bbox[_bld_name] = tuple(_bb_row)
                print(f"[S195] §BOOTSTRAP centres={len(bv._building_centres)} "
                      f"bboxes={len(bv._direct_stream_bld_bbox)} "
                      f"total_elements={sum(bv._building_element_counts.values()):,}")
            except Exception as _e:
                print(f"[S195] §BOOTSTRAP WARN: {_e}")

        if not bv._building_centres:
            self.report({'WARNING'}, "No buildings found in DB")
            return {'CANCELLED'}

        # ── Bootstrap: search suggestions for RTree Inspector building list ──
        if not bv._search_suggestions:
            bv._populate_search_suggestions(_db)

        bv._direct_stream_enabled = not bv._direct_stream_enabled

        if bv._direct_stream_enabled:
            # Register eye-tracking draw handler if not already running
            if bv._dlod_draw_handler is None:
                bv._dlod_draw_handler = bpy.types.SpaceView3D.draw_handler_add(
                    bv._dlod_track_eye, (), 'WINDOW', 'POST_VIEW')
            if not bpy.app.timers.is_registered(_direct_stream_tick):
                # S197: fresh log on each stream session
                try:
                    with open(_DS_LOG, 'w') as f:
                        f.write(f"# Direct Stream Log — {__import__('datetime').datetime.now().isoformat()}\n")
                except Exception:
                    pass
                bpy.app.timers.register(_direct_stream_tick, first_interval=1.0)
            # S198: reset autopilot for cinematic fly-in
            import time as _t
            global _ds_start_time, _ds_autopilot_fired
            _ds_start_time = _t.time()
            _ds_autopilot_fired = False
            # Auto-enable HUD for disc bar feedback
            from . import progress_hud
            if not progress_hud.is_hud_enabled():
                progress_hud.enable_hud()
            # S197: set clip_end to 5km on startup for city-scale viewing
            for _area in bpy.context.screen.areas:
                if _area.type == 'VIEW_3D':
                    _area.spaces[0].clip_end = 5000
                    _area.tag_redraw()
                    break
            _total = sum(bv._building_element_counts.values())
            print(f"[S195] §DS_ON radius={bv._DIRECT_STREAM_RADIUS}m "
                  f"buildings={len(bv._building_centres)} "
                  f"elements_in_db={_total:,} budget={bv._DIRECT_STREAM_BUDGET:,}")
            self.report({'INFO'}, f"Direct Stream ON — {len(bv._building_centres)} buildings, "
                        f"{bv._DIRECT_STREAM_RADIUS}m radius")
        else:
            if bpy.app.timers.is_registered(_direct_stream_tick):
                bpy.app.timers.unregister(_direct_stream_tick)
            # S197: reset settle state
            bv._direct_stream_cam_last = None
            bv._direct_stream_cam_still_t = 0.0
            count = len(bv._direct_stream_guids)
            print(f"[S195] §DS_OFF streamed={count:,}")
            self.report({'INFO'}, f"Direct Stream OFF — {count:,} elements remain in scene")

        return {'FINISHED'}


class FedRTreeDirectStreamClear(bpy.types.Operator):
    """S195: Clear all direct-streamed objects from the scene."""
    bl_idname = "bim.fed_rtree_direct_stream_clear"
    bl_label = "Clear Direct Stream"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from . import bbox_visualization as bv

        for bld in list(bv._direct_stream_buildings.keys()):
            _direct_stream_remove_building(bld)
        bv._direct_stream_guids.clear()
        bv._direct_stream_objects.clear()
        bv._direct_stream_buildings.clear()
        bv._direct_stream_disc_phase.clear()
        bv._direct_stream_active_bld = None
        self.report({'INFO'}, "Direct Stream cleared")
        return {'FINISHED'}


class FedRTreeCinematic(bpy.types.Operator):
    """S198: One-click cinematic scene — HDRI sky, sun, ground, EEVEE bloom."""
    bl_idname = "bim.fed_rtree_cinematic"
    bl_label = "Cinematic"
    bl_description = "Add sky, sun, ground plane, and EEVEE effects for presentation-ready viewport"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import bpy as _bpy
        from . import bbox_visualization as bv
        import math

        scene = context.scene

        # ── 1. EEVEE render engine ──
        scene.render.engine = 'BLENDER_EEVEE'
        # Enable effects
        try:
            scene.eevee.use_bloom = True
            scene.eevee.bloom_intensity = 0.05
            scene.eevee.bloom_threshold = 0.8
        except AttributeError:
            pass  # Blender 5.0+ handles bloom differently
        try:
            scene.eevee.use_gtao = True  # ambient occlusion
            scene.eevee.gtao_distance = 5.0
        except AttributeError:
            pass
        try:
            scene.eevee.shadow_cube_size = '512'
        except AttributeError:
            pass  # Blender 5.0 removed this setting

        # ── 2. Nishita sky (procedural — no HDRI file needed) ──
        world = scene.world
        if not world:
            world = _bpy.data.worlds.new("DS_World")
            scene.world = world
        world.use_nodes = True
        nodes = world.node_tree.nodes
        links = world.node_tree.links
        nodes.clear()
        out_n = nodes.new('ShaderNodeOutputWorld')
        bg_n = nodes.new('ShaderNodeBackground')
        sky_n = nodes.new('ShaderNodeTexSky')
        sky_n.sky_type = 'HOSEK_WILKIE'
        sky_n.sun_direction = (0.4, -0.5, 0.76)  # higher sun — softer shadows
        bg_n.inputs['Strength'].default_value = 0.8  # subtle sky, not overpowering
        links.new(sky_n.outputs['Color'], bg_n.inputs['Color'])
        links.new(bg_n.outputs['Background'], out_n.inputs['Surface'])

        # ── 3. Sun lamp (matching sky direction) ──
        sun_name = "DS_Sun"
        sun_obj = _bpy.data.objects.get(sun_name)
        if not sun_obj:
            sun_data = _bpy.data.lights.new(sun_name, 'SUN')
            sun_obj = _bpy.data.objects.new(sun_name, sun_data)
            context.scene.collection.objects.link(sun_obj)
        sun_obj.data.energy = 1.2  # soft — light shadows, not black
        sun_obj.data.color = (0.95, 0.95, 1.0)  # cool daylight
        sun_obj.data.angle = math.radians(5)  # spread sun disc — softer shadow edges
        sun_obj.rotation_euler = (math.radians(50), 0, math.radians(200))

        # ── 4. Ground plane for shadow catching ──
        ground_name = "DS_Ground"
        ground_obj = _bpy.data.objects.get(ground_name)
        if not ground_obj:
            _extent = 500
            if bv._building_centres:
                _all_x = [c[0] for c in bv._building_centres.values()]
                _all_y = [c[1] for c in bv._building_centres.values()]
                _extent = max(max(_all_x) - min(_all_x),
                              max(_all_y) - min(_all_y)) + 200
            _bpy.ops.mesh.primitive_plane_add(size=_extent * 2)
            ground_obj = context.active_object
            ground_obj.name = ground_name
            if bv._building_centres and bv._model_offset:
                _avg_x = sum(c[0] for c in bv._building_centres.values()) / len(bv._building_centres)
                _avg_y = sum(c[1] for c in bv._building_centres.values()) / len(bv._building_centres)
                _off = bv._model_offset
                ground_obj.location = (_avg_x - _off.x, _avg_y - _off.y, -0.1 - _off.z)
            # Deselect so yellow selection box doesn't show
            ground_obj.select_set(False)
            context.view_layer.objects.active = None
        # Patchy dark earth — noise texture into ColorRamp (green↔brown)
        mat_name = "DS_Ground_Mat"
        mat = _bpy.data.materials.get(mat_name)
        if not mat:
            mat = _bpy.data.materials.new(mat_name)
            mat.use_nodes = True
            _mn = mat.node_tree.nodes
            _ml = mat.node_tree.links
            _mn.clear()
            out_m = _mn.new('ShaderNodeOutputMaterial')
            bsdf = _mn.new('ShaderNodeBsdfPrincipled')
            bsdf.inputs['Roughness'].default_value = 0.95
            # Noise → ColorRamp (dark green to dark brown)
            noise = _mn.new('ShaderNodeTexNoise')
            noise.inputs['Scale'].default_value = 0.4
            noise.inputs['Detail'].default_value = 6.0
            noise.inputs['Roughness'].default_value = 0.8
            ramp = _mn.new('ShaderNodeValToRGB')
            ramp.color_ramp.elements[0].position = 0.3
            ramp.color_ramp.elements[0].color = (0.12, 0.18, 0.08, 1.0)  # dark moss
            ramp.color_ramp.elements[1].position = 0.7
            ramp.color_ramp.elements[1].color = (0.22, 0.15, 0.08, 1.0)  # dark earth
            _ml.new(noise.outputs['Fac'], ramp.inputs['Fac'])
            _ml.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
            _ml.new(bsdf.outputs['BSDF'], out_m.inputs['Surface'])
        if not ground_obj.data.materials:
            ground_obj.data.materials.append(mat)
        else:
            ground_obj.data.materials[0] = mat

        # ── 5. Switch viewport to Material Preview ��─
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces[0]
                space.shading.type = 'MATERIAL'
                space.shading.use_scene_world = True
                space.shading.use_scene_lights = True
                area.tag_redraw()
                break

        self.report({'INFO'}, "Cinematic ON — sky, sun, ground, EEVEE bloom")
        print("[S198] §CINEMATIC sky=Nishita sun=35° ground=plane eevee=bloom+ao")
        return {'FINISHED'}


class FedRTreeAutoShredToggle(bpy.types.Operator):
    """S195: Toggle auto-shred — automatically remove furthest building when lagging."""
    bl_idname = "bim.fed_rtree_auto_shred_toggle"
    bl_label = "Auto-Shred"
    bl_description = (
        "Auto-shred: when viewport lags, automatically shred the furthest\n"
        "streamed building to free up budget. Budget self-tunes to your hardware."
    )
    bl_options = {'REGISTER'}

    def execute(self, context):
        from . import bbox_visualization as bv
        bv._direct_stream_auto_shred = not bv._direct_stream_auto_shred
        state = "ON" if bv._direct_stream_auto_shred else "OFF"
        print(f"[S195] §AUTO_SHRED {state} budget={bv._DIRECT_STREAM_BUDGET:,}")
        self.report({'INFO'}, f"Auto-Shred {state}")
        return {'FINISHED'}
