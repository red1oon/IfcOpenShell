"""
Federation Progress HUD
========================

Floating GPU-drawn overlay showing discipline load progress as colored bars.
Companion to discipline_legend.py — same technique (gpu + blf in POST_PIXEL).

Visual design:
- Glass-panel background with subtle border glow
- Gradient-filled bars: deep red (0%) → amber → cyan → bright blue (100%)
- Discipline accent stripe on each bar (per-discipline color)
- Pulsing glow on actively loading disciplines
- Total progress arc at top
- BACKEND status with animated blue pulse
"""

import bpy
import blf
import gpu
import time as _time
import math
from gpu_extras.batch import batch_for_shader
from .bbox_visualization import DISCIPLINE_COLORS, get_discipline_color

# Global state
_hud_handler = None
_is_enabled = False
_last_loaded = {}  # disc → loaded count last frame (detect activity)
_active_discs = set()  # disciplines that changed recently (pulse effect)
_active_disc_time = {}  # disc → timestamp of last change
_hud_offset_x = 0  # user drag offset from default position
_hud_offset_y = 0
_link_success_time = 0  # timestamp when linking completed (show success for 5s)
_link_start_time = 0   # timestamp when linking started (for elapsed display)
_link_file_count = 0   # number of files being linked
_link_total_mb = 0     # total MB being linked (for ETA)



def _get_progress_data():
    """Gather discipline progress from bbox_visualization state.
    S195: also shows DirectStream progress when no active RTree building.
    S196: suppress stale disc bars during BAKE ALL (no active building)."""
    from . import bbox_visualization as bv

    disc_counts = bv._building_disc_counts

    # S196: during BAKE ALL, stale disc_counts from a previous session are misleading
    # Only show disc bars when there's an active building context to match them
    if disc_counts and not bv._active_building and (bv._baking_buildings or bv._bake_queue):
        disc_counts = {}

    # S195: If no RTree active building but DirectStream is active or has data, show DS progress
    # S198: show nearest building to camera — streamed or just in-sight from DB totals
    if not disc_counts and (bv._direct_stream_enabled or bv._direct_stream_buildings or bv._building_centres):
        _ds_bld = bv._direct_stream_active_bld
        if not _ds_bld and bv._dlod_eye_pos:
            import math as _m
            _cam = bv._dlod_eye_pos
            _off = bv._model_offset
            _cx = _cam[0] + (_off.x if _off else 0.0)
            _cy = _cam[1] + (_off.y if _off else 0.0)
            _cz = _cam[2] + (_off.z if _off else 0.0)
            _nearest_dist = float('inf')
            # First try nearest streamed building
            for _sb in bv._direct_stream_buildings:
                _sc = bv._building_centres.get(_sb)
                if _sc:
                    _sd = _m.sqrt((_cx-_sc[0])**2 + (_cy-_sc[1])**2)
                    if _sd < _nearest_dist:
                        _nearest_dist = _sd
                        _ds_bld = _sb
            # S198: if no streamed building nearby, show nearest ANY building in sight
            if not _ds_bld or _nearest_dist > 300:
                for _sb, _sc in bv._building_centres.items():
                    _sd = _m.sqrt((_cx-_sc[0])**2 + (_cy-_sc[1])**2)
                    if _sd < _nearest_dist:
                        _nearest_dist = _sd
                        _ds_bld = _sb
        if not _ds_bld:
            _ds_bld = bv._direct_stream_last_bld
        # S198: log nearest building pick (throttled — once per building change)
        if _ds_bld and _ds_bld != getattr(_get_progress_data, '_last_hud_bld', None):
            _get_progress_data._last_hud_bld = _ds_bld
            _cached = _ds_bld in bv._direct_stream_disc_totals
            print(f"[S198] §HUD_PICK {_ds_bld} cached={_cached} "
                  f"streamed={_ds_bld in bv._direct_stream_buildings} "
                  f"enabled={bv._direct_stream_enabled}")
        if _ds_bld:
            disc_counts = bv._direct_stream_disc_totals.get(_ds_bld, {})
            # S198: query disc totals on-demand for buildings not yet streamed
            if not disc_counts and bv._db_path_cache:
                try:
                    import sqlite3 as _sq
                    _dc = _sq.connect(bv._db_path_cache)
                    _bc = "m.building = ? AND" if bv._has_building_column else ""
                    _bp = (_ds_bld,) if bv._has_building_column else ()
                    _dr = _dc.execute(f"""
                        SELECT m.discipline, COUNT(*)
                        FROM elements_meta m
                        JOIN element_instances i ON m.guid = i.guid
                        WHERE {_bc} i.geometry_hash IS NOT NULL
                          AND m.ifc_class != 'IfcOpeningElement'
                        GROUP BY m.discipline
                    """, _bp).fetchall()
                    disc_counts = {d: c for d, c in _dr}
                    bv._direct_stream_disc_totals[_ds_bld] = disc_counts
                    _dc.close()
                    _disc_str = ' '.join(f"{d}={c:,}" for d, c in sorted(disc_counts.items()))
                    print(f"[S198] §HUD_DISC_QUERY {_ds_bld} [{_disc_str}]")
                except Exception as _e:
                    print(f"[S198] §HUD_DISC_QUERY FAIL {_ds_bld}: {_e}")
            loaded_per_disc = bv._direct_stream_disc_loaded.get(_ds_bld, {})
            # S196: snap to 100% when building phase is done
            _phase = bv._direct_stream_disc_phase.get(_ds_bld)
            _is_done = _phase in ('done', 'shell_done', 'envelope_done')
            total_count = sum(disc_counts.values())
            total_loaded = sum(loaded_per_disc.values())
            rows = []
            for disc, cnt in disc_counts.items():
                if cnt == 0:
                    continue
                loaded = loaded_per_disc.get(disc, 0)
                # When done, use actual loaded as the denominator (skip gap)
                if _is_done and loaded > 0:
                    pct = 1.0
                else:
                    pct = min(loaded / cnt, 1.0) if cnt > 0 else 0.0
                rows.append((disc, cnt, loaded, pct))
            if _is_done:
                total_loaded = total_count  # title shows ✓
            rows.sort(key=lambda r: r[1], reverse=True)
            # Inject building name for title
            _get_progress_data._ds_building = _ds_bld
            return rows, total_count, total_loaded

    _get_progress_data._ds_building = None

    if not disc_counts:
        return [], 0, 0

    _baked_col = bpy.data.collections.get(f"Baked_{bv._active_building}")
    _is_baked = _baked_col is not None
    # Also treat as fully loaded if bake is done (pending link on next Preview)
    _bake_done = bv._active_building in bv._bake_done

    loaded_per_disc = {}
    if _is_baked or _bake_done:
        loaded_per_disc = dict(disc_counts)
    else:
        for lbl, obj_names in bv._loaded_collections.items():
            if bv._active_building and bv._active_building in lbl:
                for d_name in disc_counts:
                    if lbl.endswith(f'_{d_name}') or f'_{d_name}_' in lbl:
                        loaded_per_disc[d_name] = loaded_per_disc.get(d_name, 0) + len(obj_names)

    total_count = sum(disc_counts.values())
    total_loaded = sum(loaded_per_disc.values())

    rows = []
    for disc, cnt in disc_counts.items():
        if cnt == 0:
            continue
        loaded = loaded_per_disc.get(disc, 0)
        pct = min(loaded / cnt, 1.0) if cnt > 0 else 0.0
        rows.append((disc, cnt, loaded, pct))

    rows.sort(key=lambda r: r[1], reverse=True)
    return rows, total_count, total_loaded

_get_progress_data._ds_building = None


def _grad_color(pct):
    """Multi-stop gradient: red → amber → cyan → bright blue.
    0.00 → (0.85, 0.15, 0.10)  deep red
    0.25 → (0.95, 0.60, 0.10)  amber
    0.50 → (0.20, 0.80, 0.80)  cyan
    0.75 → (0.15, 0.50, 0.95)  blue
    1.00 → (0.30, 0.70, 1.00)  bright blue
    """
    stops = [
        (0.00, (0.85, 0.15, 0.10)),
        (0.25, (0.95, 0.60, 0.10)),
        (0.50, (0.20, 0.80, 0.80)),
        (0.75, (0.15, 0.50, 0.95)),
        (1.00, (0.30, 0.70, 1.00)),
    ]
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if pct <= t1:
            f = (pct - t0) / (t1 - t0) if t1 > t0 else 0
            return (
                c0[0] + (c1[0] - c0[0]) * f,
                c0[1] + (c1[1] - c0[1]) * f,
                c0[2] + (c1[2] - c0[2]) * f,
            )
    return stops[-1][1]


def _draw_rect(shader, x, y, w, h, color):
    """Draw a filled rectangle."""
    verts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    batch = batch_for_shader(shader, 'TRI_FAN', {"pos": verts})
    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


def _draw_gradient_bar(shader, x, y, w, h, pct, segments=12):
    """Draw a bar with horizontal gradient fill based on progress.
    The gradient runs across the filled portion, showing the color ramp."""
    if pct <= 0:
        return
    fill_w = max(int(w * pct), 2)
    seg_w = fill_w / segments
    for i in range(segments):
        sx = x + i * seg_w
        sw = seg_w if i < segments - 1 else (fill_w - i * seg_w)
        # Color at this segment position in the overall gradient
        seg_pct = (i + 0.5) / segments * pct
        r, g, b = _grad_color(seg_pct)
        _draw_rect(shader, sx, y, sw, h, (r, g, b, 0.92))


def draw_progress_hud():
    """Draw callback — vibrant colored discipline progress bars in viewport."""
    global _last_loaded, _active_discs, _active_disc_time

    if not _is_enabled:
        return

    rows, total_count, total_loaded = _get_progress_data()

    from . import bbox_visualization as bv

    # S195: show HUD when streaming, baking, or streamed buildings exist
    _has_ds_data = bool(bv._direct_stream_buildings)
    _has_bake_data = bool(bv._baking_buildings or bv._bake_queue or bv._bake_done)
    if not rows and not bv._direct_stream_enabled and not _has_ds_data and not _has_bake_data:
        return
    if not rows:
        rows = []
        total_count = 0
        total_loaded = 0

    now = _time.time()
    region = bpy.context.region
    font_id = 0
    bar_height = 20
    bar_max_width = 180
    row_spacing = 6
    label_width = 55
    count_width = 90
    padding = 14
    accent_width = 4  # discipline color stripe

    n_rows = len(rows)
    # Extra space: baking status (~24 per building), overnight (~20), status line (~30)
    _extra = 0
    if bv._baking_buildings:
        _extra += len(bv._baking_buildings) * 24
    if bv._overnight_running:
        _extra += 20
    _extra += 30  # bottom status line (always reserve)
    panel_h = n_rows * (bar_height + row_spacing) + 65 + _extra
    panel_w = label_width + bar_max_width + count_width + padding * 2

    x0 = 24 + _hud_offset_x
    y0 = 70 + panel_h + _hud_offset_y

    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    gpu.state.blend_set('ALPHA')

    # ── Clean panel background ──
    _draw_rect(shader, x0 - padding, y0 - panel_h - padding,
               panel_w, panel_h + padding * 2,
               (0.08, 0.08, 0.12, 0.88))

    # ── Title — building name + status in brackets ──
    building = bv._active_building or _get_progress_data._ds_building or "Building"
    total_pct = (total_loaded / total_count * 100) if total_count > 0 else 0

    _cx = x0 + (panel_w - padding * 2) // 2  # center x

    # S196: during BAKE ALL, show bake progress as title instead of stale building name
    _n_baking = len(bv._baking_buildings)
    _n_done = len(bv._bake_done)
    _n_queued = len(bv._bake_queue)
    if _n_baking > 0 or (_n_queued > 0 and _n_done > 0):
        _n_total_bake = _n_baking + _n_done + _n_queued
        _title = f"\u26a1 Baking {_n_done}/{_n_total_bake}"
    elif _n_done > 0 and not bv._direct_stream_enabled and not total_count:
        _title = f"\u2713 {_n_done} Buildings Baked"
    elif total_loaded > 0 and total_pct < 100:
        _title = f"{building} ({total_pct:.0f}%)"
    elif total_pct >= 100:
        _title = f"{building} \u2713"
    else:
        _title = f"{building} ({total_count:,})"

    blf.size(font_id, 16)
    _tw = blf.dimensions(font_id, _title)[0]
    blf.position(font_id, _cx - _tw / 2, y0 - 4, 0)
    if _n_baking > 0 or _n_queued > 0:
        pulse = 0.6 + 0.4 * math.sin(now * 3)
        blf.color(font_id, 0.3 * pulse, 0.55 * pulse, 1.0 * pulse, 1.0)
    elif _n_done > 0 and not total_count:
        pulse = 0.7 + 0.3 * math.sin(now * 2)
        blf.color(font_id, 0.1, 1.0 * pulse, 0.35, 1.0)
    elif total_pct >= 100:
        pulse = 0.7 + 0.3 * math.sin(now * 2)
        blf.color(font_id, 0.3 * pulse, 0.7 * pulse, 1.0 * pulse, 1.0)
    elif total_loaded > 0:
        blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
    else:
        blf.color(font_id, 0.7, 0.7, 0.8, 0.9)
    blf.draw(font_id, _title)

    # ── Backend bake status (above bars when active) ──
    import time as _bake_time
    y_cursor = y0 - 42
    if bv._baking_buildings:
        for _bld, _info in bv._baking_buildings.items():
            _elapsed = _bake_time.time() - _info.get('start_time', _bake_time.time())
            _eta_total = _info.get('offline_eta', 0)
            _remaining = max(_eta_total - _elapsed, 0)
            _bake_pct = min(_elapsed / _eta_total, 1.0) if _eta_total > 0 else 0

            pulse = 0.6 + 0.4 * math.sin(now * 3)
            blf.position(font_id, x0, y_cursor, 0)
            blf.size(font_id, 11)
            blf.color(font_id, 0.3 * pulse, 0.55 * pulse, 1.0 * pulse, 1.0)
            if _remaining > 0:
                _r_txt = f"{int(_remaining)}s" if _remaining < 120 else f"{int(_remaining/60)}m"
                blf.draw(font_id, f"\u26a1 {_bld} baking ~{_r_txt}")
            else:
                blf.draw(font_id, f"\u23f3 {_bld} finishing...")

            # Bake progress bar
            y_cursor -= 14
            _bake_bar_w = panel_w - padding * 2
            _draw_rect(shader, x0, y_cursor, _bake_bar_w, 5,
                       (0.2, 0.2, 0.25, 0.6))
            if _bake_pct > 0:
                _fill = max(int(_bake_bar_w * _bake_pct), 2)
                _draw_rect(shader, x0, y_cursor, _fill, 5,
                           (0.3 * pulse, 0.55 * pulse, 1.0 * pulse, 0.9))
            y_cursor -= 10

    # ── S196: During BAKE ALL, show total elements progress bar instead of disc bars ──
    if not rows and (_n_baking > 0 or _n_queued > 0 or (_n_done > 0 and not bv._direct_stream_enabled)):
        _total_db = sum(bv._building_element_counts.values()) if bv._building_element_counts else 0
        _baked_elements = sum(
            bv._building_element_counts.get(b, 0) for b in bv._bake_done
        )
        # Also count currently baking buildings (partial credit)
        for _bb in bv._baking_buildings:
            _baked_elements += bv._building_element_counts.get(_bb, 0) // 2

        if _total_db > 0:
            _elem_pct = min(_baked_elements / _total_db, 1.0)
            _prog_bar_w = panel_w - padding * 2

            # Total progress bar — full width
            _draw_rect(shader, x0, y_cursor - 22, _prog_bar_w, 18,
                       (0.12, 0.12, 0.18, 0.85))
            # Border
            _draw_rect(shader, x0, y_cursor - 22,
                       _prog_bar_w, 1, (0.3, 0.4, 0.7, 0.5))  # bottom
            _draw_rect(shader, x0, y_cursor - 5,
                       _prog_bar_w, 1, (0.3, 0.4, 0.7, 0.5))  # top
            _draw_rect(shader, x0 + _prog_bar_w - 1, y_cursor - 22,
                       1, 18, (0.3, 0.4, 0.7, 0.5))  # right

            if _elem_pct > 0:
                pulse = 0.7 + 0.3 * math.sin(now * 3)
                _fill_w = max(int(_prog_bar_w * _elem_pct), 2)
                _draw_rect(shader, x0, y_cursor - 22, _fill_w, 18,
                           (0.15 * pulse, 0.4 * pulse, 0.9 * pulse, 0.85))

            # Label: "245,000 / 1,063,911 elements"
            blf.size(font_id, 12)
            _elem_txt = f"{_baked_elements:,} / {_total_db:,} elements"
            _etw = blf.dimensions(font_id, _elem_txt)[0]
            blf.position(font_id, x0 + (_prog_bar_w - _etw) / 2, y_cursor - 18, 0)
            blf.color(font_id, 0.9, 0.95, 1.0, 0.95)
            blf.draw(font_id, _elem_txt)

            y_cursor -= 30

    # ── Discipline bars ──
    if not rows:
        max_count = 0
    else:
        max_count = max(r[1] for r in rows)

    # Detect active loading (for pulse effect)
    for disc, cnt, loaded, pct in rows:
        prev = _last_loaded.get(disc, 0)
        if loaded > prev:
            _active_disc_time[disc] = now
        _last_loaded[disc] = loaded

    for disc, cnt, loaded, pct in rows:
        bar_w = max(int(bar_max_width * cnt / max_count), 8)

        dc = get_discipline_color(disc)
        dr, dg, db = dc[0], dc[1], dc[2]

        # Accent stripe (left edge)
        _draw_rect(shader, x0 + label_width - accent_width - 2, y_cursor - bar_height,
                   accent_width, bar_height, (dr, dg, db, 0.9))

        # S196: darker background with visible disc-tinted outline (shows total capacity)
        _draw_rect(shader, x0 + label_width, y_cursor - bar_height,
                   bar_w, bar_height, (dr * 0.12, dg * 0.12, db * 0.12, 0.85))
        # Border — thin outline in disc color so max extent is always visible
        _border_a = 0.5
        _draw_rect(shader, x0 + label_width, y_cursor - bar_height,
                   bar_w, 1, (dr * 0.5, dg * 0.5, db * 0.5, _border_a))  # bottom
        _draw_rect(shader, x0 + label_width, y_cursor - 1,
                   bar_w, 1, (dr * 0.5, dg * 0.5, db * 0.5, _border_a))  # top
        _draw_rect(shader, x0 + label_width + bar_w - 1, y_cursor - bar_height,
                   1, bar_height, (dr * 0.5, dg * 0.5, db * 0.5, _border_a))  # right edge

        # Bright fill — progress pushing out
        fill_w = 0
        if pct > 0:
            fill_w = max(int(bar_w * pct), 2)
            _draw_rect(shader, x0 + label_width, y_cursor - bar_height,
                       fill_w, bar_height, (dr, dg, db, 0.95))

            # Pulse edge at leading front
            last_change = _active_disc_time.get(disc, 0)
            age = now - last_change
            if age < 1.5:
                glow_alpha = 0.6 * (1.0 - age / 1.5)
                _draw_rect(shader, x0 + label_width + fill_w - 2, y_cursor - bar_height,
                           3, bar_height, (1.0, 1.0, 1.0, glow_alpha))

        # Discipline label — left
        blf.position(font_id, x0, y_cursor - bar_height + 5, 0)
        blf.size(font_id, 11)
        blf.color(font_id, dr, dg, db, 1.0)
        blf.draw(font_id, disc)

        # Moving number — rides the leading edge of the bar
        blf.size(font_id, 11)
        if loaded > 0:
            _num_txt = f"{loaded:,}"
            blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
            # Position at the right edge of the fill
            _num_x = x0 + label_width + fill_w + 4
        else:
            _num_txt = f"{cnt:,}"
            blf.color(font_id, dr * 0.5, dg * 0.5, db * 0.5, 0.7)
            # Position at end of dull bar
            _num_x = x0 + label_width + bar_w + 4
        blf.position(font_id, _num_x, y_cursor - bar_height + 5, 0)
        blf.draw(font_id, _num_txt)

        y_cursor -= (bar_height + row_spacing)

    # ── Status line (bottom, centered in remaining space) ──
    _panel_bottom = y0 - panel_h
    y_cursor = _panel_bottom + 8  # 8px up from panel bottom edge
    _status_txt = None
    _status_color = None

    if bv._linking_active:
        pulse = 0.4 + 0.6 * abs(math.sin(now * 4))
        # ETA: ~1s per 15MB
        _eta_s = max((_link_total_mb / 15.0) - (now - _link_start_time), 0) if _link_start_time else 0
        _eta_txt = f" ~{int(_eta_s)}s" if _eta_s > 1 else ""
        _status_txt = f"LINKING \u2014 DO NOT CLOSE{_eta_txt}"
        _status_color = (1.0 * pulse, 0.15 * pulse, 0.05, 1.0)
    elif _link_success_time and (now - _link_success_time) < 5.0:
        pulse = 0.8 + 0.2 * math.sin(now * 2)
        _status_txt = "\u2713 LINKED SUCCESS"
        _status_color = (0.1, 1.0 * pulse, 0.3, 1.0)
    elif bv._overnight_running:
        pulse = 0.7 + 0.3 * math.sin(now * 3)
        # Countdown from overnight total
        _ov_pct = bv._overnight_placed / max(bv._overnight_total, 1)
        _ov_elapsed = now - _link_start_time if _link_start_time and bv._overnight_running else 0
        if _ov_pct > 0.05 and _ov_elapsed > 5:
            _ov_remaining = _ov_elapsed / _ov_pct * (1 - _ov_pct)
            if _ov_remaining < 120:
                _ov_eta = f" ~{int(_ov_remaining)}s"
            else:
                _ov_eta = f" ~{int(_ov_remaining/60)}m"
        else:
            _ov_eta = ""
        _status_txt = f"OVERNIGHT{_ov_eta}"
        _status_color = (1.0 * pulse, 0.9 * pulse, 0.1, 1.0)
    elif bv._baking_buildings:
        pulse = 0.7 + 0.3 * math.sin(now * 3)
        # Show shortest remaining ETA across all baking buildings
        import time as _bt
        _min_remaining = float('inf')
        for _info in bv._baking_buildings.values():
            _el = _bt.time() - _info.get('start_time', _bt.time())
            _rem = max(_info.get('offline_eta', 0) - _el, 0)
            _min_remaining = min(_min_remaining, _rem)
        if _min_remaining < float('inf') and _min_remaining > 1:
            _bk_eta = f" ~{int(_min_remaining)}s" if _min_remaining < 120 else f" ~{int(_min_remaining/60)}m"
        else:
            _bk_eta = ""
        _status_txt = f"BAKING{_bk_eta}"
        _status_color = (0.3, 0.6 * pulse, 1.0 * pulse, 1.0)
    elif bv._direct_stream_enabled:
        from . import direct_stream as _ds
        _tick_ms = getattr(_ds._direct_stream_tick, '_last_tick_ms', 0)
        _ds_total = len(bv._direct_stream_guids)

        # S197: detect camera-moving / settling state for HUD
        _cam_moving = False
        _cam_settling = False
        _prev_cam = bv._direct_stream_cam_last
        if _prev_cam and bv._dlod_eye_pos:
            _off = bv._model_offset
            _hcx = bv._dlod_eye_pos[0] + (_off.x if _off else 0.0)
            _hcy = bv._dlod_eye_pos[1] + (_off.y if _off else 0.0)
            _hcz = bv._dlod_eye_pos[2] + (_off.z if _off else 0.0)
            _cd = math.sqrt((_hcx-_prev_cam[0])**2+(_hcy-_prev_cam[1])**2+(_hcz-_prev_cam[2])**2)
            if _cd > bv._DIRECT_STREAM_CAM_THRESH:
                _cam_moving = True
            elif (now - bv._direct_stream_cam_still_t) < bv._DIRECT_STREAM_SETTLE_S:
                _cam_settling = True

        if _cam_moving:
            _status_txt = f"PAUSED \u2014 CAM MOVE {_ds_total:,}"
            _status_color = (0.9, 0.7, 0.2, 0.9)
        elif _cam_settling:
            _status_txt = f"SETTLING... {_ds_total:,}"
            _status_color = (0.7, 0.6, 0.3, 0.8)
        elif _tick_ms > 1500:
            pulse = 0.6 + 0.4 * abs(math.sin(now * 4))
            _shred_hint = "auto-shredding" if bv._direct_stream_auto_shred else "SHRED to free up"
            _status_txt = f"LAG {int(_tick_ms)}ms \u2014 {_shred_hint}"
            _status_color = (1.0 * pulse, 0.3 * pulse, 0.1, 1.0)
        elif _ds_total >= bv._DIRECT_STREAM_BUDGET:
            _status_txt = f"BUDGET {_ds_total:,}/{bv._DIRECT_STREAM_BUDGET:,} \u2014 SHRED to continue"
            _status_color = (1.0, 0.7, 0.1, 0.9)
        elif bv._direct_stream_active_bld:
            # S197: show RESUMING briefly after cam settle, then STREAMING
            _since_settle = now - bv._direct_stream_cam_still_t
            _ab = bv._direct_stream_active_bld
            _ab_total = bv._building_element_counts.get(_ab, 0)
            _ab_done = len(bv._direct_stream_buildings.get(_ab, set()))
            _ab_phase = bv._direct_stream_disc_phase.get(_ab, 'envelope')
            if _since_settle < 2.0 and _ds_total > 0:
                _status_txt = f"RESUMING {_ab} {_ab_done:,}/{_ab_total:,}"
                _status_color = (0.2, 0.9, 0.6, 0.9)
            elif _ab_phase == 'envelope':
                _status_txt = f"ENVELOPE {_ab} {_ab_done:,}"
                _status_color = (0.4, 0.9, 0.5, 0.9)
            else:
                _status_txt = f"STREAMING {_ab} {_ab_done:,}/{_ab_total:,}"
                _status_color = (0.3, 0.8, 1.0, 0.9)
        else:
            # S197: check if all buildings in radius are done
            _all_done = True
            if bv._building_centres:
                _cam = bv._dlod_eye_pos
                if _cam:
                    _off = bv._model_offset
                    _ecx = _cam[0] + (_off.x if _off else 0.0)
                    _ecy = _cam[1] + (_off.y if _off else 0.0)
                    _ecz = _cam[2] + (_off.z if _off else 0.0)
                    for _bn, _bc in bv._building_centres.items():
                        _ed = math.sqrt((_ecx-_bc[0])**2+(_ecy-_bc[1])**2+(_ecz-_bc[2])**2)
                        if _ed < bv._DIRECT_STREAM_RADIUS:
                            _bph = bv._direct_stream_disc_phase.get(_bn, 'shell')
                            if _bph not in ('done', 'shell_done', 'envelope_done'):
                                _all_done = False
                                break
            # S198: brief processed stats — types streamed / elements in scene
            _n_types = len(bv._direct_stream_buildings)
            if _all_done and _ds_total > 0:
                _status_txt = f"DONE \u2014 {_n_types} types/{_ds_total:,}"
                _status_color = (0.1, 1.0, 0.35, 0.9)
            elif _ds_total > 0:
                _status_txt = f"DONE \u2014 {_n_types} types/{_ds_total:,}"
                _status_color = (0.6, 0.8, 0.7, 0.8)
            else:
                pulse = 0.6 + 0.4 * abs(math.sin(now * 1.5))
                _status_txt = f"PAN CAM TO STREAM"
                _status_color = (0.8 * pulse, 0.7 * pulse, 0.2, 0.9)
    elif bv._building_centres and not bv._direct_stream_enabled:
        # S198: streaming OFF — show processed stats
        _ds_total = len(bv._direct_stream_guids)
        _n_types = len(bv._direct_stream_buildings)
        if _ds_total > 0:
            _status_txt = f"PAUSED \u2014 {_n_types} types/{_ds_total:,}"
        else:
            _status_txt = f"{len(bv._building_centres)} buildings ready"
        _status_color = (0.6, 0.7, 0.8, 0.8)
    elif bv._bake_done:
        # S196: baked but not yet streaming — prompt user
        pulse = 0.7 + 0.3 * math.sin(now * 2)
        _n_baked = len(bv._bake_done)
        _status_txt = f"\u2713 BAKED ({_n_baked}) \u2014 STREAM TO VIEW"
        _status_color = (0.1, 1.0 * pulse, 0.35, 1.0)

    if _status_txt:
        blf.size(font_id, 16)
        _sw = blf.dimensions(font_id, _status_txt)[0]
        blf.position(font_id, _cx - _sw / 2, y_cursor, 0)
        blf.color(font_id, *_status_color)
        blf.draw(font_id, _status_txt)

    # (S195: stream control buttons are in N-panel)

    gpu.state.blend_set('NONE')


def enable_hud():
    """Enable the progress HUD overlay."""
    global _hud_handler, _is_enabled

    if _is_enabled:
        return

    _hud_handler = bpy.types.SpaceView3D.draw_handler_add(
        draw_progress_hud, (), 'WINDOW', 'POST_PIXEL'
    )
    _is_enabled = True

    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def disable_hud():
    """Disable the progress HUD overlay."""
    global _hud_handler, _is_enabled

    if not _is_enabled:
        return

    if _hud_handler:
        bpy.types.SpaceView3D.draw_handler_remove(_hud_handler, 'WINDOW')
        _hud_handler = None

    _is_enabled = False

    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def is_hud_enabled() -> bool:
    return _is_enabled


# ── Drag operator ──

class FedProgressHudDrag(bpy.types.Operator):
    """Drag the progress HUD to reposition it"""
    bl_idname = "bim.fed_progress_hud_drag"
    bl_label = "Drag Progress HUD"
    bl_options = {'INTERNAL'}

    def invoke(self, context, event):
        global _hud_offset_x, _hud_offset_y
        self._start_mx = event.mouse_region_x
        self._start_my = event.mouse_region_y
        self._start_ox = _hud_offset_x
        self._start_oy = _hud_offset_y
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        global _hud_offset_x, _hud_offset_y

        if event.type == 'MOUSEMOVE':
            _hud_offset_x = self._start_ox + (event.mouse_region_x - self._start_mx)
            _hud_offset_y = self._start_oy + (event.mouse_region_y - self._start_my)
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()
            return {'RUNNING_MODAL'}

        if event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            return {'FINISHED'}

        if event.type in {'RIGHTMOUSE', 'ESC'}:
            _hud_offset_x = self._start_ox
            _hud_offset_y = self._start_oy
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}



def register():
    bpy.utils.register_class(FedProgressHudDrag)


def unregister():
    bpy.utils.unregister_class(FedProgressHudDrag)
