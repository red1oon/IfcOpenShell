# Bonsai - OpenBIM Blender Add-on
# Copyright (C) 2025 Your Engineering Firm
#
# This file is part of Bonsai.
#
# Bonsai is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
Federation Analysis Module
===========================

Advanced analysis tools for federated BIM models using database-driven workflows.

Submodules:
- clash: Database-driven clash detection with interactive visualization
- routing: MEP conduit routing with A* pathfinding
- visualization: GPU-accelerated BIM visualization (bbox, semantic, GPU overlays)
- shared: Common utilities (database, coordinates, spatial index)

This module extracts federation-specific functionality from Bonsai's core modules
to maintain clean separation and prevent conflicts with upstream updates.
"""

import bpy
from . import ui, prop, operator
from .clash import gizmo

classes = (
    # Properties
    prop.DisciplineClashCandidate,

    # Operators - Clash Detection
    operator.BIM_OT_clash_by_discipline,
    operator.BIM_OT_select_discipline_clash,
    operator.BIM_OT_analyze_bbox_candidates,
    operator.BIM_OT_visualize_selected_discipline_clashes,
    operator.BIM_OT_deselect_all_clashes,
    operator.BIM_OT_clear_discipline_clash_visualization,
    operator.BIM_OT_enable_clash_gpu_visualization,
    operator.BIM_OT_disable_clash_gpu_visualization,
    operator.BIM_OT_enable_clash_gizmo_visualization,
    operator.BIM_OT_disable_clash_gizmo_visualization,
    operator.BIM_OT_load_clash_geometry,

    # Operators - Visualization
    operator.BIM_OT_enable_bbox_visualization,
    operator.BIM_OT_disable_bbox_visualization,
    operator.BIM_OT_enable_semantic_proxy_visualization,
    operator.BIM_OT_disable_semantic_proxy_visualization,
    operator.BIM_OT_enable_full_geometry_visualization,
    operator.BIM_OT_disable_full_geometry_visualization,

    # UI Lists
    ui.BIM_UL_discipline_clashes,

    # Panels
    ui.BIM_PT_federation_clash_detection,
    ui.BIM_PT_federation_lod_visualization,
)


def register():
    """Register federation_analysis module classes and inject properties into clash module"""
    for cls in classes:
        bpy.utils.register_class(cls)

    # Register gizmo classes (GizmoGroup uses different registration)
    bpy.utils.register_class(gizmo.ClashMarkerGizmo)
    bpy.utils.register_class(gizmo.ClashMarkerGizmoGroup)

    # Inject our custom properties into BIMClashProperties
    prop.register_federation_properties()


def unregister():
    """Unregister federation_analysis module classes and remove injected properties"""
    # Remove injected properties from BIMClashProperties
    prop.unregister_federation_properties()

    # Unregister gizmo classes
    bpy.utils.unregister_class(gizmo.ClashMarkerGizmoGroup)
    bpy.utils.unregister_class(gizmo.ClashMarkerGizmo)

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
