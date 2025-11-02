"""
Blender gizmo-based interactive clash markers

Replaces GPU overlays with native Blender gizmos - clickable, colored spheres
that appear at clash locations. Right-click to change status, left-click to jump.
"""

import bpy
from bpy.types import Gizmo, GizmoGroup, Operator, Menu
from mathutils import Vector
from typing import List, Dict, Optional, Tuple
from . import database as db
import sqlite3
from pathlib import Path
import logging
from datetime import datetime

# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_gizmo_logging():
    """Setup dual logging to bonsai.log and ERROR.log"""
    logger = logging.getLogger('bonsai.clash.gizmo')
    logger.setLevel(logging.DEBUG)

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    # Handler 1: bonsai.log (all messages)
    bonsai_log = Path.home() / "Documents/bonsai/bonsai.log"
    bonsai_log.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(bonsai_log)
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(asctime)s [%(name)s] %(levelname)s: %(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Handler 2: ERROR.log (errors only)
    error_log = Path.home() / "Documents/bonsai/ERROR.log"

    error_handler = logging.FileHandler(error_log)
    error_handler.setLevel(logging.ERROR)
    error_formatter = logging.Formatter('%(asctime)s [%(name)s] ERROR: %(message)s\n%(pathname)s:%(lineno)d\n')
    error_handler.setFormatter(error_formatter)
    logger.addHandler(error_handler)

    return logger

logger = setup_gizmo_logging()


# ============================================================================
# FEDERATION DATABASE QUERIES (Lazy loading from federation_index.db)
# ============================================================================

def get_element_bbox_center(guid: str, db_path: str) -> Optional[Vector]:
    """Query federation database for element bbox center coordinates

    Args:
        guid: Element GUID to lookup
        db_path: Path to federation_index.db

    Returns:
        Vector with (x, y, z) IFC world coordinates, or None if not found
    """
    if not db_path or not Path(db_path).exists():
        logger.warning(f"Federation DB not found: {db_path}")
        return None

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Query bbox from elements_rtree (joined with elements_meta for GUID lookup)
        cursor.execute("""
            SELECT r.minX, r.minY, r.minZ, r.maxX, r.maxY, r.maxZ
            FROM elements_meta m
            JOIN elements_rtree r ON m.id = r.id
            WHERE m.guid = ?
        """, (guid,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            logger.debug(f"Element not found in federation DB: {guid}")
            return None

        # Calculate bbox center from min/max
        min_x, min_y, min_z, max_x, max_y, max_z = row
        center = Vector((
            (min_x + max_x) / 2,
            (min_y + max_y) / 2,
            (min_z + max_z) / 2
        ))

        logger.debug(f"Queried bbox for {guid}: {center}")
        return center

    except sqlite3.Error as e:
        logger.error(f"DB query error for GUID {guid}: {e}")
        print(f"  ⚠️  DB query error for GUID {guid}: {e}")
        return None


def get_clash_bbox_centers(guid_a: str, guid_b: str, db_path: str) -> Tuple[Optional[Vector], Optional[Vector]]:
    """Query federation database for both elements in a clash

    Args:
        guid_a: First element GUID
        guid_b: Second element GUID
        db_path: Path to federation_index.db

    Returns:
        Tuple of (center_a, center_b), either may be None if not found
    """
    center_a = get_element_bbox_center(guid_a, db_path)
    center_b = get_element_bbox_center(guid_b, db_path)
    return (center_a, center_b)


# ============================================================================
# COORDINATE CONVERSION (reused from visualization.py)
# ============================================================================

# Global flag to prevent spam warnings about missing offset
_offset_warning_shown = False

def get_model_offset() -> Vector:
    """Get model offset to convert IFC coords to Blender coords

    Uses cached offset from MEP routing if available, otherwise falls back
    to Bonsai georeference properties.
    """
    global _offset_warning_shown

    # Try MEP cached offset first (most reliable)
    cached = bpy.context.scene.get("MEP_cached_offset")
    if cached:
        logger.debug(f"Using cached MEP offset: {cached}")
        return Vector(cached)

    # Fallback to georeference properties
    try:
        props = bpy.context.scene.BIMGeoreferenceProperties
        offset = Vector((
            props.model_offset_x or 0.0,
            props.model_offset_y or 0.0,
            props.model_offset_z or 0.0
        ))
        # Check if offset is actually set (not all zeros)
        if offset.length > 0.01:
            logger.info(f"Using georeference offset: {offset}")
            return offset
    except Exception as e:
        logger.debug(f"BIMGeoreferenceProperties not available: {e}")

    # No offset available - warn once and assume zero
    if not _offset_warning_shown:
        logger.warning("No offset available - using IFC world coordinates (gizmos may be positioned incorrectly)")
        print(f"  ⚠️  Gizmo: No offset available, using IFC world coordinates")
        _offset_warning_shown = True

    return Vector((0, 0, 0))


def ifc_to_blender_coords(ifc_coords: tuple) -> Vector:
    """Convert IFC world coordinates to Blender scene coordinates"""
    offset = get_model_offset()
    return Vector((
        ifc_coords[0] - offset.x,
        ifc_coords[1] - offset.y,
        ifc_coords[2] - offset.z
    ))


# ============================================================================
# STATUS COLOR MAPPING
# ============================================================================

STATUS_COLORS = {
    'NEW': (1.0, 0.0, 0.0),       # Red - requires attention
    'ACTIVE': (1.0, 0.5, 0.0),    # Orange - being reviewed
    'REVIEWED': (1.0, 1.0, 0.0),  # Yellow - reviewed, awaiting fix
    'RESOLVED': (0.0, 1.0, 0.0),  # Green - fixed/approved
}

def get_clash_color(status: str) -> tuple:
    """Get RGB color for clash status"""
    return STATUS_COLORS.get(status, (1.0, 0.0, 0.0))  # Default red


# ============================================================================
# CLASH STATUS OPERATORS
# ============================================================================

class BIM_OT_change_clash_status(Operator):
    """Change clash status and update gizmo color"""
    bl_idname = "bim.change_clash_status"
    bl_label = "Change Clash Status"
    bl_options = {'INTERNAL'}

    clash_index: bpy.props.IntProperty()
    guid_a: bpy.props.StringProperty()
    guid_b: bpy.props.StringProperty()
    new_status: bpy.props.StringProperty()

    def execute(self, context):
        # Update database
        db.set_clash_status(
            self.guid_a,
            self.guid_b,
            status=self.new_status
        )

        # Refresh gizmos to update colors
        refresh_clash_gizmos(context)

        status_emoji = {
            'NEW': '🔴',
            'ACTIVE': '🟠',
            'REVIEWED': '🟡',
            'RESOLVED': '✅'
        }.get(self.new_status, '⚪')

        self.report({'INFO'}, f"{status_emoji} Clash {self.clash_index + 1} → {self.new_status}")
        print(f"\n{status_emoji} Clash {self.clash_index + 1} status changed to {self.new_status}")

        return {'FINISHED'}


class BIM_OT_navigate_clash(Operator):
    """Navigate to previous/next clash"""
    bl_idname = "bim.navigate_clash"
    bl_label = "Navigate Clash"
    bl_options = {'INTERNAL'}

    direction: bpy.props.EnumProperty(
        items=[('PREV', 'Previous', ''), ('NEXT', 'Next', '')]
    )
    current_index: bpy.props.IntProperty()

    def execute(self, context):
        props = context.scene.BIMClashProperties

        # Get all selected clash indices
        selected_indices = [
            i for i, candidate in enumerate(props.discipline_clash_candidates)
            if candidate.selected
        ]

        if not selected_indices:
            self.report({'WARNING'}, "No clashes selected")
            return {'CANCELLED'}

        # Find current position in selected list
        try:
            current_pos = selected_indices.index(self.current_index)
        except ValueError:
            # Current clash not in selected list, go to first
            current_pos = 0

        # Navigate
        if self.direction == 'PREV':
            new_pos = (current_pos - 1) % len(selected_indices)
        else:  # NEXT
            new_pos = (current_pos + 1) % len(selected_indices)

        new_index = selected_indices[new_pos]

        # Jump to clash
        props.current_clash_index = new_index
        bpy.ops.bim.select_discipline_clash(clash_index=new_index)

        self.report({'INFO'}, f"Clash {new_index + 1}/{len(props.discipline_clash_candidates)}")
        print(f"  ➡️  Navigated to clash {new_index + 1}")

        return {'FINISHED'}


class BIM_MT_clash_gizmo_context_menu(Menu):
    """Context menu for clash gizmo"""
    bl_idname = "BIM_MT_clash_gizmo_context_menu"
    bl_label = "Clash Actions"

    def draw(self, context):
        logger.info("📋 Context menu draw() called")
        print(f"\n📋 CONTEXT MENU DRAWING...")

        layout = self.layout

        # Get clash data from scene temporary storage
        clash_index = context.scene.get("_temp_clash_index", 0)
        guid_a = context.scene.get("_temp_clash_guid_a", "")
        guid_b = context.scene.get("_temp_clash_guid_b", "")
        current_status = context.scene.get("_temp_clash_status", "NEW")

        print(f"   Clash data: index={clash_index}, status={current_status}")
        print(f"   GUID A: {guid_a[:16] if guid_a else 'None'}...")
        logger.info(f"  Menu data: clash_index={clash_index}, status={current_status}")

        # Status section
        layout.label(text=f"Current: {current_status}", icon='INFO')
        layout.separator()

        # Status change options
        layout.label(text="Change Status:", icon='DECORATE')

        for status, (icon, label) in [
            ('NEW', ('ERROR', '🔴 New')),
            ('ACTIVE', ('FUND', '🟠 Active')),
            ('REVIEWED', ('SEQUENCE_COLOR_04', '🟡 Reviewed')),
            ('RESOLVED', ('CHECKMARK', '✅ Resolved'))
        ]:
            if status != current_status:
                op = layout.operator(
                    "bim.change_clash_status",
                    text=label,
                    icon=icon
                )
                op.clash_index = clash_index
                op.guid_a = guid_a
                op.guid_b = guid_b
                op.new_status = status

        layout.separator()

        # Navigation
        layout.label(text="Navigate:", icon='RESTRICT_SELECT_OFF')

        op = layout.operator("bim.navigate_clash", text="⬅️ Previous", icon='TRIA_LEFT')
        op.direction = 'PREV'
        op.current_index = clash_index

        op = layout.operator("bim.navigate_clash", text="➡️ Next", icon='TRIA_RIGHT')
        op.direction = 'NEXT'
        op.current_index = clash_index

        layout.separator()

        # Info
        layout.label(text=f"Clash #{clash_index + 1}", icon='OUTLINER_OB_LIGHT')


# ============================================================================
# SIMPLE SPHERE GEOMETRY (3 orthogonal discs for 3D appearance)
# ============================================================================

# Create a proper 3D UV sphere with triangulated surface
import math

def generate_uv_sphere(rings=8, segments=12):
    """Generate triangle vertices for a proper 3D UV sphere"""
    verts = []

    # Generate sphere using UV coordinates
    for ring in range(rings):
        theta1 = (ring / rings) * math.pi
        theta2 = ((ring + 1) / rings) * math.pi

        for seg in range(segments):
            phi1 = (seg / segments) * 2 * math.pi
            phi2 = ((seg + 1) / segments) * 2 * math.pi

            # Calculate 4 vertices of quad on sphere surface
            # Convert spherical to cartesian: (r, theta, phi) -> (x, y, z)
            v1 = (
                math.sin(theta1) * math.cos(phi1),
                math.sin(theta1) * math.sin(phi1),
                math.cos(theta1)
            )
            v2 = (
                math.sin(theta1) * math.cos(phi2),
                math.sin(theta1) * math.sin(phi2),
                math.cos(theta1)
            )
            v3 = (
                math.sin(theta2) * math.cos(phi2),
                math.sin(theta2) * math.sin(phi2),
                math.cos(theta2)
            )
            v4 = (
                math.sin(theta2) * math.cos(phi1),
                math.sin(theta2) * math.sin(phi1),
                math.cos(theta2)
            )

            # Create 2 triangles from quad (proper 3D surface)
            verts.extend([v1, v2, v3])  # First triangle
            verts.extend([v1, v3, v4])  # Second triangle

    return verts

# Lazy-loaded sphere geometry (only generated when first needed)
_SPHERE_SIMPLE_CACHE = None

def get_sphere_geometry():
    """Get sphere geometry (lazy loaded on first use)"""
    global _SPHERE_SIMPLE_CACHE
    if _SPHERE_SIMPLE_CACHE is None:
        # 8 rings × 12 segments = 192 triangles (smooth 3D sphere)
        _SPHERE_SIMPLE_CACHE = generate_uv_sphere(rings=8, segments=12)
    return _SPHERE_SIMPLE_CACHE


# ============================================================================
# CLASH MARKER GIZMO (Individual Sphere)
# ============================================================================

class ClashMarkerGizmo(Gizmo):
    """Single clash marker - colored sphere in 3D space"""

    bl_idname = "VIEW3D_GT_clash_marker"

    # Custom properties for this gizmo instance
    clash_id: str = None
    clash_index: int = -1
    guid_a: str = None
    guid_b: str = None
    status: str = "NEW"

    def setup(self):
        """Initialize gizmo (called once when created)"""
        logger.info(f"🎯 Gizmo setup called for clash {self.clash_index}")
        print(f"🎯 GIZMO SETUP: clash_index={self.clash_index}, guid_a={self.guid_a[:8] if self.guid_a else 'None'}...")

        # Use simple 3-circle sphere shape (lightweight, lazy loaded)
        if not hasattr(self, "custom_shape"):
            self.custom_shape = self.new_custom_shape('TRIS', get_sphere_geometry())
            logger.debug(f"  Created custom shape for gizmo {self.clash_index}")

    def draw(self, context):
        """Draw the gizmo (called every frame)"""
        # Set color based on status
        color = get_clash_color(self.status)
        self.color = color
        self.color_highlight = (1.0, 1.0, 1.0)  # White when hovered
        self.alpha = 0.8
        self.alpha_highlight = 1.0

        # Draw sphere at matrix_basis position
        # (matrix_basis is set by GizmoGroup.refresh)

    def invoke(self, context, event):
        """Handle user interaction with gizmo"""
        logger.info(f"🖱️  GIZMO INVOKE: event.type={event.type}, event.value={event.value}, clash_index={self.clash_index}")
        print(f"\n🖱️  GIZMO CLICKED!")
        print(f"   Event type: {event.type}")
        print(f"   Event value: {event.value}")
        print(f"   Clash index: {self.clash_index}")
        print(f"   GUID A: {self.guid_a}")
        print(f"   GUID B: {self.guid_b}")
        print(f"   Status: {self.status}")

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            # Left-click: Jump to clash
            print(f"   ➡️  Left-click detected - jumping to clash")
            logger.info(f"  Left-click on clash {self.clash_index} - jumping")
            self.jump_to_clash(context)
            return {'RUNNING_MODAL'}

        elif event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            # Right-click: Show context menu
            print(f"   ➡️  Right-click detected - opening context menu")
            logger.info(f"  Right-click on clash {self.clash_index} - opening menu")

            # Store clash data in scene for menu access
            context.scene["_temp_clash_index"] = self.clash_index
            context.scene["_temp_clash_guid_a"] = self.guid_a
            context.scene["_temp_clash_guid_b"] = self.guid_b
            context.scene["_temp_clash_status"] = self.status

            print(f"   ➡️  Stored clash data in scene, calling menu...")

            # Show context menu
            try:
                bpy.ops.wm.call_menu(name=BIM_MT_clash_gizmo_context_menu.bl_idname)
                print(f"   ✓ Context menu called successfully")
            except Exception as e:
                print(f"   ✗ ERROR calling context menu: {e}")
                logger.error(f"  Failed to call context menu: {e}")

            return {'RUNNING_MODAL'}

        else:
            print(f"   ⚠️  Event not handled: {event.type} {event.value}")
            return {'PASS_THROUGH'}

    def jump_to_clash(self, context):
        """Jump viewport to this clash (reuse existing operator)"""
        props = context.scene.BIMClashProperties

        # Set current clash index
        if self.clash_index >= 0 and self.clash_index < len(props.discipline_clash_candidates):
            props.current_clash_index = self.clash_index

            # Call existing select operator
            bpy.ops.bim.select_discipline_clash(clash_index=self.clash_index)

            print(f"✓ Jumped to clash {self.clash_index + 1}")

    def test_select(self, context, location):
        """Enable hover detection"""
        logger.debug(f"🎯 test_select called for clash {self.clash_index}, location={location}")
        # Return distance from mouse to gizmo (for hit testing)
        # Blender handles this automatically for standard shapes
        # Return -1 to let Blender calculate distance
        return -1


# ============================================================================
# CLASH MARKER GIZMO GROUP (Manager)
# ============================================================================

class ClashMarkerGizmoGroup(GizmoGroup):
    """Manages all clash marker gizmos in viewport"""

    bl_idname = "VIEW3D_GGT_clash_markers"
    bl_label = "Clash Markers"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'PERSISTENT', '3D', 'DEPTH_3D'}

    @classmethod
    def poll(cls, context):
        """Only show in 3D viewport when gizmo visualization is enabled"""
        if context.area.type != 'VIEW_3D':
            return False

        # Only activate gizmos when explicitly enabled by user
        props = context.scene.BIMClashProperties
        return props.gizmo_visualization_enabled

    def setup(self, context):
        """Initialize gizmo group (called once)"""
        logger.info("🎯 ClashMarkerGizmoGroup.setup() called")
        print("🎯 Clash marker gizmo group setup")
        print(f"   Context: {context}")
        print(f"   Area type: {context.area.type if context.area else 'None'}")
        # Gizmos will be created in refresh()

    def refresh(self, context):
        """Update gizmos from clash data (called when data changes)"""
        props = context.scene.BIMClashProperties

        # Clear existing gizmos
        self.gizmos.clear()

        # Check if we have clash data
        if not props.discipline_clash_candidates:
            logger.info("No clash candidates to visualize")
            print("  ⚠️  No clash candidates to visualize")
            return

        # Filter to only selected clashes (user must select which ones to visualize)
        selected_candidates = [
            (i, candidate) for i, candidate in enumerate(props.discipline_clash_candidates)
            if candidate.selected
        ]

        if not selected_candidates:
            logger.info("No clashes selected for visualization")
            print("  ⚠️  No clashes selected for visualization")
            return

        logger.info(f"Creating gizmos for {len(selected_candidates)} selected clashes (out of {len(props.discipline_clash_candidates)} total)")
        print(f"  🔄 Creating gizmos for {len(selected_candidates)} selected clashes (out of {len(props.discipline_clash_candidates)} total)")

        # Get federation DB path
        db_path = props.bbox_database_path
        if not db_path:
            print("  ⚠️  No federation database path set - cannot query bbox coords")
            return

        # Create one gizmo per selected clash
        for i, candidate in selected_candidates:
            # Query federation DB for bbox centers (lazy loading)
            center_a, center_b = get_clash_bbox_centers(
                candidate.guid_a,
                candidate.guid_b,
                db_path
            )

            if not center_a or not center_b:
                print(f"  ⚠️  Skipping clash {i}: bbox not found in DB")
                continue

            # Convert to Blender coords
            blender_a = ifc_to_blender_coords(center_a)
            blender_b = ifc_to_blender_coords(center_b)
            midpoint = (blender_a + blender_b) / 2

            # DIAGNOSTIC: Log coordinate conversion for first gizmo
            if len(self.gizmos) == 0:
                offset = get_model_offset()
                logger.info(f"First gizmo coordinate check:")
                logger.info(f"  IFC coords A: {center_a}")
                logger.info(f"  IFC coords B: {center_b}")
                logger.info(f"  Model offset: {offset}")
                logger.info(f"  Blender A: {blender_a}")
                logger.info(f"  Blender B: {blender_b}")
                logger.info(f"  Midpoint: {midpoint}")
                logger.info(f"  Gizmo scale: 0.5m diameter")
                print(f"\n  📍 First gizmo diagnostic:")
                print(f"     IFC A: ({center_a.x:.2f}, {center_a.y:.2f}, {center_a.z:.2f})")
                print(f"     IFC B: ({center_b.x:.2f}, {center_b.y:.2f}, {center_b.z:.2f})")
                print(f"     Offset: ({offset.x:.2f}, {offset.y:.2f}, {offset.z:.2f})")
                print(f"     Blender midpoint: ({midpoint.x:.2f}, {midpoint.y:.2f}, {midpoint.z:.2f})")
                print(f"     Scale: 0.5m diameter sphere")

            # Get clash ID and status from database
            clash_id = db.get_clash_id(candidate.guid_a, candidate.guid_b)
            db_status = db.get_clash_status(candidate.guid_a, candidate.guid_b)

            if db_status:
                status = db_status['status']
            else:
                # New clash - default to NEW
                status = 'NEW'
                # Insert into database
                db.set_clash_status(
                    candidate.guid_a,
                    candidate.guid_b,
                    status='NEW',
                    distance=candidate.distance,
                    ifc_class_a=candidate.ifc_class_a,
                    ifc_class_b=candidate.ifc_class_b
                )

            # Create gizmo
            gz = self.gizmos.new(ClashMarkerGizmo.bl_idname)

            # Set gizmo position (world space)
            from mathutils import Matrix
            gz.matrix_basis = Matrix.Translation(midpoint)

            # Set gizmo scale (real-world size: 0.5m diameter sphere)
            gz.scale_basis = 0.5

            # Store clash data in gizmo
            gz.clash_id = clash_id
            gz.clash_index = i
            gz.guid_a = candidate.guid_a
            gz.guid_b = candidate.guid_b
            gz.status = status

            # Enable interaction
            gz.use_draw_modal = True
            gz.use_event_handle_all = True
            gz.use_select_background = True  # Allow selection even if behind other objects

            logger.info(f"  Created gizmo {len(self.gizmos)}: clash_index={i}, status={status}, use_draw_modal={gz.use_draw_modal}")
            print(f"    Gizmo {len(self.gizmos)}: clash_index={i}, status={status}, interactive={gz.use_draw_modal}")

        print(f"  ✓ Created {len(self.gizmos)} clash marker gizmos from {len(selected_candidates)} selected clashes")
        logger.info(f"✓ Refresh complete: {len(self.gizmos)} gizmos created")


# ============================================================================
# GIZMO GROUP MANAGEMENT
# ============================================================================

_gizmo_group_registered = False

def enable_clash_gizmos(context):
    """Enable clash marker gizmos in viewport"""
    global _gizmo_group_registered

    if _gizmo_group_registered:
        print("  ⚠️  Gizmos already enabled")
        # Just refresh to update positions
        refresh_clash_gizmos(context)
        return

    # Gizmo groups are automatically enabled when registered
    # Just trigger a refresh to create gizmos
    _gizmo_group_registered = True
    refresh_clash_gizmos(context)

    print("✓ Clash marker gizmos enabled")

    # Force viewport redraw
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def disable_clash_gizmos():
    """Disable clash marker gizmos"""
    global _gizmo_group_registered

    if not _gizmo_group_registered:
        return

    # Clear gizmos by triggering refresh with no data
    # (GizmoGroup.refresh will clear gizmos if no candidates)
    _gizmo_group_registered = False

    print("✓ Clash marker gizmos disabled")

    # Force viewport redraw
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()


def refresh_clash_gizmos(context):
    """Refresh all gizmo positions and colors"""
    # Trigger gizmo group refresh
    # Blender automatically calls GizmoGroup.refresh() when we tag for update

    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            for region in area.regions:
                if region.type == 'WINDOW':
                    region.tag_redraw()

    print("  🔄 Gizmo refresh triggered")


def is_gizmo_group_active() -> bool:
    """Check if gizmo visualization is currently enabled"""
    return _gizmo_group_registered


def get_marker_count() -> int:
    """Get number of active markers"""
    props = bpy.context.scene.BIMClashProperties
    return len(props.discipline_clash_candidates)


def highlight_current_clash(clash_index: int):
    """Highlight specific clash marker (for Previous/Next navigation)"""
    # TODO: Implement by changing color or scale of current marker
    # For now, just trigger refresh
    refresh_clash_gizmos(bpy.context)
