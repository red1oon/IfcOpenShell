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
Qualified Path: src/bonsai/bonsai/bim/module/federation/prop.py

Federation Module Properties
-----------------------------
Blender property groups for storing federation settings and state.
"""

from __future__ import annotations
import bpy
from pathlib import Path
from bpy.types import PropertyGroup
from bpy.props import (
    StringProperty,
    BoolProperty,
    IntProperty,
    FloatProperty,
    CollectionProperty,
    PointerProperty,
    EnumProperty,
)
from typing import TYPE_CHECKING


def get_default_federation_db_path() -> str:
    """
    Get intelligent default path for federation database

    Priority:
    1. ~/Documents/bonsai/ if exists
    2. ~/Documents/ if exists
    3. /tmp/ as fallback

    Returns filename: "federation_index.db"
    """
    home = Path.home()

    # Priority 1: ~/Documents/bonsai/
    bonsai_docs = home / "Documents" / "bonsai"
    if bonsai_docs.exists() and bonsai_docs.is_dir():
        return str(bonsai_docs / "federation_index.db")

    # Priority 2: ~/Documents/
    documents = home / "Documents"
    if documents.exists() and documents.is_dir():
        return str(documents / "federation_index.db")

    # Priority 3: /tmp/ fallback
    return "/tmp/federation_index.db"


class FederatedFile(PropertyGroup):
    """Represents a single federated IFC file"""
    
    name: StringProperty(
        name="File",
        description="Absolute filepath to IFC file in federation",
    )
    
    discipline: StringProperty(
        name="Discipline",
        description="Discipline tag (e.g., ARC, ACMV, STR)",
        default=""
    )
    
    is_preprocessed: BoolProperty(
        name="Preprocessed",
        description="Whether this file has been preprocessed for federation",
        default=False
    )
    
    element_count: IntProperty(
        name="Elements",
        description="Number of elements extracted from this file",
        default=0,
        min=0
    )

    if TYPE_CHECKING:
        name: str
        discipline: str
        is_preprocessed: bool
        element_count: int


class BIMFederationProperties(PropertyGroup):
    """Properties for multi-model federation"""
    
    # Federated file list
    federated_files: CollectionProperty(
        name="Federated Files",
        type=FederatedFile,
        description="List of IFC files in the federation"
    )
    
    active_federated_file_index: IntProperty(
        name="Active Federated File Index",
        default=0
    )
    
    # Federation database settings
    federation_database_path: StringProperty(
        name="Federation Database",
        description="Path to SQLite federation index database.\n"
                    "Auto-defaults to: ~/Documents/bonsai/federation_index.db\n"
                    "You can edit this path to point to any .db file",
        subtype='FILE_PATH',
        default=""  # Empty = will use auto-default on first access
        # Note: No get/set callbacks = editable in UI
    )
    
    index_loaded: BoolProperty(
        name="Index Loaded",
        description="Whether the federation spatial index is loaded in memory",
        default=False
    )

    solid_loaded: BoolProperty(
        name="Solid Loaded",
        description="Whether solid procedural boxes have been loaded",
        default=False
    )

    # Office/Depot address for navigation
    office_address: StringProperty(
        name="Address",
        description="Office or depot address for navigation to equipment sites.\n"
                    "Used as starting point for web map directions.\n"
                    "Example: '123 Main St, Kuala Lumpur, Malaysia'",
        default=""
    )

    # Sample extraction settings
    sample_anchor_type: EnumProperty(
        name="Sample Anchor",
        description="Element type to anchor sampling region (finds densest area around this type)",
        items=[
            ('ELEC', 'Electrical', 'Anchor to electrical elements (for conduit routing tests)'),
            ('ACMV', 'HVAC', 'Anchor to HVAC elements (for duct routing tests)'),
            ('FP', 'Fire Protection', 'Anchor to fire protection elements'),
            ('SP', 'Sprinkler', 'Anchor to sprinkler elements'),
            ('ARC', 'Architecture', 'Anchor to walls/doors (for visual context)'),
            ('STR', 'Structure', 'Anchor to structural elements'),
            ('AUTO', 'Auto (Densest MEP)', 'Automatically find densest MEP region'),
        ],
        default='ELEC'
    )

    # Visualization mode (for UI control)
    visualization_mode: EnumProperty(
        name="Visualization Mode",
        description="Choose visualization detail level",
        items=[
            ('NONE', 'None', 'No visualization loaded', 'BLANK1', 0),
            ('BBOXES', 'BBoxes', 'Fast wireframe bounding boxes (< 1s load)', 'MESH_CUBE', 1),
            ('SEMANTICS', 'Semantics', 'Simple semantic shapes (~10s load, instant switching!)', 'MESH_ICOSPHERE', 2),
            ('MATERIALS', 'Materials', 'Detailed shapes with materials (same as Semantics + enhancements)', 'SHADING_RENDERED', 3),
        ],
        default='SEMANTICS'  # Default to SEMANTICS for best balance
    )

    # S178: RTree Inspector — search box + pick result display
    rtree_search: StringProperty(
        name="Search",
        description="Search by element name, GUID, discipline (ARC/STR/MEP…), or IFC class",
        default="",
    )
    rtree_result_name: StringProperty(name="Name", default="")
    rtree_result_disc: StringProperty(name="Disc", default="")
    rtree_result_class: StringProperty(name="Class", default="")
    rtree_result_guid: StringProperty(name="GUID", default="")
    rtree_result_count: IntProperty(name="Matches", default=0)
    rtree_picked_name: StringProperty(name="Picked Name", default="")
    rtree_picked_disc: StringProperty(name="Picked Disc", default="")
    rtree_picked_class: StringProperty(name="Picked Class", default="")
    rtree_picked_guid: StringProperty(name="Picked GUID", default="")

    # S175: GN mode toggle — checked = GN (fast/scale), unchecked = per-element (full color)
    gn_mode: BoolProperty(
        name="GN Mode",
        description="ON: GN point clouds — fast load, discipline colors, DLOD\n"
                    "OFF: per-element objects — full IFC colors, selectable, named in Outliner\n"
                    "First toggle OFF auto-loads the per-element version (one-time, slower)",
        default=True
    )

    # Geometry loading mode
    use_tessellation: BoolProperty(
        name="Use Exact IFC Geometry",
        description="Load exact tessellated geometry from IFC (27s, 100% accurate)\n"
                    "If disabled, uses progressive procedural geometry (9s, approximate shapes)",
        default=True  # DEFAULT TO TESSELLATION for accuracy
    )

    # Auto-reload on file open
    auto_reload_on_open: BoolProperty(
        name="Auto-reload Visualization",
        description="Automatically restore visualization mode when reopening Blender file",
        default=True
    )

    # Preprocessing settings
    preprocessing_in_progress: BoolProperty(
        name="Preprocessing In Progress",
        description="Whether preprocessing is currently running",
        default=False
    )
    
    progress_json_path: StringProperty(
        name="Progress JSON",
        description="Path to preprocessing progress JSON file",
        subtype='FILE_PATH',
        default=""
    )
    
    # Index statistics (read-only display)
    total_elements: IntProperty(
        name="Total Elements",
        description="Total elements in federation index",
        default=0
    )
    
    loaded_disciplines: StringProperty(
        name="Loaded Disciplines",
        description="Comma-separated list of loaded disciplines",
        default=""
    )
    
    # Query settings
    query_buffer_mm: IntProperty(
        name="Query Buffer",
        description="Buffer distance in millimeters for spatial queries",
        default=500,
        min=0,
        max=5000,
        subtype='DISTANCE'
    )
    
    filter_by_discipline: BoolProperty(
        name="Filter by Discipline",
        description="Enable discipline filtering for queries",
        default=False
    )
    
    active_disciplines: StringProperty(
        name="Active Disciplines",
        description="Comma-separated disciplines to include in queries (e.g., ACMV,FP,SP)",
        default=""
    )
    
    # Display settings
    show_statistics: BoolProperty(
        name="Show Statistics",
        description="Display detailed federation statistics",
        default=False
    )

    show_help: BoolProperty(
        name="Show Help",
        description="Display help and usage tips",
        default=False
    )

    show_advanced_settings: BoolProperty(
        name="Show Advanced",
        description="Show advanced federation settings",
        default=False
    )

    # Natural Language Query (NLP) properties
    nlp_query_text: StringProperty(
        name="NLP Query",
        description="Natural language query text (e.g., 'How many beams?')",
        default=""
    )

    nlp_results_text: StringProperty(
        name="NLP Results",
        description="Formatted query results for display",
        default=""
    )

    nlp_results_count: IntProperty(
        name="NLP Results Count",
        description="Number of result rows from last query",
        default=0,
        min=0
    )

    if TYPE_CHECKING:
        federated_files: bpy.types.bpy_prop_collection_idprop[FederatedFile]
        active_federated_file_index: int
        federation_database_path: str
        index_loaded: bool
        solid_loaded: bool
        preprocessing_in_progress: bool
        progress_json_path: str
        total_elements: int
        loaded_disciplines: str
        query_buffer_mm: int
        filter_by_discipline: bool
        active_disciplines: str
        show_statistics: bool
        show_advanced_settings: bool
        nlp_query_text: str
        nlp_results_text: str
        nlp_results_count: int


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
Federation Analysis Properties

Custom properties for discipline-based clash detection and LOD visualization.
These properties are added to the existing BIMClashProperties in the clash module.
"""

# (Imports already at top of file - federation_analysis properties merged below)


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


# These properties are registered into BIMClashProperties in the clash module
# via the register_federation_properties() function called from federation/__init__.py

def get_clash_groups(context):
    """Get available clash groups for selection dropdown"""
    items = [("NONE", "Select Clash Group...", "No group selected")]

    try:
        import sqlite3
        from pathlib import Path

        # Get federation database path
        props = context.scene.BIMFederationProperties
        if not props.index_loaded:
            return items

        db_path = props.federation_database_path
        if not db_path or not Path(db_path).exists():
            return items

        # Query clash groups
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        query = """
            SELECT
                cg.group_id,
                cg.cascade_element_class,
                cg.cascade_element_discipline,
                cg.total_clashes,
                cg.severity,
                cg.cascade_element_guid,
                em.element_name,
                em.element_type
            FROM clash_groups cg
            LEFT JOIN elements_meta em ON cg.cascade_element_guid = em.guid
            ORDER BY cg.total_clashes DESC, cg.severity DESC
        """

        cursor.execute(query)
        results = cursor.fetchall()
        conn.close()

        if not results:
            items.append(("NO_GROUPS", "No clash groups found", "Run 'Analyze Clash Groups' first"))
            return items

        # Build dropdown items - show groups with element info
        # Add sequential numbering to ensure visual distinction
        for idx, row in enumerate(results, start=1):
            group_id, elem_class, discipline, total, severity, guid, elem_name, elem_type = row

            # Format display text - emphasize GROUP identity
            elem_type_short = elem_class.replace('Ifc', '') if elem_class else 'Unknown'
            disc_name = discipline if discipline else 'Unknown'

            # Display element name if available for better context
            if elem_name and elem_name.strip():
                elem_display = f"{elem_name[:18]}"  # Use element name (keep short)
            else:
                elem_display = elem_type_short  # Fallback to IFC class

            # Concise label format: "#N: Element (DISC) - X clashes"
            # Removed severity to save space - it's in the tooltip
            label = f"#{idx}: {elem_display} ({disc_name}) - {total}"

            # Create detailed tooltip
            elem_desc_for_tooltip = elem_name if elem_name else (elem_type if elem_type else elem_type_short)
            tooltip = (f"Group #{idx}\n"
                      f"Group ID: {group_id}\n"
                      f"Element: {elem_type_short}\n"
                      f"Name: {elem_desc_for_tooltip}\n"
                      f"GUID: {guid}\n"
                      f"Discipline: {disc_name}\n"
                      f"Total Clashes: {total}\n"
                      f"Severity: {severity}")

            items.append((group_id, label, tooltip))

    except Exception as e:
        print(f"⚠️  Error loading clash groups: {e}")
        import traceback
        traceback.print_exc()
        items.append(("ERROR", f"Error: {str(e)[:30]}", str(e)))

    return items


def get_resolution_options_for_group(context):
    """Get resolution options for the selected clash group"""
    items = []

    try:
        import sqlite3
        from pathlib import Path

        # Get federation database path and selected group
        props = context.scene.BIMFederationProperties
        clash_props = context.scene.BIMClashProperties

        if not props.index_loaded or not clash_props.selected_clash_group:
            return items

        db_path = props.federation_database_path
        if not db_path or not Path(db_path).exists():
            return items

        selected_group = clash_props.selected_clash_group
        if selected_group == "NONE":
            return items

        # Query resolution options for selected group
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        query = """
            SELECT
                ro.option_id,
                ro.option_type,
                ro.description,
                ro.total_design_hours,
                ro.total_design_cost,
                ro.calendar_days_required,
                ro.risk_category,
                ro.recommendation_rank
            FROM resolution_options ro
            WHERE ro.group_id = ?
            ORDER BY ro.recommendation_rank ASC
        """

        cursor.execute(query, (selected_group,))
        results = cursor.fetchall()
        conn.close()

        if not results:
            return items

        # Build option info (not for dropdown, just for display)
        for row in results:
            option_id, opt_type, desc, hours, cost, days, risk, rank = row
            items.append({
                'option_id': option_id,
                'type': opt_type,
                'description': desc,
                'hours': hours,
                'cost': cost,
                'days': days,
                'risk': risk,
                'rank': rank,
                'is_recommended': (rank == 1)
            })

    except Exception as e:
        print(f"⚠️  Error loading resolution options: {e}")
        import traceback
        traceback.print_exc()

    return items


def update_selected_resolution(self, context):
    """Update the selected_resolution_option_id when dropdown changes"""
    props = context.scene.BIMClashProperties
    if props.selected_resolution_dropdown != "NONE":
        props.selected_resolution_option_id = props.selected_resolution_dropdown
    else:
        props.selected_resolution_option_id = ""


def register_federation_properties():
    """
    Register federation analysis properties into the existing BIMClashProperties.
    Called from federation/__init__.py during module registration.
    """
    from bonsai.bim.module.clash.prop import BIMClashProperties

    # Discipline-based clash detection
    BIMClashProperties.discipline_a = EnumProperty(
        name="Discipline A",
        description="Primary discipline for clash detection",
        items=[
            ('ARC', 'Architecture', 'Architectural elements'),
            ('STR', 'Structure', 'Structural elements'),
            ('REB', 'Reinforcement', 'Reinforcement bars (rebar)'),
            ('MEP', 'MEP', 'Mechanical, Electrical, Plumbing'),
            ('ACMV', 'ACMV', 'Air Conditioning & Mechanical Ventilation'),
            ('ELEC', 'Electrical', 'Electrical systems'),
            ('FP', 'Fire Protection', 'Fire protection systems'),
            ('SP', 'Sanitary/Plumbing', 'Sanitary and plumbing'),
            ('CW', 'Civil Works', 'Civil works'),
        ],
        default='ARC'
    )

    BIMClashProperties.discipline_b = EnumProperty(
        name="Discipline B",
        description="Secondary discipline for clash detection",
        items=[
            ('ARC', 'Architecture', 'Architectural elements'),
            ('STR', 'Structure', 'Structural elements'),
            ('REB', 'Reinforcement', 'Reinforcement bars (rebar)'),
            ('MEP', 'MEP', 'Mechanical, Electrical, Plumbing'),
            ('ACMV', 'ACMV', 'Air Conditioning & Mechanical Ventilation'),
            ('ELEC', 'Electrical', 'Electrical systems'),
            ('FP', 'Fire Protection', 'Fire protection systems'),
            ('SP', 'Sanitary/Plumbing', 'Sanitary and plumbing'),
            ('CW', 'Civil Works', 'Civil works'),
        ],
        default='STR'
    )

    BIMClashProperties.clash_preset = EnumProperty(
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

    BIMClashProperties.discipline_tolerance = FloatProperty(
        name="Tolerance",
        description="Clash tolerance in meters (0.01m = 10mm)",
        default=0.01,
        min=0.001,
        max=1.0,
        precision=3,
        subtype='DISTANCE'
    )

    # Discipline clash results
    BIMClashProperties.discipline_clash_candidates = CollectionProperty(
        name="Discipline Clash Candidates",
        type=DisciplineClashCandidate
    )

    BIMClashProperties.active_discipline_clash_index = IntProperty(
        name="Active Discipline Clash Index",
        default=0
    )

    BIMClashProperties.discipline_clash_loaded = BoolProperty(
        name="Discipline Clash Loaded",
        description="Whether discipline clash results are loaded",
        default=False
    )

    # Gizmo visualization control
    BIMClashProperties.gizmo_visualization_enabled = BoolProperty(
        name="Gizmo Visualization Enabled",
        description="Whether clash gizmo markers are displayed in viewport",
        default=False
    )

    # Gizmo navigation
    BIMClashProperties.current_clash_index = IntProperty(
        name="Current Clash Index",
        description="Currently viewed clash (for Previous/Next navigation)",
        default=0
    )

    # BBox Semantic Geometry - LOD Visualization Control (Phase 2)
    BIMClashProperties.lod_visualization_mode = EnumProperty(
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

    BIMClashProperties.bbox_visualization_enabled = BoolProperty(
        name="BBox Visualization Active",
        description="Whether BBox wireframe visualization is currently active in viewport",
        default=False
    )

    BIMClashProperties.bbox_element_limit = IntProperty(
        name="Element Limit",
        description="Limit number of elements to render (0 = all). Useful for testing",
        default=0,
        min=0,
        soft_max=50000
    )

    BIMClashProperties.show_lod_stats = BoolProperty(
        name="Show Stats Overlay",
        description="Display LOD statistics in viewport (element count, memory, FPS)",
        default=True
    )

    # Intelligent clash adjustment properties
    BIMClashProperties.active_preset_name = StringProperty(
        name="Active Preset Name",
        description="Currently active cost/adjustment preset",
        default="US Market"
    )

    BIMClashProperties.show_learned_estimates = BoolProperty(
        name="Show Learned Estimates",
        description="Use machine learning estimates for clash resolution costs",
        default=True
    )

    # Clash groups analysis state
    BIMClashProperties.clash_groups_analyzed = BoolProperty(
        name="Clash Groups Analyzed",
        description="Whether clash groups have been analyzed",
        default=False
    )

    # Clash group selection (replaces overwhelming resolution options dropdown)
    BIMClashProperties.selected_clash_group = EnumProperty(
        name="Clash Group",
        description="Select a clash group to preview and analyze resolution options",
        items=lambda self, context: get_clash_groups(context),
        default=0
    )

    # Feedback panel
    BIMClashProperties.show_feedback_panel = BoolProperty(
        name="Show Feedback Panel",
        description="Show feedback panel for resolution quality tracking",
        default=False
    )

    BIMClashProperties.resolution_rating = IntProperty(
        name="Resolution Rating",
        description="Quality rating of the resolution (1-5 stars)",
        default=3,
        min=1,
        max=5
    )

    BIMClashProperties.actual_hours = FloatProperty(
        name="Actual Hours",
        description="Actual hours spent on resolution implementation",
        default=0.0,
        min=0.0,
        soft_max=100.0
    )

    BIMClashProperties.variance_notes = StringProperty(
        name="Variance Notes",
        description="Optional notes about why actual time differed from estimate",
        default=""
    )


def unregister_federation_properties():
    """
    Unregister federation analysis properties from BIMClashProperties.
    Called from federation/__init__.py during module unregistration.
    """
    from bonsai.bim.module.clash.prop import BIMClashProperties

    # Remove all custom properties
    props_to_remove = [
        'discipline_a',
        'discipline_b',
        'clash_preset',
        'discipline_tolerance',
        'discipline_clash_candidates',
        'active_discipline_clash_index',
        'discipline_clash_loaded',
        'gizmo_visualization_enabled',
        'current_clash_index',
        'lod_visualization_mode',
        'bbox_visualization_enabled',
        'bbox_element_limit',
        'show_lod_stats',
        'active_preset_name',
        'show_learned_estimates',
        'clash_groups_analyzed',
        'selected_clash_group',
        'show_feedback_panel',
        'resolution_rating',
        'actual_hours',
        'variance_notes',
    ]

    for prop_name in props_to_remove:
        if hasattr(BIMClashProperties, prop_name):
            delattr(BIMClashProperties, prop_name)


# ============================================================================
# Structural Works Properties
# ============================================================================


class BIMStructuralProperties(PropertyGroup):
    """Properties for structural rebar and concrete module"""

    project_name: StringProperty(
        name="Project Name",
        description="Project name for BOQ reports",
        default="Terminal 1 Expansion Project"
    )

    is_airport_grade: BoolProperty(
        name="Airport Grade Standards",
        description="Use heavier reinforcement for airport infrastructure (Grade 40 concrete)",
        default=False
    )

    concrete_grade: EnumProperty(
        name="Concrete Grade",
        description="Concrete strength grade",
        items=[
            ('GRADE_25', "Grade 25", "25 MPa characteristic strength"),
            ('GRADE_30', "Grade 30", "30 MPa characteristic strength (standard)"),
            ('GRADE_35', "Grade 35", "35 MPa characteristic strength"),
            ('GRADE_40', "Grade 40", "40 MPa characteristic strength (airport grade)"),
            ('GRADE_45', "Grade 45", "45 MPa characteristic strength"),
        ],
        default='GRADE_30'
    )

    exposure_class: EnumProperty(
        name="Exposure Class",
        description="Environmental exposure classification (MS 1347:2020)",
        items=[
            ('XC1', "XC1", "Dry or permanently wet (interior)"),
            ('XC3', "XC3", "Moderate humidity (exterior, standard)"),
            ('XD1', "XD1", "Moderate chloride exposure (airport grade)"),
            ('XS1', "XS1", "Marine exposure - airborne salt"),
        ],
        default='XC3'
    )

    rebar_generated: BoolProperty(
        name="Rebar Generated",
        description="Indicates if rebar has been generated for structural elements",
        default=False
    )

    last_generation_time: StringProperty(
        name="Last Generation",
        description="Timestamp of last rebar generation",
        default=""
    )

    last_boq_export: StringProperty(
        name="Last BOQ Export",
        description="Timestamp of last structural BOQ export",
        default=""
    )

    last_boq_file: StringProperty(
        name="Last BOQ File",
        description="Path to most recent structural BOQ Excel file",
        default="",
        subtype='FILE_PATH'
    )

    show_structural_settings: BoolProperty(
        name="Show Settings",
        description="Show/hide structural settings panel",
        default=False
    )
