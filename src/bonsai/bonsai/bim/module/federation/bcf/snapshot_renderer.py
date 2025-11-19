"""
Snapshot Renderer for BCF Export

Renders clash visualizations as PNG images for BCF topics.
Each snapshot shows the clashing elements highlighted in the 3D context.
"""

import bpy
import mathutils
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import tempfile

logger = logging.getLogger(__name__)


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
        highlight_clashes: bool = False,
        fast_mode: bool = True,
        target_size_kb: int = 200
    ) -> Optional[bytes]:
        """
        Render snapshot for a single clash.

        PERFORMANCE MODES:
        - fast_mode=True: Viewport screenshot (~0.5s, <200KB)
        - fast_mode=False: Full render (3-5s, higher quality)

        Args:
            clash_id: Clash ID to render
            viewpoint_data: Camera position data
            width: Image width in pixels
            height: Image height in pixels
            highlight_clashes: Draw red boxes around clashing elements
            fast_mode: Use viewport screenshot (fast) vs full render (slow)
            target_size_kb: Target PNG file size in KB

        Returns:
            PNG image as bytes, or None if rendering failed
        """
        try:
            # FAST MODE: Viewport screenshot (no full render)
            if fast_mode:
                return self._render_viewport_snapshot(
                    clash_id,
                    viewpoint_data,
                    width,
                    height,
                    target_size_kb
                )

            # SLOW MODE: Full render with object hiding
            return self._render_full_snapshot(
                clash_id,
                viewpoint_data,
                width,
                height,
                highlight_clashes
            )

        except Exception as e:
            print(f"Failed to render snapshot for clash {clash_id}: {e}")
            return None

    def render_group_snapshot(
        self,
        guids: List[str],
        viewpoint_data: Dict,
        width: int = 800,
        height: int = 600,
        target_size_kb: int = 200,
        group_id: str = None,
        cascade_guid: str = None
    ) -> Optional[bytes]:
        """
        Render snapshot for a cascade group with multiple elements.

        Highlights all elements in the cascade group (not just one clash pair).
        Used for clash resolution reports to show all affected elements.

        Args:
            guids: List of element GUIDs to highlight
            viewpoint_data: Camera position data
            width: Image width in pixels
            height: Image height in pixels
            target_size_kb: Target PNG file size in KB

        Returns:
            PNG image as bytes, or None if rendering failed
        """
        highlighted_objects = []
        try:
            import tempfile
            from pathlib import Path

            # CRITICAL: Clear visualization collection before loading new elements
            # This prevents accumulation of elements from previous group snapshots
            clash_viz_collection_name = "Clash_Viz"
            if clash_viz_collection_name in bpy.data.collections:
                collection = bpy.data.collections[clash_viz_collection_name]
                # Remove all objects from collection
                for obj in list(collection.objects):
                    bpy.data.objects.remove(obj, do_unlink=True)
                # Remove collection itself
                bpy.data.collections.remove(collection)

            # Load all elements in viewport
            try:
                from ..visualization.federation_viz_helper import get_clash_elements_for_visualization
                loaded_count = 0
                for guid in guids:
                    # Try to load each element (will create new Clash_Viz collection)
                    obj, _ = get_clash_elements_for_visualization(guid, guid, self.database_path)
                    if obj:
                        loaded_count += 1

                if loaded_count == 0:
                    print(f"  Warning: Could not load any elements from {len(guids)} GUIDs")
                    return None

            except Exception as e:
                print(f"  Warning: Failed to load cascade elements: {e}")
                return None

            # Get proximity data for intelligent coloring (if available)
            proximity_data_map = {}

            # Use provided cascade_guid parameter (passed from snapshot_manager)
            cascade_guid_for_coloring = cascade_guid

            try:
                # Try to load proximity analyzer and get data
                from ..clash.proximity_analyzer import ProximityAnalyzer
                analyzer = ProximityAnalyzer(self.database_path)

                # Try to get proximity report for this group
                # Note: This requires proximity analysis to have been run previously
                try:
                    report = analyzer.generate_proximity_report(
                        clash_group_id=group_id,
                        cascade_guid=cascade_guid_for_coloring
                    )

                    # Build proximity data map: GUID -> {'severity': str, 'clearance_mm': float}
                    for clash in report.get('potential_clashes', []):
                        proximity_data_map[clash['guid']] = {
                            'severity': clash['severity'],
                            'clearance_mm': clash['clearance_mm']
                        }

                    for warning in report.get('clearance_warnings', []):
                        proximity_data_map[warning['guid']] = {
                            'severity': warning['severity'],
                            'clearance_mm': warning['clearance_mm']
                        }
                except Exception:
                    # Proximity analysis not available for this group - use default coloring
                    pass

            except ImportError:
                # Proximity analyzer not available - use default red coloring
                pass

            # Highlight all cascade elements with proximity-aware colors
            highlighted_objects = self._highlight_elements_viewport(
                guids,
                cascade_guid=cascade_guid_for_coloring,
                proximity_data=proximity_data_map if proximity_data_map else None
            )

            # Position viewport to cascade location
            positioned = self.set_viewport_to_viewpoint(viewpoint_data)
            if not positioned:
                logger.debug(f"Could not position viewport for cascade group (using default view)")

            # Force viewport redraw to ensure camera position is applied
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()

            # Process pending updates
            bpy.context.view_layer.update()

            # Create temp file for screenshot with unique name per group
            # Use group_id if provided, otherwise use timestamp to ensure uniqueness
            import time
            if group_id:
                temp_filename = f"cascade_group_{group_id}_viewport.png"
            else:
                temp_filename = f"cascade_group_{int(time.time()*1000)}_viewport.png"
            temp_path = Path(tempfile.gettempdir()) / temp_filename

            # Take viewport screenshot using render (more reliable than screen.screenshot)
            try:
                # Store original render settings
                original_filepath = bpy.context.scene.render.filepath
                original_resolution_x = bpy.context.scene.render.resolution_x
                original_resolution_y = bpy.context.scene.render.resolution_y

                # Configure for viewport capture
                bpy.context.scene.render.filepath = str(temp_path)

                # Use OpenGL render for speed (captures viewport as-is)
                bpy.ops.render.opengl(write_still=True, view_context=True)

                # Restore original settings
                bpy.context.scene.render.filepath = original_filepath

            except Exception as e:
                print(f"  ⚠️  OpenGL render failed, trying screenshot fallback: {e}")
                try:
                    # Fallback to screenshot (may not work in all contexts)
                    bpy.ops.screen.screenshot(filepath=str(temp_path), full=True)
                except Exception as e2:
                    print(f"  ✗ Screenshot also failed: {e2}")
                    return None

            # Read screenshot
            if not temp_path.exists():
                print(f"  ✗ Error: Screenshot not saved to {temp_path}")
                return None

            with open(temp_path, 'rb') as f:
                image_data = f.read()

            # Cleanup
            try:
                temp_path.unlink()
            except:
                pass  # Ignore cleanup errors

            # Restore element highlighting
            if highlighted_objects:
                self._restore_element_highlighting_viewport(highlighted_objects)

            return image_data

        except Exception as e:
            print(f"Failed to render cascade group snapshot: {e}")
            import traceback
            traceback.print_exc()

            # Restore highlighting if failed
            if highlighted_objects:
                try:
                    self._restore_element_highlighting_viewport(highlighted_objects)
                except:
                    pass

            return None

    def _render_viewport_snapshot(
        self,
        clash_id: int,
        viewpoint_data: Dict,
        width: int,
        height: int,
        target_size_kb: int
    ) -> Optional[bytes]:
        """
        Fast viewport screenshot method.

        Captures current viewport state - no full render overhead.
        ~0.5s per snapshot, ~50-200KB file size.
        """
        highlighted_objects = []
        try:
            import tempfile
            from pathlib import Path

            # Get clash element GUIDs
            guid_a, guid_b = self._get_clash_guids(clash_id)
            if not guid_a or not guid_b:
                print(f"  Warning: Could not get GUIDs for clash {clash_id}")
                return None

            # Ensure clash elements are loaded in viewport
            # This loads them as procedural shapes if not already present
            try:
                from ..visualization.federation_viz_helper import get_clash_elements_for_visualization
                obj_a, obj_b = get_clash_elements_for_visualization(guid_a, guid_b, self.database_path)
                if not obj_a or not obj_b:
                    print(f"  Warning: Could not load clash elements for clash {clash_id}")
                    return None


            except Exception as e:
                print(f"  Warning: Failed to load clash elements: {e}")
                import traceback
                traceback.print_exc()
                return None

            # Highlight the clash elements (now that they're loaded)
            highlighted_objects = self._highlight_elements_viewport([guid_a, guid_b])

            # Position viewport to clash location
            positioned = self.set_viewport_to_viewpoint(viewpoint_data)
            if not positioned:
                logger.debug(f"Could not position viewport for clash {clash_id} (using default view)")

            # Force viewport redraw to ensure camera position is applied
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()

            # Process pending updates
            bpy.context.view_layer.update()

            # Create temp file for screenshot
            temp_path = Path(tempfile.gettempdir()) / f"clash_{clash_id}_viewport.png"

            # Render viewport to offscreen buffer (viewport only, no UI)
            screenshot_success = self._render_viewport_to_image(temp_path, width, height)

            if not screenshot_success:
                print(f"  Warning: Viewport rendering failed for clash {clash_id}")
                return None

            # Read image
            if temp_path.exists():
                with open(temp_path, 'rb') as f:
                    image_data = f.read()

                # Optimize size if needed
                file_size_kb = len(image_data) / 1024
                if file_size_kb > target_size_kb * 1.5:  # 50% over target
                    image_data = self._optimize_png_size(image_data, target_size_kb)

                # Cleanup
                temp_path.unlink()

                return image_data
            else:
                print(f"  Warning: Screenshot file not created for clash {clash_id}")
                return None

        except Exception as e:
            print(f"  Viewport snapshot failed for clash {clash_id}: {e}")
            return None
        finally:
            # Always restore highlighted elements
            if highlighted_objects:
                self._restore_element_highlighting_viewport(highlighted_objects)

    def _render_full_snapshot(
        self,
        clash_id: int,
        viewpoint_data: Dict,
        width: int,
        height: int,
        highlight_clashes: bool
    ) -> Optional[bytes]:
        """
        Full render method (original approach).

        Slower but higher quality. Used when fast_mode=False.
        """
        hidden_objects = []
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

            # CRITICAL: Hide distant objects to avoid rendering 49K elements (OOM prevention)
            clash_center = mathutils.Vector(viewpoint_data['target'])
            hidden_objects = self._hide_distant_objects(clash_center, context_radius)
            print(f"  Rendering context: {len(bpy.data.objects) - len(hidden_objects)}/{len(bpy.data.objects)} objects visible (hid {len(hidden_objects)} distant)")

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

            # Restore hidden objects
            for obj in hidden_objects:
                obj.hide_render = False
                obj.hide_viewport = False

            # Restore render settings
            self._restore_render_settings(original_settings)

            return image_data

        except Exception as e:
            print(f"Failed to render snapshot for clash {clash_id}: {e}")
            # Ensure objects are restored even on error
            for obj in hidden_objects:
                try:
                    obj.hide_render = False
                    obj.hide_viewport = False
                except:
                    pass
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
        height: int = 600,
        fast_mode: bool = True
    ) -> Dict[int, bytes]:
        """
        Render snapshots for multiple clashes.

        Args:
            viewpoints: Dict mapping clash_id to viewpoint_data
            clash_ids: Specific clash IDs to render (None = all in viewpoints)
            width: Image width
            height: Image height
            fast_mode: Use viewport screenshot (fast) vs full render (slow)

        Returns:
            Dict mapping clash_id to PNG bytes
        """
        snapshots = {}

        ids_to_render = clash_ids if clash_ids else list(viewpoints.keys())
        total = len(ids_to_render)

        mode_str = "FAST viewport" if fast_mode else "quality render"
        print(f"\n{'='*60}")
        print(f"Rendering {total} snapshots ({mode_str} mode)")
        print(f"{'='*60}\n")

        for i, clash_id in enumerate(ids_to_render, 1):
            if clash_id not in viewpoints:
                print(f"[{i}/{total}] Warning: No viewpoint for clash {clash_id}, skipping")
                continue

            print(f"[{i}/{total}] Rendering snapshot for clash {clash_id}...")

            snapshot = self.render_clash_snapshot(
                clash_id,
                viewpoints[clash_id],
                width,
                height,
                fast_mode=fast_mode
            )

            if snapshot:
                size_kb = len(snapshot) / 1024
                snapshots[clash_id] = snapshot
                print(f"          ✓ Success ({size_kb:.0f}KB)")
            else:
                print(f"          ✗ Failed")

        print(f"\n{'='*60}")
        print(f"Completed: {len(snapshots)}/{total} snapshots rendered")
        print(f"{'='*60}\n")

        return snapshots

    def render_clash_snapshots_lazy(
        self,
        viewpoints: Dict[int, Dict],
        clash_ids: Optional[List[int]] = None,
        width: int = 800,
        height: int = 600
    ):
        """
        Render snapshots one at a time (generator pattern - memory efficient).

        This is the RECOMMENDED method for large clash sets to avoid OOM.

        Args:
            viewpoints: Dict mapping clash_id to viewpoint_data
            clash_ids: Specific clash IDs to render (None = all in viewpoints)
            width: Image width
            height: Image height

        Yields:
            Tuple of (clash_id, snapshot_bytes) for each rendered snapshot
        """
        ids_to_render = clash_ids if clash_ids else list(viewpoints.keys())

        for i, clash_id in enumerate(ids_to_render, 1):
            if clash_id not in viewpoints:
                print(f"Warning: No viewpoint for clash {clash_id}, skipping")
                continue

            print(f"Rendering snapshot {i}/{len(ids_to_render)} for clash {clash_id}...")

            snapshot = self.render_clash_snapshot(
                clash_id,
                viewpoints[clash_id],
                width,
                height
            )

            if snapshot:
                yield (clash_id, snapshot)
            else:
                print(f"  Warning: Snapshot rendering failed for clash {clash_id}")

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

    def _highlight_elements_viewport(
        self,
        guids: List[str],
        cascade_guid: str = None,
        proximity_data: Dict = None
    ) -> List[Dict]:
        """
        Highlight elements for viewport screenshots with proximity-aware coloring.

        Color scheme:
        - ORANGE (1.0, 0.5, 0.0): Cascade element (root cause)
        - RED (1.0, 0.0, 0.0): Direct clashing elements / high severity (<50mm)
        - YELLOW (1.0, 1.0, 0.0): Nearby elements / medium severity (50-200mm)

        Args:
            guids: List of element GUIDs to highlight
            cascade_guid: GUID of cascade element (colored orange if provided)
            proximity_data: Optional dict mapping GUIDs to proximity info:
                            {'guid': {'severity': 'HIGH'|'MEDIUM'|'LOW', 'clearance_mm': float}}

        Returns:
            List of original states for restoration.
        """
        highlighted = []

        for obj in bpy.data.objects:
            # Check if object has IFC GUID (in various possible locations)
            ifc_guid = None

            # PRIORITY 1: Check federation_guid custom property (database-only mode)
            if "federation_guid" in obj:
                ifc_guid = obj["federation_guid"]

            # PRIORITY 2: Check object name (common pattern: object.name == GUID)
            # This handles objects created by get_clash_elements_for_visualization()
            elif obj.name in guids:
                ifc_guid = obj.name

            # PRIORITY 3: Try BIMObjectProperties (full IFC load mode)
            elif hasattr(obj, 'BIMObjectProperties') and hasattr(obj.BIMObjectProperties, 'attributes'):
                for attr in obj.BIMObjectProperties.attributes:
                    if attr.name == 'GlobalId':
                        ifc_guid = attr.string_value
                        break

            # PRIORITY 4: Try direct property access
            elif hasattr(obj, 'BIMObjectProperties'):
                ifc_guid = obj.BIMObjectProperties.get('ifc_guid', '')

            # PRIORITY 5: Check object name contains GUID (last resort)
            elif any(guid in obj.name for guid in guids):
                ifc_guid = next((guid for guid in guids if guid in obj.name), None)

            if ifc_guid and ifc_guid in guids:
                # Store original state
                original = {
                    'object': obj,
                    'color': obj.color[:] if hasattr(obj, 'color') else (1.0, 1.0, 1.0, 1.0),
                    'hide_viewport': obj.hide_viewport,
                    'hide_select': obj.hide_select,
                    'select': obj.select_get()
                }
                highlighted.append(original)

                # Determine color based on element role and proximity
                highlight_color = (1.0, 0.0, 0.0, 1.0)  # Default: bright red (clashing)

                if cascade_guid and ifc_guid == cascade_guid:
                    # CASCADE ELEMENT: Orange (root cause)
                    highlight_color = (1.0, 0.5, 0.0, 1.0)
                elif proximity_data and ifc_guid in proximity_data:
                    # PROXIMITY-AWARE COLORING
                    severity = proximity_data[ifc_guid].get('severity', 'HIGH')
                    if severity == 'HIGH':
                        highlight_color = (1.0, 0.0, 0.0, 1.0)  # Red (direct clash / <50mm)
                    elif severity == 'MEDIUM':
                        highlight_color = (1.0, 1.0, 0.0, 1.0)  # Yellow (nearby / 50-200mm)
                    else:
                        highlight_color = (0.5, 0.5, 1.0, 1.0)  # Light blue (low risk)

                # Apply highlight color
                obj.color = highlight_color
                obj.hide_viewport = False
                obj.hide_select = False
                obj.select_set(True)  # Select for visibility

                # Make appear in front (helps with occlusion)
                if hasattr(obj, 'show_in_front'):
                    obj.show_in_front = True


        return highlighted

    def _restore_element_highlighting_viewport(self, highlighted: List[Dict]):
        """Restore elements to original viewport state."""
        for item in highlighted:
            obj = item['object']
            obj.color = item['color']
            obj.hide_viewport = item['hide_viewport']
            obj.hide_select = item['hide_select']
            obj.select_set(item['select'])

            if hasattr(obj, 'show_in_front'):
                obj.show_in_front = False

    def _hide_distant_objects(self, center: mathutils.Vector, radius: float) -> List:
        """
        Hide objects beyond radius from center to reduce render complexity.

        PERFORMANCE: Returns empty list - RENDERING DISABLED for large scenes!
        Instead, BCF export will use viewpoint-only mode (no snapshots).

        This is a pragmatic fix for 49K+ element scenes where rendering
        is prohibitively slow (30s+ per snapshot × 30 clashes = 15+ minutes).

        Args:
            center: Center point (clash location)
            radius: Radius in meters

        Returns:
            Empty list (no hiding performed)
        """
        import time
        start_time = time.time()

        # DISABLED: Return empty list to skip rendering
        # The operator should detect this and fall back to viewpoint-only BCF
        print(f"  Snapshot rendering SKIPPED (large scene optimization)")
        print(f"  BCF will export with viewpoints only (no PNG images)")

        return []  # Return empty - no objects hidden, render will be fast but ugly

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

    def _optimize_png_size(self, image_data: bytes, target_kb: int) -> bytes:
        """
        Optimize PNG file size to meet target.

        Uses PIL/Pillow to reduce quality/resolution if needed.
        Falls back to original if PIL not available.
        """
        try:
            from PIL import Image
            import io

            # Load image
            img = Image.open(io.BytesIO(image_data))

            # Try compression first
            output = io.BytesIO()
            img.save(output, format='PNG', optimize=True, compress_level=9)
            optimized_data = output.getvalue()

            # If still too large, reduce resolution
            if len(optimized_data) / 1024 > target_kb:
                scale = (target_kb * 1024 / len(optimized_data)) ** 0.5
                new_size = (int(img.width * scale * 0.9), int(img.height * scale * 0.9))
                img_resized = img.resize(new_size, Image.LANCZOS)

                output = io.BytesIO()
                img_resized.save(output, format='PNG', optimize=True, compress_level=9)
                optimized_data = output.getvalue()

            final_size_kb = len(optimized_data) / 1024
            print(f"    Optimized: {len(image_data)/1024:.0f}KB → {final_size_kb:.0f}KB")

            return optimized_data

        except ImportError:
            print("    Note: PIL/Pillow not available for size optimization")
            return image_data
        except Exception as e:
            print(f"    Warning: Optimization failed: {e}")
            return image_data

    def _render_viewport_to_image(self, filepath: Path, width: int, height: int) -> bool:
        """
        Render current viewport view to image file (clean render, no UI).

        Uses viewport render for speed (~1s instead of ~10s with full render).

        Args:
            filepath: Output PNG file path
            width: Image width in pixels
            height: Image height in pixels

        Returns:
            True if successful, False otherwise
        """
        temp_camera = None
        original_camera = None
        original_settings = None

        try:
            # Store original render settings
            original_settings = self._store_render_settings()
            scene = bpy.context.scene
            original_camera = scene.camera

            # Find 3D viewport to get current view
            region_3d = None
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    space = area.spaces.active
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            region_3d = space.region_3d
                            break
                    if region_3d:
                        break

            if not region_3d:
                print("  Error: No 3D viewport region_3d found")
                return False

            # Create temporary camera matching viewport view
            camera_data = bpy.data.cameras.new(name="BCF_Temp_Viewport_Cam")
            temp_camera = bpy.data.objects.new("BCF_Temp_Viewport_Cam", camera_data)
            scene.collection.objects.link(temp_camera)

            # Copy viewport camera transform to temp camera
            temp_camera.matrix_world = region_3d.view_matrix.inverted()

            # Set camera FOV to match viewport
            camera_data.lens = 35  # Default perspective lens

            # Set as scene camera
            scene.camera = temp_camera

            # Configure render settings for FAST viewport render
            scene.render.resolution_x = width
            scene.render.resolution_y = height
            scene.render.resolution_percentage = 100
            scene.render.image_settings.file_format = 'PNG'
            scene.render.image_settings.color_mode = 'RGB'  # RGB is faster than RGBA

            # Use workbench engine with minimal settings for SPEED
            scene.render.engine = 'BLENDER_WORKBENCH'
            scene.display.shading.light = 'FLAT'  # Flat is fastest (no lighting calc)
            scene.display.shading.color_type = 'OBJECT'  # Show object colors

            # SPEED OPTIMIZATIONS
            scene.render.use_simplify = True
            scene.render.simplify_subdivision = 0  # No subdivision

            # Disable expensive features
            scene.render.use_motion_blur = False
            scene.render.use_border = False

            # Viewport render (much faster than full render)
            scene.render.filepath = str(filepath)
            bpy.ops.render.opengl(write_still=True)  # FAST: viewport render instead of full render

            return True

        except Exception as e:
            print(f"  Error rendering viewport: {e}")
            import traceback
            traceback.print_exc()
            return False

        finally:
            # Cleanup: Remove temp camera and restore settings
            if temp_camera:
                bpy.data.objects.remove(temp_camera, do_unlink=True)
            if original_camera:
                bpy.context.scene.camera = original_camera
            if original_settings:
                self._restore_render_settings(original_settings)

    def set_viewport_to_viewpoint(self, viewpoint_data: Dict) -> bool:
        """
        Set Blender viewport camera to match viewpoint data.

        Useful for positioning view before taking screenshots.

        Args:
            viewpoint_data: Dict with camera, target, up

        Returns:
            True if successful, False if viewport not found
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

            # No 3D viewport found
            return False

        except Exception as e:
            logger.debug(f"Failed to set viewport: {e}")
            return False
