"""
Shape Template Library for Semantic Geometry Generation
Phase 3: Database-driven procedural geometry (no IFC files)

Generates Blender mesh geometry from semantic metadata:
- Level 1 (Semantic Proxies): Basic shapes (cylinders, boxes)
- Level 2 (Full Geometry): Detailed shapes (flanges, dampers, fittings)
"""

import bpy
import bmesh
from mathutils import Vector, Matrix
from math import pi, cos, sin
from typing import Tuple, Optional, Dict, List


# ============================================================================
# DISCIPLINE COLORS (from bbox_visualization.py)
# ============================================================================

DISCIPLINE_COLORS = {
    'ACMV': (0.0, 0.75, 1.0, 1.0),      # Cyan/Blue
    'FP': (1.0, 0.0, 0.0, 1.0),          # Red
    'ELEC': (1.0, 1.0, 0.0, 1.0),        # Yellow
    'CW': (0.0, 1.0, 1.0, 1.0),          # Cyan
    'SP': (1.0, 0.5, 0.0, 1.0),          # Orange
    'ARC': (0.5, 0.5, 0.5, 0.7),         # Gray
    'ARCHITECTURE': (0.5, 0.5, 0.5, 0.7),
    'STR': (0.6, 0.4, 0.2, 1.0),         # Brown
    'STRUCTURE': (0.6, 0.4, 0.2, 1.0),
    'DEFAULT': (0.7, 0.7, 0.7, 0.5),     # Light gray
}


# ============================================================================
# LEVEL 1: BASIC SHAPES (Semantic Proxies)
# ============================================================================

def create_cylinder_basic(radius: float, length: float, segments: int = 12) -> bmesh.types.BMesh:
    """
    Create basic cylinder mesh (for round ducts, pipes).

    Args:
        radius: Cylinder radius (mm)
        length: Cylinder length along Z-axis (mm)
        segments: Number of circular segments (lower = faster)

    Returns:
        BMesh with cylinder geometry
    """
    bm = bmesh.new()

    # Create two circles at Z=0 and Z=length
    verts_bottom = []
    verts_top = []

    for i in range(segments):
        angle = (2 * pi * i) / segments
        x = radius * cos(angle)
        y = radius * sin(angle)

        verts_bottom.append(bm.verts.new((x, y, 0)))
        verts_top.append(bm.verts.new((x, y, length)))

    # Create side faces
    for i in range(segments):
        next_i = (i + 1) % segments
        bm.faces.new([
            verts_bottom[i],
            verts_bottom[next_i],
            verts_top[next_i],
            verts_top[i]
        ])

    # Create end caps
    bm.faces.new(verts_bottom)
    bm.faces.new(reversed(verts_top))

    bm.normal_update()
    return bm


def create_box_basic(width: float, height: float, length: float) -> bmesh.types.BMesh:
    """
    Create basic box mesh (for rectangular ducts, cable trays).

    Args:
        width: Box width (X-axis, mm)
        height: Box height (Y-axis, mm)
        length: Box length (Z-axis, mm)

    Returns:
        BMesh with box geometry
    """
    bm = bmesh.new()

    # Create 8 corner vertices
    w2, h2 = width / 2, height / 2
    corners = [
        bm.verts.new((-w2, -h2, 0)),       # 0: bottom-front-left
        bm.verts.new((w2, -h2, 0)),        # 1: bottom-front-right
        bm.verts.new((w2, h2, 0)),         # 2: bottom-back-right
        bm.verts.new((-w2, h2, 0)),        # 3: bottom-back-left
        bm.verts.new((-w2, -h2, length)),  # 4: top-front-left
        bm.verts.new((w2, -h2, length)),   # 5: top-front-right
        bm.verts.new((w2, h2, length)),    # 6: top-back-right
        bm.verts.new((-w2, h2, length)),   # 7: top-back-left
    ]

    # Create 6 faces
    bm.faces.new([corners[0], corners[1], corners[2], corners[3]])  # Bottom
    bm.faces.new([corners[4], corners[7], corners[6], corners[5]])  # Top
    bm.faces.new([corners[0], corners[4], corners[5], corners[1]])  # Front
    bm.faces.new([corners[2], corners[6], corners[7], corners[3]])  # Back
    bm.faces.new([corners[0], corners[3], corners[7], corners[4]])  # Left
    bm.faces.new([corners[1], corners[5], corners[6], corners[2]])  # Right

    bm.normal_update()
    return bm


def create_elbow_basic(radius: float, bend_radius: float, angle: float = 90, segments: int = 12) -> bmesh.types.BMesh:
    """
    Create basic elbow/bend mesh (for pipe/duct elbows).

    Args:
        radius: Pipe/duct radius (mm)
        bend_radius: Radius of the bend centerline (mm)
        angle: Bend angle in degrees (default 90°)
        segments: Number of segments around pipe and along bend

    Returns:
        BMesh with elbow geometry
    """
    bm = bmesh.new()

    # Simplified elbow: create bent cylinder
    # For basic version, create straight cylinder (full elbow implementation is complex)
    # This is a placeholder - full implementation would create actual bent geometry

    length = (angle / 180) * pi * bend_radius  # Arc length

    # Create cylinder along Z-axis (basic approximation)
    for i in range(segments):
        angle_i = (2 * pi * i) / segments
        x = radius * cos(angle_i)
        y = radius * sin(angle_i)

        for j in range(segments + 1):
            z = (length * j) / segments
            bm.verts.new((x, y, z))

    bm.normal_update()
    return bm


# ============================================================================
# LEVEL 2: DETAILED SHAPES (Full Geometry)
# ============================================================================

def create_cylinder_detailed(radius: float, length: float, has_flanges: bool = True,
                            segments: int = 24) -> bmesh.types.BMesh:
    """
    Create detailed cylinder with flanges (for realistic pipes).

    Args:
        radius: Cylinder radius (mm)
        length: Cylinder length (mm)
        has_flanges: Add flanges at both ends
        segments: Number of circular segments (higher = smoother)

    Returns:
        BMesh with detailed cylinder + flanges
    """
    bm = bmesh.new()

    # Main cylinder body
    flange_width = radius * 0.3 if has_flanges else 0
    flange_thickness = radius * 0.15 if has_flanges else 0

    body_start = flange_thickness if has_flanges else 0
    body_end = length - flange_thickness if has_flanges else length

    # Create cylinder body
    verts_bottom = []
    verts_top = []

    for i in range(segments):
        angle = (2 * pi * i) / segments
        x = radius * cos(angle)
        y = radius * sin(angle)

        verts_bottom.append(bm.verts.new((x, y, body_start)))
        verts_top.append(bm.verts.new((x, y, body_end)))

    # Create side faces
    for i in range(segments):
        next_i = (i + 1) % segments
        bm.faces.new([
            verts_bottom[i],
            verts_bottom[next_i],
            verts_top[next_i],
            verts_top[i]
        ])

    # Add flanges if requested
    if has_flanges:
        flange_radius = radius + flange_width

        # Bottom flange
        for i in range(segments):
            angle = (2 * pi * i) / segments
            x = flange_radius * cos(angle)
            y = flange_radius * sin(angle)
            bm.verts.new((x, y, 0))
            bm.verts.new((x, y, flange_thickness))

        # Top flange
        for i in range(segments):
            angle = (2 * pi * i) / segments
            x = flange_radius * cos(angle)
            y = flange_radius * sin(angle)
            bm.verts.new((x, y, length - flange_thickness))
            bm.verts.new((x, y, length))

    # Create end caps
    bm.faces.new(verts_bottom)
    bm.faces.new(reversed(verts_top))

    bm.normal_update()
    return bm


def create_box_detailed(width: float, height: float, length: float,
                       has_damper: bool = False) -> bmesh.types.BMesh:
    """
    Create detailed rectangular duct with optional damper.

    Args:
        width: Duct width (mm)
        height: Duct height (mm)
        length: Duct length (mm)
        has_damper: Add damper blade in middle

    Returns:
        BMesh with detailed duct geometry
    """
    bm = bmesh.new()

    # Create basic box
    w2, h2 = width / 2, height / 2

    # Main duct body (hollow box with wall thickness)
    wall_thickness = min(width, height) * 0.05  # 5% wall thickness

    # Outer box
    outer_corners = [
        (-w2, -h2, 0), (w2, -h2, 0), (w2, h2, 0), (-w2, h2, 0),
        (-w2, -h2, length), (w2, -h2, length), (w2, h2, length), (-w2, h2, length)
    ]

    # Inner box (for hollow duct)
    wi2, hi2 = (width - 2*wall_thickness) / 2, (height - 2*wall_thickness) / 2
    inner_corners = [
        (-wi2, -hi2, 0), (wi2, -hi2, 0), (wi2, hi2, 0), (-wi2, hi2, 0),
        (-wi2, -hi2, length), (wi2, -hi2, length), (wi2, hi2, length), (-wi2, hi2, length)
    ]

    # Create vertices
    outer_verts = [bm.verts.new(v) for v in outer_corners]
    inner_verts = [bm.verts.new(v) for v in inner_corners]

    # Create outer faces
    bm.faces.new([outer_verts[0], outer_verts[1], outer_verts[2], outer_verts[3]])  # Bottom
    bm.faces.new([outer_verts[4], outer_verts[7], outer_verts[6], outer_verts[5]])  # Top
    bm.faces.new([outer_verts[0], outer_verts[4], outer_verts[5], outer_verts[1]])  # Front
    bm.faces.new([outer_verts[2], outer_verts[6], outer_verts[7], outer_verts[3]])  # Back
    bm.faces.new([outer_verts[0], outer_verts[3], outer_verts[7], outer_verts[4]])  # Left
    bm.faces.new([outer_verts[1], outer_verts[5], outer_verts[6], outer_verts[2]])  # Right

    # Add damper if requested (simple blade across middle)
    if has_damper:
        damper_z = length / 2
        damper_thickness = wall_thickness

        # Create damper blade vertices
        damper_verts = [
            bm.verts.new((-w2, -damper_thickness/2, damper_z)),
            bm.verts.new((w2, -damper_thickness/2, damper_z)),
            bm.verts.new((w2, damper_thickness/2, damper_z)),
            bm.verts.new((-w2, damper_thickness/2, damper_z)),
        ]
        bm.faces.new(damper_verts)

    bm.normal_update()
    return bm


def create_tee_detailed(radius: float, segments: int = 16) -> bmesh.types.BMesh:
    """
    Create detailed pipe tee fitting.

    Args:
        radius: Pipe radius (mm)
        segments: Number of circular segments

    Returns:
        BMesh with tee fitting geometry
    """
    bm = bmesh.new()

    # Simplified tee: three cylinders meeting at right angles
    # Main run: along Z-axis
    length = radius * 4

    # Create main cylinder
    for i in range(segments):
        angle = (2 * pi * i) / segments
        x = radius * cos(angle)
        y = radius * sin(angle)

        bm.verts.new((x, y, 0))
        bm.verts.new((x, y, length))

    # Branch: along X-axis at Z = length/2
    branch_z = length / 2
    for i in range(segments):
        angle = (2 * pi * i) / segments
        y = radius * cos(angle)
        z = radius * sin(angle) + branch_z

        bm.verts.new((0, y, z))
        bm.verts.new((length/2, y, z))

    bm.normal_update()
    return bm


# ============================================================================
# SHAPE FACTORY (Selects appropriate template based on semantics)
# ============================================================================

def create_shape_from_semantics(
    ifc_class: str,
    profile_type: str,
    dimensions: Dict[str, float],
    detail_level: str = 'basic'
) -> Optional[bmesh.types.BMesh]:
    """
    Create procedural geometry based on semantic metadata.

    Args:
        ifc_class: IFC class name (e.g., 'IfcDuct', 'IfcPipeSegment')
        profile_type: Profile type (e.g., 'CIRCULAR', 'RECTANGULAR')
        dimensions: Dict with 'width', 'height', 'radius', 'length' (in mm)
        detail_level: 'basic' (Semantic Proxies) or 'detailed' (Full Geometry)

    Returns:
        BMesh with generated geometry, or None if unsupported
    """
    # Default length if not specified
    if 'length' not in dimensions or dimensions['length'] is None:
        dimensions['length'] = 1000.0  # Default 1 meter

    # DUCTS
    if 'Duct' in ifc_class:
        if profile_type == 'CIRCULAR':
            radius = dimensions.get('radius', 150.0)  # Default 300mm diameter
            length = dimensions['length']

            if detail_level == 'detailed':
                return create_cylinder_detailed(radius, length, has_flanges=False, segments=24)
            else:
                return create_cylinder_basic(radius, length, segments=12)

        elif profile_type == 'RECTANGULAR':
            width = dimensions.get('width', 600.0)
            height = dimensions.get('height', 400.0)
            length = dimensions['length']

            if detail_level == 'detailed':
                return create_box_detailed(width, height, length, has_damper=True)
            else:
                return create_box_basic(width, height, length)

    # PIPES
    elif 'Pipe' in ifc_class:
        if 'Fitting' in ifc_class:
            # Pipe fittings (elbows, tees, etc.)
            radius = dimensions.get('radius', 50.0)  # Default 100mm diameter

            if detail_level == 'detailed':
                return create_tee_detailed(radius, segments=16)
            else:
                return create_elbow_basic(radius, bend_radius=radius*1.5, segments=8)

        else:
            # Straight pipe segments
            radius = dimensions.get('radius', 50.0)
            length = dimensions['length']

            if detail_level == 'detailed':
                return create_cylinder_detailed(radius, length, has_flanges=True, segments=24)
            else:
                return create_cylinder_basic(radius, length, segments=12)

    # CABLES
    elif 'Cable' in ifc_class:
        radius = dimensions.get('radius', 10.0)  # Small cables
        length = dimensions['length']

        # Cables are always simple cylinders
        return create_cylinder_basic(radius, length, segments=8)

    # CABLE TRAYS / CONDUITS
    elif 'Tray' in ifc_class or 'Conduit' in ifc_class:
        width = dimensions.get('width', 200.0)
        height = dimensions.get('height', 100.0)
        length = dimensions['length']

        return create_box_basic(width, height, length)

    # Unsupported class - return None
    return None


def bmesh_to_mesh(bm: bmesh.types.BMesh, name: str) -> bpy.types.Mesh:
    """
    Convert BMesh to Blender mesh data.

    Args:
        bm: BMesh to convert
        name: Name for the mesh

    Returns:
        Blender mesh data
    """
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def create_material_for_discipline(discipline: str) -> bpy.types.Material:
    """
    Get or create material for discipline color.

    Args:
        discipline: Discipline name (e.g., 'ACMV', 'FP')

    Returns:
        Blender material with discipline color
    """
    mat_name = f"Federation_{discipline}"

    # Reuse existing material if available
    if mat_name in bpy.data.materials:
        return bpy.data.materials[mat_name]

    # Create new material
    mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True

    # Get color
    color = DISCIPLINE_COLORS.get(discipline, DISCIPLINE_COLORS['DEFAULT'])

    # Set principled BSDF color
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    if bsdf:
        bsdf.inputs['Base Color'].default_value = color
        bsdf.inputs['Metallic'].default_value = 0.3
        bsdf.inputs['Roughness'].default_value = 0.5

    return mat
