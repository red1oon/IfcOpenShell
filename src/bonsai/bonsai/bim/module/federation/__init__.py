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
from . import ui, prop, operator, discipline_legend, cache_monitor, color_palette
from .loading.unified_progressive_loader import GlassOutlineLoader
from .clash import gizmo
from .tandem import ui as tandem_ui, operator as tandem_operator, sensor_overlay

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
    operator.LoadFullFederationViewportGI,  # GI-enabled version (experimental)
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

    # 4D Schedule Export & Animation
    operator.BIM_OT_generate_construction_schedule,
    operator.BIM_OT_export_mpp_schedule,
    operator.BIM_OT_export_schedule_excel,
    operator.BIM_OT_animate_4d_construction,

    # BOQ (Bill of Quantities) Export
    operator.BIM_OT_export_comprehensive_boq,
    operator.BIM_OT_open_boq_report,
    operator.BIM_OT_regenerate_boq_report,

    # Structural Works - Rebar & Concrete
    prop.BIMStructuralProperties,
    operator.BIM_OT_generate_rebar_structural,
    operator.BIM_OT_export_structural_boq,

    # Natural Language Query (NLP)
    operator.BIM_OT_execute_nlp_query,
    operator.BIM_OT_set_nlp_query,
    operator.BIM_OT_clear_nlp_results,
    operator.BIM_OT_export_nlp_results,

    # UI Panels and Lists
    ui.BIM_PT_federation,
    ui.BIM_UL_federated_files,
    ui.BIM_UL_discipline_clashes,
    ui.BIM_UL_clash_groups,
    ui.BIM_UL_resolution_options,
    ui.BIM_PT_federation_clash_detection,
    ui.BIM_PT_federation_lod_visualization,
    ui.BIM_PT_clash_adjustment,
    ui.BIM_PT_tab_4d_5d,
    ui.BIM_PT_4d_schedule_export,
    ui.BIM_PT_boq_export,
    ui.BIM_PT_structural_works,
    ui.BIM_PT_nlp_query,

    # Color Palette UI (standalone panel)
    color_palette.ColorHistoryItem,
    color_palette.BIMFederationColorProperties,
    color_palette.BIM_OT_apply_palette_color,
    color_palette.BIM_OT_apply_color_to_selected,
    color_palette.BIM_OT_strip_door_materials,
    color_palette.BIM_OT_get_type_from_selection,
    color_palette.BIM_OT_refresh_ifc_types,
    color_palette.BIM_OT_reset_colors,
    color_palette.BIM_OT_save_color_scheme,
    color_palette.BIM_OT_load_color_scheme,
    color_palette.BIM_PT_federation_color_palette,

    # Digital Twin (Tandem) - 6D/7D BIM Operators
    tandem_operator.BIM_OT_import_assets_from_ifc,
    tandem_operator.BIM_OT_import_assets_from_federation,
    tandem_operator.BIM_OT_import_assets_from_csv,
    tandem_operator.BIM_OT_refresh_asset_list,
    tandem_operator.BIM_OT_view_asset_details,
    tandem_operator.BIM_OT_highlight_asset_in_3d,
    tandem_operator.BIM_OT_update_asset_status,
    tandem_operator.BIM_OT_visualize_assets_by_condition,
    tandem_operator.BIM_OT_export_asset_report,
    tandem_operator.BIM_OT_generate_pm_schedule,
    tandem_operator.BIM_OT_create_work_order,
    tandem_operator.BIM_OT_refresh_work_order_list,
    tandem_operator.BIM_OT_complete_work_order,
    tandem_operator.BIM_OT_view_pm_summary,
    # IoT Command Center (Phase 3)
    tandem_operator.BIM_OT_iot_generate_mock_data,
    tandem_operator.BIM_OT_iot_export_analytics,
    tandem_operator.BIM_OT_iot_switch_to_command_center,
    sensor_overlay.BIM_OT_iot_enable_sensor_overlay,
    sensor_overlay.BIM_OT_iot_disable_sensor_overlay,
    # Sensor Actions
    tandem_operator.BIM_OT_view_sensor_history,
    tandem_operator.BIM_OT_create_sensor_alert_rule,
    tandem_operator.BIM_OT_create_sensor_work_order,

    # Digital Twin (Tandem) - 6D/7D BIM UI
    tandem_ui.BIMTandemAssetItem,
    tandem_ui.BIMTandemProperties,
    tandem_ui.BIM_UL_tandem_assets,
    tandem_ui.BIM_PT_tandem_main,
    tandem_ui.BIM_PT_tandem_assets,
    tandem_ui.BIM_PT_tandem_asset_details,
    tandem_ui.BIM_PT_tandem_statistics,
    tandem_ui.BIMTandemWorkOrderItem,
    tandem_ui.BIM_UL_tandem_work_orders,
    tandem_ui.BIM_PT_tandem_maintenance,
    tandem_ui.BIM_PT_tandem_work_orders,
    tandem_ui.BIM_PT_tandem_maintenance_stats,
    # IoT Command Center UI (Phase 3)
    tandem_ui.BIM_PT_tandem_iot_command_center,
    tandem_ui.BIM_PT_tandem_iot_sensors,
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

                    # Enable discipline legend if this is a GI cache (organized by discipline)
                    if "Federation_Cached" in bpy.data.collections:
                        discipline_legend.enable_legend()
                        print(f"✓ Discipline legend enabled")

            except Exception as e:
                print(f"⚠ Could not restore federation index: {e}")


def register():
    """Called when addon is enabled"""
    # Attach properties to Blender's Scene
    bpy.types.Scene.BIMFederationProperties = bpy.props.PointerProperty(
        type=prop.BIMFederationProperties
    )
    bpy.types.Scene.BIMStructuralProperties = bpy.props.PointerProperty(
        type=prop.BIMStructuralProperties
    )

    # Color Palette properties
    bpy.types.Scene.BIMFederationColorProperties = bpy.props.PointerProperty(
        type=color_palette.BIMFederationColorProperties
    )

    # Digital Twin (Tandem) properties
    bpy.types.Scene.BIMTandemProperties = bpy.props.PointerProperty(
        type=tandem_ui.BIMTandemProperties
    )
    bpy.types.Scene.bim_tandem_assets = bpy.props.CollectionProperty(
        type=tandem_ui.BIMTandemAssetItem
    )
    bpy.types.Scene.bim_tandem_assets_index = bpy.props.IntProperty()
    bpy.types.Scene.bim_tandem_work_orders = bpy.props.CollectionProperty(
        type=tandem_ui.BIMTandemWorkOrderItem
    )
    bpy.types.Scene.bim_tandem_work_orders_index = bpy.props.IntProperty()

    # Register federation analysis properties on BIMClashProperties
    prop.register_federation_properties()

    # Register load handler to restore federation index
    if restore_federation_index_on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(restore_federation_index_on_load)

    print("✓ federation module registered (consolidated + Digital Twin)")

def unregister():
    """Called when addon is disabled - cleanup"""
    # Remove load handler
    if restore_federation_index_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(restore_federation_index_on_load)

    # Unregister federation analysis properties from BIMClashProperties
    prop.unregister_federation_properties()

    # Remove Digital Twin (Tandem) properties
    del bpy.types.Scene.bim_tandem_work_orders_index
    del bpy.types.Scene.bim_tandem_work_orders
    del bpy.types.Scene.bim_tandem_assets_index
    del bpy.types.Scene.bim_tandem_assets
    del bpy.types.Scene.BIMTandemProperties

    # Remove properties from Scene
    del bpy.types.Scene.BIMFederationProperties
    del bpy.types.Scene.BIMStructuralProperties
    if hasattr(bpy.types.Scene, 'BIMFederationColorProperties'):
        del bpy.types.Scene.BIMFederationColorProperties
