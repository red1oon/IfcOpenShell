# Bonsai - OpenBIM Blender Add-on
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
            # TODO: Add property to track number of groups found
            # For now, show placeholder
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
            info_col.label(text="💡 Generates ranked options with:")
            info_col.label(text="  • Design effort estimates (hours)")
            info_col.label(text="  • Cost breakdown by discipline")
            info_col.label(text="  • Risk assessment")

            # Suggest resolutions button
            row = resolution_box.row()
            row.scale_y = 1.5
            row.operator("bim.suggest_resolutions",
                         text="Suggest Resolutions for All Groups",
                         icon="EXPERIMENTAL")

            # Show resolution results if available
            if hasattr(props, 'resolutions_generated') and props.resolutions_generated:
                result_box = layout.box()
                result_box.label(text="Resolution Options Available:", icon="CHECKMARK")
                result_box.label(text="  (Check Blender console for ranked options)")

                # Add button to view/select resolution options
                row = result_box.row()
                row.operator("bim.select_resolution_option",
                             text="View Resolution Options",
                             icon="PRESET")


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
