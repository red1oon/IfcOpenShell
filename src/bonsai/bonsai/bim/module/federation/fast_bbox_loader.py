"""
Fast BBox Loader - Direct R-tree Reading
========================================

Loads bounding boxes DIRECTLY from R-tree spatial index.
No geometry processing, no convex hulls - just read coordinates and create cubes.

Target: 2 seconds for 49K elements
"""

import bpy
import sqlite3
import time
from mathutils import Vector

# Discipline color palette (bright distinct colors for easy identification)
DISCIPLINE_COLORS = {
    'ARC': (0.7, 0.7, 0.7),      # Light gray (architecture/structure)
    'STR': (0.5, 0.5, 0.5),      # Dark gray (structural)
    'ACMV': (0.3, 0.7, 1.0),     # Sky blue (air conditioning)
    'ELEC': (1.0, 0.9, 0.2),     # Yellow (electrical)
    'FP': (1.0, 0.2, 0.2),       # Red (fire protection)
    'LPG': (1.0, 0.5, 0.0),      # Orange (LPG/gas)
    'SP': (0.2, 0.8, 0.2),       # Green (sanitary/plumbing)
    'CW': (0.3, 0.3, 0.9),       # Blue (chilled water)
    'DEFAULT': (0.6, 0.6, 0.6),  # Medium gray (unknown)
}

def create_bbox_mesh(name, minX, maxX, minY, maxY, minZ, maxZ):
    """
    Creates a simple cube mesh from bbox coordinates.
    Fast: just 8 vertices and 12 triangles.
    """
    # Create mesh
    mesh = bpy.data.meshes.new(name)

    # 8 vertices of the bounding box
    vertices = [
        (minX, minY, minZ),  # 0: bottom-left-front
        (maxX, minY, minZ),  # 1: bottom-right-front
        (maxX, maxY, minZ),  # 2: bottom-right-back
        (minX, maxY, minZ),  # 3: bottom-left-back
        (minX, minY, maxZ),  # 4: top-left-front
        (maxX, minY, maxZ),  # 5: top-right-front
        (maxX, maxY, maxZ),  # 6: top-right-back
        (minX, maxY, maxZ),  # 7: top-left-back
    ]

    # 12 triangles (2 per face, 6 faces)
    faces = [
        # Bottom
        (0, 1, 2), (0, 2, 3),
        # Top
        (4, 7, 6), (4, 6, 5),
        # Front
        (0, 4, 5), (0, 5, 1),
        # Back
        (2, 6, 7), (2, 7, 3),
        # Left
        (0, 3, 7), (0, 7, 4),
        # Right
        (1, 5, 6), (1, 6, 2),
    ]

    mesh.from_pydata(vertices, [], faces)
    mesh.update()

    return mesh


def load_bboxes_from_rtree(db_path):
    """
    Loads bounding boxes directly from R-tree spatial index.

    Returns:
        Dictionary mapping discipline -> [(guid, minX, maxX, minY, maxY, minZ, maxZ), ...]
    """
    print("\n" + "="*80)
    print("FAST BBOX LOADER - Reading R-tree spatial index")
    print("="*80)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get bbox coordinates + metadata in one query
    query = """
    SELECT
        m.guid,
        m.discipline,
        m.ifc_class,
        r.minX, r.maxX, r.minY, r.maxY, r.minZ, r.maxZ
    FROM elements_rtree r
    JOIN elements_meta m ON r.id = m.id
    ORDER BY m.discipline, m.ifc_class
    """

    print(f"Querying R-tree for bbox coordinates...")
    start = time.time()
    cursor.execute(query)
    rows = cursor.fetchall()
    elapsed = time.time() - start

    print(f"✓ Retrieved {len(rows):,} bboxes from database in {elapsed:.2f}s")
    conn.close()

    # Organize by discipline
    by_discipline = {}
    for guid, discipline, ifc_class, minX, maxX, minY, maxY, minZ, maxZ in rows:
        if discipline not in by_discipline:
            by_discipline[discipline] = []
        by_discipline[discipline].append((guid, ifc_class, minX, maxX, minY, maxY, minZ, maxZ))

    print(f"\nOrganized into {len(by_discipline)} disciplines:")
    for disc, items in sorted(by_discipline.items()):
        print(f"  {disc}: {len(items):,} elements")

    return by_discipline


def get_discipline_material(discipline):
    """
    Gets or creates a material for a specific discipline.
    Uses color coding for easy visual identification.
    """
    mat_name = f"BBox_{discipline}"
    mat = bpy.data.materials.get(mat_name)

    if not mat:
        mat = bpy.data.materials.new(mat_name)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        nodes.clear()

        # Get color for this discipline
        color = DISCIPLINE_COLORS.get(discipline, DISCIPLINE_COLORS['DEFAULT'])

        # Simple emission shader for wireframe
        emission = nodes.new('ShaderNodeEmission')
        emission.inputs[0].default_value = (*color, 1.0)  # Discipline color
        emission.inputs[1].default_value = 0.6  # Moderate emission for visibility

        output = nodes.new('ShaderNodeOutputMaterial')
        mat.node_tree.links.new(emission.outputs[0], output.inputs[0])

    return mat


def create_bbox_objects(by_discipline, batch_size=1000):
    """
    Creates bbox objects in viewport, organized by discipline collections.

    Args:
        by_discipline: Dictionary from load_bboxes_from_rtree()
        batch_size: Elements to process before progress update
    """
    print("\n" + "="*80)
    print("Creating bbox objects in viewport")
    print("="*80)

    # Create main federation collection
    if "Federation" in bpy.data.collections:
        main_coll = bpy.data.collections["Federation"]
    else:
        main_coll = bpy.data.collections.new("Federation")
        bpy.context.scene.collection.children.link(main_coll)

    total_elements = sum(len(items) for items in by_discipline.values())
    created = 0
    start = time.time()

    # Create collections and objects for each discipline
    for discipline, items in sorted(by_discipline.items()):
        # Create discipline collection
        disc_coll_name = f"Geometry1st{discipline}"
        if disc_coll_name in bpy.data.collections:
            disc_coll = bpy.data.collections[disc_coll_name]
        else:
            disc_coll = bpy.data.collections.new(disc_coll_name)
            main_coll.children.link(disc_coll)

        # Get material for this discipline
        mat = get_discipline_material(discipline)
        color = DISCIPLINE_COLORS.get(discipline, DISCIPLINE_COLORS['DEFAULT'])
        print(f"\nProcessing {discipline}: {len(items):,} elements (color: RGB{color})")

        for guid, ifc_class, minX, maxX, minY, maxY, minZ, maxZ in items:
            # Create bbox mesh
            mesh_name = f"{guid}_bbox"
            mesh = create_bbox_mesh(mesh_name, minX, maxX, minY, maxY, minZ, maxZ)

            # Create object
            obj = bpy.data.objects.new(guid, mesh)
            obj["ifc_class"] = ifc_class
            obj["discipline"] = discipline
            obj["is_bbox"] = True

            # Assign discipline-specific material
            if len(obj.data.materials) == 0:
                obj.data.materials.append(mat)
            else:
                obj.data.materials[0] = mat

            # Set display mode to wireframe
            obj.display_type = 'WIRE'

            # Link to collection
            disc_coll.objects.link(obj)

            created += 1

            # Progress update
            if created % batch_size == 0:
                elapsed = time.time() - start
                rate = created / elapsed
                remaining = (total_elements - created) / rate
                print(f"  {created:,}/{total_elements:,} objects ({rate:.1f}/s, {remaining:.1f}s remaining)")

    elapsed = time.time() - start
    print(f"\n✓ Created {created:,} bbox objects in {elapsed:.2f}s ({created/elapsed:.1f} objects/s)")

    # Update scene
    print("\nUpdating viewport...")
    update_start = time.time()
    bpy.context.view_layer.update()
    update_time = time.time() - update_start
    print(f"✓ Viewport updated in {update_time:.2f}s")

    return created


def load_federation_bboxes(db_path):
    """
    Main entry point: Load federation as fast bounding boxes.

    This is the 2-second "Preview" mode for MEP engineers.
    """
    overall_start = time.time()

    # Step 0: Register federation index for MEP routing/clashing
    print("\n" + "="*80)
    print("Registering federation index for MEP operations...")
    print("="*80)

    if not hasattr(bpy.types.WindowManager, 'federation_index'):
        from .spatial_index import FederationIndex
        index = FederationIndex(db_path)
        index.build()
        bpy.types.WindowManager.federation_index = index

        # Update properties
        if hasattr(bpy.context, 'scene') and hasattr(bpy.context.scene, 'BIMFederationProperties'):
            props = bpy.context.scene.BIMFederationProperties
            stats = index.get_statistics()
            props.index_loaded = True
            props.total_elements = stats.get('total_elements', 0)
            props.loaded_disciplines = stats.get('total_disciplines', 0)
        print(f"✓ Federation index registered: routing and clashing enabled\n")
    else:
        print("✓ Federation index already registered\n")

    # Step 1: Read bboxes from R-tree
    by_discipline = load_bboxes_from_rtree(db_path)

    # Step 2: Create bbox objects
    created = create_bbox_objects(by_discipline)

    overall_elapsed = time.time() - overall_start

    print("\n" + "="*80)
    print("FAST BBOX LOADING COMPLETE")
    print("="*80)
    print(f"Total elements: {created:,}")
    print(f"Total time: {overall_elapsed:.2f}s")
    print(f"Average: {overall_elapsed*1000/created:.2f}ms per element")
    print("="*80)
    print("\n✓ MEP engineers can now work (routing, clashing, spatial queries)")
    print("✓ Use 'Load Full Geometry' button for detailed visualization\n")

    return created


if __name__ == "__main__":
    # Test with sample database
    db_path = "/home/red1/Documents/bonsai/DatabaseFiles/sample_extracted_v3.db"
    load_federation_bboxes(db_path)
