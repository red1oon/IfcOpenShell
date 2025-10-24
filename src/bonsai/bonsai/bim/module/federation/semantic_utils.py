"""
Semantic Utilities for BBox-First Federation Architecture
----------------------------------------------------------
Provides IFC class to semantic type mapping, profile dimension extraction,
and material assignment for procedural proxy generation.

Part of Phase 1: BBox Semantic Geometry System
"""

import json
from typing import Dict, Optional, Tuple, Any


# IFC Class to Semantic Type Mapping
# Maps 35+ IFC classes to 8 semantic types for procedural generation
# Following industry standard BIM classification practices
SEMANTIC_TYPE_MAPPING = {
    # Architecture
    'IfcDoor': 'door',
    'IfcDoorStandardCase': 'door',
    'IfcWindow': 'window',
    'IfcWindowStandardCase': 'window',
    'IfcWall': 'wall',
    'IfcWallStandardCase': 'wall',
    'IfcSlab': 'slab',
    'IfcRoof': 'slab',
    'IfcCurtainWall': 'wall',
    'IfcCovering': 'slab',  # Floor/wall coverings (carpets, tiles, cladding)
    'IfcStairFlight': 'slab',  # Stairs (treated as horizontal slabs)
    'IfcRampFlight': 'slab',  # Ramps (treated as sloped slabs)
    'IfcRailing': 'equipment',  # Railings (linear equipment)
    'IfcFurnishingElement': 'equipment',  # Furniture (desks, chairs, cabinets)

    # Structure
    'IfcBeam': 'beam',
    'IfcBeamStandardCase': 'beam',
    'IfcColumn': 'column',
    'IfcColumnStandardCase': 'column',
    'IfcMember': 'beam',  # Structural members (treat as beams)
    'IfcPlate': 'slab',  # Structural plates (thin slabs)

    # MEP - ACMV (Heating, Ventilation, Air Conditioning)
    'IfcDuctSegment': 'duct',
    'IfcDuctFitting': 'duct',
    'IfcAirTerminal': 'equipment',  # Diffusers, grilles, VAV boxes
    'IfcUnitaryEquipment': 'equipment',  # AHUs, FCUs, chillers

    # MEP - Fire Protection
    'IfcPipeSegment': 'pipe',
    'IfcPipeFitting': 'pipe',
    'IfcFireSuppressionTerminal': 'equipment',  # Sprinkler heads, fire extinguishers

    # MEP - Plumbing & Sanitary
    'IfcSanitaryTerminal': 'equipment',  # Toilets, sinks, urinals
    'IfcFlowTerminal': 'equipment',  # Generic terminals (includes FP equipment when discipline=FP)

    # MEP - Electrical
    'IfcCableSegment': 'conduit',
    'IfcCableCarrierSegment': 'conduit',
    'IfcCableCarrierFitting': 'conduit',
    'IfcElectricDistributionBoard': 'equipment',  # Switchboards, DBs
    'IfcLightFixture': 'equipment',  # Light fittings

    # MEP - Generic Flow (pipes, ducts, cables across disciplines)
    'IfcFlowFitting': 'pipe',  # Elbows, tees, crosses (contextual: pipe for FP/SP, duct for ACMV)
    'IfcFlowController': 'equipment',  # Valves, dampers, switches (control devices)

    # Proxy/Generic elements
    'IfcBuildingElementProxy': 'equipment',  # Generic proxy elements
    'IfcElementAssembly': 'equipment',  # Assembled elements

    # Default fallback
    'DEFAULT': 'equipment'
}


# Material Library Mapping (semantic_type + discipline → material_id)
MATERIAL_MAPPING = {
    ('door', 'ARCHITECTURE'): 1,  # DOOR_WOOD
    ('window', 'ARCHITECTURE'): 2,  # WINDOW_GLASS
    ('wall', 'ARCHITECTURE'): 7,  # WALL_GENERIC
    ('slab', 'STRUCTURE'): 3,  # CONCRETE_SLAB
    ('beam', 'STRUCTURE'): 4,  # STEEL_BEAM
    ('column', 'STRUCTURE'): 4,  # STEEL_BEAM
    ('duct', 'ACMV'): 5,  # DUCT_ACMV
    ('pipe', 'FP'): 6,  # PIPE_FP (Red)
    ('pipe', 'PLUMBING'): 8,  # PIPE_PLUMBING (Blue)
    ('conduit', 'ELEC'): 9,  # CONDUIT_ELEC (Yellow)
    ('equipment', None): 10,  # GENERIC_EQUIPMENT
}


def get_material_properties(ifc_class: str, discipline: str) -> Dict[str, Any]:
    """
    Get industry-standard material properties for an element.

    Uses SEMANTIC_MATERIAL_RULES for specific (IFC class, discipline) combinations,
    falls back to DISCIPLINE_MATERIAL_DEFAULTS for discipline-level defaults.

    Args:
        ifc_class: IFC class name (e.g., 'IfcPipeSegment', 'IfcDuctSegment')
        discipline: Discipline (e.g., 'FP', 'ACMV', 'ELEC', 'STRUCTURE')

    Returns:
        Dictionary with material properties:
        - material: Material type (steel, pvc, concrete, etc.)
        - base_color: RGBA tuple for Blender (0-1 range)
        - display_color: Hex color for UI/exports
        - finish: Finish type (painted, galvanized, insulated, etc.)
        - roughness: PBR roughness (0-1)
        - metallic: PBR metallic (0-1)
        - transparency: Optional transparency (0-1)
        - display_name: Human-readable name
        - assembly_details: Optional construction details dict
        - has_insulation: Boolean flag for insulation

    Example:
        >>> get_material_properties('IfcPipeSegment', 'FP')
        {
            'material': 'steel',
            'base_color': (0.8, 0.1, 0.1, 1.0),
            'display_color': '#CC0000',
            'finish': 'painted',
            'roughness': 0.4,
            'metallic': 0.8,
            'has_insulation': False,
            'display_name': 'FP Steel Pipe (Painted)',
            'assembly_details': {'wall_schedule': 'Schedule 40', 'coating': 'red_enamel'}
        }
    """
    # Try exact (IFC class, discipline) match first
    key = (ifc_class, discipline)
    if key in SEMANTIC_MATERIAL_RULES:
        return SEMANTIC_MATERIAL_RULES[key].copy()

    # Fall back to discipline default
    if discipline in DISCIPLINE_MATERIAL_DEFAULTS:
        return DISCIPLINE_MATERIAL_DEFAULTS[discipline].copy()

    # Final fallback: generic default
    return DISCIPLINE_MATERIAL_DEFAULTS['DEFAULT'].copy()


def get_semantic_type(ifc_class: str) -> str:
    """
    Map IFC class name to semantic type.

    Args:
        ifc_class: IFC class name (e.g., 'IfcDoor', 'IfcDuctSegment')

    Returns:
        Semantic type: door/window/beam/column/slab/duct/pipe/conduit/equipment
    """
    return SEMANTIC_TYPE_MAPPING.get(ifc_class, SEMANTIC_TYPE_MAPPING['DEFAULT'])


def determine_dominant_axis(bbox: Tuple[float, float, float, float, float, float]) -> Optional[str]:
    """
    Determine dominant axis for linear elements (beams, columns, ducts, pipes, conduits).

    Args:
        bbox: Bounding box (min_x, min_y, min_z, max_x, max_y, max_z)

    Returns:
        'X', 'Y', 'Z', or None if no clear dominant axis
    """
    min_x, min_y, min_z, max_x, max_y, max_z = bbox

    dim_x = max_x - min_x
    dim_y = max_y - min_y
    dim_z = max_z - min_z

    # Dominant axis must be 2x longer than others
    if dim_z > max(dim_x, dim_y) * 2:
        return 'Z'
    elif dim_x > max(dim_y, dim_z) * 2:
        return 'X'
    elif dim_y > max(dim_x, dim_z) * 2:
        return 'Y'

    return None


def extract_profile_dimensions(bbox: Tuple[float, float, float, float, float, float],
                                semantic_type: str,
                                dominant_axis: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    """
    Extract profile width and height from bounding box.

    For MEP elements (duct, pipe, conduit), this is the cross-section dimensions.
    For beams/columns, this is the profile dimensions.

    Args:
        bbox: Bounding box (min_x, min_y, min_z, max_x, max_y, max_z)
        semantic_type: Semantic type from get_semantic_type()
        dominant_axis: Dominant axis from determine_dominant_axis()

    Returns:
        Tuple of (profile_width, profile_height) in mm, or (None, None)
    """
    min_x, min_y, min_z, max_x, max_y, max_z = bbox

    dim_x = max_x - min_x
    dim_y = max_y - min_y
    dim_z = max_z - min_z

    dimensions = [dim_x, dim_y, dim_z]

    if semantic_type in ['duct', 'pipe', 'conduit', 'beam', 'column']:
        # For linear elements, cross-section is the 2 smallest dimensions
        sorted_dims = sorted(dimensions)

        if semantic_type == 'pipe' or semantic_type == 'conduit':
            # Circular profile: diameter = smallest dimension
            profile_width = sorted_dims[0]
            profile_height = sorted_dims[0]  # Same as width for circular
        else:
            # Rectangular profile: width x height
            profile_width = sorted_dims[0]
            profile_height = sorted_dims[1]

        return (profile_width, profile_height)

    # For other types, use bbox dimensions as-is
    return (dim_x, dim_y)


def get_material_id(semantic_type: str, discipline: str) -> int:
    """
    Get material library ID for semantic type and discipline.

    Args:
        semantic_type: Semantic type (door, window, duct, etc.)
        discipline: Discipline (ARCHITECTURE, STRUCTURE, ACMV, FP, PLUMBING, ELEC, etc.)

    Returns:
        Material ID (1-10), defaults to 10 (generic equipment)
    """
    # Try exact match first
    key = (semantic_type, discipline)
    if key in MATERIAL_MAPPING:
        return MATERIAL_MAPPING[key]

    # Try with None discipline (generic)
    key = (semantic_type, None)
    if key in MATERIAL_MAPPING:
        return MATERIAL_MAPPING[key]

    # Default: generic equipment
    return 10


def extract_semantic_metadata(guid: str,
                               ifc_class: str,
                               discipline: str,
                               bbox: Tuple[float, float, float, float, float, float]) -> Dict[str, Any]:
    """
    Extract complete semantic metadata for an element.

    This is the main function called during federation preprocessing.

    Args:
        guid: Element GUID
        ifc_class: IFC class name
        discipline: Discipline (ARCHITECTURE, STRUCTURE, ACMV, FP, etc.)
        bbox: Bounding box (min_x, min_y, min_z, max_x, max_y, max_z)

    Returns:
        Dictionary with semantic metadata for database insertion
    """
    semantic_type = get_semantic_type(ifc_class)
    dominant_axis = determine_dominant_axis(bbox)
    profile_width, profile_height = extract_profile_dimensions(bbox, semantic_type, dominant_axis)
    material_id = get_material_id(semantic_type, discipline)

    # Determine subtype (basic heuristic, can be enhanced)
    subtype = None
    if semantic_type == 'duct':
        subtype = 'rectangular' if profile_width != profile_height else 'square'
    elif semantic_type == 'pipe' or semantic_type == 'conduit':
        subtype = 'circular'

    return {
        'guid': guid,
        'semantic_type': semantic_type,
        'subtype': subtype,
        'material_id': material_id,
        'dominant_axis': dominant_axis,
        'profile_width': profile_width,
        'profile_height': profile_height,
        'wall_thickness': None,  # Can be enhanced later
        'has_opening': False,  # Can be enhanced later
        'connects_to': None,  # Can be enhanced later
        'flow_direction': None,  # Can be enhanced later
    }


# Pre-defined material library data (will be inserted into database)
MATERIAL_LIBRARY_DATA = [
    {
        'id': 1,
        'name': 'DOOR_WOOD',
        'category': 'architecture',
        'generation_rules': json.dumps({"type": "rectangle_with_handle", "handle_height": 1000}),
        'base_color': '#8B4513',
        'metallic': 0.0,
        'roughness': 0.8,
        'transparency': 0.0,
        'emissive': 0.0
    },
    {
        'id': 2,
        'name': 'WINDOW_GLASS',
        'category': 'architecture',
        'generation_rules': json.dumps({"type": "glazing_with_frame", "frame_width": 50}),
        'base_color': '#87CEEB',
        'metallic': 0.0,
        'roughness': 0.1,
        'transparency': 0.7,
        'emissive': 0.0
    },
    {
        'id': 3,
        'name': 'CONCRETE_SLAB',
        'category': 'structure',
        'generation_rules': json.dumps({"type": "flat_plane"}),
        'base_color': '#808080',
        'metallic': 0.0,
        'roughness': 0.9,
        'transparency': 0.0,
        'emissive': 0.0
    },
    {
        'id': 4,
        'name': 'STEEL_BEAM',
        'category': 'structure',
        'generation_rules': json.dumps({"type": "i_beam_extrusion"}),
        'base_color': '#C0C0C0',
        'metallic': 0.8,
        'roughness': 0.3,
        'transparency': 0.0,
        'emissive': 0.0
    },
    {
        'id': 5,
        'name': 'DUCT_ACMV',
        'category': 'mep',
        'generation_rules': json.dumps({"type": "rectangular_extrusion"}),
        'base_color': '#00BFFF',
        'metallic': 0.5,
        'roughness': 0.4,
        'transparency': 0.0,
        'emissive': 0.0
    },
    {
        'id': 6,
        'name': 'PIPE_FP',
        'category': 'mep',
        'generation_rules': json.dumps({"type": "circular_extrusion", "add_flow_arrow": True}),
        'base_color': '#FF0000',
        'metallic': 0.6,
        'roughness': 0.3,
        'transparency': 0.0,
        'emissive': 0.0
    },
    {
        'id': 7,
        'name': 'WALL_GENERIC',
        'category': 'architecture',
        'generation_rules': json.dumps({"type": "vertical_plane"}),
        'base_color': '#F5F5DC',
        'metallic': 0.0,
        'roughness': 0.8,
        'transparency': 0.0,
        'emissive': 0.0
    },
    {
        'id': 8,
        'name': 'PIPE_PLUMBING',
        'category': 'mep',
        'generation_rules': json.dumps({"type": "circular_extrusion"}),
        'base_color': '#0000FF',
        'metallic': 0.6,
        'roughness': 0.3,
        'transparency': 0.0,
        'emissive': 0.0
    },
    {
        'id': 9,
        'name': 'CONDUIT_ELEC',
        'category': 'mep',
        'generation_rules': json.dumps({"type": "circular_extrusion"}),
        'base_color': '#FFFF00',
        'metallic': 0.4,
        'roughness': 0.4,
        'transparency': 0.0,
        'emissive': 0.0
    },
    {
        'id': 10,
        'name': 'GENERIC_EQUIPMENT',
        'category': 'equipment',
        'generation_rules': json.dumps({"type": "box"}),
        'base_color': '#A9A9A9',
        'metallic': 0.2,
        'roughness': 0.6,
        'transparency': 0.0,
        'emissive': 0.0
    },
]


# Industry-Standard Material Inference Rules
# Maps (IFC class, discipline) → complete material specification
# Provides "finished engineering look" with professional appearance
SEMANTIC_MATERIAL_RULES = {
    # MEP - Fire Protection Pipes (Red steel, painted)
    ('IfcPipeSegment', 'FP'): {
        'material': 'steel',
        'base_color': (0.8, 0.1, 0.1, 1.0),  # Red (international FP standard)
        'display_color': '#CC0000',
        'finish': 'painted',
        'roughness': 0.4,
        'metallic': 0.8,
        'has_insulation': False,
        'display_name': 'FP Steel Pipe (Painted)',
        'assembly_details': {'wall_schedule': 'Schedule 40', 'coating': 'red_enamel'}
    },
    ('IfcPipeFitting', 'FP'): {
        'material': 'steel',
        'base_color': (0.8, 0.1, 0.1, 1.0),
        'display_color': '#CC0000',
        'finish': 'painted',
        'roughness': 0.4,
        'metallic': 0.8,
        'has_insulation': False,
        'display_name': 'FP Steel Fitting (Painted)',
        'assembly_details': {'type': 'threaded', 'coating': 'red_enamel'}
    },

    # MEP - ACMV Pipes (Blue steel, insulated)
    ('IfcPipeSegment', 'ACMV'): {
        'material': 'steel',
        'base_color': (0.2, 0.5, 0.8, 1.0),  # Blue (chilled water)
        'display_color': '#3385CC',
        'finish': 'insulated',
        'roughness': 0.6,  # Insulation texture
        'metallic': 0.2,   # Insulation visible, not steel
        'has_insulation': True,
        'display_name': 'ACMV Chilled Water Pipe (Insulated)',
        'assembly_details': {'insulation_thickness': 25, 'insulation_type': 'armaflex'}
    },
    ('IfcPipeFitting', 'ACMV'): {
        'material': 'steel',
        'base_color': (0.2, 0.5, 0.8, 1.0),
        'display_color': '#3385CC',
        'finish': 'insulated',
        'roughness': 0.6,
        'metallic': 0.2,
        'has_insulation': True,
        'display_name': 'ACMV Chilled Water Fitting (Insulated)',
        'assembly_details': {'insulation_thickness': 25, 'insulation_type': 'armaflex'}
    },

    # MEP - Plumbing/Sanitary Pipes (Gray PVC)
    ('IfcPipeSegment', 'SP'): {
        'material': 'pvc',
        'base_color': (0.5, 0.5, 0.5, 1.0),  # Gray PVC
        'display_color': '#808080',
        'finish': 'smooth_plastic',
        'roughness': 0.3,
        'metallic': 0.0,
        'has_insulation': False,
        'display_name': 'Sanitary PVC Pipe',
        'assembly_details': {'material_type': 'upvc', 'joint': 'solvent_weld'}
    },
    ('IfcPipeFitting', 'SP'): {
        'material': 'pvc',
        'base_color': (0.5, 0.5, 0.5, 1.0),
        'display_color': '#808080',
        'finish': 'smooth_plastic',
        'roughness': 0.3,
        'metallic': 0.0,
        'has_insulation': False,
        'display_name': 'Sanitary PVC Fitting',
        'assembly_details': {'material_type': 'upvc', 'joint': 'solvent_weld'}
    },

    # MEP - ACMV Ducts (Galvanized steel, silver/gray)
    ('IfcDuctSegment', 'ACMV'): {
        'material': 'galvanized_steel',
        'base_color': (0.7, 0.7, 0.75, 1.0),  # Silver/gray metallic
        'display_color': '#B0B0C0',
        'finish': 'galvanized',
        'roughness': 0.5,
        'metallic': 0.9,
        'has_insulation': True,  # External insulation common
        'display_name': 'ACMV Galvanized Duct',
        'assembly_details': {'gauge': 'G24', 'insulation_thickness': 25}
    },
    ('IfcDuctFitting', 'ACMV'): {
        'material': 'galvanized_steel',
        'base_color': (0.7, 0.7, 0.75, 1.0),
        'display_color': '#B0B0C0',
        'finish': 'galvanized',
        'roughness': 0.5,
        'metallic': 0.9,
        'has_insulation': True,
        'display_name': 'ACMV Galvanized Fitting',
        'assembly_details': {'gauge': 'G24', 'type': 'welded_seam'}
    },

    # MEP - Electrical Conduit (Orange PVC or steel)
    ('IfcCableCarrierSegment', 'ELEC'): {
        'material': 'pvc',
        'base_color': (1.0, 0.6, 0.0, 1.0),  # Orange (electrical warning color)
        'display_color': '#FF9900',
        'finish': 'smooth_plastic',
        'roughness': 0.3,
        'metallic': 0.0,
        'has_insulation': False,
        'display_name': 'Electrical PVC Conduit',
        'assembly_details': {'material_type': 'pvc_heavy_duty', 'ip_rating': 'IP65'}
    },
    ('IfcCableSegment', 'ELEC'): {
        'material': 'copper',
        'base_color': (0.9, 0.5, 0.2, 1.0),  # Copper color
        'display_color': '#E68A00',
        'finish': 'bare_metal',
        'roughness': 0.2,
        'metallic': 0.95,
        'has_insulation': True,  # Cable insulation
        'display_name': 'Electrical Cable',
        'assembly_details': {'conductor': 'copper', 'insulation': 'xlpe'}
    },

    # Structure - Steel Beams (Gray steel, painted/bare)
    ('IfcBeam', 'STRUCTURE'): {
        'material': 'steel',
        'base_color': (0.6, 0.6, 0.65, 1.0),  # Gray steel
        'display_color': '#999999',
        'finish': 'painted',
        'roughness': 0.4,
        'metallic': 0.8,
        'has_insulation': False,
        'display_name': 'Structural Steel Beam',
        'assembly_details': {'profile': 'i_beam', 'coating': 'intumescent'}
    },
    ('IfcColumn', 'STRUCTURE'): {
        'material': 'steel',
        'base_color': (0.6, 0.6, 0.65, 1.0),
        'display_color': '#999999',
        'finish': 'painted',
        'roughness': 0.4,
        'metallic': 0.8,
        'has_insulation': False,
        'display_name': 'Structural Steel Column',
        'assembly_details': {'profile': 'h_column', 'coating': 'intumescent'}
    },

    # Structure - Concrete Elements (Gray concrete, rough)
    ('IfcSlab', 'STRUCTURE'): {
        'material': 'concrete',
        'base_color': (0.5, 0.5, 0.5, 1.0),  # Medium gray
        'display_color': '#808080',
        'finish': 'concrete',
        'roughness': 0.9,
        'metallic': 0.0,
        'has_insulation': False,
        'display_name': 'Concrete Slab',
        'assembly_details': {'grade': 'C30', 'finish': 'smooth_trowel'}
    },

    # Architecture - Walls (Beige/white plaster)
    ('IfcWall', 'ARCHITECTURE'): {
        'material': 'plaster',
        'base_color': (0.95, 0.95, 0.9, 1.0),  # Off-white
        'display_color': '#F5F5E6',
        'finish': 'painted',
        'roughness': 0.8,
        'metallic': 0.0,
        'has_insulation': False,
        'display_name': 'Interior Wall (Painted)',
        'assembly_details': {'finish': 'emulsion_paint', 'substrate': 'gypsum_board'}
    },

    # Architecture - Doors (Wood finish, brown)
    ('IfcDoor', 'ARCHITECTURE'): {
        'material': 'wood',
        'base_color': (0.55, 0.35, 0.2, 1.0),  # Medium brown wood
        'display_color': '#8B5A32',
        'finish': 'varnished',
        'roughness': 0.6,
        'metallic': 0.0,
        'has_insulation': False,
        'display_name': 'Timber Door (Varnished)',
        'assembly_details': {'material': 'solid_core', 'hardware': 'lever_handle'}
    },

    # Architecture - Windows (Clear glass with aluminum frame)
    ('IfcWindow', 'ARCHITECTURE'): {
        'material': 'glass',
        'base_color': (0.8, 0.9, 1.0, 0.3),  # Light blue, transparent
        'display_color': '#CCEEFF',
        'finish': 'glazed',
        'roughness': 0.05,
        'metallic': 0.0,
        'has_insulation': False,
        'transparency': 0.7,
        'display_name': 'Aluminum Window (Glazed)',
        'assembly_details': {'glazing': 'double_glazed', 'frame': 'aluminum'}
    },

    # MEP - Equipment (Generic gray/beige equipment)
    ('IfcUnitaryEquipment', 'ACMV'): {
        'material': 'sheet_metal',
        'base_color': (0.85, 0.85, 0.8, 1.0),  # Light gray/beige
        'display_color': '#D9D9CC',
        'finish': 'powder_coated',
        'roughness': 0.5,
        'metallic': 0.3,
        'has_insulation': True,
        'display_name': 'ACMV Equipment (AHU/FCU)',
        'assembly_details': {'casing': 'powder_coated_steel', 'insulation': 'internal'}
    },
    ('IfcAirTerminal', 'ACMV'): {
        'material': 'aluminum',
        'base_color': (0.9, 0.9, 0.9, 1.0),  # Light silver
        'display_color': '#E6E6E6',
        'finish': 'anodized',
        'roughness': 0.3,
        'metallic': 0.7,
        'has_insulation': False,
        'display_name': 'Air Terminal (Diffuser/Grille)',
        'assembly_details': {'material': 'anodized_aluminum', 'type': 'swirl_diffuser'}
    },
}

# Discipline fallback defaults (when specific IFC class not in rules)
DISCIPLINE_MATERIAL_DEFAULTS = {
    'FP': {
        'material': 'steel',
        'base_color': (0.8, 0.1, 0.1, 1.0),
        'display_color': '#CC0000',
        'finish': 'painted',
        'roughness': 0.4,
        'metallic': 0.8,
        'display_name': 'FP Element'
    },
    'ACMV': {
        'material': 'galvanized_steel',
        'base_color': (0.7, 0.7, 0.75, 1.0),
        'display_color': '#B0B0C0',
        'finish': 'galvanized',
        'roughness': 0.5,
        'metallic': 0.9,
        'display_name': 'ACMV Element'
    },
    'ELEC': {
        'material': 'pvc',
        'base_color': (1.0, 0.6, 0.0, 1.0),
        'display_color': '#FF9900',
        'finish': 'smooth_plastic',
        'roughness': 0.3,
        'metallic': 0.0,
        'display_name': 'Electrical Element'
    },
    'SP': {
        'material': 'pvc',
        'base_color': (0.5, 0.5, 0.5, 1.0),
        'display_color': '#808080',
        'finish': 'smooth_plastic',
        'roughness': 0.3,
        'metallic': 0.0,
        'display_name': 'Sanitary Element'
    },
    'STRUCTURE': {
        'material': 'steel',
        'base_color': (0.6, 0.6, 0.65, 1.0),
        'display_color': '#999999',
        'finish': 'painted',
        'roughness': 0.4,
        'metallic': 0.8,
        'display_name': 'Structural Element'
    },
    'ARCHITECTURE': {
        'material': 'plaster',
        'base_color': (0.95, 0.95, 0.9, 1.0),
        'display_color': '#F5F5E6',
        'finish': 'painted',
        'roughness': 0.8,
        'metallic': 0.0,
        'display_name': 'Architectural Element'
    },
    'DEFAULT': {
        'material': 'generic',
        'base_color': (0.7, 0.7, 0.7, 1.0),
        'display_color': '#B3B3B3',
        'finish': 'matte',
        'roughness': 0.6,
        'metallic': 0.2,
        'display_name': 'Generic Element'
    },
}
