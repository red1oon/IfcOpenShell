# Bonsai - OpenBIM Blender Add-on
# River Equipment Monitoring Module
# Item 11: River Monitoring Equipment & Ecosystem

"""
River Equipment Monitoring
===========================
Comprehensive river monitoring system with equipment placement,
sensor dashboards, and OSM integration.

Modules:
- equipment_placement: Main equipment placement and sensor dashboard
- equipment_sensor: Sensor status calculation and visualization
- equipment_gizmo: GPU-drawn gizmo spheres for equipment markers
- centerline_osm: OpenStreetMap river centerline import and styling
"""

from . import equipment_placement
from . import equipment_gizmo
from . import centerline_osm
from . import gps_sync_handler

# Expose data structures that may be accessed from outside
from .equipment_placement import (
    EQUIPMENT_TYPES,
    PLACED_EQUIPMENT,
    SENSOR_TYPE_ICONS,
    SENSOR_TYPE_COLORS,
)

# Expose classes for registration in federation module
classes = (
    # Equipment Placement UI Panel
    equipment_placement.BIM_PT_river_equipment_placement,

    # Equipment Placement Operators
    equipment_placement.BIM_OT_equipment_select_type,
    equipment_placement.BIM_OT_equipment_place_marker,
    equipment_placement.BIM_OT_equipment_load_from_db,
    equipment_placement.BIM_OT_equipment_view_properties,
    equipment_placement.BIM_OT_equipment_open_google_maps,
    equipment_placement.BIM_OT_equipment_export_and_launch_html,
    equipment_placement.BIM_OT_equipment_export_kml,
    equipment_placement.BIM_OT_equipment_export_mobile_html,
    equipment_placement.BIM_OT_equipment_view_sensor_dashboard,
    equipment_placement.BIM_OT_equipment_clear_all,

    # River Centerline - OpenStreetMap Integration
    centerline_osm.BIM_OT_river_import_osm_centerline,
    centerline_osm.BIM_OT_river_simplify_centerline,
    centerline_osm.BIM_OT_river_save_to_database,
    centerline_osm.BIM_OT_river_realign_markers,
    centerline_osm.BIM_OT_river_apply_width_material,
    centerline_osm.BIM_OT_river_snap_markers_to_mesh,

    # 7D Maintenance - Right-click Context Menu
    equipment_placement.BIM_MT_equipment_context_menu,
    equipment_placement.BIM_OT_equipment_view_pm_schedule,
    equipment_placement.BIM_OT_equipment_log_breakdown,
    equipment_placement.BIM_OT_equipment_create_work_order,

    # Equipment Gizmos (GPU-drawn spheres)
    equipment_gizmo.EquipmentMarkerGizmo,
    equipment_gizmo.EquipmentMarkerGizmoGroup,

    # GPS Auto-Sync
    gps_sync_handler.BIM_OT_enable_gps_auto_sync,
    gps_sync_handler.BIM_OT_disable_gps_auto_sync,
    gps_sync_handler.BIM_OT_update_selected_gps,
    gps_sync_handler.BIM_OT_recalibrate_gps_anchor,
    gps_sync_handler.BIM_PT_gps_auto_sync,
)


def register():
    """Called when river module is registered"""
    gps_sync_handler.register()


def unregister():
    """Called when river module is unregistered"""
    gps_sync_handler.unregister()
