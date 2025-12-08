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
        'color': (1.0, 0.0, 0.0),  # Pure Red
        'icon': 'MESH_CIRCLE',
        'radius': 3.0
    },
    'water_quality': {
        'name': 'Water Quality Station',
        'color': (0.0, 0.5, 1.0),  # Blue
        'icon': 'MATFLUID',
        'radius': 3.0
    },
    'biodiversity': {
        'name': 'Biodiversity Monitor',
        'color': (0.0, 1.0, 0.0),  # Pure Green
        'icon': 'ORPHAN_DATA',
        'radius': 3.0
    },
}

# Global storage for placed equipment
PLACED_EQUIPMENT = {key: [] for key in EQUIPMENT_TYPES.keys()}

LOGGER.log(f"Loaded {len(EQUIPMENT_TYPES)} equipment types:")
for key, info in EQUIPMENT_TYPES.items():
    LOGGER.log(f"  • {info['name']} - RGB{info['color']}")

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
        box.label(text=f"Color: {'Red' if info['color'][0] == 1.0 else 'Blue' if info['color'][2] == 1.0 else 'Green'}")
        box.label(text=f"Radius: {info['radius']}m")


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

        # Add to scene
        context.collection.objects.link(empty)

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

            # Get mesh object transform (same as mesh baking uses)
            # Mesh baking sets obj.location = element_transforms offset
            # Apply same offset to equipment for alignment
            cursor.execute("SELECT center_x, center_y, center_z FROM element_transforms LIMIT 1")
            transform_row = cursor.fetchone()
            mesh_offset = transform_row if transform_row else (0.0, 0.0, 0.0)
            LOGGER.log(f"Mesh object offset: ({mesh_offset[0]:.2f}, {mesh_offset[1]:.2f}, {mesh_offset[2]:.2f})")
            LOGGER.log("Applying same offset to equipment (display time, not stored)")

            # Query equipment markers
            cursor.execute("""
                SELECT marker_type, name, location_x, location_y, location_z
                FROM project_markers
                WHERE marker_type IN ('boom_trap', 'water_quality', 'biodiversity')
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

            # Create empties from database
            total_loaded = 0
            for marker_type, name, x, y, z in rows:
                if marker_type not in EQUIPMENT_TYPES:
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

                context.collection.objects.link(empty)

                # Store with offset-applied coordinates (same as empty.location)
                # Gizmos read from here, so must match empty position
                stored_x = x + mesh_offset[0]
                stored_y = y + mesh_offset[1]
                stored_z = z + mesh_offset[2]

                PLACED_EQUIPMENT[marker_type].append({
                    'id': empty.name,
                    'number': count,
                    'x': stored_x,
                    'y': stored_y,
                    'z': stored_z,
                    'object': empty,
                    'object_name': empty.name
                })

                total_loaded += 1
                LOGGER.log(f"  Loaded: {name} - DB:({x:.1f}, {y:.1f}, {z:.1f}) → Display:({stored_x:.1f}, {stored_y:.1f}, {stored_z:.1f})")

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


class BIM_OT_equipment_view_sensor_dashboard(Operator):
    """View animated sensor bar chart overlay (Day 1-7 animation)"""
    bl_idname = "bim.equipment_view_sensor_dashboard"
    bl_label = "View Sensor Dashboard"
    bl_options = {'REGISTER'}

    # Class-level singleton instance tracker
    _active_instance = None

    _draw_handler = None
    _timer = None
    _sensor_data = []
    _equipment_name = ""
    _marker_id = 0
    _animation_time = 0.0
    _cycle_duration = 6.0  # 6 seconds for Day 1-6 (1 sec per day, smoother)
    _linger_duration = 2.0  # 2 second linger on Day 7

    def invoke(self, context, event):
        import sqlite3
        from pathlib import Path

        # Close any existing dashboard instance first
        if BIM_OT_equipment_view_sensor_dashboard._active_instance is not None:
            old_instance = BIM_OT_equipment_view_sensor_dashboard._active_instance
            LOGGER.log("Closing previous dashboard instance...")
            old_instance.cleanup(context)
            BIM_OT_equipment_view_sensor_dashboard._active_instance = None

        LOGGER.section("SENSOR DASHBOARD OPENING (GPU OVERLAY)")

        if not context.active_object:
            LOGGER.log("WARNING: No equipment selected", error=True)
            self.report({'WARNING'}, "No equipment selected")
            return {'CANCELLED'}

        obj = context.active_object

        # Extract marker ID from object name
        patterns = ['BOOM_TRAP_', 'WATER_QUALITY_', 'BIODIVERSITY_']
        found = False
        for pattern in patterns:
            if obj.name.startswith(pattern):
                try:
                    num_str = obj.name.split('_')[-1]
                    self._marker_id = int(num_str)
                    self._equipment_name = obj.name
                    found = True
                    LOGGER.log(f"Equipment: {obj.name}, Marker ID: {self._marker_id}")
                    break
                except Exception as e:
                    LOGGER.log(f"ERROR parsing equipment name: {e}", error=True)
                    pass

        if not found:
            LOGGER.log("WARNING: Selected object is not equipment marker", error=True)
            self.report({'WARNING'}, "Selected object is not equipment marker")
            return {'CANCELLED'}

        # Load sensor data
        db_path = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db")
        if not db_path.exists():
            LOGGER.log(f"ERROR: Database not found: {db_path}", error=True)
            self.report({'ERROR'}, "Database not found")
            return {'CANCELLED'}

        try:
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

            # Sensor type colors (RGB)
            colors = {
                'loadcell': (0.3, 0.5, 0.9),
                'waterlevel': (0.2, 0.7, 0.9),
                'flowvelocity': (0.4, 0.8, 0.6),
                'ph': (0.6, 0.9, 0.4),
                'dissolvedoxygen': (0.3, 0.9, 0.6),
                'turbidity': (0.8, 0.6, 0.4),
                'temperature': (0.95, 0.6, 0.3),
                'conductivity': (0.7, 0.5, 0.9),
                'heavymetals': (0.9, 0.3, 0.3),
                'aicamera': (0.6, 0.6, 0.95),
                'pirmotion': (0.95, 0.9, 0.4),
                'audiorecorder': (0.8, 0.4, 0.8),
                'integrity': (0.4, 0.4, 0.4),
            }

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
                    self._sensor_data.append({
                        'name': sensor_name,
                        'type': sensor_type,
                        'threshold': threshold_max if threshold_max else max(day_values) * 0.9,
                        'values': day_values,
                        'color': colors.get(sensor_type, (0.5, 0.5, 0.5))
                    })
                    LOGGER.log(f"  Loaded: {sensor_name} ({sensor_type})")

            conn.close()

            if not self._sensor_data:
                LOGGER.log("WARNING: No sensor data available", error=True)
                self.report({'WARNING'}, "No sensor data available")
                return {'CANCELLED'}

            LOGGER.log(f"✓ Loaded {len(self._sensor_data)} sensors with data")

            # Set up GPU draw handler
            import bpy
            import blf
            import gpu
            from gpu_extras.batch import batch_for_shader

            args = (self, context)
            self._draw_handler = bpy.types.SpaceView3D.draw_handler_add(
                self.draw_callback_px, args, 'WINDOW', 'POST_PIXEL'
            )

            # Set up timer for animation
            self._timer = context.window_manager.event_timer_add(0.033, window=context.window)  # ~30fps
            self._animation_time = 0.0

            context.window_manager.modal_handler_add(self)

            # Register this instance as the active one
            BIM_OT_equipment_view_sensor_dashboard._active_instance = self

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
            self.cleanup(context)
            # Clear the active instance tracker
            if BIM_OT_equipment_view_sensor_dashboard._active_instance == self:
                BIM_OT_equipment_view_sensor_dashboard._active_instance = None
            LOGGER.log("✓ Sensor dashboard closed (ESC)")
            return {'CANCELLED'}

        if event.type == 'TIMER':
            # Update animation time
            self._animation_time += 0.033
            total_cycle = self._cycle_duration + self._linger_duration
            if self._animation_time > total_cycle:
                self._animation_time -= total_cycle

            # Redraw viewport
            context.area.tag_redraw()

        return {'PASS_THROUGH'}

    def cleanup(self, context):
        import bpy

        if self._draw_handler:
            bpy.types.SpaceView3D.draw_handler_remove(self._draw_handler, 'WINDOW')
            self._draw_handler = None

        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None

    @staticmethod
    def draw_callback_px(operator_self, context):
        import blf
        import gpu
        from gpu_extras.batch import batch_for_shader

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

        # Chart dimensions
        chart_width = 1000
        chart_height = 400
        bar_width = 45  # 50% wider (was 30)
        bar_spacing = 15  # Increased spacing proportionally
        margin_left = 50
        margin_bottom = 100

        # Position in viewport (bottom-left area)
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
        # Determine equipment type color
        equipment_name = operator_self._equipment_name
        if equipment_name.startswith('BOOM_TRAP'):
            header_color = (1.0, 0.0, 0.0, 0.85)  # Red for Boom Traps
        elif equipment_name.startswith('WATER_QUALITY'):
            header_color = (0.0, 0.5, 1.0, 0.85)  # Blue for Water Quality
        elif equipment_name.startswith('BIODIVERSITY'):
            header_color = (0.0, 1.0, 0.0, 0.85)  # Green for Biodiversity
        else:
            header_color = (0.3, 0.3, 0.3, 0.85)  # Gray fallback

        header_vertices = [
            (chart_x - 20, chart_y + chart_height + 10),
            (chart_x + chart_width + 20, chart_y + chart_height + 10),
            (chart_x + chart_width + 20, chart_y + chart_height + 80),
            (chart_x - 20, chart_y + chart_height + 80)
        ]
        batch = batch_for_shader(shader, 'TRIS', {"pos": header_vertices}, indices=indices)
        shader.uniform_float("color", header_color)
        batch.draw(shader)

        # Draw title and infographic
        font_id = 0
        blf.size(font_id, 20)
        blf.color(font_id, 1.0, 1.0, 1.0, 1.0)
        blf.position(font_id, chart_x, chart_y + chart_height + 40, 0)
        blf.draw(font_id, f"📊 {operator_self._equipment_name} - Day {current_day + 1}/7")

        # Infographic subtitle
        blf.size(font_id, 12)
        blf.color(font_id, 0.7, 0.7, 0.7, 1.0)
        blf.position(font_id, chart_x, chart_y + chart_height + 20, 0)
        blf.draw(font_id, "7-Day Sensor Trend → Yellow line = Threshold limit")

        # Draw threshold line
        threshold_y = chart_y + int(chart_height * 0.77)  # Threshold at ~77% height
        vertices = [
            (chart_x, threshold_y),
            (chart_x + chart_width, threshold_y)
        ]
        batch = batch_for_shader(shader, 'LINES', {"pos": vertices})
        shader.uniform_float("color", (1.0, 0.8, 0.0, 0.6))
        batch.draw(shader)

        # Draw threshold label
        blf.size(font_id, 14)
        blf.color(font_id, 1.0, 0.8, 0.0, 0.8)
        blf.position(font_id, chart_x - 45, threshold_y - 7, 0)
        blf.draw(font_id, "MAX")

        # Draw sensor bars
        num_sensors = len(operator_self._sensor_data)
        total_bar_width = num_sensors * (bar_width + bar_spacing)
        start_x = chart_x + (chart_width - total_bar_width) // 2

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
                        top_color = (1.0, 0.6, 0.0, 1.0)  # Orange
                    else:
                        top_color = (1.0, 0.0, 0.0, 1.0)  # Red

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

            # Draw value label INSIDE bar (rotated sideways) - all days during animation
            if bar_pixel_height > 50:
                blf.size(font_id, 9)

                # Format value based on magnitude
                if value >= 1000:
                    value_text = f"{value/1000:.1f}k"
                elif value >= 100:
                    value_text = f"{value:.0f}"
                else:
                    value_text = f"{value:.1f}"

                # White text for contrast
                blf.color(font_id, 1.0, 1.0, 1.0, 1.0)

                # Calculate text position (middle of bar)
                text_x = bar_x + 5
                text_y = bar_y + (bar_pixel_height // 2) - 15

                # Save current state
                import math
                angle = math.radians(90)  # 90 degrees in radians

                # Apply rotation and draw
                blf.enable(font_id, blf.ROTATION)
                blf.rotation(font_id, angle)
                blf.position(font_id, text_x + 22, text_y, 0)
                blf.draw(font_id, value_text)
                blf.rotation(font_id, 0)  # Reset rotation
                blf.disable(font_id, blf.ROTATION)

            # Draw sensor icon INSIDE bar (bottom section)
            # Sensor type emoji mapping
            sensor_icons = {
                'loadcell': '⚖️',
                'waterlevel': '🌊',
                'flowvelocity': '💨',
                'ph': '🧪',
                'dissolvedoxygen': '💧',
                'turbidity': '☁️',
                'temperature': '🌡️',
                'conductivity': '⚡',
                'heavymetals': '☢️',
                'aicamera': '📷',
                'pirmotion': '👁️',
                'audiorecorder': '🎤',
                'integrity': '🔧',
            }

            sensor_icon = sensor_icons.get(sensor['type'], '📊')
            blf.size(font_id, 18)  # Larger icon (was 14)
            blf.color(font_id, 1.0, 1.0, 1.0, 0.8)  # Slightly more opaque
            icon_x = bar_x + (bar_width // 2) - 9  # Center icon in wider bar
            icon_y = bar_y + 8
            blf.position(font_id, icon_x, icon_y, 0)
            blf.draw(font_id, sensor_icon)

        # Draw color legend (bottom right)
        legend_x = chart_x + chart_width - 250
        legend_y = chart_y - 60
        blf.size(font_id, 11)

        # Green indicator
        blf.color(font_id, 0.3, 1.0, 0.3, 1.0)
        blf.position(font_id, legend_x, legend_y, 0)
        blf.draw(font_id, "■ Normal")

        # Orange indicator
        blf.color(font_id, 1.0, 0.6, 0.0, 1.0)
        blf.position(font_id, legend_x + 70, legend_y, 0)
        blf.draw(font_id, "■ Warning")

        # Red indicator
        blf.color(font_id, 1.0, 0.0, 0.0, 1.0)
        blf.position(font_id, legend_x + 150, legend_y, 0)
        blf.draw(font_id, "■ Critical")

        # Draw ESC hint
        blf.size(font_id, 16)
        blf.color(font_id, 0.8, 0.8, 0.8, 0.9)
        blf.position(font_id, chart_x + chart_width - 100, chart_y - 85, 0)
        blf.draw(font_id, "ESC to close")

        gpu.state.blend_set('NONE')


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

        # Check if it's an equipment marker
        patterns = ['BOOM_TRAP_', 'WATER_QUALITY_', 'BIODIVERSITY_']
        equipment_type = None

        for pattern in patterns:
            if obj.name.startswith(pattern):
                if pattern == 'BOOM_TRAP_':
                    equipment_type = 'boom_trap'
                elif pattern == 'WATER_QUALITY_':
                    equipment_type = 'water_quality'
                elif pattern == 'BIODIVERSITY_':
                    equipment_type = 'biodiversity'
                break

        if not equipment_type:
            self.report({'WARNING'}, "Selected object is not equipment marker")
            return {'CANCELLED'}

        # Extract marker ID from name
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
                WHERE marker_id = ?
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
            color_name = '🔴 RED' if marker_type == 'boom_trap' else '🔵 BLUE' if marker_type == 'water_quality' else '🟢 GREEN'

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

                # GPS verification status
                if pos_source == 'gps_verified':
                    col.label(text=f"GPS: {latitude:.6f}°N, {longitude:.6f}°E ✓", icon='WORLD')
                else:
                    col.label(text=f"GPS: {latitude:.6f}°N, {longitude:.6f}°E (estimated)", icon='WORLD')

                if gps_elevation:
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

                    # Sensor header
                    row = sensor_item.row()
                    status_icon = 'CHECKMARK' if sensor_status == 'ACTIVE' else 'QUESTION' if sensor_status == 'PROVISIONED' else 'ERROR'
                    row.label(text=sensor_name, icon=status_icon)

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
        patterns = ['BOOM_TRAP_', 'WATER_QUALITY_', 'BIODIVERSITY_']
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
            cursor.execute("SELECT COUNT(*) FROM project_markers WHERE marker_type IN ('boom_trap', 'water_quality', 'biodiversity')")
            count_before = cursor.fetchone()[0]

            # Delete equipment markers (keep other marker types if any)
            cursor.execute("""
                DELETE FROM project_markers
                WHERE marker_type IN ('boom_trap', 'water_quality', 'biodiversity')
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

        # Counts
        box = layout.box()
        box.label(text="Placed Equipment:", icon='CHECKMARK')

        global PLACED_EQUIPMENT
        total_count = 0
        for equipment_type, items in PLACED_EQUIPMENT.items():
            count = len(items)
            if count > 0:
                row = box.row()
                icon = EQUIPMENT_TYPES[equipment_type]['icon']
                name = EQUIPMENT_TYPES[equipment_type]['name']
                color_name = '🔴 Red' if equipment_type == 'boom_trap' else '🔵 Blue' if equipment_type == 'water_quality' else '🟢 Green'
                row.label(text=f"{color_name} - {name}: {count}", icon=icon)
                total_count += count

        if total_count == 0:
            box.label(text="(None placed yet)")

        layout.separator()

        # View Details (if equipment selected)
        if context.active_object:
            patterns = ['BOOM_TRAP_', 'WATER_QUALITY_', 'BIODIVERSITY_']
            if any(context.active_object.name.startswith(p) for p in patterns):
                detail_box = layout.box()
                detail_box.label(text="Selected Equipment:", icon='OUTLINER_OB_EMPTY')
                detail_box.label(text=f"  {context.active_object.name}")

                row = detail_box.row(align=True)
                row.scale_y = 1.2
                row.operator("bim.equipment_view_sensor_dashboard", text="📊 Sensor Dashboard", icon='GRAPH')

                detail_box.operator("bim.equipment_view_properties", text="View Details", icon='VIEWZOOM')
                layout.separator()

        # Actions
        col = layout.column(align=True)
        col.alert = True
        col.operator("bim.equipment_clear_all", text="Clear All", icon='TRASH')

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
        patterns = ['BOOM_TRAP_', 'WATER_QUALITY_', 'BIODIVERSITY_']
        return any(context.active_object.name.startswith(p) for p in patterns)

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

        # Extract marker ID from name
        try:
            if obj.name.startswith('BOOM_TRAP_'):
                marker_id = int(obj.name.replace('BOOM_TRAP_', ''))
            elif obj.name.startswith('WATER_QUALITY_'):
                marker_id = int(obj.name.replace('WATER_QUALITY_', ''))
            elif obj.name.startswith('BIODIVERSITY_'):
                marker_id = int(obj.name.replace('BIODIVERSITY_', ''))
            else:
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

        # Extract marker ID
        try:
            if obj.name.startswith('BOOM_TRAP_'):
                marker_id = int(obj.name.replace('BOOM_TRAP_', ''))
            elif obj.name.startswith('WATER_QUALITY_'):
                marker_id = int(obj.name.replace('WATER_QUALITY_', ''))
            elif obj.name.startswith('BIODIVERSITY_'):
                marker_id = int(obj.name.replace('BIODIVERSITY_', ''))
            else:
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

        # Extract marker ID
        try:
            if obj.name.startswith('BOOM_TRAP_'):
                marker_id = int(obj.name.replace('BOOM_TRAP_', ''))
            elif obj.name.startswith('WATER_QUALITY_'):
                marker_id = int(obj.name.replace('WATER_QUALITY_', ''))
            elif obj.name.startswith('BIODIVERSITY_'):
                marker_id = int(obj.name.replace('BIODIVERSITY_', ''))
            else:
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


# Register context menu to appear on right-click
def menu_func(self, context):
    if context.active_object:
        patterns = ['BOOM_TRAP_', 'WATER_QUALITY_', 'BIODIVERSITY_']
        if any(context.active_object.name.startswith(p) for p in patterns):
            self.layout.separator()
            self.layout.menu("BIM_MT_equipment_context_menu", icon='TOOL_SETTINGS')


# =============================================================================
# REGISTRATION
# =============================================================================

LOGGER.section("MODULE LOADED")
LOGGER.log("Ready for registration in federation __init__.py")
LOGGER.log(f"Log file: {LOGGER.log_file}")
