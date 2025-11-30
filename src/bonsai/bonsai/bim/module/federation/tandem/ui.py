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
    bl_label = "Digital Twin - Facilities Management"
    bl_idname = "BIM_PT_tandem_main"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return True

    def draw(self, context):
        layout = self.layout
        props = context.scene.BIMTandemProperties

        # Database connection
        box = layout.box()
        box.label(text="Database:", icon='DATABASE')
        row = box.row(align=True)
        row.prop(props, "database_path", text="")

        # Quick actions
        box = layout.box()
        box.label(text="Asset Management:", icon='ASSET_MANAGER')

        row = box.row(align=True)
        row.operator("bim.import_assets_from_ifc", text="Import from IFC", icon='IMPORT')
        row.operator("bim.refresh_asset_list", text="Refresh", icon='FILE_REFRESH')

        row = box.row()
        row.operator("bim.export_asset_report", text="Export Report", icon='EXPORT')

        # Visualization
        box = layout.box()
        box.label(text="Visualization:", icon='SHADING_RENDERED')
        box.operator("bim.visualize_assets_by_condition", text="Color by Condition", icon='COLOR')


class BIM_PT_tandem_assets(Panel):
    """Asset list panel"""
    bl_label = "Assets"
    bl_idname = "BIM_PT_tandem_assets"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tandem_main"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        props = context.scene.BIMTandemProperties

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
    bl_parent_id = "BIM_PT_tandem_main"
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
        box.label(text="Update Status:", icon='MODIFIER')

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
    bl_parent_id = "BIM_PT_tandem_main"
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
            box.label(text=f"Total Assets: {stats.get('total_assets', 0)}", icon='ASSET_MANAGER')

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
                box.label(text="By Condition:", icon='SHADERFX')
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
    bl_parent_id = "BIM_PT_tandem_main"
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
