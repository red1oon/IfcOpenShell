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
        pass  # Children panels provide content


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
        pass  # Children panels provide content


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
        pass  # Children panels provide content


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