# ============================================================================
# FILE: ui.py
# PURPOSE: Define UI panels that appear in Blender interface
# ============================================================================

import bpy
import os
import bonsai.tool as tool
from bpy.types import Panel

class BIM_PT_mep_engineering(Panel):
    """MEP Engineering panel in Blender UI"""
    bl_label = "Conduit Testing"
    bl_idname = "BIM_PT_mep_engineering"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tab_mep_engineering"
    
    def draw(self, context):
        """Draw the panel UI"""
        layout = self.layout
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
        
        # Route Button
        box.separator()
        row = box.row()
        row.scale_y = 1.5
        row.enabled = fed_props.index_loaded
        row.operator("bim.route_mep_conduit", text="Route Conduit", icon='ANIM')

        # Visualization buttons (embedded here, no separate section)
        box.separator()
        row = box.row(align=True)
        row.enabled = fed_props.index_loaded
        row.operator("bim.visualize_routing_obstacles", text="Visualize Conduit", icon='HIDE_OFF')
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