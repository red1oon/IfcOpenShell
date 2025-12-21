# Bonsai - OpenBIM Blender Add-on
# PDF Terrain Extraction Module
#
# This file is part of Bonsai.
#
# Bonsai is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
PDF Terrain Module
==================
Extracts terrain/topography from survey PDFs using Google Vision API.
Generates TIN mesh and exports to .blend + .ifc files.

Workflow:
1. User picks PDF file
2. Google Vision extracts elevation points + contours
3. TIN mesh generated from extracted points
4. Mesh displayed in viewport
5. User saves -> .blend + .ifc in same folder as PDF
"""

import bpy
from . import ui, operator

# Expose classes for registration by parent federation module
classes = (
    # Properties (must be registered before UI that uses them)
    operator.PDFTerrainProperties,
    # Operators
    operator.BIM_OT_pdf_terrain_pick_file,
    operator.BIM_OT_pdf_terrain_generate,
    operator.BIM_OT_pdf_terrain_save,
    # UI Panel
    ui.BIM_PT_pdf_terrain,
)


def register():
    """Called by federation module to set up Scene properties"""
    # Attach properties to Scene (classes are registered by federation module)
    bpy.types.Scene.PDFTerrainProperties = bpy.props.PointerProperty(
        type=operator.PDFTerrainProperties
    )
    print("  PDF Terrain properties registered")


def unregister():
    """Called by federation module to clean up"""
    if hasattr(bpy.types.Scene, "PDFTerrainProperties"):
        del bpy.types.Scene.PDFTerrainProperties
