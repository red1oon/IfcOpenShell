"""
IoT Sensor Overlay - GPU-based 3D visualization layer
Animated sensor markers with real-time data display in Blender viewport

Features:
- Pulsing spheres for temperature sensors (heat ripple effect)
- Rotating cubes for pressure sensors (radiating waves)
- Animated arrows for flow sensors (directional particles)
- Cloud particles for air quality sensors
- Electric arcs for power sensors
- Urgent blink for alerts/faults
"""

import bpy
import gpu
import numpy as np
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, Matrix
from datetime import datetime
import math


class SensorVisualEffect:
    """Base class for sensor visual effects"""

    SENSOR_VISUAL_TYPES = {
        'Temperature': {
            'shape': 'pulsing_sphere',
            'particle_effect': 'heat_ripples',
            'color_gradient': 'blue_to_red',  # Heat spectrum
            'glow': True,
            'pulse_speed': 1.0,
        },
        'Pressure': {
            'shape': 'rotating_cube',
            'particle_effect': 'pressure_lines',
            'color': (0.3, 0.6, 1.0, 0.8),
            'rotation_speed': 0.5,
        },
        'Flow': {
            'shape': 'animated_arrow',
            'particle_effect': 'flowing_particles',
            'trail': True,
            'color': (0.0, 0.8, 0.8, 0.9),
        },
        'CO2': {
            'shape': 'cloud_particles',
            'transparency': 0.3,
            'color': (0.7, 0.7, 0.3, 0.3),
            'diffusion': True,
        },
        'Power': {
            'shape': 'electric_arc',
            'particle_effect': 'electric_sparks',
            'color': (1.0, 1.0, 0.0, 0.9),
            'intensity': 1.5,
        },
        'Alert': {
            'shape': 'warning_icon',
            'animation': 'urgent_blink',
            'color': (1.0, 0.0, 0.0, 1.0),
            'blink_speed': 3.0,
            'sound': True,
        }
    }

    def __init__(self, sensor_type, location, value, thresholds=None):
        self.sensor_type = sensor_type
        self.location = Vector(location)
        self.value = value
        self.thresholds = thresholds or {}
        self.config = self.SENSOR_VISUAL_TYPES.get(sensor_type, {})
        self.time_offset = np.random.random() * 2 * math.pi  # Random phase for animation

    def get_color(self, current_time):
        """Get animated color based on sensor type and value"""
        if self.sensor_type == 'Temperature':
            # Heat gradient: blue (cold) -> red (hot)
            if self.thresholds:
                min_val = self.thresholds.get('min', 15.0)
                max_val = self.thresholds.get('max', 35.0)
                norm = (self.value - min_val) / (max_val - min_val)
                norm = max(0.0, min(1.0, norm))  # Clamp 0-1

                # Blue -> Green -> Yellow -> Red gradient
                if norm < 0.5:
                    # Blue to green
                    r = 0.0
                    g = norm * 2.0
                    b = 1.0 - norm * 2.0
                else:
                    # Green to red
                    r = (norm - 0.5) * 2.0
                    g = 1.0 - (norm - 0.5) * 2.0
                    b = 0.0

                # Add pulsing effect
                pulse = math.sin(current_time * self.config.get('pulse_speed', 1.0) + self.time_offset) * 0.1 + 0.9
                return (r * pulse, g * pulse, b * pulse, 0.8)
            else:
                return (0.8, 0.4, 0.0, 0.8)  # Default orange

        elif self.sensor_type == 'Alert':
            # Urgent blinking red
            blink_speed = self.config.get('blink_speed', 3.0)
            intensity = (math.sin(current_time * blink_speed) + 1.0) / 2.0
            return (1.0, 0.0, 0.0, 0.5 + intensity * 0.5)

        else:
            # Default color from config
            return self.config.get('color', (1.0, 1.0, 1.0, 0.8))

    def get_size(self, current_time):
        """Get animated size/scale"""
        shape = self.config.get('shape', 'pulsing_sphere')

        if shape == 'pulsing_sphere':
            # Gentle breathing animation
            base_size = 0.15
            pulse = math.sin(current_time * 2.0 + self.time_offset) * 0.03
            return base_size + pulse

        elif shape == 'warning_icon':
            # Sharp pulsing for alerts
            pulse = (math.sin(current_time * 4.0 + self.time_offset) + 1.0) / 2.0
            return 0.2 + pulse * 0.1

        else:
            return 0.15

    def get_rotation(self, current_time):
        """Get rotation angle for rotating shapes"""
        if self.config.get('shape') == 'rotating_cube':
            speed = self.config.get('rotation_speed', 0.5)
            return current_time * speed + self.time_offset
        return 0.0


class IoTSensorOverlay:
    """
    GPU-based sensor overlay system for Blender viewport
    Draws animated markers for all sensors in real-time
    """

    def __init__(self):
        self.sensors = []  # List of SensorVisualEffect instances
        self.enabled = False
        self.draw_handler = None
        self.shader = None
        self.batch_sphere = None
        self.batch_cube = None

    def add_sensor(self, sensor_type, location, value, thresholds=None, metadata=None):
        """Add sensor to overlay"""
        effect = SensorVisualEffect(sensor_type, location, value, thresholds)
        if metadata:
            effect.metadata = metadata
        self.sensors.append(effect)

    def load_sensors_from_database(self, db_path, asset_guid=None):
        """Load sensors from Digital Twin database"""
        import sqlite3

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Query sensors with location from element_transforms via asset_guid
        # Note: sensors table doesn't have location columns - we get it from the asset's transform
        if asset_guid:
            query = """
            SELECT
                s.sensor_id,
                s.sensor_type,
                COALESCE(t.center_x, 0.0) as location_x,
                COALESCE(t.center_y, 0.0) as location_y,
                COALESCE(t.center_z, 0.0) as location_z,
                sr.value,
                s.min_threshold,
                s.max_threshold,
                m.element_name as asset_name
            FROM sensors s
            LEFT JOIN element_transforms t ON s.asset_guid = t.guid
            LEFT JOIN elements_meta m ON s.asset_guid = m.guid
            LEFT JOIN (
                SELECT sensor_id, value
                FROM sensor_readings
                WHERE id IN (
                    SELECT MAX(id) FROM sensor_readings GROUP BY sensor_id
                )
            ) sr ON s.sensor_id = sr.sensor_id
            WHERE s.asset_guid = ? AND s.is_active = 1
            """
            cursor.execute(query, (asset_guid,))
        else:
            query = """
            SELECT
                s.sensor_id,
                s.sensor_type,
                COALESCE(t.center_x, 0.0) as location_x,
                COALESCE(t.center_y, 0.0) as location_y,
                COALESCE(t.center_z, 0.0) as location_z,
                sr.value,
                s.min_threshold,
                s.max_threshold,
                m.element_name as asset_name
            FROM sensors s
            LEFT JOIN element_transforms t ON s.asset_guid = t.guid
            LEFT JOIN elements_meta m ON s.asset_guid = m.guid
            LEFT JOIN (
                SELECT sensor_id, value
                FROM sensor_readings
                WHERE id IN (
                    SELECT MAX(id) FROM sensor_readings GROUP BY sensor_id
                )
            ) sr ON s.sensor_id = sr.sensor_id
            WHERE s.is_active = 1
            """
            cursor.execute(query)

        for row in cursor.fetchall():
            sensor_id, sensor_type, x, y, z, value, thresh_min, thresh_max, asset_name = row

            thresholds = {}
            if thresh_min is not None:
                thresholds['min'] = thresh_min
            if thresh_max is not None:
                thresholds['max'] = thresh_max

            metadata = {
                'sensor_id': sensor_id,
                'asset_name': asset_name or 'Unknown',
            }

            self.add_sensor(sensor_type, (x, y, z), value or 0.0, thresholds, metadata)

        conn.close()
        print(f"[IoT Overlay] Loaded {len(self.sensors)} sensors from database")

    def create_sphere_batch(self):
        """Create GPU batch for sphere geometry"""
        # Icosphere approximation (12 vertices)
        phi = (1.0 + math.sqrt(5.0)) / 2.0  # Golden ratio
        vertices = [
            (-1, phi, 0), (1, phi, 0), (-1, -phi, 0), (1, -phi, 0),
            (0, -1, phi), (0, 1, phi), (0, -1, -phi), (0, 1, -phi),
            (phi, 0, -1), (phi, 0, 1), (-phi, 0, -1), (-phi, 0, 1)
        ]

        # Normalize
        vertices = [Vector(v).normalized() for v in vertices]

        # Triangles (20 faces of icosahedron)
        indices = [
            (0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11),
            (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
            (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9),
            (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)
        ]

        return vertices, indices

    def create_cube_batch(self):
        """Create GPU batch for cube geometry"""
        # 8 vertices of unit cube
        vertices = [
            Vector((-1, -1, -1)), Vector((1, -1, -1)), Vector((1, 1, -1)), Vector((-1, 1, -1)),
            Vector((-1, -1, 1)), Vector((1, -1, 1)), Vector((1, 1, 1)), Vector((-1, 1, 1))
        ]

        # 12 triangles (6 faces × 2 triangles)
        indices = [
            (0, 1, 2), (0, 2, 3),  # Front
            (4, 6, 5), (4, 7, 6),  # Back
            (0, 4, 5), (0, 5, 1),  # Bottom
            (2, 6, 7), (2, 7, 3),  # Top
            (0, 3, 7), (0, 7, 4),  # Left
            (1, 5, 6), (1, 6, 2),  # Right
        ]

        return vertices, indices

    def draw_callback(self):
        """GPU draw callback - renders all sensor markers"""
        if not self.enabled or not self.sensors:
            return

        # Debug: Print once every 60 frames to avoid spam
        if not hasattr(self, '_frame_count'):
            self._frame_count = 0
            print(f"[IoT Overlay] draw_callback() called! Rendering {len(self.sensors)} sensors")
        self._frame_count = (self._frame_count + 1) % 60

        # Get current time for animations
        current_time = bpy.context.scene.frame_current / bpy.context.scene.render.fps

        # Setup GPU state
        gpu.state.blend_set('ALPHA')
        gpu.state.depth_test_set('LESS_EQUAL')

        # Get viewport matrix
        region = bpy.context.region
        rv3d = bpy.context.region_data
        view_matrix = rv3d.view_matrix
        projection_matrix = rv3d.window_matrix

        # Create shader if needed
        if not self.shader:
            vertex_shader = '''
                uniform mat4 viewMatrix;
                uniform mat4 projectionMatrix;
                uniform mat4 modelMatrix;

                in vec3 position;

                void main() {
                    gl_Position = projectionMatrix * viewMatrix * modelMatrix * vec4(position, 1.0);
                }
            '''

            fragment_shader = '''
                uniform vec4 color;
                out vec4 fragColor;

                void main() {
                    fragColor = color;
                }
            '''

            self.shader = gpu.types.GPUShader(vertex_shader, fragment_shader)

        # Prepare geometry
        if not self.batch_sphere:
            sphere_verts, sphere_indices = self.create_sphere_batch()
            self.batch_sphere = batch_for_shader(
                self.shader, 'TRIS',
                {"position": [v[:] for v in sphere_verts]},
                indices=sphere_indices
            )

        if not self.batch_cube:
            cube_verts, cube_indices = self.create_cube_batch()
            self.batch_cube = batch_for_shader(
                self.shader, 'TRIS',
                {"position": [v[:] for v in cube_verts]},
                indices=cube_indices
            )

        # Draw each sensor
        self.shader.bind()

        for sensor in self.sensors:
            # Get animated properties
            color = sensor.get_color(current_time)
            size = sensor.get_size(current_time)
            rotation = sensor.get_rotation(current_time)

            # Create model matrix (translate + rotate + scale)
            mat_loc = Matrix.Translation(sensor.location)
            mat_rot = Matrix.Rotation(rotation, 4, 'Z')
            mat_scale = Matrix.Scale(size, 4)
            model_matrix = mat_loc @ mat_rot @ mat_scale

            # Set uniforms
            self.shader.uniform_float("viewMatrix", view_matrix)
            self.shader.uniform_float("projectionMatrix", projection_matrix)
            self.shader.uniform_float("modelMatrix", model_matrix)
            self.shader.uniform_float("color", color)

            # Select geometry batch
            shape = sensor.config.get('shape', 'pulsing_sphere')
            if 'cube' in shape:
                batch = self.batch_cube
            else:
                batch = self.batch_sphere

            # Draw
            batch.draw(self.shader)

        # Restore GPU state
        gpu.state.blend_set('NONE')

    def enable(self, context):
        """Enable overlay drawing"""
        if not self.enabled:
            # Create Empty objects for each sensor (for Outliner/selection)
            self.create_sensor_empties(context)

            # Store draw handler reference
            self.draw_handler = bpy.types.SpaceView3D.draw_handler_add(
                self.draw_callback, (), 'WINDOW', 'POST_VIEW'
            )
            self.enabled = True
            print(f"[IoT Overlay] Enabled - showing {len(self.sensors)} sensors")
            print(f"[IoT Overlay] Draw handler: {self.draw_handler}")
            print(f"[IoT Overlay] Created {len(self.sensors)} Empty objects")

            # Force viewport refresh
            if hasattr(context, 'screen') and context.screen:
                for area in context.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()
                        print(f"[IoT Overlay] Tagged VIEW_3D area for redraw")

            # Also tag all regions
            for window in context.window_manager.windows:
                for area in window.screen.areas:
                    if area.type == 'VIEW_3D':
                        for region in area.regions:
                            region.tag_redraw()

    def create_sensor_empties(self, context):
        """Create Empty objects for sensors (for Outliner + selection)"""
        # Get or create IoT Sensors collection
        if "IoT Sensors" not in bpy.data.collections:
            col = bpy.data.collections.new("IoT Sensors")
            context.scene.collection.children.link(col)
            print("[IoT Overlay] Created 'IoT Sensors' collection")
        else:
            col = bpy.data.collections["IoT Sensors"]

        # Create Empty for each sensor
        self.sensor_empties = []
        for sensor in self.sensors:
            # Create Empty object
            empty = bpy.data.objects.new(f"IoT_{sensor.sensor_type}_{sensor.metadata.get('sensor_id', 'unknown')[:8]}", None)
            empty.location = sensor.location

            # Visual style
            empty.empty_display_type = 'SPHERE'
            empty.empty_display_size = 0.15
            empty.show_name = True
            empty.hide_render = True  # Don't render these

            # Custom properties (for properties panel)
            empty["is_iot_sensor"] = True
            empty["sensor_id"] = sensor.metadata.get('sensor_id', 'unknown')
            empty["sensor_type"] = sensor.sensor_type
            empty["current_value"] = sensor.value
            empty["asset_name"] = sensor.metadata.get('asset_name', 'Unknown')

            if sensor.thresholds:
                empty["threshold_min"] = sensor.thresholds.get('min', 0)
                empty["threshold_max"] = sensor.thresholds.get('max', 100)

            # Add to collection
            col.objects.link(empty)
            self.sensor_empties.append(empty)

        print(f"[IoT Overlay] Created {len(self.sensor_empties)} sensor Empty objects")

    def disable(self, context):
        """Disable overlay drawing"""
        if self.enabled and self.draw_handler:
            bpy.types.SpaceView3D.draw_handler_remove(self.draw_handler, 'WINDOW')
            self.draw_handler = None
            self.enabled = False
            print("[IoT Overlay] Disabled")

            # Remove sensor Empty objects
            self.remove_sensor_empties(context)

            # Refresh viewport
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()

    def remove_sensor_empties(self, context):
        """Remove sensor Empty objects"""
        if hasattr(self, 'sensor_empties'):
            for empty in self.sensor_empties:
                if empty and empty.name in bpy.data.objects:
                    bpy.data.objects.remove(empty, do_unlink=True)
            self.sensor_empties.clear()
            print(f"[IoT Overlay] Removed sensor Empty objects")

        # Remove collection if empty
        if "IoT Sensors" in bpy.data.collections:
            col = bpy.data.collections["IoT Sensors"]
            if len(col.objects) == 0:
                bpy.data.collections.remove(col)
                print("[IoT Overlay] Removed empty 'IoT Sensors' collection")

    def clear(self):
        """Clear all sensors"""
        self.sensors.clear()
        if hasattr(self, 'sensor_empties'):
            self.sensor_empties.clear()


# Global instance
_sensor_overlay = None

def get_sensor_overlay():
    """Get global sensor overlay instance"""
    global _sensor_overlay
    if _sensor_overlay is None:
        _sensor_overlay = IoTSensorOverlay()
    return _sensor_overlay


# =========================================================================
# BLENDER OPERATORS
# =========================================================================

class BIM_OT_iot_enable_sensor_overlay(bpy.types.Operator):
    """Enable IoT sensor visualization overlay in 3D viewport"""
    bl_idname = "bim.iot_enable_sensor_overlay"
    bl_label = "Enable IoT Sensors"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        # Check if database exists
        from pathlib import Path
        work_dir = Path.home() / 'Projects' / 'IfcOpenShell' / 'WORK_DIR' / 'databases'
        db = work_dir / 'enhanced_federation.db'
        return db.exists() or (hasattr(context.scene, 'BIMFederationProperties') and
                               context.scene.BIMFederationProperties.federation_database_path)

    def execute(self, context):
        try:
            # Get database path
            from pathlib import Path
            import os

            db_path = None
            if hasattr(context.scene, 'BIMFederationProperties'):
                db_path = bpy.path.abspath(context.scene.BIMFederationProperties.federation_database_path)
                if not os.path.exists(db_path):
                    db_path = None

            if not db_path:
                work_dir = Path.home() / 'Projects' / 'IfcOpenShell' / 'WORK_DIR' / 'databases'
                db_path = str(work_dir / 'enhanced_federation.db')

            if not os.path.exists(db_path):
                self.report({'ERROR'}, f"Database not found: {db_path}")
                return {'CANCELLED'}

            # Get overlay
            overlay = get_sensor_overlay()

            # Clear and reload sensors
            overlay.clear()
            overlay.load_sensors_from_database(db_path)

            # Enable overlay
            overlay.enable(context)

            self.report({'INFO'}, f"IoT Overlay enabled - {len(overlay.sensors)} sensors")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to enable overlay: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}


class BIM_OT_iot_disable_sensor_overlay(bpy.types.Operator):
    """Disable IoT sensor visualization overlay"""
    bl_idname = "bim.iot_disable_sensor_overlay"
    bl_label = "Disable IoT Sensors"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        overlay = get_sensor_overlay()
        overlay.disable(context)
        self.report({'INFO'}, "IoT Overlay disabled")
        return {'FINISHED'}


# Registration
classes = (
    BIM_OT_iot_enable_sensor_overlay,
    BIM_OT_iot_disable_sensor_overlay,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
