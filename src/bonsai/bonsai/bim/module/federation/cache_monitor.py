"""
Modal operator to monitor background cache baking and notify when complete.

This runs as a non-blocking timer that checks the background process status
and notifies the user when the .blend cache is ready to open.
"""

import bpy
import os
import time
from pathlib import Path


class MonitorCacheBaking(bpy.types.Operator):
    """Monitor background cache baking and notify when complete"""
    bl_idname = "bim.monitor_cache_baking"
    bl_label = "Monitor Cache Baking"

    # Properties to store monitoring state
    cache_path: bpy.props.StringProperty()
    db_path: bpy.props.StringProperty()
    mode: bpy.props.StringProperty()

    _timer = None
    _start_time = 0
    _last_message = ""

    def modal(self, context, event):
        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        from . import blend_cache

        # Get status
        status = blend_cache.get_baking_status(self.cache_path)

        elapsed = time.time() - self._start_time

        # Update header with progress
        if status['status'] == 'running':
            # Show progress in viewport header
            msg = f"⏳ Baking cache: {elapsed:.0f}s - {status['message'][:50]}"
            if msg != self._last_message:
                context.area.header_text_set(msg)
                self._last_message = msg
            return {'PASS_THROUGH'}

        elif status['status'] == 'complete':
            # Cache ready! Notify user (NO auto-load)
            print(f"\n{'='*70}")
            print(f"✅ CACHE BAKING COMPLETE! ({elapsed:.0f}s)")
            print(f"{'='*70}")

            cache_file = Path(self.cache_path).name
            print(f"\n📁 Cache file ready: {cache_file}")
            print(f"   Location: {Path(self.cache_path).parent}")
            print(f"\n🎯 Next Steps:")
            print(f"   1. Save your current work (if needed)")
            print(f"   2. File → Open → {cache_file}")
            print(f"   3. Full geometry ready for deep analysis!")
            print(f"\n💡 Or continue using Preview mode in current session")
            print(f"{'='*70}\n")

            # Clean up temporary files (.log and .complete)
            import os
            try:
                log_file = f"{self.cache_path}.log"
                complete_file = f"{self.cache_path}.complete"
                if os.path.exists(log_file):
                    os.remove(log_file)
                if os.path.exists(complete_file):
                    os.remove(complete_file)
            except Exception as e:
                print(f"⚠️  Could not clean up temp files: {e}")

            # Friendly user notification
            msg = f"Cache ready! ({elapsed:.0f}s) - Open '{cache_file}' to work with full geometry"
            self.report({'INFO'}, msg)
            context.area.header_text_set(None)  # Clear header

            return self.cancel(context)

        elif status['status'] == 'failed':
            # Baking failed - clean up temp files
            import os
            try:
                log_file = f"{self.cache_path}.log"
                complete_file = f"{self.cache_path}.complete"
                if os.path.exists(log_file):
                    os.remove(log_file)
                if os.path.exists(complete_file):
                    os.remove(complete_file)
            except Exception:
                pass  # Ignore cleanup errors on failure

            self.report({'ERROR'}, f"Background baking failed: {status['message']}")
            print(f"\n❌ Background baking failed:")
            print(f"   {status['message']}")
            context.area.header_text_set(None)
            return self.cancel(context)

        # Timeout after 10 minutes
        if elapsed > 600:
            # Clean up temp files on timeout
            import os
            try:
                log_file = f"{self.cache_path}.log"
                complete_file = f"{self.cache_path}.complete"
                if os.path.exists(log_file):
                    os.remove(log_file)
                if os.path.exists(complete_file):
                    os.remove(complete_file)
            except Exception:
                pass  # Ignore cleanup errors

            self.report({'ERROR'}, "Background baking timed out (10 min)")
            print(f"\n❌ Background baking timed out after 10 minutes")
            context.area.header_text_set(None)
            return self.cancel(context)

        return {'PASS_THROUGH'}

    def execute(self, context):
        # Start timer (check every 2 seconds)
        wm = context.window_manager
        self._timer = wm.event_timer_add(2.0, window=context.window)
        wm.modal_handler_add(self)

        self._start_time = time.time()

        print(f"\n🔍 Monitoring background cache baking...")
        print(f"   Cache: {self.cache_path}")
        print(f"   Open .blend when complete")
        print(f"   Your viewport stays responsive!\n")

        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)
        context.area.header_text_set(None)
        return {'CANCELLED'}


def register():
    bpy.utils.register_class(MonitorCacheBaking)


def unregister():
    bpy.utils.unregister_class(MonitorCacheBaking)
