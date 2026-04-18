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
from . import ui, prop, operator, discipline_legend, progress_hud, cache_monitor, color_palette, crud_operators, webui_sync
# from . import ui_federation_tab  # Old experimental sandbox - replaced by ui_federation_project
from . import ui_federation_project  # Clean enterprise layout under Project Overview
from . import river  # River Equipment Monitoring - Item 11
from . import pdf_terrain  # PDF Terrain Extraction - Item 12
# from . import equipment_placement  # Equipment Placement Tool - Item 12 (ARCHIVED - rebuilding POC)
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
    operator.LinkFederationLibrary,         # Library link (per-element)
    operator.ClearFederationViewport,       # Clear all federation data
    operator.ReloadFederationViewport,
    operator.FedRTreeSearch,                # S178: search + fly-to
    operator.FedRTreeFlyToResult,           # S178: click building → L2 drill-down
    operator.FedRTreeFlyToElement,          # S178: click element in L2 list
    operator.FedRTreeFlyToStorey,           # S186: click storey → L2 drill-down
    operator.FedRTreeFilterDisc,             # S187: click discipline bar → filter elements
    operator.FedRTreeBackToBuilding,        # S186: back from storey to building
    operator.FedRTreePick,                  # S178: click-to-identify
    operator.FedRTreeLoadMesh,              # S180: stingy mesh loader
    operator.FedRTreeOvernight,             # S186: batch-load all meshes
    operator.FedRTreeOvernightPause,        # S186: pause overnight
    operator.FedRTreeOvernightCancel,       # S186: cancel overnight
    operator.FedRTreeOvernightDismiss,      # S186: dismiss DONE box
    operator.FedRTreeSwitchOffline,         # S186-s2: accept offline bake
    operator.FedRTreeReopenBaked,           # S189: reopen baked .blend
    operator.FedRTreeMergeCountdown,       # S189l: countdown modal for save & close
    operator.FedRTreeKeepGoing,             # S186-s2: decline offline bake
    operator.FedRTreeCancelBake,            # S186-s2: cancel bake subprocess
    operator.FedRTreeBakeAll,               # S188: parallel bake all buildings
    operator.FedRTreeRelinkBaked,           # S193: crash recovery — relink from baked/
    operator.FedRTreeDirectStream,         # S195: direct DB streaming (no .blend files)
    operator.FedRTreeDirectStreamClear,    # S195: clear direct-streamed objects
    operator.FedRTreeAutoShredToggle,      # S195: auto-shred furthest when lagging
    operator.FedRTreeShred,                 # S180: remove last loaded collection
    operator.FedRTreeCountBuilding,         # S183: cockpit discipline counts
    operator.FedRTreeCopyGuid,              # S183: clipboard GUID copy
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

    # Web UI Launcher (S56)
    operator.BIM_OT_launch_web_ui,


    # Federation CRUD (manual additions)
    crud_operators.BIM_OT_add_to_federation,
    crud_operators.BIM_OT_update_federation_element,
    crud_operators.BIM_OT_remove_from_federation,
    crud_operators.BIM_OT_query_federation_additions,

    # UI Lists (needed for display)
    ui.BIM_UL_federated_files,
    ui.BIM_UL_discipline_clashes,
    ui.BIM_UL_clash_groups,
    ui.BIM_UL_resolution_options,

    # ═══════════════════════════════════════════════════════════════
    # CRITICAL: Register NUMBERED PANELS 0-10 (parents) BEFORE their children
    # ═══════════════════════════════════════════════════════════════
    ui_federation_project.BIM_PT_webui_sync,                   # 0 — Web UI Sync bar (S57)
    ui_federation_project.BIM_PT_1d_bom_designer,              # 1D — BOM Designer (S56)
    ui_federation_project.BIM_PT_2d_import_export,             # 2D — Import/Export (S56)
    ui_federation_project.BIM_PT_federation_setup,
    ui_federation_project.BIM_PT_visualization_control,
    ui_federation_project.BIM_PT_mep_coordination,           # #3 - parent for MEP
    ui_federation_project.BIM_PT_clash_detection,
    ui_federation_project.BIM_PT_structural_works,
    ui_federation_project.BIM_PT_4d_scheduling,
    ui_federation_project.BIM_PT_5d_cost_management,
    ui_federation_project.BIM_PT_digital_twin,               # 6D - Asset Maintenance
    ui_federation_project.BIM_PT_tandem_iot,                 # 7D - Tandem IoT
    ui_federation_project.BIM_PT_8_erp_reports,              # 8  - ERP Reports (S56)
    ui_federation_project.BIM_PT_nlp_query,                  # 9 - NLP
    ui_federation_project.BIM_PT_visualization_settings,     # 10 - Color Studio

    # River Equipment Monitoring - Item 11
    *river.classes,

    # PDF Terrain Extraction - Item 12
    *pdf_terrain.classes,

    # Equipment Placement - Item 12 (ARCHIVED - rebuilding POC)
    # equipment_placement.BIM_PT_equipment_placement,
    # equipment_placement.BIM_OT_equipment_select_type,
    # equipment_placement.BIM_OT_equipment_place_marker,
    # equipment_placement.BIM_OT_equipment_export,
    # equipment_placement.BIM_OT_equipment_clear,

    # OLD UI PANELS - Commented out for clean POC
    # ui.BIM_PT_tab_federation,
    # ui.BIM_PT_tab_clash_detection,
    # ui.BIM_PT_federation,
    # ui.BIM_PT_federation_additions,
    # ui.BIM_PT_federation_clash_detection,
    # ui.BIM_PT_federation_lod_visualization,
    # ui.BIM_PT_clash_adjustment,
    # ui.BIM_PT_tab_4d_5d,
    # ui.BIM_PT_4d_schedule_export,
    # ui.BIM_PT_boq_export,
    # ui.BIM_PT_structural_works,
    # ui.BIM_PT_nlp_query,
    ui.BIM_PT_rtree_inspector,              # S178: search + pick N-panel in 3D viewport

    # ═══════════════════════════════════════════════════════════════
    # CHILD PANELS (after their parents exist)
    # ═══════════════════════════════════════════════════════════════

    # Color Palette UI (child of #10)
    color_palette.ColorHistoryItem,
    color_palette.BIMFederationColorProperties,
    color_palette.BIM_OT_apply_palette_color,
    color_palette.BIM_OT_apply_color_to_selected,
    color_palette.BIM_OT_strip_materials_from_type,
    color_palette.BIM_OT_get_type_from_selection,
    color_palette.BIM_OT_refresh_ifc_types,
    color_palette.BIM_OT_reset_colors,
    color_palette.BIM_OT_save_color_scheme,
    color_palette.BIM_OT_load_color_scheme,
    # color_palette.BIM_PT_federation_color_palette,  # Removed - content moved to #10 parent

    # WebUI Sync — Bonsai ↔ Web UI bidirectional sync (S57)
    webui_sync.BIM_OT_start_webui_sync,
    webui_sync.BIM_OT_stop_webui_sync,

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
    # tandem_ui.BIM_PT_tandem_main,  # Removed - content moved to #8 parent
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


@persistent
def restore_equipment_on_load(dummy):
    """
    Restore river equipment markers when .blend file is loaded.

    Equipment Empty objects ARE saved in .blend file, but the
    PLACED_EQUIPMENT runtime dictionary is not. This handler
    reconstructs the dictionary from existing scene objects,
    allowing gizmos to auto-appear on file open.
    """
    if not hasattr(bpy.context, 'scene'):
        return

    try:
        # Import equipment config module to access PLACED_EQUIPMENT
        from .river import equipment_config

        # Clear existing data
        for equipment_type in equipment_config.EQUIPMENT_TYPES.keys():
            equipment_config.PLACED_EQUIPMENT[equipment_type] = []

        # Equipment name patterns to scan for - dynamically built from EQUIPMENT_TYPES
        equipment_map = {
            f'{eq_type.upper()}_': eq_type
            for eq_type in equipment_config.EQUIPMENT_TYPES.keys()
        }

        # Scan scene for equipment Empty objects
        total_restored = 0
        for obj in bpy.data.objects:
            if obj.type == 'EMPTY':
                for prefix, eq_type in equipment_map.items():
                    if obj.name.startswith(prefix):
                        # Extract number from name (e.g., BOOM_TRAP_001 → 1)
                        try:
                            num_str = obj.name.replace(prefix, '')
                            number = int(num_str)
                        except:
                            number = len(equipment_config.PLACED_EQUIPMENT[eq_type]) + 1

                        # Add to PLACED_EQUIPMENT dictionary
                        equipment_config.PLACED_EQUIPMENT[eq_type].append({
                            'id': obj.name,
                            'number': number,
                            'marker_id': obj.get("marker_id", number),  # Read from object custom property
                            'x': obj.location.x,
                            'y': obj.location.y,
                            'z': obj.location.z,
                            'object': obj,
                            'object_name': obj.name
                        })
                        total_restored += 1
                        break

        if total_restored > 0:
            print(f"✓ River Equipment: Restored {total_restored} equipment markers from scene")

            # Log details per type
            for eq_type, items in equipment_config.PLACED_EQUIPMENT.items():
                if items:
                    eq_name = equipment_config.EQUIPMENT_TYPES[eq_type]['name']
                    print(f"  • {eq_name}: {len(items)} markers")

            # Force gizmo refresh
            for area in bpy.context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()

    except Exception as e:
        print(f"⚠ Could not restore river equipment markers: {e}")


# ── S169: Thin .blend — strip meshes on save, restore on open ────────

@persistent
def federation_save_pre(dummy):
    """S174: Strip template meshes before save — only if thin_save=ON.
    Handles both GN path (_GN_Templates) and library path (_Templates)."""
    _TAG = "[S174][SAVE_PRE]"
    thin_save = False
    try:
        props = bpy.context.scene.BIMFederationProperties
        thin_save = getattr(props, 'thin_save', False)
    except Exception:
        pass

    if not thin_save:
        print(f"{_TAG} §FINE thin_save=OFF — normal save, keeping meshes")
        return

    print(f"{_TAG} §FINE thin_save=ON — stripping meshes for meshless save")
    from . import blend_cache
    blend_cache.strip_template_meshes()

@persistent
def federation_save_post(dummy):
    """S174: Restore meshes after save.
    S191: Link baked files from temp/ → move to {project}/ on save."""
    _TAG = "[S174][SAVE_POST]"

    # ── S174: thin_save restore ──
    thin_save = False
    try:
        props = bpy.context.scene.BIMFederationProperties
        thin_save = getattr(props, 'thin_save', False)
    except Exception:
        pass
    if thin_save:
        print(f"{_TAG} §FINE thin_save=ON — restoring meshes after save (no flicker)")
        from . import blend_cache
        blend_cache.restore_template_meshes()

    # ── S191: link baked from temp/, move to project folder ──
    from . import bbox_visualization as _bv
    from pathlib import Path as _P
    import re as _re_sv
    import shutil as _sh_sv
    import time as _t_sv

    _db = _bv._db_path_cache or ""
    if not _db:
        try:
            _db = bpy.context.scene.BIMFederationProperties.federation_database_path or ""
        except Exception:
            pass
    if _db:
        _db = bpy.path.abspath(_db)

    # Find DAGCompiler/baked/ root
    _baked_root = None
    if _db:
        for _anc in _P(_db).resolve().parents:
            _cand = _anc / "DAGCompiler" / "baked"
            if _cand.exists():
                _baked_root = _cand
                break
    if not _baked_root:
        return

    _temp_dir = _baked_root / "temp"
    if not _temp_dir.exists():
        return

    _temp_files = sorted(_temp_dir.glob("*.blend"))
    if not _temp_files:
        return

    # Already linked — skip
    _already_linked = set()
    for _lib in bpy.data.libraries:
        if _lib.filepath:
            _already_linked.add(_P(bpy.path.abspath(_lib.filepath)).name)

    _to_link = [f for f in _temp_files if f.name not in _already_linked]
    # Clean up skipped files (already linked from a previous save)
    _skipped = [f for f in _temp_files if f.name in _already_linked]
    for _sf in _skipped:
        try:
            _sf.unlink()
        except Exception:
            pass
    if _skipped:
        print(f"[S191] §SAVE_POST cleaned {len(_skipped)} already-linked files from temp/")
    if not _to_link:
        # Remove empty temp dir
        try:
            _temp_dir.rmdir()
        except Exception:
            pass
        print(f"[S191] §SAVE_POST all {len(_temp_files)} baked files already linked")
        return

    # Project folder = stem of saved .blend
    _proj_name = _P(bpy.data.filepath).stem if bpy.data.filepath else "unsaved"
    _proj_dir = _baked_root / _proj_name
    _proj_dir.mkdir(exist_ok=True)

    # S193: If too many files, just move to City/ — don't link all at once.
    # Auto-Stream or Relink handles progressive linking.
    _SAFE_LINK_LIMIT = 50
    if len(_to_link) > _SAFE_LINK_LIMIT:
        _moved = 0
        for _bf in _to_link:
            _dst = _proj_dir / _bf.name
            try:
                if _dst.exists():
                    _dst.unlink()
                _sh_sv.move(str(_bf), str(_dst))
                _moved += 1
            except Exception as _me:
                print(f"[S191] §MOVE_WARN {_bf.name}: {_me}")
        # Clean up temp/ if empty
        remaining = list(_temp_dir.glob("*.blend"))
        if not remaining:
            try:
                _temp_dir.rmdir()
            except Exception:
                pass
        # Refresh baked file registry for Auto-Stream
        _bv._baked_files.clear()
        import re as _re_refresh
        for _sub in _baked_root.iterdir():
            if _sub.is_dir() and _sub.name != "temp":
                for _rbf in _sub.glob("*.blend"):
                    _bn = _re_refresh.sub(r'(_baked|_chunk\d+)$', '', _rbf.stem)
                    _bv._baked_files.setdefault(_bn, []).append(_rbf)
        print(f"[S191] §SAVE_MOVE_ONLY moved={_moved} to {_proj_dir.name}/ "
              f"(>{_SAFE_LINK_LIMIT} files — use Auto-Stream or Relink)")
        _bv._bake_done.clear()
        return

    _bv._linking_active = True
    from . import progress_hud as _ph
    _ph._link_start_time = _t_sv.time()
    _ph._link_file_count = len(_to_link)
    _ph._link_total_mb = sum(f.stat().st_size for f in _to_link) / (1024 * 1024)
    # Force viewport redraw so HUD shows "LINKING" before freeze
    for _area in bpy.context.screen.areas:
        if _area.type == 'VIEW_3D':
            _area.tag_redraw()
    try:
        bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
    except Exception:
        pass
    print(f"[S191] {_t_sv.strftime('%H:%M:%S', _t_sv.localtime())} "
          f"§SAVE_LINK_START {len(_to_link)} baked files → {_proj_dir.name}/")

    _linked = 0
    _bld_parents = {}
    for _bf in _to_link:
        _bld_name = _re_sv.sub(r'(_baked|_chunk\d+)$', '', _bf.stem)
        _bf_mb = _bf.stat().st_size / (1024 * 1024)

        # Move to project folder first (so library path is permanent)
        _dst = _proj_dir / _bf.name
        try:
            if _dst.exists():
                _dst.unlink()
            _sh_sv.move(str(_bf), str(_dst))
        except Exception as _me:
            print(f"[S191] §MOVE_WARN {_bf.name}: {_me}")
            _dst = _bf  # fallback: link from temp/

        # Link into scene
        try:
            with bpy.data.libraries.load(str(_dst), link=True) as (src, dst):
                _dcols = [c for c in src.collections
                          if _re_sv.search(r'_[A-Z]{2,5}$', c)]
                if _dcols:
                    dst.collections = _dcols
                elif src.collections:
                    dst.collections = [src.collections[0]]

            # Nest under building parent collection
            if _bld_name not in _bld_parents:
                # Shred old Loaded_* overnight meshes
                _loaded_prefix = f"Loaded_{_bld_name}_"
                for _old_col in list(bpy.data.collections):
                    if _old_col.name.startswith(_loaded_prefix):
                        for _obj in list(_old_col.objects):
                            bpy.data.objects.remove(_obj, do_unlink=True)
                        bpy.data.collections.remove(_old_col)
                _old_parent = bpy.data.collections.get(f"Loaded_{_bld_name}")
                if _old_parent:
                    bpy.data.collections.remove(_old_parent)
                _pc = bpy.data.collections.get(_bld_name)
                if _pc is None:
                    _pc = bpy.data.collections.new(_bld_name)
                    bpy.context.scene.collection.children.link(_pc)
                _bld_parents[_bld_name] = _pc

            _parent_col = _bld_parents[_bld_name]
            for _col in dst.collections:
                if _col is not None:
                    _parent_col.children.link(_col)
                    _linked += 1
            print(f"[S191] §SAVE_LINK {_bf.name} ({_bf_mb:.1f}MB) → {_proj_dir.name}/{_bld_name}")
        except Exception as _e:
            print(f"[S191] §SAVE_LINK_WARN {_bf.name}: {_e}")

    # Clear _bake_done since they're now linked
    _bv._bake_done.clear()

    # Clean up temp/ if empty
    remaining = list(_temp_dir.glob("*.blend"))
    if not remaining:
        try:
            _temp_dir.rmdir()
        except Exception:
            pass

    _bv._linking_active = False
    # S191: trigger success message in HUD (visible 5s)
    from . import progress_hud as _ph
    _ph._link_success_time = _t_sv.time()
    print(f"[S191] §SAVE_LINK_DONE linked={_linked} project={_proj_dir.name}")

@persistent
def federation_load_post_meshes(dummy):
    """S174: On file open:
    - GN path: restore templates from component_library.db
    - Library path + thin_save ON: auto-trigger R-tree preview (meshless open)
    - Library path + thin_save OFF: auto-restore from library.blend
    S170: Also rebuild LOD manager index and start LOD timer."""
    _TAG = "[S174][LOAD_POST]"
    from . import blend_cache

    # Check thin_save flag
    thin_save = False
    try:
        props = bpy.context.scene.BIMFederationProperties
        thin_save = getattr(props, 'thin_save', False)
    except Exception:
        pass

    # GN path — always restore
    gn_templates = bpy.data.collections.get('_GN_Templates')
    if gn_templates:
        print(f"{_TAG} §FINE GN path detected — restoring templates")
        blend_cache.restore_template_meshes()

    # Library-linked path (per-element)
    lib_templates = bpy.data.collections.get('_Templates')
    has_stubs = False
    if lib_templates:
        # Check if there are stub meshes (meshless save)
        for obj in bpy.data.objects:
            if obj.type == 'MESH' and obj.data and obj.data.name.startswith('stub_'):
                has_stubs = True
                break

    if has_stubs:
        if thin_save:
            print(f"{_TAG} §FINE thin_save=ON, stubs detected — auto-triggering R-tree preview")
            try:
                bpy.ops.bim.preview_federation_viewport()
                print(f"{_TAG} §PROOF RTREE_AUTO auto R-tree preview triggered on meshless open")
            except Exception as e:
                print(f"{_TAG} §WARN R-tree auto-trigger failed: {e} — user can click R-Tree manually")
        else:
            print(f"{_TAG} §FINE thin_save=OFF, stubs detected — auto-restoring library-linked meshes")
            blend_cache.restore_template_meshes()
    elif lib_templates:
        print(f"{_TAG} §FINE library path, no stubs — meshes intact (normal save)")
    else:
        print(f"{_TAG} §FINE no federation collections found — normal .blend open")

    # S170: Rebuild LOD index from database on file open
    _init_lod_from_scene()


# ── S170: LOD — discipline visibility tracking ──────────────────────

def _init_lod_from_scene():
    """Initialize LOD manager from scene state after file open."""
    try:
        root = bpy.data.collections.get('Federation_Cached')
        if not root:
            return
        db_path = root.get('database_path')
        lib_path = root.get('library_path')
        if not db_path or not Path(db_path).exists():
            return

        from . import lod_manager
        mgr = lod_manager.get_manager()
        if mgr._built:
            return  # Already initialized

        mgr.build_index(db_path, library_path=lib_path)

        # Detect which disciplines are currently visible
        root_lc = None
        for lc in bpy.context.view_layer.layer_collection.children:
            if lc.name == 'Federation_Cached':
                root_lc = lc
                break
        if root_lc:
            for disc_lc in root_lc.children:
                if not disc_lc.exclude:
                    mgr.visible_disciplines.add(disc_lc.name)
                    mgr.loaded_hashes |= mgr.disc_hashes.get(disc_lc.name, set())

        mgr.candidate_hashes = mgr.get_visible_hashes()

        # Count loaded templates for large model detection
        tmpl_coll = bpy.data.collections.get('_GN_Templates')
        total_templates = len(tmpl_coll.objects) if tmpl_coll else 0
        mgr.distance_enabled = (total_templates >= 5000)

        lod_manager.start_lod_timer()
        print(f"[S170] LOD restored: {len(mgr.visible_disciplines)} visible disciplines, "
              f"{len(mgr.loaded_hashes):,} loaded hashes")
    except Exception as e:
        print(f"[S170] LOD init skipped: {e}")


# S170: Track previous discipline visibility state for change detection
_prev_disc_visibility = {}

@persistent
def federation_depsgraph_update(scene, depsgraph):
    """S170: Detect discipline collection visibility changes → trigger LOD load/unload."""
    global _prev_disc_visibility

    root_lc = None
    try:
        for lc in bpy.context.view_layer.layer_collection.children:
            if lc.name == 'Federation_Cached':
                root_lc = lc
                break
    except Exception:
        return

    if not root_lc:
        return

    # Check each discipline sub-collection's exclude state
    changed = False
    for disc_lc in root_lc.children:
        name = disc_lc.name
        visible = not disc_lc.exclude
        prev = _prev_disc_visibility.get(name)
        if prev is None:
            # First time seeing this — just record
            _prev_disc_visibility[name] = visible
            continue
        if visible != prev:
            _prev_disc_visibility[name] = visible
            changed = True
            try:
                from . import lod_manager
                lod_manager.on_discipline_toggle(name, visible)
            except Exception as e:
                print(f"[S170] Discipline toggle error ({name}): {e}")


def register():
    """Called when addon is enabled"""
    # S191: Progress HUD — always on, independent of legend/clear
    progress_hud.register()
    try:
        progress_hud.enable_hud()
    except Exception:
        pass  # 3D view may not exist yet at registration time

    # Attach properties to Blender's Scene
    bpy.types.Scene.BIMFederationProperties = bpy.props.PointerProperty(
        type=prop.BIMFederationProperties
    )
    bpy.types.Scene.BIMStructuralProperties = bpy.props.PointerProperty(
        type=prop.BIMStructuralProperties
    )

    # Hide old Project panels for clean POC
    from .hide_old_panels import hide_old_project_panels
    try:
        hide_old_project_panels()
    except:
        pass  # Ignore if panels don't exist yet

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

    # River Equipment Placement properties (Phase 1 POC)
    from bpy.props import EnumProperty
    bpy.types.Scene.equipment_marker_type = EnumProperty(
        name="Equipment Type",
        items=[
            ('boom_trap', 'Boom Trap Station', 'Boom Trap Station'),
            ('water_quality', 'Water Quality Station', 'Water Quality Station'),
            ('biodiversity', 'Biodiversity Monitor', 'Biodiversity Monitor'),
        ],
        default='boom_trap'
    )

    # Register federation analysis properties on BIMClashProperties
    prop.register_federation_properties()

    # Register load handler to restore federation index
    if restore_federation_index_on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(restore_federation_index_on_load)

    # Register load handler to restore river equipment markers
    if restore_equipment_on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(restore_equipment_on_load)

    # S169: Register save/load handlers for thin .blend
    if federation_save_pre not in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.append(federation_save_pre)
    if federation_save_post not in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.append(federation_save_post)
    if federation_load_post_meshes not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(federation_load_post_meshes)

    # S170: Register depsgraph handler for discipline visibility tracking
    if federation_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(federation_depsgraph_update)

    # S174: Register DLOD (Distance LOD) handler — optional, non-fatal
    try:
        from . import dlod_handler
        dlod_handler.register_handler()
        print("[S174][DLOD] §FINE handler registered")
    except Exception as e:
        print(f"[S174][DLOD] §WARN register failed (non-fatal): {e}")

    # Register equipment context menu (right-click on equipment)
    # Note: river module handles its own context menu in river/__init__.py register()
    # bpy.types.VIEW3D_MT_object_context_menu.append(river.equipment_maintenance.menu_func)

    # Equipment Placement properties (ARCHIVED - rebuilding POC)
    # equipment_placement.register()

    # PDF Terrain module properties
    pdf_terrain.register()

    # S195: Ctrl+Shift+A keymap for Direct Stream toggle
    wm = bpy.context.window_manager
    km = wm.keyconfigs.addon.keymaps.new(name='3D View', space_type='VIEW_3D')
    kmi = km.keymap_items.new('bim.fed_rtree_direct_stream', 'A', 'PRESS', ctrl=True, shift=True)
    _addon_keymaps.append((km, kmi))

    print("✓ federation module registered (consolidated + Digital Twin + River Equipment + 7D Maintenance)")

# S193: keymap storage
_addon_keymaps = []

def unregister():
    """Called when addon is disabled - cleanup"""
    # S193: remove keymaps
    for km, kmi in _addon_keymaps:
        km.keymap_items.remove(kmi)
    _addon_keymaps.clear()

    progress_hud.disable_hud()
    progress_hud.unregister()
    # Remove load handlers
    if restore_federation_index_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(restore_federation_index_on_load)
    if restore_equipment_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(restore_equipment_on_load)

    # S169: Remove save/load handlers
    if federation_save_pre in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(federation_save_pre)
    if federation_save_post in bpy.app.handlers.save_post:
        bpy.app.handlers.save_post.remove(federation_save_post)
    if federation_load_post_meshes in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(federation_load_post_meshes)

    # S170: Remove depsgraph handler + shutdown LOD
    if federation_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(federation_depsgraph_update)
    try:
        from . import lod_manager
        lod_manager.stop_lod_timer()
        lod_manager.shutdown_manager()
    except Exception:
        pass

    # S174: Unregister DLOD handler + shutdown state
    try:
        from . import dlod_handler
        dlod_handler.unregister_handler()
        print("[S174][DLOD] §FINE handler unregistered")
    except Exception:
        pass

    # Remove equipment context menu
    # Note: river module handles its own context menu in river/__init__.py unregister()
    # bpy.types.VIEW3D_MT_object_context_menu.remove(river.equipment_maintenance.menu_func)

    # Unregister federation analysis properties from BIMClashProperties
    prop.unregister_federation_properties()

    # Remove Digital Twin (Tandem) properties
    del bpy.types.Scene.bim_tandem_work_orders_index
    del bpy.types.Scene.bim_tandem_work_orders
    del bpy.types.Scene.bim_tandem_assets_index
    del bpy.types.Scene.bim_tandem_assets
    del bpy.types.Scene.BIMTandemProperties

    # River Equipment Placement cleanup (Phase 1 POC)
    if hasattr(bpy.types.Scene, 'equipment_marker_type'):
        del bpy.types.Scene.equipment_marker_type

    # Equipment Placement cleanup (ARCHIVED - rebuilding POC)
    # equipment_placement.unregister()

    # PDF Terrain module cleanup
    pdf_terrain.unregister()

    # Remove properties from Scene
    del bpy.types.Scene.BIMFederationProperties
    del bpy.types.Scene.BIMStructuralProperties
    if hasattr(bpy.types.Scene, 'BIMFederationColorProperties'):
        del bpy.types.Scene.BIMFederationColorProperties
