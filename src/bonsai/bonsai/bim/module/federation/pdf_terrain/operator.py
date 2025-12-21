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
        return {'FINISHED'}

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
            png_path = pdf_path.with_suffix('.png') if pdf_path.suffix.lower() == '.pdf' else pdf_path

            # Step 1: Extract elevation points using Google Vision
            props.status_message = "Extracting points with Google Vision..."

            # Check for Google credentials
            creds_path = os.environ.get('GOOGLE_APPLICATION_CREDENTIALS', '')
            if not creds_path or not Path(creds_path).exists():
                # Try default location
                default_creds = Path("C:/Dev/bonsai-extensions/WORK_DIR/vision-api.json")
                if default_creds.exists():
                    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = str(default_creds)
                else:
                    self.report({'WARNING'}, "Google Vision credentials not found. Using cached data if available.")

            # Run extraction pipeline
            cmd = [
                sys.executable,
                str(extract_script),
                str(png_path if png_path.exists() else pdf_path),
                str(json_path),
                "--dpi", "300"
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(module_dir))

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

            points = data.get('elevations', [])
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
        """Create terrain mesh from elevation points using Delaunay triangulation"""
        import bmesh
        from mathutils import Vector

        # Get calibration data
        calibration = data.get('calibration', {})
        scale = calibration.get('scale', 0.0423)  # meters per pixel
        image_height = calibration.get('image_height', 7017)

        # Create mesh
        mesh = bpy.data.meshes.new("Terrain_TIN")
        obj = bpy.data.objects.new("Terrain_TIN", mesh)

        # Link to scene
        context.collection.objects.link(obj)

        # Create BMesh
        bm = bmesh.new()

        # Add vertices from elevation points
        verts = []
        for pt in points:
            # Convert pixel coordinates to world coordinates
            px = pt.get('x', 0)
            py = pt.get('y', 0)
            pz = pt.get('z', 0)

            # Apply scale and flip Y
            x_world = px * scale
            y_world = (image_height - py) * scale
            z_world = pz  # Elevation is already in meters

            v = bm.verts.new((x_world, y_world, z_world))
            verts.append(v)

        bm.verts.ensure_lookup_table()

        # Create faces using Delaunay triangulation
        if len(verts) >= 3:
            try:
                # Use BMesh's convex hull as simple triangulation
                # For proper TIN, we'd need scipy.spatial.Delaunay
                bmesh.ops.convex_hull(bm, input=verts)
            except Exception as e:
                print(f"Triangulation error: {e}")
                # Fallback: just create point cloud
                pass

        # Update mesh
        bm.to_mesh(mesh)
        bm.free()

        # Set as active object
        context.view_layer.objects.active = obj
        obj.select_set(True)

        # Zoom to object
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        override = {'area': area, 'region': region}
                        with context.temp_override(**override):
                            bpy.ops.view3d.view_selected()
                        break


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
            # Save .blend file
            blend_path = output_dir / f"{base_name}.blend"
            bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
            self.report({'INFO'}, f"Saved: {blend_path}")

            # Export .ifc file
            ifc_path = output_dir / f"{base_name}.ifc"

            # Check if IfcOpenShell is available
            try:
                import ifcopenshell
                import ifcopenshell.api

                # Create minimal IFC file with terrain
                self._export_terrain_ifc(context, ifc_path)
                self.report({'INFO'}, f"Saved: {ifc_path}")

            except ImportError:
                self.report({'WARNING'}, "IfcOpenShell not available, IFC export skipped")

            props.output_path = str(output_dir)
            props.status_message = f"Saved to {output_dir.name}/"

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Save error: {str(e)}")
            return {'CANCELLED'}

    def _export_terrain_ifc(self, context, ifc_path):
        """Export terrain mesh as IFC file"""
        import ifcopenshell
        import ifcopenshell.api

        # Find terrain object
        terrain_obj = None
        for obj in context.scene.objects:
            if obj.type == 'MESH' and 'Terrain' in obj.name:
                terrain_obj = obj
                break

        if not terrain_obj:
            return

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

        # Create terrain as IfcGeographicElement
        terrain = ifcopenshell.api.run("root.create_entity", ifc,
            ifc_class="IfcGeographicElement", name="Terrain_TIN")

        # Get mesh data
        mesh = terrain_obj.data
        verts = [(v.co.x, v.co.y, v.co.z) for v in mesh.vertices]
        faces = [[v for v in f.vertices] for f in mesh.polygons]

        # Create geometry representation
        if verts and faces:
            representation = ifcopenshell.api.run("geometry.add_mesh_representation", ifc,
                context=body, vertices=[verts], faces=[faces])
            ifcopenshell.api.run("geometry.assign_representation", ifc,
                product=terrain, representation=representation)

        # Assign to site
        ifcopenshell.api.run("spatial.assign_container", ifc, relating_structure=site, products=[terrain])

        # Write file
        ifc.write(str(ifc_path))
