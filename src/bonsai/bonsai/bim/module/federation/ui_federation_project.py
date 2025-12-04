# Bonsai - OpenBIM Blender Add-on
# Copyright (C) 2025 Dion Moult, Yassine Oualid <dion@thinkmoult.com>
#
# This file is part of Bonsai.
#
# Bonsai is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
Federation Management UI - Clean Enterprise Layout
==================================================
Organized under Project Overview for clean POC sandbox.
"""

import bpy
import os
from bpy.types import Panel
import bonsai.tool as tool


# =============================================================================
# 1. FEDERATION SETUP
# =============================================================================

class BIM_PT_federation_setup(Panel):
    """Federation Setup - Model sources and database"""
    bl_label = "1. Federation Setup"
    bl_idname = "BIM_PT_federation_setup"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tabs"
    bl_order = 1

    # No poll needed - always show in Project Overview

    def draw(self, context):
        layout = self.layout
        props = context.scene.BIMFederationProperties

        # Model Sources section
        box = layout.box()
        box.label(text="Model Sources", icon="FILE_3D")

        row = box.row(align=True)
        row.operator("bim.add_federated_file", icon="ADD", text="Add IFC Files")
        row.operator("bim.select_federated_folder", icon="FILE_FOLDER", text="Scan Folder")

        if props.federated_files:
            box.template_list(
                "BIM_UL_federated_files",
                "",
                props,
                "federated_files",
                props,
                "active_federated_file_index",
                rows=3,
            )

        # Database Creation section
        layout.separator()
        box = layout.box()
        box.label(text="Database Creation", icon="FILE_FOLDER")

        row = box.row(align=True)
        row.scale_y = 1.3
        row.operator("bim.extract_full_database", icon="TIME", text="Extract Full")
        row.operator("bim.extract_sample_database", icon="QUESTION", text="Extract Sample")


# =============================================================================
# 2. VISUALIZATION CONTROL
# =============================================================================

class BIM_PT_visualization_control(Panel):
    """Visualization Control - Database and display modes"""
    bl_label = "2. Visualization Control"
    bl_idname = "BIM_PT_visualization_control"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tabs"
    bl_order = 2

    # No poll needed - always show in Project Overview

    def draw(self, context):
        layout = self.layout
        props = context.scene.BIMFederationProperties

        # Database Path
        box = layout.box()
        box.label(text="Database Path", icon="FILE")
        box.prop(props, "federation_database_path", text="")

        # Display Modes
        layout.separator()
        box = layout.box()
        box.label(text="Display Modes", icon="HIDE_OFF")

        row = box.row(align=True)
        row.scale_y = 1.3
        row.operator("bim.preview_federation_viewport", icon="MESH_CUBE", text="Preview BBoxes")
        row.operator("bim.unload_federation_viewport", icon="X", text="Clear")

        row = box.row()
        row.scale_y = 1.3
        row.operator("bim.load_full_federation_viewport_gi", icon="MESH_DATA", text="Full Load")

        # Model Management (CRUD)
        layout.separator()
        box = layout.box()
        box.label(text="Model Management", icon="OBJECT_DATA")

        obj = context.active_object
        if obj and 'ifc_guid' in obj:
            col = box.column(align=True)
            col.label(text=f"Selected: {obj.name}", icon="OBJECT_DATA")
            row = col.row(align=True)
            row.operator("bim.update_federation_element", icon="FILE_REFRESH", text="Update")
            row.operator("bim.remove_from_federation", icon="CANCEL", text="Remove")
        else:
            row = box.row()
            row.scale_y = 1.5
            row.operator("bim.add_to_federation", icon="ADD", text="Add Element (CRUD) ⭐")


# =============================================================================
# 3. MEP COORDINATION
# =============================================================================

class BIM_PT_mep_coordination(Panel):
    """MEP Coordination - Routing tools"""
    bl_label = "3. MEP Coordination"
    bl_idname = "BIM_PT_mep_coordination"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tabs"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 3

    # No poll needed - always show in Project Overview

    def draw(self, context):
        layout = self.layout

        # Safety check: MEP properties might not be registered
        if not hasattr(context.scene, 'BIMmepEngineeringProperties'):
            layout.label(text="MEP Engineering module not loaded")
            return

        props = context.scene.BIMmepEngineeringProperties
        fed_props = context.scene.BIMFederationProperties

        # ================================================================
        # ROUTING SECTION
        # ================================================================

        box = layout.box()
        box.label(text="Conduit Routing", icon='CURVE_PATH')

        # Start Point
        row = box.row(align=True)
        row.label(text="Start Point:")
        row.operator("bim.set_route_start_point", text="Set from Cursor", icon='CURSOR')

        row = box.row()
        row.prop(props, "route_start_point", text="")

        # End Point
        row = box.row(align=True)
        row.label(text="End Point:")
        row.operator("bim.set_route_end_point", text="Set from Cursor", icon='CURSOR')

        row = box.row()
        row.prop(props, "route_end_point", text="")

        # Settings
        box.separator()
        row = box.row()
        row.prop(props, "clearance_distance")

        row = box.row()
        row.prop(props, "conduit_diameter")

        row = box.row()
        row.prop(props, "target_disciplines")

        # Action buttons section
        box.separator()

        # Test Routing button (auto-pick from federation DB)
        row = box.row(align=True)
        row.enabled = fed_props.index_loaded
        row.operator("bim.auto_pick_routing_endpoints", text="Test Routing", icon='PLAY')

        # Route Conduit button
        row = box.row(align=True)
        row.scale_y = 1.5
        row.enabled = fed_props.index_loaded
        row.operator("bim.route_mep_conduit", text="Route Conduit", icon='ANIM')

        # Visualization buttons
        box.separator()
        row = box.row(align=True)
        row.enabled = fed_props.index_loaded
        row.operator("bim.visualize_routing_obstacles", text="View Conduit", icon='HIDE_OFF')
        row.operator("bim.clear_routing_debug", text="Clear Conduit", icon='X')

        # ================================================================
        # FUTURE ROUTING TOOLS (Placeholder for planned enhancements)
        # ================================================================
        layout.separator()

        box = layout.box()
        box.label(text="Duct Routing", icon='STICKY_UVS_LOC')
        row = box.row()
        row.enabled = False
        row.label(text="Coming soon: Automated duct routing")

        layout.separator()

        box = layout.box()
        box.label(text="MEP Roadmap & Planned Features", icon='LIGHT')
        col = box.column(align=True)
        col.label(text="Clash Report Generation (High Priority):", icon='ERROR')
        col.label(text="  • Multi-discipline clash reports (BCF/HTML/Excel)")
        col.label(text="  • Per-clash screenshots with annotations")
        col.label(text="  • Status tracking (New/Approved/Resolved)")
        col.label(text="  • Discipline assignment & due dates")
        col.label(text="  • Industry-standard BCF export/import")
        col.separator()
        col.label(text="Other Planned Features:")
        col.label(text="  • Duct sizing calculations")
        col.label(text="  • Pressure drop analysis")
        col.label(text="  • Equipment scheduling")
        col.label(text="  • Load calculations")


# =============================================================================
# 4. CLASH DETECTION
# =============================================================================

class BIM_PT_clash_detection(Panel):
    """Clash Detection with resolution management"""
    bl_label = "4. Clash Detection"
    bl_idname = "BIM_PT_clash_detection"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tabs"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 4

    # No poll needed - always show in Project Overview

    def draw(self, context):
        layout = self.layout
        props = tool.Clash.get_clash_props()

        # Quick Clash
        box = layout.box()
        box.label(text="Quick Clash by Discipline", icon="GROUP")

        # Tolerance setting
        row = box.row()
        row.prop(props, "discipline_tolerance", text="Tolerance")

        # Preset selection
        row = box.row()
        row.prop(props, "clash_preset", text="")

        # Detect button
        row = box.row()
        row.scale_y = 1.3
        row.operator("bim.clash_by_discipline", icon="ADD", text="Detect Clashes")

        # Clash Results List
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
            header.label(text="☐")
            header.label(text="Element A")
            header.label(text="Element B")
            header.label(text="Type")

            # Clash list
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
            row.operator("bim.clear_discipline_clash_visualization", text="Clear All", icon="PANEL_CLOSE")

        # Clash Visualization
        if props.discipline_clash_loaded and props.discipline_clash_candidates:
            layout.separator()
            box = layout.box()
            box.label(text="Visualization", icon="HIDE_OFF")
            row = box.row(align=True)
            row.operator("bim.enable_clash_gpu_visualization", text="GPU Overlay", icon="HIDE_OFF")
            row.operator("bim.enable_clash_gizmo_visualization", text="Gizmos", icon="OBJECT_DATA")
            row = box.row()
            row.operator("bim.clear_discipline_clash_visualization", text="Clear All", icon="X")

        # Group Resolution
        layout.separator()
        box = layout.box()
        box.label(text="Group Resolution Management", icon="GROUP")
        row = box.row()
        row.scale_y = 1.3
        row.operator("bim.analyze_clash_groups", text="Analyze Groups", icon="AUTO")

        # Group selector and preview
        clash_props = context.scene.BIMClashProperties
        if hasattr(clash_props, "clash_groups_analyzed") and clash_props.clash_groups_analyzed:
            row = box.row()
            row.prop(clash_props, "selected_clash_group", text="Group")

            row = box.row()
            row.scale_y = 1.3
            row.enabled = bool(clash_props.selected_clash_group and clash_props.selected_clash_group != "NONE")
            row.operator("bim.preview_clash_group", text="Preview Group", icon="HIDE_OFF")

        # BCF Export
        layout.separator()
        row = layout.row()
        row.scale_y = 1.2
        row.operator("bim.export_bcf", icon="FILE_TICK", text="Export BCF Report")


# =============================================================================
# 5. STRUCTURAL WORKS
# =============================================================================

class BIM_PT_structural_works(Panel):
    """Structural Works - Rebar and concrete"""
    bl_label = "5. Structural Works"
    bl_idname = "BIM_PT_structural_works"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tabs"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 5

    # No poll needed - always show in Project Overview

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        row.scale_y = 1.5
        row.operator("bim.generate_rebar_structural", text="Generate Rebar", icon="ADD")

        layout.separator()
        row = layout.row()
        row.operator("bim.export_structural_boq", text="Export Structural BOQ", icon="FILE")


# =============================================================================
# 6. 4D SCHEDULING
# =============================================================================

class BIM_PT_4d_scheduling(Panel):
    """4D Construction Scheduling"""
    bl_label = "6. 4D Scheduling"
    bl_idname = "BIM_PT_4d_scheduling"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tabs"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 6

    # No poll needed - always show in Project Overview

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        row.scale_y = 1.5
        row.operator("bim.generate_construction_schedule", text="Generate Schedule", icon="TIME")

        layout.separator()
        row = layout.row(align=True)
        row.operator("bim.export_mpp_schedule", text="Export XML", icon="FILE_TICK")
        row.operator("bim.export_schedule_excel", text="Export Excel", icon="FILE")

        layout.separator()
        row = layout.row()
        row.scale_y = 1.3
        row.operator("bim.animate_4d_construction", text="4D Animation", icon="TIME")


# =============================================================================
# 7. 5D COST MANAGEMENT
# =============================================================================

class BIM_PT_5d_cost_management(Panel):
    """5D Cost Management - BOQ"""
    bl_label = "7. 5D Cost Management"
    bl_idname = "BIM_PT_5d_cost_management"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tabs"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 7

    # No poll needed - always show in Project Overview

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        row.scale_y = 1.5
        row.operator("bim.export_comprehensive_boq", text="Generate BOQ", icon="FILE")

        row = layout.row()
        row.operator("bim.open_boq_report", text="Export Cost Reports", icon="FILE_TICK")


# =============================================================================
# 8. 6D/7D DIGITAL TWIN
# =============================================================================

class BIM_PT_digital_twin(Panel):
    """6D/7D Digital Twin - Asset management and IoT"""
    bl_label = "8. 6D/7D Digital Twin"
    bl_idname = "BIM_PT_digital_twin"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tabs"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 8

    # No poll needed - always show in Project Overview

    def draw(self, context):
        layout = self.layout
        props = context.scene.BIMTandemProperties
        fed_props = context.scene.BIMFederationProperties

        # Database status (read-only, shows Federation DB)
        box = layout.box()
        if fed_props.federation_database_path:
            box.label(text="Using Federation Database:", icon='FILE')
            row = box.row()
            row.scale_y = 0.7
            row.label(text=f"{fed_props.federation_database_path.split('/')[-1]}")
        else:
            box.label(text="⚠ No Federation Database Loaded", icon='ERROR')
            row = box.row()
            row.scale_y = 0.7
            row.label(text="Load database in Federation panel first")
            return

        # Quick actions
        box = layout.box()
        box.label(text="Asset Management:", icon='PROPERTIES')

        row = box.row(align=True)
        row.operator("bim.import_assets_from_ifc", text="Import from IFC", icon='IMPORT')
        row.operator("bim.refresh_asset_list", text="Refresh", icon='FILE_REFRESH')

        row = box.row()
        row.operator("bim.export_asset_report", text="Export Report", icon='EXPORT')

        # Visualization
        box = layout.box()
        box.label(text="Visualization:", icon='SHADING_RENDERED')
        box.operator("bim.visualize_assets_by_condition", text="Color by Condition", icon='SHADING_SOLID')


# =============================================================================
# 9. NATURAL LANGUAGE QUERY
# =============================================================================

class BIM_PT_nlp_query(Panel):
    """Natural Language Query"""
    bl_label = "9. Natural Language Query"
    bl_idname = "BIM_PT_nlp_query"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tabs"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 9

    # No poll needed - always show in Project Overview

    def draw(self, context):
        layout = self.layout
        props = context.scene.BIMFederationProperties

        # Query input box
        box = layout.box()
        box.label(text="Enter Query:", icon="VIEWZOOM")
        row = box.row()
        row.prop(props, "nlp_query_text", text="")

        # Execute buttons
        row = box.row(align=True)
        row.scale_y = 1.3
        row.operator("bim.execute_nlp_query", text="Search", icon="PLAY")
        row.operator("bim.clear_nlp_results", text="Clear", icon="X")

        # Suggested queries
        layout.separator()
        suggest_box = layout.box()
        suggest_box.label(text="Common Queries:", icon="LIGHT")

        # Create two columns
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

        # Results display (if available)
        if hasattr(props, "nlp_results_count") and props.nlp_results_count > 0:
            layout.separator()
            results_box = layout.box()
            results_box.label(text=f"Results ({props.nlp_results_count} rows):", icon="INFO")

            if hasattr(props, "nlp_results_text"):
                results_col = results_box.column(align=True)
                results_col.scale_y = 0.7

                # Display first 15 lines of results
                lines = props.nlp_results_text.split('\n')[:15]
                for line in lines:
                    results_col.label(text=line)

                if len(props.nlp_results_text.split('\n')) > 15:
                    results_col.label(text="... (view full results in exported CSV)")

            # Export button
            row = results_box.row()
            row.scale_y = 1.2
            row.operator("bim.export_nlp_results", text="Export to CSV", icon="FILE_TICK")


# =============================================================================
# 10. VISUALIZATION SETTINGS
# =============================================================================

class BIM_PT_visualization_settings(Panel):
    """Visualization Settings - Colors and materials"""
    bl_label = "10. Visualization Settings"
    bl_idname = "BIM_PT_visualization_settings"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tabs"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 10

    # No poll needed - always show in Project Overview

    def draw(self, context):
        layout = self.layout
        props = context.scene.BIMFederationColorProperties

        # Import CONSTRUCTION_PALETTES from color_palette module
        from .color_palette import CONSTRUCTION_PALETTES

        # Palette selector
        box = layout.box()
        row = box.row()
        row.label(text="Theme:", icon='COLOR')
        row.prop(props, "active_palette", text="")

        # Color grid
        palette = CONSTRUCTION_PALETTES.get(props.active_palette, {})
        colors = palette.get("colors", [])

        grid_box = layout.box()
        grid_box.label(text="Quick Colors:", icon='BRUSHES_ALL')

        # Create color swatches (4 columns)
        col_count = 4
        for i in range(0, len(colors), col_count):
            row = grid_box.row(align=True)
            for j in range(col_count):
                if i + j < len(colors):
                    name, color = colors[i + j]
                    op = row.operator("bim.apply_palette_color", text="", icon='BLANK1')
                    op.color = color
                    # Show color as background (hacky but works)
                    col = row.column()
                    col.scale_x = 0.3
                    col.label(text=name[:8])

        # Custom color picker
        layout.separator()
        color_box = layout.box()
        color_box.label(text="Custom Color:", icon='EYEDROPPER')
        color_box.prop(props, "selected_color", text="")

        row = color_box.row(align=True)
        op = row.operator("bim.apply_palette_color", text="Apply Custom", icon='CHECKMARK')
        op.color = props.selected_color

        # Filters
        layout.separator()
        filter_box = layout.box()
        filter_box.label(text="Filters:", icon='FILTER')

        row = filter_box.row()
        row.prop(props, "filter_discipline", text="")

        row = filter_box.row()
        row.prop(props, "filter_ifc_type", text="", icon='OBJECT_DATA')

        # Quick access buttons
        row = filter_box.row(align=True)
        row.operator("bim.get_type_from_selection", text="Get from Selected", icon='EYEDROPPER')
        row.operator("bim.refresh_ifc_types", text="Refresh", icon='FILE_REFRESH')

        # Options
        row = filter_box.row()
        row.prop(props, "auto_apply", text="Auto Apply")
        row.prop(props, "show_preview", text="Preview")

        # Actions
        layout.separator()
        action_box = layout.box()
        action_box.label(text="Actions:", icon='TOOL_SETTINGS')

        row = action_box.row(align=True)
        op = row.operator("bim.apply_color_to_selected", text="Apply to Selected", icon='RESTRICT_SELECT_OFF')
        op.color = props.selected_color

        row = action_box.row(align=True)
        row.operator("bim.reset_federation_colors", text="Reset All", icon='FILE_REFRESH')

        # Utilities
        row = action_box.row(align=True)
        row.operator("bim.strip_materials_from_type", text="Strip Materials", icon='MATERIAL')

        row = action_box.row(align=True)
        row.operator("bim.save_color_scheme", text="Save Scheme", icon='FILE_TICK')
        row.operator("bim.load_color_scheme", text="Load Scheme", icon='FILE_FOLDER')

        # Info
        info_box = layout.box()
        info_box.scale_y = 0.8
        info_text = info_box.column()
        info_text.label(text="💡 Tips:", icon='INFO')
        info_text.label(text="  • Use Solid shading mode")
        info_text.label(text="  • Alt+Z for X-ray view")
        info_text.label(text="  • Filter by discipline/type")


# =============================================================================
# Registration
# =============================================================================

classes = (
    BIM_PT_federation_setup,
    BIM_PT_visualization_control,
    BIM_PT_mep_coordination,
    BIM_PT_clash_detection,
    BIM_PT_structural_works,
    BIM_PT_4d_scheduling,
    BIM_PT_5d_cost_management,
    BIM_PT_digital_twin,
    BIM_PT_nlp_query,
    BIM_PT_visualization_settings,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    print("✓ Federation Project Overview UI registered")


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)