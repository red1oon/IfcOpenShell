#!/usr/bin/env python3
"""
Diagnostic: Test if detailed geometry actually differs from basic geometry
Checks vertex counts, examines meshes, identifies which elements should be detailed
"""

import bpy
from collections import defaultdict

print("=" * 70)
print("GEOMETRY DETAIL LEVEL DIAGNOSTIC")
print("=" * 70)

# Expected vertex counts for templates
EXPECTED_VERTICES = {
    'cylinder_basic_12seg': 24,      # 12 segments * 2 circles
    'cylinder_detailed_24seg': 96,   # 24 segments * 4 (with flanges)
    'box_basic': 8,                  # Simple cube
    'box_detailed': 32,              # Box with damper details
}

# Find Federation collections
collections_found = []
for coll_name in ['Federation_Basic', 'Federation_Detailed']:
    if coll_name in bpy.data.collections:
        collections_found.append(coll_name)
        print(f"\n✅ Found collection: {coll_name}")

if not collections_found:
    print("\n❌ No Federation collections found!")
    print("   Enable Semantic Proxies or Full Geometry first")
    exit(1)

# Analyze each collection
for coll_name in collections_found:
    collection = bpy.data.collections[coll_name]
    objects = list(collection.objects)

    if not objects:
        print(f"\n⚠️  {coll_name} is empty")
        continue

    print(f"\n{'='*70}")
    print(f"ANALYZING: {coll_name}")
    print(f"{'='*70}")
    print(f"Total objects: {len(objects):,}")

    # Group by semantic type (from custom properties or IFC class)
    semantic_groups = defaultdict(list)
    vertex_counts = defaultdict(list)

    for obj in objects:
        # Get semantic info
        ifc_class = obj.get("ifc_class", "Unknown")
        discipline = obj.get("discipline", "Unknown")

        # Count vertices
        if obj.data and hasattr(obj.data, 'vertices'):
            vert_count = len(obj.data.vertices)
        else:
            vert_count = 0

        # Classify by IFC class
        semantic_groups[ifc_class].append(obj)
        vertex_counts[ifc_class].append(vert_count)

    # Report statistics
    print(f"\n📊 Element Distribution:")
    print(f"{'IFC Class':<30} {'Count':>8} {'Avg Vertices':>15}")
    print("-" * 70)

    for ifc_class in sorted(semantic_groups.keys(), key=lambda x: len(semantic_groups[x]), reverse=True):
        count = len(semantic_groups[ifc_class])
        avg_verts = sum(vertex_counts[ifc_class]) / len(vertex_counts[ifc_class])
        print(f"{ifc_class:<30} {count:>8,} {avg_verts:>15.1f}")

    # Identify elements that SHOULD be detailed
    print(f"\n🔍 Detail Level Analysis:")

    # Check specific IFC classes that should have detailed geometry
    detailed_expected = ['IfcFlowSegment', 'IfcFlowFitting', 'IfcFlowTerminal',
                        'IfcPipeSegment', 'IfcPipeFitting', 'IfcDuctSegment',
                        'IfcDuctFitting', 'IfcCableSegment']

    basic_expected = ['IfcSlab', 'IfcPlate', 'IfcBeam', 'IfcWall', 'IfcColumn',
                     'IfcWindow', 'IfcDoor', 'IfcBuildingElementProxy']

    for ifc_class in semantic_groups.keys():
        objs = semantic_groups[ifc_class]
        verts = vertex_counts[ifc_class]
        avg_verts = sum(verts) / len(verts)
        min_verts = min(verts)
        max_verts = max(verts)

        # Determine if this should be detailed
        should_be_detailed = any(pattern in ifc_class for pattern in detailed_expected)
        should_be_basic = any(pattern in ifc_class for pattern in basic_expected)

        if 'Detailed' in coll_name and should_be_detailed:
            # Check if detailed (should have more vertices)
            if avg_verts < 30:  # Threshold for basic vs detailed
                print(f"\n⚠️  {ifc_class}: Expected DETAILED but looks BASIC")
                print(f"   Count: {len(objs):,}, Avg vertices: {avg_verts:.1f}")
                print(f"   Range: {min_verts}-{max_verts} vertices")
                print(f"   Expected: >50 vertices for detailed geometry")
            else:
                print(f"\n✅ {ifc_class}: Correctly DETAILED")
                print(f"   Count: {len(objs):,}, Avg vertices: {avg_verts:.1f}")

        elif 'Detailed' in coll_name and should_be_basic:
            # Architectural elements - basic is OK
            print(f"\n✓  {ifc_class}: Basic geometry (architectural)")
            print(f"   Count: {len(objs):,}, Avg vertices: {avg_verts:.1f}")

    # Sample mesh inspection
    print(f"\n🔬 Sample Mesh Inspection:")
    print(f"{'Object':<40} {'IFC Class':<25} {'Vertices':>10}")
    print("-" * 70)

    sample_size = min(10, len(objects))
    for obj in objects[:sample_size]:
        ifc_class = obj.get("ifc_class", "Unknown")
        vert_count = len(obj.data.vertices) if obj.data and hasattr(obj.data, 'vertices') else 0
        obj_name = obj.name[:37] + "..." if len(obj.name) > 40 else obj.name
        print(f"{obj_name:<40} {ifc_class:<25} {vert_count:>10}")

# Summary
print(f"\n{'='*70}")
print("DIAGNOSTIC SUMMARY")
print(f"{'='*70}")

print(f"\nVertex Count Reference:")
print(f"  • Basic cylinder (12 seg):  24 vertices")
print(f"  • Detailed cylinder (24 seg + flanges): 96+ vertices")
print(f"  • Basic box: 8 vertices")
print(f"  • Detailed box (with damper): 32+ vertices")
print(f"  • Architectural elements (slabs, beams): 8 vertices (no detailed variant)")

print(f"\n{'='*70}")
