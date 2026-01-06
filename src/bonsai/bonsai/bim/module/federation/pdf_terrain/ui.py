# Bonsai - OpenBIM Blender Add-on
# PDF Terrain - UI Module

"""
PDF Terrain UI Panel
====================
N Panel UI for PDF terrain extraction.
Simple workflow: Pick PDF -> Generate -> Save
"""

import bpy
from bpy.types import Panel


class BIM_PT_pdf_terrain(Panel):
    """PDF Terrain Extraction - N Sidebar"""
    bl_label = "PDF Terrain"
    bl_idname = "BIM_PT_pdf_terrain"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "PDF Terrain"

    def draw(self, context):
        layout = self.layout
        props = context.scene.PDFTerrainProperties

        # Header
        header_box = layout.box()
        header_box.label(text="PDF Survey to 3D Terrain", icon="WORLD")
        col = header_box.column(align=True)
        col.scale_y = 0.8
        col.label(text="Extract elevation points from PDF")
        col.label(text="Generate TIN mesh for BIM/CAD")

        layout.separator()

        # Step 1: Pick PDF
        box = layout.box()
        box.label(text="1. Select PDF File", icon="FILE")

        row = box.row()
        row.scale_y = 1.3
        row.operator("bim.pdf_terrain_pick_file", text="Pick PDF", icon="FILEBROWSER")

        if props.pdf_path:
            col = box.column(align=True)
            col.scale_y = 0.8
            # Show just filename
            import os
            filename = os.path.basename(props.pdf_path)
            col.label(text=f"File: {filename}", icon="CHECKMARK")

        layout.separator()

        # Step 2: Generate
        box = layout.box()
        box.label(text="2. Generate Terrain", icon="MESH_GRID")

        row = box.row()
        row.scale_y = 1.5
        row.enabled = bool(props.pdf_path)
        row.operator("bim.pdf_terrain_generate", text="Generate", icon="PLAY")

        # Status
        if props.status_message:
            col = box.column(align=True)
            col.scale_y = 0.8
            icon = "INFO" if "Error" not in props.status_message else "ERROR"
            col.label(text=props.status_message, icon=icon)

        if props.point_count > 0:
            col = box.column(align=True)
            col.scale_y = 0.8
            col.label(text=f"Points extracted: {props.point_count}", icon="VERTEXSEL")

        layout.separator()

        # Step 3: Save
        box = layout.box()
        box.label(text="3. Save Output", icon="FILE_TICK")

        row = box.row()
        row.scale_y = 1.5
        row.enabled = props.mesh_generated
        row.operator("bim.pdf_terrain_save", text="Export .ifc", icon="EXPORT")

        if props.output_path:
            col = box.column(align=True)
            col.scale_y = 0.8
            col.label(text=f"Saved to: {props.output_path}", icon="CHECKMARK")

        # Info section
        layout.separator()
        info_box = layout.box()
        info_box.label(text="Output File:", icon="INFO")
        col = info_box.column(align=True)
        col.scale_y = 0.7
        col.label(text="  survey.ifc - For Revit/AutoCAD import")
        col.label(text="  (Use File > Save to save .blend manually)")
