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

import bpy
from pathlib import Path
from bpy.types import PropertyGroup
from bpy.props import (
    StringProperty,
    BoolProperty,
    IntProperty,
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
        show_advanced_settings: bool# Bonsai - OpenBIM Blender Add-on
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

from __future__ import annotations
import bpy
from bpy.props import (
    StringProperty,
    BoolProperty,
    FloatProperty,
    EnumProperty,
    IntProperty,
    CollectionProperty,
)
from bpy.types import PropertyGroup
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from mathutils import Vector


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
# via the register_federation_properties() function called from federation_analysis/__init__.py

def register_federation_properties():
    """
    Register federation analysis properties into the existing BIMClashProperties.
    Called from federation_analysis/__init__.py during module registration.
    """
    from bonsai.bim.module.clash.prop import BIMClashProperties

    # Discipline-based clash detection
    BIMClashProperties.discipline_a = EnumProperty(
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

    BIMClashProperties.discipline_b = EnumProperty(
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
        description="Clash tolerance in model units",
        default=0.01,
        min=0.0,
        soft_max=1.0,
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


def unregister_federation_properties():
    """
    Unregister federation analysis properties from BIMClashProperties.
    Called from federation_analysis/__init__.py during module unregistration.
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
    ]

    for prop_name in props_to_remove:
        if hasattr(BIMClashProperties, prop_name):
            delattr(BIMClashProperties, prop_name)
