"""
Sectional Reveal Script - Show Hidden MEP Systems
--------------------------------------------------
Hides building envelope (ARC + STR) midway through animation
to dramatically reveal hidden MEP systems (ACMV, ELEC, FP).

Usage:
1. Run AFTER creating 4D animation
2. Sets up automatic hide/show at specified frames
3. Just scrub timeline or play - envelope hides automatically!
"""

import bpy


def add_sectional_reveal(
    reveal_start_frame: int = 4000,  # When to hide envelope (midpoint)
    reveal_duration: int = 100,       # How many frames to stay revealed
    disciplines_to_hide: list = ['ARC', 'STR']  # Building envelope
):
    """
    Add sectional reveal effect to existing animation.

    Args:
        reveal_start_frame: Frame when envelope hides (default: 4000 = ~46% through)
        reveal_duration: How long envelope stays hidden (default: 100 frames = ~50 days)
        disciplines_to_hide: Which disciplines to hide (default: ARC + STR)

    Timeline:
        Frame 0-4000: Normal construction (everything appears progressively)
        Frame 4000: ARC+STR hide (MEP systems visible!)
        Frame 4100: ARC+STR reappear (back to normal)
        Frame 4101+: Continue normal construction
    """

    print(f"\n{'='*60}")
    print(f"🎭 SECTIONAL REVEAL - MEP Systems Visualization")
    print(f"{'='*60}")
    print(f"Reveal starts: Frame {reveal_start_frame}")
    print(f"Duration: {reveal_duration} frames (~{reveal_duration/2:.0f} days)")
    print(f"Hiding: {', '.join(disciplines_to_hide)}")
    print(f"\nProcessing objects...")

    reveal_end_frame = reveal_start_frame + reveal_duration
    count = 0

    for obj in bpy.context.scene.objects:
        # Skip objects without discipline property
        if 'discipline' not in obj:
            continue

        # Only process envelope disciplines (ARC, STR)
        if obj['discipline'] not in disciplines_to_hide:
            continue

        # Add reveal keyframes (keep existing animation intact)

        # At reveal_start: Hide the object
        obj.hide_viewport = True
        obj.hide_render = True
        obj.keyframe_insert('hide_viewport', frame=reveal_start_frame)
        obj.keyframe_insert('hide_render', frame=reveal_start_frame)

        # At reveal_end: Show the object again
        obj.hide_viewport = False
        obj.hide_render = False
        obj.keyframe_insert('hide_viewport', frame=reveal_end_frame)
        obj.keyframe_insert('hide_render', frame=reveal_end_frame)

        count += 1

        if count % 1000 == 0:
            print(f"   Processed {count:,} envelope objects...")

    print(f"\n✅ Sectional reveal complete!")
    print(f"   Modified {count:,} objects ({', '.join(disciplines_to_hide)})")
    print(f"\n{'='*60}")
    print(f"USAGE:")
    print(f"{'='*60}")
    print(f"1. Scrub to frame {reveal_start_frame} → Envelope HIDES")
    print(f"2. See MEP systems inside (ACMV ducts, ELEC conduits, FP pipes)")
    print(f"3. Scrub to frame {reveal_end_frame} → Envelope REAPPEARS")
    print(f"4. Press SPACEBAR to watch automatic reveal during playback")
    print(f"\n💡 TIP: Set camera angle BEFORE frame {reveal_start_frame}")
    print(f"   for best MEP visualization (e.g., inside building view)")
    print(f"{'='*60}\n")

    return {
        'objects_modified': count,
        'reveal_start': reveal_start_frame,
        'reveal_end': reveal_end_frame,
        'disciplines_hidden': disciplines_to_hide
    }


def add_multiple_reveals(frames: list = [2000, 4000, 6000], duration: int = 100):
    """
    Add multiple sectional reveals at different points.

    Args:
        frames: List of frame numbers for reveals
        duration: How long each reveal lasts

    Example:
        Frame 2000: Show Level 0 MEP (early construction)
        Frame 4000: Show Level 1 MEP (mid construction)
        Frame 6000: Show Level 2 MEP (late construction)
    """
    print(f"\n🎭 MULTIPLE REVEALS - {len(frames)} sectional cuts")

    for i, frame in enumerate(frames):
        print(f"\nReveal {i+1}/{len(frames)} at frame {frame}")
        add_sectional_reveal(
            reveal_start_frame=frame,
            reveal_duration=duration
        )

    print(f"\n✅ {len(frames)} reveals configured!")


def add_progressive_transparency(
    start_frame: int = 4000,
    duration: int = 50,
    disciplines: list = ['ARC', 'STR']
):
    """
    ADVANCED: Fade envelope to transparency instead of hiding.

    Requires: Materials with transparency support
    More visually appealing but slower performance.
    """
    print(f"\n🎨 PROGRESSIVE TRANSPARENCY (advanced)")
    print(f"Note: This modifies materials - may take longer")

    count = 0

    for obj in bpy.context.scene.objects:
        if 'discipline' not in obj or obj['discipline'] not in disciplines:
            continue

        if obj.type != 'MESH' or not obj.data.materials:
            continue

        # Enable transparency in material
        mat = obj.data.materials[0]
        mat.blend_method = 'BLEND'

        # Get shader node
        nodes = mat.node_tree.nodes
        principled = nodes.get('Principled BSDF')

        if principled:
            # Fade to transparent
            principled.inputs['Alpha'].default_value = 1.0
            principled.inputs['Alpha'].keyframe_insert(
                data_path='default_value',
                frame=start_frame
            )

            principled.inputs['Alpha'].default_value = 0.1  # 10% visible
            principled.inputs['Alpha'].keyframe_insert(
                data_path='default_value',
                frame=start_frame + duration
            )

            # Fade back to opaque
            principled.inputs['Alpha'].default_value = 1.0
            principled.inputs['Alpha'].keyframe_insert(
                data_path='default_value',
                frame=start_frame + duration * 2
            )

            count += 1

    print(f"✅ Added transparency fade to {count} objects")


# ==============================================================================
# READY-TO-USE PRESETS
# ==============================================================================

def preset_single_reveal_midpoint():
    """
    PRESET 1: Single reveal at midpoint (frame 4000)
    Best for: General MEP showcase
    """
    print("🎯 PRESET 1: Single Midpoint Reveal")
    add_sectional_reveal(
        reveal_start_frame=4000,  # ~46% through project
        reveal_duration=200,       # Stay revealed for ~100 days
        disciplines_to_hide=['ARC', 'STR']
    )


def preset_three_stage_reveal():
    """
    PRESET 2: Three reveals showing MEP at different stages
    Best for: Progressive MEP installation showcase
    """
    print("🎯 PRESET 2: Three-Stage Progressive Reveal")
    add_multiple_reveals(
        frames=[2000, 4500, 7000],  # Early, mid, late construction
        duration=150
    )


def preset_long_section():
    """
    PRESET 3: Extended reveal for detailed MEP exploration
    Best for: Detailed walkthroughs, presentations
    """
    print("🎯 PRESET 3: Extended Section (500 frames)")
    add_sectional_reveal(
        reveal_start_frame=4000,
        reveal_duration=500,  # ~250 days visible
        disciplines_to_hide=['ARC', 'STR']
    )


def preset_mep_only_reveal():
    """
    PRESET 4: Hide everything except MEP at specific frame
    Best for: Pure MEP coordination review
    """
    print("🎯 PRESET 4: MEP-Only Reveal")
    add_sectional_reveal(
        reveal_start_frame=4000,
        reveal_duration=300,
        disciplines_to_hide=['ARC', 'STR', 'CW', 'FP']  # Hide walls, ceilings too
    )


# ==============================================================================
# MAIN EXECUTION
# ==============================================================================

if __name__ == "__main__":
    print("\n" + "="*60)
    print("SECTIONAL REVEAL - MEP Systems Visualization")
    print("="*60)
    print("\nAvailable presets:")
    print("1. preset_single_reveal_midpoint()     - Simple reveal at 46%")
    print("2. preset_three_stage_reveal()         - Three reveals (early/mid/late)")
    print("3. preset_long_section()               - Extended 500-frame reveal")
    print("4. preset_mep_only_reveal()            - Hide all except MEP")
    print("\nCustom:")
    print("5. add_sectional_reveal(frame, duration, disciplines)")
    print("6. add_progressive_transparency(...)   - Fancy fade effect")

    print("\n" + "="*60)
    print("RUNNING: Preset 1 (Single Midpoint Reveal)")
    print("="*60)

    # RUN DEFAULT PRESET
    preset_single_reveal_midpoint()

    print("\n💾 Don't forget to save (Ctrl+S) after running!")
    print("\n📹 CAMERA TIP:")
    print("   At frame 3900: Set camera inside building")
    print("   At frame 4000: Walls hide, camera sees MEP!")
    print("   At frame 4200: Walls return\n")


# ==============================================================================
# HOW TO USE THIS SCRIPT
# ==============================================================================
"""
METHOD 1: Run in Blender Python Console
========================================
1. Open your animated .blend file
2. Window → Toggle System Console (to see output)
3. Switch to Scripting workspace
4. Open this file: sectional_reveal_mep.py
5. Click "Run Script" button (▶)
6. Watch console for progress
7. Ctrl+S to save
8. Scrub to frame 4000 → See envelope hide!

METHOD 2: Run from Terminal (Background)
=========================================
~/blender-4.2.14/blender WORK_DIR/databases/enhanced_federation_4d_animated.blend \\
    --background \\
    --python WORK_DIR/test_outputs/sectional_reveal_mep.py

METHOD 3: Custom Frame/Duration
================================
# In Blender Python console:
import sys
sys.path.insert(0, "/home/red1/Projects/IfcOpenShell/WORK_DIR/test_outputs")
from sectional_reveal_mep import add_sectional_reveal

# Custom reveal
add_sectional_reveal(
    reveal_start_frame=5000,   # Your choice
    reveal_duration=250,        # Your choice
    disciplines_to_hide=['ARC', 'STR', 'CW']  # Your choice
)

EXAMPLES OF DRAMATIC REVEALS
=============================

# Show foundation MEP before slab pour:
add_sectional_reveal(1500, 100, ['ARC', 'STR'])

# Show ceiling MEP before drywall:
add_sectional_reveal(6500, 200, ['ARC'])

# Progressive basement → roof reveal:
add_multiple_reveals([1000, 3000, 5000, 7000], duration=100)

# Ultra-long reveal for walkthroughs:
add_sectional_reveal(4000, 1000, ['ARC', 'STR'])
"""
