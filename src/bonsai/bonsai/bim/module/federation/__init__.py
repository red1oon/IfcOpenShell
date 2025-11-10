# Bonsai - OpenBIM Blender Add-on
# Copyright (C) 2025 Your Engineering Firm
#
# This file is part of Bonsai.
#
# Bonsai is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Bonsai is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Bonsai.  If not, see <http://www.gnu.org/licenses/>.

"""
Federation Module - Multi-Model Coordination & Analysis
--------------------------------------------------------
Consolidated module for federated BIM workflows including:

Core Infrastructure:
- Spatial indexing and preprocessing (core/)
- Multi-stage geometry loading (loading/)
- Database extraction and querying

Analysis Features:
- Clash detection with intelligent grouping (clash/)
- BCF 2.1 export with snapshots (bcf/)
- Bill of Quantities export (boq/)
- Interactive 3D visualization (visualization/)

This module enables spatial queries across multiple discipline IFC files without
merging, solving spatial hierarchy mismatch problems through coordinate-based queries.
"""

import bpy
from bpy.app.handlers import persistent
from pathlib import Path
from . import ui, prop, operator, discipline_legend, cache_monitor
from .loading.unified_progressive_loader import GlassOutlineLoader
from .clash import gizmo

# Expose classes so main __init__.py can find them
classes = (
    # Core Federation Properties & Operators
    prop.FederatedFile,
    prop.DisciplineClashCandidate,
    prop.BIMFederationProperties,
    operator.AddFederatedFile,
    operator.RemoveFederatedFile,
    operator.SelectFederatedFile,
    operator.SelectFederatedFolder,
    operator.PreprocessFederatedModels,
    operator.LoadFederationIndex,
    operator.UnloadFederationIndex,
    operator.QueryFederationIndex,
    operator.LoadFederationModel,
    operator.LoadFederationStage2Background,
    operator.DetectFederationClashes,
    operator.PreviewFederationViewport,
    operator.LoadSolidFederationViewport,
    operator.LoadFullFederationViewport,
    operator.ReloadFederationViewport,
    operator.UnloadFederationViewport,
    operator.ExtractSampleDatabase,
    operator.ExtractFullDatabase,
    operator.RedoSampleExtraction,
    GlassOutlineLoader,

    # Cache monitoring
    cache_monitor.MonitorCacheBaking,

    # Clash Detection Operators
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

    # Visualization Operators
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
    gizmo.ClashMarkerGizmo,
    gizmo.ClashMarkerGizmoGroup,

    # Clash Resolution Operators
    operator.BIM_OT_analyze_clash_groups,
    operator.BIM_OT_suggest_resolutions,
    operator.BIM_OT_select_resolution_option,
    operator.BIM_OT_preview_resolution,
    operator.BIM_OT_apply_resolution,
    operator.BIM_OT_submit_resolution_feedback,
    operator.BIM_OT_change_preset,
    operator.BIM_OT_clear_preview,
    operator.BIM_OT_preview_clash_group,

    # BCF Export
    operator.BIM_OT_export_bcf,

    # Report Generation
    operator.BIM_OT_generate_clash_resolution_report,

    # BOQ (Bill of Quantities) Export
    operator.BIM_OT_export_comprehensive_boq,
    operator.BIM_OT_open_boq_report,
    operator.BIM_OT_regenerate_boq_report,

    # Natural Language Query (NLP)
    operator.BIM_OT_execute_nlp_query,
    operator.BIM_OT_set_nlp_query,
    operator.BIM_OT_clear_nlp_results,
    operator.BIM_OT_export_nlp_results,

    # UI Panels and Lists
    ui.BIM_PT_federation,
    ui.BIM_UL_federated_files,
    ui.BIM_UL_discipline_clashes,
    ui.BIM_PT_federation_clash_detection,
    ui.BIM_PT_federation_lod_visualization,
    ui.BIM_PT_clash_adjustment,
    ui.BIM_PT_boq_export,
    ui.BIM_PT_nlp_query,
)

@persistent
def restore_federation_index_on_load(dummy):
    """
    Restore federation index when .blend file is loaded.

    The federation database path is stored in the .blend file,
    but the FederationIndex Python object is not. This handler
    recreates the index when the file is opened.
    """
    if not hasattr(bpy.context, 'scene'):
        return

    props = bpy.context.scene.BIMFederationProperties

    # Check if database path is set and file exists
    if props.federation_database_path:
        # Resolve Blender's // relative path prefix
        db_path_resolved = bpy.path.abspath(props.federation_database_path)

        if Path(db_path_resolved).exists():
            try:
                from .core.spatial_index import FederationIndex

                # Only register if not already loaded
                if not hasattr(bpy.types.WindowManager, 'federation_index'):
                    print(f"Restoring federation index: {db_path_resolved}")

                    index = FederationIndex(db_path_resolved)
                    index.build()

                    bpy.types.WindowManager.federation_index = index

                    stats = index.get_statistics()
                    props.index_loaded = True
                    props.total_elements = stats['total_elements']
                    props.loaded_disciplines = ', '.join(stats['disciplines'])

                    # Update displayed path to resolved absolute path (remove // prefix)
                    props.federation_database_path = db_path_resolved

                    print(f"✓ Federation index restored: {stats['total_elements']:,} elements")
                    print(f"  Database path updated to: {db_path_resolved}")
            except Exception as e:
                print(f"⚠ Could not restore federation index: {e}")


def register():
    """Called when addon is enabled"""
    # Attach properties to Blender's Scene
    bpy.types.Scene.BIMFederationProperties = bpy.props.PointerProperty(
        type=prop.BIMFederationProperties
    )

    # Register federation analysis properties on BIMClashProperties
    prop.register_federation_properties()

    # Register load handler to restore federation index
    if restore_federation_index_on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(restore_federation_index_on_load)

    print("✓ federation module registered (consolidated)")

def unregister():
    """Called when addon is disabled - cleanup"""
    # Remove load handler
    if restore_federation_index_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(restore_federation_index_on_load)

    # Unregister federation analysis properties from BIMClashProperties
    prop.unregister_federation_properties()

    # Remove properties from Scene
    del bpy.types.Scene.BIMFederationProperties
