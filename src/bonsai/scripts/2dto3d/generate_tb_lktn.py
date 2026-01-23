"""
TB-LKTN House Generator for Blender
Reads TB_LKTN_INSTANCE.json and generates 3D geometry
"""

import bpy
import bmesh
import json
import os
from mathutils import Vector

# Path to instance data
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_FILE = os.path.join(SCRIPT_DIR, "config", "TB_LKTN_INSTANCE.json")

def clear_scene():
    """Remove all mesh objects from scene"""
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

def mm_to_m(val):
    """Convert millimeters to meters"""
    return val / 1000.0

def create_wall(name, start, end, thickness, height, is_interior=False):
    """Create a wall as a box between two points"""
    # Calculate wall direction and length
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = (dx**2 + dy**2)**0.5

    if length < 0.001:
        return None

    # Wall center
    cx = (start[0] + end[0]) / 2
    cy = (start[1] + end[1]) / 2
    cz = height / 2

    # Create mesh
    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz))
    wall = bpy.context.active_object
    wall.name = name

    # Scale to wall dimensions
    import math
    angle = math.atan2(dy, dx)

    wall.scale.x = length
    wall.scale.y = thickness
    wall.scale.z = height
    wall.rotation_euler.z = angle

    # Apply transforms
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    # Set material color
    mat = bpy.data.materials.new(name=f"mat_{name}")
    if is_interior:
        mat.diffuse_color = (0.9, 0.85, 0.8, 1.0)  # Light beige for interior
    else:
        mat.diffuse_color = (0.8, 0.75, 0.7, 1.0)  # Darker for exterior
    wall.data.materials.append(mat)

    return wall

def create_floor_slab(name, x_min, x_max, y_min, y_max, thickness=0.15):
    """Create a floor slab"""
    width = x_max - x_min
    depth = y_max - y_min
    cx = (x_min + x_max) / 2
    cy = (y_min + y_max) / 2
    cz = -thickness / 2

    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz))
    slab = bpy.context.active_object
    slab.name = name
    slab.scale = (width, depth, thickness)
    bpy.ops.object.transform_apply(scale=True)

    mat = bpy.data.materials.new(name=f"mat_{name}")
    mat.diffuse_color = (0.6, 0.6, 0.6, 1.0)
    slab.data.materials.append(mat)

    return slab

def create_roof_plane(name, vertices, material_color=(0.6, 0.3, 0.2, 1.0)):
    """Create a roof plane from vertices"""
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)

    bm = bmesh.new()

    # Add vertices
    bm_verts = []
    for v in vertices:
        bm_verts.append(bm.verts.new((v['x'], v['y'], v['z'])))

    bm.verts.ensure_lookup_table()

    # Create face
    if len(bm_verts) >= 3:
        bm.faces.new(bm_verts)

    bm.to_mesh(mesh)
    bm.free()

    # Add material
    mat = bpy.data.materials.new(name=f"mat_{name}")
    mat.diffuse_color = material_color
    obj.data.materials.append(mat)

    return obj

def create_opening(wall_obj, position, width, height, sill_height=0, opening_type="door"):
    """Cut an opening in a wall using boolean modifier"""
    # Create cutter box
    bpy.ops.mesh.primitive_cube_add(size=1)
    cutter = bpy.context.active_object
    cutter.name = f"cutter_{opening_type}"

    # Position and scale cutter
    cutter.location = (position[0], position[1], sill_height + height/2)
    cutter.scale = (width * 1.1, 0.3, height)
    bpy.ops.object.transform_apply(scale=True)

    # Apply boolean difference
    bool_mod = wall_obj.modifiers.new(name="Opening", type='BOOLEAN')
    bool_mod.operation = 'DIFFERENCE'
    bool_mod.object = cutter

    bpy.context.view_layer.objects.active = wall_obj
    bpy.ops.object.modifier_apply(modifier="Opening")

    # Delete cutter
    bpy.data.objects.remove(cutter)

def create_porch_columns(columns, height=2.7):
    """Create porch support columns"""
    for col in columns:
        pos = col['position_m']
        bpy.ops.mesh.primitive_cylinder_add(
            radius=0.1,
            depth=height,
            location=(pos[0], pos[1], height/2)
        )
        column = bpy.context.active_object
        column.name = col['id']

        mat = bpy.data.materials.new(name=f"mat_{col['id']}")
        mat.diffuse_color = (0.9, 0.9, 0.9, 1.0)
        column.data.materials.append(mat)

def generate_house(data):
    """Main function to generate the house from instance data"""

    # Get envelope dimensions
    envelope = data['envelope']
    floor = data['floor']

    # Convert to meters
    building_width = mm_to_m(envelope['building_width_mm'])
    building_depth = mm_to_m(envelope['building_depth_mm'])
    front_wall_y = mm_to_m(envelope['front_wall_y_mm'])
    back_wall_y = mm_to_m(envelope['back_wall_y_mm'])
    floor_height = mm_to_m(floor['floor_to_floor_mm'])

    print(f"Building: {building_width}m x {building_depth}m, height: {floor_height}m")

    # Create floor slab
    create_floor_slab("SLAB_GROUND", 0, building_width, front_wall_y, back_wall_y)

    # Create walls
    walls_created = {}
    for wall_data in data['walls']:
        wall_id = wall_data['id']
        geom = wall_data['geometry']

        start = (mm_to_m(geom['start_mm']['x']), mm_to_m(geom['start_mm']['y']))
        end = (mm_to_m(geom['end_mm']['x']), mm_to_m(geom['end_mm']['y']))
        thickness = mm_to_m(wall_data['thickness_mm'])
        height = mm_to_m(geom['height_mm'])
        is_interior = 'INT' in wall_id

        wall_obj = create_wall(wall_id, start, end, thickness, height, is_interior)
        if wall_obj:
            walls_created[wall_id] = wall_obj
            print(f"Created wall: {wall_id}")

    # Create roof
    roof_data = data['roof']['components']
    for roof_comp in roof_data:
        roof_id = roof_comp['id']

        if roof_comp['type'] == 'HIP':
            # Create each roof plane
            for plane in roof_comp['planes']:
                verts_m = []
                for v in plane['vertices_mm']:
                    verts_m.append({
                        'x': mm_to_m(v['x']),
                        'y': mm_to_m(v['y']),
                        'z': mm_to_m(v['z'])
                    })
                create_roof_plane(f"{roof_id}_{plane['name']}", verts_m)
                print(f"Created roof plane: {plane['name']}")

        elif roof_comp['type'] == 'LEAN_TO':
            # Create lean-to porch roof
            fp = roof_comp['footprint_mm']
            high_z = mm_to_m(roof_comp['high_edge_z_mm'])
            low_z = mm_to_m(roof_comp['low_edge_z_mm'])

            x_min = mm_to_m(fp['x_min'])
            x_max = mm_to_m(fp['x_max'])
            y_min = mm_to_m(fp['y_min'])
            y_max = mm_to_m(fp['y_max'])

            verts = [
                {'x': x_min, 'y': y_max, 'z': high_z},
                {'x': x_max, 'y': y_max, 'z': high_z},
                {'x': x_max, 'y': y_min, 'z': low_z},
                {'x': x_min, 'y': y_min, 'z': low_z}
            ]
            create_roof_plane(roof_id, verts, (0.5, 0.25, 0.15, 1.0))
            print(f"Created porch roof: {roof_id}")

    # Create porch floor
    porch_x_min = mm_to_m(4400)
    porch_x_max = mm_to_m(7600)
    porch_y_min = mm_to_m(0)
    porch_y_max = mm_to_m(2300)
    create_floor_slab("SLAB_PORCH", porch_x_min, porch_x_max, porch_y_min, porch_y_max, 0.1)

    # Create porch columns
    porch_roof = next((r for r in roof_data if r['type'] == 'LEAN_TO'), None)
    if porch_roof and 'columns' in data.get('infrastructure', {}):
        pass  # Columns data would go here

    # Simple porch columns at corners
    col_positions = [
        {'id': 'COL_1', 'position_m': [porch_x_min + 0.15, porch_y_min + 0.15, 0]},
        {'id': 'COL_2', 'position_m': [porch_x_max - 0.15, porch_y_min + 0.15, 0]}
    ]
    create_porch_columns(col_positions, 2.7)

    print("House generation complete!")

def main():
    """Main entry point"""
    print("=" * 50)
    print("TB-LKTN House Generator")
    print("=" * 50)

    # Clear existing objects
    clear_scene()

    # Load instance data
    print(f"Loading: {INSTANCE_FILE}")
    with open(INSTANCE_FILE, 'r') as f:
        data = json.load(f)

    print(f"Project: {data['project']['name']}")

    # Generate house
    generate_house(data)

    # Set view
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    space.shading.type = 'SOLID'
                    space.shading.color_type = 'MATERIAL'

    # Save file
    output_path = os.path.join(SCRIPT_DIR, "OUTPUT", "TB_LKTN_house.blend")
    bpy.ops.wm.save_as_mainfile(filepath=output_path)
    print(f"Saved to: {output_path}")

if __name__ == "__main__":
    main()
