"""
Digital Twin - Blender Operators
UI operators for asset management in Blender

Operators:
- Import assets from IFC
- View asset details
- Update asset status
- Visualize assets by condition
"""

import bpy
import os
from datetime import datetime, timedelta
from bpy.types import Operator
from bpy.props import StringProperty, EnumProperty, BoolProperty
from pathlib import Path

from .asset_registry import AssetRegistry
from .asset_importer import AssetImporter


def get_tandem_db_path(context) -> str:
    """Get path to enhanced federation database (integrated with 4D/5D)"""
    # PRIORITY 1: Use Federation panel's database (main integration point)
    if hasattr(context.scene, 'BIMFederationProperties'):
        fed_db_path = context.scene.BIMFederationProperties.federation_database_path
        if fed_db_path:
            # Resolve Blender's // relative path
            resolved_path = bpy.path.abspath(fed_db_path)
            if os.path.exists(resolved_path):
                return resolved_path

    # PRIORITY 2: Check Tandem-specific property (if user manually set it)
    if hasattr(context.scene, 'BIMTandemProperties'):
        db_path = context.scene.BIMTandemProperties.database_path
        if db_path and os.path.exists(db_path):
            return db_path

    # PRIORITY 3: Default locations
    # Check WORK_DIR symlink
    work_dir = Path.home() / 'Projects' / 'IfcOpenShell' / 'WORK_DIR' / 'databases'
    if work_dir.exists():
        db_path = work_dir / 'enhanced_federation.db'
        if db_path.exists():
            return str(db_path)

    # Check Documents location
    docs_db = Path.home() / 'Documents' / 'bonsai' / 'DatabaseFiles' / 'enhanced_federation.db'
    if docs_db.exists():
        return str(docs_db)

    # Fallback to temp (will create new DB)
    return str(Path(bpy.app.tempdir) / 'enhanced_federation.db')


class BIM_OT_import_assets_from_ifc(Operator):
    """Import equipment assets from loaded IFC model"""
    bl_idname = "bim.import_assets_from_ifc"
    bl_label = "Import Assets from IFC"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        import bonsai.tool as tool
        return tool.Ifc.get() is not None

    def execute(self, context):
        import bonsai.tool as tool

        ifc_file = tool.Ifc.get()
        if not ifc_file:
            self.report({'ERROR'}, "No IFC file loaded")
            return {'CANCELLED'}

        try:
            # Get database path
            db_path = get_tandem_db_path(context)

            # Initialize registry and importer
            registry = AssetRegistry(db_path)
            importer = AssetImporter(registry)

            # Progress tracking
            self.progress_current = 0
            self.progress_total = 0

            def progress_callback(current, total, message):
                self.progress_current = current
                self.progress_total = total
                print(f"[{current}/{total}] {message}")

            # Import from blend
            stats = importer.import_from_blend(progress_callback)

            # Report results
            message = (
                f"Import complete: {stats['imported']} assets imported, "
                f"{stats['skipped']} skipped, {stats['errors']} errors"
            )
            self.report({'INFO'}, message)

            print("\nImport Statistics:")
            print(f"  Total scanned: {stats['total_scanned']}")
            print(f"  Imported: {stats['imported']}")
            print(f"  Skipped: {stats['skipped']}")
            print(f"  Errors: {stats['errors']}")
            print("\nBy Discipline:")
            for disc, count in stats['by_discipline'].items():
                print(f"  {disc}: {count}")

            # Update scene properties
            if hasattr(context.scene, 'BIMTandemProperties'):
                context.scene.BIMTandemProperties.database_path = db_path
                context.scene.BIMTandemProperties.last_sync = bpy.context.scene.frame_current

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Import failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}


class BIM_OT_import_assets_from_federation(Operator):
    """Import equipment assets from federation database (PRIMARY METHOD)"""
    bl_idname = "bim.import_assets_from_federation"
    bl_label = "Import from Federation DB"
    bl_options = {'REGISTER', 'UNDO'}

    discipline_filter: EnumProperty(
        name="Discipline Filter",
        description="Only import specific disciplines",
        items=[
            ('ALL', 'All Disciplines', 'Import all equipment'),
            ('ACMV', 'ACMV', 'HVAC equipment only'),
            ('ELEC', 'Electrical', 'Electrical equipment only'),
            ('PLB', 'Plumbing', 'Plumbing equipment only'),
            ('FP', 'Fire Protection', 'Fire protection equipment only'),
        ],
        default='ALL',
    )

    @classmethod
    def poll(cls, context):
        # Check if federation DB exists (check both WORK_DIR and Documents locations)
        work_dir = Path.home() / 'Projects' / 'IfcOpenShell' / 'WORK_DIR' / 'databases'
        fed_db = work_dir / 'enhanced_federation.db'
        if fed_db.exists():
            return True
        # Fallback to Documents location
        docs_db = Path.home() / 'Documents' / 'bonsai' / 'DatabaseFiles' / 'enhanced_federation.db'
        return docs_db.exists()

    def execute(self, context):
        try:
            # Get database path
            db_path = get_tandem_db_path(context)

            # Federation DB path (check both locations)
            work_dir = Path.home() / 'Projects' / 'IfcOpenShell' / 'WORK_DIR' / 'databases'
            federation_db = work_dir / 'enhanced_federation.db'

            if not federation_db.exists():
                # Try Documents location
                federation_db = Path.home() / 'Documents' / 'bonsai' / 'DatabaseFiles' / 'enhanced_federation.db'
                if not federation_db.exists():
                    self.report({'ERROR'}, f"Federation database not found in WORK_DIR or Documents")
                    return {'CANCELLED'}

            # Initialize registry and importer
            registry = AssetRegistry(db_path)
            importer = AssetImporter(registry)

            # Prepare discipline filter
            discipline_list = None if self.discipline_filter == 'ALL' else [self.discipline_filter]

            # Progress tracking
            def progress_callback(current, total, message):
                print(f"[{current}/{total}] {message}")

            # Import from federation DB
            stats = importer.import_from_federation_db(
                str(federation_db),
                discipline_filter=discipline_list,
                progress_callback=progress_callback
            )

            # Report results
            message = (
                f"Import complete: {stats['imported']} assets imported, "
                f"{stats['skipped']} skipped, {stats['errors']} errors"
            )
            self.report({'INFO'}, message)

            print("\nImport Statistics:")
            print(f"  Total scanned: {stats['total_scanned']}")
            print(f"  Imported: {stats['imported']}")
            print(f"  Skipped: {stats['skipped']}")
            print(f"  Errors: {stats['errors']}")
            print("\nBy Discipline:")
            for disc, count in stats['by_discipline'].items():
                print(f"  {disc}: {count}")

            # Update scene properties
            if hasattr(context.scene, 'BIMTandemProperties'):
                context.scene.BIMTandemProperties.database_path = db_path
                context.scene.BIMTandemProperties.last_sync = bpy.context.scene.frame_current

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Import failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}


class BIM_OT_import_assets_from_csv(Operator):
    """Import assets from CSV file (external sources - IoT devices, manual additions)"""
    bl_idname = "bim.import_assets_from_csv"
    bl_label = "Import from CSV"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: StringProperty(
        name="CSV File",
        subtype='FILE_PATH',
    )

    filter_glob: StringProperty(
        default='*.csv',
        options={'HIDDEN'}
    )

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        try:
            if not self.filepath:
                self.report({'ERROR'}, "No file selected")
                return {'CANCELLED'}

            # Get database path
            db_path = get_tandem_db_path(context)

            # Initialize registry and importer
            registry = AssetRegistry(db_path)
            importer = AssetImporter(registry)

            # Progress tracking
            def progress_callback(current, total, message):
                print(f"[{current}/{total}] {message}")

            # Import from CSV
            stats = importer.import_from_csv(
                self.filepath,
                skip_duplicates=True,
                progress_callback=progress_callback
            )

            # Report results
            message = (
                f"Import complete: {stats['imported']} assets imported, "
                f"{stats['skipped']} skipped, {stats['errors']} errors"
            )
            self.report({'INFO'}, message)

            print("\nCSV Import Statistics:")
            print(f"  Total scanned: {stats['total_scanned']}")
            print(f"  Imported: {stats['imported']}")
            print(f"  Skipped: {stats['skipped']}")
            print(f"  Errors: {stats['errors']}")
            print("\nBy Discipline:")
            for disc, count in stats['by_discipline'].items():
                print(f"  {disc}: {count}")

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Import failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}


class BIM_OT_refresh_asset_list(Operator):
    """Refresh asset list from database"""
    bl_idname = "bim.refresh_asset_list"
    bl_label = "Refresh Asset List"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            db_path = get_tandem_db_path(context)
            registry = AssetRegistry(db_path)

            # Get filter settings
            props = context.scene.BIMTandemProperties
            discipline = props.filter_discipline if props.filter_discipline != 'ALL' else None
            status = props.filter_status if props.filter_status != 'ALL' else None

            # List assets
            assets = registry.list_assets(
                discipline=discipline,
                status=status
            )

            # Update UI collection
            context.scene.bim_tandem_assets.clear()
            for asset in assets:
                item = context.scene.bim_tandem_assets.add()
                item.guid = asset['guid']
                item.name = asset['name']
                item.ifc_class = asset['ifc_class']
                item.discipline = asset.get('discipline', 'Unknown')
                item.status = asset.get('status', 'Unknown')
                item.condition = asset.get('condition', 'Unknown')

            self.report({'INFO'}, f"Loaded {len(assets)} assets")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Refresh failed: {str(e)}")
            return {'CANCELLED'}


class BIM_OT_view_asset_details(Operator):
    """View detailed information about selected asset"""
    bl_idname = "bim.view_asset_details"
    bl_label = "View Asset Details"
    bl_options = {'REGISTER', 'UNDO'}

    asset_guid: StringProperty()

    def execute(self, context):
        try:
            db_path = get_tandem_db_path(context)
            registry = AssetRegistry(db_path)

            asset = registry.get_asset(self.asset_guid)
            if not asset:
                self.report({'ERROR'}, f"Asset {self.asset_guid} not found")
                return {'CANCELLED'}

            # Store in scene properties for display
            props = context.scene.BIMTandemProperties
            props.selected_asset_guid = self.asset_guid
            props.selected_asset_name = asset.get('name', 'Unknown')
            props.selected_asset_manufacturer = asset.get('manufacturer', '')
            props.selected_asset_model = asset.get('model', '')
            props.selected_asset_status = asset.get('status', 'Unknown')
            props.selected_asset_condition = asset.get('condition', 'Unknown')

            self.report({'INFO'}, f"Viewing: {asset['name']}")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to load asset: {str(e)}")
            return {'CANCELLED'}


class BIM_OT_highlight_asset_in_3d(Operator):
    """Highlight selected asset in 3D viewport"""
    bl_idname = "bim.highlight_asset_in_3d"
    bl_label = "Highlight in 3D"
    bl_options = {'REGISTER', 'UNDO'}

    asset_guid: StringProperty()

    def execute(self, context):
        import bonsai.tool as tool

        ifc_file = tool.Ifc.get()
        if not ifc_file:
            self.report({'ERROR'}, "No IFC file loaded")
            return {'CANCELLED'}

        try:
            # Find element by GUID
            element = ifc_file.by_guid(self.asset_guid)
            if not element:
                self.report({'ERROR'}, f"Asset {self.asset_guid} not found in IFC")
                return {'CANCELLED'}

            # Find corresponding Blender object
            obj = tool.Ifc.get_object(element)
            if obj:
                # Deselect all
                bpy.ops.object.select_all(action='DESELECT')

                # Select and make active
                obj.select_set(True)
                context.view_layer.objects.active = obj

                # Frame in viewport
                for area in context.screen.areas:
                    if area.type == 'VIEW_3D':
                        for region in area.regions:
                            if region.type == 'WINDOW':
                                with context.temp_override(area=area, region=region):
                                    bpy.ops.view3d.view_selected()

                self.report({'INFO'}, f"Selected: {obj.name}")
                return {'FINISHED'}
            else:
                self.report({'WARNING'}, "Asset not visible in 3D view")
                return {'CANCELLED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to highlight: {str(e)}")
            return {'CANCELLED'}


class BIM_OT_update_asset_status(Operator):
    """Update asset status or condition"""
    bl_idname = "bim.update_asset_status"
    bl_label = "Update Asset Status"
    bl_options = {'REGISTER', 'UNDO'}

    asset_guid: StringProperty()
    field: EnumProperty(
        items=[
            ('status', 'Status', 'Update status field'),
            ('condition', 'Condition', 'Update condition field')
        ]
    )
    value: StringProperty()

    def execute(self, context):
        try:
            db_path = get_tandem_db_path(context)
            registry = AssetRegistry(db_path)

            updates = {self.field: self.value}
            success = registry.update_asset(self.asset_guid, updates, changed_by='blender_user')

            if success:
                self.report({'INFO'}, f"Updated {self.field} to {self.value}")
                # Refresh list
                bpy.ops.bim.refresh_asset_list()
                return {'FINISHED'}
            else:
                self.report({'ERROR'}, "Asset not found")
                return {'CANCELLED'}

        except Exception as e:
            self.report({'ERROR'}, f"Update failed: {str(e)}")
            return {'CANCELLED'}


class BIM_OT_visualize_assets_by_condition(Operator):
    """Color-code assets in 3D by condition"""
    bl_idname = "bim.visualize_assets_by_condition"
    bl_label = "Visualize by Condition"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import bonsai.tool as tool

        ifc_file = tool.Ifc.get()
        if not ifc_file:
            self.report({'ERROR'}, "No IFC file loaded")
            return {'CANCELLED'}

        try:
            db_path = get_tandem_db_path(context)
            registry = AssetRegistry(db_path)

            # Get all assets
            assets = registry.list_assets()

            # Condition color mapping
            condition_colors = {
                'Excellent': (0.0, 0.8, 0.0, 1.0),  # Green
                'Good': (0.4, 0.8, 0.4, 1.0),       # Light green
                'Fair': (1.0, 0.8, 0.0, 1.0),       # Yellow
                'Poor': (1.0, 0.5, 0.0, 1.0),       # Orange
                'Failed': (1.0, 0.0, 0.0, 1.0),     # Red
            }

            colored_count = 0

            for asset in assets:
                try:
                    element = ifc_file.by_guid(asset['guid'])
                    if not element:
                        continue

                    obj = tool.Ifc.get_object(element)
                    if not obj:
                        continue

                    condition = asset.get('condition', 'Good')
                    color = condition_colors.get(condition, (0.5, 0.5, 0.5, 1.0))

                    # Set viewport display color
                    obj.color = color
                    colored_count += 1

                except:
                    pass

            # Enable color display in viewport
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            space.shading.color_type = 'OBJECT'

            self.report({'INFO'}, f"Colored {colored_count} assets by condition")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Visualization failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}


class BIM_OT_export_asset_report(Operator):
    """Export asset list to CSV"""
    bl_idname = "bim.export_asset_report"
    bl_label = "Export Asset Report"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: StringProperty(subtype='FILE_PATH')

    def execute(self, context):
        try:
            import csv

            db_path = get_tandem_db_path(context)
            registry = AssetRegistry(db_path)

            assets = registry.list_assets()

            if not self.filepath:
                work_dir = Path.home() / 'Projects' / 'IfcOpenShell' / 'WORK_DIR'
                self.filepath = str(work_dir / 'asset_report.csv')

            # Write CSV
            with open(self.filepath, 'w', newline='', encoding='utf-8') as f:
                if not assets:
                    self.report({'WARNING'}, "No assets to export")
                    return {'CANCELLED'}

                writer = csv.DictWriter(f, fieldnames=assets[0].keys())
                writer.writeheader()
                writer.writerows(assets)

            self.report({'INFO'}, f"Exported {len(assets)} assets to {self.filepath}")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {str(e)}")
            return {'CANCELLED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


# =========================================================================
# MAINTENANCE OPERATORS (Phase 2)
# =========================================================================

class BIM_OT_generate_pm_schedule(Operator):
    """Generate PM work orders for upcoming period"""
    bl_idname = "bim.generate_pm_schedule"
    bl_label = "Generate PM Schedule"
    bl_options = {'REGISTER', 'UNDO'}

    days_ahead: bpy.props.IntProperty(name="Days Ahead", default=90, min=1, max=365)

    def execute(self, context):
        try:
            from .maintenance_manager import MaintenanceManager
            from .pm_scheduler import PMScheduler

            db_path = get_tandem_db_path(context)
            registry = AssetRegistry(db_path)
            maintenance = MaintenanceManager(db_path)
            scheduler = PMScheduler(registry, maintenance)

            print(f"\nGenerating PM schedule for next {self.days_ahead} days...")

            def progress(current, total, message):
                print(f"  [{current}/{total}] {message}")

            stats = scheduler.generate_pm_schedule(self.days_ahead, progress)

            message = (
                f"PM Schedule generated: {stats['work_orders_created']} work orders created, "
                f"{stats['work_orders_skipped']} skipped"
            )
            self.report({'INFO'}, message)

            print(f"\n{message}")
            print(f"  Templates processed: {stats['templates_processed']}")
            print(f"  Assets scanned: {stats['assets_scanned']}")
            print(f"  Errors: {stats['errors']}")

            # Refresh work order list
            bpy.ops.bim.refresh_work_order_list()

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"PM generation failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class BIM_OT_create_work_order(Operator):
    """Create new work order"""
    bl_idname = "bim.create_work_order"
    bl_label = "Create Work Order"
    bl_options = {'REGISTER', 'UNDO'}

    asset_guid: StringProperty()
    work_type: EnumProperty(
        items=[
            ('PM', 'Preventive Maintenance', ''),
            ('Corrective', 'Corrective', ''),
            ('Emergency', 'Emergency', ''),
            ('Inspection', 'Inspection', '')
        ],
        default='Corrective'
    )
    priority: EnumProperty(
        items=[
            ('Low', 'Low', ''),
            ('Medium', 'Medium', ''),
            ('High', 'High', ''),
            ('Critical', 'Critical', '')
        ],
        default='Medium'
    )
    title: StringProperty(name="Title")
    description: StringProperty(name="Description")

    def execute(self, context):
        try:
            from .maintenance_manager import MaintenanceManager

            if not self.asset_guid or not self.title:
                self.report({'ERROR'}, "Asset and title required")
                return {'CANCELLED'}

            db_path = get_tandem_db_path(context)
            maintenance = MaintenanceManager(db_path)

            wo_number = maintenance._generate_wo_number()

            wo_data = {
                'work_order_number': wo_number,
                'asset_guid': self.asset_guid,
                'work_type': self.work_type,
                'priority': self.priority,
                'title': self.title,
                'description': self.description,
                'due_date': (datetime.now() + timedelta(days=7)).date().isoformat(),
                'created_by': 'blender_user',
            }

            wo_id = maintenance.create_work_order(wo_data)

            self.report({'INFO'}, f"Work order {wo_number} created")
            bpy.ops.bim.refresh_work_order_list()

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to create work order: {str(e)}")
            return {'CANCELLED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class BIM_OT_refresh_work_order_list(Operator):
    """Refresh work order list"""
    bl_idname = "bim.refresh_work_order_list"
    bl_label = "Refresh Work Orders"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            from .maintenance_manager import MaintenanceManager

            db_path = get_tandem_db_path(context)
            maintenance = MaintenanceManager(db_path)

            # Get filter from properties
            props = context.scene.BIMTandemProperties
            status = props.filter_wo_status if hasattr(props, 'filter_wo_status') and props.filter_wo_status != 'ALL' else None

            work_orders = maintenance.list_work_orders(status=status)

            # Update UI collection
            context.scene.bim_tandem_work_orders.clear()
            for wo in work_orders:
                item = context.scene.bim_tandem_work_orders.add()
                item.wo_id = wo['id']
                item.wo_number = wo['work_order_number']
                item.title = wo['title']
                item.work_type = wo['work_type']
                item.priority = wo['priority']
                item.status = wo['status']
                item.due_date = wo.get('due_date', '')

            self.report({'INFO'}, f"Loaded {len(work_orders)} work orders")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Refresh failed: {str(e)}")
            return {'CANCELLED'}


class BIM_OT_complete_work_order(Operator):
    """Mark work order as completed"""
    bl_idname = "bim.complete_work_order"
    bl_label = "Complete Work Order"
    bl_options = {'REGISTER', 'UNDO'}

    wo_id: bpy.props.IntProperty()
    actual_hours: bpy.props.FloatProperty(name="Actual Hours", default=0.0, min=0.0)

    def execute(self, context):
        try:
            from .maintenance_manager import MaintenanceManager

            db_path = get_tandem_db_path(context)
            maintenance = MaintenanceManager(db_path)

            success = maintenance.complete_work_order(self.wo_id, self.actual_hours)

            if success:
                self.report({'INFO'}, f"Work order {self.wo_id} completed")
                bpy.ops.bim.refresh_work_order_list()
                return {'FINISHED'}
            else:
                self.report({'ERROR'}, "Work order not found")
                return {'CANCELLED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to complete: {str(e)}")
            return {'CANCELLED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class BIM_OT_view_pm_summary(Operator):
    """View PM schedule summary"""
    bl_idname = "bim.view_pm_summary"
    bl_label = "View PM Summary"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            from .maintenance_manager import MaintenanceManager
            from .pm_scheduler import PMScheduler

            db_path = get_tandem_db_path(context)
            registry = AssetRegistry(db_path)
            maintenance = MaintenanceManager(db_path)
            scheduler = PMScheduler(registry, maintenance)

            summary = scheduler.get_upcoming_pm_summary(days=30)

            print("\n=== PM Schedule Summary (Next 30 Days) ===")
            print(f"Total upcoming: {summary['total_upcoming']}")
            print(f"Overdue: {summary['overdue']}")
            print(f"Due this week: {summary['due_this_week']}")
            print(f"Due next week: {summary['due_next_week']}")

            if summary['by_discipline']:
                print("\nBy Discipline:")
                for disc, count in sorted(summary['by_discipline'].items()):
                    print(f"  {disc}: {count}")

            self.report({'INFO'}, f"{summary['total_upcoming']} PM work orders upcoming")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to load summary: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}


# =========================================================================
# IOT COMMAND CENTER OPERATORS (Phase 3)
# =========================================================================

class BIM_OT_iot_generate_mock_data(Operator):
    """Generate mock sensor data for demo scenarios"""
    bl_idname = "bim.iot_generate_mock_data"
    bl_label = "Generate Mock IoT Data"
    bl_options = {'REGISTER', 'UNDO'}

    scenario: EnumProperty(
        name="Scenario",
        items=[
            ('normal', 'Normal Operation', 'Typical Tuesday'),
            ('heatwave', 'Heatwave Stress', 'Outdoor 38°C, chillers struggling'),
            ('degradation', 'Equipment Degradation', 'AHU bearing wearing'),
            ('optimization', 'Energy Waste', 'Chiller inefficiency'),
        ],
        default='normal'
    )

    hours: bpy.props.IntProperty(name="Hours of History", default=24, min=1, max=168)

    def execute(self, context):
        try:
            from .mock_data_generator import MockDataGenerator
            from .sensor_registry import SensorRegistry

            db_path = get_tandem_db_path(context)
            registry = SensorRegistry(db_path)
            generator = MockDataGenerator(registry)

            # Set anomaly probability based on scenario
            anomaly_prob = {
                'normal': 0.02,
                'heatwave': 0.15,
                'degradation': 0.25,
                'optimization': 0.10,
            }[self.scenario]

            print(f"\nGenerating mock data - Scenario: {self.scenario}")
            stats = generator.generate_batch(
                hours=self.hours,
                interval_minutes=5,
                anomaly_probability=anomaly_prob
            )

            message = f"Generated {stats.get('total_readings', 0)} sensor readings"
            self.report({'INFO'}, message)

            print(f"\n{message}")
            print(f"  Sensors processed: {stats.get('sensors_processed', 0)}")
            print(f"  Time range: {self.hours} hours")

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Mock data generation failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class BIM_OT_view_sensor_history(Operator):
    """View sensor reading history graph"""
    bl_idname = "bim.view_sensor_history"
    bl_label = "View Sensor History"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or not obj.get("is_iot_sensor"):
            self.report({'ERROR'}, "No sensor selected")
            return {'CANCELLED'}

        sensor_id = obj.get("sensor_id")
        self.report({'INFO'}, f"Opening history for {sensor_id} (feature coming soon)")

        # TODO: Implement graph view
        # - Query sensor_readings table
        # - Display in Graph Editor
        # - Or create matplotlib plot

        return {'FINISHED'}


class BIM_OT_create_sensor_alert_rule(Operator):
    """Create alert rule for this sensor"""
    bl_idname = "bim.create_sensor_alert_rule"
    bl_label = "Create Alert Rule"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or not obj.get("is_iot_sensor"):
            self.report({'ERROR'}, "No sensor selected")
            return {'CANCELLED'}

        sensor_id = obj.get("sensor_id")
        self.report({'INFO'}, f"Creating alert rule for {sensor_id} (feature coming soon)")

        # TODO: Implement alert rule creation
        # - Show dialog with threshold inputs
        # - Create entry in alert_rules table
        # - Start monitoring

        return {'FINISHED'}


class BIM_OT_create_sensor_work_order(Operator):
    """Create work order for sensor's asset"""
    bl_idname = "bim.create_sensor_work_order"
    bl_label = "Create Work Order"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or not obj.get("is_iot_sensor"):
            self.report({'ERROR'}, "No sensor selected")
            return {'CANCELLED'}

        sensor_id = obj.get("sensor_id")
        asset_name = obj.get("asset_name", "Unknown")

        self.report({'INFO'}, f"Creating work order for {asset_name} (feature coming soon)")

        # TODO: Implement work order creation
        # - Get asset_guid from sensor
        # - Create work_order entry
        # - Auto-fill description with sensor alert

        return {'FINISHED'}


class BIM_OT_iot_switch_to_command_center(Operator):
    """Switch to IoT Command Center workspace (full-screen layout)"""
    bl_idname = "bim.iot_switch_to_command_center"
    bl_label = "Open Command Center"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Check if Mission Control workspace exists
        if "Mission Control" in bpy.data.workspaces:
            context.window.workspace = bpy.data.workspaces["Mission Control"]
            self.report({'INFO'}, "Switched to Mission Control workspace")
            return {'FINISHED'}
        elif "IoT Command Center" in bpy.data.workspaces:
            context.window.workspace = bpy.data.workspaces["IoT Command Center"]
            self.report({'INFO'}, "Switched to IoT Command Center workspace")
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "Workspace not found - run create_mission_control_layout.py first")
            return {'CANCELLED'}


class BIM_OT_iot_export_analytics(Operator):
    """Export IoT analytics to JSON/CSV"""
    bl_idname = "bim.iot_export_analytics"
    bl_label = "Export IoT Analytics"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: StringProperty(subtype='FILE_PATH')

    def execute(self, context):
        try:
            import json
            from pathlib import Path
            from datetime import datetime

            from .sensor_registry import SensorRegistry
            from .alert_engine import AlertEngine

            db_path = get_tandem_db_path(context)
            registry = SensorRegistry(db_path)
            alert_engine = AlertEngine(db_path)

            # Gather analytics data
            sensors = registry.list_sensors(active_only=True)
            alerts = alert_engine.get_active_alerts()

            analytics = {
                'export_timestamp': datetime.now().isoformat(),
                'building': 'Terminal 1',
                'total_sensors': len(sensors),
                'active_alerts': len(alerts),
                'sensors_by_type': {},
                'health_scores': {
                    'overall': 87,
                    'ACMV': 92,
                    'Electrical': 78,
                    'Fire': 95,
                    'Plumbing': 64,
                },
                'alerts': [
                    {
                        'sensor_id': alert.get('sensor_id'),
                        'severity': alert.get('severity'),
                        'message': alert.get('message'),
                        'timestamp': alert.get('timestamp'),
                    }
                    for alert in alerts
                ],
            }

            # Count sensors by type
            for sensor in sensors:
                sensor_type = sensor.get('sensor_type', 'Unknown')
                analytics['sensors_by_type'][sensor_type] = analytics['sensors_by_type'].get(sensor_type, 0) + 1

            # Default filename
            if not self.filepath:
                work_dir = Path.home() / 'Projects' / 'IfcOpenShell' / 'WORK_DIR'
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                self.filepath = str(work_dir / f'IoT_Analytics_{timestamp}.json')

            # Write JSON
            with open(self.filepath, 'w') as f:
                json.dump(analytics, f, indent=2)

            self.report({'INFO'}, f"Analytics exported to {self.filepath}")
            print(f"✅ Analytics exported: {self.filepath}")

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


# Registration
classes = (
    # Asset operators
    BIM_OT_import_assets_from_ifc,
    BIM_OT_import_assets_from_federation,  # NEW: Federation DB import
    BIM_OT_import_assets_from_csv,         # NEW: CSV import (external sources)
    BIM_OT_refresh_asset_list,
    BIM_OT_view_asset_details,
    BIM_OT_highlight_asset_in_3d,
    BIM_OT_update_asset_status,
    BIM_OT_visualize_assets_by_condition,
    BIM_OT_export_asset_report,
    # Maintenance operators (Phase 2)
    BIM_OT_generate_pm_schedule,
    BIM_OT_create_work_order,
    BIM_OT_refresh_work_order_list,
    BIM_OT_complete_work_order,
    BIM_OT_view_pm_summary,
    # IoT Command Center (Phase 3)
    BIM_OT_iot_generate_mock_data,
    BIM_OT_iot_export_analytics,
    BIM_OT_iot_switch_to_command_center,
    # Sensor Actions
    BIM_OT_view_sensor_history,
    BIM_OT_create_sensor_alert_rule,
    BIM_OT_create_sensor_work_order,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
