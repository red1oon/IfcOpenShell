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
    bl_label = "Multi-Model Federation"
    bl_idname = "BIM_PT_federation"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_options = {"DEFAULT_CLOSED"}
    # Nest under Quality Control tab
    bl_parent_id = "BIM_PT_tab_quality_control"
    
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
        
        # Database path
        box = layout.box()
        box.label(text="Federation Database", icon="FILE")
        box.prop(props, "federation_database_path", text="")
        
        # Progress indicator
        if props.preprocessing_in_progress:
            box.label(text="Preprocessing in progress...", icon="TIME")
            if props.progress_json_path:
                from pathlib import Path
                box.label(text=f"Progress: {Path(props.progress_json_path).name}")
        
        layout.separator()
        
        # Main actions
        col = layout.column(align=True)
        
        # Preprocess button
        row = col.row()
        row.scale_y = 1.3
        row.enabled = not props.preprocessing_in_progress
        row.operator("bim.preprocess_federated_models", icon="PLAY")
        
        # Load/Unload buttons
        row = col.row(align=True)
        if props.index_loaded:
            row.operator("bim.unload_federation_index", icon="PANEL_CLOSE")
            row.operator("bim.query_federation_index", text="Test Query", icon="VIEWZOOM")
        else:
            row.operator("bim.load_federation_index", icon="IMPORT")
        
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
        
        # Tips section
        layout.separator()
        box = layout.box()
        box.label(text="Usage:", icon="INFO")
        col = box.column(align=True)
        col.scale_y = 0.8
        col.label(text="1. Add all discipline IFC files")
        col.label(text="2. Set output database path")
        col.label(text="3. Run preprocessing (may take 10-20 min)")
        col.label(text="4. Load index for spatial queries")
        col.label(text="5. Use in MEP routing or clash detection")