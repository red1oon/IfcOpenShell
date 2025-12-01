"""
Digital Twin (Tandem Alternative) Module
Open-source facilities management and IoT integration for IFC buildings

Phase 1: Asset Management
- Import equipment from IFC models
- Track asset metadata, lifecycle, warranties
- Visualize assets in 3D by condition
- Export asset reports

Phase 2: Maintenance Scheduling
- Preventive maintenance scheduling
- Work order management
- Maintenance history tracking

Phase 3: IoT Command Center 🚀
- Animated sensor visualization in 3D viewport
- Real-time building health monitoring
- AI-powered analytics and predictions
- Mission Control style interface
"""

import bpy

# Module info
bl_info = {
    "name": "Digital Twin - Asset Management & IoT",
    "description": "Open-source facilities management (Tandem alternative) with IoT Command Center",
    "author": "red1oon",
    "version": (2, 0, 0),  # Phase 3
    "blender": (4, 2, 0),
    "category": "BIM",
}

# Import submodules
from . import operator
from . import ui
from . import sensor_overlay


def register():
    """Register all Blender classes"""
    operator.register()
    ui.register()
    sensor_overlay.register()
    print("✅ Digital Twin module loaded - Phase 3 IoT Command Center ready")


def unregister():
    """Unregister all Blender classes"""
    sensor_overlay.unregister()
    ui.unregister()
    operator.unregister()


if __name__ == "__main__":
    register()
