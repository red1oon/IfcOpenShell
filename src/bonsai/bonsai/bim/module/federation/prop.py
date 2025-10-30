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
        preprocessing_in_progress: bool
        progress_json_path: str
        total_elements: int
        loaded_disciplines: str
        query_buffer_mm: int
        filter_by_discipline: bool
        active_disciplines: str
        show_statistics: bool
        show_advanced_settings: bool