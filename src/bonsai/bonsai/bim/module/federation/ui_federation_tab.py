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
Qualified Path: src/bonsai/bonsai/bim/module/federation/ui_federation_tab.py

Federation Management UI - Clean POC Sandbox
--------------------------------------------

Organized under Project Overview for enterprise BIM coordination.
All federation features in one clean, logical hierarchy without clutter.

Layout:
1. Federation Setup (IFC sources, database creation)
2. Visualization Control (preview, load, CRUD)
3. MEP Coordination
4. Clash Detection (with resolution management)
5. Structural Works (rebar, concrete)
6. 4D Scheduling
7. 5D Cost Management
8. 6D/7D Digital Twin
9. Natural Language Query
10. Visualization Settings
"""

import bpy
import os
from bpy.types import Panel

# Import from existing modules (reuse logic, just reorganize UI)
import bonsai.tool as tool


# =============================================================================
# FEDERATION PANELS - Under Project Overview
# =============================================================================

# Note: All panels now parent to BIM_PT_tab_project_info for clean organization


# =============================================================================
# 1. FEDERATION SETUP
# =============================================================================

class BIM_PT_federation_setup(Panel):
    """Federation Setup - IFC sources and database creation"""
    bl_label = "1. Federation Setup"
    bl_idname = "BIM_PT_federation_setup"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tab_project_info"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 1

    @classmethod
    def poll(cls, context):
        return tool.Blender.is_tab(context, "PROJECT")

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

        # Database path
        row = layout.row()
        row.prop(props, "federation_database_path", text="")

        # Load/Unload buttons
        row = layout.row(align=True)
        if not props.index_loaded:
            row.scale_y = 1.5
            row.operator("bim.load_federation_index", icon="IMPORT", text="Load Federation")
        else:
            row.operator("bim.reload_federation_viewport", icon="FILE_REFRESH", text="Reload")
            row.operator("bim.unload_federation_index", icon="X", text="Unload")

        layout.separator()

        # Federated files section
        if props.index_loaded:
            box = layout.box()
            box.label(text="IFC Source Files", icon="OUTLINER_OB_POINTCLOUD")

            row = box.row(align=True)
            row.operator("bim.add_federated_file", icon="ADD", text="Add File")
            row.operator("bim.select_federated_folder", icon="FILEBROWSER", text="Scan Folder")

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


class BIM_PT_federation_new_additions(Panel):
    """Add/Edit custom elements in federation - THE KILLER FEATURE"""
    bl_label = "Additions ⭐"
    bl_idname = "BIM_PT_federation_new_additions"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tab_federation_new"
    # NO default_closed - this is the killer feature, always visible!
    bl_order = 2

    def draw(self, context):
        layout = self.layout
        props = context.scene.BIMFederationProperties
        obj = context.active_object

        # Killer feature callout
        box = layout.box()
        box.label(text="Editable Federation Database", icon="EDITMODE_HLT")
        col = box.column(align=True)
        col.scale_y = 0.8
        col.label(text="Add site equipment, coordination geometry,")
        col.label(text="or temporary structures to federated model.")
        col.label(text="Elements persist and participate in clashes.")

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

                # Add button (prominent!)
                row = status_box.row()
                row.scale_y = 1.8
                row.operator("bim.add_to_federation", icon="ADD", text="Add to Federation")
        else:
            info_box = layout.box()
            info_box.label(text="No object selected", icon="INFO")
            info_box.label(text="Create object (Shift+A) then select it")

        layout.separator()

        # Query additions
        query_box = layout.box()
        query_box.label(text="View All Additions", icon="VIEWZOOM")
        row = query_box.row()
        row.scale_y = 1.2
        row.operator("bim.query_federation_additions", icon="DOCUMENTS")

        # Quick start guide (collapsible)
        layout.separator()
        help_box = layout.box()
        help_box.label(text="Quick Start:", icon="QUESTION")
        col = help_box.column(align=True)
        col.scale_y = 0.7
        col.label(text="1. Create object in Blender (Shift+A)")
        col.label(text="2. Position it using GPS coordinates")
        col.label(text="3. Select object, click 'Add to Federation'")
        col.label(text="4. Choose IFC class and discipline")
        col.label(text="5. Object persists across sessions!")


class BIM_PT_federation_new_clash(Panel):
    """Clash detection across all disciplines"""
    bl_label = "Clash Detection"
    bl_idname = "BIM_PT_federation_new_clash"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tab_federation_new"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 3

    def draw(self, context):
        layout = self.layout
        props = tool.Clash.get_clash_props()

        # Quick clash by discipline
        box = layout.box()
        box.label(text="Quick Clash by Discipline", icon="COMMUNITY")

        row = box.row()
        row.prop(props, "clash_preset", text="")

        row = box.row(align=True)
        row.scale_y = 1.3
        row.operator("bim.clash_by_discipline", icon="CHECKMARK", text="Detect Clashes")

        # Clash results summary
        if props.discipline_clashes:
            layout.separator()
            results_box = layout.box()
            results_box.label(text=f"Found {len(props.discipline_clashes)} clash pairs", icon="ERROR")

            results_box.template_list(
                "BIM_UL_discipline_clashes",
                "",
                props,
                "discipline_clashes",
                props,
                "active_discipline_clash_index",
                rows=4,
            )

            # Visualization controls
            row = results_box.row(align=True)
            row.operator("bim.visualize_selected_discipline_clashes", icon="HIDE_OFF")
            row.operator("bim.clear_discipline_clash_visualization", icon="X")

        # BCF export
        layout.separator()
        row = layout.row()
        row.scale_y = 1.2
        row.operator("bim.export_bcf", icon="EXPORT", text="Export BCF Report")


class BIM_PT_federation_new_mep(Panel):
    """MEP routing and sizing (requires MEP disciplines)"""
    bl_label = "MEP Engineering"
    bl_idname = "BIM_PT_federation_new_mep"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tab_federation_new"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 4

    @classmethod
    def poll(cls, context):
        # Only show if MEP disciplines are loaded
        props = context.scene.BIMFederationProperties
        if not props.loaded_disciplines:
            return False
        disciplines = props.loaded_disciplines.split(', ')
        return any(d in ['ACMV', 'PLB', 'ELEC'] for d in disciplines)

    def draw(self, context):
        layout = self.layout

        # MEP routing section
        box = layout.box()
        box.label(text="MEP Routing", icon="CURVE_PATH")
        col = box.column(align=True)
        col.scale_y = 0.8
        col.label(text="Route pipes, ducts, and cables using")
        col.label(text="federation database for obstacles.")

        # Placeholder - link to MEP module
        row = box.row()
        row.scale_y = 1.3
        row.operator("bim.load_federation_viewport", icon="IMPORT", text="Load MEP Workspace")

        layout.separator()
        info_box = layout.box()
        info_box.label(text="MEP tools available when MEP", icon="INFO")
        info_box.label(text="disciplines (ACMV, PLB, ELEC) are loaded")


class BIM_PT_federation_new_4d5d(Panel):
    """4D scheduling and 5D cost management"""
    bl_label = "4D/5D BIM"
    bl_idname = "BIM_PT_federation_new_4d5d"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tab_federation_new"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 5

    def draw(self, context):
        layout = self.layout

        # Schedule export
        box = layout.box()
        box.label(text="4D Construction Schedule", icon="TIME")

        row = box.row(align=True)
        row.operator("bim.generate_construction_schedule", icon="PRESET", text="Generate")
        row.operator("bim.export_mpp_schedule", icon="EXPORT", text="Export .mpp")

        # BOQ export
        layout.separator()
        box = layout.box()
        box.label(text="5D Bill of Quantities", icon="SPREADSHEET")

        row = box.row(align=True)
        row.scale_y = 1.3
        row.operator("bim.export_comprehensive_boq", icon="EXPORT", text="Export BOQ")
        row.operator("bim.open_boq_report", icon="FILE_FOLDER", text="Open")


class BIM_PT_federation_new_nlp(Panel):
    """Natural language query interface"""
    bl_label = "AI Query"
    bl_idname = "BIM_PT_federation_new_nlp"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tab_federation_new"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 6

    def draw(self, context):
        layout = self.layout
        props = context.scene.BIMFederationProperties

        # Query input
        box = layout.box()
        box.label(text="Ask Questions in Natural Language", icon="LIGHT")

        row = box.row()
        row.prop(props, "nlp_query_text", text="", icon="CONSOLE")

        row = box.row()
        row.scale_y = 1.5
        row.operator("bim.execute_nlp_query", icon="PLAY", text="Ask")

        # Suggested queries
        layout.separator()
        suggest_box = layout.box()
        suggest_box.label(text="Examples:", icon="QUESTION")
        col = suggest_box.column(align=True)
        col.scale_y = 0.9

        for query in ["How many beams?", "Total concrete volume?", "Find ACMV equipment"]:
            op = col.operator("bim.set_nlp_query", text=query, icon="RIGHTARROW_THIN")
            op.query_text = query

        # Results
        if hasattr(props, "nlp_results_count") and props.nlp_results_count > 0:
            layout.separator()
            results_box = layout.box()
            results_box.label(text=f"Results: {props.nlp_results_count} rows", icon="DOCUMENTS")
            row = results_box.row()
            row.operator("bim.export_nlp_results", text="Export CSV", icon="EXPORT")


class BIM_PT_federation_new_digital_twin(Panel):
    """Asset management and IoT integration (6D/7D)"""
    bl_label = "Digital Twin"
    bl_idname = "BIM_PT_federation_new_digital_twin"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tab_federation_new"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 7

    def draw(self, context):
        layout = self.layout

        # Asset management
        box = layout.box()
        box.label(text="Asset Management (6D)", icon="ASSET_MANAGER")

        row = box.row(align=True)
        row.operator("bim.import_assets_from_federation", icon="IMPORT", text="Import Assets")
        row.operator("bim.refresh_asset_list", icon="FILE_REFRESH", text="Refresh")

        # IoT Command Center
        layout.separator()
        box = layout.box()
        box.label(text="IoT Command Center (7D)", icon="VIEWZOOM")

        row = box.row()
        row.scale_y = 1.3
        row.operator("bim.iot_enable_sensor_overlay", icon="OUTLINER_OB_LIGHT", text="Enable Sensors")

        # Quick stats
        layout.separator()
        info_box = layout.box()
        info_box.label(text="Digital Twin integrates:", icon="INFO")
        col = info_box.column(align=True)
        col.scale_y = 0.8
        col.label(text="• Asset lifecycle tracking")
        col.label(text="• Maintenance schedules")
        col.label(text="• IoT sensor monitoring")


# =============================================================================
# Registration
# =============================================================================

classes = (
    BIM_PT_tab_federation_new,
    BIM_PT_federation_new_management,
    BIM_PT_federation_new_additions,
    BIM_PT_federation_new_clash,
    BIM_PT_federation_new_mep,
    BIM_PT_federation_new_4d5d,
    BIM_PT_federation_new_nlp,
    BIM_PT_federation_new_digital_twin,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    print("✓ New Federation tab registered (experimental sandbox)")


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
