"""
Modal operator to monitor background cache baking and auto-load when complete.

This runs as a non-blocking timer that checks the background process status
and automatically loads the cache when ready.
"""

import bpy
import os
import time


class MonitorCacheBaking(bpy.types.Operator):
    """Monitor background cache baking and auto-load when complete"""
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
            # Cache ready! Auto-load it
            print(f"\n{'='*70}")
            print(f"✅ CACHE BAKING COMPLETE! ({elapsed:.0f}s)")
            print(f"{'='*70}")
            print(f"Auto-loading cache into viewport...")

            try:
                # Load from cache
                blend_cache.load_from_cache(context, self.db_path)

                self.report({'INFO'}, f"Cache loaded! ({elapsed:.0f}s total)")
                context.area.header_text_set(None)  # Clear header

                print(f"\n✅ Cache loaded successfully!")
                print(f"   Total time: {elapsed:.0f}s (background baking + loading)")
                print(f"   Next time: ~15s (load from cache only)")
                print(f"{'='*70}\n")

            except Exception as e:
                self.report({'ERROR'}, f"Auto-load failed: {e}")
                print(f"❌ Auto-load failed: {e}")
                context.area.header_text_set(None)

            return self.cancel(context)

        elif status['status'] == 'failed':
            # Baking failed
            self.report({'ERROR'}, f"Background baking failed: {status['message']}")
            print(f"\n❌ Background baking failed:")
            print(f"   {status['message']}")
            context.area.header_text_set(None)
            return self.cancel(context)

        # Timeout after 10 minutes
        if elapsed > 600:
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
        print(f"   Will auto-load when complete")
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
