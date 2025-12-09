# Bonsai - OpenBIM Blender Add-on
# River Equipment Placement - Phase 1 POC
# Item 11: River Monitoring Equipment

"""
River Equipment Placement - Phase 1
====================================
Fresh implementation with comprehensive logging:
- Equipment type selection (3 types: Red/Blue/Green)
- Click-to-place with raycast
- Flat-colored gizmo spheres (NO pulse animation)
- Clear all function
- Full debug logging to console and file
"""

import bpy
from bpy.props import EnumProperty
from bpy.types import Panel, Operator
from bpy_extras import view3d_utils
from mathutils import Vector
from pathlib import Path
from datetime import datetime

# Import Google Maps operators from separate module
from . import river_map_background

# =============================================================================
# CONSOLE LOGGER
# =============================================================================

class RiverEquipmentLogger:
    """Logger that writes to both console and file for debugging"""

    def __init__(self):
        self.log_dir = Path.home() / "Documents" / "bonsai" / "consolelogs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "river_equipment_placement.txt"

        # Initialize log file
        header = f"""
{'='*70}
RIVER EQUIPMENT PLACEMENT - PHASE 1 POC
{'='*70}
Session: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Log File: {self.log_file}
{'='*70}
"""
        with open(self.log_file, 'w') as f:
            f.write(header + '\n')
        print(header)

    def log(self, message, error=False):
        """Log to both console and file"""
        prefix = "❌" if error else "→"
        formatted = f"{prefix} {message}"

        print(formatted)
        try:
            with open(self.log_file, 'a') as f:
                f.write(formatted + '\n')
        except:
            pass

        return formatted

    def section(self, title):
        """Log section header"""
        line = f"\n{'-'*70}"
        header = f"{title}"
        formatted = f"{line}\n{header}\n{line}"

        print(formatted)
        try:
            with open(self.log_file, 'a') as f:
                f.write(formatted + '\n')
        except:
            pass

# Global logger
LOGGER = RiverEquipmentLogger()
LOGGER.section("INITIALIZATION")
LOGGER.log("River Equipment Placement module loading...")

# =============================================================================
# EQUIPMENT TYPES
# =============================================================================

EQUIPMENT_TYPES = {
    'boom_trap': {
        'name': 'Boom Trap Station',
        'color': (1.0, 0.42, 0.21),  # Orange #FF6B35
        'icon': 'MESH_CIRCLE',
        'radius': 3.0
    },
    'water_quality': {
        'name': 'Water Quality Station',
        'color': (0.31, 0.80, 0.77),  # Turquoise #4ECDC4
        'icon': 'MATFLUID',
        'radius': 3.0
    },
    'biodiversity': {
        'name': 'Biodiversity Monitor',
        'color': (0.0, 1.0, 0.0),  # Green
        'icon': 'ORPHAN_DATA',
        'radius': 3.0
    },
    'wildlife_camera': {
        'name': 'Wildlife Camera',
        'color': (0.0, 1.0, 0.0),  # Green (alias for biodiversity)
        'icon': 'CAMERA_DATA',
        'radius': 3.0
    },
    'biochar': {
        'name': 'Biochar Facility',
        'color': (0.60, 0.93, 0.85),  # Mint #99EDD9
        'icon': 'EXPERIMENTAL',
        'radius': 3.0
    },
    'mrf': {
        'name': 'MRF Site',
        'color': (1.0, 0.75, 0.80),  # Pink #FFBFCC
        'icon': 'PREFERENCES',
        'radius': 3.0
    },
    'pollutant_sensor': {
        'name': 'Pollutant Sensor',
        'color': (0.67, 0.59, 0.85),  # Purple #AA96DA
        'icon': 'EXPERIMENTAL',
        'radius': 3.0
    },
    'flood_monitor': {
        'name': 'Flood Monitor',
        'color': (0.36, 0.61, 0.84),  # Blue #5B9BD5
        'icon': 'MOD_FLUIDSIM',
        'radius': 3.0
    },
}

# =============================================================================
# SENSOR TYPE ICON & COLOR MAPPINGS (Centralized)
# =============================================================================

# Sensor emoji icons - used in dashboard GPU overlay and popup displays
SENSOR_TYPE_ICONS = {
    # Boom Trap sensors
    'loadcell': '⚖️',
    'integrity': '🔧',
    'waterlevel': '🌊',
    'flowvelocity': '💨',
    'camera': '📹',
    'vibration': '📳',
    'gps_drift': '🛰️',
    'powerusage': '🔋',

    # Water Quality sensors
    'turbidity': '☁️',
    'heavymetals': '☢️',
    'ph': '🧪',
    'dissolvedoxygen': '💧',
    'temperature': '🌡️',
    'conductivity': '⚡',
    'nitrate': '🧬',
    'phosphate': '💎',

    # Biodiversity sensors
    'aicamera': '📷',
    'pirmotion': '👁️',
    'thermalcamera': '🔥',
    'audiorecorder': '🎤',
    'ultrasonic': '🦇',
    'ndvi': '🌿',
    'soilmoisture': '🌱',
    'canopy_height': '🌳',

    # Biochar Facility sensors
    'feedstock_mass': '🪵',
    'biochar_yield': '⚫',
    'pyrolysis_temp': '🔥',
    'carbon_content': '💨',
    'co2_emissions': '🌫️',
    'particulate': '💨',
    'reactor_pressure': '🔩',
    'energy_consumption': '⚡',

    # MRF Site sensors
    'conveyor_load': '📦',
    'pet_stream': '♻️',
    'hdpe_stream': '🥤',
    'organic_stream': '🍃',
    'contamination': '⚠️',
    'ai_sorter_accuracy': '🤖',
    'throughput': '📊',
    'power_usage': '🔌',

    # Flood Monitor sensors
    'flowrate': '🌊',
    'rainfall': '🌧️',
    'barometric': '🌐',
    'velocity_spike': '⚡',
    'debris_radar': '📡',
    'bridge_clearance': '🌉',
    'siren_status': '🚨',

    # Pollutant Sensor sensors
    'voc': '💨',
    'cod': '🧪',
    'bod': '🦠',
    'tss': '🌫️',
    'oil_grease': '🛢️',
    'cyanide': '☠️',
    'phenols': '⚗️',
}

# Sensor color mappings - RGB tuples for dashboard visualization
SENSOR_TYPE_COLORS = {
    # Boom Trap sensors
    'loadcell': (0.0, 0.5, 1.0),           # Blue
    'integrity': (1.0, 0.6, 0.0),          # Orange
    'waterlevel': (0.53, 0.81, 0.92),      # Light Blue
    'flowvelocity': (0.0, 0.8, 0.8),       # Teal
    'camera': (0.6, 0.4, 0.8),             # Purple
    'vibration': (1.0, 0.75, 0.0),         # Amber
    'gps_drift': (0.68, 0.85, 0.68),       # Light Green
    'powerusage': (1.0, 1.0, 0.0),         # Yellow

    # Water Quality sensors
    'turbidity': (0.6, 0.4, 0.2),          # Brown
    'heavymetals': (1.0, 0.0, 0.0),        # Red
    'ph': (0.75, 1.0, 0.0),                # Lime
    'dissolvedoxygen': (0.0, 1.0, 1.0),    # Cyan
    'temperature': (1.0, 0.27, 0.0),       # Orange-Red
    'conductivity': (0.93, 0.51, 0.93),    # Violet
    'nitrate': (0.0, 0.8, 0.0),            # Green
    'phosphate': (0.8, 1.0, 0.0),          # Yellow-Green

    # Biodiversity sensors
    'aicamera': (0.90, 0.70, 1.0),         # Lavender
    'pirmotion': (1.0, 1.0, 0.4),          # Bright Yellow
    'thermalcamera': (1.0, 0.1, 0.1),      # Bright Red
    'audiorecorder': (1.0, 0.0, 1.0),      # Magenta
    'ultrasonic': (0.53, 0.81, 0.98),      # Sky Blue
    'ndvi': (0.13, 0.55, 0.13),            # Forest Green
    'soilmoisture': (0.6, 0.4, 0.2),       # Soil Brown
    'canopy_height': (0.5, 1.0, 0.0),      # Bright Green

    # Biochar Facility sensors
    'feedstock_mass': (0.82, 0.71, 0.55),  # Tan
    'biochar_yield': (0.33, 0.33, 0.33),   # Dark Grey
    'pyrolysis_temp': (1.0, 0.15, 0.0),    # Fire Red
    'carbon_content': (0.18, 0.18, 0.18),  # Charcoal
    'co2_emissions': (0.5, 0.5, 0.5),      # Grey
    'particulate': (0.75, 0.75, 0.75),     # Light Grey
    'reactor_pressure': (1.0, 0.84, 0.0),  # Gold
    'energy_consumption': (1.0, 1.0, 0.2), # Bright Yellow

    # MRF Site sensors
    'conveyor_load': (0.42, 0.56, 0.64),   # Blue-Grey
    'pet_stream': (0.68, 0.85, 0.90),      # Light Blue
    'hdpe_stream': (0.96, 0.96, 0.96),     # White
    'organic_stream': (0.5, 0.5, 0.0),     # Olive
    'contamination': (1.0, 0.6, 0.0),      # Orange
    'ai_sorter_accuracy': (0.0, 1.0, 1.0), # Bright Cyan
    'throughput': (0.8, 0.8, 1.0),         # Periwinkle
    'power_usage': (1.0, 1.0, 0.2),        # Bright Yellow

    # Flood Monitor sensors
    'flowrate': (0.0, 0.4, 0.8),           # Ocean Blue
    'rainfall': (0.4, 0.6, 0.8),           # Rain Blue
    'barometric': (0.7, 0.75, 0.78),       # Light Blue-Grey
    'velocity_spike': (1.0, 0.2, 0.2),     # Alert Red
    'debris_radar': (1.0, 0.75, 0.0),      # Amber
    'bridge_clearance': (0.6, 0.98, 0.6),  # Mint
    'siren_status': (1.0, 0.0, 0.0),       # Alarm Red

    # Pollutant Sensor sensors
    'voc': (1.0, 0.75, 0.80),              # Pink
    'cod': (0.6, 0.4, 0.2),                # Brown
    'bod': (0.4, 0.3, 0.2),                # Mud
    'tss': (0.96, 0.96, 0.86),             # Beige
    'oil_grease': (0.1, 0.1, 0.1),         # Oil Black
    'cyanide': (1.0, 1.0, 0.5),            # Toxic Yellow
    'phenols': (1.0, 0.4, 0.6),            # Rose
}

# Global storage for placed equipment
PLACED_EQUIPMENT = {key: [] for key in EQUIPMENT_TYPES.keys()}

LOGGER.log(f"Loaded {len(EQUIPMENT_TYPES)} equipment types:")
for key, info in EQUIPMENT_TYPES.items():
    LOGGER.log(f"  • {info['name']} - RGB{info['color']}")

LOGGER.log(f"Loaded {len(SENSOR_TYPE_ICONS)} sensor type icons")
LOGGER.log(f"Loaded {len(SENSOR_TYPE_COLORS)} sensor type colors")

# =============================================================================
# OPERATORS
# =============================================================================

class BIM_OT_equipment_select_type(Operator):
    """Select equipment type for placement"""
    bl_idname = "bim.equipment_select_type"
    bl_label = "Select Equipment Type"
    bl_options = {'REGISTER'}

    equipment_type: EnumProperty(
        name="Equipment Type",
        items=[(k, v['name'], v['name']) for k, v in EQUIPMENT_TYPES.items()],
        default='boom_trap'
    )

    def execute(self, context):
        context.scene.equipment_marker_type = self.equipment_type
        selected_name = EQUIPMENT_TYPES[self.equipment_type]['name']

        LOGGER.section("EQUIPMENT TYPE SELECTED")
        LOGGER.log(f"User selected: {selected_name}")

        # Start placement mode - find 3D view and invoke there
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        # Override context to 3D view
                        override = context.copy()
                        override['area'] = area
                        override['region'] = region
                        with context.temp_override(**override):
                            bpy.ops.bim.equipment_place_marker('INVOKE_DEFAULT')
                        return {'FINISHED'}

        self.report({'ERROR'}, "No 3D View found")
        LOGGER.log("ERROR: No 3D View found", error=True)
        return {'CANCELLED'}

    def invoke(self, context, event):
        LOGGER.log("Opening equipment type selection dialog...")
        return context.window_manager.invoke_props_dialog(self, width=400)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Choose equipment to place:", icon='CURSOR')
        layout.separator()
        layout.prop(self, "equipment_type", text="Type")

        # Show equipment info
        info = EQUIPMENT_TYPES[self.equipment_type]
        box = layout.box()

        # Color display with emoji
        color_map = {
            'boom_trap': '🟠 Orange',
            'water_quality': '🩵 Turquoise',
            'biodiversity': '🟢 Green',
            'wildlife_camera': '🟢 Green',
            'biochar': '🟩 Mint',
            'mrf': '🩷 Pink',
            'pollutant_sensor': '🟣 Purple',
            'flood_monitor': '🔵 Blue',
        }
        color_name = color_map.get(self.equipment_type, '⚪ Unknown')

        box.label(text=f"Color: {color_name}")
        box.label(text=f"Radius: {info['radius']}m")

        # Show sensor count
        sensor_counts = {
            'boom_trap': 8,
            'water_quality': 8,
            'biodiversity': 8,
            'wildlife_camera': 8,
            'biochar': 8,
            'mrf': 8,
            'pollutant_sensor': 8,
            'flood_monitor': 8,
        }
        box.label(text=f"Sensors: {sensor_counts.get(self.equipment_type, 0)} IoT devices")


class BIM_OT_equipment_place_marker(Operator):
    """Place equipment markers by clicking (Phase 1: Basic placement)"""
    bl_idname = "bim.equipment_place_marker"
    bl_label = "Place Equipment Marker"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        """Check if we can run - need 3D view available"""
        # Allow if current area is 3D view OR if any 3D view exists
        if context.area and context.area.type == 'VIEW_3D':
            return True
        # Check if any screen has a 3D view
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                return True
        return False

    def modal(self, context, event):
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            LOGGER.log(f"CLICK detected at ({event.mouse_region_x}, {event.mouse_region_y})")

            coord = event.mouse_region_x, event.mouse_region_y
            hit_location = self.get_click_location(context, coord)

            if hit_location:
                LOGGER.log(f"  ✓ Hit surface at {hit_location}")
                self.create_flat_gizmo_sphere(context, hit_location)
                return {'RUNNING_MODAL'}
            else:
                LOGGER.log(f"  ✗ No surface hit", error=True)
                self.report({'WARNING'}, "Click on a surface!")
                return {'RUNNING_MODAL'}

        elif event.type in {'RIGHTMOUSE', 'ESC'}:
            equipment_type = context.scene.equipment_marker_type
            count = len(PLACED_EQUIPMENT.get(equipment_type, []))
            LOGGER.section("PLACEMENT MODE FINISHED")
            LOGGER.log(f"Placed {count} {EQUIPMENT_TYPES[equipment_type]['name']}(s)")

            # Save to database
            self.save_to_database()

            self.report({'INFO'}, f"Placed {count} {EQUIPMENT_TYPES[equipment_type]['name']}(s)")
            return {'FINISHED'}

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        equipment_type = context.scene.equipment_marker_type
        equipment_name = EQUIPMENT_TYPES[equipment_type]['name']

        LOGGER.section("PLACEMENT MODE ACTIVATED")
        LOGGER.log(f"Equipment type: {equipment_name}")
        LOGGER.log("→ Left-click to place")
        LOGGER.log("→ ESC or Right-click to finish")

        wm = context.window_manager
        wm.modal_handler_add(self)

        self.report({'INFO'}, f"Placing {equipment_name}. Click to place, ESC to finish.")
        return {'RUNNING_MODAL'}

    def get_click_location(self, context, coord):
        """Raycast to find surface at click location"""
        region = context.region
        rv3d = context.region_data

        # Debug: Check scene objects
        visible_objects = [obj for obj in context.scene.objects if obj.visible_get()]
        LOGGER.log(f"  → Scene has {len(visible_objects)} visible objects")
        if len(visible_objects) > 0:
            LOGGER.log(f"  → Sample objects: {[obj.name for obj in visible_objects[:5]]}")

        # Convert 2D mouse position to 3D ray
        view_vector = view3d_utils.region_2d_to_vector_3d(region, rv3d, coord)
        ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, coord)

        LOGGER.log(f"  → Ray origin: {ray_origin}")
        LOGGER.log(f"  → Ray direction: {view_vector}")

        # Raycast against scene with extended distance
        depsgraph = context.evaluated_depsgraph_get()

        # Normalize and extend ray vector for long distance
        ray_vector = view_vector.normalized() * 10000.0  # 10km ray

        result, location, normal, index, obj, matrix = context.scene.ray_cast(
            depsgraph, ray_origin, ray_vector
        )

        if result:
            LOGGER.log(f"  ✓ Hit object: {obj.name if obj else 'Unknown'}")
            LOGGER.log(f"  ✓ Hit location: {location}")
            return location
        else:
            LOGGER.log(f"  ✗ No surface hit (tried {len(visible_objects)} objects)", error=True)
        return None

    def create_flat_gizmo_sphere(self, context, location):
        """Create Empty gizmo with constant screen-space size (like Clash Gizmo)"""
        global PLACED_EQUIPMENT

        equipment_type = context.scene.equipment_marker_type
        equipment_info = EQUIPMENT_TYPES[equipment_type]
        count = len(PLACED_EQUIPMENT[equipment_type]) + 1

        LOGGER.section(f"CREATING GIZMO #{count}")
        LOGGER.log(f"Type: {equipment_info['name']}")
        LOGGER.log(f"Location: ({location.x:.1f}, {location.y:.1f}, {location.z:.1f})")
        LOGGER.log(f"Color: RGB{equipment_info['color']}")

        # Create Empty object (constant screen-space size like Clash Gizmo)
        empty = bpy.data.objects.new(f"{equipment_type.upper()}_{count:03d}", None)
        empty.location = location
        empty.empty_display_type = 'SPHERE'
        empty.empty_display_size = 100.0  # Much larger for visibility
        empty.show_name = True  # Show name in viewport

        # Set color
        color = equipment_info['color']
        empty.color = (*color, 1.0)  # RGBA
        empty.show_in_front = True  # Always visible on top

        # Get or create collection for this equipment type
        parent_collection_name = "River Equipment"
        if parent_collection_name not in bpy.data.collections:
            parent_collection = bpy.data.collections.new(parent_collection_name)
            context.scene.collection.children.link(parent_collection)
        else:
            parent_collection = bpy.data.collections[parent_collection_name]

        collection_name = equipment_info['name'] + 's'  # Plural
        if collection_name not in bpy.data.collections:
            eq_collection = bpy.data.collections.new(collection_name)
            parent_collection.children.link(eq_collection)
        else:
            eq_collection = bpy.data.collections[collection_name]

        # Add to type-specific collection
        eq_collection.objects.link(empty)

        LOGGER.log(f"→ Created empty: {empty.name}")
        LOGGER.log(f"→ Display type: SPHERE (constant screen-space size)")
        LOGGER.log(f"→ Color: RGB{color}")
        LOGGER.log(f"→ Show in front: True")

        # Store equipment data
        PLACED_EQUIPMENT[equipment_type].append({
            'id': empty.name,
            'number': count,
            'x': location.x,
            'y': location.y,
            'z': location.z,
            'object': empty,
            'object_name': empty.name
        })

        LOGGER.log(f"✅ Gizmo #{count} created successfully (Empty object)")

        # Trigger gizmo refresh to show new equipment
        self.refresh_equipment_gizmos()

        self.report({'INFO'}, f"{equipment_info['name']} #{count} placed")

    def refresh_equipment_gizmos(self):
        """Refresh equipment gizmo group to show updated equipment"""
        try:
            # Find equipment gizmo group and refresh it
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            # Gizmo groups auto-refresh via poll, but we can force update
                            space.show_gizmo = True  # Ensure gizmos enabled
                            area.tag_redraw()
                            LOGGER.log("→ Triggered gizmo refresh")
                            break
        except Exception as e:
            LOGGER.log(f"Warning: Could not refresh gizmos: {e}")

    def save_to_database(self):
        """Save all placed equipment to database with auto-generated sensors and GPS coords"""
        import sqlite3
        import sys
        from pathlib import Path
        from datetime import datetime

        db_path = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db")

        if not db_path.exists():
            LOGGER.log("Database not found, skipping save", error=True)
            return

        try:
            # Import sensor generation module
            sensor_defs_path = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/scripts")
            if str(sensor_defs_path) not in sys.path:
                sys.path.insert(0, str(sensor_defs_path))

            from sensor_definitions import create_sensors_for_equipment
            from georeferencing import GeoReferencing

            # Initialize georeferencing
            geo = GeoReferencing(db_path)

            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            LOGGER.section("SAVING TO DATABASE")

            total_saved = 0
            total_sensors = 0

            for equipment_type, items in PLACED_EQUIPMENT.items():
                if not items:
                    continue

                equipment_info = EQUIPMENT_TYPES[equipment_type]
                color_hex = '#{:02x}{:02x}{:02x}'.format(
                    int(equipment_info['color'][0] * 255),
                    int(equipment_info['color'][1] * 255),
                    int(equipment_info['color'][2] * 255)
                )

                for item in items:
                    # Use marker_id from item number
                    marker_id = item['number']
                    name = f"{equipment_info['name']} #{marker_id}"

                    # Calculate GPS coordinates
                    latitude, longitude, elevation = geo.blender_to_gps(item['x'], item['y'], item['z'])

                    # Save equipment marker
                    cursor.execute("""
                        INSERT OR REPLACE INTO project_markers (
                            marker_id, marker_type, name, description,
                            location_x, location_y, location_z,
                            latitude, longitude, gps_elevation,
                            color, priority, status,
                            installation_date, position_source
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        marker_id,
                        equipment_type,
                        name,
                        f"{equipment_info['name']} placed via Blender UI",
                        item['x'],
                        item['y'],
                        item['z'],
                        latitude,
                        longitude,
                        elevation,
                        color_hex,
                        'MEDIUM',
                        'ACTIVE',
                        datetime.now().isoformat(),
                        'manual'  # User-placed
                    ))
                    total_saved += 1
                    LOGGER.log(f"  Saved: {name} at ({item['x']:.1f}, {item['y']:.1f}, {item['z']:.1f})")
                    LOGGER.log(f"    GPS: {latitude:.6f}°N, {longitude:.6f}°E")

                    # Auto-generate sensors for this equipment
                    sensors = create_sensors_for_equipment(equipment_type, marker_id, marker_id)

                    for sensor in sensors:
                        cursor.execute("""
                            INSERT OR REPLACE INTO sensors (
                                sensor_id, equipment_marker_id, sensor_type, sensor_name, unit,
                                api_endpoint, mqtt_topic,
                                threshold_min, threshold_max, calibration_date,
                                manufacturer, model, installation_date, status
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            sensor['sensor_id'],
                            sensor['equipment_marker_id'],
                            sensor['sensor_type'],
                            sensor['sensor_name'],
                            sensor['unit'],
                            sensor['api_endpoint'],
                            sensor['mqtt_topic'],
                            sensor['threshold_min'],
                            sensor['threshold_max'],
                            sensor['calibration_date'],
                            sensor['manufacturer'],
                            sensor['model'],
                            sensor['installation_date'],
                            sensor['status'],
                        ))
                        total_sensors += 1
                        LOGGER.log(f"    → Sensor: {sensor['sensor_id']} ({sensor['sensor_name']})")

            conn.commit()
            conn.close()

            LOGGER.log(f"✅ Saved {total_saved} equipment markers to database")
            LOGGER.log(f"✅ Created {total_sensors} IoT sensors with unique IDs")
            LOGGER.log(f"Database: {db_path}")

        except Exception as e:
            LOGGER.log(f"ERROR saving to database: {e}", error=True)
            import traceback
            traceback.print_exc()


class BIM_OT_equipment_load_from_db(Operator):
    """Load equipment from database"""
    bl_idname = "bim.equipment_load_from_db"
    bl_label = "Load from Database"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        global PLACED_EQUIPMENT
        import sqlite3
        from pathlib import Path

        db_path = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db")

        if not db_path.exists():
            self.report({'ERROR'}, "Database not found")
            LOGGER.log("Database not found", error=True)
            return {'CANCELLED'}

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            LOGGER.section("LOADING FROM DATABASE")

            # River markers and meshes are in world coordinates (no offset needed)
            # River objects are at origin with transforms applied to geometry
            mesh_offset = (0.0, 0.0, 0.0)
            LOGGER.log(f"River equipment uses world coordinates (no offset applied)")

            # Query equipment markers (all types) - MUST include marker_id for sensor lookup
            marker_types = ', '.join([f"'{mt}'" for mt in EQUIPMENT_TYPES.keys()])
            cursor.execute(f"""
                SELECT marker_id, marker_type, name, location_x, location_y, location_z
                FROM project_markers
                WHERE marker_type IN ({marker_types})
                ORDER BY marker_id
            """)

            rows = cursor.fetchall()
            conn.close()

            if not rows:
                LOGGER.log("No equipment found in database")
                self.report({'INFO'}, "No equipment in database")
                return {'FINISHED'}

            LOGGER.log(f"Found {len(rows)} equipment markers in database")

            # Clear existing
            for equipment_type in EQUIPMENT_TYPES.keys():
                PLACED_EQUIPMENT[equipment_type] = []

            # Remove ALL old equipment objects and collections
            parent_collection_name = "River Equipment"
            if parent_collection_name in bpy.data.collections:
                old_parent = bpy.data.collections[parent_collection_name]
                LOGGER.log(f"Clearing old parent collection: {parent_collection_name}")

                # Recursively delete all child collections and their objects
                for child_coll in list(old_parent.children):
                    # Delete all objects in child collection
                    for obj in list(child_coll.objects):
                        bpy.data.objects.remove(obj, do_unlink=True)
                    # Unlink and remove child collection
                    old_parent.children.unlink(child_coll)
                    bpy.data.collections.remove(child_coll)

                # Delete any objects directly in parent
                for obj in list(old_parent.objects):
                    bpy.data.objects.remove(obj, do_unlink=True)

                # Unlink parent from scene
                context.scene.collection.children.unlink(old_parent)
                # Remove parent collection
                bpy.data.collections.remove(old_parent)
                LOGGER.log("  All old equipment cleared")

            # Create fresh parent collection
            parent_collection = bpy.data.collections.new(parent_collection_name)
            context.scene.collection.children.link(parent_collection)
            LOGGER.log(f"Created fresh parent collection: {parent_collection_name}")

            # Create fresh collections for each equipment type
            equipment_collections = {}
            for eq_type in EQUIPMENT_TYPES.keys():
                eq_info = EQUIPMENT_TYPES[eq_type]
                collection_name = eq_info['name'] + 's'  # Plural

                # Create new collection (old ones already cleared above)
                eq_collection = bpy.data.collections.new(collection_name)
                parent_collection.children.link(eq_collection)
                equipment_collections[eq_type] = eq_collection
                LOGGER.log(f"  Created collection: {collection_name}")

            # Create empties from database, organized by collection
            total_loaded = 0
            for marker_id, marker_type, name, x, y, z in rows:
                if marker_type not in EQUIPMENT_TYPES:
                    LOGGER.log(f"WARNING: Unknown marker type '{marker_type}' - skipping", error=True)
                    continue

                equipment_info = EQUIPMENT_TYPES[marker_type]
                count = len(PLACED_EQUIPMENT[marker_type]) + 1

                # Apply same transform as mesh baking (offset at display time)
                # DB stores raw vertex coords, offset applied when creating empty
                location = Vector((x + mesh_offset[0], y + mesh_offset[1], z + mesh_offset[2]))
                empty = bpy.data.objects.new(f"{marker_type.upper()}_{count:03d}", None)
                empty.location = location
                empty.empty_display_type = 'SPHERE'
                empty.empty_display_size = 100.0
                empty.show_name = True

                color = equipment_info['color']
                empty.color = (*color, 1.0)
                empty.show_in_front = True

                # Store marker_id as custom property for sensor lookup
                empty["marker_id"] = marker_id

                # Link to type-specific collection
                equipment_collections[marker_type].objects.link(empty)

                # Store with offset-applied coordinates (same as empty.location)
                # Gizmos read from here, so must match empty position
                stored_x = x + mesh_offset[0]
                stored_y = y + mesh_offset[1]
                stored_z = z + mesh_offset[2]

                PLACED_EQUIPMENT[marker_type].append({
                    'id': empty.name,
                    'number': count,
                    'marker_id': marker_id,  # Store actual DB marker_id for sensor lookup
                    'x': stored_x,
                    'y': stored_y,
                    'z': stored_z,
                    'object': empty,
                    'object_name': empty.name
                })

                total_loaded += 1
                LOGGER.log(f"  Loaded: {name} (marker_id={marker_id}) - DB:({x:.1f}, {y:.1f}, {z:.1f}) → Display:({stored_x:.1f}, {stored_y:.1f}, {stored_z:.1f})")

            LOGGER.log(f"✅ Loaded {total_loaded} equipment markers from database")

            # Force gizmo refresh by triggering viewport update
            # Gizmos read from PLACED_EQUIPMENT which now has offset-applied coords
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            # Force gizmo group to refresh
                            space.show_gizmo = False
                            space.show_gizmo = True
                    area.tag_redraw()

            LOGGER.log(f"Equipment stored with offset: ({mesh_offset[0]:.2f}, {mesh_offset[1]:.2f}, {mesh_offset[2]:.2f})")

            self.report({'INFO'}, f"Loaded {total_loaded} equipment from database")
            return {'FINISHED'}

        except Exception as e:
            LOGGER.log(f"ERROR loading from database: {e}", error=True)
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, f"Failed to load: {str(e)}")
            return {'CANCELLED'}


# =============================================================================
# SENSOR DASHBOARD - HELPER CLASSES (Refactored Design)
# =============================================================================

class SensorStatusCalculator:
    """Calculates equipment status from sensor readings"""

    STATUS_PRIORITY = {
        'OK': 0,
        'INSPECTION': 1,
        'PM_ACTION': 2,
        'FOLLOW_SOP': 3,
        'REPAIR': 4
    }

    STATUS_COLORS = {
        'OK': (0.2, 0.8, 0.2, 0.6),         # Green, low opacity
        'INSPECTION': (0.9, 0.7, 0.2, 0.7),  # Yellow
        'PM_ACTION': (0.9, 0.5, 0.1, 0.8),   # Orange
        'FOLLOW_SOP': (0.9, 0.2, 0.1, 0.9),  # Red-orange
        'REPAIR': (0.9, 0.1, 0.1, 1.0),      # Bright red
    }

    STATUS_ICONS = {
        'OK': '✓',
        'INSPECTION': '🔍',
        'PM_ACTION': '⚠️',
        'FOLLOW_SOP': '🚨',
        'REPAIR': '🔧',
    }

    @staticmethod
    def calculate_sensor_status(value, threshold_min, threshold_max):
        """
        Determines status based on threshold breach severity
        Returns: 'OK', 'INSPECTION', 'PM_ACTION', 'FOLLOW_SOP', or 'REPAIR'
        """
        if value is None:
            return 'OK'

        # Check if outside safe range
        breach_pct = 0
        if threshold_min is not None and value < threshold_min:
            breach_pct = abs(value - threshold_min) / max(threshold_min, 0.01) * 100
        elif threshold_max is not None and value > threshold_max:
            breach_pct = abs(value - threshold_max) / max(threshold_max, 0.01) * 100
        else:
            return 'OK'

        # Severity levels
        if breach_pct > 50:
            return 'REPAIR'
        elif breach_pct > 30:
            return 'FOLLOW_SOP'
        elif breach_pct > 15:
            return 'PM_ACTION'
        else:
            return 'INSPECTION'

    @staticmethod
    def get_marker_status(marker_id, db_path):
        """
        Returns worst sensor status for this marker
        Priority: REPAIR > FOLLOW_SOP > PM_ACTION > INSPECTION > OK
        """
        import sqlite3

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT s.sensor_type, sr.value, s.threshold_min, s.threshold_max
                FROM sensors s
                LEFT JOIN sensor_readings sr ON s.sensor_id = sr.sensor_id
                WHERE s.equipment_marker_id = ?
                  AND sr.timestamp LIKE 'Day 7%'
                ORDER BY s.sensor_type
            """, (marker_id,))

            results = cursor.fetchall()
            if not results:
                # No sensor data for this marker
                conn.close()
                return 'OK'

            worst_status = 'OK'

            for sensor_type, value, tmin, tmax in results:
                status = SensorStatusCalculator.calculate_sensor_status(value, tmin, tmax)
                if SensorStatusCalculator.STATUS_PRIORITY[status] > SensorStatusCalculator.STATUS_PRIORITY[worst_status]:
                    worst_status = status

            conn.close()
            return worst_status

        except Exception as e:
            LOGGER.log(f"ERROR calculating status for marker {marker_id}: {e}", error=True)
            return 'OK'


class GlobalAlertView:
    """Manages global alert beacon rendering and filtering"""

    def __init__(self, db_path):
        self.db_path = db_path
        self.filtered_markers = []
        self.filter_zones = ['ZONE_I_EAST', 'ZONE_II_MIDDLE', 'ZONE_III_WEST']
        self.filter_equipment_types = list(EQUIPMENT_TYPES.keys())
        self.alert_mode = 'AUTO'  # AUTO, ALL_CRITICAL, REPAIR_ONLY, etc.
        self._cached_markers = None
        self._cache_valid = False

    def get_filtered_markers(self):
        """
        Query database for markers matching current filters
        Returns list of dicts with marker info and status
        """
        # Return cached results if still valid
        if self._cache_valid and self._cached_markers is not None:
            return self._cached_markers

        import sqlite3

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Build zone filter
            zone_placeholders = ','.join('?' * len(self.filter_zones))
            equipment_placeholders = ','.join('?' * len(self.filter_equipment_types))

            query = f"""
                SELECT id, marker_type, location_x, location_y, location_z, river_section
                FROM project_markers
                WHERE river_section IN ({zone_placeholders})
                  AND marker_type IN ({equipment_placeholders})
            """

            cursor.execute(query, self.filter_zones + self.filter_equipment_types)
            raw_results = cursor.fetchall()

            markers = []
            for marker_id, marker_type, x, y, z, section in raw_results:
                # Calculate status
                status = SensorStatusCalculator.get_marker_status(marker_id, self.db_path)

                # Apply alert level filter
                if self._should_include_status(status):
                    markers.append({
                        'marker_id': marker_id,
                        'equipment_type': marker_type,
                        'location': (x, y, z),
                        'river_section': section,
                        'status': status
                    })

            conn.close()

            # Sort by priority (worst first)
            markers.sort(key=lambda m: SensorStatusCalculator.STATUS_PRIORITY[m['status']], reverse=True)

            # Apply AUTO limit (max 20)
            if self.alert_mode == 'AUTO' and len(markers) > 20:
                markers = markers[:20]

            # Cache the results
            self._cached_markers = markers
            self._cache_valid = True

            return markers

        except Exception as e:
            LOGGER.log(f"ERROR querying filtered markers: {e}", error=True)
            return []

    def _should_include_status(self, status):
        """Check if status matches current alert mode filter"""
        if self.alert_mode == 'AUTO':
            # Include up to 20 worst
            return True
        elif self.alert_mode == 'ALL_CRITICAL':
            return status in ['REPAIR', 'FOLLOW_SOP', 'PM_ACTION']
        elif self.alert_mode == 'REPAIR_ONLY':
            return status == 'REPAIR'
        elif self.alert_mode == 'FOLLOW_SOP_ONLY':
            return status == 'FOLLOW_SOP'
        elif self.alert_mode == 'PM_ACTION_ONLY':
            return status == 'PM_ACTION'
        else:
            return True

    def create_beacon_objects(self, context):
        """
        Create Blender empties for each beacon (appears in outliner)
        These replace pure GPU drawing for better UX
        """
        import bpy

        # Clean up existing beacons - more robust approach
        beacon_collection_name = "River_Alert_Beacons"

        # First pass: Remove all beacon objects by type
        objects_to_remove = []
        for obj in bpy.data.objects:
            if obj.get("beacon_type") == "alert_beacon":
                objects_to_remove.append(obj)

        for obj in objects_to_remove:
            bpy.data.objects.remove(obj, do_unlink=True)

        # Second pass: Clean up collection
        if beacon_collection_name in bpy.data.collections:
            old_collection = bpy.data.collections[beacon_collection_name]

            # Unlink from all scenes
            for scene in bpy.data.scenes:
                if old_collection.name in scene.collection.children:
                    scene.collection.children.unlink(old_collection)

            # Remove the collection
            bpy.data.collections.remove(old_collection)

        # Create fresh collection for beacons
        beacon_collection = bpy.data.collections.new(beacon_collection_name)
        context.scene.collection.children.link(beacon_collection)

        # Build a map of marker_id to equipment Blender object
        marker_to_object = {}
        for obj in bpy.data.objects:
            if obj.get("marker_id"):
                marker_to_object[obj["marker_id"]] = obj

        markers = self.get_filtered_markers()
        for marker in markers:
            marker_id = marker['marker_id']

            if marker_id not in marker_to_object:
                continue

            # Get equipment object location
            equipment_obj = marker_to_object[marker_id]
            x, y, z = equipment_obj.location
            z += 50.0  # Raise beacon 50m above equipment

            # Create beacon empty
            status = marker['status']
            equipment_type = marker['equipment_type']
            beacon_name = f"BEACON_{status}_{equipment_type}_{marker_id}"
            beacon = bpy.data.objects.new(beacon_name, None)
            beacon.location = (x, y, z)
            beacon.empty_display_type = 'SPHERE'
            beacon.empty_display_size = 200.0  # 200m radius

            # Color code by status
            color = SensorStatusCalculator.STATUS_COLORS[status]
            beacon.color = color

            # Store metadata
            beacon["beacon_type"] = "alert_beacon"
            beacon["marker_id"] = marker_id
            beacon["status"] = status
            beacon["equipment_type"] = equipment_type

            # Add to collection
            beacon_collection.objects.link(beacon)

        LOGGER.log(f"✓ Created {len(markers)} beacon objects in outliner")

    def draw_beacons_3d(self, context):
        """
        Render large 3D world-space spheres visible from any distance
        Similar scale to equipment but bigger and pulsing
        """
        import bpy
        import gpu
        from gpu_extras.batch import batch_for_shader
        import math
        import time

        # Use cached markers (no repeated queries)
        markers = self.get_filtered_markers()
        if not markers:
            return

        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('LESS_EQUAL')

        # Build a map of marker_id to Blender object
        marker_to_object = {}
        for obj in bpy.data.objects:
            if obj.get("marker_id"):
                marker_to_object[obj["marker_id"]] = obj

        # Pulsing animation (scale)
        pulse_time = time.time()
        pulse_scale = 1.0 + 0.3 * math.sin(pulse_time * 3.0)  # Pulse between 1.0 and 1.3

        for marker in markers:
            marker_id = marker['marker_id']

            # Try to find the actual Blender object for this marker
            if marker_id not in marker_to_object:
                continue

            # Use the actual Blender object location (already has correct offset)
            obj = marker_to_object[marker_id]
            x, y, z = obj.location
            z += 50.0  # Raise beacon 50m above equipment so it's very visible

            status = marker['status']
            color = SensorStatusCalculator.STATUS_COLORS[status]

            # Draw LARGE 3D sphere (200m radius = very visible from afar)
            sphere_radius = 200.0 * pulse_scale
            num_segments = 16
            num_rings = 8

            # Generate wireframe sphere vertices
            vertices = []
            for ring in range(num_rings + 1):
                theta = math.pi * ring / num_rings
                for segment in range(num_segments + 1):
                    phi = 2.0 * math.pi * segment / num_segments

                    sx = sphere_radius * math.sin(theta) * math.cos(phi)
                    sy = sphere_radius * math.sin(theta) * math.sin(phi)
                    sz = sphere_radius * math.cos(theta)

                    vertices.append((x + sx, y + sy, z + sz))

            # Draw sphere wireframe (horizontal rings)
            for ring in range(num_rings + 1):
                ring_verts = []
                for segment in range(num_segments + 1):
                    idx = ring * (num_segments + 1) + segment
                    if idx < len(vertices):
                        ring_verts.append(vertices[idx])

                if len(ring_verts) > 1:
                    batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": ring_verts})
                    shader.bind()
                    shader.uniform_float("color", color)
                    gpu.state.line_width_set(3.0)
                    batch.draw(shader)

            # Draw vertical meridians
            for segment in range(0, num_segments, 2):  # Every other meridian
                meridian_verts = []
                for ring in range(num_rings + 1):
                    idx = ring * (num_segments + 1) + segment
                    if idx < len(vertices):
                        meridian_verts.append(vertices[idx])

                if len(meridian_verts) > 1:
                    batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": meridian_verts})
                    shader.bind()
                    shader.uniform_float("color", color)
                    gpu.state.line_width_set(3.0)
                    batch.draw(shader)

        gpu.state.line_width_set(1.0)
        gpu.state.blend_set('NONE')


class FilterPanelUI:
    """Renders filter panel UI for global alert view"""

    def __init__(self, global_alert_view):
        self.alert_view = global_alert_view
        self.panel_width = 550
        self.panel_height = 780  # Increased to cover all equipment types + bottom text

        # Track clickable regions for interaction
        self.clickable_regions = []  # List of (x1, y1, x2, y2, callback, label)

    def draw_panel_2d(self, context):
        """
        Render filter panel overlay in 2D
        Called from modal operator's 2D draw handler
        """
        import blf
        import gpu
        from gpu_extras.batch import batch_for_shader

        region = context.region

        # Position panel (top-left corner with margin)
        panel_x = 50
        panel_y = region.height - self.panel_height - 50

        # Clear clickable regions for this frame
        self.clickable_regions = []

        # Draw background panel
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        vertices = [
            (panel_x, panel_y),
            (panel_x + self.panel_width, panel_y),
            (panel_x + self.panel_width, panel_y + self.panel_height),
            (panel_x, panel_y + self.panel_height)
        ]
        indices = [(0, 1, 2), (2, 3, 0)]
        batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
        shader.bind()
        shader.uniform_float("color", (0.1, 0.1, 0.1, 0.90))
        gpu.state.blend_set('ALPHA')
        batch.draw(shader)

        # Draw header
        header_vertices = [
            (panel_x, panel_y + self.panel_height - 60),
            (panel_x + self.panel_width, panel_y + self.panel_height - 60),
            (panel_x + self.panel_width, panel_y + self.panel_height),
            (panel_x, panel_y + self.panel_height)
        ]
        batch = batch_for_shader(shader, 'TRIS', {"pos": header_vertices}, indices=indices)
        shader.uniform_float("color", (0.2, 0.4, 0.6, 0.95))
        batch.draw(shader)

        font_id = 0

        # Title (shortened)
        blf.size(font_id, 24)
        blf.color(font_id, 0.95, 0.95, 0.95, 1.0)
        blf.position(font_id, panel_x + 20, panel_y + self.panel_height - 40, 0)
        blf.draw(font_id, "RIVER ALERT OVERVIEW")

        # Zoom/Frame All button (target icon) - centered in header right area
        import math
        zoom_button_size = 40
        zoom_button_x = panel_x + self.panel_width - zoom_button_size - 15  # 15px margin from right
        zoom_button_y = panel_y + self.panel_height - 50  # Centered vertically in header (60px header, 40px button = 10px top margin)

        # Button background
        zoom_bg_verts = [
            (zoom_button_x, zoom_button_y),
            (zoom_button_x + zoom_button_size, zoom_button_y),
            (zoom_button_x + zoom_button_size, zoom_button_y + zoom_button_size),
            (zoom_button_x, zoom_button_y + zoom_button_size)
        ]
        batch = batch_for_shader(shader, 'TRIS', {"pos": zoom_bg_verts}, indices=indices)
        shader.uniform_float("color", (0.3, 0.5, 0.7, 0.8))
        batch.draw(shader)

        # Button border
        zoom_border_verts = [
            (zoom_button_x, zoom_button_y),
            (zoom_button_x + zoom_button_size, zoom_button_y),
            (zoom_button_x + zoom_button_size, zoom_button_y + zoom_button_size),
            (zoom_button_x, zoom_button_y + zoom_button_size),
            (zoom_button_x, zoom_button_y)
        ]
        batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": zoom_border_verts})
        shader.uniform_float("color", (0.5, 0.7, 0.9, 1.0))
        gpu.state.line_width_set(2.0)
        batch.draw(shader)
        gpu.state.line_width_set(1.0)

        # Target icon (concentric circles with crosshair)
        target_center_x = zoom_button_x + zoom_button_size / 2
        target_center_y = zoom_button_y + zoom_button_size / 2

        # Outer circle
        num_segments = 24
        outer_circle_verts = []
        for i in range(num_segments + 1):
            angle = 2.0 * math.pi * i / num_segments
            cx = target_center_x + 12 * math.cos(angle)
            cy = target_center_y + 12 * math.sin(angle)
            outer_circle_verts.append((cx, cy))

        batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": outer_circle_verts})
        shader.uniform_float("color", (0.95, 0.95, 0.95, 1.0))
        gpu.state.line_width_set(2.0)
        batch.draw(shader)

        # Inner circle
        inner_circle_verts = []
        for i in range(num_segments + 1):
            angle = 2.0 * math.pi * i / num_segments
            cx = target_center_x + 6 * math.cos(angle)
            cy = target_center_y + 6 * math.sin(angle)
            inner_circle_verts.append((cx, cy))

        batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": inner_circle_verts})
        shader.uniform_float("color", (0.95, 0.95, 0.95, 1.0))
        gpu.state.line_width_set(1.5)
        batch.draw(shader)

        # Crosshair
        crosshair_verts = [
            (target_center_x - 14, target_center_y),
            (target_center_x + 14, target_center_y)
        ]
        batch = batch_for_shader(shader, 'LINES', {"pos": crosshair_verts})
        shader.uniform_float("color", (0.95, 0.95, 0.95, 1.0))
        gpu.state.line_width_set(1.5)
        batch.draw(shader)

        crosshair_verts = [
            (target_center_x, target_center_y - 14),
            (target_center_x, target_center_y + 14)
        ]
        batch = batch_for_shader(shader, 'LINES', {"pos": crosshair_verts})
        shader.uniform_float("color", (0.95, 0.95, 0.95, 1.0))
        gpu.state.line_width_set(1.5)
        batch.draw(shader)
        gpu.state.line_width_set(1.0)

        # Register zoom button as clickable
        self.clickable_regions.append({
            'x1': zoom_button_x,
            'y1': zoom_button_y,
            'x2': zoom_button_x + zoom_button_size,
            'y2': zoom_button_y + zoom_button_size,
            'action': 'frame_all_beacons',
            'value': None,
            'label': 'Frame All Beacons'
        })

        # Content area with better spacing
        content_y = panel_y + self.panel_height - 90

        # Alert Level section
        blf.size(font_id, 16)
        blf.color(font_id, 0.95, 0.95, 0.95, 1.0)
        blf.position(font_id, panel_x + 20, content_y, 0)
        blf.draw(font_id, "Alert Level:")
        content_y -= 30

        # Alert mode options (radio buttons)
        alert_modes = [
            ('AUTO', 'AUTO (Max 20 worst)'),
            ('ALL_CRITICAL', 'ALL CRITICAL (REPAIR + FOLLOW SOP + PM)'),
            ('REPAIR_ONLY', 'REPAIR ONLY'),
            ('FOLLOW_SOP_ONLY', 'FOLLOW SOP ONLY'),
            ('PM_ACTION_ONLY', 'PM ACTION ONLY'),
        ]

        blf.size(font_id, 13)
        for mode_key, mode_label in alert_modes:
            selected = (self.alert_view.alert_mode == mode_key)

            # Draw button background
            button_x = panel_x + 30
            button_y = content_y - 3
            button_width = self.panel_width - 60
            button_height = 22

            # Button background color
            if selected:
                bg_color = (0.2, 0.5, 0.8, 0.8)  # Blue highlight for selected
            else:
                bg_color = (0.15, 0.15, 0.15, 0.6)  # Dark gray for unselected

            # Draw button background
            button_verts = [
                (button_x, button_y),
                (button_x + button_width, button_y),
                (button_x + button_width, button_y + button_height),
                (button_x, button_y + button_height)
            ]
            batch = batch_for_shader(shader, 'TRIS', {"pos": button_verts}, indices=indices)
            shader.uniform_float("color", bg_color)
            batch.draw(shader)

            # Draw button border
            border_verts = [
                (button_x, button_y),
                (button_x + button_width, button_y),
                (button_x + button_width, button_y + button_height),
                (button_x, button_y + button_height),
                (button_x, button_y)  # Close the loop
            ]
            batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": border_verts})
            border_color = (0.4, 0.6, 0.9, 1.0) if selected else (0.3, 0.3, 0.3, 0.8)
            shader.uniform_float("color", border_color)
            gpu.state.line_width_set(2.0)
            batch.draw(shader)
            gpu.state.line_width_set(1.0)

            # Draw radio circle
            circle_x = button_x + 10
            circle_y = button_y + button_height / 2
            circle_radius = 5

            # Outer circle
            circle_verts = []
            num_segments = 12
            import math
            for i in range(num_segments + 1):
                angle = 2.0 * math.pi * i / num_segments
                cx = circle_x + circle_radius * math.cos(angle)
                cy = circle_y + circle_radius * math.sin(angle)
                circle_verts.append((cx, cy))

            batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": circle_verts})
            shader.uniform_float("color", (0.8, 0.8, 0.8, 1.0))
            gpu.state.line_width_set(1.5)
            batch.draw(shader)
            gpu.state.line_width_set(1.0)

            # Inner filled circle if selected
            if selected:
                inner_circle_verts = []
                inner_radius = 3
                for i in range(num_segments):
                    angle = 2.0 * math.pi * i / num_segments
                    cx = circle_x + inner_radius * math.cos(angle)
                    cy = circle_y + inner_radius * math.sin(angle)
                    inner_circle_verts.append((cx, cy))

                # Create triangles for filled circle
                inner_indices = []
                for i in range(1, num_segments - 1):
                    inner_indices.append((0, i, i + 1))

                batch = batch_for_shader(shader, 'TRIS', {"pos": inner_circle_verts}, indices=inner_indices)
                shader.uniform_float("color", (0.9, 0.9, 0.9, 1.0))
                batch.draw(shader)

            # Draw text
            text_color = (0.95, 0.95, 0.95, 1.0) if selected else (0.7, 0.7, 0.7, 1.0)
            blf.color(font_id, *text_color)
            text_x = button_x + 25
            text_y = button_y + 5
            blf.position(font_id, text_x, text_y, 0)
            blf.draw(font_id, mode_label)

            # Register clickable region
            self.clickable_regions.append({
                'x1': button_x,
                'y1': button_y,
                'x2': button_x + button_width,
                'y2': button_y + button_height,
                'action': 'set_alert_mode',
                'value': mode_key,
                'label': mode_label
            })

            content_y -= 26

        # Separator
        content_y -= 15
        sep_vertices = [
            (panel_x + 20, content_y),
            (panel_x + self.panel_width - 20, content_y)
        ]
        batch = batch_for_shader(shader, 'LINES', {"pos": sep_vertices})
        shader.uniform_float("color", (0.4, 0.4, 0.4, 0.8))
        gpu.state.line_width_set(2.0)
        batch.draw(shader)
        gpu.state.line_width_set(1.0)
        content_y -= 25

        # River Zones section
        blf.size(font_id, 16)
        blf.color(font_id, 0.95, 0.95, 0.95, 1.0)
        blf.position(font_id, panel_x + 20, content_y, 0)
        blf.draw(font_id, "River Zones:")
        content_y -= 30

        zones = [
            ('ZONE_I_EAST', 'Zone I (EAST - Puchong, 30m width)'),
            ('ZONE_II_MIDDLE', 'Zone II (MIDDLE - Meandering)'),
            ('ZONE_III_WEST', 'Zone III (WEST - Intake, 80m width)'),
        ]

        blf.size(font_id, 13)
        for zone_key, zone_label in zones:
            checked = zone_key in self.alert_view.filter_zones

            # Draw button/checkbox background
            button_x = panel_x + 30
            button_y = content_y - 3
            button_width = self.panel_width - 60
            button_height = 22

            # Button background color
            if checked:
                bg_color = (0.2, 0.6, 0.3, 0.7)  # Green for checked
            else:
                bg_color = (0.15, 0.15, 0.15, 0.6)  # Dark gray for unchecked

            # Draw button background
            button_verts = [
                (button_x, button_y),
                (button_x + button_width, button_y),
                (button_x + button_width, button_y + button_height),
                (button_x, button_y + button_height)
            ]
            batch = batch_for_shader(shader, 'TRIS', {"pos": button_verts}, indices=indices)
            shader.uniform_float("color", bg_color)
            batch.draw(shader)

            # Draw button border
            border_verts = [
                (button_x, button_y),
                (button_x + button_width, button_y),
                (button_x + button_width, button_y + button_height),
                (button_x, button_y + button_height),
                (button_x, button_y)
            ]
            batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": border_verts})
            border_color = (0.3, 0.7, 0.4, 1.0) if checked else (0.3, 0.3, 0.3, 0.8)
            shader.uniform_float("color", border_color)
            gpu.state.line_width_set(2.0)
            batch.draw(shader)
            gpu.state.line_width_set(1.0)

            # Draw checkbox square
            checkbox_x = button_x + 8
            checkbox_y = button_y + 6
            checkbox_size = 10

            # Checkbox border
            checkbox_verts = [
                (checkbox_x, checkbox_y),
                (checkbox_x + checkbox_size, checkbox_y),
                (checkbox_x + checkbox_size, checkbox_y + checkbox_size),
                (checkbox_x, checkbox_y + checkbox_size),
                (checkbox_x, checkbox_y)
            ]
            batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": checkbox_verts})
            shader.uniform_float("color", (0.8, 0.8, 0.8, 1.0))
            gpu.state.line_width_set(1.5)
            batch.draw(shader)
            gpu.state.line_width_set(1.0)

            # Checkmark if checked
            if checked:
                check_verts = [
                    (checkbox_x + 2, checkbox_y + 5),
                    (checkbox_x + 4, checkbox_y + 2),
                    (checkbox_x + 8, checkbox_y + 8)
                ]
                batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": check_verts})
                shader.uniform_float("color", (0.2, 0.9, 0.2, 1.0))
                gpu.state.line_width_set(2.5)
                batch.draw(shader)
                gpu.state.line_width_set(1.0)

            # Draw text
            text_color = (0.95, 0.95, 0.95, 1.0) if checked else (0.7, 0.7, 0.7, 1.0)
            blf.color(font_id, *text_color)
            text_x = button_x + 25
            text_y = button_y + 5
            blf.position(font_id, text_x, text_y, 0)
            blf.draw(font_id, zone_label)

            # Register clickable region
            self.clickable_regions.append({
                'x1': button_x,
                'y1': button_y,
                'x2': button_x + button_width,
                'y2': button_y + button_height,
                'action': 'toggle_zone',
                'value': zone_key,
                'label': zone_label
            })

            content_y -= 26

        # Equipment Type section
        content_y -= 15
        blf.size(font_id, 16)
        blf.color(font_id, 0.95, 0.95, 0.95, 1.0)
        blf.position(font_id, panel_x + 20, content_y, 0)
        blf.draw(font_id, "Equipment Type:")
        content_y -= 30

        # Show first few equipment types + "All Types" option
        all_types_selected = len(self.alert_view.filter_equipment_types) == len(EQUIPMENT_TYPES)
        all_types_label = "All Types"

        # Draw button/checkbox background
        button_x = panel_x + 30
        button_y = content_y - 3
        button_width = self.panel_width - 60
        button_height = 22

        # Button background color
        if all_types_selected:
            bg_color = (0.2, 0.6, 0.3, 0.7)  # Green for checked
        else:
            bg_color = (0.15, 0.15, 0.15, 0.6)  # Dark gray for unchecked

        # Draw button background
        button_verts = [
            (button_x, button_y),
            (button_x + button_width, button_y),
            (button_x + button_width, button_y + button_height),
            (button_x, button_y + button_height)
        ]
        batch = batch_for_shader(shader, 'TRIS', {"pos": button_verts}, indices=indices)
        shader.uniform_float("color", bg_color)
        batch.draw(shader)

        # Draw button border
        border_verts = [
            (button_x, button_y),
            (button_x + button_width, button_y),
            (button_x + button_width, button_y + button_height),
            (button_x, button_y + button_height),
            (button_x, button_y)
        ]
        batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": border_verts})
        border_color = (0.3, 0.7, 0.4, 1.0) if all_types_selected else (0.3, 0.3, 0.3, 0.8)
        shader.uniform_float("color", border_color)
        gpu.state.line_width_set(2.0)
        batch.draw(shader)
        gpu.state.line_width_set(1.0)

        # Draw checkbox square
        checkbox_x = button_x + 8
        checkbox_y = button_y + 6
        checkbox_size = 10

        # Checkbox border
        checkbox_verts = [
            (checkbox_x, checkbox_y),
            (checkbox_x + checkbox_size, checkbox_y),
            (checkbox_x + checkbox_size, checkbox_y + checkbox_size),
            (checkbox_x, checkbox_y + checkbox_size),
            (checkbox_x, checkbox_y)
        ]
        batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": checkbox_verts})
        shader.uniform_float("color", (0.8, 0.8, 0.8, 1.0))
        gpu.state.line_width_set(1.5)
        batch.draw(shader)
        gpu.state.line_width_set(1.0)

        # Checkmark if checked
        if all_types_selected:
            check_verts = [
                (checkbox_x + 2, checkbox_y + 5),
                (checkbox_x + 4, checkbox_y + 2),
                (checkbox_x + 8, checkbox_y + 8)
            ]
            batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": check_verts})
            shader.uniform_float("color", (0.2, 0.9, 0.2, 1.0))
            gpu.state.line_width_set(2.5)
            batch.draw(shader)
            gpu.state.line_width_set(1.0)

        # Draw text
        blf.size(font_id, 13)
        text_color = (0.95, 0.95, 0.95, 1.0) if all_types_selected else (0.7, 0.7, 0.7, 1.0)
        blf.color(font_id, *text_color)
        text_x = button_x + 25
        text_y = button_y + 5
        blf.position(font_id, text_x, text_y, 0)
        blf.draw(font_id, all_types_label)

        # Register clickable region
        self.clickable_regions.append({
            'x1': button_x,
            'y1': button_y,
            'x2': button_x + button_width,
            'y2': button_y + button_height,
            'action': 'toggle_all_types',
            'value': None,
            'label': all_types_label
        })

        content_y -= 18  # Increased spacing to separate "All Types" from individual types

        # Individual equipment type checkboxes
        blf.size(font_id, 13)
        for eq_type, eq_info in EQUIPMENT_TYPES.items():
            checked = eq_type in self.alert_view.filter_equipment_types
            eq_label = eq_info['name']

            # Draw button/checkbox background
            button_x = panel_x + 50  # Indent more to show it's under "All Types"
            button_y = content_y - 3
            button_width = self.panel_width - 80
            button_height = 20

            # Button background color
            if checked:
                bg_color = (0.2, 0.6, 0.3, 0.6)  # Green for checked (slightly dimmer)
            else:
                bg_color = (0.15, 0.15, 0.15, 0.5)  # Dark gray for unchecked

            # Draw button background
            button_verts = [
                (button_x, button_y),
                (button_x + button_width, button_y),
                (button_x + button_width, button_y + button_height),
                (button_x, button_y + button_height)
            ]
            batch = batch_for_shader(shader, 'TRIS', {"pos": button_verts}, indices=indices)
            shader.uniform_float("color", bg_color)
            batch.draw(shader)

            # Draw button border
            border_verts = [
                (button_x, button_y),
                (button_x + button_width, button_y),
                (button_x + button_width, button_y + button_height),
                (button_x, button_y + button_height),
                (button_x, button_y)
            ]
            batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": border_verts})
            border_color = (0.3, 0.7, 0.4, 0.8) if checked else (0.25, 0.25, 0.25, 0.6)
            shader.uniform_float("color", border_color)
            gpu.state.line_width_set(1.5)
            batch.draw(shader)
            gpu.state.line_width_set(1.0)

            # Draw checkbox square (smaller for individual items)
            checkbox_x = button_x + 6
            checkbox_y = button_y + 5
            checkbox_size = 8

            # Checkbox border
            checkbox_verts = [
                (checkbox_x, checkbox_y),
                (checkbox_x + checkbox_size, checkbox_y),
                (checkbox_x + checkbox_size, checkbox_y + checkbox_size),
                (checkbox_x, checkbox_y + checkbox_size),
                (checkbox_x, checkbox_y)
            ]
            batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": checkbox_verts})
            shader.uniform_float("color", (0.7, 0.7, 0.7, 1.0))
            gpu.state.line_width_set(1.0)
            batch.draw(shader)

            # Checkmark if checked
            if checked:
                check_verts = [
                    (checkbox_x + 1, checkbox_y + 4),
                    (checkbox_x + 3, checkbox_y + 1),
                    (checkbox_x + 7, checkbox_y + 7)
                ]
                batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": check_verts})
                shader.uniform_float("color", (0.2, 0.9, 0.2, 1.0))
                gpu.state.line_width_set(2.0)
                batch.draw(shader)
                gpu.state.line_width_set(1.0)

            # Draw text (smaller font)
            blf.size(font_id, 11)
            text_color = (0.9, 0.9, 0.9, 1.0) if checked else (0.6, 0.6, 0.6, 1.0)
            blf.color(font_id, *text_color)
            text_x = button_x + 20
            text_y = button_y + 4
            blf.position(font_id, text_x, text_y, 0)
            blf.draw(font_id, eq_label)

            # Register clickable region
            self.clickable_regions.append({
                'x1': button_x,
                'y1': button_y,
                'x2': button_x + button_width,
                'y2': button_y + button_height,
                'action': 'toggle_equipment_type',
                'value': eq_type,
                'label': eq_label
            })

            content_y -= 22

        # Separator
        content_y -= 10
        sep_vertices = [
            (panel_x + 20, content_y),
            (panel_x + self.panel_width - 20, content_y)
        ]
        batch = batch_for_shader(shader, 'LINES', {"pos": sep_vertices})
        shader.uniform_float("color", (0.4, 0.4, 0.4, 0.8))
        gpu.state.line_width_set(2.0)
        batch.draw(shader)
        gpu.state.line_width_set(1.0)
        content_y -= 25

        # Summary section
        markers = self.alert_view.get_filtered_markers()

        # Count by zone
        zone_counts = {'ZONE_I_EAST': 0, 'ZONE_II_MIDDLE': 0, 'ZONE_III_WEST': 0}
        status_counts = {'REPAIR': 0, 'FOLLOW_SOP': 0, 'PM_ACTION': 0, 'INSPECTION': 0}

        for marker in markers:
            if marker['river_section'] in zone_counts:
                zone_counts[marker['river_section']] += 1
            if marker['status'] in status_counts:
                status_counts[marker['status']] += 1

        blf.size(font_id, 16)
        blf.color(font_id, 0.9, 0.7, 0.2, 1.0)  # Yellow for alert
        blf.position(font_id, panel_x + 20, content_y, 0)
        blf.draw(font_id, f"⚠️ Showing: {len(markers)} beacons")
        content_y -= 30

        blf.size(font_id, 13)
        blf.color(font_id, 0.85, 0.85, 0.85, 1.0)
        blf.position(font_id, panel_x + 35, content_y, 0)
        blf.draw(font_id, f"Zone I: {zone_counts['ZONE_I_EAST']}   Zone II: {zone_counts['ZONE_II_MIDDLE']}   Zone III: {zone_counts['ZONE_III_WEST']}")
        content_y -= 25

        blf.position(font_id, panel_x + 35, content_y, 0)
        blf.draw(font_id, f"🔴 {status_counts['REPAIR']} REPAIR  🟠 {status_counts['FOLLOW_SOP']} FOLLOW SOP  🟡 {status_counts['PM_ACTION']} PM")
        content_y -= 30

        # Instructions
        blf.size(font_id, 12)
        blf.color(font_id, 0.6, 0.6, 0.6, 0.9)
        blf.position(font_id, panel_x + 20, panel_y + 35, 0)
        blf.draw(font_id, "Press ESC to exit")
        blf.position(font_id, panel_x + 20, panel_y + 15, 0)
        blf.draw(font_id, "Click marker → Select → Dashboard to view sensors")

        gpu.state.blend_set('NONE')

    def handle_click(self, mouse_x, mouse_y):
        """
        Handle mouse click on filter panel
        Returns True if click was handled, False otherwise
        """
        for region in self.clickable_regions:
            if (region['x1'] <= mouse_x <= region['x2'] and
                region['y1'] <= mouse_y <= region['y2']):

                action = region['action']
                value = region['value']

                LOGGER.log(f"✓ Clicked filter: {action} = {value} ({region['label']})")

                if action == 'set_alert_mode':
                    self.alert_view.alert_mode = value
                    self.alert_view._cache_valid = False  # Invalidate cache
                    return True

                elif action == 'toggle_zone':
                    if value in self.alert_view.filter_zones:
                        self.alert_view.filter_zones.remove(value)
                    else:
                        self.alert_view.filter_zones.append(value)
                    self.alert_view._cache_valid = False  # Invalidate cache
                    return True

                elif action == 'toggle_all_types':
                    # Toggle between all types and no types
                    if len(self.alert_view.filter_equipment_types) == len(EQUIPMENT_TYPES):
                        self.alert_view.filter_equipment_types = []
                    else:
                        self.alert_view.filter_equipment_types = list(EQUIPMENT_TYPES.keys())
                    self.alert_view._cache_valid = False  # Invalidate cache
                    return True

                elif action == 'toggle_equipment_type':
                    # Toggle individual equipment type
                    if value in self.alert_view.filter_equipment_types:
                        self.alert_view.filter_equipment_types.remove(value)
                    else:
                        self.alert_view.filter_equipment_types.append(value)
                    self.alert_view._cache_valid = False  # Invalidate cache
                    return True

                elif action == 'frame_all_beacons':
                    # Frame all beacons in viewport
                    self.frame_all_beacons()
                    return True

        return False  # Click not on any filter

    def frame_all_beacons(self):
        """Frame camera to show all alert beacons"""
        import bpy

        # Get all beacon objects
        beacon_objects = []
        for obj in bpy.data.objects:
            if obj.get("beacon_type") == "alert_beacon":
                beacon_objects.append(obj)

        if not beacon_objects:
            LOGGER.log("No beacons to frame")
            return

        # Calculate bounding box of all beacons
        min_x = min_y = min_z = float('inf')
        max_x = max_y = max_z = float('-inf')

        for obj in beacon_objects:
            x, y, z = obj.location
            # Account for beacon radius (200m)
            radius = 200.0
            min_x = min(min_x, x - radius)
            max_x = max(max_x, x + radius)
            min_y = min(min_y, y - radius)
            max_y = max(max_y, y + radius)
            min_z = min(min_z, z - radius)
            max_z = max(max_z, z + radius)

        # Calculate center and size
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2
        center_z = (min_z + max_z) / 2

        # Get the active 3D view
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        # Set view to look from above (top-down)
                        region_3d = space.region_3d

                        # Calculate distance to fit all beacons
                        span_x = max_x - min_x
                        span_y = max_y - min_y
                        max_span = max(span_x, span_y)

                        # Distance calculation (empirical formula for perspective view)
                        distance = max_span * 1.5

                        # Set view location (center of all beacons)
                        region_3d.view_location = (center_x, center_y, center_z)

                        # Set view distance
                        region_3d.view_distance = distance

                        # Set view to top-down (quaternion for looking down Z axis)
                        import mathutils
                        region_3d.view_rotation = mathutils.Quaternion((1.0, 0.0, 0.0, 0.0))

                        area.tag_redraw()

                        LOGGER.log(f"✓ Framed {len(beacon_objects)} beacons in viewport")
                        return

        LOGGER.log("No 3D viewport found")


class MarkerSensorView:
    """Manages 7-day sensor bar chart rendering for a single marker"""

    def __init__(self, marker_id, equipment_name, db_path):
        self.marker_id = marker_id
        self.equipment_name = equipment_name
        self.db_path = db_path
        self.sensor_data = []
        self.animation_time = 0.0
        self.cycle_duration = 6.0  # 6 seconds for Day 1-6
        self.linger_duration = 2.0  # 2 second linger on Day 7

    def load_sensor_data(self):
        """Load 7-day sensor readings from database"""
        import sqlite3

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Get sensors
            cursor.execute("""
                SELECT sensor_id, sensor_name, sensor_type, unit, threshold_max
                FROM sensors
                WHERE equipment_marker_id = ?
                ORDER BY sensor_type
            """, (self.marker_id,))

            sensors = cursor.fetchall()

            if not sensors:
                conn.close()
                return False

            LOGGER.log(f"Found {len(sensors)} sensors for marker {self.marker_id}")

            self.sensor_data = []

            for sensor_id, sensor_name, sensor_type, unit, threshold_max in sensors:
                # Get 7-day readings
                cursor.execute("""
                    SELECT timestamp, value
                    FROM sensor_readings
                    WHERE sensor_id = ?
                    ORDER BY timestamp ASC
                """, (sensor_id,))

                readings = cursor.fetchall()

                # Extract Day 1-7 values
                day_values = []
                for day in range(1, 8):
                    day_label = f'Day {day}'
                    for timestamp, value in readings:
                        if timestamp.startswith(day_label):
                            day_values.append(float(value))
                            break

                if len(day_values) == 7:
                    self.sensor_data.append({
                        'name': sensor_name,
                        'type': sensor_type,
                        'threshold': threshold_max if threshold_max else max(day_values) * 0.9,
                        'values': day_values,
                        'color': SENSOR_TYPE_COLORS.get(sensor_type, (0.5, 0.5, 0.5))
                    })
                    LOGGER.log(f"  Loaded: {sensor_name} ({sensor_type})")

            conn.close()

            if not self.sensor_data:
                return False

            LOGGER.log(f"✓ Loaded {len(self.sensor_data)} sensors with data")
            return True

        except Exception as e:
            LOGGER.log(f"ERROR loading sensor data: {e}", error=True)
            return False

    def update_animation(self, delta_time):
        """Update animation timer"""
        self.animation_time += delta_time
        total_cycle = self.cycle_duration + self.linger_duration
        if self.animation_time > total_cycle:
            self.animation_time -= total_cycle

    def draw_sensor_chart_2d(self, context):
        """
        Render 7-day sensor bar chart (existing dashboard visualization)
        Called from modal operator's 2D draw handler

        NOTE: This is the existing chart rendering code, kept intact for compatibility
        """
        # This method will contain the existing draw_callback_px code
        # For now, we'll keep it as a placeholder and integrate the existing code
        pass


class BIM_OT_equipment_view_sensor_dashboard(Operator):
    """View sensor dashboard - dual mode: Global Alert View or Marker Sensor View"""
    bl_idname = "bim.equipment_view_sensor_dashboard"
    bl_label = "View Sensor Dashboard"
    bl_options = {'REGISTER'}

    # Class-level singleton instance tracker
    _active_instance = None

    _is_running = False  # Flag to prevent stale draw calls
    _draw_handler_2d = None
    _draw_handler_3d = None
    _timer = None

    # Mode tracking
    _mode = None  # 'GLOBAL_ALERTS' or 'MARKER_SENSORS'

    # Marker sensor view (old behavior)
    _sensor_data = []
    _equipment_name = ""
    _marker_id = 0
    _animation_time = 0.0
    _cycle_duration = 6.0  # 6 seconds for Day 1-6 (1 sec per day, smoother)
    _linger_duration = 2.0  # 2 second linger on Day 7
    _marker_sensor_view = None

    # Global alert view (new behavior)
    _global_alert_view = None
    _filter_panel_ui = None

    def invoke(self, context, event):
        from pathlib import Path

        # Close any existing dashboard instance first
        if BIM_OT_equipment_view_sensor_dashboard._active_instance is not None:
            old_instance = BIM_OT_equipment_view_sensor_dashboard._active_instance
            LOGGER.log("Closing previous dashboard instance...")
            old_instance.cleanup(context)
            BIM_OT_equipment_view_sensor_dashboard._active_instance = None

        LOGGER.section("SENSOR DASHBOARD OPENING (GPU OVERLAY)")

        # Database path
        db_path = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db")
        if not db_path.exists():
            LOGGER.log(f"ERROR: Database not found: {db_path}", error=True)
            self.report({'ERROR'}, "Database not found")
            return {'CANCELLED'}

        # Determine mode based on selection
        is_equipment = False
        if context.active_object:
            # Check if object name matches equipment pattern
            obj = context.active_object
            equipment_patterns = [eq_type.upper() + '_' for eq_type in EQUIPMENT_TYPES.keys()]
            is_equipment = any(obj.name.upper().startswith(p) for p in equipment_patterns)

        if not context.active_object or not is_equipment:
            # GLOBAL MODE - No marker selected or non-equipment selected
            self._mode = 'GLOBAL_ALERTS'
            LOGGER.log("Opening dashboard in GLOBAL ALERT mode (no equipment selected)")

            # Initialize global alert view
            self._global_alert_view = GlobalAlertView(str(db_path))
            self._filter_panel_ui = FilterPanelUI(self._global_alert_view)

            # Create beacon objects in the outliner
            self._global_alert_view.create_beacon_objects(context)

            # Set up GPU draw handlers (2D for panel, 3D for beacons)
            import bpy
            self._draw_handler_2d = bpy.types.SpaceView3D.draw_handler_add(
                self.draw_callback_global_2d, (context,), 'WINDOW', 'POST_PIXEL'
            )
            self._draw_handler_3d = bpy.types.SpaceView3D.draw_handler_add(
                self.draw_callback_global_3d, (context,), 'WINDOW', 'POST_VIEW'
            )

            # Set up timer for refreshing
            self._timer = context.window_manager.event_timer_add(0.1, window=context.window)

            context.window_manager.modal_handler_add(self)

            # Register this instance as the active one and mark as running
            BIM_OT_equipment_view_sensor_dashboard._active_instance = self
            self._is_running = True

            LOGGER.log("✓ Global Alert View enabled")
            return {'RUNNING_MODAL'}

        else:
            # MARKER MODE - Equipment marker selected
            self._mode = 'MARKER_SENSORS'
            obj = context.active_object

            # Try to find marker in PLACED_EQUIPMENT first
            global PLACED_EQUIPMENT
            found_marker = None
            for eq_type, items in PLACED_EQUIPMENT.items():
                for item in items:
                    if item['object_name'] == obj.name:
                        found_marker = item
                        break
                if found_marker:
                    break

            if not found_marker:
                # Fallback: extract marker ID from object name (e.g., "BOOM_TRAP_12" -> 12)
                LOGGER.log("WARNING: Object not in PLACED_EQUIPMENT, extracting ID from name")
                try:
                    # Split by underscore and get last part as number
                    name_parts = obj.name.split('_')
                    marker_id = int(name_parts[-1])
                    found_marker = {'marker_id': marker_id, 'number': marker_id}
                    LOGGER.log(f"Extracted marker ID: {marker_id} from name: {obj.name}")
                except (ValueError, IndexError):
                    LOGGER.log("ERROR: Could not extract marker ID from object name", error=True)
                    self.report({'WARNING'}, "Invalid equipment name format")
                    return {'CANCELLED'}

            # Use actual database marker_id (not sequential count)
            self._marker_id = found_marker.get('marker_id', found_marker['number'])
            self._equipment_name = obj.name
            LOGGER.log(f"Opening dashboard in MARKER SENSOR mode")
            LOGGER.log(f"Equipment: {obj.name}, Database Marker ID: {self._marker_id}")

            try:
                # Load sensor data using existing logic (keep compatibility)
                import sqlite3
                LOGGER.log("Loading sensor data from database...")
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                # Get sensors
                cursor.execute("""
                    SELECT sensor_id, sensor_name, sensor_type, unit, threshold_max
                    FROM sensors
                    WHERE equipment_marker_id = ?
                    ORDER BY sensor_type
                """, (self._marker_id,))

                sensors = cursor.fetchall()

                if not sensors:
                    LOGGER.log(f"WARNING: No sensors found for equipment {self._marker_id}", error=True)
                    self.report({'WARNING'}, "No sensors for this equipment")
                    conn.close()
                    return {'CANCELLED'}

                LOGGER.log(f"Found {len(sensors)} sensors")

                self._sensor_data = []

                # Use centralized color mapping for sensors
                for sensor_id, sensor_name, sensor_type, unit, threshold_max in sensors:
                    # Get 7-day readings
                    cursor.execute("""
                        SELECT day_label, value
                        FROM sensor_readings
                        WHERE sensor_id = ?
                        ORDER BY timestamp ASC
                    """, (sensor_id,))

                    readings = cursor.fetchall()

                    # Extract Day 1-7 values
                    day_values = []
                    for day in range(1, 8):
                        day_label = f'Day {day}'
                        for reading_day_label, value in readings:
                            if reading_day_label == day_label:
                                day_values.append(float(value))
                                break

                    if len(day_values) == 7:
                        self._sensor_data.append({
                            'name': sensor_name,
                            'type': sensor_type,
                            'threshold': threshold_max if threshold_max else max(day_values) * 0.9,
                            'values': day_values,
                            'color': SENSOR_TYPE_COLORS.get(sensor_type, (0.5, 0.5, 0.5))
                        })
                        LOGGER.log(f"  Loaded: {sensor_name} ({sensor_type})")

                conn.close()

                if not self._sensor_data:
                    LOGGER.log("WARNING: No sensor data available", error=True)
                    self.report({'WARNING'}, "No sensor data available")
                    return {'CANCELLED'}

                LOGGER.log(f"✓ Loaded {len(self._sensor_data)} sensors with data")

                # Set up GPU draw handler (existing 2D chart)
                import bpy
                args = (self, context)
                self._draw_handler_2d = bpy.types.SpaceView3D.draw_handler_add(
                    self.draw_callback_px, args, 'WINDOW', 'POST_PIXEL'
                )

                # Set up timer for animation
                self._timer = context.window_manager.event_timer_add(0.033, window=context.window)  # ~30fps
                self._animation_time = 0.0

                context.window_manager.modal_handler_add(self)

                # Register this instance as the active one and mark as running
                BIM_OT_equipment_view_sensor_dashboard._active_instance = self
                self._is_running = True

                LOGGER.log("✓ GPU overlay enabled, animation started")
                return {'RUNNING_MODAL'}

            except Exception as e:
                LOGGER.log(f"ERROR loading sensor data: {e}", error=True)
                import traceback
                traceback.print_exc()
                self.report({'ERROR'}, f"Failed: {str(e)}")
                return {'CANCELLED'}

    def modal(self, context, event):
        if event.type in {'ESC'}:
            self._is_running = False  # Stop draw callbacks
            self.cleanup(context)
            # Clear the active instance tracker
            if BIM_OT_equipment_view_sensor_dashboard._active_instance == self:
                BIM_OT_equipment_view_sensor_dashboard._active_instance = None
            LOGGER.log("✓ Sensor dashboard closed (ESC)")
            return {'CANCELLED'}

        # Handle left mouse clicks in GLOBAL_ALERTS mode
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if self._mode == 'GLOBAL_ALERTS' and self._filter_panel_ui:
                mouse_x = event.mouse_region_x
                mouse_y = event.mouse_region_y

                # Check if click is on filter panel
                if self._filter_panel_ui.handle_click(mouse_x, mouse_y):
                    # Refresh beacon objects when filters change
                    self._global_alert_view.create_beacon_objects(context)
                    context.area.tag_redraw()
                    return {'RUNNING_MODAL'}

        if event.type == 'TIMER':
            if self._mode == 'MARKER_SENSORS':
                # Update animation time for marker sensor view
                self._animation_time += 0.033
                total_cycle = self._cycle_duration + self._linger_duration
                if self._animation_time > total_cycle:
                    self._animation_time -= total_cycle

            # Redraw viewport
            context.area.tag_redraw()

        return {'PASS_THROUGH'}

    def cleanup(self, context):
        import bpy

        # Mark as not running first to prevent draw callbacks
        self._is_running = False

        # Clean up beacon objects from outliner
        if self._mode == 'GLOBAL_ALERTS':
            beacon_collection_name = "River_Alert_Beacons"

            # Remove all beacon objects
            objects_to_remove = []
            for obj in bpy.data.objects:
                if obj.get("beacon_type") == "alert_beacon":
                    objects_to_remove.append(obj)

            for obj in objects_to_remove:
                bpy.data.objects.remove(obj, do_unlink=True)

            # Remove beacon collection
            if beacon_collection_name in bpy.data.collections:
                old_collection = bpy.data.collections[beacon_collection_name]

                # Unlink from all scenes
                for scene in bpy.data.scenes:
                    if old_collection.name in scene.collection.children:
                        scene.collection.children.unlink(old_collection)

                # Remove the collection
                bpy.data.collections.remove(old_collection)

            LOGGER.log("✓ Cleaned up beacon objects from outliner")

        if self._timer:
            try:
                context.window_manager.event_timer_remove(self._timer)
            except:
                pass
            self._timer = None

        if self._draw_handler_2d:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(self._draw_handler_2d, 'WINDOW')
            except:
                pass
            self._draw_handler_2d = None

        if self._draw_handler_3d:
            try:
                bpy.types.SpaceView3D.draw_handler_remove(self._draw_handler_3d, 'WINDOW')
            except:
                pass
            self._draw_handler_3d = None

        # Force redraw to clear artifacts
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

    # =============================================================================
    # DRAW CALLBACKS - GLOBAL ALERT VIEW
    # =============================================================================

    def draw_callback_global_2d(self, context):
        """Draw filter panel UI for global alert view"""
        try:
            if not self._is_running or self._mode != 'GLOBAL_ALERTS':
                return
            if self._filter_panel_ui:
                self._filter_panel_ui.draw_panel_2d(context)
        except (ReferenceError, AttributeError):
            return

    def draw_callback_global_3d(self, context):
        """Draw 3D beacons for global alert view"""
        try:
            if not self._is_running or self._mode != 'GLOBAL_ALERTS':
                return
            if self._global_alert_view:
                self._global_alert_view.draw_beacons_3d(context)
        except (ReferenceError, AttributeError):
            return

    # =============================================================================
    # DRAW CALLBACKS - MARKER SENSOR VIEW (Existing Code)
    # =============================================================================

    @staticmethod
    def draw_callback_px(operator_self, context):
        import blf
        import gpu
        from gpu_extras.batch import batch_for_shader

        # Safety check: exit if operator is no longer running
        try:
            if not operator_self._is_running:
                return
        except (ReferenceError, AttributeError):
            # Operator has been removed, exit silently
            return

        # Calculate current day (0-6 for Day 1-7) with smooth interpolation
        total_cycle = operator_self._cycle_duration + operator_self._linger_duration
        if operator_self._animation_time < operator_self._cycle_duration:
            # Days 1-6: smooth progression with interpolation
            progress = operator_self._animation_time / operator_self._cycle_duration
            current_day_float = progress * 6.0
            current_day = int(current_day_float)
            # Interpolation factor for smooth morphing (0.0 to 1.0 within each day)
            interp_factor = current_day_float - current_day
        else:
            # Day 7: linger (no interpolation)
            current_day = 6
            interp_factor = 0.0

        # Chart dimensions - DYNAMIC width based on content
        chart_height = 400
        bar_width = 45
        bar_spacing = 15
        margin_left = 50
        margin_bottom = 100

        # Calculate dynamic width based on number of sensors + STATUS box
        num_sensors = len(operator_self._sensor_data)
        total_bar_width = num_sensors * (bar_width + bar_spacing)

        # STATUS box width: compact width with double-line layout for icons
        # Width = label(140px) + icons per line (4 icons × 22px) + padding(40px)
        status_label_width = 140  # "B. INSPECTION" text width
        icons_per_line = 4  # Icons wrap to second line after 4
        status_icon_width = icons_per_line * 22  # 4 icons per line
        status_padding = 40  # Left/right padding
        status_box_width = status_label_width + status_icon_width + status_padding
        status_gap = 30

        # Chart width = bars + gap + STATUS box + margins
        chart_width = total_bar_width + status_gap + status_box_width + 100  # 100px extra margin

        # Position in viewport (bottom-center)
        region = context.region
        chart_x = (region.width - chart_width) // 2
        chart_y = margin_bottom

        # Draw background panel (main body - dark)
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        vertices = [
            (chart_x - 20, chart_y - 20),
            (chart_x + chart_width + 20, chart_y - 20),
            (chart_x + chart_width + 20, chart_y + chart_height + 10),
            (chart_x - 20, chart_y + chart_height + 10)
        ]
        indices = [(0, 1, 2), (2, 3, 0)]
        batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=indices)
        shader.bind()
        shader.uniform_float("color", (0.1, 0.1, 0.1, 0.85))
        gpu.state.blend_set('ALPHA')
        batch.draw(shader)

        # Draw header panel (color-coded by equipment type)
        # Determine equipment type color from EQUIPMENT_TYPES
        equipment_name = operator_self._equipment_name
        header_color = (0.3, 0.3, 0.3, 0.85)  # Gray fallback

        for eq_type, eq_info in EQUIPMENT_TYPES.items():
            pattern = eq_type.upper().replace('_', '_')
            if equipment_name.upper().startswith(pattern):
                header_color = (*eq_info['color'], 0.85)
                break

        header_vertices = [
            (chart_x - 20, chart_y + chart_height + 10),
            (chart_x + chart_width + 20, chart_y + chart_height + 10),
            (chart_x + chart_width + 20, chart_y + chart_height + 80),
            (chart_x - 20, chart_y + chart_height + 80)
        ]
        batch = batch_for_shader(shader, 'TRIS', {"pos": header_vertices}, indices=indices)
        shader.uniform_float("color", header_color)
        batch.draw(shader)

        # Calculate header color brightness for text contrast
        header_r, header_g, header_b = header_color[:3]
        header_brightness = (header_r * 0.299 + header_g * 0.587 + header_b * 0.114)

        # Use off-white for dark headers, off-black for light headers
        if header_brightness < 0.5:
            header_text_color = (0.95, 0.95, 0.95, 1.0)  # Off-white
            subtitle_color = (0.85, 0.85, 0.85, 1.0)  # Slightly darker off-white
        else:
            header_text_color = (0.15, 0.15, 0.15, 1.0)  # Off-black
            subtitle_color = (0.25, 0.25, 0.25, 1.0)  # Slightly lighter off-black

        # Draw title and infographic - BOLD and larger than STATUS (32pt vs 28pt)
        font_id = 0
        blf.size(font_id, 32)  # Larger than STATUS (28pt)
        blf.enable(font_id, blf.SHADOW)
        blf.shadow(font_id, 5, 0.0, 0.0, 0.0, 0.8)  # Shadow for emphasis
        blf.color(font_id, *header_text_color)
        blf.position(font_id, chart_x, chart_y + chart_height + 40, 0)
        day_text = "TODAY" if current_day == 6 else f"Day {current_day + 1}/7"
        blf.draw(font_id, f"📊 {operator_self._equipment_name} - {day_text}")
        blf.disable(font_id, blf.SHADOW)

        # Infographic subtitle with contrast-based color
        blf.size(font_id, 12)
        blf.color(font_id, *subtitle_color)
        blf.position(font_id, chart_x, chart_y + chart_height + 20, 0)
        blf.draw(font_id, "7-Day Sensor Trend → Yellow line = Threshold limit")

        # Draw threshold line (full width - no legend on right anymore)
        threshold_y = chart_y + int(chart_height * 0.77)  # Threshold at ~77% height

        vertices = [
            (chart_x, threshold_y),
            (chart_x + chart_width, threshold_y)
        ]
        batch = batch_for_shader(shader, 'LINES', {"pos": vertices})
        shader.uniform_float("color", (1.0, 0.8, 0.0, 0.6))
        batch.draw(shader)

        # Draw threshold label - ABOVE the line, inside panel
        blf.size(font_id, 14)
        blf.color(font_id, 1.0, 0.8, 0.0, 0.8)
        blf.position(font_id, chart_x + 5, threshold_y + 5, 0)  # Above line (threshold_y + 5)
        blf.draw(font_id, "MAX")

        # Draw sensor bars (legend integrated into bars)
        num_sensors = len(operator_self._sensor_data)
        total_bar_width = num_sensors * (bar_width + bar_spacing)

        # Position content (bars + gap + STATUS) slightly right of center
        # Total content width = bars + gap + STATUS box
        content_width = total_bar_width + status_gap + status_box_width
        # Add 50px offset to shift right from perfect center
        content_start_x = chart_x + (chart_width - content_width) // 2 + 50

        # Bars start at the beginning of positioned content
        start_x = content_start_x

        # Track sensor status for STATUS BOX
        sensors_inspection = []  # Sensors that went above threshold (yellow line)
        sensors_pm_action = []   # Sensors in WARNING zone (orange)
        sensors_follow_sop = []  # Sensors in CRITICAL zone (red)

        for i, sensor in enumerate(operator_self._sensor_data):
            # Smooth interpolation between current day and next day
            current_value = sensor['values'][current_day]
            if current_day < 6 and interp_factor > 0:
                next_value = sensor['values'][current_day + 1]
                value = current_value + (next_value - current_value) * interp_factor
            else:
                value = current_value

            threshold = sensor['threshold']
            base_color = sensor['color']

            # Normalized height (safety check for zero threshold)
            if threshold <= 0:
                threshold = max(sensor['values']) if sensor['values'] else 1.0

            max_val = threshold * 1.3
            if max_val == 0:
                max_val = 1.0  # Fallback to prevent division by zero

            norm_height = min(value / max_val, 1.0)
            bar_pixel_height = int(norm_height * chart_height)

            # Threshold pixel position
            threshold_height = int((threshold / max_val) * chart_height)

            # Bar position
            bar_x = start_x + i * (bar_width + bar_spacing)
            bar_y = chart_y

            # Draw bar (split colors based on threshold)
            if bar_pixel_height > 0:
                # Bottom part (below threshold or entire bar if below)
                bottom_height = min(bar_pixel_height, threshold_height)
                if bottom_height > 0:
                    vertices = [
                        (bar_x, bar_y),
                        (bar_x + bar_width, bar_y),
                        (bar_x + bar_width, bar_y + bottom_height),
                        (bar_x, bar_y + bottom_height)
                    ]
                    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=[(0, 1, 2), (2, 3, 0)])
                    shader.uniform_float("color", (*base_color, 1.0))
                    batch.draw(shader)

                # Top part (above threshold)
                if bar_pixel_height > threshold_height:
                    top_height = bar_pixel_height - threshold_height
                    # Orange: 100-110%, Red: >110%
                    if value <= threshold * 1.10:
                        top_color = (1.0, 0.6, 0.0, 1.0)  # Orange - WARNING
                        if sensor not in sensors_pm_action:
                            sensors_pm_action.append(sensor)
                    else:
                        top_color = (1.0, 0.0, 0.0, 1.0)  # Red - CRITICAL
                        if sensor not in sensors_follow_sop:
                            sensors_follow_sop.append(sensor)

                    # Track if sensor went above threshold at all (INSPECTION)
                    if sensor not in sensors_inspection:
                        sensors_inspection.append(sensor)

                    vertices = [
                        (bar_x, bar_y + threshold_height),
                        (bar_x + bar_width, bar_y + threshold_height),
                        (bar_x + bar_width, bar_y + threshold_height + top_height),
                        (bar_x, bar_y + threshold_height + top_height)
                    ]
                    batch = batch_for_shader(shader, 'TRIS', {"pos": vertices}, indices=[(0, 1, 2), (2, 3, 0)])
                    shader.uniform_float("color", top_color)
                    batch.draw(shader)

            # Highlight current day bar (white outline on Day 7)
            if current_day == 6 and interp_factor == 0.0:
                vertices = [
                    (bar_x - 2, bar_y - 2),
                    (bar_x + bar_width + 2, bar_y - 2),
                    (bar_x + bar_width + 2, bar_y + chart_height + 2),
                    (bar_x - 2, bar_y + chart_height + 2),
                    (bar_x - 2, bar_y - 2)
                ]
                batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": vertices})
                shader.uniform_float("color", (1.0, 1.0, 1.0, 0.7))
                gpu.state.line_width_set(2.0)
                batch.draw(shader)
                gpu.state.line_width_set(1.0)

            # Calculate brightness of bar color to determine text/icon color
            r, g, b = base_color
            brightness = (r * 0.299 + g * 0.587 + b * 0.114)  # Perceived brightness

            # Use off-black (grey) for light colors, off-white for dark colors
            if brightness > 0.5:
                text_color = (0.15, 0.15, 0.15, 1.0)  # Off-black (dark grey)
            else:
                text_color = (0.95, 0.95, 0.95, 1.0)  # Off-white

            # Convert type name to UPPER CASE and shorten to fit in bar
            type_name = sensor['type'].upper()
            if len(type_name) > 10:
                type_name = type_name[:8] + '..'

            import math
            angle = math.radians(90)  # 90 degrees rotation

            # Format value based on magnitude
            if value == 0:
                value_text = "0"
            elif value >= 1000:
                value_text = f"{value/1000:.1f}k"
            elif value >= 100:
                value_text = f"{value:.0f}"
            else:
                value_text = f"{value:.1f}"

            # Minimum required height for inside text: icon(40px) + type(~60px) + spacing(100px) + value(~60px) = 260px
            # If bar is tall enough (>260px), place everything INSIDE with guaranteed spacing
            min_height_for_inside = 260

            if bar_pixel_height >= min_height_for_inside:
                # Draw sensor icon at bottom
                sensor_icon = SENSOR_TYPE_ICONS.get(sensor['type'], '📊')
                blf.size(font_id, 32)
                blf.color(font_id, *text_color)  # Same color as text
                icon_x = bar_x + (bar_width // 2) - 16
                icon_y = bar_y + 8
                blf.position(font_id, icon_x, icon_y, 0)
                blf.draw(font_id, sensor_icon)

                # Draw type text above icon (rotated) - ABSOLUTE position
                blf.size(font_id, 18)
                blf.color(font_id, *text_color)
                blf.enable(font_id, blf.ROTATION)
                blf.rotation(font_id, angle)
                type_y_absolute = bar_y + 45  # Fixed position from bar bottom
                blf.position(font_id, bar_x + 22, type_y_absolute, 0)
                blf.draw(font_id, type_name)
                blf.rotation(font_id, 0)
                blf.disable(font_id, blf.ROTATION)

                # Draw value with ABSOLUTE 120px spacing from type text (increased from 100px)
                blf.size(font_id, 18)
                blf.color(font_id, *text_color)
                blf.enable(font_id, blf.ROTATION)
                blf.rotation(font_id, angle)
                value_y_absolute = type_y_absolute + 120  # ABSOLUTE 120px spacing
                blf.position(font_id, bar_x + 22, value_y_absolute, 0)
                blf.draw(font_id, value_text)
                blf.rotation(font_id, 0)
                blf.disable(font_id, blf.ROTATION)

            # If bar is short/nil, draw everything INSIDE panel starting from bar_y (fixed position)
            # Text should NOT move outside the chart area - fixed to bar base
            else:
                # Fixed base position - always start from bar_y (bottom of chart)
                base_y = bar_y + 5  # Start just above bar base, not moving with bar height

                # Draw sensor icon at fixed position
                sensor_icon = SENSOR_TYPE_ICONS.get(sensor['type'], '📊')
                blf.size(font_id, 32)
                # Use brightness-adjusted color for better visibility
                if brightness > 0.5:
                    icon_color = (0.15, 0.15, 0.15, 1.0)  # Dark for light sensors
                else:
                    icon_color = (0.95, 0.95, 0.95, 1.0)  # Light for dark sensors
                blf.color(font_id, *icon_color)
                icon_x = bar_x + (bar_width // 2) - 16
                icon_y = base_y
                blf.position(font_id, icon_x, icon_y, 0)
                blf.draw(font_id, sensor_icon)

                # Draw type text above icon (rotated) - ABSOLUTE fixed position
                blf.size(font_id, 18)
                blf.color(font_id, *icon_color)
                blf.enable(font_id, blf.ROTATION)
                blf.rotation(font_id, angle)
                type_y_absolute = base_y + 45  # ABSOLUTE 45px from icon
                blf.position(font_id, bar_x + 22, type_y_absolute, 0)
                blf.draw(font_id, type_name)
                blf.rotation(font_id, 0)
                blf.disable(font_id, blf.ROTATION)

                # Draw value above type text (rotated) - ABSOLUTE 120px spacing (same as tall bars)
                blf.size(font_id, 18)
                blf.color(font_id, *icon_color)
                blf.enable(font_id, blf.ROTATION)
                blf.rotation(font_id, angle)
                value_y_absolute = type_y_absolute + 120  # ABSOLUTE 120px spacing
                blf.position(font_id, bar_x + 22, value_y_absolute, 0)
                blf.draw(font_id, value_text)
                blf.rotation(font_id, 0)
                blf.disable(font_id, blf.ROTATION)

        # =============================================================================
        # STATUS BOX (Right side) - Comprehensive status with sensor icons
        # =============================================================================
        # status_box_width already calculated dynamically above (line 1093)
        status_box_height = 200
        # Position box with space from animation area (30px gap from last bar)
        last_bar_x = bar_x + bar_width  # x position of last drawn bar
        status_box_x = last_bar_x + 30
        status_box_y = chart_y + 40

        # No background - transparent only

        # STATUS BOX Title - double size (28pt), off-white
        blf.size(font_id, 28)
        blf.color(font_id, 0.85, 0.85, 0.85, 1.0)  # Off-white
        blf.position(font_id, status_box_x + 10, status_box_y + status_box_height - 40, 0)
        blf.draw(font_id, "STATUS")

        # Status items - off-white, double-line layout (label + icons on two lines)
        blf.size(font_id, 11)
        blf.color(font_id, 0.85, 0.85, 0.85, 1.0)  # Off-white default
        item_y = status_box_y + status_box_height - 70  # Increased from 55 to 70
        line_height = 45  # Increased from 30 to 45 for double-line layout
        icons_per_line = 4  # Max icons per line before wrapping

        # A. OK - grey if issues, off-white if all OK
        all_ok = len(sensors_inspection) == 0
        if all_ok:
            blf.color(font_id, 0.85, 0.85, 0.85, 1.0)  # Off-white
        else:
            blf.color(font_id, 0.4, 0.4, 0.4, 0.7)  # Grey transparent
        blf.position(font_id, status_box_x + 10, item_y, 0)
        blf.draw(font_id, "A. OK")

        # B. INSPECTION - with icons wrapping to second line
        item_y -= line_height
        if len(sensors_inspection) > 0:
            blf.color(font_id, 0.85, 0.85, 0.85, 1.0)  # Off-white (active)
            blf.position(font_id, status_box_x + 10, item_y, 0)
            blf.draw(font_id, "B. INSPECTION")
            # Show icons with wrapping (4 per line)
            icon_x_start = 140
            icon_y_line1 = item_y - 2  # First line (same as label)
            icon_y_line2 = item_y - 18  # Second line (16px below)
            for idx, sensor in enumerate(sensors_inspection):
                sensor_icon = SENSOR_TYPE_ICONS.get(sensor['type'], '📊')
                blf.size(font_id, 16)
                blf.color(font_id, 0.85, 0.85, 0.85, 1.0)  # Off-white
                # Calculate position with wrapping
                col = idx % icons_per_line
                row = idx // icons_per_line
                icon_x = status_box_x + icon_x_start + (col * 22)
                icon_y = icon_y_line1 if row == 0 else icon_y_line2
                blf.position(font_id, icon_x, icon_y, 0)
                blf.draw(font_id, sensor_icon)
            blf.size(font_id, 11)
        else:
            blf.color(font_id, 0.4, 0.4, 0.4, 0.7)  # Grey (inactive)
            blf.position(font_id, status_box_x + 10, item_y, 0)
            blf.draw(font_id, "B. INSPECTION")

        # C. PM ACTION - sensors in WARNING (orange) with wrapping
        item_y -= line_height
        if len(sensors_pm_action) > 0:
            blf.color(font_id, 0.85, 0.85, 0.85, 1.0)  # Off-white (active)
            blf.position(font_id, status_box_x + 10, item_y, 0)
            blf.draw(font_id, "C. PM ACTION")
            # Show icons with wrapping (4 per line)
            icon_x_start = 140
            icon_y_line1 = item_y - 2
            icon_y_line2 = item_y - 18
            for idx, sensor in enumerate(sensors_pm_action):
                sensor_icon = SENSOR_TYPE_ICONS.get(sensor['type'], '📊')
                blf.size(font_id, 16)
                blf.color(font_id, 0.85, 0.85, 0.85, 1.0)  # Off-white
                col = idx % icons_per_line
                row = idx // icons_per_line
                icon_x = status_box_x + icon_x_start + (col * 22)
                icon_y = icon_y_line1 if row == 0 else icon_y_line2
                blf.position(font_id, icon_x, icon_y, 0)
                blf.draw(font_id, sensor_icon)
            blf.size(font_id, 11)
        else:
            blf.color(font_id, 0.4, 0.4, 0.4, 0.7)  # Grey (inactive)
            blf.position(font_id, status_box_x + 10, item_y, 0)
            blf.draw(font_id, "C. PM ACTION")

        # D. FOLLOW SOP - sensors in CRITICAL (red) with wrapping
        item_y -= line_height
        if len(sensors_follow_sop) > 0:
            blf.color(font_id, 0.85, 0.85, 0.85, 1.0)  # Off-white (active)
            blf.position(font_id, status_box_x + 10, item_y, 0)
            blf.draw(font_id, "D. FOLLOW SOP")
            # Show icons with wrapping (4 per line)
            icon_x_start = 140
            icon_y_line1 = item_y - 2
            icon_y_line2 = item_y - 18
            for idx, sensor in enumerate(sensors_follow_sop):
                sensor_icon = SENSOR_TYPE_ICONS.get(sensor['type'], '📊')
                blf.size(font_id, 16)
                blf.color(font_id, 0.85, 0.85, 0.85, 1.0)  # Off-white
                col = idx % icons_per_line
                row = idx // icons_per_line
                icon_x = status_box_x + icon_x_start + (col * 22)
                icon_y = icon_y_line1 if row == 0 else icon_y_line2
                blf.position(font_id, icon_x, icon_y, 0)
                blf.draw(font_id, sensor_icon)
            blf.size(font_id, 11)
        else:
            blf.color(font_id, 0.4, 0.4, 0.4, 0.7)  # Grey (inactive)
            blf.position(font_id, status_box_x + 10, item_y, 0)
            blf.draw(font_id, "D. FOLLOW SOP")

        # E. REPAIR/REPLACE - to be implemented
        item_y -= line_height
        blf.color(font_id, 0.4, 0.4, 0.4, 0.7)  # Grey (not implemented)
        blf.position(font_id, status_box_x + 10, item_y, 0)
        blf.draw(font_id, "E. REPAIR/REPLACE")

        # Draw ESC hint (LEFT side, bottom)
        blf.size(font_id, 10)
        blf.color(font_id, 0.6, 0.6, 0.6, 0.9)
        blf.position(font_id, chart_x + 15, chart_y + 5, 0)
        blf.draw(font_id, "ESC to close")

        gpu.state.blend_set('NONE')


class BIM_OT_equipment_open_google_maps(Operator):
    """Open Google Maps with directions from office to equipment location"""
    bl_idname = "bim.equipment_open_google_maps"
    bl_label = "Get Directions"
    bl_options = {'REGISTER'}

    latitude: bpy.props.FloatProperty()
    longitude: bpy.props.FloatProperty()

    def execute(self, context):
        import webbrowser

        props = context.scene.BIMFederationProperties
        office_address = props.office_address

        if not office_address:
            self.report({'WARNING'}, "Please set Office/Depot Address in N Panel first")
            return {'CANCELLED'}

        if not self.latitude or not self.longitude:
            self.report({'ERROR'}, "Equipment has no GPS coordinates")
            return {'CANCELLED'}

        # Build Google Maps directions URL
        # Format: https://www.google.com/maps/dir/?api=1&origin=ADDRESS&destination=LAT,LON
        origin = office_address.replace(' ', '+')
        destination = f"{self.latitude},{self.longitude}"

        url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={destination}"

        LOGGER.log(f"Opening Google Maps directions: {office_address} → {destination}")
        webbrowser.open(url)

        self.report({'INFO'}, f"Opened directions in browser")
        return {'FINISHED'}


class BIM_OT_equipment_view_properties(Operator):
    """View equipment properties and sensor details"""
    bl_idname = "bim.equipment_view_properties"
    bl_label = "View Equipment Details"
    bl_options = {'REGISTER'}

    equipment_name: bpy.props.StringProperty()
    equipment_type: bpy.props.StringProperty()
    marker_id: bpy.props.IntProperty()

    def execute(self, context):
        return {'FINISHED'}

    def invoke(self, context, event):
        # Get selected object
        if not context.active_object:
            self.report({'WARNING'}, "No equipment selected")
            return {'CANCELLED'}

        obj = context.active_object

        # Check if it's an equipment marker and extract type
        equipment_type = None

        for eq_type in EQUIPMENT_TYPES.keys():
            pattern = eq_type.upper() + '_'
            if obj.name.upper().startswith(pattern):
                equipment_type = eq_type
                break

        if not equipment_type:
            self.report({'WARNING'}, "Selected object is not equipment marker")
            return {'CANCELLED'}

        # Extract marker ID from custom property (preferred) or name (fallback)
        if "marker_id" in obj:
            marker_id = obj["marker_id"]
        else:
            try:
                num_str = obj.name.split('_')[-1]
                marker_id = int(num_str)
            except:
                self.report({'ERROR'}, "Could not parse equipment ID")
                return {'CANCELLED'}

        self.equipment_name = obj.name
        self.equipment_type = equipment_type
        self.marker_id = marker_id

        # Fetch data from database
        return context.window_manager.invoke_props_dialog(self, width=600)

    def draw(self, context):
        import sqlite3
        from pathlib import Path

        layout = self.layout

        db_path = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db")

        if not db_path.exists():
            layout.label(text="Database not found", icon='ERROR')
            return

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Get equipment info
            cursor.execute("""
                SELECT name, marker_type, location_x, location_y, location_z,
                       latitude, longitude, gps_elevation,
                       gps_accuracy_m, gps_measured_date, gps_measured_by,
                       position_source, priority, status, installation_date
                FROM project_markers
                WHERE id = ?
            """, (self.marker_id,))

            marker_row = cursor.fetchone()

            if not marker_row:
                layout.label(text="Equipment not found in database", icon='ERROR')
                conn.close()
                return

            (name, marker_type, loc_x, loc_y, loc_z, latitude, longitude, gps_elevation,
             gps_accuracy, gps_date, gps_by, pos_source, priority, status, install_date) = marker_row

            # Header
            equipment_info = EQUIPMENT_TYPES.get(marker_type, {})

            # Dynamic color emoji mapping
            color_map = {
                'boom_trap': '🟠 ORANGE',
                'water_quality': '🩵 TURQUOISE',
                'biodiversity': '🟢 GREEN',
                'wildlife_camera': '🟢 GREEN',
                'biochar': '🟩 MINT',
                'mrf': '🩷 PINK',
                'pollutant_sensor': '🟣 PURPLE',
                'flood_monitor': '🔵 BLUE',
            }
            color_name = color_map.get(marker_type, '⚪ UNKNOWN')

            header_box = layout.box()
            header_box.scale_y = 1.5
            row = header_box.row()
            row.label(text=f"{color_name} - {equipment_info.get('name', 'Unknown')}", icon=equipment_info.get('icon', 'MESH_CIRCLE'))

            layout.separator()

            # Equipment details
            info_box = layout.box()
            info_box.label(text="Equipment Information", icon='INFO')
            col = info_box.column(align=True)
            col.label(text=f"ID: {self.equipment_name}")
            col.label(text=f"Blender: ({loc_x:.1f}, {loc_y:.1f}, {loc_z:.1f})")

            if latitude and longitude:
                col.separator(factor=0.5)

                # GPS coordinates with clickable link
                gps_row = col.row(align=True)
                # GPS verification status
                if pos_source == 'gps_verified':
                    gps_row.label(text=f"📍 {latitude:.6f}°N, {longitude:.6f}°E ✓", icon='WORLD')
                else:
                    gps_row.label(text=f"📍 {latitude:.6f}°N, {longitude:.6f}°E", icon='WORLD')

                # Google Maps directions button
                nav_row = col.row(align=True)
                nav_row.scale_y = 1.2
                op = nav_row.operator("bim.equipment_open_google_maps", text="🗺️ Get Directions from Office", icon='URL')
                op.latitude = latitude
                op.longitude = longitude

                if gps_elevation:
                    col.separator(factor=0.3)
                    col.label(text=f"Elevation: {gps_elevation:.1f}m")

                # GPS accuracy info
                if gps_accuracy:
                    col.label(text=f"GPS Accuracy: ±{gps_accuracy:.1f}m")
                if gps_date and gps_by:
                    col.label(text=f"Verified: {gps_date[:10]} by {gps_by}")

            col.separator(factor=0.5)
            col.label(text=f"Priority: {priority}")
            col.label(text=f"Status: {status}")
            if install_date:
                col.label(text=f"Installed: {install_date[:10]}")

            layout.separator()

            # Get sensors
            cursor.execute("""
                SELECT sensor_id, sensor_name, sensor_type, unit,
                       manufacturer, model, status, api_endpoint, mqtt_topic
                FROM sensors
                WHERE equipment_marker_id = ?
                ORDER BY sensor_type
            """, (self.marker_id,))

            sensors = cursor.fetchall()

            sensor_box = layout.box()
            sensor_box.label(text=f"IoT Sensors ({len(sensors)} devices)", icon='OUTLINER_OB_LIGHTPROBE')

            if sensors:
                grid = sensor_box.grid_flow(row_major=True, columns=1, align=True)

                for sensor_id, sensor_name, sensor_type, unit, manufacturer, model, sensor_status, api_endpoint, mqtt_topic in sensors:
                    sensor_item = grid.box()

                    # Sensor header with emoji icon
                    row = sensor_item.row()
                    sensor_emoji = SENSOR_TYPE_ICONS.get(sensor_type, '📊')
                    status_icon = 'CHECKMARK' if sensor_status == 'ACTIVE' else 'QUESTION' if sensor_status == 'PROVISIONED' else 'ERROR'
                    row.label(text=f"{sensor_emoji} {sensor_name}", icon=status_icon)

                    # Sensor details
                    col = sensor_item.column(align=True)
                    col.scale_y = 0.8
                    col.label(text=f"  ID: {sensor_id}")
                    col.label(text=f"  Type: {sensor_type} ({unit})" if unit else f"  Type: {sensor_type}")
                    col.label(text=f"  Device: {manufacturer} {model}")
                    col.label(text=f"  Status: {sensor_status}")

                    # API integration info
                    col.separator(factor=0.3)
                    col.label(text=f"  API: {api_endpoint}")
                    col.label(text=f"  MQTT: {mqtt_topic}")

            else:
                sensor_box.label(text="No sensors configured")

            conn.close()

        except Exception as e:
            layout.label(text=f"Error: {str(e)}", icon='ERROR')
            import traceback
            traceback.print_exc()


class BIM_OT_equipment_clear_all(Operator):
    """Clear all placed equipment"""
    bl_idname = "bim.equipment_clear_all"
    bl_label = "Clear All Equipment"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        global PLACED_EQUIPMENT

        LOGGER.section("CLEARING ALL EQUIPMENT")

        total = 0

        # Delete by name pattern (more robust - doesn't rely on object references)
        patterns = ['BOOM_TRAP_', 'WATER_QUALITY_', 'BIODIVERSITY_', 'WILDLIFE_CAMERA_',
                    'BIOCHAR_', 'MRF_', 'POLLUTANT_SENSOR_', 'FLOOD_MONITOR_']
        for obj in list(bpy.data.objects):
            if any(obj.name.startswith(pattern) for pattern in patterns):
                try:
                    obj_name = obj.name  # Store name before deletion
                    bpy.data.objects.remove(obj, do_unlink=True)
                    total += 1
                    LOGGER.log(f"  Deleted: {obj_name}")
                except Exception as e:
                    LOGGER.log(f"  Failed to delete {obj.name}: {e}")

        # Clear data structure (don't access object references after deletion)
        for equipment_type in EQUIPMENT_TYPES.keys():
            PLACED_EQUIPMENT[equipment_type] = []

        # Delete from database
        self.delete_from_database()

        LOGGER.log(f"✅ CLEARED: Removed {total} equipment markers from scene")

        # Force gizmo group refresh by recreating it
        try:
            # Unregister and re-register gizmo group to force refresh
            from . import river_equipment_gizmo

            # Find all 3D view areas and refresh gizmos
            for window in bpy.context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        # Force redraw which triggers gizmo refresh
                        area.tag_redraw()
                        LOGGER.log(f"→ Triggered gizmo refresh for 3D view")

            # Also refresh current context
            if bpy.context.area and bpy.context.area.type == 'VIEW_3D':
                bpy.context.area.tag_redraw()

        except Exception as e:
            LOGGER.log(f"Warning: Could not refresh gizmos: {e}")

        self.report({'INFO'}, f"Cleared {total} equipment markers")
        return {'FINISHED'}

    def delete_from_database(self):
        """Delete all equipment markers from database"""
        import sqlite3
        from pathlib import Path

        db_path = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db")

        if not db_path.exists():
            LOGGER.log("Database not found, skipping delete", error=True)
            return

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            LOGGER.section("DELETING FROM DATABASE")

            # Get count before delete
            marker_types = ', '.join([f"'{mt}'" for mt in EQUIPMENT_TYPES.keys()])
            cursor.execute(f"SELECT COUNT(*) FROM project_markers WHERE marker_type IN ({marker_types})")
            count_before = cursor.fetchone()[0]

            # Delete equipment markers (keep other marker types if any)
            marker_types = ', '.join([f"'{mt}'" for mt in EQUIPMENT_TYPES.keys()])
            cursor.execute(f"""
                DELETE FROM project_markers
                WHERE marker_type IN ({marker_types})
            """)

            deleted = cursor.rowcount
            conn.commit()
            conn.close()

            LOGGER.log(f"✅ Deleted {deleted} equipment markers from database")
            LOGGER.log(f"Database: {db_path}")

        except Exception as e:
            LOGGER.log(f"ERROR deleting from database: {e}", error=True)
            import traceback
            traceback.print_exc()


# =============================================================================
# UI PANEL
# =============================================================================

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

        # Map Background & River Centerline
        map_box = layout.box()
        map_box.label(text="🗺️ Map Background:", icon='WORLD')
        row = map_box.row(align=True)
        op = row.operator("bim.river_load_map_background", text="Satellite", icon='IMAGE_DATA')
        op.layer_type = 'satellite'
        op = row.operator("bim.river_load_map_background", text="Terrain", icon='RNDCURVE')
        op.layer_type = 'terrain'

        # River Centerline from OSM
        map_box.separator()
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

        # Counts
        box = layout.box()
        box.label(text="Placed Equipment:", icon='CHECKMARK')

        global PLACED_EQUIPMENT
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
        col.label(text="Starting point for Google Maps directions")
        props = context.scene.BIMFederationProperties
        address_box.prop(props, "office_address", text="")

        layout.separator()

        # Debug info
        debug_box = layout.box()
        debug_box.label(text="Debug Info:", icon='INFO')
        debug_box.label(text=f"Log: ~/Documents/bonsai/consolelogs/")
        debug_box.label(text="river_equipment_placement.txt")


# =============================================================================
# 7D MAINTENANCE - RIGHT-CLICK CONTEXT MENU
# =============================================================================

class BIM_MT_equipment_context_menu(bpy.types.Menu):
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


class BIM_OT_equipment_view_pm_schedule(Operator):
    """View Preventive Maintenance Schedule for Equipment"""
    bl_idname = "bim.equipment_view_pm_schedule"
    bl_label = "View PM Schedule"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import sqlite3
        import subprocess
        import sys
        from pathlib import Path

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
        db_path = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db")
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
        from pathlib import Path
        from datetime import datetime

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

        db_path = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db")
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
        from pathlib import Path
        from datetime import datetime, timedelta

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

        db_path = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db")
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
# GOOGLE MAPS INTEGRATION - Imported from river_map_background.py
# =============================================================================
# Map background operators are in separate module for maintainability


# Register context menu to appear on right-click
def menu_func(self, context):
    if context.active_object:
        patterns = [eq_type.upper() + '_' for eq_type in EQUIPMENT_TYPES.keys()]
        if any(context.active_object.name.upper().startswith(p) for p in patterns):
            self.layout.separator()
            self.layout.menu("BIM_MT_equipment_context_menu", icon='TOOL_SETTINGS')


# =============================================================================
# REGISTRATION
# =============================================================================

LOGGER.section("MODULE LOADED")
LOGGER.log("Ready for registration in federation __init__.py")
LOGGER.log(f"Log file: {LOGGER.log_file}")
