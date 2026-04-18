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

from __future__ import annotations
import bpy
import os
import bonsai.tool as tool
from bpy.types import Panel, UIList
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bonsai.bim.module.clash.prop import BIMClashProperties

# Import label mapper for friendly IFC class names
from .ifc_label_mapper import get_friendly_label, get_discipline_label


# =============================================================================
# PARENT TAB PANELS (for old scattered UI - kept for compatibility)
# =============================================================================

class BIM_PT_tab_federation(Panel):
    """Old Federation parent tab (compatibility)"""
    bl_label = "Federation (Old)"
    bl_idname = "BIM_PT_tab_federation"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_options = {"HIDE_HEADER"}
    bl_order = 99  # Push to bottom

    def draw(self, context):
        pass


class BIM_PT_tab_clash_detection(Panel):
    """Clash Detection parent tab"""
    bl_label = "Clash Detection (Old)"
    bl_idname = "BIM_PT_tab_clash_detection"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_options = {"HIDE_HEADER"}
    bl_order = 98  # Push to bottom

    def draw(self, context):
        pass


# =============================================================================
# FEDERATED FILES UI
# =============================================================================

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
                "BIM_UL_federated_files", "", props, "federated_files", props, "active_federated_file_index"
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
            row.prop(
                props,
                "show_statistics",
                icon="TRIA_DOWN" if props.show_statistics else "TRIA_RIGHT",
                text="Federation Statistics",
                emboss=False,
            )

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
        # S189: Auto-restore DB path from baked .blend scene property
        if not props.federation_database_path:
            _saved = context.scene.get("fed_db_path", "")
            if _saved:
                from pathlib import Path as _PUI
                if _PUI(_saved).exists():
                    props.federation_database_path = _saved
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

        # Action buttons — R-Tree / Library / Clear
        col = box.column(align=True)

        # Row 1: R-Tree | Library (main workflow)
        row = col.row(align=True)
        row.scale_y = 1.5
        row.operator("bim.preview_federation_viewport", icon="OUTLINER_DATA_POINTCLOUD", text="R-Tree")
        row.operator("bim.link_federation_library", icon="ASSET_MANAGER", text="Library")

        # Row 2: Clear
        row = col.row(align=True)
        row.operator("bim.clear_federation_viewport", icon="PANEL_CLOSE", text="Clear")

        # Row 3: Legacy loaders (collapsed, for backward compat)
        row = col.row(align=True)
        row.scale_y = 0.8
        sub = row.row(align=True)
        sub.scale_x = 0.7
        sub.operator("bim.load_full_federation_viewport", icon="MESH_DATA", text="Full Load (legacy)")

        # Auto-reload setting
        box.separator()
        col = box.column()
        col.prop(props, "auto_reload_on_open", text="Auto-reload on file open")

        # Help section (collapsible)
        layout.separator()
        box = layout.box()
        row = box.row()
        row.prop(
            props,
            "show_help",
            icon="TRIA_DOWN" if props.show_help else "TRIA_RIGHT",
            text="Help & Usage Tips",
            emboss=False,
        )

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
            col.label(text="• Redo: Try different sample region")  # Bonsai - OpenBIM Blender Add-on


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

# === Federation Additions Panel (CRUD for manual elements) ===


class BIM_PT_federation_additions(Panel):
    """Panel for adding/editing elements in federation database"""

    bl_label = "Federation Additions"
    bl_idname = "BIM_PT_federation_additions"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_options = {"DEFAULT_CLOSED"}
    bl_parent_id = "BIM_PT_tab_federation"

    def draw(self, context):
        layout = self.layout
        props = context.scene.BIMFederationProperties
        obj = context.active_object

        # Info box
        box = layout.box()
        box.label(text="Add Custom Elements to Federation", icon="ADD")
        col = box.column(align=True)
        col.scale_y = 0.8
        col.label(text="Add site equipment, coordination geometry,")
        col.label(text="or temporary structures to federated model.")

        layout.separator()

        # Object status
        if obj:
            status_box = layout.box()
            status_box.label(text=f"Selected: {obj.name}", icon="OBJECT_DATA")

            if 'ifc_guid' in obj:
                # Object is tracked in federation
                col = status_box.column(align=True)
                col.label(text=f"GUID: {obj['ifc_guid'][:16]}...", icon="CHECKMARK")
                if 'ifc_class' in obj:
                    col.label(text=f"Class: {obj['ifc_class']}")
                if 'discipline' in obj:
                    col.label(text=f"Discipline: {obj['discipline']}")

                # Update/Remove buttons
                row = status_box.row(align=True)
                row.scale_y = 1.2
                row.operator("bim.update_federation_element", icon="FILE_REFRESH")
                row.operator("bim.remove_from_federation", icon="TRASH")
            else:
                # Object not in federation
                col = status_box.column(align=True)
                col.label(text="Not in federation", icon="INFO")

                # Add button
                row = status_box.row()
                row.scale_y = 1.5
                row.operator("bim.add_to_federation", icon="ADD")
        else:
            info_box = layout.box()
            info_box.label(text="No object selected", icon="INFO")

        layout.separator()

        # Query additions
        query_box = layout.box()
        query_box.label(text="View Additions", icon="VIEWZOOM")
        row = query_box.row()
        row.scale_y = 1.2
        row.operator("bim.query_federation_additions", icon="DOCUMENTS")

        # Usage help (collapsible)
        layout.separator()
        help_box = layout.box()
        help_box.label(text="Quick Start:", icon="QUESTION")
        col = help_box.column(align=True)
        col.scale_y = 0.7
        col.label(text="1. Create object in Blender (Shift+A)")
        col.label(text="2. Position it in scene (using GPS coords)")
        col.label(text="3. Select object, click 'Add to Federation'")
        col.label(text="4. Choose IFC class and discipline")
        col.label(text="5. Object persists across sessions")


# === Federation Analysis UI Panels (merged from federation_analysis module) ===
# Panels for discipline-based clash detection and LOD visualization


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
        if props.clash_preset == "CUSTOM":
            row = box.row(align=True)
            row.prop(props, "discipline_a", text="")
            row.label(text="vs")
            row.prop(props, "discipline_b", text="")

        # Tolerance
        row = box.row()
        row.prop(props, "discipline_tolerance")

        # Run button
        row = box.row()
        row.operator("bim.clash_by_discipline", text="Run Clash Detection", icon="PLAY")

        # Display discipline clash results
        if props.discipline_clash_loaded and props.discipline_clash_candidates:
            layout.separator()
            result_box = layout.box()
            result_box.label(text=f"{len(props.discipline_clash_candidates)} Clash Candidates Found", icon="ERROR")

            # Filter hint
            filter_row = result_box.row()
            filter_row.scale_y = 0.8
            filter_row.label(text="💡 Use filter box (🔍) to search: 'wall', 'door', 'ifcwall*', etc.", icon="INFO")

            # Header row
            header = result_box.row(align=True)
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
                "active_discipline_clash_index",
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
            gpu_row.operator("bim.enable_clash_gpu_visualization", text="GPU Overlay", icon="RESTRICT_VIEW_OFF")
            gpu_row.operator("bim.disable_clash_gpu_visualization", text="", icon="X")

            # Gizmo Visualization (Interactive 3D Markers) - Now with lazy loading!
            gizmo_row = viz_box.row(align=True)
            gizmo_row.operator(
                "bim.enable_clash_gizmo_visualization", text="Interactive Gizmos", icon="PIVOT_INDIVIDUAL"
            )
            gizmo_row.operator("bim.disable_clash_gizmo_visualization", text="", icon="X")

            # Info about gizmo features
            info_col = viz_box.column(align=True)
            info_col.scale_y = 0.7
            info_col.label(text="💡 Gizmo features:", icon="INFO")
            info_col.label(text="  • Left-click to jump to clash")
            info_col.label(text="  • Right-click for context menu")
            info_col.label(text="  • Color-coded: Red=New, Orange=Active, Yellow=Reviewed, Green=Resolved")

            # BCF Export
            layout.separator()
            bcf_box = layout.box()
            bcf_box.label(text="BCF Export", icon="EXPORT")

            bcf_row = bcf_box.row()
            bcf_row.operator("bim.export_bcf", text="Export to BCF 2.1", icon="FILE_TICK")

            # Info about BCF
            bcf_info = bcf_box.column(align=True)
            bcf_info.scale_y = 0.7
            bcf_info.label(text="💡 BCF (BIM Collaboration Format):", icon="INFO")
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

                # Get database path for label lookups
                fed_props = context.scene.BIMFederationProperties
                db_path = bpy.path.abspath(fed_props.federation_database_path) if fed_props.federation_database_path else None

                # Get friendly class names
                friendly_class_a = get_friendly_label(candidate.ifc_class_a, db_path=db_path)
                friendly_class_b = get_friendly_label(candidate.ifc_class_b, db_path=db_path)

                col.label(text=f"Element A: {candidate.name_a}")
                col.label(text=f"  GUID: {candidate.guid_a}")
                col.label(text=f"  Class: {friendly_class_a}")
                col.separator()
                col.label(text=f"Element B: {candidate.name_b}")
                col.label(text=f"  GUID: {candidate.guid_b}")
                col.label(text=f"  Class: {friendly_class_b}")


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
            info_row.label(text="⚠ Set database in Multi-Model Federation panel first", icon="ERROR")
            info_row = lod_box.row()
            info_row.label(text="   (Scene Properties → Multi-Model Federation)")
            return

        # LOD mode selector
        row = lod_box.row()
        row.prop(props, "lod_visualization_mode", text="")

        # BBox Wireframe controls (Level 0)
        if props.lod_visualization_mode == "BBOX_WIREFRAME":
            row = lod_box.row(align=True)
            if props.bbox_visualization_enabled:
                row.operator("bim.disable_bbox_visualization", text="Disable BBox View", icon="HIDE_ON")
            else:
                row.operator("bim.enable_bbox_visualization", text="Enable BBox View", icon="HIDE_OFF")

            # Element limit (for testing)
            row = lod_box.row()
            row.prop(props, "bbox_element_limit")
            if props.bbox_element_limit == 0:
                hint_row = lod_box.row()
                hint_row.scale_y = 0.6
                hint_row.label(text="💡 0 = All elements (44K+)", icon="INFO")

            # Stats toggle
            row = lod_box.row()
            row.prop(props, "show_lod_stats")

            # Info
            info_col = lod_box.column(align=True)
            info_col.scale_y = 0.7
            info_col.label(text="💡 BBox Wireframe:", icon="INFO")
            info_col.label(text="  • Instant loading (<3 seconds)")
            info_col.label(text="  • <10 MB memory usage")
            info_col.label(text="  • Color-coded by discipline")
            info_col.label(text="  • ACMV=Cyan, FP=Red, ELEC=Yellow")

        # Semantic Proxies (Level 1) - Basic Templates
        elif props.lod_visualization_mode == "SEMANTIC_PROXY":
            row = lod_box.row(align=True)
            if props.bbox_visualization_enabled:  # Reuse flag for any visualization mode
                row.operator(
                    "bim.disable_semantic_proxy_visualization", text="Disable Semantic Proxies", icon="HIDE_ON"
                )
            else:
                row.operator(
                    "bim.enable_semantic_proxy_visualization", text="Enable Semantic Proxies", icon="MESH_CUBE"
                )

            # Element limit (for testing)
            row = lod_box.row()
            row.prop(props, "bbox_element_limit", text="Element Limit")
            if props.bbox_element_limit == 0:
                hint_row = lod_box.row()
                hint_row.scale_y = 0.6
                hint_row.label(text="💡 0 = All elements (database-driven)", icon="INFO")

            # Info
            info_col = lod_box.column(align=True)
            info_col.scale_y = 0.7
            info_col.label(text="💡 Semantic Proxies:", icon="INFO")
            info_col.label(text="  • Basic procedural shapes from templates")
            info_col.label(text="  • Cylinders for round ducts/pipes")
            info_col.label(text="  • Boxes for rectangular ducts/trays")
            info_col.label(text="  • Database-driven (no IFC files)")
            info_col.label(text="  • Memory: ~100-200MB per 1000 elements")

        # Full IFC Geometry (Level 2) - Load from database
        elif props.lod_visualization_mode == "FULL_GEOMETRY":
            row = lod_box.row(align=True)
            if props.bbox_visualization_enabled:  # Reuse flag for any visualization mode
                row.operator("bim.disable_full_geometry_visualization", text="Disable Full Geometry", icon="HIDE_ON")
            else:
                row.operator("bim.enable_full_geometry_visualization", text="Enable Full Geometry", icon="IMPORT")

            # Element limit (for testing)
            row = lod_box.row()
            row.prop(props, "bbox_element_limit", text="Element Limit")
            if props.bbox_element_limit == 0:
                hint_row = lod_box.row()
                hint_row.scale_y = 0.6
                hint_row.label(text="💡 0 = All elements (may take time)", icon="INFO")

            # Info
            info_col = lod_box.column(align=True)
            info_col.scale_y = 0.7
            info_col.label(text="💡 Full Geometry:", icon="INFO")
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
            row = layout.row(align=True)

            # Checkbox column
            row.prop(item, "selected", text="")

            # Element A | Element B - Show friendly IFC class names
            # Get database path for label lookups
            fed_props = context.scene.BIMFederationProperties
            db_path = bpy.path.abspath(fed_props.federation_database_path) if fed_props.federation_database_path else None
            # Get friendly labels
            friendly_a = get_friendly_label(item.ifc_class_a, db_path=db_path)
            friendly_b = get_friendly_label(item.ifc_class_b, db_path=db_path)
            row.label(text=f"{friendly_a}  |  {friendly_b}", translate=False)
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

                pattern = filter_text.replace("*", ".*")

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
            info_box.label(text="⚠ Run clash detection first", icon="INFO")
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
        row.operator("bim.analyze_clash_groups", text="Analyze Clash Groups", icon="AUTO")

        # Show grouping results if available
        if hasattr(props, "clash_groups_analyzed") and props.clash_groups_analyzed:
            result_box = layout.box()
            result_box.label(text="Grouping Results:", icon="CHECKMARK")
            result_box.label(text="  (Check Blender console for details)")

            # ================================================================
            # STEP 2: SELECT GROUP & PREVIEW
            # ================================================================
            layout.separator()
            action_box = layout.box()
            action_box.label(text="Step 2: Select Group & Preview", icon="PLAY")

            # Group selector dropdown (replaces overwhelming options dropdown)
            row = action_box.row()
            row.prop(props, "selected_clash_group", text="Clash Group")

            # Preview button (now previews the entire group)
            row = action_box.row()
            row.scale_y = 1.3
            row.enabled = bool(props.selected_clash_group and props.selected_clash_group != "NONE")
            row.operator("bim.preview_clash_group", text="Preview Group in 3D", icon="HIDE_OFF")

            # Clear preview button
            row = action_box.row()
            row.scale_y = 1.0
            row.operator("bim.clear_preview", text="Clear Preview", icon="X")

            # ================================================================
            # RESOLUTION OPTIONS INFO PANEL (Read-Only)
            # ================================================================
            if props.selected_clash_group and props.selected_clash_group != "NONE":
                layout.separator()

                options_box = layout.box()
                options_box.label(text="Resolution Options (Study Only)", icon="INFO")

                # Get resolution options for selected group
                from bonsai.bim.module.federation.prop import get_resolution_options_for_group
                options = get_resolution_options_for_group(context)

                if options:
                    for opt in options:
                        opt_col = options_box.column(align=True)
                        opt_col.scale_y = 0.8

                        # Option header
                        header_row = opt_col.row()
                        if opt['is_recommended']:
                            header_row.label(text=f"✓ Option {opt['rank']} (Recommended):", icon="CHECKMARK")
                        else:
                            header_row.label(text=f"○ Option {opt['rank']}:", icon="DOT")

                        # Description
                        desc_text = opt['description'][:80] + "..." if len(opt['description']) > 80 else opt['description']
                        opt_col.label(text=f"  {desc_text}")

                        # Cost/effort details
                        details_row = opt_col.row()
                        details_row.label(text=f"  Design: {opt['hours']:.1f} hrs (${opt['cost']:,.0f})")
                        details_row.label(text=f"Schedule: {opt['days']:.0f} days")
                        details_row.label(text=f"Risk: {opt['risk']}")

                        opt_col.separator()

                    # Info note
                    note_col = options_box.column(align=True)
                    note_col.scale_y = 0.7
                    note_col.label(text="💡 Options are for study/reports only", icon="INFO")
                    note_col.label(text="   See generated report for full analysis")
                else:
                    options_box.label(text="No resolution options generated yet")
                    options_box.label(text="Run 'Generate Resolution Options' first")

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
                row.operator("bim.submit_resolution_feedback", text="Submit Feedback", icon="EXPORT")

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
            row.operator("bim.generate_clash_resolution_report", text="Generate Report", icon="FILE_TEXT")

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
            severity_icons = {"CRITICAL": "ERROR", "HIGH": "ERROR", "MEDIUM": "INFO", "LOW": "CHECKMARK"}
            severity = getattr(item, "severity", "MEDIUM")
            row.label(text=severity, icon=severity_icons.get(severity, "INFO"))

            # Clash count
            clash_count = getattr(item, "clash_count", 0)
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

            # Resolution type - Replace IFC class names with friendly labels
            resolution_type = getattr(item, "resolution_type", "Unknown")

            # Parse and replace IFC class names (e.g., "IfcOpeningElement(8)" -> "Opening(8)")
            import re

            fed_props = context.scene.BIMFederationProperties
            db_path = bpy.path.abspath(fed_props.federation_database_path) if fed_props.federation_database_path else None

            def replace_ifc_class(match):
                ifc_class = match.group(1)
                count = match.group(2)
                friendly = get_friendly_label(ifc_class, db_path=db_path)
                # Pluralize if count > 1
                plural = friendly + "s" if int(count) > 1 else friendly
                return f"{count} {plural}"

            # Replace pattern like "IfcOpeningElement(8) Coordinate $1.1k 10h MED"
            # with "8 Openings → Coordinate ($1.1k, 10h, MED)"
            friendly_resolution_type = re.sub(r"(Ifc\w+)\((\d+)\)", replace_ifc_class, resolution_type)

            # Reformat: Extract action and details, add arrow
            # Pattern: "5 HVAC Duct Segments Reroute Mep $0.9k 7h MED"
            # Split into: element count/type + action + cost/time/confidence
            parts = friendly_resolution_type.split()
            if len(parts) >= 3:
                # Find where the action starts (after the element description)
                # Simple heuristic: action words are "Coordinate", "Reroute", "Lower", etc.
                action_words = ["Coordinate", "Reroute", "Lower", "Raise", "Resize", "Move"]
                action_idx = None
                for i, part in enumerate(parts):
                    if any(part.startswith(word) for word in action_words):
                        action_idx = i
                        break

                if action_idx:
                    element_part = " ".join(parts[:action_idx])  # "5 HVAC Duct Segments"
                    action_part = " ".join(parts[action_idx:])  # "Reroute Mep $0.9k 7h MED"

                    # Extract cost, time, confidence if present
                    cost_match = re.search(r"\$[\d.]+k?", action_part)
                    time_match = re.search(r"\d+\.?\d*h", action_part)
                    conf_match = re.search(r"(LOW|MED|HIGH|CRITICAL)", action_part)

                    if cost_match and time_match and conf_match:
                        action_name = action_part[: cost_match.start()].strip()
                        details = f"({cost_match.group()}, {time_match.group()}, {conf_match.group()})"
                        friendly_resolution_type = f"{element_part} → {action_name} {details}"

            row.label(text=friendly_resolution_type)

            # Risk level
            risk_icons = {"CRITICAL": "ERROR", "HIGH": "ERROR", "MEDIUM": "INFO", "LOW": "CHECKMARK"}
            risk = getattr(item, "risk_level", "MEDIUM")
            row.label(text=risk, icon=risk_icons.get(risk, "INFO"))
        else:
            layout.label(text="", translate=False)


class BIM_PT_tab_4d_5d(Panel):
    """4D/5D BIM Tab"""

    bl_label = "4D/5D BIM"
    bl_idname = "BIM_PT_tab_4d_5d"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_order = 4

    def draw(self, context):
        pass


class BIM_PT_4d_schedule_export(Panel):
    """4D Construction Schedule Export Panel"""

    bl_label = "4D Construction Schedule"
    bl_idname = "BIM_PT_4d_schedule_export"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tab_4d_5d"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        assert self.layout
        layout = self.layout

        # Get federation database path
        fed_props = context.scene.BIMFederationProperties
        db_path = bpy.path.abspath(fed_props.federation_database_path) if fed_props.federation_database_path else None

        # Check schedule status
        import os
        import glob
        from datetime import datetime
        from pathlib import Path

        schedule_exists = False
        schedule_file = None
        schedule_timestamp = ""
        has_schedule_table = False
        task_count = 0

        # Search for existing schedule XML files in WORK_DIR/schedules/
        if db_path and os.path.exists(db_path):
            db_path_obj = Path(db_path)
            work_dir = db_path_obj.parent.parent  # ../.. from databases/Terminal1.db
            schedules_dir = work_dir / "schedules"

            if schedules_dir.exists():
                schedule_pattern = str(schedules_dir / "Terminal1_Schedule_*.xml")
                schedule_files = sorted(glob.glob(schedule_pattern), reverse=True)
                if schedule_files:
                    schedule_file = schedule_files[0]  # Most recent
                    schedule_exists = True
                    mtime = os.path.getmtime(schedule_file)
                    schedule_timestamp = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")

        # Check if database has construction_schedule table with data
        if db_path and os.path.exists(db_path):
            import sqlite3

            try:
                conn = sqlite3.connect(db_path)
                # Check if table exists
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='construction_schedule'")
                table_exists = cursor.fetchone() is not None

                # Check if table has data
                if table_exists:
                    cursor = conn.execute("SELECT COUNT(*) FROM construction_schedule")
                    task_count = cursor.fetchone()[0]
                    has_schedule_table = task_count > 0
                else:
                    has_schedule_table = False

                conn.close()
            except:
                has_schedule_table = False

        # Header with status indicator
        box = layout.box()
        row = box.row()
        row.label(text="4D Construction Schedule", icon="TIME")

        # Status indicator (right-aligned)
        status_row = row.row()
        status_row.alignment = "RIGHT"
        if has_schedule_table:
            status_row.label(text="Ready", icon="CHECKMARK")
        else:
            status_row.label(text="Not Generated", icon="INFO")

        # Info text
        info_col = box.column(align=True)
        info_col.scale_y = 0.7
        info_col.label(text="💡 MS Project XML export format", icon="INFO")
        info_col.label(text="   Duration from labor productivity (CIDB 2024)")

        box.separator()

        # Check database path
        if not db_path or not os.path.exists(db_path):
            warn_row = box.row()
            warn_row.alert = True
            warn_row.label(text="⚠ Set database in Multi-Model Federation panel first", icon="ERROR")
            return

        # Step 1: Generate Schedule
        step_box = box.box()
        step_row = step_box.row()
        step_row.label(text="Step 1: Generate Schedule", icon="SEQUENCE")

        if has_schedule_table:
            # Schedule exists - show info and regenerate option
            info_col = step_box.column(align=True)
            info_col.scale_y = 0.7
            info_col.label(text=f"✓ {task_count} tasks in database")

            row = step_box.row(align=True)
            row.scale_y = 1.3
            row.operator("bim.generate_construction_schedule", text="Regenerate Schedule", icon="FILE_REFRESH")
        else:
            # No schedule - show generate button
            row = step_box.row()
            row.scale_y = 1.5
            row.operator("bim.generate_construction_schedule", text="Generate Schedule", icon="PLAY")

            hint = step_box.column(align=True)
            hint.scale_y = 0.6
            hint.label(text="(Analyzes elements and calculates task durations)")

        box.separator()

        # Step 2: Export Schedule
        step_box = box.box()
        step_row = step_box.row()
        step_row.label(text="Step 2: Export Schedule", icon="EXPORT")

        if schedule_exists and has_schedule_table:
            # Both schedule table and XML file exist
            row = step_box.row(align=True)
            row.scale_y = 1.3

            # Open existing button
            op = row.operator("bim.open_boq_report", text="Open XML", icon="FILE_FOLDER")
            op.filepath = schedule_file

            # Export buttons
            row.operator("bim.export_mpp_schedule", text="XML", icon="EXPORT")
            row.operator("bim.export_schedule_excel", text="Excel", icon="DOCUMENTS")

            # Show file info
            info_col = step_box.column(align=True)
            info_col.scale_y = 0.6
            info_col.label(text=f"Last exported: {schedule_timestamp}")
            info_col.label(text=f"File: {os.path.basename(schedule_file)}")

        elif has_schedule_table:
            # Schedule table exists but no XML file
            row = step_box.row(align=True)
            row.scale_y = 1.3
            row.operator("bim.export_mpp_schedule", text="Export to XML (MS Project)", icon="EXPORT")
            row.operator("bim.export_schedule_excel", text="Export to Excel", icon="DOCUMENTS")

            hint = step_box.column(align=True)
            hint.scale_y = 0.6
            hint.label(text="XML: For MS Project/ProjectLibre | Excel: For spreadsheet viewers")
        else:
            # No schedule table - disabled
            row = step_box.row(align=True)
            row.scale_y = 1.3
            row.enabled = False
            row.operator("bim.export_mpp_schedule", text="Export to XML", icon="EXPORT")
            row.operator("bim.export_schedule_excel", text="Export to Excel", icon="DOCUMENTS")

            hint = step_box.column(align=True)
            hint.scale_y = 0.6
            hint.alert = True
            hint.label(text="(Generate schedule first)")

        box.separator()

        # Step 3: Animate 4D Construction
        step_box = box.box()
        step_row = step_box.row()
        step_row.label(text="Step 3: Animate Construction (4D)", icon="PLAY")

        if has_schedule_table:
            # Schedule exists - enable animation
            row = step_box.row(align=True)
            row.scale_y = 1.5
            op = row.operator("bim.animate_4d_construction", text="🎬 Create 4D Animation", icon="SEQUENCE")

            hint = step_box.column(align=True)
            hint.scale_y = 0.6
            hint.label(text="Shows construction sequence over time in Blender viewport")
            hint.label(text="Press SPACE to play timeline after creating animation")
        else:
            # No schedule - disabled
            row = step_box.row(align=True)
            row.scale_y = 1.5
            row.enabled = False
            row.operator("bim.animate_4d_construction", text="Create 4D Animation", icon="SEQUENCE")

            hint = step_box.column(align=True)
            hint.scale_y = 0.6
            hint.alert = True
            hint.label(text="(Generate schedule first)")

        # Compatibility info
        box.separator()
        compat_box = box.box()
        compat_box.label(text="Compatible Software:", icon="INFO")
        compat_col = compat_box.column(align=True)
        compat_col.scale_y = 0.7
        compat_col.label(text="  • Microsoft Project 2010+")
        compat_col.label(text="  • ProjectLibre (free & open source)")
        compat_col.label(text="  • Primavera P6 (via import)")
        compat_col.label(text="  • Asta Powerproject")


class BIM_PT_boq_export(Panel):
    """Bill of Quantities Export Panel"""

    bl_label = "Bill of Quantities (5D)"
    bl_idname = "BIM_PT_boq_export"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tab_4d_5d"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        assert self.layout
        layout = self.layout

        # Get federation database path
        fed_props = context.scene.BIMFederationProperties
        db_path = bpy.path.abspath(fed_props.federation_database_path) if fed_props.federation_database_path else None

        # Check BOQ status
        import os
        import glob
        from datetime import datetime
        from pathlib import Path

        boq_exists = False
        boq_file = None
        boq_timestamp = ""
        has_qto_table = False

        # Search for existing BOQ files in WORK_DIR/boq_reports/
        if db_path and os.path.exists(db_path):
            db_path_obj = Path(db_path)
            work_dir = db_path_obj.parent.parent  # ../.. from databases/Terminal1.db
            boq_reports_dir = work_dir / "boq_reports"

            if boq_reports_dir.exists():
                boq_pattern = str(boq_reports_dir / "BOQ_Comprehensive_*.xlsx")
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
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='simple_qto'")
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
        status_row.alignment = "RIGHT"
        if boq_exists and has_qto_table:
            status_row.label(text="Ready", icon="CHECKMARK")
        else:
            status_row.label(text="Not Ready", icon="INFO")

        # Info text
        info_col = box.column(align=True)
        info_col.scale_y = 0.7
        info_col.label(text="💡 Malaysian standards (CIDB 2024)", icon="INFO")
        info_col.label(text="   Materials + Labor + Equipment breakdown")

        box.separator()

        # Check database path
        if not db_path or not os.path.exists(db_path):
            warn_row = box.row()
            warn_row.alert = True
            warn_row.label(text="⚠ Set database in Multi-Model Federation panel first", icon="ERROR")
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
            row.operator("bim.export_comprehensive_boq", text="Generate BOQ Report", icon="DOCUMENTS")

            # Helper text
            hint = box.column(align=True)
            hint.scale_y = 0.6
            if not has_qto_table:
                hint.label(text="(Database analysis will run automatically)")
            else:
                hint.label(text="(Click to generate Excel report)")


class BIM_PT_structural_works(Panel):
    """Structural Works - Rebar & Concrete BOQ"""

    bl_label = "Structural Works"
    bl_idname = "BIM_PT_structural_works"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tab_federation"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        fed_props = context.scene.BIMFederationProperties
        structural_props = context.scene.BIMStructuralProperties

        # Get database path
        db_path = bpy.path.abspath(fed_props.federation_database_path) if fed_props.federation_database_path else None

        # Header with icon
        box = layout.box()
        row = box.row()
        row.label(text="Rebar & Concrete", icon="FORCE_HARMONIC")

        # Status indicator
        status_row = row.row()
        status_row.alignment = "RIGHT"
        if structural_props.rebar_generated:
            status_row.label(text="Ready", icon="CHECKMARK")
        elif db_path and os.path.exists(db_path):
            status_row.label(text="Not Generated", icon="BLANK1")
        else:
            status_row.label(text="No Database", icon="ERROR")

        # Info text
        info_col = box.column(align=True)
        info_col.scale_y = 0.6
        info_col.label(text="Automatic reinforcement design & BOQ export")
        info_col.label(text="MS 1347:2020 compliant | 97% time savings")

        box.separator()

        # Check database
        if not db_path or not os.path.exists(db_path):
            warn_row = box.row()
            warn_row.alert = True
            warn_row.label(text="⚠ Set database path first", icon="ERROR")
            return

        # Settings (collapsible)
        settings_box = layout.box()
        settings_row = settings_box.row()
        settings_row.prop(
            structural_props,
            "show_structural_settings",
            icon="TRIA_DOWN" if structural_props.show_structural_settings else "TRIA_RIGHT",
            text="Settings",
            emboss=False
        )

        if structural_props.show_structural_settings:
            settings_col = settings_box.column(align=True)
            settings_col.prop(structural_props, "project_name")
            settings_col.separator()
            settings_col.prop(structural_props, "is_airport_grade")
            settings_col.prop(structural_props, "concrete_grade")
            settings_col.prop(structural_props, "exposure_class")

        # Step 1: Generate Rebar
        box = layout.box()
        row = box.row()
        row.label(text="Step 1: Generate Rebar Design", icon="MOD_BUILD")

        if structural_props.rebar_generated and structural_props.last_generation_time:
            # Show status + regenerate button
            status_col = box.column(align=True)
            status_col.scale_y = 0.7
            status_col.label(text=f"✓ Generated: {structural_props.last_generation_time}")

            row = box.row(align=True)
            row.operator("bim.generate_rebar_structural", text="Regenerate", icon="FILE_REFRESH")
        else:
            # Show generate button
            row = box.row()
            row.scale_y = 1.5
            row.operator("bim.generate_rebar_structural", text="Generate Rebar Design", icon="MOD_BUILD")

            hint = box.column(align=True)
            hint.scale_y = 0.6
            hint.label(text="(Processes STR discipline: slabs, beams, columns)")

        # Step 2: Export Structural BOQ
        box = layout.box()
        row = box.row()
        row.label(text="Step 2: Export Structural BOQ", icon="DOCUMENTS")

        if structural_props.last_boq_export and structural_props.last_boq_file:
            # Show status + buttons
            status_col = box.column(align=True)
            status_col.scale_y = 0.7
            status_col.label(text=f"Last exported: {structural_props.last_boq_export}")
            status_col.label(text=f"File: {os.path.basename(structural_props.last_boq_file)}")

            row = box.row(align=True)
            row.operator("bim.export_structural_boq", text="Regenerate", icon="FILE_REFRESH")

            if os.path.exists(structural_props.last_boq_file):
                op = row.operator("bim.open_boq_report", text="Open", icon="FILE_FOLDER")
                op.filepath = structural_props.last_boq_file
        else:
            # Show generate button
            row = box.row()
            row.scale_y = 1.5
            row.operator("bim.export_structural_boq", text="Export Structural BOQ", icon="DOCUMENTS")

            hint = box.column(align=True)
            hint.scale_y = 0.6
            if structural_props.rebar_generated:
                hint.label(text="(Concrete + Reinforcement)")
            else:
                hint.label(text="(Concrete only - generate rebar first for full BOQ)")

        # Help text
        help_box = layout.box()
        help_col = help_box.column(align=True)
        help_col.scale_y = 0.6
        help_col.label(text="ℹ️ Structural BOQ vs Comprehensive BOQ:")
        help_col.label(text="  • Structural: Concrete + Rebar (MS 1347:2020)")
        help_col.label(text="  • Comprehensive: All disciplines (PWD Form 203A)")


class BIM_PT_nlp_query(Panel):
    """Natural Language Query Panel"""

    bl_label = "Natural Language Query (NLP)"
    bl_idname = "BIM_PT_nlp_query"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tab_federation"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        props = context.scene.BIMFederationProperties

        # Get database path
        db_path = bpy.path.abspath(props.federation_database_path) if props.federation_database_path else None

        # Header with info
        box = layout.box()
        row = box.row()
        row.label(text="Natural Language Query (NLP)", icon="VIEWZOOM")

        # Status indicator
        status_row = row.row()
        status_row.alignment = "RIGHT"
        if db_path and os.path.exists(db_path):
            status_row.label(text="Ready", icon="CHECKMARK")
        else:
            status_row.label(text="No Database", icon="ERROR")

        # Info text
        info_col = box.column(align=True)
        info_col.scale_y = 0.7
        info_col.label(text="💡 Ask questions in plain English", icon="INFO")
        info_col.label(text="   Powered by FTS5 full-text search")

        box.separator()

        # Check database
        if not db_path or not os.path.exists(db_path):
            warn_row = box.row()
            warn_row.alert = True
            warn_row.label(text="⚠ Set database path first", icon="ERROR")
            return

        # Query input
        query_box = layout.box()
        query_box.label(text="Enter Query:", icon="EXPERIMENTAL")

        # Text input for query
        row = query_box.row()
        row.prop(props, "nlp_query_text", text="", icon="VIEWZOOM")

        # Execute button
        row = query_box.row(align=True)
        row.scale_y = 1.3
        execute_op = row.operator("bim.execute_nlp_query", text="Search", icon="PLAY")
        row.operator("bim.clear_nlp_results", text="Clear", icon="X")

        # Suggested queries section
        suggest_box = layout.box()
        suggest_box.label(text="Suggested Queries:", icon="LIGHT")

        # Create two columns for suggested queries
        col_split = suggest_box.split(factor=0.5)

        # Column 1
        col1 = col_split.column()
        col1.scale_y = 0.9

        queries_col1 = [
            "How many beams?",
            "How many doors?",
            "Find lights from Linergy",
            "Total building cost",
            "Floor area",
        ]

        for query in queries_col1:
            op = col1.operator("bim.set_nlp_query", text=query, icon="RIGHTARROW_THIN")
            op.query_text = query

        # Column 2
        col2 = col_split.column()
        col2.scale_y = 0.9

        queries_col2 = [
            "How much concrete?",
            "Cost of ACMV work",
            "Which disciplines exist?",
            "Search for AHU",
            "Show ACMV elements",
        ]

        for query in queries_col2:
            op = col2.operator("bim.set_nlp_query", text=query, icon="RIGHTARROW_THIN")
            op.query_text = query

        # Results section (if results exist)
        if hasattr(props, "nlp_results_count") and props.nlp_results_count > 0:
            results_box = layout.box()
            results_box.label(text=f"Results ({props.nlp_results_count} rows):", icon="DOCUMENTS")

            # Display results summary
            if hasattr(props, "nlp_results_text"):
                results_col = results_box.column(align=True)
                results_col.scale_y = 0.7

                # Split results text into lines and display (max 15 lines)
                lines = props.nlp_results_text.split("\n")[:15]
                for line in lines:
                    if line.strip():
                        results_col.label(text=line)

                if len(props.nlp_results_text.split("\n")) > 15:
                    results_col.label(text="... (see console for full results)")

            # Export button
            row = results_box.row()
            row.operator("bim.export_nlp_results", text="Export to CSV", icon="EXPORT")


# ── S178: RTree Inspector — N-panel in 3D Viewport ───────────────────────────

class BIM_PT_rtree_inspector(bpy.types.Panel):
    """Search + pick elements in the GPU R-Tree overlay without creating objects."""
    bl_label = "RTree Inspector"
    bl_idname = "BIM_PT_rtree_inspector"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'BIM'
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        props = context.scene.BIMFederationProperties
        from . import bbox_visualization as bv
        import re as _re

        has_building = bool(bv._active_building)
        has_storey = bool(bv._active_storey)
        has_storeys_list = bool(bv._building_storeys)

        # ── SEARCH ──
        row = layout.row(align=True)
        row.prop(props, "rtree_search", text="", icon='VIEWZOOM')
        row.operator("bim.fed_rtree_search", text="", icon='PLAY')

        # ── S187: Quick-pick buttons (shown when idle — no results, no drill-down) ──
        if not bv._search_results and not has_building and bv._search_suggestions:
            # Split: first 5 are types/disciplines, rest are buildings
            type_picks = [s for s in bv._search_suggestions if s != '*'][:5]
            bld_picks = [s for s in bv._search_suggestions if s != '*'][5:]
            # Types row
            if type_picks:
                grid = layout.grid_flow(row_major=True, columns=3, align=True)
                grid.scale_y = 0.9
                for s in type_picks:
                    op = grid.operator("bim.fed_rtree_search", text=s, icon='NONE')
                    op.term = s
            # Buildings
            if bld_picks:
                layout.separator(factor=0.2)
                bx = layout.box()
                bx.label(text="BUILDINGS", icon='WORLD')
                bgrid = bx.grid_flow(row_major=True, columns=2, align=True)
                bgrid.scale_y = 0.85
                for s in bld_picks:
                    op = bgrid.operator("bim.fed_rtree_search", text=s, icon='HOME')
                    op.term = s
            # Show all
            row_all = layout.row(align=True)
            op_all = row_all.operator("bim.fed_rtree_search", text="* Show All", icon='WORLD')
            op_all.term = "*"

        # ── L0: BUILDING LIST (city level — no building drilled into) ──
        if props.rtree_result_count and bv._search_results:
            box = layout.box()
            box.label(text=f"BUILDINGS  \u2014 '{props.rtree_search}'", icon='WORLD')
            col = box.column(align=True)
            col.scale_y = 1.1
            for i, r in enumerate(bv._search_results):
                building = r.get('building', '?')
                count    = r.get('count', 0)
                n_tiles  = r.get('tile_count', 1)
                active   = (building == bv._active_building)
                row2 = col.row(align=True)
                row2.alert = active
                badge = f" \u00d7{n_tiles}" if n_tiles > 1 else ""
                disp = _re.sub(r'^[TS]\d+_(\d+_)?', '', building)
                op = row2.operator("bim.fed_rtree_fly_to_result",
                                   text=f"{disp}{badge}  ({count:,})", icon='HOME')
                op.result_index = i

        elif props.rtree_search:
            layout.label(text="No results", icon='ERROR')

        # ── L1+: BUILDING COCKPIT (when building drilled into) ──
        if has_building and props.rtree_bld_total > 0:
            layout.separator(factor=0.3)
            bx = layout.box()
            disp_bld = _re.sub(r'^[TS]\d+_(\d+_)?', '', bv._active_building)

            # S187: Breadcrumb header with back navigation at every level
            hdr = bx.row(align=True)
            if has_storey:
                # L2: Building > Storey — back returns to building
                hdr.operator("bim.fed_rtree_back_to_building",
                             text="", icon='BACK')
                hdr.label(text=f"{disp_bld}  >  {bv._active_storey}")
            else:
                # L1: Building — back returns to city (empty search = home)
                op_home = hdr.operator("bim.fed_rtree_search",
                                       text="", icon='BACK')
                op_home.term = "_HOME_"
                hdr.label(text=disp_bld, icon='HOME')

            # ── STOREY LIST (L1: building has storeys, none selected yet) ──
            if has_storeys_list and not has_storey:
                st_box = bx.box()
                st_box.label(text=f"FLOORS ({len(bv._building_storeys)})",
                             icon='LINENUMBERS_ON')
                st_col = st_box.column(align=True)
                st_col.scale_y = 1.0
                for st in bv._building_storeys:
                    # S186-s2: show element count from cached bbox
                    st_info = bv._building_storey_bboxes.get(st)
                    st_cnt = f"  ({st_info['count']:,})" if st_info else ""
                    op_st = st_col.operator("bim.fed_rtree_fly_to_storey",
                                            text=f"{st}{st_cnt}", icon='TRIA_RIGHT')
                    op_st.storey = st

            # ── CLASS GROUPS (fallback: no storeys at all) ──
            elif not has_storeys_list and not has_storey and bv._building_class_groups:
                cg_box = bx.box()
                cg_box.label(text="ELEMENT TYPES", icon='OBJECT_DATA')
                cg_col = cg_box.column(align=True)
                cg_col.scale_y = 0.9
                for cg in bv._building_class_groups:
                    short = cg['ifc_class'].replace('Ifc', '').replace('StandardCase', '')
                    cg_col.label(text=f"{short}  ({cg['count']:,})")

            # ── Discipline filter + HUD drag ──
            _hud_row = bx.row(align=True)
            _hud_row.scale_y = 0.7
            _hud_row.operator("bim.fed_progress_hud_drag", text="", icon='GRIP')
            _hud_row.label(text="Disciplines (drag HUD \u2192)")
            self._draw_discipline_bars(bx, props, bv)

            # ── S187: IFC type list within active discipline filter ──
            if bv._active_disc_filter and bv._disc_class_groups:
                dt_box = bx.box()
                dt_hdr = dt_box.row(align=True)
                # Back to building (clear disc filter)
                op_back = dt_hdr.operator("bim.fed_rtree_filter_disc",
                                          text="", icon='BACK')
                op_back.disc = ""
                dt_hdr.label(text=f"{bv._active_disc_filter} TYPES",
                             icon='OBJECT_DATA')
                dt_col = dt_box.column(align=True)
                dt_col.scale_y = 0.95
                for cg in bv._disc_class_groups:
                    short = cg['ifc_class'].replace('Ifc', '').replace('StandardCase', '')
                    op_cg = dt_col.operator("bim.fed_rtree_search",
                                            text=f"{short}  ({cg['count']:,})",
                                            icon='TRIA_RIGHT')
                    op_cg.term = cg['ifc_class']

        # ── ELEMENT LIST (L2 — shown when storey is active, or building has no storeys) ──
        # S191: elements list only at storey/disc level (not building top level)
        if has_building and has_storey and bv._building_elements:
            layout.separator(factor=0.3)
            box2 = layout.box()
            scope_label = bv._active_storey if has_storey else "top"
            busy = bv._overnight_running or (has_building and bv._active_building in bv._baking_buildings)
            show = props.rtree_show_elements and not busy
            hdr = box2.row(align=True)
            hdr.prop(props, "rtree_show_elements",
                     icon='TRIA_DOWN' if show else 'TRIA_RIGHT',
                     text=f"ELEMENTS \u2014 {scope_label} ({len(bv._building_elements)})",
                     emboss=False)
            if show:
                col2 = box2.column(align=True)
                col2.scale_y = 0.95
                for j, e in enumerate(bv._building_elements):
                    ifc_cls = e.get('ifc_class', '')
                    etype   = e.get('element_type') or e.get('name') or ''
                    storey  = e.get('storey', '')
                    guid    = e.get('guid', '')
                    parts = [p for p in [ifc_cls, etype[:20] if etype else None, storey] if p]
                    label = '  \u00b7  '.join(parts) if parts else guid[:20]
                    row3 = col2.row(align=True)
                    op2 = row3.operator("bim.fed_rtree_fly_to_element",
                                        text=label, icon='RADIOBUT_ON')
                    op2.elem_index = j
                    if guid:
                        op_cp = row3.operator("bim.fed_rtree_copy_guid", text="", icon='COPYDOWN')
                        op_cp.guid = guid

        # ── MESH / SHRED actions ──
        # S186: Only shown after drilling into a building (L1+), NOT at L0 city level.
        # Discipline buttons are DYNAMIC — read from actual DB data.
        # S186-s2: greyed when building is being baked offline.
        is_baking = has_building and bv._active_building in bv._baking_buildings
        if has_building and props.rtree_bld_total > 0:
            layout.separator(factor=0.3)
            act_box = layout.box()

            # S191: simplified N-panel — just action buttons. Progress in GPU HUD.
            scope_txt = f"MESH ({bv._active_storey})" if has_storey else "MESH ACTIONS"
            act_box.label(text=scope_txt, icon='IMPORT')
            disc_list = list(bv._building_disc_counts.keys()) if bv._building_disc_counts else ['ARC', 'STR', 'MEP', 'ELEC', 'FP']
            grid = act_box.grid_flow(row_major=True, columns=3, align=True)
            for disc in disc_list:
                op3 = grid.operator("bim.fed_rtree_load_mesh",
                                    text=f"+{disc}", icon='NONE')
                op3.target_disc = disc

            sh_row = act_box.row(align=True)
            sh_row.scale_y = 1.2
            sh_row.operator("bim.fed_rtree_shred", text="SHRED SELECTED  \u2702", icon='TRASH')

            act_box.separator(factor=0.3)
            # Action row: OVERNIGHT + BACKEND + controls
            btn_row = act_box.row(align=True)
            if bv._overnight_running:
                if bv._overnight_paused:
                    btn_row.operator("bim.fed_rtree_overnight_pause",
                                     text="RESUME", icon='PLAY')
                else:
                    btn_row.operator("bim.fed_rtree_overnight_pause",
                                     text="PAUSE", icon='PAUSE')
                btn_row.operator("bim.fed_rtree_overnight_cancel",
                                 text="CANCEL", icon='X')
                # SHORT-CUT → Backend
                if bv._overnight_shortcut_factor > 0:
                    sc_row = act_box.row(align=True)
                    sc_row.scale_y = 1.3
                    eta_txt = bv._overnight_shortcut_eta or "?"
                    sc_row.operator("bim.fed_rtree_switch_offline",
                                    text=f"\u26a1 BACKEND  ~{eta_txt}",
                                    icon='NONE')
            elif bv._overnight_progress and not bv._overnight_running:
                is_done = (bv._overnight_progress.startswith("DONE")
                           or bv._overnight_progress.startswith("\u2713"))
                if is_done:
                    btn_row.operator("bim.fed_rtree_overnight_dismiss",
                                     text="OK", icon='CHECKMARK')
                else:
                    btn_row.operator("bim.fed_rtree_overnight",
                                     text="OVERNIGHT", icon='TIME')
            else:
                _this_busy = (is_baking or bv._active_building in bv._bake_done)
                btn_row.operator("bim.fed_rtree_overnight",
                                 text="OVERNIGHT", icon='TIME')
                be_btn = btn_row.operator("bim.fed_rtree_switch_offline",
                                          text="\u26a1 BACKEND", icon='NONE')
                btn_row.enabled = not _this_busy if _this_busy else True
            # Cancel bake (only when baking)
            if is_baking:
                c_row = act_box.row(align=True)
                op_cb = c_row.operator("bim.fed_rtree_cancel_bake",
                                       text="CANCEL BAKE", icon='X')
                op_cb.building = bv._active_building

        # ── S188: BAKE ALL — parallel bake for multi-building DBs ──
        if (len(bv._search_results) > 1
                and not bv._overnight_running
                and not bv._bake_queue
                and not any(True for _ in bv._baking_buildings)):
            layout.separator(factor=0.3)
            ba_row = layout.row(align=True)
            ba_row.scale_y = 1.3
            ba_row.operator("bim.fed_rtree_bake_all",
                            text=f"BAKE ALL ({len(bv._search_results)} buildings)",
                            icon='RENDER_ANIMATION')
        elif bv._bake_queue or len(bv._baking_buildings) > 1:
            # Show queue status during parallel bake
            layout.separator(factor=0.3)
            ba_box = layout.box()
            ba_box.alert = True
            running = len(bv._baking_buildings)
            queued = len(bv._bake_queue)
            ba_box.label(text=f"Baking {running}/{bv._MAX_BAKE_WORKERS}, queued {queued}",
                         icon='RENDER_ANIMATION')

        # S191: backend/bake status moved to GPU HUD

        # ── PICK ──
        layout.separator(factor=0.3)
        layout.operator("bim.fed_rtree_pick", text="Click to Identify", icon='EYEDROPPER')
        if props.rtree_picked_name:
            pb = layout.box()
            ifc_cls = props.rtree_picked_class or ''
            disc    = props.rtree_picked_disc or ''
            label = '  \u00b7  '.join(p for p in [ifc_cls, disc, props.rtree_picked_name[:24]] if p)
            pb.label(text=label, icon='RADIOBUT_ON')
            guid = props.rtree_picked_guid
            if guid:
                gr = pb.row(align=True)
                gr.label(text=guid[:28], icon='COPY_ID')
                op_cp2 = gr.operator("bim.fed_rtree_copy_guid", text="", icon='COPYDOWN')
                op_cp2.guid = guid
        layout.label(text="Eye icon on \u25cf DISC = hide/show")

        # ── S195: Direct Stream controls (bottom of panel) ──
        layout.separator(factor=0.8)
        _ds_box = layout.box()
        _ds_row = _ds_box.row(align=True)
        _ds_row.scale_y = 1.4
        _ds_row.alert = bv._direct_stream_enabled  # red bar when streaming
        _ds_icon = 'PAUSE' if bv._direct_stream_enabled else 'PLAY'
        _ds_row.operator("bim.fed_rtree_direct_stream",
                         text="Stream", icon=_ds_icon)
        _ds_row.operator("bim.fed_rtree_shred",
                         text="Shred", icon='TRASH')
        _auto_text = "Auto ON" if bv._direct_stream_auto_shred else "Auto"
        _auto_icon = 'CHECKBOX_HLT' if bv._direct_stream_auto_shred else 'LOOP_BACK'
        _ds_row.operator("bim.fed_rtree_auto_shred_toggle",
                         text=_auto_text, icon=_auto_icon,
                         depress=bv._direct_stream_auto_shred)

    def _draw_discipline_bars(self, bx, props, bv):
        """S191: simplified — disc filter buttons only. Progress moved to GPU HUD."""
        disc_counts = bv._building_disc_counts
        if not disc_counts:
            return

        # Compact discipline filter buttons (2 per row)
        _disc_icons = {
            'ARC': 'HOME', 'STR': 'MOD_LATTICE', 'MEP': 'CURVES',
            'ELEC': 'LIGHT', 'FP': 'MESH_CIRCLE', 'ACMV': 'FORCE_WIND',
            'PLB': 'MOD_FLUIDSIM', 'HVAC': 'FORCE_WIND',
        }
        _discs = [d for d, c in disc_counts.items() if c > 0]
        for i in range(0, len(_discs), 2):
            row_d = bx.row(align=True)
            row_d.scale_y = 0.8
            for d in _discs[i:i+2]:
                op_d = row_d.operator("bim.fed_rtree_filter_disc",
                                      text=f"{d} ({disc_counts[d]:,})",
                                      icon=_disc_icons.get(d, 'DOT'),
                                      emboss=False)
                op_d.disc = d
