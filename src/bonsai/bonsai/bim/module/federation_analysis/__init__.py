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
    # NOTE: DisciplineClashCandidate is auto-registered by Blender when
    # BIMClashProperties (in clash module) is registered, because it's referenced
    # in CollectionProperty(type=DisciplineClashCandidate). Explicit registration
    # here causes "already registered" error.
    # prop.DisciplineClashCandidate,

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

    # Gizmo operators and menu
    gizmo.BIM_OT_change_clash_status,
    gizmo.BIM_OT_navigate_clash,
    gizmo.BIM_MT_clash_gizmo_context_menu,

    # Gizmos (MUST be in classes tuple for Blender to monitor poll())
    gizmo.ClashMarkerGizmo,
    gizmo.ClashMarkerGizmoGroup,

    # Clash Adjustment operators
    operator.BIM_OT_analyze_clash_groups,
    operator.BIM_OT_suggest_resolutions,
    operator.BIM_OT_select_resolution_option,

    # Phase 1.5 + Phase 2 operators
    operator.BIM_OT_preview_resolution,
    operator.BIM_OT_apply_resolution,
    operator.BIM_OT_submit_resolution_feedback,
    operator.BIM_OT_change_preset,
    operator.BIM_OT_clear_preview,

    # BCF Export
    operator.BIM_OT_export_bcf,

    # Report Generation
    operator.BIM_OT_generate_clash_resolution_report,

    # UI Lists
    ui.BIM_UL_discipline_clashes,
    # Note: BIM_UL_clash_groups and BIM_UL_resolution_options not used in POC
    # POC reads directly from database, no collection properties needed

    # Panels
    ui.BIM_PT_federation_clash_detection,
    ui.BIM_PT_federation_lod_visualization,
    ui.BIM_PT_clash_adjustment,
)


def register():
    """Register federation_analysis module - classes are auto-registered by bim/__init__.py"""
    # NOTE: Classes are registered by bim/__init__.py via the classes tuple above.
    # This function is only for additional setup (properties, handlers, etc.)

    # NOTE: Property injection disabled - properties are now statically defined
    # in bonsai/bim/module/clash/prop.py BIMClashProperties class.
    # Dynamic property injection fails because BIMClashProperties is already registered.
    # prop.register_federation_properties()

    print("✓ federation_analysis module registered")


def unregister():
    """Unregister federation_analysis module - classes are auto-unregistered by bim/__init__.py"""
    # NOTE: Classes are unregistered by bim/__init__.py.
    # This function is only for cleanup (properties, handlers, etc.)

    # NOTE: Property removal disabled - properties are statically defined in clash module
    # prop.unregister_federation_properties()
    pass
