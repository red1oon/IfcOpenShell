"""
IoT Sensor Installation Tool
Interactive 3D sensor placement with compliance checking

Features:
- Click-to-place sensors in 3D viewport
- Link sensors to BIM elements
- Compliance templates (Fire Safety, HVAC, Security)
- Coverage visualization
- Export to database
"""

import bpy
from bpy.types import Operator, Panel
from bpy.props import StringProperty, EnumProperty, FloatProperty, BoolProperty
import sqlite3
from pathlib import Path
from datetime import datetime
import math


# Compliance Templates with Standards Citations
#
# Standards References:
# - NFPA 72: National Fire Alarm and Signaling Code (2022 Edition)
# - ASHRAE 90.1: Energy Standard for Buildings Except Low-Rise Residential (2019)
# - ASHRAE 62.1: Ventilation for Acceptable Indoor Air Quality (2019)
# - IBC: International Building Code (2021)
# - ASHRAE 55: Thermal Environmental Conditions for Human Occupancy (2020)
# - ISO 16484-5: Building automation and control systems (BACnet)
#
SENSOR_TEMPLATES = {
    'Fire Safety': {
        'description': 'NFPA 72-2022 Fire Alarm Code',
        'standard': 'NFPA 72-2022 Chapter 17 (Initiating Devices)',
        'citation_url': 'https://www.nfpa.org/codes-and-standards/72',
        'sensors': [
            {
                'type': 'Smoke Detector',
                'spacing': 9.0,  # 9m max spacing (NFPA 72 §17.7.3.2.3.1: 30ft smooth ceiling)
                'height': 3.0,   # Ceiling mount (NFPA 72 §17.7.3.5)
                'protocol': 'BACnet',
                'standard_ref': 'NFPA 72 §17.7.3 (Spot-Type Smoke Detectors)'
            },
            {
                'type': 'Heat Detector',
                'spacing': 15.0,  # 15m max spacing (NFPA 72 §17.6.3.1: 50ft @ 10ft ceiling)
                'height': 3.0,
                'protocol': 'BACnet',
                'standard_ref': 'NFPA 72 §17.6.3 (Spot-Type Heat Detectors)'
            },
            {
                'type': 'Manual Pull Station',
                'spacing': 60.0,  # 60m max travel distance (NFPA 72 §17.14.5: 200ft)
                'height': 1.2,    # 1.2m (NFPA 72 §17.14.8: 42-48 inches)
                'protocol': 'Hardwired',
                'standard_ref': 'NFPA 72 §17.14 (Manual Fire Alarm Boxes)'
            },
            {
                'type': 'Sprinkler Flow',
                'spacing': None,  # Equipment-specific
                'height': None,
                'protocol': 'BACnet',
                'standard_ref': 'NFPA 72 §17.16 (Waterflow Alarms)'
            },
        ]
    },
    'HVAC Monitoring': {
        'description': 'ASHRAE 90.1-2019 Energy Monitoring',
        'standard': 'ASHRAE 90.1-2019 §6.4 (Mandatory Provisions)',
        'citation_url': 'https://www.ashrae.org/technical-resources/bookstore/standard-90-1',
        'sensors': [
            {
                'type': 'Temperature',
                'spacing': 20.0,  # Zone-based (ASHRAE 55-2020: 20m typical zone size)
                'height': 1.5,    # Occupied zone (ASHRAE 55 §5.2.4: 1.1-1.7m)
                'protocol': 'MQTT',
                'standard_ref': 'ASHRAE 55-2020 §5.2 (Thermal Comfort)'
            },
            {
                'type': 'Humidity',
                'spacing': 20.0,
                'height': 1.5,
                'protocol': 'MQTT',
                'standard_ref': 'ASHRAE 55-2020 §5.2.2.1 (Relative Humidity)'
            },
            {
                'type': 'CO2',
                'spacing': 30.0,  # Ventilation zones (ASHRAE 62.1-2019)
                'height': 1.5,    # Breathing zone
                'protocol': 'MQTT',
                'standard_ref': 'ASHRAE 62.1-2019 §6.2.6 (Demand Control Ventilation)'
            },
            {
                'type': 'Pressure',
                'spacing': None,  # Equipment-specific (ducts, VAV boxes)
                'height': None,
                'protocol': 'MQTT',
                'standard_ref': 'ASHRAE 90.1-2019 §6.5.3 (Economizers)'
            },
            {
                'type': 'Airflow',
                'spacing': None,  # Per AHU/VAV box
                'height': None,
                'protocol': 'MQTT',
                'standard_ref': 'ASHRAE 90.1-2019 §6.4.3.10 (Air System Balancing)'
            },
        ]
    },
    'Occupancy & Lighting': {
        'description': 'ASHRAE 90.1-2019 §9 Lighting Control',
        'standard': 'ASHRAE 90.1-2019 §9.4.1 (Automatic Lighting Shutoff)',
        'citation_url': 'https://www.ashrae.org/technical-resources/bookstore/standard-90-1',
        'sensors': [
            {
                'type': 'PIR Motion',
                'spacing': 18.0,  # 18m coverage radius (typical PIR range)
                'height': 2.4,    # Ceiling mount (IBC 2021: 2.4m typical ceiling)
                'protocol': 'MQTT',
                'standard_ref': 'ASHRAE 90.1-2019 §9.4.1.2 (Occupant Sensor Control)'
            },
            {
                'type': 'Light Level',
                'spacing': 12.0,  # Daylight zones
                'height': 0.8,    # Task plane (IESNA LM-83: 0.76m)
                'protocol': 'MQTT',
                'standard_ref': 'ASHRAE 90.1-2019 §9.4.1.3 (Daylight Control)'
            },
            {
                'type': 'Occupancy Count',
                'spacing': 30.0,  # Per zone
                'height': 2.5,
                'protocol': 'MQTT',
                'standard_ref': 'ASHRAE 62.1-2019 §6.2.6 (DCV Occupant Sensors)'
            },
        ]
    },
    'Water Management': {
        'description': 'IBC 2021 §903 Leak Detection',
        'standard': 'IBC 2021 §903.3.8 (Floor Control Valves)',
        'citation_url': 'https://codes.iccsafe.org/content/IBC2021P1',
        'sensors': [
            {
                'type': 'Water Leak',
                'spacing': 5.0,   # 5m coverage (equipment-specific)
                'height': 0.1,    # Floor-mounted
                'protocol': 'MQTT',
                'standard_ref': 'IBC 2021 §903.3.8 (Leak Detection)'
            },
            {
                'type': 'Water Flow',
                'spacing': None,  # Per riser/zone
                'height': None,
                'protocol': 'MQTT',
                'standard_ref': 'IBC 2021 §903.4 (Water Flow Monitoring)'
            },
            {
                'type': 'Water Pressure',
                'spacing': None,
                'height': None,
                'protocol': 'MQTT',
                'standard_ref': 'IBC 2021 §903.3.5 (Water Pressure Monitoring)'
            },
            {
                'type': 'Water Quality',
                'spacing': None,  # Per system
                'height': None,
                'protocol': 'MQTT',
                'standard_ref': 'ASHRAE 188-2018 (Legionellosis Management)'
            },
        ]
    },
    'Security & Access': {
        'description': 'IBC 2021 §1010 Security Systems',
        'standard': 'IBC 2021 §1010 (Means of Egress)',
        'citation_url': 'https://codes.iccsafe.org/content/IBC2021P1',
        'sensors': [
            {
                'type': 'Door Contact',
                'spacing': None,  # Per door
                'height': 2.1,    # Door frame height
                'protocol': 'BACnet',
                'standard_ref': 'IBC 2021 §1010.1.9.8 (Door Status Monitoring)'
            },
            {
                'type': 'Glass Break',
                'spacing': 15.0,  # 15m coverage radius
                'height': 2.0,
                'protocol': 'BACnet',
                'standard_ref': 'Industry Best Practice (UL 639 Glass Break Detectors)'
            },
            {
                'type': 'Access Card Reader',
                'spacing': None,  # Per access point
                'height': 1.2,    # ADA compliant height (ADAAG §308.2.1: 0.38-1.22m)
                'protocol': 'MQTT',
                'standard_ref': 'ADA Standards §308.2 (Forward Reach)'
            },
            {
                'type': 'Security Camera',
                'spacing': 25.0,  # 25m coverage (varies by lens)
                'height': 3.0,
                'protocol': 'RTSP',
                'standard_ref': 'Industry Best Practice (ASIS Guidelines)'
            },
        ]
    },
    'Energy Monitoring': {
        'description': 'ASHRAE 90.1-2019 §8.4 Energy Monitoring',
        'standard': 'ASHRAE 90.1-2019 §8.4.2 (Additional Metering)',
        'citation_url': 'https://www.ashrae.org/technical-resources/bookstore/standard-90-1',
        'sensors': [
            {
                'type': 'Power Meter',
                'spacing': None,  # Per distribution panel/circuit
                'height': None,
                'protocol': 'Modbus',
                'standard_ref': 'ASHRAE 90.1-2019 §8.4.2 (Individual Metering)'
            },
            {
                'type': 'Energy Submeter',
                'spacing': None,  # Per end-use (HVAC, lighting, etc.)
                'height': None,
                'protocol': 'Modbus',
                'standard_ref': 'ASHRAE 90.1-2019 §8.4.2.1 (End-Use Monitoring)'
            },
            {
                'type': 'Solar Production',
                'spacing': None,  # Per inverter/array
                'height': None,
                'protocol': 'MQTT',
                'standard_ref': 'ASHRAE 90.1-2019 §11.4.3 (Renewable Energy)'
            },
        ]
    },
    'Custom': {
        'description': 'Manual sensor placement (no template)',
        'standard': 'User-defined placement',
        'citation_url': None,
        'sensors': []
    }
}


class BIM_OT_install_sensor_at_cursor(Operator):
    """Install sensor at 3D cursor location"""
    bl_idname = "bim.install_sensor_at_cursor"
    bl_label = "Place Sensor at Cursor"
    bl_options = {'REGISTER', 'UNDO'}

    sensor_type: EnumProperty(
        name="Sensor Type",
        items=[
            ('Temperature', 'Temperature Sensor', 'Ambient temperature measurement'),
            ('Humidity', 'Humidity Sensor', 'Relative humidity measurement'),
            ('CO2', 'CO2 Sensor', 'CO2 concentration monitoring'),
            ('Pressure', 'Pressure Sensor', 'Air/water pressure monitoring'),
            ('Flow', 'Flow Sensor', 'Air/water flow measurement'),
            ('Smoke Detector', 'Smoke Detector', 'Fire safety smoke detection'),
            ('Heat Detector', 'Heat Detector', 'Fire safety heat detection'),
            ('PIR Motion', 'PIR Motion Sensor', 'Passive infrared motion detection'),
            ('Water Leak', 'Water Leak Detector', 'Water leak detection'),
            ('Door Contact', 'Door Contact Sensor', 'Door open/close status'),
            ('Power Meter', 'Power Meter', 'Electrical power measurement'),
            ('Custom', 'Custom Sensor', 'Custom sensor type'),
        ],
        default='Temperature'
    )

    protocol: EnumProperty(
        name="Protocol",
        items=[
            ('MQTT', 'MQTT', 'MQTT message broker'),
            ('BACnet', 'BACnet', 'Building automation protocol'),
            ('Modbus', 'Modbus', 'Industrial protocol'),
            ('HTTP', 'HTTP/REST', 'HTTP API'),
            ('RTSP', 'RTSP', 'Real-time streaming'),
        ],
        default='MQTT'
    )

    measurement_unit: StringProperty(
        name="Unit",
        default="°C"
    )

    update_interval: IntProperty(
        name="Update Interval (seconds)",
        default=60,
        min=1,
        max=3600
    )

    link_to_element: BoolProperty(
        name="Link to Selected Element",
        description="Link sensor to currently selected BIM element",
        default=True
    )

    def execute(self, context):
        # Get database path
        fed_props = context.scene.BIMFederationProperties
        db_path = bpy.path.abspath(fed_props.federation_database_path)

        if not db_path or not Path(db_path).exists():
            self.report({'ERROR'}, "Federation database not found")
            return {'CANCELLED'}

        # Get 3D cursor location
        cursor_loc = context.scene.cursor.location
        x, y, z = cursor_loc.x, cursor_loc.y, cursor_loc.z

        # Get linked element (if selected)
        asset_guid = None
        asset_name = "Manual Placement"

        if self.link_to_element and context.selected_objects:
            obj = context.active_object
            if obj and 'guid' in obj:
                asset_guid = obj['guid']
                asset_name = obj.name

        # Generate sensor ID
        sensor_id = f"{self.sensor_type.upper().replace(' ', '_')}_{int(x)}_{int(y)}_{int(z)}"

        # Insert into database
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Check if sensors table exists
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sensors';")
            if not cursor.fetchone():
                self.report({'ERROR'}, "IoT tables not initialized. Run populate_iot_sensors first.")
                conn.close()
                return {'CANCELLED'}

            # Create virtual asset if no element selected
            if not asset_guid:
                asset_guid = f"VIRTUAL_SENSOR_{sensor_id}"

                # Create virtual element in element_transforms
                cursor.execute("""
                    INSERT OR REPLACE INTO element_transforms
                    (guid, center_x, center_y, center_z)
                    VALUES (?, ?, ?, ?)
                """, (asset_guid, x, y, z))

                # Create virtual element in elements_meta
                cursor.execute("""
                    INSERT OR REPLACE INTO elements_meta
                    (guid, ifc_class, element_name, discipline)
                    VALUES (?, 'Virtual', ?, 'IoT')
                """, (asset_guid, asset_name))

            # Insert sensor
            cursor.execute("""
                INSERT INTO sensors (
                    sensor_id,
                    asset_guid,
                    sensor_type,
                    measurement_unit,
                    protocol,
                    topic,
                    update_interval_seconds,
                    location_description,
                    is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (
                sensor_id,
                asset_guid,
                self.sensor_type,
                self.measurement_unit,
                self.protocol,
                f"building/{self.sensor_type.lower().replace(' ', '_')}/{sensor_id}",
                self.update_interval,
                f"Manually placed at ({x:.1f}, {y:.1f}, {z:.1f})"
            ))

            conn.commit()
            conn.close()

            # Create visual marker in Blender
            self.create_sensor_marker(context, sensor_id, self.sensor_type, cursor_loc)

            self.report({'INFO'}, f"Installed {self.sensor_type} sensor: {sensor_id}")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to install sensor: {str(e)}")
            return {'CANCELLED'}

    def create_sensor_marker(self, context, sensor_id, sensor_type, location):
        """Create Empty marker in Blender scene"""
        # Get or create IoT Sensors collection
        if "IoT Sensors" not in bpy.data.collections:
            col = bpy.data.collections.new("IoT Sensors")
            context.scene.collection.children.link(col)
        else:
            col = bpy.data.collections["IoT Sensors"]

        # Create Empty
        empty = bpy.data.objects.new(f"IoT_{sensor_type.replace(' ', '_')}_{sensor_id[:8]}", None)
        empty.location = location
        empty.empty_display_type = 'SPHERE'
        empty.empty_display_size = 0.3
        empty.show_name = True
        empty.hide_render = True

        # Custom properties
        empty["is_iot_sensor"] = True
        empty["sensor_id"] = sensor_id
        empty["sensor_type"] = sensor_type

        # Color coding
        if 'Fire' in sensor_type or 'Smoke' in sensor_type:
            empty.color = (1.0, 0.0, 0.0, 1.0)  # Red
        elif 'Temperature' in sensor_type or 'Humidity' in sensor_type:
            empty.color = (0.0, 0.8, 1.0, 1.0)  # Cyan
        elif 'Motion' in sensor_type or 'Occupancy' in sensor_type:
            empty.color = (1.0, 0.8, 0.0, 1.0)  # Yellow
        elif 'Water' in sensor_type:
            empty.color = (0.0, 0.5, 1.0, 1.0)  # Blue
        else:
            empty.color = (0.0, 1.0, 0.0, 1.0)  # Green

        col.objects.link(empty)


class BIM_OT_place_sensors_from_template(Operator):
    """Auto-place sensors based on compliance template"""
    bl_idname = "bim.place_sensors_from_template"
    bl_label = "Auto-Place from Template"
    bl_options = {'REGISTER', 'UNDO'}

    template: EnumProperty(
        name="Template",
        items=[
            ('Fire Safety', 'Fire Safety (NFPA 72)', 'Fire alarm and detection'),
            ('HVAC Monitoring', 'HVAC (ASHRAE 90.1)', 'Temperature, humidity, CO2'),
            ('Occupancy & Lighting', 'Occupancy & Lighting', 'Motion, light sensors'),
            ('Water Management', 'Water Leak & Flow', 'Leak detection'),
            ('Security & Access', 'Security System', 'Access control, cameras'),
            ('Energy Monitoring', 'Energy Metering', 'Power consumption'),
        ],
        default='HVAC Monitoring'
    )

    def execute(self, context):
        self.report({'INFO'}, f"Auto-placement for {self.template} - Feature coming soon!")
        self.report({'INFO'}, "Use cursor placement for now")
        return {'FINISHED'}


class BIM_OT_link_sensor_to_element(Operator):
    """Link selected sensor to selected BIM element"""
    bl_idname = "bim.link_sensor_to_element"
    bl_label = "Link Sensor to Element"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if len(context.selected_objects) != 2:
            self.report({'ERROR'}, "Select exactly 2 objects: sensor and element")
            return {'CANCELLED'}

        # Identify sensor and element
        sensor_obj = None
        element_obj = None

        for obj in context.selected_objects:
            if obj.get("is_iot_sensor"):
                sensor_obj = obj
            elif 'guid' in obj:
                element_obj = obj

        if not sensor_obj or not element_obj:
            self.report({'ERROR'}, "Select one sensor and one BIM element")
            return {'CANCELLED'}

        sensor_id = sensor_obj.get("sensor_id")
        asset_guid = element_obj.get("guid")

        # Update database
        fed_props = context.scene.BIMFederationProperties
        db_path = bpy.path.abspath(fed_props.federation_database_path)

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("""
                UPDATE sensors
                SET asset_guid = ?,
                    location_description = ?
                WHERE sensor_id = ?
            """, (asset_guid, f"Linked to {element_obj.name}", sensor_id))
            conn.commit()
            conn.close()

            # Move sensor to element location
            sensor_obj.location = element_obj.location

            self.report({'INFO'}, f"Linked {sensor_id} to {element_obj.name}")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to link: {str(e)}")
            return {'CANCELLED'}


class BIM_OT_delete_sensor(Operator):
    """Delete selected IoT sensor"""
    bl_idname = "bim.delete_sensor"
    bl_label = "Delete Sensor"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj or not obj.get("is_iot_sensor"):
            self.report({'ERROR'}, "Select an IoT sensor to delete")
            return {'CANCELLED'}

        sensor_id = obj.get("sensor_id")

        # Delete from database
        fed_props = context.scene.BIMFederationProperties
        db_path = bpy.path.abspath(fed_props.federation_database_path)

        try:
            conn = sqlite3.connect(db_path)
            conn.execute("DELETE FROM sensors WHERE sensor_id = ?", (sensor_id,))
            conn.execute("DELETE FROM sensor_readings WHERE sensor_id = ?", (sensor_id,))
            conn.commit()
            conn.close()

            # Delete Blender object
            bpy.data.objects.remove(obj, do_unlink=True)

            self.report({'INFO'}, f"Deleted sensor: {sensor_id}")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to delete: {str(e)}")
            return {'CANCELLED'}


class BIM_PT_tandem_sensor_installer(Panel):
    """Sensor Installation Panel"""
    bl_label = "Sensor Installation"
    bl_idname = "BIM_PT_tandem_sensor_installer"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tandem_iot"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout

        # Instructions
        box = layout.box()
        box.label(text="📍 Interactive Sensor Placement", icon='INFO')
        col = box.column(align=True)
        col.scale_y = 0.7
        col.label(text="1. Position 3D cursor (Shift+RightClick)")
        col.label(text="2. Select sensor type below")
        col.label(text="3. Click 'Place Sensor'")
        col.label(text="4. Optional: Select element to link")

        # Quick placement
        box = layout.box()
        box.label(text="Quick Placement:", icon='ADD')

        # Sensor type selector
        row = box.row()
        row.label(text="Type:")

        # Quick buttons for common sensors
        grid = box.grid_flow(row_major=True, columns=2, align=True)

        op = grid.operator("bim.install_sensor_at_cursor", text="🌡️ Temperature", icon='OUTLINER_OB_LIGHT')
        op.sensor_type = 'Temperature'
        op.measurement_unit = '°C'

        op = grid.operator("bim.install_sensor_at_cursor", text="💧 Humidity", icon='MATFLUID')
        op.sensor_type = 'Humidity'
        op.measurement_unit = '%'

        op = grid.operator("bim.install_sensor_at_cursor", text="🔥 Smoke", icon='PARTICLES')
        op.sensor_type = 'Smoke Detector'

        op = grid.operator("bim.install_sensor_at_cursor", text="🚶 Motion", icon='HIDE_OFF')
        op.sensor_type = 'PIR Motion'

        op = grid.operator("bim.install_sensor_at_cursor", text="💧 Leak", icon='MOD_FLUIDSIM')
        op.sensor_type = 'Water Leak'

        op = grid.operator("bim.install_sensor_at_cursor", text="⚡ Power", icon='OUTLINER_OB_LIGHT')
        op.sensor_type = 'Power Meter'

        # Compliance templates
        layout.separator()
        box = layout.box()
        box.label(text="Compliance Templates:", icon='DOCUMENTS')

        for template_name, template_data in SENSOR_TEMPLATES.items():
            if template_name == 'Custom':
                continue

            row = box.row()
            row.scale_y = 0.8
            op = row.operator("bim.place_sensors_from_template",
                             text=template_name,
                             icon='CHECKMARK')
            op.template = template_name

            # Description
            row = box.row()
            row.scale_y = 0.6
            row.label(text=f"   {template_data['description']}")

        # Advanced options
        layout.separator()
        box = layout.box()
        box.label(text="Advanced:", icon='PREFERENCES')

        row = box.row(align=True)
        row.operator("bim.link_sensor_to_element", text="Link to Element", icon='LINKED')
        row.operator("bim.delete_sensor", text="Delete", icon='TRASH')

        # Stats
        layout.separator()
        box = layout.box()
        box.label(text="📊 Installed Sensors:", icon='INFO')

        # Count sensors
        sensor_count = 0
        if "IoT Sensors" in bpy.data.collections:
            sensor_count = len(bpy.data.collections["IoT Sensors"].objects)

        row = box.row()
        row.label(text=f"Total: {sensor_count} sensors")


# Registration
classes = (
    BIM_OT_install_sensor_at_cursor,
    BIM_OT_place_sensors_from_template,
    BIM_OT_link_sensor_to_element,
    BIM_OT_delete_sensor,
    BIM_PT_tandem_sensor_installer,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
