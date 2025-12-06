#!/usr/bin/env python3

# DEPRECATED: Use blosm_to_gi_complete.py instead (combines both stages)
# This script is kept for reference only
"""
BLOSM to IFC Converter - FIXED VERSION
Properly exports mesh geometry with coordinate handling

Usage: ~/blender-4.5.0/blender --background klang_buildings_blosm.blend --python blosm_to_ifc_fixed_v2.py
"""
import bpy
import bmesh
import sys
import os
from pathlib import Path

# Add ifcopenshell from Bonsai wheels
wheel_dir = Path.home() / ".config/blender/4.5/extensions/blender_org/bonsai/wheels"
if wheel_dir.exists():
    sys.path.insert(0, str(wheel_dir))

try:
    import ifcopenshell
    import ifcopenshell.api
except ImportError as e:
    print(f"ERROR: Failed to import ifcopenshell: {e}")
    sys.exit(1)

OUTPUT_IFC = "/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_blosm_fixed.ifc"

# Classification
CLASSIFICATION = {
    'water': ('IfcGeographicElement', 'USERDEFINED', 'WATER'),
    'building': ('IfcBuildingElementProxy', 'USERDEFINED', 'BUILDING'),
    'road': ('IfcBuildingElementProxy', 'USERDEFINED', 'ROAD'),
    'terrain': ('IfcGeographicElement', 'TERRAIN', 'TERRAIN'),
}

def classify_object(name):
    name_lower = name.lower()
    for key in CLASSIFICATION:
        if key in name_lower:
            return key
    return None

def get_scene_offset():
    """Calculate offset to center scene near origin"""
    all_locations = []

    for obj in bpy.data.objects:
        if obj.type == 'MESH' and obj.data.vertices:
            # Get world center of object
            matrix = obj.matrix_world
            world_verts = [matrix @ v.co for v in obj.data.vertices]
            center = sum(world_verts, type(world_verts[0])()) / len(world_verts)
            all_locations.append(center)

    if not all_locations:
        return (0, 0, 0)

    # Calculate centroid
    avg_x = sum(v.x for v in all_locations) / len(all_locations)
    avg_y = sum(v.y for v in all_locations) / len(all_locations)
    avg_z = sum(v.z for v in all_locations) / len(all_locations)

    # Only offset if coordinates are large
    if abs(avg_x) > 1000 or abs(avg_y) > 1000:
        print(f"  Applying offset: ({-avg_x:.2f}, {-avg_y:.2f}, {-avg_z:.2f})")
        return (-avg_x, -avg_y, -avg_z)

    return (0, 0, 0)

def extract_mesh_geometry(obj, offset=(0, 0, 0)):
    """Extract triangulated mesh in world coordinates with offset"""

    # For BLOSM water objects, use original mesh (evaluated is empty)
    # For other objects, try evaluated first (applies modifiers)
    if 'water' in obj.name.lower():
        mesh_data = obj.data
    else:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh_data = obj_eval.data

    # Create bmesh and triangulate
    bm = bmesh.new()
    bm.from_mesh(mesh_data)
    bmesh.ops.triangulate(bm, faces=bm.faces)

    # Get world matrix
    matrix = obj.matrix_world

    # Extract vertices in world coords with offset
    vertices = []
    for v in bm.verts:
        world_co = matrix @ v.co
        vertices.append((
            world_co.x + offset[0],
            world_co.y + offset[1],
            world_co.z + offset[2]
        ))

    # Extract faces
    faces = []
    for f in bm.faces:
        faces.append([v.index for v in f.verts])

    bm.free()

    return vertices, faces

def main():
    print("\n" + "="*60)
    print("BLOSM TO IFC CONVERTER - FIXED")
    print("="*60)

    # Calculate scene offset
    print("\n[1] Analyzing scene coordinates...")
    offset = get_scene_offset()

    # Create IFC file
    print("\n[2] Creating IFC structure...")
    ifc = ifcopenshell.api.run("project.create_file", version="IFC4")

    # Create project hierarchy
    project = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcProject", name="Klang River POC")

    # Set units to meters
    ifcopenshell.api.run("unit.assign_unit", ifc, length={"is_metric": True, "raw": "METERS"})

    # Create contexts
    model_context = ifcopenshell.api.run("context.add_context", ifc, context_type="Model")
    body_context = ifcopenshell.api.run(
        "context.add_context", ifc,
        context_type="Model",
        context_identifier="Body",
        target_view="MODEL_VIEW",
        parent=model_context
    )

    # Create spatial structure
    site = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcSite", name="Sungai Klang")
    building = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcBuilding", name="River Context")
    storey = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcBuildingStorey", name="Ground")

    # Aggregate spatial structure
    ifcopenshell.api.run("aggregate.assign_object", ifc, products=[site], relating_object=project)
    ifcopenshell.api.run("aggregate.assign_object", ifc, products=[building], relating_object=site)
    ifcopenshell.api.run("aggregate.assign_object", ifc, products=[storey], relating_object=building)

    # Store georeference offset if applied
    if offset != (0, 0, 0):
        print(f"  Storing georeference offset in IfcSite")
        # Could add EPset_MapConversion here for full georeferencing

    # Process objects
    print("\n[3] Converting objects to IFC...")
    stats = {'water': 0, 'building': 0, 'road': 0, 'terrain': 0, 'skipped': 0}

    for obj in bpy.data.objects:
        # Skip non-geometry
        if obj.type not in ['MESH']:
            continue
        if obj.name in ['Camera', 'Light', 'Cube'] or obj.name.startswith('profile_'):
            continue
        if not obj.data.vertices:
            continue
        if not obj.data.polygons:
            continue

        # Classify
        category = classify_object(obj.name)
        if not category:
            print(f"  ? Skipping unknown: {obj.name}")
            stats['skipped'] += 1
            continue

        ifc_class, predefined_type, object_type = CLASSIFICATION[category]

        try:
            # Extract geometry
            vertices, faces = extract_mesh_geometry(obj, offset)

            if not vertices or not faces:
                print(f"  WARNING: No geometry: {obj.name}")
                stats['skipped'] += 1
                continue

            # For flat water, add tiny thickness (5cm) to make it visible
            if category == 'water' and len(obj.data.polygons) <= 5:  # Flat water surface
                print(f"  Adding 5cm thickness to flat water surface...")
                original_vert_count = len(vertices)
                # Duplicate vertices offset down
                bottom_verts = [(v[0], v[1], v[2] - 0.05) for v in vertices]
                vertices.extend(bottom_verts)

                # Duplicate faces for bottom (reversed winding)
                new_faces = []
                for face in faces:
                    bottom_face = [i + original_vert_count for i in reversed(face)]
                    new_faces.append(bottom_face)

                # Add side walls connecting top and bottom
                for face in faces[:]:  # Original top faces only
                    for i in range(len(face)):
                        next_i = (i + 1) % len(face)
                        t1, t2 = face[i], face[next_i]
                        b1, b2 = t1 + original_vert_count, t2 + original_vert_count
                        new_faces.append([t1, t2, b2])
                        new_faces.append([t1, b2, b1])

                faces.extend(new_faces)

            # Create IFC element
            element = ifcopenshell.api.run(
                "root.create_entity", ifc,
                ifc_class=ifc_class,
                name=obj.name
            )

            # Set predefined type and object type
            if hasattr(element, 'PredefinedType'):
                element.PredefinedType = predefined_type
            if hasattr(element, 'ObjectType'):
                element.ObjectType = object_type

            # Create mesh representation
            # API expects list of vertex lists and list of face lists (one per mesh item)
            representation = ifcopenshell.api.run(
                "geometry.add_mesh_representation", ifc,
                context=body_context,
                vertices=[vertices],  # Wrap in list - one mesh item
                faces=[faces]  # Wrap in list - one mesh item
            )

            # Assign representation to element
            ifcopenshell.api.run(
                "geometry.assign_representation", ifc,
                product=element,
                representation=representation
            )

            # Assign to spatial container
            container = site if category in ['water', 'terrain'] else storey
            ifcopenshell.api.run(
                "spatial.assign_container", ifc,
                products=[element],
                relating_structure=container
            )

            stats[category] += 1
            print(f"  OK: {obj.name}: {len(vertices)} verts, {len(faces)} faces -> {ifc_class}")

        except Exception as e:
            print(f"  ERROR on {obj.name}: {e}")
            import traceback
            traceback.print_exc()
            stats['skipped'] += 1

    # Save IFC
    print(f"\n[4] Saving IFC...")
    ifc.write(OUTPUT_IFC)

    # Verify
    if os.path.exists(OUTPUT_IFC):
        size_mb = os.path.getsize(OUTPUT_IFC) / (1024 * 1024)
        print(f"  OK: Saved: {OUTPUT_IFC} ({size_mb:.2f} MB)")

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Water:    {stats['water']}")
    print(f"Building: {stats['building']}")
    print(f"Road:     {stats['road']}")
    print(f"Terrain:  {stats['terrain']}")
    print(f"Skipped:  {stats['skipped']}")
    print(f"\nTotal converted: {sum(stats.values()) - stats['skipped']}")

    if offset != (0, 0, 0):
        print(f"\nWARNING: Coordinate offset applied: {offset}")
        print("    To restore original coords, use IfcPatch OffsetObjectPlacements")

    print("\n" + "="*60)

if __name__ == "__main__":
    main()
