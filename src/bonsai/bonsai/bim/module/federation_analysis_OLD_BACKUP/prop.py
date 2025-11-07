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
