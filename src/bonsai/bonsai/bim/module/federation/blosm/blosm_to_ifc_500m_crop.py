#!/usr/bin/env python3
"""
BLOSM to IFC Converter - 500m Crop Around Buildings
Crops geometry to 500m radius around buildings center

Usage: ~/blender-4.5.0/blender --background klang_buildings_blosm.blend --python blosm_to_ifc_500m_crop.py
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

OUTPUT_IFC = "/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_500m_crop.ifc"

# Crop settings - 500m radius around buildings (buildings center at ~(2, 1))
CROP_CENTER = (0, 0)  # Buildings are centered near origin
CROP_RADIUS = 500  # 500m radius = 1km diameter

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

def is_point_in_crop(x, y, center, radius):
    """Check if point is within crop radius"""
    dx = x - center[0]
    dy = y - center[1]
    distance = (dx*dx + dy*dy) ** 0.5
    return distance <= radius

def extract_and_crop_mesh(obj, center, radius):
    """Extract mesh and crop to radius, clipping edges at boundary"""

    # For BLOSM water objects, use original mesh (evaluated is empty)
    if 'water' in obj.name.lower():
        mesh_data = obj.data
    else:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        mesh_data = obj_eval.data

    # Create bmesh and triangulate first
    bm = bmesh.new()
    bm.from_mesh(mesh_data)
    bmesh.ops.triangulate(bm, faces=bm.faces)

    # Get world matrix
    matrix = obj.matrix_world

    # Convert to world coords and mark which vertices are inside
    vert_world_co = {}
    vert_inside = {}
    for v in bm.verts:
        world_co = matrix @ v.co
        vert_world_co[v] = (world_co.x, world_co.y, world_co.z)
        vert_inside[v] = is_point_in_crop(world_co.x, world_co.y, center, radius)

    # Classify faces
    faces_to_keep = []
    for f in bm.faces:
        inside_count = sum(1 for v in f.verts if vert_inside[v])

        if inside_count == 3:
            # All vertices inside - keep face as-is
            faces_to_keep.append(('full', f, f.verts[:]))
        elif inside_count > 0:
            # Partially inside - clip the face
            faces_to_keep.append(('partial', f, f.verts[:]))

    if not faces_to_keep:
        bm.free()
        return None, None

    # Build vertex list and face list
    new_vertices = []
    new_faces = []
    vert_remap = {}

    def add_vertex(world_co):
        """Add vertex and return its index"""
        if world_co not in vert_remap:
            vert_remap[world_co] = len(new_vertices)
            new_vertices.append(world_co)
        return vert_remap[world_co]

    def clip_edge(v1_co, v2_co, v1_inside, v2_inside):
        """Clip edge at circle boundary, return intersection point"""
        if v1_inside and v2_inside:
            return None  # Both inside, no clip needed

        x1, y1, z1 = v1_co
        x2, y2, z2 = v2_co

        # Parametric line: P(t) = P1 + t*(P2-P1), find t where distance = radius
        # Solve: (x1 + t*dx - cx)^2 + (y1 + t*dy - cy)^2 = r^2
        dx = x2 - x1
        dy = y2 - y1
        dz = z2 - z1
        cx, cy = center

        # Quadratic coefficients
        a = dx*dx + dy*dy
        b = 2*(dx*(x1-cx) + dy*(y1-cy))
        c = (x1-cx)*(x1-cx) + (y1-cy)*(y1-cy) - radius*radius

        discriminant = b*b - 4*a*c
        if discriminant < 0 or abs(a) < 1e-10:
            return None

        # Find t that gives intersection
        t1 = (-b - discriminant**0.5) / (2*a)
        t2 = (-b + discriminant**0.5) / (2*a)

        # Use t between 0 and 1
        t = None
        if 0 <= t1 <= 1:
            t = t1
        elif 0 <= t2 <= 1:
            t = t2

        if t is None:
            return None

        return (x1 + t*dx, y1 + t*dy, z1 + t*dz)

    for face_type, face, verts in faces_to_keep:
        if face_type == 'full':
            # All vertices inside - add as-is
            indices = [add_vertex(vert_world_co[v]) for v in verts]
            new_faces.append(indices)
        else:
            # Partial face - clip it
            # For simplicity with triangles, just keep if at least 2 vertices inside
            inside_verts = [v for v in verts if vert_inside[v]]
            if len(inside_verts) >= 2:
                # Keep the face with clipped edges
                clipped_indices = []
                for i, v in enumerate(verts):
                    v_next = verts[(i+1) % len(verts)]
                    v_co = vert_world_co[v]
                    v_next_co = vert_world_co[v_next]
                    v_in = vert_inside[v]
                    v_next_in = vert_inside[v_next]

                    if v_in:
                        clipped_indices.append(add_vertex(v_co))

                    # Check if edge crosses boundary
                    if v_in != v_next_in:
                        clip_point = clip_edge(v_co, v_next_co, v_in, v_next_in)
                        if clip_point:
                            clipped_indices.append(add_vertex(clip_point))

                if len(clipped_indices) >= 3:
                    new_faces.append(clipped_indices)

    bm.free()

    if not new_vertices or not new_faces:
        return None, None

    return new_vertices, new_faces

def main():
    print("\n" + "="*60)
    print("BLOSM TO IFC CONVERTER - 500m CROP")
    print("="*60)
    print(f"Crop center: {CROP_CENTER}")
    print(f"Crop radius: {CROP_RADIUS}m")

    # Create IFC file
    print("\n[1] Creating IFC structure...")
    ifc = ifcopenshell.api.run("project.create_file", version="IFC4")

    project = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcProject", name="Klang River 500m Section")
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
    site = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcSite", name="Sungai Klang 500m")
    building = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcBuilding", name="River Context")
    storey = ifcopenshell.api.run("root.create_entity", ifc, ifc_class="IfcBuildingStorey", name="Ground")

    ifcopenshell.api.run("aggregate.assign_object", ifc, products=[site], relating_object=project)
    ifcopenshell.api.run("aggregate.assign_object", ifc, products=[building], relating_object=site)
    ifcopenshell.api.run("aggregate.assign_object", ifc, products=[storey], relating_object=building)

    # Process objects
    print("\n[2] Converting and cropping objects...")
    stats = {'water': 0, 'building': 0, 'road': 0, 'terrain': 0, 'skipped': 0}

    for obj in bpy.data.objects:
        if obj.type not in ['MESH']:
            continue
        if obj.name in ['Camera', 'Light', 'Cube'] or obj.name.startswith('profile_'):
            continue
        if not obj.data.vertices or not obj.data.polygons:
            continue

        category = classify_object(obj.name)
        if not category:
            print(f"  ? Skipping unknown: {obj.name}")
            stats['skipped'] += 1
            continue

        ifc_class, predefined_type, object_type = CLASSIFICATION[category]

        try:
            print(f"  Processing {obj.name}...")
            vertices, faces = extract_and_crop_mesh(obj, CROP_CENTER, CROP_RADIUS)

            if not vertices or not faces:
                print(f"    WARNING: No geometry in crop area")
                stats['skipped'] += 1
                continue

            # For water, add thickness
            if category == 'water':
                print(f"    Adding 10cm thickness to water...")
                original_vert_count = len(vertices)
                bottom_verts = [(v[0], v[1], v[2] - 0.10) for v in vertices]
                vertices.extend(bottom_verts)

                new_faces = []
                for face in faces:
                    # Bottom face (reversed)
                    bottom_face = [i + original_vert_count for i in reversed(face)]
                    new_faces.append(bottom_face)

                    # Side walls
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

            if hasattr(element, 'PredefinedType'):
                element.PredefinedType = predefined_type
            if hasattr(element, 'ObjectType'):
                element.ObjectType = object_type

            # Create mesh representation
            representation = ifcopenshell.api.run(
                "geometry.add_mesh_representation", ifc,
                context=body_context,
                vertices=[vertices],
                faces=[faces]
            )

            ifcopenshell.api.run(
                "geometry.assign_representation", ifc,
                product=element,
                representation=representation
            )

            container = site if category in ['water', 'terrain'] else storey
            ifcopenshell.api.run(
                "spatial.assign_container", ifc,
                products=[element],
                relating_structure=container
            )

            stats[category] += 1
            print(f"    OK: {len(vertices)} verts, {len(faces)} faces -> {ifc_class}")

        except Exception as e:
            print(f"    ERROR: {e}")
            import traceback
            traceback.print_exc()
            stats['skipped'] += 1

    # Save IFC
    print(f"\n[3] Saving IFC...")
    ifc.write(OUTPUT_IFC)

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
    print(f"Cropped to: {CROP_RADIUS}m radius around buildings")
    print("\n" + "="*60)

if __name__ == "__main__":
    main()
