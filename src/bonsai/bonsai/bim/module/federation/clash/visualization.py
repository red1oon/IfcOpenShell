"""
GPU-based clash marker visualization with zoom-adaptive LOD

Uses Blender's GPU shader system (like Bonsai decorations) to draw clash markers
without creating scene objects. Implements Google Maps-style progressive detail:
- Far zoom: Directional arrows to clash clusters
- Medium zoom: Cluster markers
- Close zoom: Individual clashes with shadows

Fixes coordinate offset issue by using Bonsai's georeference properties.
"""

import bpy
import gpu
import math
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, Matrix
from typing import List, Tuple, Optional

# Global state
_clash_markers = []  # Cached marker positions
_draw_handler = None
_zoom_level = 'OVERVIEW'


def get_model_offset():
    """Get model offset to convert IFC coords to Blender coords

    Uses cached offset from MEP routing if available, otherwise falls back
    to Bonsai georeference properties.
    """
    # Try MEP cached offset first (most reliable)
    cached = bpy.context.scene.get("MEP_cached_offset")
    if cached:
        print(f"  📍 Clash viz using MEP cached offset: {cached}")
        return Vector(cached)

    # Fallback to georeference properties
    try:
        props = bpy.context.scene.BIMGeoreferenceProperties
        offset = Vector((
            props.model_offset_x or 0.0,
            props.model_offset_y or 0.0,
            props.model_offset_z or 0.0
        ))
        print(f"  📍 Clash viz using georeference offset: {offset}")
        return offset
    except:
        # No offset available - assume zero
        print(f"  ⚠️  Clash viz: No offset available, using zero")
        return Vector((0, 0, 0))


def ifc_to_blender_coords(ifc_coords: Tuple[float, float, float]) -> Vector:
    """Convert IFC world coordinates to Blender scene coordinates"""
    offset = get_model_offset()
    return Vector((
        ifc_coords[0] - offset.x,
        ifc_coords[1] - offset.y,
        ifc_coords[2] - offset.z
    ))


def get_zoom_level(context) -> str:
    """Determine zoom level based on viewport distance"""
    try:
        view3d = context.space_data
        if view3d.type != 'VIEW_3D':
            return 'OVERVIEW'

        region_3d = view3d.region_3d
        distance = region_3d.view_distance

        # Adaptive thresholds (adjust based on building scale)
        if distance > 100:  # Far - see whole building
            return 'OVERVIEW'
        elif distance > 20:  # Medium - see floor/wing
            return 'CLUSTERS'
        else:  # Close - see individual clashes
            return 'DETAIL'
    except:
        return 'OVERVIEW'


def cluster_markers(markers: List[dict], radius: float = 10.0) -> List[dict]:
    """Group nearby markers into clusters for medium zoom level"""
    if not markers:
        return []

    clusters = []
    unclustered = markers.copy()

    while unclustered:
        seed = unclustered.pop(0)
        cluster = {
            'position': seed['position'],
            'members': [seed],
            'count': 1
        }

        # Find all markers within radius
        i = 0
        while i < len(unclustered):
            dist = (unclustered[i]['position'] - seed['position']).length
            if dist < radius:
                member = unclustered.pop(i)
                cluster['members'].append(member)
                cluster['count'] += 1
                # Update cluster center (average)
                cluster['position'] = sum((m['position'] for m in cluster['members']), Vector()) / cluster['count']
            else:
                i += 1

        clusters.append(cluster)

    return clusters


def draw_sphere_batch(position: Vector, radius: float, color: Tuple[float, float, float, float]):
    """Draw a simple sphere using GPU shader (optimized for many markers)"""
    # Simple billboard circle (faces camera)
    # TODO: Replace with proper sphere if performance allows
    segments = 16
    vertices = []

    for i in range(segments):
        angle = (i / segments) * math.pi * 2
        x = math.cos(angle) * radius
        y = math.sin(angle) * radius
        vertices.append(position + Vector((x, y, 0)))

    # Close the circle
    vertices.append(vertices[0])

    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
    batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": vertices})

    shader.bind()
    shader.uniform_float("color", color)
    batch.draw(shader)


def draw_directional_arrow(direction: Vector, count: int, color: Tuple[float, float, float, float]):
    """Draw directional arrow for overview zoom level"""
    # Draw arrow pointing to clash clusters
    # TODO: Implement arrow geometry
    pass


def draw_clash_overlays():
    """Main draw handler - called every viewport refresh"""
    global _clash_markers, _zoom_level

    if not _clash_markers:
        return

    context = bpy.context
    _zoom_level = get_zoom_level(context)

    # Enable depth testing and blending
    gpu.state.depth_test_set('LESS_EQUAL')
    gpu.state.blend_set('ALPHA')

    try:
        if _zoom_level == 'OVERVIEW':
            # Far zoom: Show directional guidance (TODO)
            # For now, show large cluster markers
            clusters = cluster_markers(_clash_markers, radius=50.0)
            for cluster in clusters:
                draw_sphere_batch(cluster['position'], radius=5.0, color=(1.0, 0.5, 0.0, 0.8))

        elif _zoom_level == 'CLUSTERS':
            # Medium zoom: Show cluster markers
            clusters = cluster_markers(_clash_markers, radius=10.0)
            for cluster in clusters:
                # Size based on cluster count
                radius = 1.0 + (cluster['count'] * 0.1)
                draw_sphere_batch(cluster['position'], radius=radius, color=(1.0, 0.0, 0.0, 0.7))

        else:  # DETAIL
            # Close zoom: Show individual markers
            for marker in _clash_markers:
                # Bright markers for nearby clashes
                draw_sphere_batch(marker['position'], radius=0.5, color=(1.0, 0.0, 0.0, 1.0))

                # TODO: Add "shadow" (faded) markers for adjacent clashes

    finally:
        # Restore GPU state
        gpu.state.depth_test_set('NONE')
        gpu.state.blend_set('NONE')


def load_clash_markers(clash_candidates: list):
    """Load clash positions from database, apply coordinate offset, cache for drawing"""
    global _clash_markers

    _clash_markers = []

    for clash in clash_candidates:
        # Get clash midpoint from database (IFC world coordinates)
        # Assuming clash object has center_a and center_b with (x, y, z) tuples
        ifc_center_a = Vector(clash.get('center_a', (0, 0, 0)))
        ifc_center_b = Vector(clash.get('center_b', (0, 0, 0)))

        # Convert to Blender coordinates (apply offset)
        blender_a = ifc_to_blender_coords(ifc_center_a)
        blender_b = ifc_to_blender_coords(ifc_center_b)

        # Midpoint in Blender space
        midpoint = (blender_a + blender_b) / 2

        _clash_markers.append({
            'position': midpoint,
            'clash_id': clash.get('id'),
            'severity': clash.get('distance', 0.0)
        })

    print(f"Loaded {len(_clash_markers)} clash markers with offset correction")


def enable_visualization():
    """Enable GPU overlay drawing"""
    global _draw_handler

    if _draw_handler is not None:
        return  # Already enabled

    # Register draw handler for all 3D viewports
    _draw_handler = bpy.types.SpaceView3D.draw_handler_add(
        draw_clash_overlays,
        (),
        'WINDOW',
        'POST_VIEW'
    )

    print("Clash visualization enabled (GPU overlays)")

    # Force viewport redraw
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def disable_visualization():
    """Disable GPU overlay drawing"""
    global _draw_handler, _clash_markers

    if _draw_handler is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_draw_handler, 'WINDOW')
        _draw_handler = None

    _clash_markers = []

    print("Clash visualization disabled")

    # Force viewport redraw
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def is_enabled() -> bool:
    """Check if visualization is currently active"""
    return _draw_handler is not None
