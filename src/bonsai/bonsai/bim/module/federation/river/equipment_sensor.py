# Bonsai - OpenBIM Blender Add-on
# River Equipment Sensor Dashboard
# Extracted from river_equipment_placement.py for maintainability

"""
River Equipment Sensor Dashboard
=================================
Sensor status calculation, filtering, and visualization.
Extracted to separate module to keep main file manageable.
"""

import bpy
import blf
import gpu
from gpu_extras.batch import batch_for_shader
from pathlib import Path

# Will be imported from parent module
EQUIPMENT_TYPES = None
PLACED_EQUIPMENT = None
LOGGER = None
SENSOR_TYPE_COLORS = None


def init_module(equipment_types, placed_equipment, logger, sensor_type_colors):
    """Initialize module with shared data from parent"""
    global EQUIPMENT_TYPES, PLACED_EQUIPMENT, LOGGER, SENSOR_TYPE_COLORS
    EQUIPMENT_TYPES = equipment_types
    PLACED_EQUIPMENT = placed_equipment
    LOGGER = logger
    SENSOR_TYPE_COLORS = sensor_type_colors


# =============================================================================
# SENSOR DASHBOARD - HELPER CLASSES
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


