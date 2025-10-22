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

from __future__ import annotations
import bpy
import bonsai.tool as tool
import bonsai.bim.helper
from bpy.types import Panel
from bonsai.bim.module.clash.data import ClashData
from typing import TYPE_CHECKING, assert_never

if TYPE_CHECKING:
    from bonsai.bim.module.clash.prop import BIMClashProperties, ClashSet, SmartClashGroup, Clash


class BIM_PT_ifcclash(Panel):
    bl_label = "Clash Sets"
    bl_idname = "BIM_PT_ifcclash"
    bl_options = {"DEFAULT_CLOSED"}
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tab_clash_detection"

    def draw(self, context):
        if not ClashData.is_loaded:
            ClashData.load()

        assert self.layout
        layout = self.layout
        props = tool.Clash.get_clash_props()

        # Discipline-based clash detection (simplified workflow)
        box = layout.box()
        box.label(text="Quick Clash by Discipline", icon="LIGHT")

        row = box.row()
        row.prop(props, "clash_preset", text="")

        if props.clash_preset == 'CUSTOM':
            row = box.row(align=True)
            row.prop(props, "discipline_a", text="")
            row.label(text="vs")
            row.prop(props, "discipline_b", text="")

        row = box.row()
        row.prop(props, "discipline_tolerance")

        row = box.row()
        row.operator("bim.clash_by_discipline",
                     text="Run Clash Detection",
                     icon="PLAY")

        # Display discipline clash results
        if props.discipline_clash_loaded and props.discipline_clash_candidates:
            layout.separator()
            box = layout.box()
            box.label(text=f"{len(props.discipline_clash_candidates)} Clash Candidates Found", icon="ERROR")

            # Header row
            split = box.split(factor=0.05, align=True)
            split.label(text="#")
            row = split.row(align=True)
            row.label(text="Element A")
            row.label(text="Element B")
            row.label(text="Type")

            # Clash list
            box.template_list(
                "BIM_UL_discipline_clashes",
                "",
                props,
                "discipline_clash_candidates",
                props,
                "active_discipline_clash_index"
            )

            # Select clash button
            row = box.row()
            row.operator("bim.select_discipline_clash", text="Select & Zoom to Clash", icon="ZOOM_IN")

            # Show selected clash details
            if 0 <= props.active_discipline_clash_index < len(props.discipline_clash_candidates):
                candidate = props.discipline_clash_candidates[props.active_discipline_clash_index]
                detail_box = box.box()
                detail_box.label(text="Clash Details:", icon="INFO")
                col = detail_box.column(align=True)
                col.label(text=f"Element A: {candidate.name_a}")
                col.label(text=f"  GUID: {candidate.guid_a}")
                col.label(text=f"  Class: {candidate.ifc_class_a}")
                col.separator()
                col.label(text=f"Element B: {candidate.name_b}")
                col.label(text=f"  GUID: {candidate.guid_b}")
                col.label(text=f"  Class: {candidate.ifc_class_b}")

        # Advanced: Traditional clash sets (collapsible)
        layout.separator()

        def draw_traditional_clash_sets(layout_: bpy.types.UILayout, context_: bpy.types.Context) -> None:
            row = layout_.row(align=True)
            row.operator("bim.add_clash_set")
            row.operator("bim.import_clash_sets", text="", icon="IMPORT")
            row.operator("bim.export_clash_sets", text="", icon="EXPORT")

            if not props.clash_sets:
                layout_.label(text="No clash sets configured", icon="INFO")
                return

            layout_.template_list("BIM_UL_clash_sets", "", props, "clash_sets", props, "active_clash_set_index")

            if not props.active_clash_set:
                return

            clash_set = props.active_clash_set

            row = layout_.row(align=True)
            row.prop(clash_set, "name")
            row.operator("bim.remove_clash_set", icon="X", text="").index = props.active_clash_set_index

            row = layout_.row()
            row.prop(clash_set, "mode")

            if clash_set.mode == "intersection":
                row = layout_.row()
                row.prop(clash_set, "tolerance")
                row = layout_.row()
                row.prop(clash_set, "check_all")
            elif clash_set.mode == "collision":
                row = layout_.row()
                row.prop(clash_set, "allow_touching")
            elif clash_set.mode == "clearance":
                row = layout_.row()
                row.prop(clash_set, "clearance")
                row = layout_.row()
                row.prop(clash_set, "check_all")
            else:
                assert_never(clash_set.mode)

            def draw_clash_set_group(group: tool.Clash.ClashSourceGroup) -> None:
                row = layout_.row(align=True)
                row.label(text=f"Group {group.upper()}:", icon="OUTLINER_OB_POINTCLOUD")
                row.operator("bim.add_clash_source", icon="ADD", text="").group = group

                sources = clash_set.get_clash_sources_group(group)
                if not sources:
                    return
                box_ = layout_.box()
                for index, source in enumerate(sources):
                    row = box_.row(align=True)
                    row.column().label(text="", icon="POINTCLOUD_POINT")

                    col = row.column()
                    col.alert = not bool(source.name)
                    col.prop(source, "name", text="", placeholder="source.ifc")

                    op = row.operator("bim.select_clash_source", icon="FILE_FOLDER", text="")
                    op.index = index
                    op.group = group
                    row.label(text="", icon="BLANK1")

                    row.prop(source, "mode", text="")
                    op = row.operator("bim.remove_clash_source", icon="X", text="")
                    op.index = index
                    op.group = group

                    if source.mode != "a":
                        def draw_filter(layout__: bpy.types.UILayout, context__: bpy.types.Context) -> None:
                            bonsai.bim.helper.draw_filter(
                                layout__,
                                source.filter_groups,
                                ClashData,
                                f"clash_{props.active_clash_set_index}_{group}_{index}",
                            )

                        bonsai.bim.helper.draw_expandable_panel(
                            box_,
                            context_,
                            "Filter",
                            draw_filter,
                            default_closed=True,
                            panel_id=f"filter_{group}_{index}",
                        )

            layout_.separator()
            draw_clash_set_group("a")
            layout_.separator()
            draw_clash_set_group("b")
            layout_.separator()

            row = layout_.row()
            row.prop(props, "should_create_clash_snapshots")

            layout_.prop(props, "export_path")

            box_ = layout_.box()
            box_.label(text="Performance Optimization", icon='SETTINGS')
            row = box_.row()
            row.prop(props, "enable_bbox_prefilter", text="Use Spatial Index Prefilter")

            if props.enable_bbox_prefilter:
                row = box_.row()
                row.prop(props, "bbox_database_path", text="Database")

            row = layout_.row()
            op = row.operator("bim.execute_ifc_clash")
            op.filepath = props.export_path

            row = layout_.row()
            if clash_set.clashes_loaded:
                row.column().label(text=f"{len(clash_set.clashes)} Clashes Found", icon="PIVOT_CURSOR")

                col = row.column()
                col.alignment = "RIGHT"
                col.prop(clash_set, "clashes_loaded", text="", icon="TRASH", invert_checkbox=True)

                split = layout_.split(factor=0.07, align=True)
                split.label(text="#")

                row = split.row(align=True)
                row.label(text="Group A Element")
                row.label(text="Group B Element")
                row.label(text="Type")

                layout_.template_list("BIM_UL_clashes", "", clash_set, "clashes", props, "active_clash_index")
                row = layout_.row()
                row.operator("bim.select_clash")
            else:
                row.label(text="Clashes Are Not Loaded", icon="PIVOT_CURSOR")

        bonsai.bim.helper.draw_expandable_panel(
            layout,
            context,
            "Advanced: Traditional Clash Sets (File-based)",
            draw_traditional_clash_sets,
            default_closed=True,
            panel_id="traditional_clash_sets",
        )


class BIM_PT_clash_manager(Panel):
    bl_idname = "BIM_PT_clash_manager"
    bl_label = "Clash Manager"
    bl_options = {"DEFAULT_CLOSED"}
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tab_clash_detection"

    def draw(self, context):
        pass


class BIM_PT_smart_clash_manager(Panel):
    bl_idname = "BIM_PT_smart_clash_manager"
    bl_label = "Smart Clash Manager"
    bl_options = {"DEFAULT_CLOSED"}
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_clash_manager"

    def draw(self, context):
        assert self.layout
        layout = self.layout
        props = tool.Clash.get_clash_props()

        row = layout.row()
        layout.label(text="Select clash results to group:")

        row = layout.row(align=True)
        row.prop(props, "clash_results_path", text="")
        op = row.operator("bim.select_clash_results", icon="FILE_FOLDER", text="")

        row = layout.row()
        layout.label(text="Select output path for smart-grouped clashes:")

        row = layout.row(align=True)
        row.prop(props, "smart_grouped_clashes_path", text="")
        op = row.operator("bim.select_smart_grouped_clashes_path", icon="FILE_FOLDER", text="")

        row = layout.row(align=True)
        row.prop(props, "smart_clash_grouping_max_distance")

        row = layout.row(align=True)
        row.operator("bim.smart_clash_group")

        row = layout.row(align=True)
        row.operator("bim.load_smart_groups_for_active_clash_set")

        layout.template_list("BIM_UL_smart_groups", "", props, "smart_clash_groups", props, "active_smart_group_index")

        row = layout.row(align=True)
        row.operator("bim.select_smart_group")


class BIM_UL_clash_sets(bpy.types.UIList):
    def draw_item(
        self,
        context,
        layout: bpy.types.UILayout,
        data: BIMClashProperties,
        item: ClashSet,
        icon,
        active_data,
        active_propname,
    ) -> None:
        if item:
            layout.prop(item, "name", text="", emboss=False)
        else:
            layout.label(text="", translate=False)


class BIM_UL_smart_groups(bpy.types.UIList):
    def draw_item(
        self,
        context,
        layout: bpy.types.UILayout,
        data: BIMClashProperties,
        item: SmartClashGroup,
        icon,
        active_data,
        active_propname,
    ) -> None:
        if item:
            layout.label(text=str(item.number), translate=False, icon="NONE", icon_value=0)
        else:
            layout.label(text="", translate=False)


class BIM_UL_discipline_clashes(bpy.types.UIList):
    """UIList for discipline-based clash results"""
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
            split = layout.split(factor=0.05, align=True)
            split.label(text=str(index + 1))

            row = split.row(align=False)
            row.label(text=str(item.name_a), translate=False, icon="NONE")
            row.label(text=str(item.name_b), translate=False, icon="NONE")

            col = row.column()
            col.enabled = False
            col.label(text=f"{item.ifc_class_a}/{item.ifc_class_b}")
        else:
            layout.label(text="", translate=False)


class BIM_UL_clashes(bpy.types.UIList):
    def draw_item(
        self,
        context,
        layout: bpy.types.UILayout,
        data: BIMClashProperties,
        item: Clash,
        icon,
        active_data,
        active_propname,
        index,
        fit_flag,
    ) -> None:
        if item:
            split = layout.split(factor=0.05, align=True)
            split.label(text=str(index + 1))

            row = split.row(align=False)
            row.label(text=str(item.a_name), translate=False, icon="NONE", icon_value=0)
            row.label(text=str(item.b_name), translate=False, icon="NONE", icon_value=0)

            col = row.column()
            col.enabled = False
            col.prop(item, "clash_type", text="")

            row.prop(item, "status", text="")
        else:
            layout.label(text="", translate=False)
