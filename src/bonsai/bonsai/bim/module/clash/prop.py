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


class ClashGroup(PropertyGroup):
    """Clash group from cascade detection (element with 3+ clashes)"""
    group_id: IntProperty(
        name="Group ID",
        description="Unique identifier for this clash group"
    )
    element_guid: StringProperty(
        name="Central Element GUID",
        description="GUID of the element causing multiple clashes"
    )
    element_name: StringProperty(
        name="Central Element Name",
        description="Name of the central element"
    )
    ifc_class: StringProperty(
        name="IFC Class",
        description="IFC class of the central element"
    )
    discipline: StringProperty(
        name="Discipline",
        description="Discipline of the central element"
    )
    clash_count: IntProperty(
        name="Clash Count",
        description="Number of clashes this element is involved in",
        default=0
    )
    severity: EnumProperty(
        name="Severity",
        description="Clash group severity based on count and disciplines",
        items=[
            ('LOW', 'Low', 'Low severity (3-5 clashes)'),
            ('MEDIUM', 'Medium', 'Medium severity (6-10 clashes)'),
            ('HIGH', 'High', 'High severity (11-20 clashes)'),
            ('CRITICAL', 'Critical', 'Critical severity (20+ clashes)'),
        ],
        default='LOW'
    )
    member_clash_ids: StringProperty(
        name="Member Clash IDs",
        description="Comma-separated clash IDs that belong to this group",
        default=""
    )

    if TYPE_CHECKING:
        group_id: int
        element_guid: str
        element_name: str
        ifc_class: str
        discipline: str
        clash_count: int
        severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        member_clash_ids: str


class ResolutionOption(PropertyGroup):
    """Single resolution option with cost and risk estimates"""
    option_id: IntProperty(
        name="Option ID",
        description="Unique identifier for this resolution option"
    )
    description: StringProperty(
        name="Description",
        description="Human-readable description of the resolution approach"
    )
    total_hours: FloatProperty(
        name="Total Design Effort (hours)",
        description="Total estimated person-hours",
        default=0.0
    )
    total_cost: FloatProperty(
        name="Total Cost",
        description="Total estimated cost in dollars",
        default=0.0,
        subtype='UNSIGNED'
    )
    risk_level: EnumProperty(
        name="Risk Level",
        description="Risk assessment for this resolution approach",
        items=[
            ('LOW', 'Low', 'Low risk - straightforward implementation'),
            ('MEDIUM', 'Medium', 'Medium risk - some coordination needed'),
            ('HIGH', 'High', 'High risk - complex coordination'),
            ('CRITICAL', 'Critical', 'Critical risk - major schedule/budget impact'),
        ],
        default='LOW'
    )
    clashes_resolved: IntProperty(
        name="Clashes Resolved",
        description="Number of clashes this option will resolve",
        default=0
    )
    schedule_days: FloatProperty(
        name="Schedule Impact (days)",
        description="Estimated schedule impact in working days",
        default=0.0
    )
    recommended: BoolProperty(
        name="Recommended",
        description="Whether this is the recommended option",
        default=False
    )

    if TYPE_CHECKING:
        option_id: int
        description: str
        total_hours: float
        total_cost: float
        risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
        clashes_resolved: int
        schedule_days: float
        recommended: bool


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

    # Clash Adjustment workflow tracking
    clash_groups_analyzed: BoolProperty(
        name="Clash Groups Analyzed",
        description="Whether clash grouping analysis has been performed",
        default=False
    )
    resolutions_generated: BoolProperty(
        name="Resolutions Generated",
        description="Whether resolution suggestions have been generated",
        default=False
    )

    # Gizmo visualization control
    gizmo_visualization_enabled: BoolProperty(
        name="Gizmo Visualization Enabled",
        description="Whether clash gizmo markers are displayed in viewport",
        default=False,
        options={'SKIP_SAVE'}  # Don't persist across sessions - user must enable manually
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

    # ================================================================
    # INTELLIGENT CLASH GROUPING & RESOLUTION (POC)
    # ================================================================
    # Note: Clash groups and resolution options are stored in database
    # UI reads directly from database queries (no need for collection properties in POC)

    # ================================================================
    # PHASE 1.5: Configuration System
    # ================================================================

    # Active configuration preset
    active_preset_name: StringProperty(
        name="Active Preset",
        description="Currently active configuration preset (US Market, Singapore, EU Standard)",
        default="US Market"
    )

    # Show learned estimates toggle
    show_learned_estimates: BoolProperty(
        name="Show Learned Estimates",
        description="Display database-learned estimates with confidence indicators",
        default=False
    )

    # Resolution selection
    selected_resolution_index: IntProperty(
        name="Selected Resolution Index",
        description="Index of currently selected resolution option in UIList",
        default=-1
    )

    selected_resolution_option_id: StringProperty(
        name="Selected Resolution Option ID",
        description="Database option_id of selected resolution",
        default=""
    )

    def get_resolution_options_enum(self, context):
        """Dynamically populate resolution options from database"""
        import sqlite3
        import os
        import bpy

        items = [("NONE", "-- Select Resolution Option --", "No option selected")]

        try:
            # Get database path from federation properties
            fed_props = context.scene.BIMFederationProperties
            db_path = fed_props.federation_database_path
            if not db_path or not os.path.exists(db_path):
                return items

            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT DISTINCT
                    ro.option_id,
                    ro.group_id,
                    ro.option_type,
                    ro.total_design_hours,
                    ro.total_design_cost,
                    ro.risk_category,
                    cg.cascade_element_class,
                    cg.total_clashes
                FROM resolution_options ro
                JOIN clash_groups cg ON ro.group_id = cg.group_id
                ORDER BY ro.group_id, ro.recommendation_rank
            """)

            rows = cursor.fetchall()
            conn.close()

            for option_id, group_id, opt_type, hours, cost, risk, elem_class, clashes in rows:
                # Format: "Wall(17) Relocate $1.5k 12h MED"
                cost_k = cost / 1000
                opt_short = opt_type.replace('_element', '').replace('_', ' ').title()
                label = f"{elem_class}({clashes}) {opt_short} ${cost_k:.1f}k {hours:.0f}h {risk[:3].upper()}"
                desc = f"{elem_class} ({clashes} clashes) → {opt_type}: ${cost:,.0f}, {hours:.1f}hrs, Risk: {risk}"
                items.append((option_id, label, desc))

        except Exception as e:
            print(f"Error loading resolution options: {e}")
            return items

        return items

    selected_resolution_dropdown: EnumProperty(
        name="Resolution Option",
        description="Select a resolution option to preview or apply",
        items=get_resolution_options_enum,
        update=lambda self, context: setattr(self, 'selected_resolution_option_id', self.selected_resolution_dropdown if self.selected_resolution_dropdown != "NONE" else "")
    )

    # ================================================================
    # PHASE 2: Learning System & Feedback
    # ================================================================

    # Feedback panel visibility
    show_feedback_panel: BoolProperty(
        name="Show Feedback Panel",
        description="Whether to show resolution feedback collection panel",
        default=False
    )

    # Feedback inputs
    resolution_rating: IntProperty(
        name="Resolution Rating",
        description="How well did this resolution work? (1-5 stars)",
        min=1,
        max=5,
        default=3
    )

    actual_hours: FloatProperty(
        name="Actual Hours",
        description="Actual time spent implementing this resolution (total hours)",
        min=0.0,
        default=0.0,
        precision=1,
        subtype='NONE'
    )

    variance_notes: StringProperty(
        name="Variance Notes",
        description="Optional notes explaining why actual differed from estimate",
        default=""
    )

    # Track last applied resolution for feedback
    last_applied_resolution_history_id: IntProperty(
        name="Last Applied Resolution History ID",
        description="Database history_id for last applied resolution (for feedback tracking)",
        default=-1
    )

    # Project ID for learning context
    project_id: StringProperty(
        name="Project ID",
        description="Project identifier for project-specific learning (e.g., 'Terminal_1')",
        default="Terminal_1"
    )
