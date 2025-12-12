# Bonsai - OpenBIM Blender Add-on
# River Equipment Placement - UI Module

"""
Equipment UI Panel
==================
N Panel UI for river equipment placement operations.
Provides interface for placement, database, exports, and dashboard.
"""

import bpy
from bpy.types import Panel

from .equipment_config import EQUIPMENT_TYPES, PLACED_EQUIPMENT


class BIM_PT_river_equipment_placement(Panel):
    """River Equipment Placement - N Sidebar"""
    bl_label = "River Equipment"
    bl_idname = "BIM_PT_river_equipment_placement"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "River Equipment"

    def draw(self, context):
        layout = self.layout

        # Header
        header_box = layout.box()
        header_box.label(text="🌊 Equipment Placement POC", icon="WORLD")

        col = header_box.column(align=True)
        col.label(text="Phase 1: Basic Click-to-Place")
        col.label(text="Flat gizmo spheres (no animation)")

        layout.separator()

        # Database operations
        db_box = layout.box()
        db_box.label(text="Database:", icon='DISK_DRIVE')
        row = db_box.row(align=True)
        row.operator("bim.equipment_load_from_db", text="Load from DB", icon='IMPORT')
        row.operator("bim.equipment_select_type", text="Place New", icon='CURSOR')

        layout.separator()

        # River Centerline from OSM
        map_box = layout.box()
        map_box.label(text="🌊 River Centerline (OSM):", icon='CURVE_DATA')
        row = map_box.row(align=True)
        op = row.operator("bim.river_import_osm_centerline", text="Import from OSM", icon='IMPORT')
        op.waterway_type = 'river'

        # Convert and Save buttons (for selected curve)
        if context.active_object and context.active_object.type == 'CURVE' and "gps_coordinates" in context.active_object:
            map_box.separator()
            row = map_box.row(align=True)
            row.operator("object.convert", text="Convert to Mesh", icon='MESH_DATA').target = 'MESH'
            row.operator("bim.river_save_to_database", text="Save to DB", icon='DATABASE')

        # River mesh styling (for converted mesh)
        if context.active_object and context.active_object.type == 'MESH':
            map_box.separator()
            row = map_box.row(align=True)
            row.operator("bim.river_apply_width_material", text="Apply Width (50m)", icon='MOD_SOLIDIFY')
            row.operator("bim.river_snap_markers_to_mesh", text="Snap Markers", icon='SNAP_ON')
            map_box.label(text="Use colorize tool for river color", icon='INFO')

        # Marker realignment tool
        map_box.separator()
        map_box.operator("bim.river_realign_markers", text="Batch Move Markers", icon='ORIENTATION_CURSOR')

        layout.separator()

        # Export and Launch HTML
        html_box = layout.box()
        html_box.label(text="🗺️ Map Export:", icon='WORLD')
        row = html_box.row(align=True)
        row.operator("bim.equipment_export_and_launch_html", text="Launch HTML", icon='URL')
        row = html_box.row(align=True)
        row.operator("bim.equipment_export_kml", text="Export KML (Mobile Apps)", icon='EXPORT')

        layout.separator()

        # Counts
        box = layout.box()
        box.label(text="Placed Equipment:", icon='CHECKMARK')

        # Add total count at the top
        global PLACED_EQUIPMENT
        total_count_temp = sum(len(items) for items in PLACED_EQUIPMENT.values())
        if total_count_temp > 0:
            row = box.row()
            row.label(text=f"Total: {total_count_temp}", icon='SORTSIZE')

        total_count = 0

        # Color emoji mapping
        color_map = {
            'boom_trap': '🟠',
            'water_quality': '🩵',
            'biodiversity': '🟢',
            'wildlife_camera': '🟢',
            'biochar': '🟩',
            'mrf': '🩷',
            'pollutant_sensor': '🟣',
            'flood_monitor': '🔵',
        }

        for equipment_type, items in PLACED_EQUIPMENT.items():
            count = len(items)
            if count > 0:
                row = box.row()
                icon = EQUIPMENT_TYPES[equipment_type]['icon']
                name = EQUIPMENT_TYPES[equipment_type]['name']
                color_emoji = color_map.get(equipment_type, '⚪')
                row.label(text=f"{color_emoji} {name}: {count}", icon=icon)
                total_count += count

        if total_count == 0:
            box.label(text="(None placed yet)")

        layout.separator()

        # Sensor Dashboard - Always available (dual-mode)
        dashboard_box = layout.box()
        dashboard_box.label(text="Dashboard:", icon='GRAPH')

        # Show mode hint based on selection
        if context.active_object:
            patterns = [eq_type.upper() + '_' for eq_type in EQUIPMENT_TYPES.keys()]
            if any(context.active_object.name.upper().startswith(p) for p in patterns):
                dashboard_box.label(text="Mode: Marker Sensors", icon='DOT')
        else:
            dashboard_box.label(text="Mode: Global Alerts", icon='WORLD')

        row = dashboard_box.row(align=True)
        row.scale_y = 1.4
        row.operator("bim.equipment_view_sensor_dashboard", text="📊 Sensor Dashboard", icon='GRAPH')

        layout.separator()

        # View Details (if equipment selected)
        if context.active_object:
            patterns = [eq_type.upper() + '_' for eq_type in EQUIPMENT_TYPES.keys()]
            if any(context.active_object.name.upper().startswith(p) for p in patterns):
                detail_box = layout.box()
                detail_box.label(text="Selected Equipment:", icon='OUTLINER_OB_EMPTY')
                detail_box.label(text=f"  {context.active_object.name}")
                detail_box.operator("bim.equipment_view_properties", text="View Details", icon='VIEWZOOM')
                layout.separator()

        # Actions
        col = layout.column(align=True)
        col.alert = True
        col.operator("bim.equipment_clear_all", text="Clear All", icon='TRASH')

        layout.separator()

        # Office Address for navigation
        address_box = layout.box()
        address_box.label(text="Office/Depot Address:", icon='HOME')
        col = address_box.column(align=True)
        col.scale_y = 0.8
        col.label(text="Starting point for directions to equipment")
        props = context.scene.BIMFederationProperties
        address_box.prop(props, "office_address", text="")

        layout.separator()

        # GPS Calibration Utils
        gps_utils_box = layout.box()
        gps_utils_box.label(text="GPS Calibration Utils:", icon='DRIVER_DISTANCE')
        col = gps_utils_box.column(align=True)
        col.operator("bim.equipment_recalibrate_gps_from_truth", text="Recalibrate GPS from Truth File", icon='FILE_REFRESH')
        col.operator("bim.equipment_compare_gps_blend_db", text="Compare GPS: Blend ↔ DB", icon='COMMUNITY')

        layout.separator()

        # Debug info
        debug_box = layout.box()
        debug_box.label(text="Debug Info:", icon='INFO')
        debug_box.label(text=f"Log: ~/Documents/bonsai/consolelogs/")
        debug_box.label(text="river_equipment_placement.txt")
        debug_box.operator("bim.equipment_dump_gps", text="Dump GPS to File", icon='EXPORT')
