#!/usr/bin/env python3
"""
Test script: Compare Basic vs Detailed geometry modes
Enables both modes, collects statistics, and verifies differences
"""

import sys
import os

# Add Bonsai module path
bonsai_path = "/home/red1/Projects/IfcOpenShell/src/bonsai"
sys.path.insert(0, bonsai_path)

import bpy
from collections import defaultdict

# Import federation modules
from bonsai.bim.module.clash import semantic_visualization

# Database path
DB_PATH = "/home/red1/Documents/bonsai/federation_index.db"

# Expected vertex counts
EXPECTED_VERTICES = {
    'basic_cylinder_12seg': 24,      # 12 segments * 2 circles
    'detailed_cylinder_24seg': 96,   # 24 segments * 4 (with flanges)
    'basic_box': 8,                  # Simple cube
    'detailed_box': 32,              # Box with damper details
}

print("=" * 80)
print("DETAILED GEOMETRY COMPARISON TEST")
print("=" * 80)


def analyze_collection(collection_name):
    """Analyze a collection and return statistics"""
    if collection_name not in bpy.data.collections:
        return None

    collection = bpy.data.collections[collection_name]
    objects = list(collection.objects)

    if not objects:
        return None

    # Group by IFC class
    stats = {
        'total_objects': len(objects),
        'by_ifc_class': defaultdict(lambda: {'count': 0, 'vertices': []}),
        'total_vertices': 0,
        'avg_vertices': 0
    }

    for obj in objects:
        ifc_class = obj.get("ifc_class", "Unknown")
        vert_count = len(obj.data.vertices) if obj.data and hasattr(obj.data, 'vertices') else 0

        stats['by_ifc_class'][ifc_class]['count'] += 1
        stats['by_ifc_class'][ifc_class]['vertices'].append(vert_count)
        stats['total_vertices'] += vert_count

    stats['avg_vertices'] = stats['total_vertices'] / len(objects) if objects else 0

    # Calculate averages per class
    for ifc_class, data in stats['by_ifc_class'].items():
        data['avg_vertices'] = sum(data['vertices']) / len(data['vertices'])
        data['min_vertices'] = min(data['vertices'])
        data['max_vertices'] = max(data['vertices'])

    return stats


def print_stats(stats, mode_name):
    """Print statistics for a mode"""
    print(f"\n{'='*80}")
    print(f"{mode_name.upper()} MODE STATISTICS")
    print(f"{'='*80}")
    print(f"Total objects: {stats['total_objects']:,}")
    print(f"Total vertices: {stats['total_vertices']:,}")
    print(f"Average vertices per object: {stats['avg_vertices']:.1f}")

    print(f"\n{'IFC Class':<30} {'Count':>8} {'Avg Verts':>12} {'Min':>8} {'Max':>8}")
    print("-" * 80)

    # Sort by count
    sorted_classes = sorted(
        stats['by_ifc_class'].items(),
        key=lambda x: x[1]['count'],
        reverse=True
    )

    for ifc_class, data in sorted_classes[:15]:  # Top 15
        print(f"{ifc_class:<30} {data['count']:>8,} "
              f"{data['avg_vertices']:>12.1f} "
              f"{data['min_vertices']:>8} "
              f"{data['max_vertices']:>8}")


def compare_modes(basic_stats, detailed_stats):
    """Compare basic and detailed modes"""
    print(f"\n{'='*80}")
    print("MODE COMPARISON")
    print(f"{'='*80}")

    # Overall comparison
    print(f"\n📊 Overall Metrics:")
    print(f"{'Metric':<40} {'Basic':>15} {'Detailed':>15} {'Difference':>15}")
    print("-" * 80)

    print(f"{'Total objects':<40} {basic_stats['total_objects']:>15,} "
          f"{detailed_stats['total_objects']:>15,} "
          f"{detailed_stats['total_objects'] - basic_stats['total_objects']:>15,}")

    print(f"{'Total vertices':<40} {basic_stats['total_vertices']:>15,} "
          f"{detailed_stats['total_vertices']:>15,} "
          f"{detailed_stats['total_vertices'] - basic_stats['total_vertices']:>15,}")

    print(f"{'Average vertices/object':<40} {basic_stats['avg_vertices']:>15.1f} "
          f"{detailed_stats['avg_vertices']:>15.1f} "
          f"{detailed_stats['avg_vertices'] - basic_stats['avg_vertices']:>15.1f}")

    # Per-class comparison for MEP elements
    print(f"\n🔍 MEP Element Detail Analysis:")
    print(f"{'IFC Class':<30} {'Count':>8} {'Basic Avg':>12} {'Detail Avg':>12} {'Increase':>12}")
    print("-" * 80)

    mep_classes = ['IfcFlowFitting', 'IfcFlowTerminal', 'IfcFlowSegment',
                   'IfcDuctSegment', 'IfcPipeSegment', 'IfcFlowController']

    differences_found = False

    for ifc_class in mep_classes:
        if ifc_class in basic_stats['by_ifc_class'] and ifc_class in detailed_stats['by_ifc_class']:
            basic_avg = basic_stats['by_ifc_class'][ifc_class]['avg_vertices']
            detailed_avg = detailed_stats['by_ifc_class'][ifc_class]['avg_vertices']
            count = basic_stats['by_ifc_class'][ifc_class]['count']
            increase = detailed_avg - basic_avg

            status = "✅" if increase > 10 else "⚠️"
            print(f"{status} {ifc_class:<27} {count:>8,} "
                  f"{basic_avg:>12.1f} {detailed_avg:>12.1f} "
                  f"{increase:>12.1f}")

            if increase > 10:
                differences_found = True

    # Summary
    print(f"\n{'='*80}")
    print("TEST RESULT")
    print(f"{'='*80}")

    if differences_found:
        print("✅ PASS: Detailed mode creates more complex geometry for MEP elements")
    else:
        print("❌ FAIL: No significant difference between Basic and Detailed modes")

    vertex_increase = ((detailed_stats['total_vertices'] - basic_stats['total_vertices'])
                      / basic_stats['total_vertices'] * 100)
    print(f"\nOverall vertex count increase: {vertex_increase:.1f}%")

    if vertex_increase > 20:
        print("✅ Significant geometry detail improvement")
    elif vertex_increase > 5:
        print("⚠️  Modest geometry detail improvement")
    else:
        print("❌ Minimal geometry detail improvement")


# Phase 1: Enable Basic mode
print("\n" + "=" * 80)
print("PHASE 1: ENABLING SEMANTIC PROXIES (BASIC)")
print("=" * 80)

success, message = semantic_visualization.enable_semantic_visualization(
    DB_PATH,
    detail_level='basic',
    limit=5000  # Test with subset first
)

if not success:
    print(f"❌ Failed to enable basic mode: {message}")
    sys.exit(1)

print(f"✅ {message}")

# Analyze basic mode
basic_stats = analyze_collection("Federation_Basic")
if basic_stats:
    print_stats(basic_stats, "Basic")
else:
    print("❌ Failed to analyze Federation_Basic collection")
    sys.exit(1)

# Disable basic mode
print("\nDisabling basic mode...")
semantic_visualization.disable_semantic_visualization()

# Phase 2: Enable Detailed mode
print("\n" + "=" * 80)
print("PHASE 2: ENABLING FULL GEOMETRY (DETAILED)")
print("=" * 80)

success, message = semantic_visualization.enable_semantic_visualization(
    DB_PATH,
    detail_level='detailed',
    limit=5000  # Same subset
)

if not success:
    print(f"❌ Failed to enable detailed mode: {message}")
    sys.exit(1)

print(f"✅ {message}")

# Analyze detailed mode
detailed_stats = analyze_collection("Federation_Detailed")
if detailed_stats:
    print_stats(detailed_stats, "Detailed")
else:
    print("❌ Failed to analyze Federation_Detailed collection")
    sys.exit(1)

# Phase 3: Compare modes
compare_modes(basic_stats, detailed_stats)

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
