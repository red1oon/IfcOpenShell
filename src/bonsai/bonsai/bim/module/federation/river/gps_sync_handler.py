# Bonsai - OpenBIM Blender Add-on
# GPS Auto-Sync Handler - Updates GPS when objects move in Blender

"""
GPS Auto-Sync Handler
=====================
Automatically updates GPS coordinates (latitude/longitude) when equipment
objects are moved in Blender 3D space.

**Algorithm:**
Uses affine transformation from georef_config database table.
- Loads calibration bounds on initialization
- Converts Blender XY → GPS using normalized interpolation
- No anchor needed - uses full georeferencing system
- Blender-only updates - no database sync (backward compatible)

**Affine Transformation:**
lon = lon_min + (x - x_min) / (x_max - x_min) * (lon_max - lon_min)
lat = lat_min + (y - y_min) / (y_max - y_min) * (lat_max - lat_min)
"""

import bpy
from bpy.app.handlers import persistent, depsgraph_update_post
import sqlite3
from pathlib import Path


class GPSAutoSync:
    """Handles automatic GPS synchronization when objects move"""

    def __init__(self):
        self.enabled = False
        # Affine calibration bounds (loaded from georef_config)
        self.x_min = None
        self.x_max = None
        self.y_min = None
        self.y_max = None
        self.lon_min = None
        self.lon_max = None
        self.lat_min = None
        self.lat_max = None
        self.tracked_objects = set()
        self.last_positions = {}

    def enable(self):
        """Enable GPS auto-sync (Blender-only, no database)"""
        # Load affine calibration from database
        if not self._load_affine_calibration():
            return False

        self.enabled = True
        print(f"✓ GPS Auto-Sync: Enabled (Affine Calibration)")
        print(f"  Blender X: {self.x_min:.2f} to {self.x_max:.2f} m")
        print(f"  Blender Y: {self.y_min:.2f} to {self.y_max:.2f} m")
        print(f"  GPS Lon:   {self.lon_min:.6f}° to {self.lon_max:.6f}° E")
        print(f"  GPS Lat:   {self.lat_min:.6f}° to {self.lat_max:.6f}° N")
        return True

    def _load_affine_calibration(self):
        """Load affine transformation bounds from database georef_config table"""
        db_path = Path.home() / "Projects/IfcOpenShell/WORK_DIR/RIVER/databases/klang_river_perfect.db"

        if not db_path.exists():
            print(f"⚠️  GPS Auto-Sync: Database not found: {db_path}")
            return False

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            cursor.execute("""
                SELECT blender_x_min, blender_x_max, blender_y_min, blender_y_max,
                       gps_lon_min, gps_lon_max, gps_lat_min, gps_lat_max
                FROM georef_config
                WHERE id = 1
            """)

            row = cursor.fetchone()
            conn.close()

            if not row or not all(row):
                print(f"⚠️  GPS Auto-Sync: Georef calibration not found in database")
                return False

            self.x_min, self.x_max, self.y_min, self.y_max, \
            self.lon_min, self.lon_max, self.lat_min, self.lat_max = row

            return True

        except Exception as e:
            print(f"⚠️  GPS Auto-Sync: Failed to load calibration - {e}")
            return False

    def disable(self):
        """Disable GPS auto-sync"""
        self.enabled = False
        self.tracked_objects.clear()
        self.last_positions.clear()
        print("✓ GPS Auto-Sync: Disabled")

    def track_equipment_objects(self):
        """Auto-track all equipment objects in scene"""
        count = 0
        for obj in bpy.data.objects:
            if self._is_equipment_object(obj):
                self.tracked_objects.add(obj.name)
                self.last_positions[obj.name] = obj.location.copy()
                count += 1
        print(f"✓ GPS Auto-Sync: Tracking {count} equipment objects")

    def _is_equipment_object(self, obj):
        """Check if object is equipment marker"""
        equipment_keywords = ['BOOM', 'PUMP', 'GATE', 'SENSOR', 'WATER_QUALITY',
                             'BIODIVERSITY', 'WILDLIFE', 'BIOCHAR', 'MRF', 'POLLUTANT',
                             'FLOOD', 'ISLET', 'MANGROVE']
        return any(keyword in obj.name.upper() for keyword in equipment_keywords)

    def update_gps_for_object(self, obj):
        """Update GPS coordinates for a single object using affine transformation"""
        if not self.enabled:
            return False

        try:
            # Get current Blender position
            x, y = obj.location.x, obj.location.y

            # Affine transformation: Blender XY → GPS
            # Normalize to [0, 1]
            x_norm = (x - self.x_min) / (self.x_max - self.x_min) if self.x_max != self.x_min else 0.5
            y_norm = (y - self.y_min) / (self.y_max - self.y_min) if self.y_max != self.y_min else 0.5

            # Map to GPS coordinates
            lon = self.lon_min + x_norm * (self.lon_max - self.lon_min)
            lat = self.lat_min + y_norm * (self.lat_max - self.lat_min)

            # Update object custom properties (Blender-only)
            obj["latitude"] = lat
            obj["longitude"] = lon

            # Update last known position
            self.last_positions[obj.name] = obj.location.copy()

            return True

        except Exception as e:
            print(f"⚠️  GPS Auto-Sync: Failed to update {obj.name} - {e}")
            return False

    def check_for_updates(self, scene, depsgraph):
        """Check for object position changes (called by depsgraph handler)"""
        if not self.enabled:
            return

        # Check each tracked object
        for obj_name in list(self.tracked_objects):
            obj = bpy.data.objects.get(obj_name)
            if not obj:
                continue

            # Check if position changed
            last_pos = self.last_positions.get(obj_name)
            if last_pos is None:
                self.last_positions[obj_name] = obj.location.copy()
                continue

            # Compare X and Y (ignore Z for GPS)
            current_pos = obj.location
            if abs(current_pos.x - last_pos.x) > 0.01 or abs(current_pos.y - last_pos.y) > 0.01:
                # Position changed - update GPS using affine transformation
                if self.update_gps_for_object(obj):
                    print(f"✓ GPS Updated: {obj_name} → Lat {obj['latitude']:.6f}, Lon {obj['longitude']:.6f}")


# Global instance
_gps_sync = GPSAutoSync()


# =============================================================================
# DEPSGRAPH HANDLER
# =============================================================================

@persistent
def gps_sync_depsgraph_handler(scene, depsgraph):
    """Handler called on every depsgraph update"""
    _gps_sync.check_for_updates(scene, depsgraph)


# =============================================================================
# OPERATORS
# =============================================================================

class BIM_OT_enable_gps_auto_sync(bpy.types.Operator):
    """Enable automatic GPS updates when objects move"""
    bl_idname = "bim.enable_gps_auto_sync"
    bl_label = "Enable GPS Auto-Sync"
    bl_description = "Auto-update GPS when objects move (uses affine calibration from georef_config)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if _gps_sync.enable():
            # Track all equipment objects
            _gps_sync.track_equipment_objects()

            # Register depsgraph handler
            if gps_sync_depsgraph_handler not in depsgraph_update_post:
                depsgraph_update_post.append(gps_sync_depsgraph_handler)

            self.report({'INFO'}, "GPS Auto-Sync enabled (Affine Calibration)")
        else:
            self.report({'ERROR'}, "Failed to enable GPS Auto-Sync - check georef_config table")

        return {'FINISHED'}


class BIM_OT_disable_gps_auto_sync(bpy.types.Operator):
    """Disable automatic GPS updates"""
    bl_idname = "bim.disable_gps_auto_sync"
    bl_label = "Disable GPS Auto-Sync"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        _gps_sync.disable()

        # Unregister depsgraph handler
        if gps_sync_depsgraph_handler in depsgraph_update_post:
            depsgraph_update_post.remove(gps_sync_depsgraph_handler)

        self.report({'INFO'}, "GPS Auto-Sync disabled")
        return {'FINISHED'}


class BIM_OT_update_selected_gps(bpy.types.Operator):
    """Manually update GPS for selected objects"""
    bl_idname = "bim.update_selected_gps"
    bl_label = "Update GPS for Selected"
    bl_description = "Recalculate GPS for selected objects based on current position"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _gps_sync.enabled:
            self.report({'ERROR'}, "GPS Auto-Sync not enabled. Enable it first.")
            return {'CANCELLED'}

        updated = 0
        for obj in context.selected_objects:
            if _gps_sync.update_gps_for_object(obj):
                updated += 1

        self.report({'INFO'}, f"Updated GPS for {updated} objects")
        return {'FINISHED'}


class BIM_OT_recalibrate_gps_affine(bpy.types.Operator):
    """Reload affine calibration from database"""
    bl_idname = "bim.recalibrate_gps_affine"
    bl_label = "Reload Affine Calibration"
    bl_description = "Reload affine transformation bounds from georef_config table"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if _gps_sync._load_affine_calibration():
            self.report({'INFO'}, "Affine calibration reloaded from database")
        else:
            self.report({'ERROR'}, "Failed to reload calibration - check georef_config table")

        return {'FINISHED'}


# =============================================================================
# UI PANEL
# =============================================================================

class BIM_PT_gps_auto_sync(bpy.types.Panel):
    """GPS Auto-Sync Panel"""
    bl_label = "GPS Auto-Sync"
    bl_idname = "BIM_PT_gps_auto_sync"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'River Equipment'
    bl_parent_id = "BIM_PT_river_equipment_placement"

    def draw(self, context):
        layout = self.layout

        # Toggle checkbox
        row = layout.row()
        if _gps_sync.enabled:
            row.operator("bim.disable_gps_auto_sync", text="☑ Auto-Update GPS on Move", depress=True)
        else:
            row.operator("bim.enable_gps_auto_sync", text="☐ Auto-Update GPS on Move")

        if _gps_sync.enabled:
            layout.separator()
            box = layout.box()
            box.label(text="✓ Active (Affine Calibration)", icon='CHECKMARK')

            layout.separator()
            layout.operator("bim.update_selected_gps", text="Update Selected GPS", icon='FILE_REFRESH')
            layout.operator("bim.recalibrate_gps_affine", text="Reload Calibration", icon='FILE_REFRESH')

        layout.separator()
        info_box = layout.box()
        info_box.label(text="How it works:", icon='INFO')
        info_box.label(text="• Move any object in viewport")
        info_box.label(text="• GPS auto-updates via affine transform")
        info_box.label(text="• Uses georef_config bounds")


# =============================================================================
# REGISTRATION
# =============================================================================

classes = (
    BIM_OT_enable_gps_auto_sync,
    BIM_OT_disable_gps_auto_sync,
    BIM_OT_update_selected_gps,
    BIM_OT_recalibrate_gps_affine,
    BIM_PT_gps_auto_sync,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # Auto-enable GPS sync on startup
    if _gps_sync.enable():
        _gps_sync.track_equipment_objects()
        if gps_sync_depsgraph_handler not in depsgraph_update_post:
            depsgraph_update_post.append(gps_sync_depsgraph_handler)
        print("✓ GPS Auto-Sync enabled by default")


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    # Clean up handler
    if gps_sync_depsgraph_handler in depsgraph_update_post:
        depsgraph_update_post.remove(gps_sync_depsgraph_handler)
