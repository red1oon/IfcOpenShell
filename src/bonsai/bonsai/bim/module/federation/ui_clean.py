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
Clean Federation Tab UI
-----------------------
Simplified federation UI that provides a dedicated tab under BIM_PT_tabs
with organized child panels for all federation features.
"""

from __future__ import annotations
import bpy
import bonsai.tool as tool
from bpy.types import Panel

# =============================================================================
# MAIN FEDERATION TAB (Parent under BIM_PT_tabs)
# =============================================================================

class BIM_PT_tab_federation_clean(Panel):
    """Main Federation tab - appears as a section in Scene Properties"""
    bl_label = "Federation"
    bl_idname = "BIM_PT_tab_federation_clean"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tabs"  # CRITICAL: Must be under Bonsai tabs
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 1

    @classmethod
    def poll(cls, context):
        """Ensure parent BIM_PT_tabs exists"""
        return hasattr(bpy.types, "BIM_PT_tabs") and context.scene is not None

    def draw(self, context):
        # Main panel - shows federation info
        layout = self.layout
        props = context.scene.BIMFederationProperties

        # Show basic info if federation is loaded
        if props.index_loaded:
            box = layout.box()
            box.label(text=f"Elements: {props.total_elements:,}", icon="DOCUMENTS")
            if props.loaded_disciplines:
                box.label(text=f"Disciplines: {props.loaded_disciplines}")
        else:
            layout.label(text="No federation loaded", icon="INFO")


# =============================================================================
# FEDERATION CHILD PANELS
# =============================================================================

class BIM_PT_federation_models(Panel):
    """Manage federated model sources"""
    bl_label = "Model Sources"
    bl_idname = "BIM_PT_federation_models"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_options = {"DEFAULT_CLOSED"}
    bl_parent_id = "BIM_PT_tab_federation_clean"

    @classmethod
    def poll(cls, context):
        return hasattr(bpy.types, "BIM_PT_tab_federation_clean") and context.scene is not None

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        props = context.scene.BIMFederationProperties

        # File list controls
        row = layout.row(align=True)
        row.operator("bim.add_federated_file", icon="ADD")
        row.operator("bim.select_federated_folder", icon="FILE_FOLDER")

        # Display file list
        if props.federated_files:
            layout.template_list(
                "BIM_UL_federated_files",
                "",
                props,
                "federated_files",
                props,
                "active_federated_file_index",
            )

        # Preprocess button
        layout.separator()
        row = layout.row()
        row.scale_y = 1.5
        row.operator("bim.preprocess_federated_models", icon="IMPORT")


class BIM_PT_federation_clash(Panel):
    """Clash detection and coordination"""
    bl_label = "Clash Detection"
    bl_idname = "BIM_PT_federation_clash"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_options = {"DEFAULT_CLOSED"}
    bl_parent_id = "BIM_PT_tab_federation_clean"

    @classmethod
    def poll(cls, context):
        return hasattr(bpy.types, "BIM_PT_tab_federation_clean") and context.scene is not None

    def draw(self, context):
        layout = self.layout
        props = context.scene.BIMFederationProperties

        if not props.index_loaded:
            box = layout.box()
            box.label(text="Federation index not loaded", icon="INFO")
            box.label(text="Preprocess models first")
            return

        # Clash detection controls
        layout.operator("bim.detect_federation_clashes", icon="HANDLETYPE_VECTOR_VEC")

        # Display clash results
        clash_props = context.scene.BIMClashProperties if hasattr(context.scene, 'BIMClashProperties') else None
        if clash_props and clash_props.discipline_clash_loaded and clash_props.discipline_clash_candidates:
            layout.separator()
            layout.label(text=f"Found {len(clash_props.discipline_clash_candidates)} clash groups")
            layout.template_list(
                "BIM_UL_discipline_clashes",
                "",
                clash_props,
                "discipline_clash_candidates",
                clash_props,
                "active_discipline_clash_index",
            )


class BIM_PT_federation_spatial(Panel):
    """Spatial queries and analysis"""
    bl_label = "Spatial Analysis"
    bl_idname = "BIM_PT_federation_spatial"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_options = {"DEFAULT_CLOSED"}
    bl_parent_id = "BIM_PT_tab_federation_clean"

    @classmethod
    def poll(cls, context):
        return hasattr(bpy.types, "BIM_PT_tab_federation_clean") and context.scene is not None

    def draw(self, context):
        layout = self.layout
        props = context.scene.BIMFederationProperties

        if not props.index_loaded:
            box = layout.box()
            box.label(text="Federation index not loaded", icon="INFO")
            return

        # Spatial query interface
        layout.label(text="Query federated elements:")
        layout.operator("bim.query_federation_index", text="Run Query")

        # Display stats
        if props.total_elements > 0:
            box = layout.box()
            box.label(text=f"Total Elements: {props.total_elements:,}")
            if props.loaded_disciplines:
                box.label(text=f"Disciplines: {props.loaded_disciplines}")


class BIM_PT_federation_lod(Panel):
    """LOD visualization controls"""
    bl_label = "Visualization (LOD)"
    bl_idname = "BIM_PT_federation_lod"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_options = {"DEFAULT_CLOSED"}
    bl_parent_id = "BIM_PT_tab_federation_clean"

    @classmethod
    def poll(cls, context):
        return hasattr(bpy.types, "BIM_PT_tab_federation_clean") and context.scene is not None

    def draw(self, context):
        layout = self.layout
        props = context.scene.BIMFederationProperties

        if not props.index_loaded:
            box = layout.box()
            box.label(text="Federation index not loaded", icon="INFO")
            return

        # LOD controls
        layout.label(text="Level of Detail:")

        row = layout.row(align=True)
        row.operator("bim.preview_federation_viewport", text="Preview (Wireframe)")

        row = layout.row(align=True)
        row.operator("bim.load_solid_federation_viewport", text="Solid (Bboxes)")

        row = layout.row(align=True)
        row.operator("bim.load_full_federation_viewport", text="Full Geometry")

        layout.separator()
        layout.operator("bim.unload_federation_viewport", text="Unload", icon="X")
