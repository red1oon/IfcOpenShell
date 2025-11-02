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

classes = (
    # Properties
    prop.BIMFederationAnalysisProperties,

    # Operators - Clash Detection
    operator.BIM_OT_clash_by_discipline,
    operator.BIM_OT_select_discipline_clash,
    operator.BIM_OT_deselect_all_clashes,
    operator.BIM_OT_clear_discipline_clash_visualization,
    operator.BIM_OT_enable_clash_gpu_visualization,
    operator.BIM_OT_disable_clash_gpu_visualization,
    operator.BIM_OT_enable_clash_gizmo_visualization,
    operator.BIM_OT_disable_clash_gizmo_visualization,

    # Operators - Visualization
    operator.BIM_OT_enable_bbox_visualization,
    operator.BIM_OT_disable_bbox_visualization,
    operator.BIM_OT_enable_semantic_proxy_visualization,
    operator.BIM_OT_disable_semantic_proxy_visualization,

    # Operators - MEP Routing
    operator.BIM_OT_route_conduit,
    operator.BIM_OT_view_conduit,
    operator.BIM_OT_clear_conduit_routes,

    # UI Lists
    ui.BIM_UL_discipline_clashes,

    # Panels
    ui.BIM_PT_federation_analysis_clash,
    ui.BIM_PT_federation_analysis_routing,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.BIMFederationAnalysisProperties = bpy.props.PointerProperty(
        type=prop.BIMFederationAnalysisProperties
    )


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.BIMFederationAnalysisProperties
