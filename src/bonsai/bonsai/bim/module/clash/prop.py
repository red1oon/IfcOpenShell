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
import bonsai.tool as tool
from bonsai.bim.prop import StrProperty, Attribute, BIMFilterGroup
from bpy.types import PropertyGroup
from bpy.props import (
    PointerProperty,
    StringProperty,
    EnumProperty,
    BoolProperty,
    IntProperty,
    FloatProperty,
    FloatVectorProperty,
    CollectionProperty,
)
from ifcopenshell.geom.main import ClashType, CLASH_TYPE_ITEMS
from mathutils import Vector
from typing import TYPE_CHECKING, Literal, Union


class ClashSource(PropertyGroup):
    name: StringProperty(  # pyright: ignore[reportRedeclaration]
        name="File",
        description="Absolute filepath to existing .ifc file to use as a clash source.",
    )
    filter_groups: CollectionProperty(type=BIMFilterGroup, name="Filter Groups")  # pyright: ignore[reportRedeclaration]
    mode: EnumProperty(  # pyright: ignore[reportRedeclaration]
        items=[
            ("a", "All Elements", "All elements will be used for clashing"),
            ("i", "Include", "Only the selected elements are included for clashing"),
            ("e", "Exclude", "All elements except the selected elements are included for clashing"),
        ],
        name="Mode",
    )

    if TYPE_CHECKING:
        name: str
        filter_groups: bpy.types.bpy_prop_collection_idprop[BIMFilterGroup]
        mode: Literal["a", "i", "e"]


class Clash(PropertyGroup):
    a_global_id: StringProperty(name="A")
    b_global_id: StringProperty(name="B")
    a_name: StringProperty(name="A Name")
    b_name: StringProperty(name="B Name")
    clash_type: EnumProperty(  # pyright: ignore[reportRedeclaration]
        name="Clash Type",
        items=tuple((i, i, "") for i in CLASH_TYPE_ITEMS),
    )
    status: BoolProperty(
        name="Status",
        description="Clash status, not stored anywhere - currently just displayed in UI for convenience.",
        default=False,
    )

    if TYPE_CHECKING:
        a_global_id: str
        b_global_id: str
        a_name: str
        b_name: str
        clash_type: ClashType
        status: bool


def clashes_loaded_update(self: "ClashSet", context: bpy.types.Context) -> None:
    if self.clashes_loaded:
        return
    tool.Clash.clear_active_clash_set_results()


class ClashSet(PropertyGroup):
    mode: EnumProperty(
        items=[
            (
                "intersection",
                "Intersection",
                "Detect objects that protrude or pierce another object",
                "PIVOT_MEDIAN",
                1,
            ),
            ("collision", "Collision", "Detect touching objects with any surface collision", "PIVOT_INDIVIDUAL", 2),
            ("clearance", "Clearance", "Detect objects within a proximity threshold", "PIVOT_ACTIVE", 3),
        ],
        name="Mode",
    )
    tolerance: FloatProperty(name="Tolerance", default=0.002, subtype="DISTANCE")
    clearance: FloatProperty(name="Clearance", default=0.01, subtype="DISTANCE")
    allow_touching: BoolProperty(name="Allow Touching", default=False)
    check_all: BoolProperty(name="Check All", default=False)
    a: CollectionProperty(name="Group A", type=ClashSource)
    b: CollectionProperty(name="Group B", type=ClashSource)
    clashes: CollectionProperty(name="Clashes", type=Clash)
    clashes_loaded: BoolProperty(
        name="Clash Results Are Loaded",
        description="Click to unload clash results for the clash set.",
        update=clashes_loaded_update,
    )

    if TYPE_CHECKING:
        mode: Literal["intersection", "collision", "clearance"]
        tolerance: float
        clearance: float
        allow_touching: bool
        check_all: bool
        a: bpy.types.bpy_prop_collection_idprop[ClashSource]
        b: bpy.types.bpy_prop_collection_idprop[ClashSource]
        clashes: bpy.types.bpy_prop_collection_idprop[Clash]
        clashes_loaded: bool

    def get_clash_sources_group(
        self, group: tool.Clash.ClashSourceGroup
    ) -> "bpy.types.bpy_prop_collection_idprop[ClashSource]":
        return getattr(self, group)

    def get_clash_sources(
        self,
    ) -> "dict[tool.Clash.ClashSourceGroup, bpy.types.bpy_prop_collection_idprop[ClashSource]]":
        return {g: self.get_clash_sources_group(g) for g in tool.Clash.CLASH_SOURCE_GROUP_LITERALS}


class SmartClashGroup(PropertyGroup):
    number: StringProperty(name="Number")
    global_ids: CollectionProperty(name="GlobalIDs", type=StrProperty)

    if TYPE_CHECKING:
        number: str
        global_ids: bpy.types.bpy_prop_collection_idprop[StrProperty]


class DisciplineClashCandidate(PropertyGroup):
    """Single clash candidate from discipline-based detection"""
    guid_a: StringProperty(name="Element A GUID")
    guid_b: StringProperty(name="Element B GUID")
    name_a: StringProperty(name="Element A Name")
    name_b: StringProperty(name="Element B Name")
    ifc_class_a: StringProperty(name="Element A IFC Class")
    ifc_class_b: StringProperty(name="Element B IFC Class")

    # Selection state for multi-select visualization
    selected: BoolProperty(
        name="Selected",
        description="Select this clash for visualization",
        default=False
    )

    # Clash metadata
    distance: FloatProperty(
        name="Clash Distance",
        description="Overlap or clearance distance",
        default=0.0,
        subtype='DISTANCE'
    )

    # Status tracking (persisted in SQLite database)
    status: EnumProperty(
        name="Status",
        description="Clash review status",
        items=[
            ('NEW', 'New', 'Newly detected clash'),
            ('ACTIVE', 'Active', 'Under review'),
            ('REVIEWED', 'Reviewed', 'Reviewed, awaiting fix'),
            ('RESOLVED', 'Resolved', 'Fixed/Approved'),
        ],
        default='NEW'
    )

    if TYPE_CHECKING:
        guid_a: str
        guid_b: str
        name_a: str
        name_b: str
        ifc_class_a: str
        ifc_class_b: str
        distance: float
        status: Literal["NEW", "ACTIVE", "REVIEWED", "RESOLVED"]


class BIMClashProperties(PropertyGroup):
    blender_clash_set_a: CollectionProperty(name="Blender Clash Set A", type=StrProperty)
    blender_clash_set_b: CollectionProperty(name="Blender Clash Set B", type=StrProperty)
    clash_sets: CollectionProperty(name="Clash Sets", type=ClashSet)
    should_create_clash_snapshots: BoolProperty(
        name="Create Snapshots", description="Create bcf snapshots", default=False
    )
    clash_results_path: StringProperty(name="Clash Results Path")
    smart_grouped_clashes_path: StringProperty(name="Smart Grouped Clashes Path")
    active_clash_set_index: IntProperty(name="Active Clash Set Index")
    active_clash_index: IntProperty(name="Active Clash Index")
    smart_clash_groups: CollectionProperty(name="Smart Clash Groups", type=SmartClashGroup)
    active_smart_group_index: IntProperty(name="Active Smart Group Index")
    smart_clash_grouping_max_distance: IntProperty(
        name="Smart Clash Grouping Max Distance", default=3, soft_min=1, soft_max=10
    )
    p1: FloatVectorProperty(name="P1", default=(0.0, 0.0, 0.0), subtype="XYZ")
    p2: FloatVectorProperty(name="P2", default=(0.0, 0.0, 0.0), subtype="XYZ")
    active_clash_text: StringProperty(name="Active Clash Text")
    export_path: StringProperty(
        name="Export Path",
        description=".bcf or .json file to export the clash results to",
        subtype="FILE_PATH",
    )

    if TYPE_CHECKING:
        blender_clash_set_a: bpy.types.bpy_prop_collection_idprop[StrProperty]
        blender_clash_set_b: bpy.types.bpy_prop_collection_idprop[StrProperty]
        clash_sets: bpy.types.bpy_prop_collection_idprop[ClashSet]
        should_create_clash_snapshots: bool
        clash_results_path: str
        smart_grouped_clashes_path: str
        active_clash_set_index: int
        active_clash_index: int
        smart_clash_groups: bpy.types.bpy_prop_collection_idprop[SmartClashGroup]
        active_smart_group_index: int
        smart_clash_grouping_max_distance: int
        p1: Vector
        p2: Vector
        active_clash_text: str
        export_path: str

    @property
    def active_clash_set(self) -> Union[ClashSet, None]:
        return tool.Blender.get_active_uilist_element(self.clash_sets, self.active_clash_set_index)

    @property
    def active_smart_group(self) -> Union[SmartClashGroup, None]:
        return tool.Blender.get_active_uilist_element(self.smart_clash_groups, self.active_smart_group_index)

    @property
    def active_clash(self) -> Union[Clash, None]:
        if not (clash_set := self.active_clash_set):
            return None
        return tool.Blender.get_active_uilist_element(clash_set.clashes, self.active_clash_index)

    enable_bbox_prefilter: BoolProperty(
        name="Enable Bbox Prefilter",
        description="Use spatial index for pre-broadphase filtering",
        default=False
    )
    bbox_database_path: StringProperty(
        name="Bbox Database Path",
        description="Path to spatial index database",
        subtype='FILE_PATH',
        default=""
    )

    # Discipline-based clash detection
    discipline_a: EnumProperty(
        name="Discipline A",
        description="Primary discipline for clash detection",
        items=[
            ('ARC', 'Architecture', 'Architectural elements'),
            ('STR', 'Structure', 'Structural elements'),
            ('MEP', 'MEP', 'Mechanical, Electrical, Plumbing'),
            ('ACMV', 'ACMV', 'Air Conditioning & Mechanical Ventilation'),
            ('ELEC', 'Electrical', 'Electrical systems'),
            ('FP', 'Fire Protection', 'Fire protection systems'),
            ('SP', 'Sanitary/Plumbing', 'Sanitary and plumbing'),
            ('CW', 'Civil Works', 'Civil works'),
        ],
        default='ARC'
    )
    discipline_b: EnumProperty(
        name="Discipline B",
        description="Secondary discipline for clash detection",
        items=[
            ('ARC', 'Architecture', 'Architectural elements'),
            ('STR', 'Structure', 'Structural elements'),
            ('MEP', 'MEP', 'Mechanical, Electrical, Plumbing'),
            ('ACMV', 'ACMV', 'Air Conditioning & Mechanical Ventilation'),
            ('ELEC', 'Electrical', 'Electrical systems'),
            ('FP', 'Fire Protection', 'Fire protection systems'),
            ('SP', 'Sanitary/Plumbing', 'Sanitary and plumbing'),
            ('CW', 'Civil Works', 'Civil works'),
        ],
        default='STR'
    )
    clash_preset: EnumProperty(
        name="Clash Preset",
        description="Common clash detection presets",
        items=[
            ('CUSTOM', 'Custom', 'Custom discipline selection'),
            ('ARC_STR', 'Architecture vs Structure', 'Detect ARC-STR clashes'),
            ('ELEC_ARC', 'Electrical vs Architecture', 'Detect ELEC-ARC clashes'),
            ('ACMV_ARC', 'ACMV vs Architecture', 'Detect ACMV-ARC clashes'),
            ('FP_ARC', 'Fire Protection vs Architecture', 'Detect FP-ARC clashes'),
            ('SP_ARC', 'Sanitary Plumbing vs Architecture', 'Detect SP-ARC clashes'),
            ('ALL_MEP', 'All MEP vs ARC+STR (Demo)', 'All MEP (ELEC+ACMV+FP+SP) vs Architecture+Structure'),
        ],
        default='ELEC_ARC'
    )
    discipline_tolerance: FloatProperty(
        name="Tolerance",
        description="Clash tolerance in model units",
        default=0.01,
        min=0.0,
        soft_max=1.0,
        precision=3,
        subtype='DISTANCE'
    )

    # Discipline clash results
    discipline_clash_candidates: CollectionProperty(
        name="Discipline Clash Candidates",
        type=DisciplineClashCandidate
    )
    active_discipline_clash_index: IntProperty(
        name="Active Discipline Clash Index",
        default=0
    )
    discipline_clash_loaded: BoolProperty(
        name="Discipline Clash Loaded",
        description="Whether discipline clash results are loaded",
        default=False
    )

    # Gizmo visualization control
    gizmo_visualization_enabled: BoolProperty(
        name="Gizmo Visualization Enabled",
        description="Whether clash gizmo markers are displayed in viewport",
        default=False
    )

    # Gizmo navigation
    current_clash_index: IntProperty(
        name="Current Clash Index",
        description="Currently viewed clash (for Previous/Next navigation)",
        default=0
    )

    # BBox Semantic Geometry - LOD Visualization Control (Phase 2)
    lod_visualization_mode: EnumProperty(
        name="LOD Mode",
        description="Level of Detail visualization mode",
        items=[
            ('NONE', 'None', 'No federation visualization', 'HIDE_ON', 0),
            ('BBOX_WIREFRAME', 'BBox Wireframe', 'Colored wireframe bounding boxes (instant, <10MB)', 'SHADING_BBOX', 1),
            ('SEMANTIC_PROXY', 'Semantic Proxies', 'Procedural geometry (fast, ~200MB)', 'MESH_CUBE', 2),
            ('FULL_GEOMETRY', 'Full IFC Geometry', 'Complete IFC geometry (slow, ~16GB)', 'MESH_ICOSPHERE', 3),
        ],
        default='NONE'
    )

    bbox_visualization_enabled: BoolProperty(
        name="BBox Visualization Active",
        description="Whether BBox wireframe visualization is currently active in viewport",
        default=False
    )

    bbox_element_limit: IntProperty(
        name="Element Limit",
        description="Limit number of elements to render (0 = all). Useful for testing",
        default=0,
        min=0,
        soft_max=50000
    )

    show_lod_stats: BoolProperty(
        name="Show Stats Overlay",
        description="Display LOD statistics in viewport (element count, memory, FPS)",
        default=True
    )
