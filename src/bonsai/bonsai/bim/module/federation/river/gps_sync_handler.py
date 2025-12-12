# Bonsai - OpenBIM Blender Add-on
# GPS Auto-Sync Handler - Updates GPS when objects move in Blender

"""
GPS Auto-Sync Handler
=====================
Automatically updates GPS coordinates (latitude/longitude) when equipment
objects are moved in Blender 3D space.

**Algorithm:**
Uses BOOM_TRAP_002 as the ANCHOR reference point (hard-coded for now).
- Anchor GPS is never changed (considered ground truth)
- All other objects' GPS calculated relative to anchor using scale factors
- Scale: GPS degrees per Blender unit (calculated from anchor + one other point)
- Blender-only updates - no database sync (backward compatible)

**Note to Users:**
BOOM_TRAP_002 is the GPS anchor. Do not move this object unless you recalibrate.
Later: Will support dynamic anchor selection when other markers verified to river mesh.
"""

import bpy
from bpy.app.handlers import persistent, depsgraph_update_post


class GPSAutoSync:
    """Handles automatic GPS synchronization when objects move"""

    # Hard-coded anchor for now (verified ground truth)
    ANCHOR_NAME = "BOOM_TRAP_002"

    def __init__(self):
        self.enabled = False
        self.anchor_obj_name = None
        self.anchor_blender_pos = None  # (x, y)
        self.anchor_gps = None  # (lat, lon)
        self.scale_x_to_lon = None  # Longitude degrees per Blender X unit
        self.scale_y_to_lat = None  # Latitude degrees per Blender Y unit
        self.tracked_objects = set()
        self.last_positions = {}

    def enable(self):
        """Enable GPS auto-sync (Blender-only, no database)"""
        # Find anchor object and calculate scale
        if not self._calibrate_from_scene():
            return False

        self.enabled = True
        print(f"✓ GPS Auto-Sync: Enabled")
        print(f"  Anchor: {self.anchor_obj_name}")
        print(f"  Scale: {self.scale_x_to_lon:.10f} lon/X, {self.scale_y_to_lat:.10f} lat/Y")
        return True

    def _calibrate_from_scene(self):
        """Find anchor object and calculate GPS scale factors"""
        # Find all equipment objects with GPS
        equipment = []
        for obj in bpy.data.objects:
            if self._is_equipment_object(obj):
                lat = obj.get('latitude')
                lon = obj.get('longitude')
                if lat is not None and lon is not None:
                    equipment.append({
                        'obj': obj,
                        'name': obj.name,
                        'x': obj.location.x,
                        'y': obj.location.y,
                        'lat': lat,
                        'lon': lon
                    })

        if len(equipment) < 2:
            print(f"⚠️  GPS Auto-Sync: Need at least 2 equipment objects with GPS")
            return False

        # Find anchor (hard-coded BOOM_TRAP_002)
        anchor = next((e for e in equipment if e['name'] == self.ANCHOR_NAME), None)
        if not anchor:
            print(f"⚠️  GPS Auto-Sync: Anchor {self.ANCHOR_NAME} not found")
            return False

        self.anchor_obj_name = anchor['name']
        self.anchor_blender_pos = (anchor['x'], anchor['y'])
        self.anchor_gps = (anchor['lat'], anchor['lon'])

        # Find eastmost-northmost for scale calculation (maximum X+Y)
        opposite = max(equipment, key=lambda e: e['x'] + e['y'])

        # Calculate scale factors
        dx = opposite['x'] - anchor['x']
        dy = opposite['y'] - anchor['y']
        dlon = opposite['lon'] - anchor['lon']
        dlat = opposite['lat'] - anchor['lat']

        if abs(dx) < 0.1 or abs(dy) < 0.1:
            print(f"⚠️  GPS Auto-Sync: Objects too close for calibration")
            return False

        self.scale_x_to_lon = dlon / dx
        self.scale_y_to_lat = dlat / dy

        return True

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
                             'BIODIVERSITY', 'WILDLIFE', 'BIOCHAR', 'MRF', 'POLLUTANT', 'FLOOD']
        return any(keyword in obj.name.upper() for keyword in equipment_keywords)

    def update_gps_for_object(self, obj):
        """Update GPS coordinates for a single object"""
        if not self.enabled:
            return False

        # Don't update anchor object
        if obj.name == self.anchor_obj_name:
            return False

        try:
            # Get current Blender position
            x, y = obj.location.x, obj.location.y

            # Calculate GPS relative to anchor
            dx = x - self.anchor_blender_pos[0]
            dy = y - self.anchor_blender_pos[1]

            lon = self.anchor_gps[1] + (dx * self.scale_x_to_lon)
            lat = self.anchor_gps[0] + (dy * self.scale_y_to_lat)

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
            # Skip anchor
            if obj_name == self.anchor_obj_name:
                continue

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
                # Position changed - update GPS
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
    bl_description = "Auto-update GPS when objects move (BOOM_TRAP_002 is anchor)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if _gps_sync.enable():
            # Track all equipment objects
            _gps_sync.track_equipment_objects()

            # Register depsgraph handler
            if gps_sync_depsgraph_handler not in depsgraph_update_post:
                depsgraph_update_post.append(gps_sync_depsgraph_handler)

            self.report({'INFO'}, f"GPS Auto-Sync enabled (Anchor: {_gps_sync.anchor_obj_name})")
        else:
            self.report({'ERROR'}, "Failed to enable GPS Auto-Sync")

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


class BIM_OT_recalibrate_gps_anchor(bpy.types.Operator):
    """Recalibrate GPS anchor and scale from current scene"""
    bl_idname = "bim.recalibrate_gps_anchor"
    bl_label = "Recalibrate GPS Anchor"
    bl_description = "Recalculate anchor point and scale factors from current equipment positions"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if _gps_sync._calibrate_from_scene():
            self.report({'INFO'}, f"Recalibrated (Anchor: {_gps_sync.anchor_obj_name})")
        else:
            self.report({'ERROR'}, "Failed to recalibrate")

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
            box.label(text=f"✓ Active (Anchor: {_gps_sync.anchor_obj_name})", icon='CHECKMARK')

            layout.separator()
            layout.operator("bim.update_selected_gps", text="Update Selected GPS", icon='FILE_REFRESH')
            layout.operator("bim.recalibrate_gps_anchor", text="Recalibrate Anchor", icon='MODIFIER')

        layout.separator()
        info_box = layout.box()
        info_box.label(text="How it works:", icon='INFO')
        info_box.label(text="• Move any object in viewport")
        info_box.label(text="• GPS auto-updates based on X/Y")
        info_box.label(text="• Anchor: BOOM_TRAP_002")


# =============================================================================
# REGISTRATION
# =============================================================================

classes = (
    BIM_OT_enable_gps_auto_sync,
    BIM_OT_disable_gps_auto_sync,
    BIM_OT_update_selected_gps,
    BIM_OT_recalibrate_gps_anchor,
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
