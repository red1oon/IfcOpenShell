# Bonsai - OpenBIM Blender Add-on
# River Equipment Operators Module
# Extracted from equipment_placement.py

"""
Equipment Operators
===================
Core operators for equipment placement, loading, and interaction:
- Equipment type selection
- Click-to-place marker placement
- Database loading
- Sensor dashboard viewing
- Properties viewing
- Clear all functionality
"""

import bpy
from bpy.props import EnumProperty
from bpy.types import Operator
from bpy_extras import view3d_utils
from mathutils import Vector
from pathlib import Path
from datetime import datetime

# Import shared configuration
from .equipment_logger import LOGGER
from .equipment_config import (
    EQUIPMENT_TYPES,
    SENSOR_TYPE_ICONS,
    SENSOR_TYPE_COLORS,
    PLACED_EQUIPMENT
)
from . import equipment_sensor  # For sensor dashboard functionality


# =============================================================================
# EQUIPMENT SELECTION OPERATOR
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


# =============================================================================
# EQUIPMENT PLACEMENT OPERATOR
# =============================================================================

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
        from . import river_utils

        db_path = river_utils.RIVER_DB_PATH

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
                color_hex = river_utils.rgb_to_hex(*equipment_info['color'])

                for item in items:
                    marker_id = item['number']
                    name = f"{equipment_info['name']} #{marker_id}"
                    latitude, longitude, elevation = geo.blender_to_gps(item['x'], item['y'], item['z'])

                    # Save equipment marker
                    river_utils.save_marker_to_db(
                        cursor, marker_id, equipment_type, name,
                        f"{equipment_info['name']} placed via Blender UI",
                        item['x'], item['y'], item['z'],
                        latitude, longitude, elevation, color_hex
                    )
                    total_saved += 1
                    LOGGER.log(f"  Saved: {name} at ({item['x']:.1f}, {item['y']:.1f}, {item['z']:.1f})")
                    LOGGER.log(f"    GPS: {latitude:.6f}°N, {longitude:.6f}°E")

                    # Auto-generate and save sensors
                    sensors = create_sensors_for_equipment(equipment_type, marker_id, marker_id)
                    for sensor in sensors:
                        river_utils.save_sensor_to_db(cursor, sensor)
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


# =============================================================================
# LOAD FROM DATABASE OPERATOR
# =============================================================================

class BIM_OT_equipment_load_from_db(Operator):
    """Load equipment from database"""
    bl_idname = "bim.equipment_load_from_db"
    bl_label = "Load from Database"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        global PLACED_EQUIPMENT
        import sqlite3
        from . import river_utils

        db_path = river_utils.RIVER_DB_PATH

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
# SENSOR DASHBOARD OPERATOR (imported from equipment_sensor module)
# =============================================================================

# Note: The actual BIM_OT_equipment_view_sensor_dashboard is in equipment_sensor.py
# This is a placeholder reference for imports
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
        from . import river_utils

        # Close any existing dashboard instance first
        if BIM_OT_equipment_view_sensor_dashboard._active_instance is not None:
            old_instance = BIM_OT_equipment_view_sensor_dashboard._active_instance
            LOGGER.log("Closing previous dashboard instance...")
            old_instance.cleanup(context)
            BIM_OT_equipment_view_sensor_dashboard._active_instance = None

        LOGGER.section("SENSOR DASHBOARD OPENING (GPU OVERLAY)")

        # Database path
        db_path = river_utils.RIVER_DB_PATH
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
            self._global_alert_view = equipment_sensor.GlobalAlertView(str(db_path))
            self._filter_panel_ui = equipment_sensor.FilterPanelUI(self._global_alert_view)

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



# =============================================================================
# PROPERTIES VIEWER OPERATOR
# =============================================================================

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
        from . import river_utils

        layout = self.layout

        db_path = river_utils.RIVER_DB_PATH

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


# =============================================================================
# CLEAR ALL OPERATOR
# =============================================================================

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
            from . import equipment_gizmo

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
        from . import river_utils

        db_path = river_utils.RIVER_DB_PATH

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
