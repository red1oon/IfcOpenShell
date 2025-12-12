# Bonsai - OpenBIM Blender Add-on
# River Equipment Gizmo - Constant-size circles like Clash Gizmo

"""
Equipment Marker Gizmo System
==============================
GPU-drawn sphere gizmos with constant screen-space size.
Based on clash/gizmo.py implementation.
"""

import bpy
from bpy.types import Gizmo, GizmoGroup
from mathutils import Vector, Matrix
import math

# ============================================================================
# SPHERE GEOMETRY (Same as Clash Gizmo)
# ============================================================================

_SPHERE_CACHE = None

def generate_uv_sphere(rings=8, segments=12):
    """Generate triangle vertices for UV sphere"""
    verts = []

    for ring in range(rings):
        theta1 = (ring / rings) * math.pi
        theta2 = ((ring + 1) / rings) * math.pi

        for seg in range(segments):
            phi1 = (seg / segments) * 2 * math.pi
            phi2 = ((seg + 1) / segments) * 2 * math.pi

            # Calculate 4 vertices of quad on sphere surface
            v1 = (
                math.sin(theta1) * math.cos(phi1),
                math.sin(theta1) * math.sin(phi1),
                math.cos(theta1)
            )
            v2 = (
                math.sin(theta2) * math.cos(phi1),
                math.sin(theta2) * math.sin(phi1),
                math.cos(theta2)
            )
            v3 = (
                math.sin(theta2) * math.cos(phi2),
                math.sin(theta2) * math.sin(phi2),
                math.cos(theta2)
            )
            v4 = (
                math.sin(theta1) * math.cos(phi2),
                math.sin(theta1) * math.sin(phi2),
                math.cos(theta1)
            )

            # Two triangles per quad
            verts.extend([v1, v2, v3])  # Triangle 1
            verts.extend([v1, v3, v4])  # Triangle 2

    return verts

def get_sphere_geometry():
    """Get cached sphere geometry (lazy load)"""
    global _SPHERE_CACHE
    if _SPHERE_CACHE is None:
        _SPHERE_CACHE = generate_uv_sphere(rings=8, segments=12)
    return _SPHERE_CACHE


# ============================================================================
# EQUIPMENT COLORS
# ============================================================================

EQUIPMENT_COLORS = {
    'boom_trap': (1.0, 0.0, 0.0),      # Red
    'water_quality': (0.0, 0.5, 1.0),  # Blue
    'biodiversity': (0.0, 1.0, 0.0),   # Green
}


# ============================================================================
# EQUIPMENT MARKER GIZMO (Individual Sphere)
# ============================================================================

class EquipmentMarkerGizmo(Gizmo):
    """Single equipment marker - colored sphere with constant screen size"""

    bl_idname = "VIEW3D_GT_equipment_marker"
    bl_target_properties = ()

    # Custom properties
    equipment_type: str = "boom_trap"
    equipment_index: int = -1
    location: Vector = Vector((0, 0, 0))

    def setup(self):
        """Initialize gizmo"""
        if not hasattr(self, "custom_shape"):
            self.custom_shape = self.new_custom_shape('TRIS', get_sphere_geometry())

    def draw(self, context):
        """Draw the gizmo every frame"""
        if not hasattr(self, "custom_shape") or self.custom_shape is None:
            return

        # Set color based on equipment type
        color = EQUIPMENT_COLORS.get(self.equipment_type, (1.0, 1.0, 1.0))
        self.color = color
        self.color_highlight = (1.0, 1.0, 1.0)  # White on hover
        self.alpha = 1.0
        self.alpha_highlight = 1.0

        # Set scale for constant screen-space size
        self.scale_basis = 15.0  # Adjust for visibility
        self.use_draw_scale = True

        # Set position
        self.matrix_basis = Matrix.Translation(self.location)

        # Draw the sphere
        try:
            self.draw_custom_shape(self.custom_shape)
        except Exception as e:
            print(f"Failed to draw equipment gizmo: {e}")

    def draw_select(self, context, select_id):
        """Draw for selection (enables clicking)"""
        if not hasattr(self, "custom_shape") or self.custom_shape is None:
            return

        try:
            self.draw_custom_shape(self.custom_shape, select_id=select_id)
        except:
            pass

    def test_select(self, context, location):
        """Enable hover detection"""
        return -1  # Let Blender calculate distance

    def invoke(self, context, event):
        """Handle click on equipment marker"""
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            print(f"Clicked equipment {self.equipment_type} #{self.equipment_index}")
            # Future: Show properties popup
            return {'RUNNING_MODAL'}
        return {'PASS_THROUGH'}


# ============================================================================
# EQUIPMENT MARKER GIZMO GROUP (Manager)
# ============================================================================

class EquipmentMarkerGizmoGroup(GizmoGroup):
    """Manages all equipment marker gizmos"""

    bl_idname = "VIEW3D_GGT_equipment_markers"
    bl_label = "Equipment Markers"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT', 'SCALE'}

    @classmethod
    def poll(cls, context):
        """Only show in 3D view"""
        return context.area.type == 'VIEW_3D'

    def setup(self, context):
        """Initialize gizmo group"""
        print("Equipment Gizmo Group setup")
        self._last_count = 0  # Track equipment count for auto-refresh

    def draw_prepare(self, context):
        """Called every frame - check if we need to refresh"""
        from .equipment_config import PLACED_EQUIPMENT

        # Count current equipment
        current_count = sum(len(items) for items in PLACED_EQUIPMENT.values())

        # If count changed, refresh gizmos
        if current_count != self._last_count:
            print(f"Equipment count changed: {self._last_count} -> {current_count}, refreshing gizmos")
            self._last_count = current_count
            self.refresh_gizmos()

    def refresh_gizmos(self):
        """Refresh gizmos from placed equipment data"""
        from .equipment_config import PLACED_EQUIPMENT, EQUIPMENT_TYPES

        # Clear existing gizmos
        self.gizmos.clear()

        # Create gizmo for each placed equipment
        for equipment_type, items in PLACED_EQUIPMENT.items():
            for item in items:
                gz = self.gizmos.new(EquipmentMarkerGizmo.bl_idname)
                gz.equipment_type = equipment_type
                gz.equipment_index = item['number']
                gz.location = Vector((item['x'], item['y'], item['z']))
                gz.setup()

        print(f"Refreshed equipment gizmos: {len(self.gizmos)} total")


print("✓ Equipment Gizmo module loaded")
