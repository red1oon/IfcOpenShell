# Bonsai - OpenBIM Blender Add-on
# PDF Terrain - Operators

"""
PDF Terrain Operators
=====================
Operators for PDF terrain extraction workflow.
"""

import bpy
import os
import sys
import json
import subprocess
from pathlib import Path
from bpy.props import StringProperty, IntProperty, BoolProperty, PointerProperty
from bpy.types import Operator, PropertyGroup


class PDFTerrainProperties(PropertyGroup):
    """Properties for PDF Terrain extraction"""

    pdf_path: StringProperty(
        name="PDF Path",
        description="Path to the survey PDF file",
        default="",
        subtype='FILE_PATH'
    )

    output_path: StringProperty(
        name="Output Path",
        description="Path where output files were saved",
        default=""
    )

    status_message: StringProperty(
        name="Status",
        description="Current status message",
        default=""
    )

    point_count: IntProperty(
        name="Point Count",
        description="Number of elevation points extracted",
        default=0
    )

    mesh_generated: BoolProperty(
        name="Mesh Generated",
        description="Whether terrain mesh has been generated",
        default=False
    )


class BIM_OT_pdf_terrain_pick_file(Operator):
    """Pick a PDF file for terrain extraction"""
    bl_idname = "bim.pdf_terrain_pick_file"
    bl_label = "Pick PDF File"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: StringProperty(
        subtype='FILE_PATH',
        default=""
    )

    filter_glob: StringProperty(
        default="*.pdf;*.png",
        options={'HIDDEN'}
    )

    def execute(self, context):
        props = context.scene.PDFTerrainProperties
        props.pdf_path = self.filepath
        props.status_message = "PDF selected. Click Generate."
        props.mesh_generated = False
        props.point_count = 0
        props.output_path = ""

        # Load image preview if PNG file selected
        file_path = Path(bpy.path.abspath(self.filepath))
        if file_path.suffix.lower() in ['.png', '.jpg', '.jpeg']:
            self._load_image_preview(context, file_path)

        return {'FINISHED'}

    def _load_image_preview(self, context, image_path):
        """Load image as reference in viewport for preview"""
        try:
            # Remove existing preview if any
            if "Survey_Preview_Image" in bpy.data.objects:
                bpy.data.objects.remove(bpy.data.objects["Survey_Preview_Image"], do_unlink=True)

            # Load image
            abs_path = str(image_path.absolute())
            img = bpy.data.images.load(abs_path, check_existing=True)

            # Create image empty at origin
            bpy.ops.object.empty_add(type='IMAGE', location=(0, 0, 0))
            empty = context.active_object
            empty.name = "Survey_Preview_Image"
            empty.data = img
            empty.empty_image_side = 'FRONT'
            empty.empty_image_offset = (0, 0)
            empty.empty_display_size = 100.0  # Temporary preview size

            # Frame the image in viewport
            bpy.ops.view3d.view_selected()

        except Exception as e:
            print(f"Could not load image preview: {e}")

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class BIM_OT_pdf_terrain_generate(Operator):
    """Extract elevation points from PDF and generate terrain mesh"""
    bl_idname = "bim.pdf_terrain_generate"
    bl_label = "Generate Terrain"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.PDFTerrainProperties

        if not props.pdf_path:
            self.report({'ERROR'}, "No PDF file selected")
            return {'CANCELLED'}

        pdf_path = Path(bpy.path.abspath(props.pdf_path))
        if not pdf_path.exists():
            self.report({'ERROR'}, f"File not found: {pdf_path}")
            return {'CANCELLED'}

        props.status_message = "Processing PDF..."

        try:
            # Get the pipeline scripts directory
            module_dir = Path(__file__).parent.parent / "pdf2blend" / "scripts"
            extract_script = module_dir / "survey_extract_pipeline.py"
            blend_script = module_dir / "survey_to_blend.py"

            if not extract_script.exists():
                self.report({'ERROR'}, f"Extract script not found: {extract_script}")
                return {'CANCELLED'}

            # Output paths
            output_dir = pdf_path.parent
            json_path = output_dir / f"{pdf_path.stem}_extracted.json"
            gv_cache_path = output_dir / f"{pdf_path.stem}_GV.json"  # Raw Google Vision cache
            vision_raw_path = output_dir / "vision_raw_response.json"  # Temp file from --dump-raw
            png_path = pdf_path.with_suffix('.png') if pdf_path.suffix.lower() == '.pdf' else pdf_path

            # Step 1: Extract elevation points using Google Vision
            props.status_message = "Extracting points with Google Vision..."

            # Check if we have cached Google Vision response
            use_gv_cache = gv_cache_path.exists()

            if use_gv_cache:
                props.status_message = "Using cached Google Vision data (no API call)..."
                self.report({'INFO'}, f"Using GV cache: {gv_cache_path.name} - no API charges")

                # Use cached GV response
                cmd = [
                    sys.executable,
                    str(extract_script),
                    str(png_path if png_path.exists() else pdf_path),
                    str(json_path),
                    "--from-cache", str(gv_cache_path),
                    "--dpi", "300"
                ]
            else:
                # Need to call Google Vision API
                # Check for credentials
                creds_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', '')
                if not creds_path or not Path(creds_path).exists():
                    # Try default location
                    default_creds = Path("C:/Dev/bonsai-extensions/WORK_DIR/vision-api.json")
                    if default_creds.exists():
                        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(default_creds)
                    else:
                        self.report({'ERROR'}, "Google Vision credentials not found")
                        return {'CANCELLED'}

                self.report({'WARNING'}, "Calling Google Vision API - this will incur charges (~$0.01-0.05)")
                props.status_message = "Calling Google Vision API (first time)..."

                # Call API and dump raw response
                # Note: API key from environment variable GOOGLE_APPLICATION_CREDENTIALS (secure, not in code)
                cmd = [
                    sys.executable,
                    str(extract_script),
                    str(png_path if png_path.exists() else pdf_path),
                    str(json_path),
                    "--dump-raw",
                    "--dpi", "300"
                ]

            result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(module_dir))

            # If we called API with --dump-raw, rename the raw response for future caching
            if not use_gv_cache and vision_raw_path.exists():
                vision_raw_path.rename(gv_cache_path)
                self.report({'INFO'}, f"Saved GV cache: {gv_cache_path.name} (reusable for future runs)")

            if result.returncode != 0:
                # Check if we have cached JSON
                if json_path.exists():
                    props.status_message = "Using cached extraction data..."
                else:
                    self.report({'ERROR'}, f"Extraction failed: {result.stderr}")
                    props.status_message = "Error: Extraction failed"
                    return {'CANCELLED'}

            # Load extracted points
            if not json_path.exists():
                self.report({'ERROR'}, "No extraction output found")
                return {'CANCELLED'}

            with open(json_path, 'r') as f:
                data = json.load(f)

            points = data.get('ground_elevations', [])
            props.point_count = len(points)

            if props.point_count == 0:
                self.report({'ERROR'}, "No elevation points extracted")
                props.status_message = "Error: No points found"
                return {'CANCELLED'}

            # Step 2: Create terrain mesh in current scene
            props.status_message = f"Creating mesh from {props.point_count} points..."

            # Create mesh directly in Blender
            self._create_terrain_mesh(context, points, data)

            props.mesh_generated = True
            props.status_message = f"Generated terrain with {props.point_count} points"
            self.report({'INFO'}, f"Terrain generated: {props.point_count} points")

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Error: {str(e)}")
            props.status_message = f"Error: {str(e)}"
            return {'CANCELLED'}

    def _create_terrain_mesh(self, context, points, data):
        """Create terrain point cloud with reference image (matches standalone script)"""
        from mathutils import Vector

        # Setup logging
        log_path = Path(bpy.path.abspath("//")) / "pdf_terrain_debug.log"
        if not log_path.parent.exists():
            log_path = Path.home() / "pdf_terrain_debug.log"

        # Get metadata
        meta = data.get('metadata', {})
        image_width = meta.get('image_dimensions', {}).get('width', 9934)
        image_height = meta.get('image_dimensions', {}).get('height', 7017)
        scale = meta.get('scale', 0.0423)
        affine_transform = meta.get('affine_transform')
        y_scale_factor = meta.get('y_scale_factor', 1.0)

        # Log metadata
        props = context.scene.PDFTerrainProperties
        pdf_path = Path(bpy.path.abspath(props.pdf_path))
        gv_cache_path = pdf_path.parent / f"{pdf_path.stem}_GV.json"

        def log(msg):
            """Log to both file and console"""
            print(f"[PDF_TERRAIN] {msg}")
            with open(log_path, 'a') as f:
                f.write(f"{msg}\n")

        # Clear log file
        with open(log_path, 'w') as f:
            f.write("")

        log("=== PDF Terrain Debug Log ===")
        log(f"API Security: Key from environment variable (not stored in code)")
        log(f"GV Cache: {gv_cache_path.name} ({'EXISTS - no API call' if gv_cache_path.exists() else 'NOT FOUND - will call API'})")
        log(f"")
        log(f"Metadata:")
        log(f"  Image: {image_width} x {image_height}")
        log(f"  Scale: {scale}")
        log(f"  Y Scale Factor: {y_scale_factor}")
        log(f"  Affine Transform: {'DISABLED (testing simple)' if affine_transform else 'None'}")

        # Get image path
        image_path = meta.get('source', '')
        if not image_path or not Path(image_path).exists():
            # Try to find image from props
            props = context.scene.PDFTerrainProperties
            pdf_path = Path(bpy.path.abspath(props.pdf_path))
            if pdf_path.suffix.lower() == '.png':
                image_path = str(pdf_path)

        # Calculate world dimensions
        world_width = image_width * scale
        world_height = image_height * scale

        log(f"  World Dimensions: {world_width:.2f} x {world_height:.2f}")
        log(f"  Image Path: {image_path}")
        log(f"  Point Count: {len(points)}")

        # Remove preview image if it exists
        if "Survey_Preview_Image" in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects["Survey_Preview_Image"], do_unlink=True)

        # Create collections
        ground_col = self._get_or_create_collection("Ground_Elevations")
        invert_col = self._get_or_create_collection("Invert_Levels")
        labels_col = self._get_or_create_collection("Labels")

        # Create reference image at Z=40.0
        if image_path and Path(image_path).exists():
            self._create_reference_image(image_path, world_width, world_height)

        # Create survey points as spheres
        point_log = []
        for idx, pt in enumerate(points):
            # Convert pixel to world coordinates using same logic as standalone
            px = pt.get('x', 0)
            py = pt.get('y', 0)
            pz = pt.get('z', 0)

            x_world, y_world, z_world = self._pixel_to_world(
                px, py, pz, image_height, scale, affine_transform, y_scale_factor
            )

            # Log first 3 points
            if idx < 3:
                point_log.append(f"  Point {idx}: pixel({px:.0f}, {py:.0f}, {pz:.3f}) -> world({x_world:.2f}, {y_world:.2f}, {z_world:.2f})")

            # Create sphere for point
            bpy.ops.mesh.primitive_uv_sphere_add(
                radius=0.05,
                segments=8,
                ring_count=6,
                location=(x_world, y_world, z_world)
            )
            point_obj = context.active_object
            point_obj.name = f"GroundLevel_{pz:.3f}"

            # Add custom properties
            point_obj["SurveyPointType"] = "GroundElevation"
            point_obj["PointID"] = pt.get('id', '')
            point_obj["Elevation"] = pz
            point_obj["PixelX"] = px
            point_obj["PixelY"] = py

            # Apply green material
            mat = bpy.data.materials.new(name=f"Mat_Ground_{pz}")
            mat.use_nodes = True
            principled = mat.node_tree.nodes.get('Principled BSDF')
            principled.inputs['Base Color'].default_value = (0.8, 0.3, 0.1, 1.0)  # Orange like standalone

            point_obj.data.materials.append(mat)

            # Move to collection - remove from all existing collections first
            for col in point_obj.users_collection:
                col.objects.unlink(point_obj)
            ground_col.objects.link(point_obj)

            # Create text label
            bpy.ops.object.text_add(location=(x_world, y_world, z_world + 0.15))
            text_obj = context.active_object
            text_obj.name = f"Label_{pt.get('id', '')}"
            text_obj.data.body = f"{pz:.3f}"
            text_obj.data.size = 1.2
            text_obj.data.extrude = 0.02
            text_obj.rotation_euler = (1.5708, 0, 0)

            # Move to labels collection - remove from all existing collections first
            for col in text_obj.users_collection:
                col.objects.unlink(text_obj)
            labels_col.objects.link(text_obj)

        # Write point log
        log("")
        log("First 3 Points (using SIMPLE transform - affine disabled for testing):")
        for pt in point_log:
            log(pt)

        # Set up camera for top-down orthographic view (like standalone)
        log("")
        log("Setting up camera view...")

        # Create camera centered above terrain
        camera_x = world_width / 2
        camera_y = world_height / 2
        camera_z = max(world_width, world_height) * 1.2  # Height adjusted to fit viewport

        bpy.ops.object.camera_add(location=(camera_x, camera_y, camera_z))
        camera = context.active_object
        camera.name = "PDF_Terrain_Camera"
        camera.rotation_euler = (0, 0, 0)  # Look straight down
        context.scene.camera = camera

        # Set camera to orthographic for technical drawing view
        camera.data.type = 'ORTHO'
        camera.data.ortho_scale = max(world_width, world_height) * 1.1

        log(f"  Camera: ({camera_x:.1f}, {camera_y:.1f}, {camera_z:.1f})")
        log(f"  Ortho scale: {camera.data.ortho_scale:.1f}")

        # Switch viewport to camera view and set shading
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.type = 'SOLID'
                        # Switch to camera view
                        space.region_3d.view_perspective = 'CAMERA'
                        break

    def _pixel_to_world(self, px, py, pz, image_height, scale, affine_transform=None, y_scale_factor=1.0):
        """Convert pixel coordinates to world coordinates (exact copy from standalone script)"""
        # TEMPORARY: Force simple transform to test (ignore affine for now)
        if False and affine_transform is not None:  # Disabled for testing
            # Use affine transform: [x, y] = A @ [px, py, 1]
            x = affine_transform[0][0] * px + affine_transform[0][1] * py + affine_transform[0][2]
            y = affine_transform[1][0] * px + affine_transform[1][1] * py + affine_transform[1][2]
        else:
            # Fallback: simple linear transform
            y_flipped = image_height - py
            x = px * scale
            y = y_flipped * scale * y_scale_factor

        z = pz  # Already in meters
        return (x, y, z)

    def _get_or_create_collection(self, name):
        """Get existing collection or create new one"""
        if name in bpy.data.collections:
            return bpy.data.collections[name]
        col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(col)
        return col

    def _create_reference_image(self, image_path, world_width, world_height):
        """Create reference image empty at Z=40.0"""
        abs_path = str(Path(image_path).absolute())
        img = bpy.data.images.load(abs_path, check_existing=True)

        bpy.ops.object.empty_add(type='IMAGE', location=(0, 0, 40.0))
        empty = bpy.context.active_object
        empty.name = "Survey_Reference_Image"
        empty.data = img
        empty.empty_image_side = 'FRONT'
        empty.empty_image_offset = (0, 0)
        empty.empty_display_size = 1.0
        empty.scale = (world_width, world_width, 1.0)  # Matches standalone script
        empty.lock_location = (False, False, False)
        empty.lock_rotation = (True, True, True)
        empty.lock_scale = (True, True, True)


class BIM_OT_pdf_terrain_save(Operator):
    """Save terrain as .blend and .ifc files"""
    bl_idname = "bim.pdf_terrain_save"
    bl_label = "Save Terrain"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.PDFTerrainProperties

        if not props.mesh_generated:
            self.report({'ERROR'}, "No terrain mesh to save")
            return {'CANCELLED'}

        if not props.pdf_path:
            self.report({'ERROR'}, "No PDF path set")
            return {'CANCELLED'}

        pdf_path = Path(bpy.path.abspath(props.pdf_path))
        output_dir = pdf_path.parent
        base_name = pdf_path.stem

        try:
            # Export IFC file only (user saves .blend manually)
            ifc_path = output_dir / f"{base_name}.ifc"

            # Check if IfcOpenShell is available
            try:
                import ifcopenshell
                import ifcopenshell.api

                # Create IFC file with terrain points
                self._export_terrain_ifc(context, ifc_path)
                self.report({'INFO'}, f"Saved IFC: {ifc_path}")

            except ImportError:
                self.report({'ERROR'}, "IfcOpenShell not available - cannot export IFC")
                return {'CANCELLED'}

            props.output_path = str(output_dir)
            props.status_message = f"Saved IFC to {output_dir.name}/"

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Save error: {str(e)}")
            return {'CANCELLED'}

    def _export_terrain_ifc(self, context, ifc_path):
        """Export terrain points as IFC file"""
        import ifcopenshell
        import ifcopenshell.api

        # Find Ground_Elevations collection
        ground_col = bpy.data.collections.get("Ground_Elevations")
        if not ground_col or len(ground_col.objects) == 0:
            self.report({'WARNING'}, "No ground elevation points found to export")
            return

        print(f"[PDF_TERRAIN] Exporting {len(ground_col.objects)} elevation points to IFC...")

        # Create IFC file
        ifc = ifcopenshell.api.run("project.create_file")

        # Create project structure
        project = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcProject", name="Terrain Project")
        site = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcSite", name="Site")

        # Create context
        context3d = ifcopenshell.api.run("context.add_context", ifc, context_type="Model")
        body = ifcopenshell.api.run("context.add_context", ifc,
            context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=context3d)

        # Assign site to project
        ifcopenshell.api.run("aggregate.assign_object", ifc, relating_object=project, products=[site])

        # Export each elevation point as IfcGeographicElement
        terrain_elements = []
        for obj in ground_col.objects:
            if obj.type != 'MESH':
                continue

            # Get elevation and position from custom properties
            elevation = obj.get("Elevation", obj.location.z)
            point_id = obj.get("PointID", obj.name)

            # Create IFC geographic element for this point
            point_elem = ifcopenshell.api.run("root.create_entity", ifc,
                ifc_class="IfcGeographicElement",
                name=f"ElevationPoint_{elevation:.3f}")

            # Add custom properties (Pset)
            pset = ifcopenshell.api.run("pset.add_pset", ifc, product=point_elem, name="Survey_Data")
            ifcopenshell.api.run("pset.edit_pset", ifc, pset=pset, properties={
                "PointID": point_id,
                "Elevation": elevation,
                "PointType": obj.get("SurveyPointType", "GroundElevation"),
                "PixelX": obj.get("PixelX", 0.0),
                "PixelY": obj.get("PixelY", 0.0)
            })

            # Get sphere geometry in world coordinates
            mesh = obj.data
            verts = [(obj.location.x + v.co.x,
                      obj.location.y + v.co.y,
                      obj.location.z + v.co.z) for v in mesh.vertices]
            faces = [[v for v in f.vertices] for f in mesh.polygons]

            # Create geometry representation (sphere)
            if verts and faces:
                representation = ifcopenshell.api.run("geometry.add_mesh_representation", ifc,
                    context=body, vertices=[verts], faces=[faces])
                ifcopenshell.api.run("geometry.assign_representation", ifc,
                    product=point_elem, representation=representation)

            terrain_elements.append(point_elem)

        # Assign all points to site
        if terrain_elements:
            ifcopenshell.api.run("spatial.assign_container", ifc,
                relating_structure=site, products=terrain_elements)

        # Write file
        ifc.write(str(ifc_path))
        print(f"[PDF_TERRAIN] IFC export complete: {len(terrain_elements)} points with survey data")
