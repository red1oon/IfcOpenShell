# Bonsai - OpenBIM Blender Add-on
# River Equipment Maintenance Module (7D BIM)
# Extracted from equipment_placement.py

"""
Equipment Maintenance Operators
================================
7D BIM maintenance management operators:
- Context menu for right-click operations
- Preventive Maintenance (PM) schedule viewing
- Breakdown logging
- Work order creation
"""

import bpy
from bpy.types import Operator, Menu

# Import shared configuration
from .equipment_logger import LOGGER
from .equipment_config import EQUIPMENT_TYPES


# =============================================================================
# EQUIPMENT CONTEXT MENU
# =============================================================================

class BIM_MT_equipment_context_menu(Menu):
    """Context menu for equipment markers (right-click)"""
    bl_label = "Equipment Maintenance"
    bl_idname = "BIM_MT_equipment_context_menu"

    @classmethod
    def poll(cls, context):
        if not context.active_object:
            return False
        patterns = [eq_type.upper() + '_' for eq_type in EQUIPMENT_TYPES.keys()]
        return any(context.active_object.name.upper().startswith(p) for p in patterns)

    def draw(self, context):
        layout = self.layout
        layout.operator_context = 'INVOKE_DEFAULT'

        layout.label(text=context.active_object.name, icon='OUTLINER_OB_EMPTY')
        layout.separator()

        # 7D Maintenance Operations
        layout.operator("bim.equipment_view_pm_schedule", text="📅 View PM Schedule", icon='TIME')
        layout.operator("bim.equipment_log_breakdown", text="⚠ Log Breakdown", icon='ERROR')
        layout.operator("bim.equipment_create_work_order", text="🔧 Create Work Order", icon='FILE_NEW')

        layout.separator()

        # Sensor Dashboard
        layout.operator("bim.equipment_view_sensor_dashboard", text="📊 Sensor Dashboard", icon='GRAPH')
        layout.operator("bim.equipment_view_properties", text="ℹ View Details", icon='VIEWZOOM')


# =============================================================================
# VIEW PM SCHEDULE OPERATOR
# =============================================================================

class BIM_OT_equipment_view_pm_schedule(Operator):
    """View Preventive Maintenance Schedule for Equipment"""
    bl_idname = "bim.equipment_view_pm_schedule"
    bl_label = "View PM Schedule"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import sqlite3
        import subprocess
        import sys
        from . import river_utils

        obj = context.active_object
        if not obj:
            self.report({'ERROR'}, "No equipment selected")
            return {'CANCELLED'}

        # Extract marker ID from name (all equipment types)
        marker_id = None
        try:
            for eq_type in EQUIPMENT_TYPES.keys():
                pattern = eq_type.upper() + '_'
                if obj.name.upper().startswith(pattern):
                    num_str = obj.name.split('_')[-1]
                    marker_id = int(num_str)
                    break

            if marker_id is None:
                self.report({'ERROR'}, "Not a valid equipment marker")
                return {'CANCELLED'}
        except:
            self.report({'ERROR'}, "Could not parse equipment ID")
            return {'CANCELLED'}

        # Query PM schedule from database
        db_path = river_utils.RIVER_DB_PATH
        if not db_path.exists():
            self.report({'ERROR'}, f"Database not found: {db_path}")
            return {'CANCELLED'}

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # Get upcoming work orders for this equipment
            cursor.execute("""
                SELECT wo.work_order_number, wo.work_type, wo.title,
                       wo.due_date, wo.priority, wo.status,
                       wo.assigned_to, pm.template_name
                FROM work_orders wo
                LEFT JOIN pm_templates pm ON wo.pm_template_id = pm.id
                WHERE wo.equipment_marker_id = ?
                  AND wo.status IN ('Open', 'InProgress')
                ORDER BY wo.due_date ASC
                LIMIT 10
            """, (marker_id,))

            work_orders = cursor.fetchall()

            if not work_orders:
                self.report({'INFO'}, f"No upcoming PM work orders for {obj.name}")
                conn.close()
                return {'FINISHED'}

            # Format report
            report = f"\n{'='*70}\n"
            report += f"PM SCHEDULE - {obj.name}\n"
            report += f"{'='*70}\n\n"

            for wo in work_orders:
                (wo_number, wo_type, title, due_date, priority, status, assigned_to, template) = wo
                report += f"🔧 {wo_number} - {title}\n"
                report += f"   Type: {wo_type} | Priority: {priority} | Status: {status}\n"
                report += f"   Due: {due_date} | Assigned: {assigned_to or 'Unassigned'}\n"
                if template:
                    report += f"   Template: {template}\n"
                report += f"\n"

            report += f"{'='*70}\n"
            report += f"Total: {len(work_orders)} work orders\n"

            print(report)
            self.report({'INFO'}, f"Found {len(work_orders)} PM work orders (see console)")

            conn.close()

        except Exception as e:
            self.report({'ERROR'}, f"Database error: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

        return {'FINISHED'}


# =============================================================================
# LOG BREAKDOWN OPERATOR
# =============================================================================

class BIM_OT_equipment_log_breakdown(Operator):
    """Log Equipment Breakdown"""
    bl_idname = "bim.equipment_log_breakdown"
    bl_label = "Log Breakdown"
    bl_options = {'REGISTER', 'UNDO'}

    description: bpy.props.StringProperty(name="Description", default="")
    severity: bpy.props.EnumProperty(
        name="Severity",
        items=[
            ('LOW', "Low", "Minor issue"),
            ('MEDIUM', "Medium", "Requires attention"),
            ('HIGH', "High", "Urgent repair needed"),
            ('CRITICAL', "Critical", "Equipment offline")
        ],
        default='MEDIUM'
    )

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "severity")
        layout.prop(self, "description")

    def execute(self, context):
        import sqlite3
        from datetime import datetime
        from . import river_utils

        obj = context.active_object
        if not obj:
            self.report({'ERROR'}, "No equipment selected")
            return {'CANCELLED'}

        # Extract marker ID (all equipment types)
        marker_id = None
        try:
            for eq_type in EQUIPMENT_TYPES.keys():
                pattern = eq_type.upper() + '_'
                if obj.name.upper().startswith(pattern):
                    num_str = obj.name.split('_')[-1]
                    marker_id = int(num_str)
                    break

            if marker_id is None:
                self.report({'ERROR'}, "Not a valid equipment marker")
                return {'CANCELLED'}
        except:
            self.report({'ERROR'}, "Could not parse equipment ID")
            return {'CANCELLED'}

        db_path = river_utils.RIVER_DB_PATH
        if not db_path.exists():
            self.report({'ERROR'}, f"Database not found: {db_path}")
            return {'CANCELLED'}

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # Generate work order number
            cursor.execute("SELECT COUNT(*) FROM work_orders")
            count = cursor.fetchone()[0]
            wo_number = f"WO-{datetime.now().strftime('%Y%m%d')}-{count + 1:04d}"

            # Priority mapping
            priority_map = {
                'LOW': 'Low',
                'MEDIUM': 'Medium',
                'HIGH': 'High',
                'CRITICAL': 'Critical'
            }

            # Create corrective work order
            cursor.execute("""
                INSERT INTO work_orders (
                    work_order_number, equipment_marker_id, work_type,
                    priority, title, description, status,
                    created_by, created_date, scheduled_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                wo_number, marker_id, 'Corrective',
                priority_map[self.severity],
                f"BREAKDOWN - {obj.name}",
                self.description or "Equipment breakdown reported from Blender",
                'Open',
                'blender_user',
                datetime.now().isoformat(),
                datetime.now().date().isoformat()
            ))

            conn.commit()
            conn.close()

            self.report({'INFO'}, f"Breakdown logged: {wo_number}")
            print(f"\n✅ BREAKDOWN LOGGED")
            print(f"   Work Order: {wo_number}")
            print(f"   Equipment: {obj.name} (ID: {marker_id})")
            print(f"   Severity: {self.severity}")
            print(f"   Description: {self.description}\n")

        except Exception as e:
            self.report({'ERROR'}, f"Database error: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

        return {'FINISHED'}


# =============================================================================
# CREATE WORK ORDER OPERATOR
# =============================================================================

class BIM_OT_equipment_create_work_order(Operator):
    """Create Custom Work Order"""
    bl_idname = "bim.equipment_create_work_order"
    bl_label = "Create Work Order"
    bl_options = {'REGISTER', 'UNDO'}

    work_type: bpy.props.EnumProperty(
        name="Type",
        items=[
            ('PM', "Preventive Maintenance", "Scheduled PM"),
            ('Corrective', "Corrective", "Fix issue"),
            ('Inspection', "Inspection", "Routine inspection"),
            ('Emergency', "Emergency", "Urgent response")
        ],
        default='PM'
    )
    title: bpy.props.StringProperty(name="Title", default="")
    description: bpy.props.StringProperty(name="Description", default="")
    estimated_hours: bpy.props.FloatProperty(name="Est. Hours", default=2.0, min=0.1)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "work_type")
        layout.prop(self, "title")
        layout.prop(self, "description")
        layout.prop(self, "estimated_hours")

    def execute(self, context):
        import sqlite3
        from datetime import datetime, timedelta
        from . import river_utils

        obj = context.active_object
        if not obj:
            self.report({'ERROR'}, "No equipment selected")
            return {'CANCELLED'}

        # Extract marker ID (all equipment types)
        marker_id = None
        try:
            for eq_type in EQUIPMENT_TYPES.keys():
                pattern = eq_type.upper() + '_'
                if obj.name.upper().startswith(pattern):
                    num_str = obj.name.split('_')[-1]
                    marker_id = int(num_str)
                    break

            if marker_id is None:
                self.report({'ERROR'}, "Not a valid equipment marker")
                return {'CANCELLED'}
        except:
            self.report({'ERROR'}, "Could not parse equipment ID")
            return {'CANCELLED'}

        db_path = river_utils.RIVER_DB_PATH
        if not db_path.exists():
            self.report({'ERROR'}, f"Database not found: {db_path}")
            return {'CANCELLED'}

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # Generate work order number
            cursor.execute("SELECT COUNT(*) FROM work_orders")
            count = cursor.fetchone()[0]
            wo_number = f"WO-{datetime.now().strftime('%Y%m%d')}-{count + 1:04d}"

            # Due date: 7 days from now for PM, 1 day for Emergency
            days_ahead = 1 if self.work_type == 'Emergency' else 7
            due_date = (datetime.now().date() + timedelta(days=days_ahead)).isoformat()

            # Create work order
            cursor.execute("""
                INSERT INTO work_orders (
                    work_order_number, equipment_marker_id, work_type,
                    priority, title, description, status,
                    estimated_hours, due_date,
                    created_by, created_date, scheduled_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                wo_number, marker_id, self.work_type,
                'High' if self.work_type == 'Emergency' else 'Medium',
                self.title or f"{self.work_type} - {obj.name}",
                self.description,
                'Open',
                self.estimated_hours,
                due_date,
                'blender_user',
                datetime.now().isoformat(),
                datetime.now().date().isoformat()
            ))

            conn.commit()
            conn.close()

            self.report({'INFO'}, f"Work order created: {wo_number}")
            print(f"\n✅ WORK ORDER CREATED")
            print(f"   WO Number: {wo_number}")
            print(f"   Equipment: {obj.name} (ID: {marker_id})")
            print(f"   Type: {self.work_type}")
            print(f"   Title: {self.title}")
            print(f"   Due: {due_date}\n")

        except Exception as e:
            self.report({'ERROR'}, f"Database error: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

        return {'FINISHED'}


# =============================================================================
# CONTEXT MENU REGISTRATION FUNCTION
# =============================================================================

def menu_func(self, context):
    """Register context menu to appear on right-click"""
    if context.active_object:
        patterns = [eq_type.upper() + '_' for eq_type in EQUIPMENT_TYPES.keys()]
        if any(context.active_object.name.upper().startswith(p) for p in patterns):
            self.layout.separator()
            self.layout.menu("BIM_MT_equipment_context_menu", icon='TOOL_SETTINGS')
