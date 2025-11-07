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
Qualified Path: src/bonsai/bonsai/bim/module/federation/ui.py

Federation Module UI
--------------------
Blender interface panels for multi-model federation management.
"""

import bpy
from bpy.types import Panel, UIList


class BIM_UL_federated_files(UIList):
    """UI List for displaying federated files"""
    
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if item:
            row = layout.row(align=True)
            
            # Preprocessed indicator
            if item.is_preprocessed:
                row.label(text="", icon="CHECKMARK")
            else:
                row.label(text="", icon="BLANK1")
            
            # Discipline tag
            col = row.column()
            col.alert = not bool(item.discipline)
            col.prop(item, "discipline", text="", emboss=False)
            
            # Filename (alert if empty)
            col = row.column()
            col.alert = not bool(item.name)
            if item.name:
                from pathlib import Path
                col.label(text=Path(item.name).name)
            else:
                col.label(text="(no file selected)")
            
            # Element count
            if item.element_count > 0:
                row.label(text=f"{item.element_count:,}")
        else:
            layout.label(text="", translate=False)


class BIM_PT_federation(Panel):
    """Multi-Model Federation panel"""
    bl_label = "Federation Management"
    bl_idname = "BIM_PT_federation"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_options = {"DEFAULT_CLOSED"}
    # Nest under Federation tab
    bl_parent_id = "BIM_PT_tab_federation"
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.BIMFederationProperties
        
        # Header info
        if props.index_loaded:
            box = layout.box()
            row = box.row()
            row.label(text="Federation Active", icon="CHECKMARK")
            
            col = box.column(align=True)
            col.label(text=f"Elements: {props.total_elements:,}")
            col.label(text=f"Disciplines: {props.loaded_disciplines}")
        else:
            box = layout.box()
            box.label(text="Federation Not Loaded", icon="INFO")
        
        layout.separator()
        
        # Federated files section
        box = layout.box()
        box.label(text="Federated IFC Files", icon="OUTLINER_OB_POINTCLOUD")

        row = box.row(align=True)
        row.operator("bim.add_federated_file", icon="ADD", text="Add File")
        row.operator("bim.select_federated_folder", icon="FILEBROWSER", text="Scan Folder")
        
        if props.federated_files:
            # File list
            box.template_list(
                "BIM_UL_federated_files", "",
                props, "federated_files",
                props, "active_federated_file_index"
            )
            
            # File operations
            if props.active_federated_file_index < len(props.federated_files):
                active_file = props.federated_files[props.active_federated_file_index]
                
                row = box.row(align=True)
                op = row.operator("bim.select_federated_file", icon="FILE_FOLDER", text="Select File")
                op.index = props.active_federated_file_index
                
                op = row.operator("bim.remove_federated_file", icon="X", text="Remove")
                op.index = props.active_federated_file_index
        
        layout.separator()

        # Statistics section (collapsible)
        if props.index_loaded:
            box = layout.box()
            row = box.row()
            row.prop(props, "show_statistics",
                    icon="TRIA_DOWN" if props.show_statistics else "TRIA_RIGHT",
                    text="Federation Statistics",
                    emboss=False)

            if props.show_statistics:
                col = box.column(align=True)

                # File statistics
                col.label(text="Files in Federation:")
                for fed_file in props.federated_files:
                    if fed_file.is_preprocessed:
                        from pathlib import Path
                        row = col.row()
                        row.label(text=f"  {fed_file.discipline}:")
                        row.label(text=f"{fed_file.element_count:,} elements")

                col.separator()

                # Query settings
                col.label(text="Query Settings:")
                col.prop(props, "query_buffer_mm")
                col.prop(props, "filter_by_discipline")

                if props.filter_by_discipline:
                    col.prop(props, "active_disciplines", text="Disciplines")

            layout.separator()

        # Viewport Control section
        layout.separator()
        box = layout.box()
        box.label(text="Viewport Control:", icon="MESH_DATA")

        # Info
        col = box.column(align=True)
        col.scale_y = 0.8
        col.label(text="Loads exact IFC geometry with GPU instancing")
        col.label(text="Expected load time: ~27 seconds for 14K elements")

        box.separator()

        # Database path - Positioned just above Preview/Solid buttons
        inner_box = box.box()
        inner_box.label(text="Federation Database", icon="FILE")
        inner_box.prop(props, "federation_database_path", text="")

        # Progress indicator
        if props.preprocessing_in_progress:
            inner_box.label(text="Preprocessing in progress...", icon="TIME")
            if props.progress_json_path:
                from pathlib import Path
                inner_box.label(text=f"Progress: {Path(props.progress_json_path).name}")

        # Database Extraction
        inner_box.separator()
        inner_box.label(text="Database Extraction:")

        # Extraction buttons (side-by-side)
        row = inner_box.row(align=True)
        row.scale_y = 1.3
        row.operator("bim.extract_full_database", icon="SEQUENCE", text="Extract Full")
        row.operator("bim.extract_sample_database", icon="EXPERIMENTAL", text="Extract Sample")

        # Sample settings
        row = inner_box.row(align=True)
        row.prop(props, "sample_anchor_type", text="Anchor")
        row.operator("bim.redo_sample_extraction", icon="FILE_REFRESH", text="Redo")

        box.separator()

        # Action buttons - Three-stage workflow
        col = box.column(align=True)

        # Row 1: Preview | Solid (fast options side-by-side)
        row = col.row(align=True)
        row.scale_y = 1.5
        row.operator("bim.preview_federation_viewport", icon="HIDE_OFF", text="Preview")
        # Disable Solid button if already loaded (prevents slow re-loading)
        solid_row = row.row(align=True)
        solid_row.enabled = not props.solid_loaded
        solid_row.operator("bim.load_solid_federation_viewport", icon="MESH_CUBE", text="Solid")

        # Row 2: Full Load (slower, exact geometry)
        row = col.row(align=True)
        row.scale_y = 1.3
        row.operator("bim.load_full_federation_viewport", icon="MESH_DATA", text="Full Load")

        # Row 3: Unload button
        row = col.row(align=True)
        row.operator("bim.unload_federation_viewport", icon="PANEL_CLOSE", text="Unload All")

        # Auto-reload setting
        box.separator()
        col = box.column()
        col.prop(props, "auto_reload_on_open", text="Auto-reload on file open")

        # Help section (collapsible)
        layout.separator()
        box = layout.box()
        row = box.row()
        row.prop(props, "show_help",
                icon="TRIA_DOWN" if props.show_help else "TRIA_RIGHT",
                text="Help & Usage Tips",
                emboss=False)

        if props.show_help:
            col = box.column(align=True)
            col.scale_y = 0.8
            col.label(text="Workflow:")
            col.label(text="1. Add all discipline IFC files")
            col.label(text="2. Extract Full (~25 min) or Sample (~5 min)")
            col.label(text="3. Click 'Reload Viewport' to visualize")
            col.label(text="4. Use in MEP routing or clash detection")
            col.separator()
            col.label(text="Extraction Options:")
            col.label(text="• Full: All elements, production-ready")
            col.label(text="• Sample: ELEC-anchored test region")
            col.label(text="• Redo: Try different sample region")# Bonsai - OpenBIM Blender Add-on
# Copyright (C) 2020, 2021 Dion Moult <dion@thinkmoult.com>
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
Federation Analysis UI

UI panels for discipline-based clash detection and LOD visualization.
"""

from __future__ import annotations
import bpy
import bonsai.tool as tool
from bpy.types import Panel, UIList
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bonsai.bim.module.clash.prop import BIMClashProperties


class BIM_PT_federation_clash_detection(Panel):
    bl_label = "Federation Clash Detection"
    bl_idname = "BIM_PT_federation_clash_detection"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tab_clash_detection"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        assert self.layout
        layout = self.layout
        props = tool.Clash.get_clash_props()

        # ================================================================
        # QUICK CLASH BY DISCIPLINE (Federation-based)
        # ================================================================
        # Requires federation DB to be loaded from MEP Engineering panel
        box = layout.box()
        box.label(text="Quick Clash by Discipline", icon="COMMUNITY")

        # Discipline preset dropdown
        row = box.row()
        row.prop(props, "clash_preset", text="")

        # Custom discipline selection
        if props.clash_preset == 'CUSTOM':
            row = box.row(align=True)
            row.prop(props, "discipline_a", text="")
            row.label(text="vs")
            row.prop(props, "discipline_b", text="")

        # Tolerance
        row = box.row()
        row.prop(props, "discipline_tolerance")

        # Run button
        row = box.row()
        row.operator("bim.clash_by_discipline",
                     text="Run Clash Detection",
                     icon="PLAY")

        # Display discipline clash results
        if props.discipline_clash_loaded and props.discipline_clash_candidates:
            layout.separator()
            result_box = layout.box()
            result_box.label(text=f"{len(props.discipline_clash_candidates)} Clash Candidates Found", icon="ERROR")

            # Filter hint
            filter_row = result_box.row()
            filter_row.scale_y = 0.8
            filter_row.label(text="💡 Use filter box (🔍) to search: 'wall', 'door', 'ifcwall*', etc.", icon='INFO')

            # Header row
            header = result_box.row(align=True)
            header.label(text="#")
            header.label(text="☐")  # Checkbox column header
            header.label(text="Element A")
            header.label(text="Element B")
            header.label(text="Type")

            # Clash list (with built-in filter support)
            result_box.template_list(
                "BIM_UL_discipline_clashes",
                "",
                props,
                "discipline_clash_candidates",
                props,
                "active_discipline_clash_index"
            )

            # Count selected clashes
            selected_count = sum(1 for c in props.discipline_clash_candidates if c.selected)

            # Selection helpers
            if selected_count > 0:
                sel_row = result_box.row(align=True)
                sel_row.label(text=f"{selected_count} selected")
                sel_row.operator("bim.deselect_all_clashes", text="Uncheck All", icon="PANEL_CLOSE")

            # Action buttons
            row = result_box.row(align=True)
            row.operator("bim.select_discipline_clash", text="View Clash", icon="ZOOM_IN")

            # OLD wireframe visualization - DISABLED (use GPU Overlays instead)
            # col = row.column()
            # col.enabled = selected_count > 0
            # col.operator("bim.visualize_selected_discipline_clashes",
            #             text=f"Visualize Selected ({selected_count})",
            #             icon="HIDE_OFF")

            row.operator("bim.clear_discipline_clash_visualization", text="Clear All", icon="PANEL_CLOSE")

            # Clash Visualization
            layout.separator()
            viz_box = layout.box()
            viz_box.label(text="Clash Visualization", icon="OUTLINER_OB_POINTCLOUD")

            # GPU Overlay Visualization
            gpu_row = viz_box.row(align=True)
            gpu_row.operator("bim.enable_clash_gpu_visualization",
                           text="GPU Overlay",
                           icon="RESTRICT_VIEW_OFF")
            gpu_row.operator("bim.disable_clash_gpu_visualization",
                           text="",
                           icon="X")

            # Gizmo Visualization (Interactive 3D Markers) - Now with lazy loading!
            gizmo_row = viz_box.row(align=True)
            gizmo_row.operator("bim.enable_clash_gizmo_visualization",
                             text="Interactive Gizmos",
                             icon="PIVOT_INDIVIDUAL")
            gizmo_row.operator("bim.disable_clash_gizmo_visualization",
                             text="",
                             icon="X")

            # Info about gizmo features
            info_col = viz_box.column(align=True)
            info_col.scale_y = 0.7
            info_col.label(text="💡 Gizmo features:", icon='INFO')
            info_col.label(text="  • Left-click to jump to clash")
            info_col.label(text="  • Right-click for context menu")
            info_col.label(text="  • Color-coded: Red=New, Orange=Active, Yellow=Reviewed, Green=Resolved")

            # BCF Export
            layout.separator()
            bcf_box = layout.box()
            bcf_box.label(text="BCF Export", icon="EXPORT")

            bcf_row = bcf_box.row()
            bcf_row.operator("bim.export_bcf",
                           text="Export to BCF 2.1",
                           icon="FILE_TICK")

            # Info about BCF
            bcf_info = bcf_box.column(align=True)
            bcf_info.scale_y = 0.7
            bcf_info.label(text="💡 BCF (BIM Collaboration Format):", icon='INFO')
            bcf_info.label(text="  • Industry standard for issue tracking")
            bcf_info.label(text="  • Compatible with Navisworks, Solibri, BIMcollab")
            bcf_info.label(text="  • Includes 3D viewpoints and clash metadata")

            # Show selection limit warning
            if selected_count > 10:
                warn_row = result_box.row()
                warn_row.alert = True
                warn_row.label(text=f"⚠ Too many selected ({selected_count}). Max 10 for visualization.", icon="ERROR")

            # Show selected clash details
            if 0 <= props.active_discipline_clash_index < len(props.discipline_clash_candidates):
                candidate = props.discipline_clash_candidates[props.active_discipline_clash_index]
                detail_box = result_box.box()
                detail_box.label(text="Clash Details:", icon="INFO")
                col = detail_box.column(align=True)
                col.label(text=f"Element A: {candidate.name_a}")
                col.label(text=f"  GUID: {candidate.guid_a}")
                col.label(text=f"  Class: {candidate.ifc_class_a}")
                col.separator()
                col.label(text=f"Element B: {candidate.name_b}")
                col.label(text=f"  GUID: {candidate.guid_b}")
                col.label(text=f"  Class: {candidate.ifc_class_b}")


class BIM_PT_federation_lod_visualization(Panel):
    bl_label = "Federation LOD Visualization"
    bl_idname = "BIM_PT_federation_lod_visualization"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tab_clash_detection"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        assert self.layout
        layout = self.layout
        props = tool.Clash.get_clash_props()

        # ================================================================
        # FEDERATION LOD VISUALIZATION (BBox Semantic Geometry - Phase 2)
        # ================================================================
        lod_box = layout.box()
        lod_box.label(text="Federation LOD Visualization", icon="SHADING_BBOX")

        # Check database (from Federation panel - no UI shown, just validation)
        fed_props = context.scene.BIMFederationProperties
        if not fed_props.federation_database_path:
            info_row = lod_box.row()
            info_row.alert = True
            info_row.label(text="⚠ Set database in Multi-Model Federation panel first", icon='ERROR')
            info_row = lod_box.row()
            info_row.label(text="   (Scene Properties → Multi-Model Federation)")
            return

        # LOD mode selector
        row = lod_box.row()
        row.prop(props, "lod_visualization_mode", text="")

        # BBox Wireframe controls (Level 0)
        if props.lod_visualization_mode == 'BBOX_WIREFRAME':
            row = lod_box.row(align=True)
            if props.bbox_visualization_enabled:
                row.operator("bim.disable_bbox_visualization",
                           text="Disable BBox View",
                           icon='HIDE_ON')
            else:
                row.operator("bim.enable_bbox_visualization",
                           text="Enable BBox View",
                           icon='HIDE_OFF')

            # Element limit (for testing)
            row = lod_box.row()
            row.prop(props, "bbox_element_limit")
            if props.bbox_element_limit == 0:
                hint_row = lod_box.row()
                hint_row.scale_y = 0.6
                hint_row.label(text="💡 0 = All elements (44K+)", icon='INFO')

            # Stats toggle
            row = lod_box.row()
            row.prop(props, "show_lod_stats")

            # Info
            info_col = lod_box.column(align=True)
            info_col.scale_y = 0.7
            info_col.label(text="💡 BBox Wireframe:", icon='INFO')
            info_col.label(text="  • Instant loading (<3 seconds)")
            info_col.label(text="  • <10 MB memory usage")
            info_col.label(text="  • Color-coded by discipline")
            info_col.label(text="  • ACMV=Cyan, FP=Red, ELEC=Yellow")

        # Semantic Proxies (Level 1) - Basic Templates
        elif props.lod_visualization_mode == 'SEMANTIC_PROXY':
            row = lod_box.row(align=True)
            if props.bbox_visualization_enabled:  # Reuse flag for any visualization mode
                row.operator("bim.disable_semantic_proxy_visualization",
                           text="Disable Semantic Proxies",
                           icon='HIDE_ON')
            else:
                row.operator("bim.enable_semantic_proxy_visualization",
                           text="Enable Semantic Proxies",
                           icon='MESH_CUBE')

            # Element limit (for testing)
            row = lod_box.row()
            row.prop(props, "bbox_element_limit", text="Element Limit")
            if props.bbox_element_limit == 0:
                hint_row = lod_box.row()
                hint_row.scale_y = 0.6
                hint_row.label(text="💡 0 = All elements (database-driven)", icon='INFO')

            # Info
            info_col = lod_box.column(align=True)
            info_col.scale_y = 0.7
            info_col.label(text="💡 Semantic Proxies:", icon='INFO')
            info_col.label(text="  • Basic procedural shapes from templates")
            info_col.label(text="  • Cylinders for round ducts/pipes")
            info_col.label(text="  • Boxes for rectangular ducts/trays")
            info_col.label(text="  • Database-driven (no IFC files)")
            info_col.label(text="  • Memory: ~100-200MB per 1000 elements")

        # Full IFC Geometry (Level 2) - Load from database
        elif props.lod_visualization_mode == 'FULL_GEOMETRY':
            row = lod_box.row(align=True)
            if props.bbox_visualization_enabled:  # Reuse flag for any visualization mode
                row.operator("bim.disable_full_geometry_visualization",
                           text="Disable Full Geometry",
                           icon='HIDE_ON')
            else:
                row.operator("bim.enable_full_geometry_visualization",
                           text="Enable Full Geometry",
                           icon='IMPORT')

            # Element limit (for testing)
            row = lod_box.row()
            row.prop(props, "bbox_element_limit", text="Element Limit")
            if props.bbox_element_limit == 0:
                hint_row = lod_box.row()
                hint_row.scale_y = 0.6
                hint_row.label(text="💡 0 = All elements (may take time)", icon='INFO')

            # Info
            info_col = lod_box.column(align=True)
            info_col.scale_y = 0.7
            info_col.label(text="💡 Full Geometry:", icon='INFO')
            info_col.label(text="  • Detailed procedural shapes with flanges/dampers")
            info_col.label(text="  • Higher poly count, smoother geometry")
            info_col.label(text="  • Database-driven (no IFC files)")
            info_col.label(text="  • Independent of clash detection")
            info_col.label(text="  • Memory: ~300-500MB per 1000 elements")


class BIM_UL_discipline_clashes(UIList):
    """UIList for discipline-based clash results"""

    # Enable built-in filter UI
    use_filter_show: bpy.props.BoolProperty(default=True)

    def draw_item(
        self,
        context,
        layout: bpy.types.UILayout,
        data,
        item,
        icon,
        active_data,
        active_propname,
        index,
        fit_flag,
    ) -> None:
        if item:
            # Number column
            row = layout.row(align=True)
            row.label(text=str(index + 1), translate=False)

            # Checkbox column
            row.prop(item, "selected", text="")

            # Element A
            row.label(text=str(item.name_a), translate=False, icon="NONE")

            # Element B
            row.label(text=str(item.name_b), translate=False, icon="NONE")

            # Type (grayed out)
            col = row.column()
            col.enabled = False
            col.label(text=f"{item.ifc_class_a}/{item.ifc_class_b}")
        else:
            layout.label(text="", translate=False)

    def filter_items(self, context, data, propname):
        """Filter clash list by text search (supports wildcards)"""
        clashes = getattr(data, propname)
        helper_funcs = bpy.types.UI_UL_list

        # Initialize filter flags (all visible by default)
        flt_flags = [self.bitflag_filter_item] * len(clashes)
        flt_neworder = []

        # Text filtering
        if self.filter_name:
            filter_text = self.filter_name.lower()

            for idx, clash in enumerate(clashes):
                # Search in: Element A name, Element B name, IFC classes
                searchable = f"{clash.name_a} {clash.name_b} {clash.ifc_class_a} {clash.ifc_class_b}".lower()

                # Simple wildcard support: convert * to regex
                import re
                pattern = filter_text.replace('*', '.*')

                if not re.search(pattern, searchable):
                    flt_flags[idx] &= ~self.bitflag_filter_item  # Hide this item

        return flt_flags, flt_neworder


class BIM_PT_clash_adjustment(Panel):
    """Panel for intelligent clash grouping and resolution suggestions"""
    bl_label = "Intelligent Clash Adjustment"
    bl_idname = "BIM_PT_clash_adjustment"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tab_clash_detection"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        assert self.layout
        layout = self.layout
        props = tool.Clash.get_clash_props()

        # Check if we have clashes loaded
        if not props.discipline_clash_loaded or not props.discipline_clash_candidates:
            info_box = layout.box()
            info_box.label(text="⚠ Run clash detection first", icon='INFO')
            info_box.label(text="  (Use 'Quick Clash by Discipline' above)")
            return

        # ================================================================
        # PHASE 1.5: CONFIGURATION SECTION
        # ================================================================
        config_box = layout.box()
        config_box.label(text="Configuration", icon="SETTINGS")

        # Active preset display
        row = config_box.row(align=True)
        row.label(text=f"Preset: {props.active_preset_name}", icon="PRESET")

        # Preset selection buttons (example presets)
        row = config_box.row(align=True)
        op = row.operator("bim.change_preset", text="US Market")
        op.preset_name = "US Market"
        op = row.operator("bim.change_preset", text="Singapore")
        op.preset_name = "Singapore"
        op = row.operator("bim.change_preset", text="EU Standard")
        op.preset_name = "EU Standard"

        # Show learned estimates toggle
        config_box.prop(props, "show_learned_estimates", text="Use Learned Estimates", toggle=True)

        layout.separator()

        # ================================================================
        # CLASH GROUPING
        # ================================================================
        grouping_box = layout.box()
        grouping_box.label(text="Step 1: Group Cascade Clashes", icon="GROUP")

        # Info about grouping
        info_col = grouping_box.column(align=True)
        info_col.scale_y = 0.7
        info_col.label(text="💡 Groups elements with 3+ clashes:")
        info_col.label(text="  Example: 1 duct causing 11 clashes → 1 group")

        # Analyze button
        row = grouping_box.row()
        row.scale_y = 1.5
        row.operator("bim.analyze_clash_groups",
                     text="Analyze Clash Groups",
                     icon="AUTO")

        # Show grouping results if available
        if hasattr(props, 'clash_groups_analyzed') and props.clash_groups_analyzed:
            result_box = layout.box()
            result_box.label(text="Grouping Results:", icon="CHECKMARK")
            result_box.label(text="  (Check Blender console for details)")

            # ================================================================
            # RESOLUTION SUGGESTIONS
            # ================================================================
            layout.separator()
            resolution_box = layout.box()
            resolution_box.label(text="Step 2: Get Resolution Suggestions", icon="OUTLINER_DATA_LIGHTPROBE")

            # Info about resolutions
            info_col = resolution_box.column(align=True)
            info_col.scale_y = 0.7
            info_col.label(text="💡 Generates resolution options for each group:")
            info_col.label(text="  • Design effort estimates (hours)")
            info_col.label(text="  • Cost breakdown by discipline")
            info_col.label(text="  • Risk assessment")

            # Suggest resolutions button
            row = resolution_box.row()
            row.scale_y = 1.5
            row.operator("bim.suggest_resolutions",
                        text="Generate Resolution Options",
                        icon="OUTLINER_DATA_LIGHTPROBE")

            layout.separator()

            # ================================================================
            # STEP 2: PREVIEW & APPLY RESOLUTION
            # ================================================================
            action_box = layout.box()
            action_box.label(text="Step 2: Preview & Apply Resolution", icon="PLAY")

            # Dropdown selector for resolution options
            row = action_box.row()
            row.prop(props, "selected_resolution_dropdown", text="Select Option")

            # Show details if selected
            if props.selected_resolution_option_id and props.selected_resolution_option_id != "NONE":
                detail_col = action_box.column(align=True)
                detail_col.scale_y = 0.7
                detail_col.label(text=f"✓ Selected: {props.selected_resolution_option_id[:8]}...", icon="CHECKMARK")

            # Action buttons
            row = action_box.row(align=True)
            row.scale_y = 1.3
            row.enabled = bool(props.selected_resolution_option_id)

            # Preview button
            row.operator("bim.preview_resolution",
                        text="Preview 3D",
                        icon="HIDE_OFF")

            # Apply button
            row.operator("bim.apply_resolution",
                        text="Apply",
                        icon="CHECKMARK")

            # Clear preview button
            row = action_box.row()
            row.scale_y = 1.0
            row.operator("bim.clear_preview",
                        text="Clear Preview",
                        icon="X")

            # ================================================================
            # PHASE 2: FEEDBACK PANEL
            # ================================================================
            if props.show_feedback_panel:
                layout.separator()
                feedback_box = layout.box()
                feedback_box.label(text="Resolution Feedback", icon="COMMUNITY")

                info_col = feedback_box.column(align=True)
                info_col.scale_y = 0.7
                info_col.label(text="💡 Help improve future estimates:")
                info_col.label(text="  Provide actual time spent and rating")

                # Rating (stars)
                row = feedback_box.row()
                row.label(text="Rating:")
                row.prop(props, "resolution_rating", text="", slider=False)
                row.label(text="⭐")

                # Actual hours
                feedback_box.prop(props, "actual_hours", text="Actual Hours Spent")

                # Variance notes (optional)
                feedback_box.prop(props, "variance_notes", text="Notes (optional)")

                # Submit feedback button
                row = feedback_box.row()
                row.scale_y = 1.5
                row.operator("bim.submit_resolution_feedback",
                            text="Submit Feedback",
                            icon="EXPORT")

            # ================================================================
            # REPORT GENERATION
            # ================================================================
            layout.separator()
            report_box = layout.box()
            report_box.label(text="Step 3: Generate Resolution Report", icon="FILE_TEXT")

            # Info about report
            info_col = report_box.column(align=True)
            info_col.scale_y = 0.7
            info_col.label(text="💡 Creates professional Markdown report:")
            info_col.label(text="  • Executive summary with cost analysis")
            info_col.label(text="  • Clash overview snapshots (current state)")
            info_col.label(text="  • Detailed action plan")
            info_col.label(text="  • Editable format (convert to PDF later)")

            # Generate report button
            row = report_box.row()
            row.scale_y = 1.5
            row.operator("bim.generate_clash_resolution_report",
                        text="Generate Report",
                        icon="FILE_TEXT")

            # Snapshot note
            note_col = report_box.column(align=True)
            note_col.scale_y = 0.6
            note_col.label(text="Note: Snapshots require geometry loaded in scene")
            note_col.label(text="(Use Preview/Solid/Full buttons first for images)")


class BIM_UL_clash_groups(UIList):
    """UIList for displaying clash groups"""

    def draw_item(
        self,
        context,
        layout: bpy.types.UILayout,
        data,
        item,
        icon,
        active_data,
        active_propname,
        index,
        fit_flag,
    ) -> None:
        if item:
            row = layout.row(align=True)

            # Group number
            row.label(text=f"Group {index + 1}", icon="GROUP")

            # Severity indicator
            severity_icons = {
                'CRITICAL': 'ERROR',
                'HIGH': 'ERROR',
                'MEDIUM': 'INFO',
                'LOW': 'CHECKMARK'
            }
            severity = getattr(item, 'severity', 'MEDIUM')
            row.label(text=severity, icon=severity_icons.get(severity, 'INFO'))

            # Clash count
            clash_count = getattr(item, 'clash_count', 0)
            row.label(text=f"{clash_count} clashes")
        else:
            layout.label(text="", translate=False)


class BIM_UL_resolution_options(UIList):
    """UIList for displaying resolution options"""

    def draw_item(
        self,
        context,
        layout: bpy.types.UILayout,
        data,
        item,
        icon,
        active_data,
        active_propname,
        index,
        fit_flag,
    ) -> None:
        if item:
            row = layout.row(align=True)

            # Option number (recommended first)
            if index == 0:
                row.label(text=f"Option {index + 1} ✓", icon="CHECKMARK")
            else:
                row.label(text=f"Option {index + 1}")

            # Resolution type
            resolution_type = getattr(item, 'resolution_type', 'Unknown')
            row.label(text=resolution_type)

            # Cost and effort
            effort_hours = getattr(item, 'effort_hours', 0.0)
            cost = getattr(item, 'cost', 0.0)
            row.label(text=f"{effort_hours:.1f}h / ${cost:,.0f}")

            # Risk level
            risk_icons = {
                'CRITICAL': 'ERROR',
                'HIGH': 'ERROR',
                'MEDIUM': 'INFO',
                'LOW': 'CHECKMARK'
            }
            risk = getattr(item, 'risk_level', 'MEDIUM')
            row.label(text=risk, icon=risk_icons.get(risk, 'INFO'))
        else:
            layout.label(text="", translate=False)


class BIM_PT_boq_export(Panel):
    """Bill of Quantities Export Panel"""
    bl_label = "Bill of Quantities (BOQ)"
    bl_idname = "BIM_PT_boq_export"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tab_clash_detection"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        assert self.layout
        layout = self.layout

        # Get federation database path
        fed_props = context.scene.BIMFederationProperties
        db_path = fed_props.federation_database_path

        # Check BOQ status
        import os
        import glob
        from datetime import datetime

        boq_exists = False
        boq_file = None
        boq_timestamp = ""
        has_qto_table = False

        # Search for existing BOQ files
        boq_pattern = os.path.expanduser("~/Documents/bonsai/BOQ_Comprehensive_*.xlsx")
        boq_files = sorted(glob.glob(boq_pattern), reverse=True)
        if boq_files:
            boq_file = boq_files[0]  # Most recent
            boq_exists = True
            mtime = os.path.getmtime(boq_file)
            boq_timestamp = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

        # Check if database has simple_qto table with data
        if db_path and os.path.exists(db_path):
            import sqlite3
            try:
                conn = sqlite3.connect(db_path)
                # Check if table exists
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='simple_qto'"
                )
                table_exists = cursor.fetchone() is not None

                # Check if table has data
                if table_exists:
                    cursor = conn.execute("SELECT COUNT(*) FROM simple_qto")
                    row_count = cursor.fetchone()[0]
                    has_qto_table = row_count > 0
                else:
                    has_qto_table = False

                conn.close()
            except:
                has_qto_table = False

        # Header with status indicator
        box = layout.box()
        row = box.row()
        row.label(text="Bill of Quantities (BOQ)", icon="TEXT")

        # Status indicator (right-aligned)
        status_row = row.row()
        status_row.alignment = 'RIGHT'
        if boq_exists and has_qto_table:
            status_row.label(text="Ready", icon="CHECKMARK")
        else:
            status_row.label(text="Not Ready", icon="INFO")

        # Info text
        info_col = box.column(align=True)
        info_col.scale_y = 0.7
        info_col.label(text="💡 Malaysian standards (CIDB 2024)", icon='INFO')
        info_col.label(text="   Materials + Labor + Equipment breakdown")

        box.separator()

        # Check database path
        if not db_path or not os.path.exists(db_path):
            warn_row = box.row()
            warn_row.alert = True
            warn_row.label(text="⚠ Set database in Multi-Model Federation panel first", icon='ERROR')
            return

        # Buttons - conditional layout
        if boq_exists:
            # Two buttons: Open existing + Regenerate
            row = box.row(align=True)
            row.scale_y = 1.5
            op = row.operator("bim.open_boq_report", text="Open BOQ", icon="DOCUMENTS")
            op.filepath = boq_file
            row.operator("bim.regenerate_boq_report", text="Regenerate", icon="FILE_REFRESH")

            # Show file info
            info_col = box.column(align=True)
            info_col.scale_y = 0.6
            info_col.label(text=f"Last generated: {boq_timestamp}")
            info_col.label(text=f"File: {os.path.basename(boq_file)}")
        else:
            # Single button: Generate
            row = box.row()
            row.scale_y = 1.5
            row.operator("bim.export_comprehensive_boq",
                         text="Generate BOQ Report",
                         icon="DOCUMENTS")

            # Helper text
            hint = box.column(align=True)
            hint.scale_y = 0.6
            if not has_qto_table:
                hint.label(text="(Database analysis will run automatically)")
            else:
                hint.label(text="(Click to generate Excel report)")
