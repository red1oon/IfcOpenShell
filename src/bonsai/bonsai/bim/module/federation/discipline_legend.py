"""
Federation Discipline Legend
============================

Floating 2D legend overlay for preview mode showing discipline colors with toggle checkboxes.
Only active during wireframe preview mode - disappears when loading solid/full geometry.

Uses blf (Blender Font) for 2D text rendering and bgl/gpu for colored boxes.
"""

import bpy
import blf
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector

# Import discipline colors from bbox_visualization (now in federation module)
from .bbox_visualization import DISCIPLINE_COLORS

# Global state
_legend_handler = None
_is_legend_enabled = False
_discipline_visibility = {}  # Track which disciplines are visible (all visible by default)


def draw_legend():
    """Draw callback for legend overlay (2D screen space)"""
    global _discipline_visibility, _is_legend_enabled

    if not _is_legend_enabled:
        return

    # Get active disciplines from bbox batches
    from . import bbox_visualization
    if not bbox_visualization._bbox_batches:
        return

    disciplines = sorted(bbox_visualization._bbox_batches.keys())
    if not disciplines:
        return

    # Legend position (top-right corner, 20px padding)
    region = bpy.context.region
    x_start = region.width - 200
    y_start = region.height - 40

    font_id = 0
    line_height = 25
    box_size = 15

    # Draw semi-transparent background panel
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')

    panel_height = len(disciplines) * line_height + 55  # +15 for search hint line
    panel_vertices = [
        (x_start - 10, y_start - panel_height),
        (x_start + 190, y_start - panel_height),
        (x_start + 190, y_start + 10),
        (x_start - 10, y_start + 10)
    ]
    panel_batch = batch_for_shader(shader, 'TRI_FAN', {"pos": panel_vertices})

    gpu.state.blend_set('ALPHA')
    shader.bind()
    shader.uniform_float("color", (0.2, 0.2, 0.2, 0.85))  # Dark gray, semi-transparent
    panel_batch.draw(shader)

    # Draw title
    blf.position(font_id, x_start, y_start, 0)
    blf.size(font_id, 14)
    blf.color(font_id, 1.0, 1.0, 1.0, 1.0)  # White
    blf.draw(font_id, "Federation Preview")

    # Draw search hint / last result (from RTree Inspector props)
    try:
        props = bpy.context.scene.BIMFederationProperties
        if props.rtree_search:
            hint = f"Search: '{props.rtree_search}'"
            if props.rtree_result_count:
                hint += f"  → {props.rtree_result_count} hit(s)"
            else:
                hint += "  → no results"
            blf.position(font_id, x_start, y_start - 18, 0)
            blf.size(font_id, 10)
            blf.color(font_id, 1.0, 1.0, 0.3, 1.0)  # Yellow hint
            blf.draw(font_id, hint)
        else:
            blf.position(font_id, x_start, y_start - 18, 0)
            blf.size(font_id, 10)
            blf.color(font_id, 0.7, 0.7, 0.7, 0.8)
            blf.draw(font_id, "N-panel BIM tab → RTree Inspector to search")
    except Exception:
        pass

    y_pos = y_start - 30

    # Draw each discipline with color box and label
    for discipline in disciplines:
        # Draw discipline color box
        color = DISCIPLINE_COLORS.get(discipline, DISCIPLINE_COLORS['DEFAULT'])

        color_vertices = [
            (x_start, y_pos - 2),
            (x_start + box_size, y_pos - 2),
            (x_start + box_size, y_pos + box_size - 2),
            (x_start, y_pos + box_size - 2)
        ]
        color_batch = batch_for_shader(shader, 'TRI_FAN', {"pos": color_vertices})
        shader.uniform_float("color", color)
        color_batch.draw(shader)

        # Draw discipline label
        blf.position(font_id, x_start + box_size + 10, y_pos + 2, 0)
        blf.size(font_id, 12)
        blf.color(font_id, 1.0, 1.0, 1.0, 1.0)  # White text
        blf.draw(font_id, discipline)

        y_pos -= line_height

    gpu.state.blend_set('NONE')


def enable_legend():
    """Enable the discipline legend overlay (visual reference only)"""
    global _legend_handler, _is_legend_enabled, _discipline_visibility

    if _is_legend_enabled:
        return  # Already enabled

    # Initialize visibility for all disciplines (all visible by default)
    from . import bbox_visualization
    if bbox_visualization._bbox_batches:
        for discipline in bbox_visualization._bbox_batches.keys():
            if discipline not in _discipline_visibility:
                _discipline_visibility[discipline] = True

    # Register draw handler for 2D overlay
    _legend_handler = bpy.types.SpaceView3D.draw_handler_add(
        draw_legend, (), 'WINDOW', 'POST_PIXEL'
    )
    _is_legend_enabled = True

    # NOTE: Click handling removed - use Outliner for toggling disciplines
    print("✓ Discipline legend enabled (visual reference - toggle via Outliner)")

    # Force viewport redraw
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def disable_legend():
    """Disable the discipline legend overlay"""
    global _legend_handler, _is_legend_enabled

    if not _is_legend_enabled:
        return

    # Remove draw handler
    if _legend_handler:
        bpy.types.SpaceView3D.draw_handler_remove(_legend_handler, 'WINDOW')
        _legend_handler = None

    _is_legend_enabled = False

    print("✓ Discipline legend disabled")

    # Force viewport redraw
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def is_legend_enabled() -> bool:
    """Check if legend is currently enabled"""
    global _is_legend_enabled
    return _is_legend_enabled


# NOTE: Modal operator and click handling removed
# Use the Outliner to toggle discipline visibility instead
# This is safer and doesn't interfere with Bonsai's architecture
