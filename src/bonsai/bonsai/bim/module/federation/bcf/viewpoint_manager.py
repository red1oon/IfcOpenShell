"""
Viewpoint Manager for BCF Export

Captures and manages 3D camera viewpoints from Blender for BCF topics.
Each clash gets a viewpoint showing both clashing elements in context.
"""

import bpy
import mathutils
from typing import Dict, List, Optional, Tuple


class ViewpointManager:
    """
    Manages 3D viewpoint capture for BCF export.

    Captures camera position, target, and up vector from Blender's 3D viewport
    or creates optimal viewpoints automatically for each clash.
    """

    def __init__(self):
        """Initialize viewpoint manager."""
        self.viewpoints = {}  # clash_id -> viewpoint_data

    def capture_current_viewpoint(self, clash_id: int) -> Dict:
        """
        Capture current 3D viewport camera settings.

        Args:
            clash_id: Clash ID to associate with this viewpoint

        Returns:
            Dict with camera, target, up vectors
        """
        # Get active 3D viewport
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                region_3d = space.region_3d

                if region_3d:
                    # Get camera location
                    view_matrix = region_3d.view_matrix.inverted()
                    camera_location = view_matrix.to_translation()

                    # Get view direction (camera target)
                    view_rotation = view_matrix.to_quaternion()
                    view_direction = view_rotation @ mathutils.Vector((0, 0, -1))
                    target = camera_location + (view_direction * region_3d.view_distance)

                    # Get up vector
                    up_vector = view_rotation @ mathutils.Vector((0, 1, 0))

                    viewpoint_data = {
                        'camera': tuple(camera_location),
                        'target': tuple(target),
                        'up': tuple(up_vector),
                        'distance': region_3d.view_distance
                    }

                    self.viewpoints[clash_id] = viewpoint_data
                    return viewpoint_data

        # Fallback if no 3D view found
        return self._create_default_viewpoint()

    def generate_clash_viewpoint(
        self,
        clash_center: Tuple[float, float, float],
        bbox_size: float = 10.0,
        angle: str = 'isometric'
    ) -> Dict:
        """
        Generate optimal viewpoint for a clash location.

        Args:
            clash_center: XYZ coordinates of clash center
            bbox_size: Approximate size of clash area (for camera distance)
            angle: View angle - 'isometric', 'top', 'front', 'side'

        Returns:
            Dict with camera, target, up vectors
        """
        center = mathutils.Vector(clash_center)

        # Calculate camera distance (1.5x the bbox diagonal for good framing)
        distance = bbox_size * 1.5

        # Define view directions based on angle
        view_configs = {
            'isometric': {
                'offset': mathutils.Vector((1, -1, 1)).normalized() * distance,
                'up': mathutils.Vector((0, 0, 1))
            },
            'top': {
                'offset': mathutils.Vector((0, 0, 1)) * distance,
                'up': mathutils.Vector((0, 1, 0))
            },
            'front': {
                'offset': mathutils.Vector((0, -1, 0)) * distance,
                'up': mathutils.Vector((0, 0, 1))
            },
            'side': {
                'offset': mathutils.Vector((1, 0, 0)) * distance,
                'up': mathutils.Vector((0, 0, 1))
            }
        }

        config = view_configs.get(angle, view_configs['isometric'])

        camera_location = center + config['offset']
        target = center
        up = config['up']

        return {
            'camera': tuple(camera_location),
            'target': tuple(target),
            'up': tuple(up),
            'distance': distance
        }

    def generate_viewpoints_for_clashes(
        self,
        database_path: str,
        clash_ids: Optional[List[int]] = None
    ) -> Dict[int, Dict]:
        """
        Generate viewpoints for all clashes based on their geometry.

        Args:
            database_path: Path to clash detection database
            clash_ids: Specific clash IDs (None = all)

        Returns:
            Dict mapping clash_id to viewpoint_data
        """
        import sqlite3

        conn = sqlite3.connect(database_path)
        cursor = conn.cursor()

        # Query to get clash locations from element bounding boxes
        # Note: elements_rtree uses 'id', elements_meta has 'guid'
        query = """
            SELECT
                cs.clash_id,
                cs.guid_a,
                cs.guid_b,
                (era.minX + era.maxX) / 2.0 as center_x_a,
                (era.minY + era.maxY) / 2.0 as center_y_a,
                (era.minZ + era.maxZ) / 2.0 as center_z_a,
                (erb.minX + erb.maxX) / 2.0 as center_x_b,
                (erb.minY + erb.maxY) / 2.0 as center_y_b,
                (erb.minZ + erb.maxZ) / 2.0 as center_z_b,
                MAX(era.maxX - era.minX, era.maxY - era.minY, era.maxZ - era.minZ) as size_a,
                MAX(erb.maxX - erb.minX, erb.maxY - erb.minY, erb.maxZ - erb.minZ) as size_b
            FROM clash_status cs
            LEFT JOIN elements_meta ema ON cs.guid_a = ema.guid
            LEFT JOIN elements_rtree era ON ema.id = era.id
            LEFT JOIN elements_meta emb ON cs.guid_b = emb.guid
            LEFT JOIN elements_rtree erb ON emb.id = erb.id
            WHERE cs.is_ignored = 0
        """

        params = []
        if clash_ids:
            placeholders = ','.join('?' * len(clash_ids))
            query += f" AND cs.clash_id IN ({placeholders})"
            params.extend(clash_ids)

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        viewpoints = {}

        for row in rows:
            clash_id = row[0]

            # Calculate clash center (midpoint between two element centers)
            center_a = (row[3], row[4], row[5])
            center_b = (row[6], row[7], row[8])

            if None in center_a or None in center_b:
                # Fallback if geometry not found
                viewpoints[clash_id] = self._create_default_viewpoint()
                continue

            clash_center = tuple(
                (a + b) / 2.0 for a, b in zip(center_a, center_b)
            )

            # Use larger of the two element sizes for framing
            bbox_size = max(row[9] or 5.0, row[10] or 5.0)

            # Generate isometric viewpoint
            viewpoint = self.generate_clash_viewpoint(
                clash_center,
                bbox_size,
                angle='isometric'
            )

            viewpoints[clash_id] = viewpoint

        self.viewpoints.update(viewpoints)
        return viewpoints

    def set_viewport_to_viewpoint(self, viewpoint_data: Dict) -> bool:
        """
        Set Blender viewport camera to match viewpoint data.

        Useful for positioning view before taking screenshots.

        Args:
            viewpoint_data: Dict with camera, target, up

        Returns:
            True if successful
        """
        try:
            camera_loc = mathutils.Vector(viewpoint_data['camera'])
            target_loc = mathutils.Vector(viewpoint_data['target'])

            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    space = area.spaces.active
                    region_3d = space.region_3d

                    # Calculate view direction
                    direction = (target_loc - camera_loc).normalized()

                    # Create rotation from direction and up vector
                    up = mathutils.Vector(viewpoint_data.get('up', (0, 0, 1)))

                    # Build view matrix
                    # Forward is -Z in Blender camera space
                    forward = -direction
                    right = up.cross(forward).normalized()
                    up_corrected = forward.cross(right)

                    rot_matrix = mathutils.Matrix([
                        right,
                        up_corrected,
                        forward
                    ]).transposed().to_4x4()

                    rot_matrix.translation = camera_loc

                    # Apply to viewport
                    region_3d.view_matrix = rot_matrix.inverted()

                    # Set view distance
                    if 'distance' in viewpoint_data:
                        region_3d.view_distance = viewpoint_data['distance']

                    return True

            return False

        except Exception as e:
            print(f"Failed to set viewport: {e}")
            return False

    def _create_default_viewpoint(self) -> Dict:
        """Create default viewpoint at origin."""
        return {
            'camera': (10.0, -10.0, 10.0),
            'target': (0.0, 0.0, 0.0),
            'up': (0.0, 0.0, 1.0),
            'distance': 14.142
        }

    def clear_viewpoints(self):
        """Clear all stored viewpoints."""
        self.viewpoints.clear()

    def get_viewpoint(self, clash_id: int) -> Optional[Dict]:
        """Get viewpoint for specific clash ID."""
        return self.viewpoints.get(clash_id)

    def get_all_viewpoints(self) -> Dict[int, Dict]:
        """Get all stored viewpoints."""
        return self.viewpoints.copy()
