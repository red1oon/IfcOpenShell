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
    S195: also shows DirectStream progress when no active RTree building."""
    from . import bbox_visualization as bv

    disc_counts = bv._building_disc_counts

    # S195: If no RTree active building but DirectStream is running, show DS progress
    if not disc_counts and bv._direct_stream_enabled:
        # Find the building currently being streamed (active or most recent)
        _ds_bld = bv._direct_stream_active_bld
        if not _ds_bld:
            # Use last active building (persists after pause)
            _ds_bld = bv._direct_stream_last_bld
        if _ds_bld:
            disc_counts = bv._direct_stream_disc_totals.get(_ds_bld, {})
            loaded_per_disc = bv._direct_stream_disc_loaded.get(_ds_bld, {})
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

    # S195: show HUD when streaming OR when streamed buildings exist (paused state)
    _has_ds_data = bool(bv._direct_stream_buildings)
    if not rows and not bv._direct_stream_enabled and not _has_ds_data:
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

    # Title: "Building (total)" idle, "Building (pct%)" when streaming
    if total_loaded > 0 and total_pct < 100:
        _title = f"{building} ({total_pct:.0f}%)"
    elif total_pct >= 100:
        _title = f"{building} \u2713"
    else:
        _title = f"{building} ({total_count:,})"

    blf.size(font_id, 16)
    _tw = blf.dimensions(font_id, _title)[0]
    blf.position(font_id, _cx - _tw / 2, y0 - 4, 0)
    if total_pct >= 100:
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

        # Dull background — full bar in dim disc color (shows total capacity)
        _draw_rect(shader, x0 + label_width, y_cursor - bar_height,
                   bar_w, bar_height, (dr * 0.2, dg * 0.2, db * 0.2, 0.6))

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
    elif bv._active_building and bv._active_building in bv._bake_done:
        pulse = 0.7 + 0.3 * math.sin(now * 2)
        _status_txt = "BAKED \u2014 SAVE TO LINK"
        _status_color = (0.1, 1.0 * pulse, 0.35, 1.0)
    elif bv._active_building and bpy.data.collections.get(f"Baked_{bv._active_building}"):
        _status_txt = "\u2713 BAKED LINK SUCCESS"
        _status_color = (0.1, 0.85, 0.3, 0.9)
    elif bv._direct_stream_enabled:
        from . import operator as _op
        _tick_ms = getattr(_op._direct_stream_tick, '_last_tick_ms', 0)
        _ds_total = len(bv._direct_stream_guids)
        if _tick_ms > 1500:
            pulse = 0.6 + 0.4 * abs(math.sin(now * 4))
            _shred_hint = "auto-shredding" if bv._direct_stream_auto_shred else "SHRED to free up"
            _status_txt = f"LAG {int(_tick_ms)}ms \u2014 {_shred_hint}"
            _status_color = (1.0 * pulse, 0.3 * pulse, 0.1, 1.0)
        elif _ds_total >= bv._DIRECT_STREAM_BUDGET:
            _status_txt = f"BUDGET {_ds_total:,}/{bv._DIRECT_STREAM_BUDGET:,} \u2014 SHRED to continue"
            _status_color = (1.0, 0.7, 0.1, 0.9)
        elif bv._direct_stream_active_bld:
            _status_txt = f"STREAMING {_ds_total:,}"
            _status_color = (0.3, 0.8, 1.0, 0.9)
        else:
            _status_txt = f"IDLE {_ds_total:,}"
            _status_color = (0.5, 0.7, 0.5, 0.7)

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
