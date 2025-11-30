"""
Digital Twin (Tandem Alternative) Module
Open-source facilities management and IoT integration for IFC buildings

Phase 1: Asset Management
- Import equipment from IFC models
- Track asset metadata, lifecycle, warranties
- Visualize assets in 3D by condition
- Export asset reports
"""

import bpy

# Module info
bl_info = {
    "name": "Digital Twin - Asset Management",
    "description": "Open-source facilities management (Tandem alternative)",
    "author": "red1oon",
    "version": (1, 0, 0),
    "blender": (4, 2, 0),
    "category": "BIM",
}

# Import submodules
from . import operator
from . import ui


def register():
    """Register all Blender classes"""
    operator.register()
    ui.register()
    print("Digital Twin module loaded")


def unregister():
    """Unregister all Blender classes"""
    ui.unregister()
    operator.unregister()


if __name__ == "__main__":
    register()
