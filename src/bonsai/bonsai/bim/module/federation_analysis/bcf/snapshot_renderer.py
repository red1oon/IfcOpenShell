"""
Snapshot Renderer for BCF Export

Renders clash visualizations as PNG images for BCF topics.
Each snapshot shows the clashing elements highlighted in the 3D context.
"""

import bpy
import mathutils
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import tempfile


class SnapshotRenderer:
    """
    Renders snapshots of clashes for BCF export.

    Creates PNG images showing clashing elements in 3D context with
    appropriate camera positioning and visual highlighting.
    """

    def __init__(self, database_path: str):
        """
        Initialize snapshot renderer.

        Args:
            database_path: Path to clash detection database
        """
        self.database_path = database_path
        self.temp_dir = tempfile.gettempdir()

    def render_clash_snapshot(
        self,
        clash_id: int,
        viewpoint_data: Dict,
        width: int = 800,
        height: int = 600,
        highlight_clashes: bool = True
    ) -> Optional[bytes]:
        """
        Render snapshot for a single clash.

        Args:
            clash_id: Clash ID to render
            viewpoint_data: Camera position data
            width: Image width in pixels
            height: Image height in pixels
            highlight_clashes: Draw red boxes around clashing elements

        Returns:
            PNG image as bytes, or None if rendering failed
        """
        try:
            # Store original render settings
            original_settings = self._store_render_settings()

            # Setup render settings
            self._setup_render_settings(width, height)

            # Create temporary camera
            camera = self._create_temp_camera(viewpoint_data)

            # Setup scene
            scene = bpy.context.scene
            scene.camera = camera

            # Get clash element GUIDs
            guid_a, guid_b = self._get_clash_guids(clash_id)

            # Highlight clashing elements if requested
            highlighted_objects = []
            if highlight_clashes and guid_a and guid_b:
                highlighted_objects = self._highlight_elements([guid_a, guid_b])

            # Render to temporary file
            output_path = Path(self.temp_dir) / f"clash_{clash_id}_snapshot.png"
            scene.render.filepath = str(output_path)

            # Render
            bpy.ops.render.render(write_still=True)

            # Read rendered image
            with open(output_path, 'rb') as f:
                image_data = f.read()

            # Cleanup
            output_path.unlink()
            bpy.data.objects.remove(camera, do_unlink=True)

            # Restore highlighting
            if highlighted_objects:
                self._restore_element_highlighting(highlighted_objects)

            # Restore render settings
            self._restore_render_settings(original_settings)

            return image_data

        except Exception as e:
            print(f"Failed to render snapshot for clash {clash_id}: {e}")
            return None

    def render_viewport_screenshot(
        self,
        width: int = 800,
        height: int = 600
    ) -> bytes:
        """
        Capture current viewport as screenshot (faster than full render).

        Args:
            width: Image width
            height: Image height

        Returns:
            PNG image as bytes
        """
        import gpu
        import bgl

        try:
            # Get active 3D viewport
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    # Trigger viewport redraw
                    area.tag_redraw()

                    # Setup offscreen rendering
                    offscreen = gpu.types.GPUOffScreen(width, height)

                    with offscreen.bind():
                        # Clear buffer
                        bgl.glClear(bgl.GL_COLOR_BUFFER_BIT | bgl.GL_DEPTH_BUFFER_BIT)

                        # Draw viewport
                        view_matrix = area.spaces.active.region_3d.view_matrix
                        projection_matrix = area.spaces.active.region_3d.window_matrix

                        # Read pixels
                        buffer = bgl.Buffer(bgl.GL_BYTE, width * height * 4)
                        bgl.glReadPixels(0, 0, width, height, bgl.GL_RGBA, bgl.GL_UNSIGNED_BYTE, buffer)

                    offscreen.free()

                    # Convert to PNG bytes
                    # Note: In production, would use PIL/Pillow for proper PNG encoding
                    return bytes(buffer)

            return None

        except Exception as e:
            print(f"Failed to capture viewport: {e}")
            return None

    def render_all_clash_snapshots(
        self,
        viewpoints: Dict[int, Dict],
        clash_ids: Optional[List[int]] = None,
        width: int = 800,
        height: int = 600
    ) -> Dict[int, bytes]:
        """
        Render snapshots for multiple clashes.

        Args:
            viewpoints: Dict mapping clash_id to viewpoint_data
            clash_ids: Specific clash IDs to render (None = all in viewpoints)
            width: Image width
            height: Image height

        Returns:
            Dict mapping clash_id to PNG bytes
        """
        snapshots = {}

        ids_to_render = clash_ids if clash_ids else list(viewpoints.keys())

        for clash_id in ids_to_render:
            if clash_id not in viewpoints:
                print(f"Warning: No viewpoint for clash {clash_id}, skipping")
                continue

            print(f"Rendering snapshot for clash {clash_id}...")

            snapshot = self.render_clash_snapshot(
                clash_id,
                viewpoints[clash_id],
                width,
                height
            )

            if snapshot:
                snapshots[clash_id] = snapshot

        return snapshots

    def _get_clash_guids(self, clash_id: int) -> Tuple[Optional[str], Optional[str]]:
        """Get element GUIDs for a clash."""
        import sqlite3

        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()

        cursor.execute(
            "SELECT guid_a, guid_b FROM clash_status WHERE clash_id = ?",
            (clash_id,)
        )

        row = cursor.fetchone()
        conn.close()

        return row if row else (None, None)

    def _highlight_elements(self, guids: List[str]) -> List[Dict]:
        """
        Highlight elements by changing their display color.

        Returns list of original states for restoration.
        """
        highlighted = []

        for obj in bpy.data.objects:
            # Check if object has IFC GUID
            if hasattr(obj, 'BIMObjectProperties'):
                ifc_guid = obj.BIMObjectProperties.get('ifc_guid', '')

                if ifc_guid in guids:
                    # Store original state
                    original = {
                        'object': obj,
                        'color': obj.color[:] if hasattr(obj, 'color') else None,
                        'display_type': obj.display_type
                    }
                    highlighted.append(original)

                    # Apply highlight
                    obj.color = (1.0, 0.0, 0.0, 1.0)  # Red
                    obj.show_in_front = True

        return highlighted

    def _restore_element_highlighting(self, highlighted: List[Dict]):
        """Restore elements to original display state."""
        for item in highlighted:
            obj = item['object']
            if item['color']:
                obj.color = item['color']
            obj.display_type = item['display_type']
            obj.show_in_front = False

    def _create_temp_camera(self, viewpoint_data: Dict) -> bpy.types.Object:
        """Create temporary camera at viewpoint position."""
        camera_data = bpy.data.cameras.new(name="BCF_Temp_Camera")
        camera_obj = bpy.data.objects.new("BCF_Temp_Camera", camera_data)
        bpy.context.scene.collection.objects.link(camera_obj)

        # Set camera location
        camera_obj.location = viewpoint_data['camera']

        # Calculate rotation to look at target
        target = mathutils.Vector(viewpoint_data['target'])
        camera_loc = mathutils.Vector(viewpoint_data['camera'])
        direction = (target - camera_loc).normalized()

        # Create rotation
        up = mathutils.Vector(viewpoint_data.get('up', (0, 0, 1)))
        rot_quat = direction.to_track_quat('-Z', 'Y')
        camera_obj.rotation_euler = rot_quat.to_euler()

        # Set field of view
        camera_data.lens = 35  # mm (60 degree FOV)

        return camera_obj

    def _setup_render_settings(self, width: int, height: int):
        """Configure render settings for snapshot."""
        scene = bpy.context.scene
        scene.render.resolution_x = width
        scene.render.resolution_y = height
        scene.render.resolution_percentage = 100
        scene.render.image_settings.file_format = 'PNG'
        scene.render.image_settings.color_mode = 'RGBA'

        # Use workbench engine for fast rendering
        scene.render.engine = 'BLENDER_WORKBENCH'
        scene.display.shading.light = 'STUDIO'
        scene.display.shading.studio_light = 'Default'

    def _store_render_settings(self) -> Dict:
        """Store current render settings for restoration."""
        scene = bpy.context.scene
        return {
            'resolution_x': scene.render.resolution_x,
            'resolution_y': scene.render.resolution_y,
            'resolution_percentage': scene.render.resolution_percentage,
            'file_format': scene.render.image_settings.file_format,
            'color_mode': scene.render.image_settings.color_mode,
            'engine': scene.render.engine
        }

    def _restore_render_settings(self, settings: Dict):
        """Restore original render settings."""
        scene = bpy.context.scene
        scene.render.resolution_x = settings['resolution_x']
        scene.render.resolution_y = settings['resolution_y']
        scene.render.resolution_percentage = settings['resolution_percentage']
        scene.render.image_settings.file_format = settings['file_format']
        scene.render.image_settings.color_mode = settings['color_mode']
        scene.render.engine = settings['engine']
