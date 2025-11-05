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

import bpy
from . import ui, prop, operator
# Note: gizmo, visualization, database moved to federation_analysis module (2025-11-02)

classes = (
    operator.AddClashSet,
    operator.AddClashSource,
    # NOTE: Federation operators moved to federation_analysis module (2025-11-03):
    # - BIM_OT_analyze_bbox_candidates
    # - BIM_OT_clash_by_discipline
    # - BIM_OT_select_discipline_clash
    # - BIM_OT_visualize_selected_discipline_clashes
    # - BIM_OT_deselect_all_clashes
    # - BIM_OT_clear_discipline_clash_visualization
    # - BIM_OT_enable_clash_gpu_visualization
    # - BIM_OT_disable_clash_gpu_visualization
    # - BIM_OT_enable_clash_gizmo_visualization
    # - BIM_OT_disable_clash_gizmo_visualization
    # - BIM_OT_load_clash_geometry
    # - BIM_OT_enable_bbox_visualization
    # - BIM_OT_disable_bbox_visualization
    # - BIM_OT_enable_semantic_proxy_visualization
    # - BIM_OT_disable_semantic_proxy_visualization
    # - BIM_OT_enable_full_geometry_visualization
    # - BIM_OT_disable_full_geometry_visualization
    operator.ExecuteIfcClash,
    operator.ExportClashSets,
    operator.ImportClashSets,
    operator.LoadSmartGroupsForActiveClashSet,
    operator.RemoveClashSet,
    operator.RemoveClashSource,
    operator.SelectClash,
    operator.SelectClashResults,
    operator.SelectClashSource,
    operator.SelectSmartGroup,
    operator.SelectSmartGroupedClashesPath,
    operator.SmartClashGroup,
    operator.BIM_OT_analyze_clash_groups,
    operator.BIM_OT_suggest_resolutions,
    operator.BIM_OT_select_resolution_option,
    prop.Clash,
    prop.ClashSource,
    prop.ClashSet,
    prop.SmartClashGroup,
    prop.DisciplineClashCandidate,
    prop.ClashGroup,
    prop.ResolutionOption,
    prop.BIMClashProperties,
    ui.BIM_PT_ifcclash,
    ui.BIM_PT_clash_manager,
    ui.BIM_PT_smart_clash_manager,
    ui.BIM_UL_clashes,
    ui.BIM_UL_clash_sets,
    # ui.BIM_UL_discipline_clashes,  # Moved to federation_analysis module
    ui.BIM_UL_smart_groups,
    # Note: ClashMarkerGizmo and ClashMarkerGizmoGroup moved to federation_analysis module
)


def register():
    bpy.types.Scene.BIMClashProperties = bpy.props.PointerProperty(type=prop.BIMClashProperties)


def unregister():
    del bpy.types.Scene.BIMClashProperties
