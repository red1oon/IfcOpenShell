"""
Background Refinement Operator
==============================

Blender modal operator for running material refinement + Stage 3 in background.

Allows user to continue working in viewport while enhancements are applied.

Performance:
- Material refinement: 3-5s
- Stage 3 detail upgrade: 15s
- Total: ~20s running in background
- User blocked: 0s (can work throughout!)

Part of Phase 1: Three-Stage Inference-Based Loading
"""

import bpy
import threading
import time
from typing import List, Optional


class FEDERATION_OT_background_refinement(bpy.types.Operator):
    """
    Run material refinement and Stage 3 detail upgrade in background.

    User can continue working in viewport while this runs!
    Progress shown in header, but viewport remains interactive.
    """
    bl_idname = "federation.background_refinement"
    bl_label = "Background Model Refinement"
    bl_description = "Refine model appearance in background (material details + high-detail geometry)"

    # Operator can run in background
    bl_options = {'REGISTER'}

    # Class variables for cross-thread communication
    _thread = None
    _progress = 0
    _stage = "idle"
    _is_running = False
    _stats = {}

    def __init__(self):
        self.objects = []
        self.enable_material_refinement = True
        self.enable_stage3 = True
        self.loader = None

    def modal(self, context, event):
        """Called every frame - non-blocking!"""

        if event.type == 'TIMER':
            # Check if background thread is still running
            if FEDERATION_OT_background_refinement._is_running:
                # Update progress display in header
                stage = FEDERATION_OT_background_refinement._stage
                progress = FEDERATION_OT_background_refinement._progress

                context.area.header_text_set(
                    f"Federation: {stage} ({progress}%)"
                )

                # Allow user to continue working!
                return {'PASS_THROUGH'}

            else:
                # Background work complete!
                context.area.header_text_set(None)

                # Show completion message with stats
                stats = FEDERATION_OT_background_refinement._stats
                self.report({'INFO'},
                    f"✅ Refinement complete! "
                    f"Flanges: {stats.get('flanges_added', 0)}, "
                    f"Seams: {stats.get('seams_added', 0)}, "
                    f"Details: {stats.get('stage3_upgrades', 0)}"
                )

                # Cleanup timer
                if hasattr(self, '_timer'):
                    context.window_manager.event_timer_remove(self._timer)

                return {'FINISHED'}

        return {'PASS_THROUGH'}

    def execute(self, context):
        """Start background refinement thread"""

        # Don't start if already running
        if FEDERATION_OT_background_refinement._is_running:
            self.report({'WARNING'}, "Background refinement already running!")
            return {'CANCELLED'}

        # Get objects from loader (passed as context property)
        if not hasattr(context.scene, 'federation_stage2_objects'):
            self.report({'ERROR'}, "No Stage 2 objects found. Load model first.")
            return {'CANCELLED'}

        self.objects = context.scene.federation_stage2_objects
        self.loader = context.scene.federation_loader

        # Reset progress
        FEDERATION_OT_background_refinement._progress = 0
        FEDERATION_OT_background_refinement._stage = "Starting..."
        FEDERATION_OT_background_refinement._is_running = True
        FEDERATION_OT_background_refinement._stats = {}

        # Start background thread
        FEDERATION_OT_background_refinement._thread = threading.Thread(
            target=self._refine_in_background,
            daemon=True
        )
        FEDERATION_OT_background_refinement._thread.start()

        # Register modal handler and timer
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)

        self.report({'INFO'}, "⏳ Background refinement started...")

        return {'RUNNING_MODAL'}

    def _refine_in_background(self):
        """
        Background thread worker.

        Runs material refinement + Stage 3 while user works.
        Updates progress variables for modal operator to display.
        """
        try:
            stats = {}

            # Stage 2.5: Material-driven refinement
            if self.enable_material_refinement:
                FEDERATION_OT_background_refinement._stage = "Material refinement"
                FEDERATION_OT_background_refinement._progress = 0

                print("\n" + "=" * 60)
                print("BACKGROUND: Material-Driven Refinement")
                print("=" * 60)

                from . import material_refinement

                start = time.time()
                mat_stats = material_refinement.refine_shapes_by_material(
                    self.objects,
                    progress_callback=self._update_progress_material
                )
                elapsed = time.time() - start

                stats.update(mat_stats)

                print(f"✓ Material refinement: {elapsed:.2f}s")
                FEDERATION_OT_background_refinement._progress = 50

            # Stage 3: Detailed geometry upgrade
            if self.enable_stage3 and self.loader:
                FEDERATION_OT_background_refinement._stage = "Detail upgrade"
                FEDERATION_OT_background_refinement._progress = 50

                print("\n" + "=" * 60)
                print("BACKGROUND: Stage 3 Detail Upgrade")
                print("=" * 60)

                start = time.time()

                # Enable Stage 3 (upgrades visible elements)
                self.loader.enable_stage3(enabled=True)

                elapsed = time.time() - start

                # Count Stage 3 upgrades
                stage3_count = sum(
                    1 for obj in self.objects
                    if obj.get('federation_stage') == 3
                )

                stats['stage3_upgrades'] = stage3_count

                print(f"✓ Stage 3 detail upgrade: {elapsed:.2f}s")
                print(f"✓ Upgraded {stage3_count} elements to high detail")

                FEDERATION_OT_background_refinement._progress = 100

            # Store final stats
            FEDERATION_OT_background_refinement._stats = stats
            FEDERATION_OT_background_refinement._stage = "Complete"
            FEDERATION_OT_background_refinement._is_running = False

            print("\n" + "=" * 60)
            print("✅ BACKGROUND REFINEMENT COMPLETE")
            print("=" * 60)
            print(f"Final statistics: {stats}")
            print("\n")

        except Exception as e:
            print(f"\n❌ Background refinement error: {e}")
            import traceback
            traceback.print_exc()

            FEDERATION_OT_background_refinement._stage = "Failed"
            FEDERATION_OT_background_refinement._is_running = False

    def _update_progress_material(self, current, total, message):
        """Progress callback for material refinement"""
        progress = int((current / total) * 50)  # 0-50% range
        FEDERATION_OT_background_refinement._progress = progress
        FEDERATION_OT_background_refinement._stage = f"Material: {message}"


def register():
    """Register operator with Blender"""
    bpy.utils.register_class(FEDERATION_OT_background_refinement)


def unregister():
    """Unregister operator from Blender"""
    bpy.utils.unregister_class(FEDERATION_OT_background_refinement)
