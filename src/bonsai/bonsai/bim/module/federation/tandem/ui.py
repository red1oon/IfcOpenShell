"""
Digital Twin - Blender UI
Properties and panels for asset management

UI Location: Properties → Scene → Digital Twin
"""

import bpy
from bpy.types import Panel, PropertyGroup, UIList
from bpy.props import (
    StringProperty,
    IntProperty,
    EnumProperty,
    CollectionProperty,
    PointerProperty
)


class BIMTandemAssetItem(PropertyGroup):
    """Asset list item for UI"""
    guid: StringProperty(name="GUID")
    name: StringProperty(name="Name")
    ifc_class: StringProperty(name="IFC Class")
    discipline: StringProperty(name="Discipline")
    status: StringProperty(name="Status")
    condition: StringProperty(name="Condition")


class BIMTandemProperties(PropertyGroup):
    """Digital Twin scene properties"""

    database_path: StringProperty(
        name="Database Path",
        description="Path to digital twin SQLite database",
        subtype='FILE_PATH'
    )

    last_sync: IntProperty(
        name="Last Sync Frame",
        description="Frame when database was last synced",
        default=0
    )

    # Filters
    filter_discipline: EnumProperty(
        name="Discipline",
        description="Filter assets by discipline",
        items=[
            ('ALL', 'All', 'Show all disciplines'),
            ('ACMV', 'ACMV', 'HVAC/Mechanical'),
            ('ELEC', 'Electrical', 'Electrical systems'),
            ('PLB', 'Plumbing', 'Plumbing/Sanitary'),
            ('FP', 'Fire Protection', 'Fire protection systems'),
            ('Other', 'Other', 'Other disciplines'),
        ],
        default='ALL'
    )

    filter_status: EnumProperty(
        name="Status",
        description="Filter assets by status",
        items=[
            ('ALL', 'All', 'Show all statuses'),
            ('Active', 'Active', 'Active assets'),
            ('Inactive', 'Inactive', 'Inactive assets'),
            ('Decommissioned', 'Decommissioned', 'Decommissioned assets'),
        ],
        default='ALL'
    )

    # Selected asset details
    selected_asset_guid: StringProperty(name="GUID")
    selected_asset_name: StringProperty(name="Name")
    selected_asset_manufacturer: StringProperty(name="Manufacturer")
    selected_asset_model: StringProperty(name="Model")
    selected_asset_status: StringProperty(name="Status")
    selected_asset_condition: StringProperty(name="Condition")

    # Maintenance filters (Phase 2)
    filter_wo_status: EnumProperty(
        name="WO Status",
        description="Filter work orders by status",
        items=[
            ('ALL', 'All', 'Show all statuses'),
            ('Open', 'Open', 'Open work orders'),
            ('InProgress', 'In Progress', 'In progress'),
            ('Completed', 'Completed', 'Completed'),
            ('Deferred', 'Deferred', 'Deferred'),
        ],
        default='ALL'
    )


class BIM_UL_tandem_assets(UIList):
    """Asset list UI"""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)

            # Condition indicator
            if item.condition == 'Excellent':
                icon = 'CHECKMARK'
            elif item.condition == 'Good':
                icon = 'TRACKING_FORWARDS_SINGLE'
            elif item.condition == 'Fair':
                icon = 'ERROR'
            elif item.condition == 'Poor':
                icon = 'CANCEL'
            elif item.condition == 'Failed':
                icon = 'CANCEL'
            else:
                icon = 'QUESTION'

            row.label(text="", icon=icon)
            row.label(text=item.name, icon='OBJECT_DATA')

            # Discipline badge
            row.label(text=item.discipline)

        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=item.name)


class BIM_PT_tandem_main(Panel):
    """Digital Twin main panel"""
    bl_label = "Digital Twin (6D/7D)"
    bl_idname = "BIM_PT_tandem_main"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"
    bl_parent_id = "BIM_PT_digital_twin"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        layout = self.layout
        props = context.scene.BIMTandemProperties
        fed_props = context.scene.BIMFederationProperties

        # Database status (read-only, shows Federation DB)
        # Note: Don't write to props in draw() - Blender doesn't allow it
        box = layout.box()
        if fed_props.federation_database_path:
            box.label(text="Using Federation Database:", icon='FILE')
            row = box.row()
            row.scale_y = 0.7
            row.label(text=f"{fed_props.federation_database_path.split('/')[-1]}")
        else:
            box.label(text="⚠ No Federation Database Loaded", icon='ERROR')
            row = box.row()
            row.scale_y = 0.7
            row.label(text="Load database in Federation panel first")
            return

        # Quick actions
        box = layout.box()
        box.label(text="Asset Management:", icon='PROPERTIES')

        row = box.row(align=True)
        row.operator("bim.import_assets_from_ifc", text="Import from IFC", icon='IMPORT')
        row.operator("bim.refresh_asset_list", text="Refresh", icon='FILE_REFRESH')

        row = box.row()
        row.operator("bim.export_asset_report", text="Export Report", icon='EXPORT')

        # Visualization
        box = layout.box()
        box.label(text="Visualization:", icon='SHADING_RENDERED')
        box.operator("bim.visualize_assets_by_condition", text="Color by Condition", icon='SHADING_SOLID')


class BIM_PT_tandem_assets(Panel):
    """Asset list panel"""
    bl_label = "Assets"
    bl_idname = "BIM_PT_tandem_assets"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"
    bl_parent_id = "BIM_PT_digital_twin"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        props = context.scene.BIMTandemProperties

        # Import section (if no assets)
        if not context.scene.bim_tandem_assets or len(context.scene.bim_tandem_assets) == 0:
            box = layout.box()
            box.label(text="No Assets Found", icon='INFO')
            row = box.row(align=True)
            row.scale_y = 1.5
            row.operator("bim.import_assets_from_federation", text="Import from Federation", icon='IMPORT')
            row = box.row()
            row.scale_y = 0.8
            row.label(text="💡 Imports equipment from enhanced_federation.db")
            return

        # Filters
        box = layout.box()
        box.label(text="Filters:", icon='FILTER')
        row = box.row(align=True)
        row.prop(props, "filter_discipline", text="")
        row.prop(props, "filter_status", text="")

        # Asset list
        layout.template_list(
            "BIM_UL_tandem_assets",
            "",
            context.scene,
            "bim_tandem_assets",
            context.scene,
            "bim_tandem_assets_index"
        )

        # Selected asset actions
        if context.scene.bim_tandem_assets:
            index = context.scene.bim_tandem_assets_index
            if 0 <= index < len(context.scene.bim_tandem_assets):
                item = context.scene.bim_tandem_assets[index]

                box = layout.box()
                box.label(text=f"Selected: {item.name}", icon='OBJECT_DATA')

                row = box.row(align=True)
                op = row.operator("bim.view_asset_details", text="Details", icon='INFO')
                op.asset_guid = item.guid

                op = row.operator("bim.highlight_asset_in_3d", text="Highlight", icon='RESTRICT_SELECT_OFF')
                op.asset_guid = item.guid

                # Status/Condition
                col = box.column(align=True)
                col.label(text=f"Status: {item.status}")
                col.label(text=f"Condition: {item.condition}")


class BIM_PT_tandem_asset_details(Panel):
    """Asset details panel"""
    bl_label = "Asset Details"
    bl_idname = "BIM_PT_tandem_asset_details"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"
    bl_parent_id = "BIM_PT_digital_twin"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        props = context.scene.BIMTandemProperties
        return props.selected_asset_guid != ""

    def draw(self, context):
        layout = self.layout
        props = context.scene.BIMTandemProperties

        box = layout.box()
        box.label(text=props.selected_asset_name, icon='OBJECT_DATA')

        col = box.column(align=True)
        col.label(text=f"GUID: {props.selected_asset_guid}")

        if props.selected_asset_manufacturer:
            col.label(text=f"Manufacturer: {props.selected_asset_manufacturer}")
        if props.selected_asset_model:
            col.label(text=f"Model: {props.selected_asset_model}")

        col.separator()
        col.label(text=f"Status: {props.selected_asset_status}")
        col.label(text=f"Condition: {props.selected_asset_condition}")

        # Update actions
        box = layout.box()
        box.label(text="Update Status:", icon='SETTINGS')

        row = box.row()
        row.label(text="Condition:")
        row = box.row(align=True)
        for cond in ['Excellent', 'Good', 'Fair', 'Poor', 'Failed']:
            op = row.operator("bim.update_asset_status", text=cond)
            op.asset_guid = props.selected_asset_guid
            op.field = 'condition'
            op.value = cond


class BIM_PT_tandem_statistics(Panel):
    """Statistics panel"""
    bl_label = "Statistics"
    bl_idname = "BIM_PT_tandem_statistics"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"
    bl_parent_id = "BIM_PT_digital_twin"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout

        try:
            from .operator import get_tandem_db_path
            from .asset_registry import AssetRegistry

            db_path = get_tandem_db_path(context)
            registry = AssetRegistry(db_path)
            stats = registry.get_statistics()

            box = layout.box()
            box.label(text=f"Total Assets: {stats.get('total_assets', 0)}", icon='PROPERTIES')

            # By discipline
            if stats.get('by_discipline'):
                box = layout.box()
                box.label(text="By Discipline:", icon='OUTLINER_DATA_LIGHTPROBE')
                for disc, count in sorted(stats['by_discipline'].items()):
                    row = box.row()
                    row.label(text=f"  {disc}: {count}")

            # By condition
            if stats.get('by_condition'):
                box = layout.box()
                box.label(text="By Condition:", icon='SHADING_SOLID')
                for cond, count in sorted(stats['by_condition'].items()):
                    row = box.row()
                    row.label(text=f"  {cond}: {count}")

        except Exception as e:
            layout.label(text=f"Error loading stats: {e}", icon='ERROR')


# =========================================================================
# MAINTENANCE UI (Phase 2)
# =========================================================================

class BIMTandemWorkOrderItem(PropertyGroup):
    """Work order list item for UI"""
    wo_id: IntProperty(name="ID")
    wo_number: StringProperty(name="Number")
    title: StringProperty(name="Title")
    work_type: StringProperty(name="Type")
    priority: StringProperty(name="Priority")
    status: StringProperty(name="Status")
    due_date: StringProperty(name="Due Date")


class BIM_UL_tandem_work_orders(UIList):
    """Work order list UI"""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)

            # Priority indicator
            if item.priority == 'Critical':
                icon = 'ERROR'
            elif item.priority == 'High':
                icon = 'FUND'
            elif item.priority == 'Medium':
                icon = 'LAYER_ACTIVE'
            else:
                icon = 'LAYER_USED'

            row.label(text="", icon=icon)

            # Type icon
            if item.work_type == 'PM':
                type_icon = 'TIME'
            elif item.work_type == 'Emergency':
                type_icon = 'ERROR'
            else:
                type_icon = 'TOOL_SETTINGS'

            row.label(text="", icon=type_icon)
            row.label(text=item.wo_number)
            row.label(text=item.title[:30])

            # Status
            if item.status == 'Completed':
                row.label(text="✓", icon='CHECKMARK')
            elif item.status == 'InProgress':
                row.label(text="⏵", icon='PLAY')

        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=item.wo_number)


class BIM_PT_tandem_maintenance(Panel):
    """Maintenance panel"""
    bl_label = "Maintenance"
    bl_idname = "BIM_PT_tandem_maintenance"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"
    bl_parent_id = "BIM_PT_digital_twin"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        props = context.scene.BIMTandemProperties

        # PM Scheduling
        box = layout.box()
        box.label(text="PM Scheduling:", icon='TIME')

        row = box.row(align=True)
        row.operator("bim.generate_pm_schedule", text="Generate PM Schedule", icon='FILE_REFRESH')
        row.operator("bim.view_pm_summary", text="Summary", icon='INFO')

        # Work Orders
        box = layout.box()
        box.label(text="Work Orders:", icon='TOOL_SETTINGS')

        row = box.row()
        row.operator("bim.refresh_work_order_list", text="Refresh List", icon='FILE_REFRESH')

        # Filter
        if hasattr(props, 'filter_wo_status'):
            row = box.row()
            row.prop(props, "filter_wo_status", text="Filter")


class BIM_PT_tandem_work_orders(Panel):
    """Work orders list panel"""
    bl_label = "Work Orders"
    bl_idname = "BIM_PT_tandem_work_orders"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tandem_maintenance"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout

        # Work order list
        layout.template_list(
            "BIM_UL_tandem_work_orders",
            "",
            context.scene,
            "bim_tandem_work_orders",
            context.scene,
            "bim_tandem_work_orders_index"
        )

        # Selected work order actions
        if context.scene.bim_tandem_work_orders:
            index = context.scene.bim_tandem_work_orders_index
            if 0 <= index < len(context.scene.bim_tandem_work_orders):
                item = context.scene.bim_tandem_work_orders[index]

                box = layout.box()
                box.label(text=f"WO: {item.wo_number}", icon='TOOL_SETTINGS')

                col = box.column(align=True)
                col.label(text=f"Type: {item.work_type}")
                col.label(text=f"Priority: {item.priority}")
                col.label(text=f"Status: {item.status}")
                col.label(text=f"Due: {item.due_date}")

                if item.status != 'Completed':
                    row = box.row()
                    op = row.operator("bim.complete_work_order", text="Complete", icon='CHECKMARK')
                    op.wo_id = item.wo_id


class BIM_PT_tandem_maintenance_stats(Panel):
    """Maintenance statistics panel"""
    bl_label = "Maintenance Statistics"
    bl_idname = "BIM_PT_tandem_maintenance_stats"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tandem_maintenance"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout

        try:
            from .operator import get_tandem_db_path
            from .maintenance_manager import MaintenanceManager

            db_path = get_tandem_db_path(context)
            maintenance = MaintenanceManager(db_path)
            stats = maintenance.get_maintenance_statistics()

            box = layout.box()
            box.label(text=f"Total Work Orders: {stats.get('total_work_orders', 0)}", icon='TOOL_SETTINGS')

            # By status
            if stats.get('by_status'):
                box = layout.box()
                box.label(text="By Status:", icon='CHECKMARK')
                for status, count in sorted(stats['by_status'].items()):
                    row = box.row()
                    row.label(text=f"  {status}: {count}")

            # By type
            if stats.get('by_type'):
                box = layout.box()
                box.label(text="By Type:", icon='TIME')
                for wtype, count in sorted(stats['by_type'].items()):
                    row = box.row()
                    row.label(text=f"  {wtype}: {count}")

            # Overdue
            if stats.get('overdue_count', 0) > 0:
                box = layout.box()
                box.alert = True
                box.label(text=f"⚠ Overdue: {stats['overdue_count']}", icon='ERROR')

            # PM templates
            box = layout.box()
            box.label(text=f"Active PM Templates: {stats.get('total_pm_templates', 0)}", icon='TIME')

        except Exception as e:
            layout.label(text=f"Error loading stats: {e}", icon='ERROR')


# =========================================================================
# IOT COMMAND CENTER (Phase 3) 🚀
# =========================================================================

class BIM_PT_tandem_iot_command_center(Panel):
    """IoT Command Center - Mission Control for Buildings"""
    bl_label = "IoT Command Center"
    bl_idname = "BIM_PT_tandem_iot_command_center"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"
    bl_parent_id = "BIM_PT_digital_twin"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout

        # Header with workspace switcher
        box = layout.box()
        row = box.row()
        row.label(text="🚀 Real-Time Building Operations", icon='LIGHT_SUN')

        # Full-screen workspace button
        box.separator()
        row = box.row()
        row.scale_y = 1.5
        row.operator("bim.iot_switch_to_command_center", text="⚡ Open Full Command Center", icon='WORKSPACE')

        # Mission Control features description
        info_col = box.column(align=True)
        info_col.scale_y = 0.7
        info_col.label(text="💡 NASA Mission Control style interface")
        info_col.label(text="   Animated sensors | Live analytics | AI predictions")

        box.separator()

        # Sensor Overlay Controls
        vis_box = layout.box()
        vis_box.label(text="Sensor Visualization:", icon='OUTLINER_OB_LIGHTPROBE')

        # Check overlay status
        from .sensor_overlay import get_sensor_overlay
        overlay = get_sensor_overlay()

        row = vis_box.row(align=True)
        row.scale_y = 1.5

        if overlay.enabled:
            # Enabled - show disable button
            row.operator("bim.iot_disable_sensor_overlay", text="Hide Sensors", icon='HIDE_ON')
            row.label(text=f"({len(overlay.sensors)} active)", icon='CHECKMARK')
        else:
            # Disabled - show enable button
            row.operator("bim.iot_enable_sensor_overlay", text="Show Sensors", icon='HIDE_OFF')

        # Info text
        info_col = vis_box.column(align=True)
        info_col.scale_y = 0.6
        if overlay.enabled:
            info_col.label(text=f"✅ Showing {len(overlay.sensors)} animated sensors in viewport")
            info_col.label(text="   🔵 Pulsing spheres = Temperature")
            info_col.label(text="   🟦 Rotating cubes = Pressure")
            info_col.label(text="   🔴 Blinking red = Alerts")
        else:
            info_col.label(text="Enable to see animated sensor markers in 3D")

        # Building Health Dashboard (placeholder for Phase 3B)
        health_box = layout.box()
        health_box.label(text="Building Health Score:", icon='HEART')

        # Placeholder stats (will be dynamic in Phase 3B)
        row = health_box.row()
        row.scale_y = 1.3
        row.label(text="Overall: 87/100 ↗️", icon='FUND')

        col = health_box.column(align=True)
        col.scale_y = 0.8
        col.label(text="🟢 ACMV:     92 (↗️ +3)")
        col.label(text="🟡 Electrical: 78 (→)")
        col.label(text="🟢 Fire:      95 (↗️ +2)")
        col.label(text="🟠 Plumbing:  64 (↘️ -8) ⚠️")

        # Analytics Panel (placeholder)
        analytics_box = layout.box()
        analytics_box.label(text="Intelligence Layer:", icon='SHADERFX')

        col = analytics_box.column(align=True)
        col.scale_y = 0.7
        col.label(text="🔮 2 issues predicted in 14 days")
        col.label(text="💡 Savings: $245/mo available")
        col.label(text="🌡️ Comfort: 89% satisfied")

        # Quick Actions
        actions_box = layout.box()
        actions_box.label(text="Quick Actions:", icon='SETTINGS')

        row = actions_box.row(align=True)
        row.operator("bim.iot_generate_mock_data", text="Generate Demo Data", icon='FILE_REFRESH')

        row = actions_box.row(align=True)
        row.operator("bim.iot_export_analytics", text="Export Analytics", icon='EXPORT')


class BIM_PT_tandem_iot_sensors(Panel):
    """IoT Sensors panel - list of active sensors"""
    bl_label = "Active Sensors"
    bl_idname = "BIM_PT_tandem_iot_sensors"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tandem_iot_command_center"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout

        try:
            from .operator import get_tandem_db_path
            from .sensor_registry import SensorRegistry

            db_path = get_tandem_db_path(context)
            registry = SensorRegistry(db_path)

            # Get sensor counts
            sensors = registry.list_sensors(active_only=True)

            # Count by type
            by_type = {}
            for sensor in sensors:
                sensor_type = sensor.get('sensor_type', 'Unknown')
                by_type[sensor_type] = by_type.get(sensor_type, 0) + 1

            # Display stats
            box = layout.box()
            box.label(text=f"Total Active: {len(sensors)}", icon='LIGHT')

            # By type breakdown
            if by_type:
                type_box = layout.box()
                type_box.label(text="By Type:", icon='FILTER')

                for sensor_type, count in sorted(by_type.items()):
                    row = type_box.row()

                    # Type icons
                    icon = 'LIGHT'
                    if sensor_type == 'Temperature':
                        icon = 'LIGHT_SUN'
                    elif sensor_type == 'Pressure':
                        icon = 'PROP_CON'
                    elif sensor_type == 'Flow':
                        icon = 'FORCE_WIND'
                    elif sensor_type == 'CO2':
                        icon = 'MATFLUID'
                    elif sensor_type == 'Power':
                        icon = 'LIGHT_SPOT'

                    row.label(text=f"{sensor_type}: {count}", icon=icon)

        except Exception as e:
            layout.label(text=f"Error loading sensors: {e}", icon='ERROR')


# =========================================================================
# SENSOR PROPERTIES PANEL (Shows when sensor selected)
# =========================================================================

class BIM_PT_sensor_properties(Panel):
    """Sensor Properties - Shows when IoT sensor Empty selected"""
    bl_label = "IoT Sensor Properties"
    bl_idname = "BIM_PT_sensor_properties"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and obj.get("is_iot_sensor", False)

    def draw(self, context):
        layout = self.layout
        obj = context.active_object

        # Header
        box = layout.box()
        sensor_type = obj.get("sensor_type", "Unknown")

        # Icon based on type
        icon = 'LIGHT'
        if sensor_type == 'Temperature':
            icon = 'LIGHT_SUN'
        elif sensor_type == 'Pressure':
            icon = 'PROP_CON'
        elif sensor_type == 'Flow':
            icon = 'FORCE_WIND'
        elif sensor_type == 'Power':
            icon = 'LIGHT_SPOT'

        row = box.row()
        row.label(text=f"{sensor_type} Sensor", icon=icon)

        # Sensor details
        col = box.column(align=True)
        col.scale_y = 0.8
        col.label(text=f"ID: {obj.get('sensor_id', 'unknown')}")

        # Current value (large display)
        value_box = layout.box()
        row = value_box.row()
        row.scale_y = 2.0
        current = obj.get("current_value", 0)

        # Unit based on type
        unit = ""
        if sensor_type == 'Temperature':
            unit = "°C"
        elif sensor_type == 'Pressure':
            unit = "bar"
        elif sensor_type == 'Flow':
            unit = "m³/h"
        elif sensor_type == 'Power':
            unit = "kW"

        row.label(text=f"{current:.2f} {unit}", icon='INFO')

        # Thresholds
        if "threshold_min" in obj:
            thresh_box = layout.box()
            thresh_box.label(text="Thresholds:", icon='PREVIEW_RANGE')

            col = thresh_box.column(align=True)
            col.scale_y = 0.7
            col.label(text=f"Min: {obj.get('threshold_min', 0):.1f} {unit}")
            col.label(text=f"Max: {obj.get('threshold_max', 100):.1f} {unit}")

            # Status indicator
            thresh_min = obj.get('threshold_min', 0)
            thresh_max = obj.get('threshold_max', 100)

            if current < thresh_min:
                status_box = thresh_box.box()
                status_box.alert = True
                status_box.label(text="⚠️ BELOW MINIMUM", icon='ERROR')
            elif current > thresh_max:
                status_box = thresh_box.box()
                status_box.alert = True
                status_box.label(text="⚠️ ABOVE MAXIMUM", icon='ERROR')
            else:
                status_box = thresh_box.box()
                status_box.label(text="✅ Normal", icon='CHECKMARK')

        # Asset info
        asset_box = layout.box()
        asset_box.label(text="Associated Asset:", icon='OBJECT_DATA')
        col = asset_box.column(align=True)
        col.scale_y = 0.7
        col.label(text=obj.get("asset_name", "Unknown"))

        # Location
        loc_col = asset_box.column(align=True)
        loc_col.scale_y = 0.6
        loc = obj.location
        loc_col.label(text=f"Location: ({loc.x:.2f}, {loc.y:.2f}, {loc.z:.2f})")

        # Actions
        actions_box = layout.box()
        actions_box.label(text="Actions:", icon='SETTINGS')

        row = actions_box.row(align=True)
        row.operator("bim.view_sensor_history", text="View History", icon='GRAPH')

        row = actions_box.row(align=True)
        row.operator("bim.create_sensor_alert_rule", text="Create Alert", icon='ERROR')

        row = actions_box.row(align=True)
        row.operator("bim.create_sensor_work_order", text="Create Work Order", icon='TOOL_SETTINGS')

        # Frame Selected hint
        hint_box = layout.box()
        hint_box.scale_y = 0.6
        hint_box.label(text="💡 Press Numpad '.' to zoom to sensor", icon='INFO')


# Registration
classes = (
    # Asset classes
    BIMTandemAssetItem,
    BIMTandemProperties,
    BIM_UL_tandem_assets,
    BIM_PT_tandem_main,
    BIM_PT_tandem_assets,
    BIM_PT_tandem_asset_details,
    BIM_PT_tandem_statistics,
    # Maintenance classes (Phase 2)
    BIMTandemWorkOrderItem,
    BIM_UL_tandem_work_orders,
    BIM_PT_tandem_maintenance,
    BIM_PT_tandem_work_orders,
    BIM_PT_tandem_maintenance_stats,
    # IoT Command Center (Phase 3)
    BIM_PT_tandem_iot_command_center,
    BIM_PT_tandem_iot_sensors,
    # Sensor Properties (interactive)
    BIM_PT_sensor_properties,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # Scene properties
    bpy.types.Scene.BIMTandemProperties = PointerProperty(type=BIMTandemProperties)
    bpy.types.Scene.bim_tandem_assets = CollectionProperty(type=BIMTandemAssetItem)
    bpy.types.Scene.bim_tandem_assets_index = IntProperty()
    # Maintenance (Phase 2)
    bpy.types.Scene.bim_tandem_work_orders = CollectionProperty(type=BIMTandemWorkOrderItem)
    bpy.types.Scene.bim_tandem_work_orders_index = IntProperty()


def unregister():
    del bpy.types.Scene.bim_tandem_work_orders_index
    del bpy.types.Scene.bim_tandem_work_orders
    del bpy.types.Scene.bim_tandem_assets_index
    del bpy.types.Scene.bim_tandem_assets
    del bpy.types.Scene.BIMTandemProperties

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
