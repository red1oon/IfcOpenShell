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
        description="Path to SQLite federation index database",
        subtype='FILE_PATH',
        default=""
    )
    
    index_loaded: BoolProperty(
        name="Index Loaded",
        description="Whether the federation spatial index is loaded in memory",
        default=False
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