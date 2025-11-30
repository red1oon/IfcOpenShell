"""
FAST VERSION - Automated MEP Showcase with Progress Output
-----------------------------------------------------------
Same as automated_mep_showcase.py but with:
- Real-time progress updates (every 1000 objects)
- Optimized keyframe insertion
- Estimated time remaining

Run this if the original script seems stuck!
"""

import bpy
import math
from mathutils import Vector
import time


def switch_to_camera_view():
    """Automatically switch to camera view (no numpad needed!)"""
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.region_3d.view_perspective = 'CAMERA'
                    print("📹 Switched to camera view!")
                    return True
    return False


def get_building_center_and_bounds():
    """Calculate building center and bounds (fast - no prints in loop)"""
    print("📐 Calculating building bounds...")

    min_x = min_y = min_z = float('inf')
    max_x = max_y = max_z = float('-inf')

    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and 'ifc_class' in obj:
            bbox = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
            for corner in bbox:
                min_x = min(min_x, corner.x)
                max_x = max(max_x, corner.x)
                min_y = min(min_y, corner.y)
                max_y = max(max_y, corner.y)
                min_z = min(min_z, corner.z)
                max_z = max(max_z, corner.z)

    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    center_z = (min_z + max_z) / 2
    radius = max(max_x - min_x, max_y - min_y) * 0.7

    print(f"   Center: ({center_x:.1f}, {center_y:.1f}, {center_z:.1f})")
    print(f"   Radius: {radius:.1f}m, Height: {min_z:.1f}m to {max_z:.1f}m")

    return Vector((center_x, center_y, center_z)), radius, min_z, max_z


def add_mep_reveal_with_progress(
    reveal_start: int = 4000,
    reveal_duration: int = 200
):
    """
    Hide building envelope with PROGRESS OUTPUT.
    Updates every 1000 objects so you know it's working!
    """

    print(f"\n🎭 Adding sectional reveal (MEP systems)...")
    print(f"   Reveal: Frame {reveal_start} → {reveal_start + reveal_duration}")

    reveal_end = reveal_start + reveal_duration
    count = 0
    total_objects = len(bpy.context.scene.objects)
    start_time = time.time()

    print(f"   Processing {total_objects:,} objects...")

    for i, obj in enumerate(bpy.context.scene.objects):
        # Progress every 1000 objects
        if (i + 1) % 1000 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            remaining = (total_objects - i - 1) / rate if rate > 0 else 0
            print(f"      Progress: {i+1:,}/{total_objects:,} ({100*(i+1)/total_objects:.0f}%) "
                  f"- {count:,} envelope objects found - ETA: {remaining:.0f}s")

        if 'discipline' not in obj:
            continue

        # Hide ARC and STR (building envelope)
        if obj['discipline'] in ['ARC', 'STR']:
            # Keyframes for hiding
            obj.hide_viewport = True
            obj.hide_render = True
            obj.keyframe_insert('hide_viewport', frame=reveal_start)
            obj.keyframe_insert('hide_render', frame=reveal_start)

            # Keyframes for showing again
            obj.hide_viewport = False
            obj.hide_render = False
            obj.keyframe_insert('hide_viewport', frame=reveal_end)
            obj.keyframe_insert('hide_render', frame=reveal_end)

            count += 1

    elapsed = time.time() - start_time
    print(f"   ✅ {count:,} envelope objects configured in {elapsed:.1f}s")


def create_camera_with_path(
    reveal_start: int = 4000,
    reveal_end: int = 4200,
    building_center: Vector = None,
    orbit_radius: float = 100.0,
    min_z: float = 0,
    max_z: float = 30
):
    """Create camera path (same as before)"""

    print(f"\n📹 Creating automated camera path...")

    # Get or create camera
    if 'MEP_Showcase_Camera' in bpy.data.objects:
        camera = bpy.data.objects['MEP_Showcase_Camera']
    else:
        cam_data = bpy.data.cameras.new('MEP_Showcase_Camera')
        cam_data.lens = 35
        camera = bpy.data.objects.new('MEP_Showcase_Camera', cam_data)
        bpy.context.collection.objects.link(camera)

    bpy.context.scene.camera = camera

    # Clear existing animation
    if camera.animation_data:
        camera.animation_data_clear()

    cx, cy, cz = building_center
    mid_z = (min_z + max_z) / 2

    # Keyframe positions
    positions = [
        {'frame': reveal_start - 200, 'loc': (cx + orbit_radius * 1.5, cy, mid_z + 20)},
        {'frame': reveal_start - 100, 'loc': (cx + orbit_radius, cy, mid_z + 10)},
        {'frame': reveal_start, 'loc': (cx + orbit_radius * 0.6, cy, mid_z)},
        {'frame': reveal_start + 50, 'loc': (cx, cy + orbit_radius * 0.6, mid_z + 5)},
        {'frame': reveal_start + 100, 'loc': (cx - orbit_radius * 0.6, cy, mid_z)},
        {'frame': reveal_start + 150, 'loc': (cx, cy - orbit_radius * 0.6, mid_z + 5)},
        {'frame': reveal_end - 20, 'loc': (cx + orbit_radius * 0.5, cy, mid_z)},
        {'frame': reveal_end, 'loc': (cx + orbit_radius, cy, mid_z + 10)},
        {'frame': reveal_end + 100, 'loc': (cx + orbit_radius * 1.5, cy, mid_z + 20)}
    ]

    # Insert keyframes
    for pos in positions:
        camera.location = pos['loc']
        camera.keyframe_insert(data_path='location', frame=pos['frame'])

        # Point at building center
        direction = Vector(building_center) - Vector(pos['loc'])
        rot_quat = direction.to_track_quat('-Z', 'Y')
        camera.rotation_euler = rot_quat.to_euler()
        camera.keyframe_insert(data_path='rotation_euler', frame=pos['frame'])

    # Smooth curves
    if camera.animation_data and camera.animation_data.action:
        for fcurve in camera.animation_data.action.fcurves:
            for kp in fcurve.keyframe_points:
                kp.interpolation = 'BEZIER'
                kp.handle_left_type = 'AUTO'
                kp.handle_right_type = 'AUTO'

    print(f"   ✅ Camera path: {len(positions)} keyframes")
    return camera


def automated_mep_showcase_fast(
    reveal_start: int = 4000,
    reveal_duration: int = 200
):
    """FAST VERSION with progress output"""

    print("\n" + "="*70)
    print("🎬 AUTOMATED MEP SHOWCASE - FAST VERSION")
    print("="*70)

    # Calculate bounds
    center, radius, min_z, max_z = get_building_center_and_bounds()

    # Add reveal (WITH PROGRESS)
    add_mep_reveal_with_progress(reveal_start, reveal_duration)

    # Create camera
    reveal_end = reveal_start + reveal_duration
    camera = create_camera_with_path(reveal_start, reveal_end, center, radius, min_z, max_z)

    # Timeline
    bpy.context.scene.frame_start = reveal_start - 200
    bpy.context.scene.frame_end = reveal_end + 100
    bpy.context.scene.frame_current = reveal_start - 200

    # Auto-switch to camera view
    switch_to_camera_view()

    print("\n" + "="*70)
    print("✅ SETUP COMPLETE!")
    print("="*70)
    print(f"\n🎮 HOW TO USE:")
    print(f"   1. Ctrl+S to save")
    print(f"   2. Already in camera view! (no numpad needed)")
    print(f"   3. Press SPACEBAR → Watch automated showcase!")
    print(f"\n📹 Timeline: Frame {reveal_start-200} → {reveal_end+100}")
    print(f"🎭 Reveal: Frame {reveal_start} (envelope hides) → {reveal_end} (returns)")
    print("="*70 + "\n")


if __name__ == "__main__":
    print("\n🚀 FAST VERSION - With Progress Output")
    print("   You'll see updates every 1000 objects\n")

    automated_mep_showcase_fast(
        reveal_start=4000,
        reveal_duration=200
    )

    print("\n💾 Save now (Ctrl+S) then press SPACEBAR!\n")
