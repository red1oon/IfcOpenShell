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

# Import centralized offset function
from bonsai.bim.module.federation.core.coordinate_utils import get_model_offset as get_model_offset_centralized

# ============================================================================
# LOGGING SETUP
# ============================================================================

def setup_gizmo_logging():
    """Setup logging to consolelogs with timestamp"""
    logger = logging.getLogger('bonsai.clash.gizmo')
    logger.setLevel(logging.DEBUG)

    # Prevent duplicate handlers
    if logger.handlers:
        return logger

    # Handler: consolelogs/gizmo_interactions_TIMESTAMP.log
    from datetime import datetime
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    consolelogs_dir = Path.home() / "Documents/bonsai/consolelogs"
    consolelogs_dir.mkdir(parents=True, exist_ok=True)

    log_file = consolelogs_dir / f"gizmo_interactions_{timestamp}.log"

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Also add console handler for Blender system console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('🎯 GIZMO: %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    logger.info(f"=== Gizmo logging initialized: {log_file} ===")
    print(f"\n🎯 GIZMO LOGGING: {log_file}\n")

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

# Use centralized offset function (imported from coordinate_utils)
# Old local implementation removed - now using get_model_offset_centralized
get_model_offset = get_model_offset_centralized


def ifc_to_blender_coords(ifc_coords: tuple) -> Vector:
    """Convert IFC world coordinates to Blender scene coordinates"""
    offset = get_model_offset()
    logger.debug(f"CLASH GIZMO offset: {offset}, IFC coords: {ifc_coords}")
    result = Vector((
        ifc_coords[0] - offset.x,
        ifc_coords[1] - offset.y,
        ifc_coords[2] - offset.z
    ))
    logger.debug(f"  → Blender coords: {result}")
    return result


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

    # CRITICAL: This makes the gizmo interactive and selectable
    bl_target_properties = ()

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
        # CRITICAL: Defensive check - ensure custom_shape still valid
        if not hasattr(self, "custom_shape") or self.custom_shape is None:
            logger.warning(f"Gizmo {self.clash_index} has no custom_shape in draw()")
            return

        # Set color based on status
        color = get_clash_color(self.status)
        self.color = color
        self.color_highlight = (1.0, 1.0, 1.0)  # White when hovered
        self.alpha = 1.0  # Fully opaque for visibility
        self.alpha_highlight = 1.0

        # CRITICAL: Actually render the custom shape!
        try:
            self.draw_custom_shape(self.custom_shape)
        except Exception as e:
            # Graceful failure if shape becomes invalid
            logger.error(f"Failed to draw gizmo {self.clash_index}: {e}")
            return

    def invoke(self, context, event):
        """Handle user interaction with gizmo

        NOTE: Double-click doesn't work reliably with gizmos because:
        - First click triggers jump_to_clash() which changes viewport
        - Viewport change can cause gizmo to lose focus
        - Second click might not reach the same gizmo

        Alternative: Use Ctrl+Click for context menu (more reliable)
        """
        logger.info(f"🖱️  GIZMO INVOKE: event.type={event.type}, event.value={event.value}, clash_index={self.clash_index}")

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            # Check for modifier key (Ctrl+Click) for context menu
            if event.ctrl:
                # Ctrl+Click: Show context menu
                logger.info(f"  Ctrl+Click on clash {self.clash_index} - opening menu")

                # Store clash data in scene for menu access
                context.scene["_temp_clash_index"] = self.clash_index
                context.scene["_temp_clash_guid_a"] = self.guid_a
                context.scene["_temp_clash_guid_b"] = self.guid_b
                context.scene["_temp_clash_status"] = self.status

                # Show context menu
                try:
                    bpy.ops.wm.call_menu(name=BIM_MT_clash_gizmo_context_menu.bl_idname)
                    logger.info(f"  ✓ Context menu opened successfully")
                except Exception as e:
                    logger.error(f"  ✗ Failed to call context menu: {e}")

                return {'RUNNING_MODAL'}
            else:
                # Normal click: Jump to clash
                logger.info(f"  Single-click on clash {self.clash_index} - jumping")
                self.jump_to_clash(context)
                return {'RUNNING_MODAL'}

        return {'PASS_THROUGH'}

    def jump_to_clash(self, context):
        """Jump viewport to this clash (reuse existing operator)"""
        try:
            props = context.scene.BIMClashProperties

            # Validate clash index
            if self.clash_index < 0 or self.clash_index >= len(props.discipline_clash_candidates):
                logger.warning(f"Invalid clash index: {self.clash_index}")
                return

            # Check if operator is already running (prevent re-entrancy)
            if hasattr(context.scene, '_clash_viz_processing'):
                return

            # Set the active clash index and call operator
            props.active_discipline_clash_index = self.clash_index
            bpy.ops.bim.select_discipline_clash()
            logger.info(f"Selected clash {self.clash_index + 1}")

        except Exception as e:
            logger.error(f"Gizmo click failed: {e}", exc_info=True)

    def draw_select(self, context, select_id):
        """Draw gizmo for selection pass (enables clicking)"""
        # CRITICAL: Defensive check - ensure custom_shape still valid
        if not hasattr(self, "custom_shape") or self.custom_shape is None:
            return

        try:
            self.draw_custom_shape(self.custom_shape, select_id=select_id)
        except Exception as e:
            logger.error(f"Failed to draw_select gizmo {self.clash_index}: {e}")
            return

    def test_select(self, context, location):
        """Enable hover detection"""
        # Log only first call per gizmo to reduce spam
        if not hasattr(self, '_test_select_logged'):
            self._test_select_logged = True
            logger.debug(f"🎯 test_select called for clash {self.clash_index}, location={location}")
        # Return distance from mouse to gizmo (for hit testing)
        # Blender handles this automatically for standard shapes
        # Return -1 to let Blender calculate distance
        return -1

    def modal(self, context, event, tweak):
        """Handle modal interaction (required for clickable gizmos)"""
        logger.info(f"🖱️  MODAL: event={event.type}, value={event.value}, clash={self.clash_index}")
        print(f"🖱️  GIZMO MODAL: event={event.type}, value={event.value}")

        # Call invoke() for actual handling
        return self.invoke(context, event)


# ============================================================================
# CLASH MARKER GIZMO GROUP (Manager)
# ============================================================================

class ClashMarkerGizmoGroup(GizmoGroup):
    """Manages all clash marker gizmos in viewport"""

    bl_idname = "bim.clash_marker_gizmos"  # Match Bonsai naming convention
    bl_label = "Clash Markers"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_options = {'3D', 'PERSISTENT', 'SHOW_MODAL_ALL'}  # Match drawing module pattern

    @classmethod
    def poll(cls, context):
        """Show gizmos in 3D viewport when visualization is enabled

        CRITICAL FIX: Blender only calls poll() when tracked properties change.
        By accessing context.active_object, we trigger Blender's dependency tracking
        system, causing poll() to be re-evaluated whenever the active object changes.

        This is the standard pattern used by working gizmos (ExtrusionWidget, ClippingPlane).
        """
        # Check VIEW_3D context first (fast early return)
        if not (context.area and context.area.type == 'VIEW_3D'):
            return False

        # Check if gizmo visualization is enabled
        props = context.scene.BIMClashProperties
        # Use hasattr to handle old .blend files that don't have this property yet
        if not getattr(props, 'gizmo_visualization_enabled', False):
            return False

        # Access active_object to trigger dependency tracking
        # This makes Blender re-evaluate poll() when active object changes
        _ = context.active_object  # Trigger tracking (value doesn't matter)

        return True

    def setup(self, context):
        """Initialize gizmo group (called once)

        CRITICAL: Industry standard pattern from Bonsai gizmos.
        - Store gizmo list as instance variable for persistence
        - Never clear during modal operations
        - Let refresh() update existing gizmos, not recreate them
        """
        logger.info("🎯 ClashMarkerGizmoGroup.setup() called")
        print("🎯 Clash marker gizmo group setup")
        print(f"   Context: {context}")
        print(f"   Area type: {context.area.type if context.area else 'None'}")

        # CRITICAL: Track gizmo state for safe updates
        self._gizmo_cache = {}  # Maps clash_index -> gizmo instance
        self._last_clash_data = None  # Track when to recreate vs update

    def refresh(self, context):
        """Update gizmos from clash data (called when data changes)

        CRITICAL: Industry standard pattern - NEVER clear() during modal operations.
        - Compare current data with cached state
        - Update existing gizmos in place when possible
        - Only recreate when selection changes (safe time to clear)
        """
        props = context.scene.BIMClashProperties

        # Check if we have clash data (use getattr for old .blend files)
        if not getattr(props, 'discipline_clash_candidates', None):
            logger.info("No clash candidates to visualize")
            # Clear gizmos only when no data (safe - user action)
            if self._gizmo_cache:
                self.gizmos.clear()
                self._gizmo_cache.clear()
                self._last_clash_data = None
            return

        # Filter to only selected clashes
        selected_candidates = [
            (i, candidate) for i, candidate in enumerate(props.discipline_clash_candidates)
            if candidate.selected
        ]

        if not selected_candidates:
            logger.info("No clashes selected for visualization")
            # Clear gizmos only when selection empty (safe - user action)
            if self._gizmo_cache:
                self.gizmos.clear()
                self._gizmo_cache.clear()
                self._last_clash_data = None
            return

        # Get federation DB path
        fed_props = context.scene.BIMFederationProperties
        db_path = fed_props.federation_database_path
        if not db_path:
            logger.warning("No federation database path set")
            return

        # Build current clash data fingerprint (for change detection)
        current_data = tuple((i, candidate.guid_a, candidate.guid_b, candidate.selected)
                            for i, candidate in enumerate(props.discipline_clash_candidates))

        # CRITICAL: Only recreate gizmos if selection changed
        # This prevents clearing gizmos during modal operations
        if current_data != self._last_clash_data:
            logger.info(f"Clash selection changed - rebuilding {len(selected_candidates)} gizmos")
            print(f"  🔄 Rebuilding gizmos for {len(selected_candidates)} selected clashes")

            # SAFE to clear: selection changed (not during modal)
            self.gizmos.clear()
            self._gizmo_cache.clear()

            # Create gizmos for selected clashes
            for i, candidate in selected_candidates:
                # Query federation DB for bbox centers
                center_a, center_b = get_clash_bbox_centers(
                    candidate.guid_a, candidate.guid_b, db_path
                )

                if not center_a or not center_b:
                    logger.warning(f"Skipping clash {i}: bbox not found in DB")
                    continue

                # Database coords are already in viewport space (offset-relative)
                # NO conversion needed - db stores same coordinate system as viewport
                midpoint = (center_a + center_b) / 2

                # Get clash status from database
                clash_id = db.get_clash_id(candidate.guid_a, candidate.guid_b)
                db_status = db.get_clash_status(candidate.guid_a, candidate.guid_b)

                if db_status:
                    status = db_status['status']
                else:
                    # New clash - default to NEW
                    status = 'NEW'
                    db.set_clash_status(
                        candidate.guid_a, candidate.guid_b,
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
                gz.scale_basis = 0.5  # 0.5m diameter sphere

                # Store clash data in gizmo
                gz.clash_id = clash_id
                gz.clash_index = i
                gz.guid_a = candidate.guid_a
                gz.guid_b = candidate.guid_b
                gz.status = status

                # Enable interaction (industry standard settings)
                gz.use_draw_modal = True
                gz.use_event_handle_all = False
                gz.use_select_background = True
                gz.use_grab_cursor = False

                # Cache gizmo reference (prevent GC)
                self._gizmo_cache[i] = gz

                logger.debug(f"  Created gizmo for clash {i}, status={status}")

            logger.info(f"✓ Created {len(self._gizmo_cache)} gizmos")
            print(f"  ✓ Created {len(self._gizmo_cache)} clash gizmos")
            self._last_clash_data = current_data

        else:
            # SAFE UPDATE PATH: Just update colors for existing gizmos
            # No clear(), no recreate - gizmos stay alive during modal
            logger.debug("Updating existing gizmo colors (no recreate)")

            for i, candidate in selected_candidates:
                if i in self._gizmo_cache:
                    gz = self._gizmo_cache[i]

                    # Update status from database (may have changed via context menu)
                    db_status = db.get_clash_status(candidate.guid_a, candidate.guid_b)
                    if db_status and db_status['status'] != gz.status:
                        gz.status = db_status['status']
                        logger.info(f"  Updated clash {i} status: {gz.status}")

            logger.debug(f"✓ Updated {len(self._gizmo_cache)} gizmo colors")


# ============================================================================
# GIZMO GROUP MANAGEMENT
# ============================================================================

_gizmo_group_registered = False

def enable_clash_gizmos(context):
    """Enable clash marker gizmos in viewport"""
    global _gizmo_group_registered

    logger.info("=== enable_clash_gizmos() called ===")
    print("\n=== Enabling Gizmo Visualization ===")

    # CRITICAL: Set the scene property to True (persists across sessions)
    props = context.scene.BIMClashProperties
    props.gizmo_visualization_enabled = True

    print(f"   gizmo_visualization_enabled: {props.gizmo_visualization_enabled}")
    logger.info(f"  Property state: gizmo_visualization_enabled={props.gizmo_visualization_enabled}")

    # Check selected clashes
    selected_count = sum(1 for c in props.discipline_clash_candidates if c.selected)
    total_count = len(props.discipline_clash_candidates)
    print(f"   Selected clashes: {selected_count} / {total_count}")
    logger.info(f"  Clashes: {selected_count} selected out of {total_count} total")

    if _gizmo_group_registered:
        print("  ⚠️  Gizmos already enabled")
        logger.warning("  Gizmos already marked as registered")
        # Just refresh to update positions
        refresh_clash_gizmos(context)
        return

    # CRITICAL: Check if GizmoGroup is actually registered with Blender
    try:
        # Try to access our registered GizmoGroup class
        from bpy.types import GizmoGroup
        all_gizmo_groups = [cls for cls in GizmoGroup.__subclasses__()]
        our_group = ClashMarkerGizmoGroup

        is_registered = our_group in all_gizmo_groups
        logger.info(f"  GizmoGroup registration check: {is_registered}")
        print(f"   ClashMarkerGizmoGroup registered: {is_registered}")
        print(f"   Total GizmoGroups: {len(all_gizmo_groups)}")
        logger.info(f"  Total GizmoGroup subclasses: {len(all_gizmo_groups)}")

        # List all registered gizmo groups
        for i, grp in enumerate(all_gizmo_groups[:10]):  # First 10
            logger.info(f"    [{i}] {grp.bl_idname if hasattr(grp, 'bl_idname') else grp.__name__}")

    except Exception as e:
        logger.error(f"  Failed to check GizmoGroup registration: {e}")
        print(f"   ✗ Error checking registration: {e}")

    _gizmo_group_registered = True
    logger.info("  Marked gizmo group as registered")

    print(f"   Calling refresh_clash_gizmos()...")
    refresh_clash_gizmos(context)

    print("✓ Clash marker gizmos enabled")
    logger.info("✓ Enable complete")

    # Force viewport redraw
    redraw_count = 0
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()
            redraw_count += 1

    print(f"   Tagged {redraw_count} 3D viewports for redraw")
    logger.info(f"  Tagged {redraw_count} viewports for redraw")


def disable_clash_gizmos(context):
    """Disable clash marker gizmos"""
    global _gizmo_group_registered

    # CRITICAL: Set the scene property to False (persists across sessions)
    props = context.scene.BIMClashProperties
    props.gizmo_visualization_enabled = False

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
    """Refresh all gizmo positions and colors

    CRITICAL: Industry standard pattern - gentle refresh, not forced recreation.
    - Tag areas for redraw (Blender calls refresh() at safe time)
    - NEVER force immediate clear/recreate during modal operations
    - Let Blender's gizmo system handle the timing
    """
    logger.info("refresh_clash_gizmos() called")
    print("  🔄 Gizmo refresh requested")

    # Gentle approach: Just tag areas for redraw
    # Blender will call GizmoGroup.refresh() at a safe time
    redraw_count = 0
    for area in context.screen.areas:
        if area.type == 'VIEW_3D':
            area.tag_redraw()
            redraw_count += 1

    logger.info(f"  Tagged {redraw_count} viewports for redraw (refresh will happen at safe time)")
    print(f"  ✓ Tagged {redraw_count} viewports for refresh")


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
