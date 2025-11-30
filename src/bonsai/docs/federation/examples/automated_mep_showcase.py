"""
Automated MEP Showcase - Sectional Reveal + Camera Animation
-------------------------------------------------------------
Combines:
1. Building envelope hiding (ARC + STR) during MEP phase
2. Automated camera flythrough around/inside building
3. Perfectly timed to MEP construction (ACMV, ELEC, FP installation)

Just press SPACEBAR and watch the show!
"""

import bpy
import math
from mathutils import Vector


def switch_to_camera_view():
    """
    Automatically switch 3D viewport to camera view.
    Works without numpad 0!
    """
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.region_3d.view_perspective = 'CAMERA'
                    print("📹 Switched to camera view (no numpad needed!)")
                    return True
    return False


def get_building_center_and_bounds():
    """
    Calculate building center and bounding box from all objects.
    Returns: (center, radius, min_z, max_z)
    """
    print("📐 Calculating building bounds...")

    min_x = min_y = min_z = float('inf')
    max_x = max_y = max_z = float('-inf')

    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and 'ifc_class' in obj:
            # Get world-space bounding box
            bbox = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]

            for corner in bbox:
                min_x = min(min_x, corner.x)
                max_x = max(max_x, corner.x)
                min_y = min(min_y, corner.y)
                max_y = max(max_y, corner.y)
                min_z = min(min_z, corner.z)
                max_z = max(max_z, corner.z)

    # Building center
    center_x = (min_x + max_x) / 2
    center_y = (min_y + max_y) / 2
    center_z = (min_z + max_z) / 2

    # Radius for camera orbit
    radius = max(max_x - min_x, max_y - min_y) * 0.7  # 70% of width

    print(f"   Center: ({center_x:.1f}, {center_y:.1f}, {center_z:.1f})")
    print(f"   Radius: {radius:.1f}m")
    print(f"   Height: {min_z:.1f}m to {max_z:.1f}m")

    return Vector((center_x, center_y, center_z)), radius, min_z, max_z


def create_camera_with_path(
    reveal_start: int = 4000,
    reveal_end: int = 4200,
    building_center: Vector = None,
    orbit_radius: float = 100.0,
    min_z: float = 0,
    max_z: float = 30
):
    """
    Create camera and animate it around the building during MEP reveal.

    Camera path:
    - Start: Outside view (normal construction)
    - Frame reveal_start-100: Begin approach
    - Frame reveal_start: Enter building, orbit around interior
    - Frame reveal_end: Exit building, return to overview

    Args:
        reveal_start: When envelope hides (MEP reveal begins)
        reveal_end: When envelope reappears
        building_center: Center point for orbit
        orbit_radius: Distance from center
        min_z, max_z: Building height range
    """

    print(f"\n📹 Creating automated camera path...")
    print(f"   Timeline: {reveal_start-200} → {reveal_end+100}")

    # Get or create camera
    if 'MEP_Showcase_Camera' in bpy.data.objects:
        camera = bpy.data.objects['MEP_Showcase_Camera']
        print(f"   Using existing camera: {camera.name}")
    else:
        # Create new camera
        cam_data = bpy.data.cameras.new('MEP_Showcase_Camera')
        cam_data.lens = 35  # Wide angle for interior views
        camera = bpy.data.objects.new('MEP_Showcase_Camera', cam_data)
        bpy.context.collection.objects.link(camera)
        print(f"   Created new camera: {camera.name}")

    # Set as active camera
    bpy.context.scene.camera = camera

    # Clear existing animation
    if camera.animation_data:
        camera.animation_data_clear()

    # Calculate keyframe positions
    cx, cy, cz = building_center
    mid_z = (min_z + max_z) / 2

    # Camera positions (circular orbit)
    positions = [
        # Phase 1: Approach (before reveal)
        {
            'frame': reveal_start - 200,
            'loc': (cx + orbit_radius * 1.5, cy, mid_z + 20),  # Far overview
            'rot': (math.radians(70), 0, math.radians(-90))  # Looking down
        },
        {
            'frame': reveal_start - 100,
            'loc': (cx + orbit_radius, cy, mid_z + 10),  # Moving closer
            'rot': (math.radians(80), 0, math.radians(-90))
        },

        # Phase 2: Enter and orbit during MEP reveal
        {
            'frame': reveal_start,
            'loc': (cx + orbit_radius * 0.6, cy, mid_z),  # Inside building
            'rot': (math.radians(90), 0, math.radians(-90))  # Level view
        },
        {
            'frame': reveal_start + 50,
            'loc': (cx, cy + orbit_radius * 0.6, mid_z + 5),  # Orbit to side
            'rot': (math.radians(85), 0, math.radians(180))
        },
        {
            'frame': reveal_start + 100,
            'loc': (cx - orbit_radius * 0.6, cy, mid_z),  # Orbit to back
            'rot': (math.radians(90), 0, math.radians(90))
        },
        {
            'frame': reveal_start + 150,
            'loc': (cx, cy - orbit_radius * 0.6, mid_z + 5),  # Orbit to other side
            'rot': (math.radians(85), 0, math.radians(0))
        },
        {
            'frame': reveal_end - 20,
            'loc': (cx + orbit_radius * 0.5, cy, mid_z),  # Complete orbit
            'rot': (math.radians(90), 0, math.radians(-90))
        },

        # Phase 3: Exit and overview
        {
            'frame': reveal_end,
            'loc': (cx + orbit_radius, cy, mid_z + 10),  # Pull out
            'rot': (math.radians(80), 0, math.radians(-90))
        },
        {
            'frame': reveal_end + 100,
            'loc': (cx + orbit_radius * 1.5, cy, mid_z + 20),  # Far overview
            'rot': (math.radians(70), 0, math.radians(-90))
        }
    ]

    # Insert keyframes
    for pos in positions:
        frame = pos['frame']

        # Set location
        camera.location = pos['loc']
        camera.keyframe_insert(data_path='location', frame=frame)

        # Set rotation (Euler XYZ)
        camera.rotation_euler = pos['rot']
        camera.keyframe_insert(data_path='rotation_euler', frame=frame)

        # Point camera at building center (track to constraint alternative)
        direction = Vector(building_center) - Vector(pos['loc'])
        rot_quat = direction.to_track_quat('-Z', 'Y')
        camera.rotation_euler = rot_quat.to_euler()
        camera.keyframe_insert(data_path='rotation_euler', frame=frame)

    # Smooth interpolation (Bezier curves for smooth motion)
    if camera.animation_data and camera.animation_data.action:
        for fcurve in camera.animation_data.action.fcurves:
            for kp in fcurve.keyframe_points:
                kp.interpolation = 'BEZIER'
                kp.handle_left_type = 'AUTO'
                kp.handle_right_type = 'AUTO'

    print(f"   ✅ Camera path created: {len(positions)} keyframes")
    print(f"   Active camera: {camera.name}")

    return camera


def add_mep_reveal(
    reveal_start: int = 4000,
    reveal_duration: int = 200
):
    """
    Hide building envelope (ARC + STR) during MEP phase.

    Args:
        reveal_start: When to hide envelope
        reveal_duration: How long to keep hidden
    """

    print(f"\n🎭 Adding sectional reveal (MEP systems)...")
    print(f"   Reveal: Frame {reveal_start} → {reveal_start + reveal_duration}")

    reveal_end = reveal_start + reveal_duration
    count = 0

    for obj in bpy.context.scene.objects:
        if 'discipline' not in obj:
            continue

        # Hide ARC and STR (building envelope)
        if obj['discipline'] in ['ARC', 'STR']:
            # Hide during reveal
            obj.hide_viewport = True
            obj.hide_render = True
            obj.keyframe_insert('hide_viewport', frame=reveal_start)
            obj.keyframe_insert('hide_render', frame=reveal_start)

            # Show again after reveal
            obj.hide_viewport = False
            obj.hide_render = False
            obj.keyframe_insert('hide_viewport', frame=reveal_end)
            obj.keyframe_insert('hide_render', frame=reveal_end)

            count += 1

    print(f"   ✅ {count:,} envelope objects will hide during reveal")


def setup_render_settings_for_preview():
    """
    Configure render settings for smooth preview playback.
    """
    scene = bpy.context.scene

    # Viewport settings for smooth playback
    scene.render.fps = 24
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 50  # 50% for faster preview

    # Enable motion blur for smoother camera movement
    scene.render.use_motion_blur = False  # Disable for preview (enable for final render)

    print("✅ Render settings configured for preview")


def automated_mep_showcase(
    reveal_start: int = 4000,
    reveal_duration: int = 200,
    auto_calculate_bounds: bool = True
):
    """
    MAIN FUNCTION: Complete automated MEP showcase setup.

    Creates:
    1. Sectional reveal (hide ARC + STR)
    2. Automated camera flythrough
    3. Render settings

    Args:
        reveal_start: Frame when MEP reveal begins (default: 4000)
        reveal_duration: How long reveal lasts (default: 200 frames)
        auto_calculate_bounds: Auto-detect building size (recommended)
    """

    print("\n" + "="*70)
    print("🎬 AUTOMATED MEP SHOWCASE - Setup")
    print("="*70)

    # Step 1: Calculate building bounds
    if auto_calculate_bounds:
        center, radius, min_z, max_z = get_building_center_and_bounds()
    else:
        # Manual fallback
        center = Vector((0, 0, 15))
        radius = 100
        min_z = 0
        max_z = 30
        print("📐 Using manual bounds (auto-detection disabled)")

    # Step 2: Add sectional reveal
    add_mep_reveal(reveal_start, reveal_duration)

    # Step 3: Create camera path
    reveal_end = reveal_start + reveal_duration
    camera = create_camera_with_path(
        reveal_start=reveal_start,
        reveal_end=reveal_end,
        building_center=center,
        orbit_radius=radius,
        min_z=min_z,
        max_z=max_z
    )

    # Step 4: Setup render settings
    setup_render_settings_for_preview()

    # Step 5: Set timeline to showcase range
    bpy.context.scene.frame_start = reveal_start - 200
    bpy.context.scene.frame_end = reveal_end + 100
    bpy.context.scene.frame_current = reveal_start - 200  # Start from beginning

    # Step 6: Auto-switch to camera view (no numpad needed!)
    switch_to_camera_view()

    print("\n" + "="*70)
    print("✅ AUTOMATED MEP SHOWCASE - Ready!")
    print("="*70)
    print(f"\n📋 Timeline Setup:")
    print(f"   Start: Frame {reveal_start - 200} (approach)")
    print(f"   Reveal: Frame {reveal_start} (MEP visible, envelope hides)")
    print(f"   End: Frame {reveal_end + 100} (exit)")
    print(f"   Duration: {reveal_duration + 300} frames (~{(reveal_duration + 300)/2:.0f} days)")

    print(f"\n📹 Camera Path:")
    print(f"   Phase 1: Approach (frames {reveal_start-200} → {reveal_start})")
    print(f"   Phase 2: Interior orbit (frames {reveal_start} → {reveal_end})")
    print(f"   Phase 3: Exit overview (frames {reveal_end} → {reveal_end+100})")

    print(f"\n🎭 Sectional Reveal:")
    print(f"   Frame {reveal_start}: ARC + STR hide")
    print(f"   Visible: ACMV ducts, ELEC conduits, FP pipes")
    print(f"   Frame {reveal_end}: ARC + STR return")

    print(f"\n🎮 HOW TO USE:")
    print(f"   1. Save file (Ctrl+S)")
    print(f"   2. Already in camera view! (no numpad needed)")
    print(f"   3. Press SPACEBAR → Watch automated showcase!")
    print(f"   4. Sit back and enjoy the flythrough 🍿")

    print(f"\n💡 TIPS:")
    print(f"   - Scrub to frame {reveal_start} to see MEP reveal")
    print(f"   - Spacebar = cinematic playback")
    print(f"   - For final render: Set resolution to 100%, enable motion blur")
    print(f"   - To exit camera view: View menu → Viewport Navigation → Orbit")

    print("\n" + "="*70 + "\n")


def quick_test_camera_only():
    """
    Test camera animation without modifying existing animation.
    Useful for previewing camera path before committing.
    """
    print("🧪 TEST MODE: Camera only (no sectional reveal)")

    center, radius, min_z, max_z = get_building_center_and_bounds()

    camera = create_camera_with_path(
        reveal_start=4000,
        reveal_end=4200,
        building_center=center,
        orbit_radius=radius,
        min_z=min_z,
        max_z=max_z
    )

    bpy.context.scene.frame_start = 3800
    bpy.context.scene.frame_end = 4300
    bpy.context.scene.frame_current = 3800

    print(f"\n✅ Test camera created: {camera.name}")
    print(f"   Press 0 (numpad) → Camera view")
    print(f"   Press SPACEBAR → Preview camera path")


# ==============================================================================
# PRESETS FOR DIFFERENT SCENARIOS
# ==============================================================================

def preset_early_mep_reveal():
    """
    Preset: Early construction phase MEP reveal
    Shows foundation and Level 0 MEP systems
    """
    print("🎯 PRESET: Early MEP Reveal (Foundation phase)")
    automated_mep_showcase(
        reveal_start=2000,   # ~23% through project
        reveal_duration=200
    )


def preset_midpoint_mep_reveal():
    """
    Preset: Midpoint MEP reveal (DEFAULT)
    Shows all MEP rough-in during structure completion
    """
    print("🎯 PRESET: Midpoint MEP Reveal (MEP rough-in phase)")
    automated_mep_showcase(
        reveal_start=4000,   # ~46% through project
        reveal_duration=200
    )


def preset_late_mep_reveal():
    """
    Preset: Late construction MEP reveal
    Shows ceiling MEP before finishes
    """
    print("🎯 PRESET: Late MEP Reveal (Before finishes)")
    automated_mep_showcase(
        reveal_start=6500,   # ~74% through project
        reveal_duration=200
    )


def preset_extended_showcase():
    """
    Preset: Extended MEP showcase (5+ minutes)
    Slow camera for detailed examination
    """
    print("🎯 PRESET: Extended Showcase (Long duration)")
    automated_mep_showcase(
        reveal_start=4000,
        reveal_duration=500  # ~250 days visible
    )


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🎬 AUTOMATED MEP SHOWCASE")
    print("="*70)
    print("\nAvailable presets:")
    print("1. preset_early_mep_reveal()    - Early construction (frame 2000)")
    print("2. preset_midpoint_mep_reveal() - Mid construction (frame 4000) [DEFAULT]")
    print("3. preset_late_mep_reveal()     - Late construction (frame 6500)")
    print("4. preset_extended_showcase()   - Extended duration (500 frames)")
    print("\nCustom:")
    print("5. automated_mep_showcase(start, duration)")
    print("6. quick_test_camera_only()     - Test camera path only")

    print("\n" + "="*70)
    print("RUNNING: Preset 2 (Midpoint MEP Reveal)")
    print("="*70 + "\n")

    # RUN DEFAULT PRESET
    preset_midpoint_mep_reveal()

    print("\n💾 IMPORTANT: Save file now (Ctrl+S)")
    print("🎬 Then press SPACEBAR to watch the automated showcase!\n")


# ==============================================================================
# USAGE EXAMPLES
# ==============================================================================
"""
METHOD 1: Run in Blender (Interactive)
=======================================
1. Open animated .blend file
2. Scripting workspace → Open this file
3. Click "Run Script" (▶)
4. Ctrl+S to save
5. Press 0 (numpad) → Camera view
6. Press SPACEBAR → Watch show!

METHOD 2: Run from Terminal (Background)
=========================================
~/blender-4.2.14/blender WORK_DIR/databases/enhanced_federation_4d_animated.blend \\
    --background \\
    --python WORK_DIR/test_outputs/automated_mep_showcase.py

METHOD 3: Custom Parameters
============================
# In Blender Python console:
import sys
sys.path.insert(0, "/home/red1/Projects/IfcOpenShell/WORK_DIR/test_outputs")
from automated_mep_showcase import automated_mep_showcase

# Custom timing
automated_mep_showcase(
    reveal_start=5000,      # Your choice
    reveal_duration=300     # Your choice
)

EXAMPLES
========

# Quick reveal early in construction:
automated_mep_showcase(1500, 100)

# Multiple reveals (run script 3 times with different starts):
automated_mep_showcase(2000, 150)  # Early
automated_mep_showcase(4000, 150)  # Mid
automated_mep_showcase(6000, 150)  # Late

# Ultra-long showcase for presentations:
automated_mep_showcase(4000, 1000)

# Test camera path without changing animation:
quick_test_camera_only()
"""
