#!/usr/bin/env python3
"""
Shape Template Coverage Test
Checks if shape_templates.py covers all IFC classes in the database
"""

import sqlite3
import os

print("=" * 80)
print("SHAPE TEMPLATE COVERAGE TEST")
print("=" * 80)

db_path = os.path.expanduser("~/Documents/bonsai/federation_index.db")

if not os.path.exists(db_path):
    print(f"❌ Database not found: {db_path}")
    print("   Run preprocessing script first!")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# ============================================================================
# Get all IFC classes from database
# ============================================================================

print("\n" + "=" * 80)
print("DATABASE IFC CLASS INVENTORY")
print("=" * 80)

cursor.execute("""
    SELECT ifc_class, COUNT(*) as count
    FROM elements_meta
    GROUP BY ifc_class
    ORDER BY count DESC
""")

ifc_classes = cursor.fetchall()

print(f"\nFound {len(ifc_classes)} distinct IFC classes in database:")
print(f"\n{'IFC Class':<40} {'Count':<10} {'%':<8}")
print("-" * 60)

total_elements = sum(count for _, count in ifc_classes)

for ifc_class, count in ifc_classes:
    pct = (count / total_elements) * 100
    print(f"{ifc_class:<40} {count:<10,} {pct:<8.2f}%")

# ============================================================================
# Check semantic type coverage
# ============================================================================

print("\n" + "=" * 80)
print("SEMANTIC TYPE COVERAGE")
print("=" * 80)

cursor.execute("""
    SELECT semantic_type, COUNT(*) as count
    FROM element_semantics
    GROUP BY semantic_type
    ORDER BY count DESC
""")

semantic_types = cursor.fetchall()

print(f"\nFound {len(semantic_types)} distinct semantic types:")
print(f"\n{'Semantic Type':<30} {'Count':<10} {'%':<8}")
print("-" * 50)

for sem_type, count in semantic_types:
    pct = (count / total_elements) * 100
    print(f"{sem_type:<30} {count:<10,} {pct:<8.2f}%")

# ============================================================================
# Define known shape templates
# ============================================================================

print("\n" + "=" * 80)
print("SHAPE TEMPLATE MAPPING")
print("=" * 80)

# Based on shape_templates.py (check actual file for current mappings)
SHAPE_TEMPLATES = {
    # MEP - Pipes
    'IfcPipeSegment': 'cylinder',
    'IfcPipeFitting': 'cylinder',

    # MEP - Ducts
    'IfcDuctSegment': 'box',
    'IfcDuctFitting': 'box',

    # MEP - Cable Trays
    'IfcCableCarrierSegment': 'box',
    'IfcCableCarrierFitting': 'box',
    'IfcCableSegment': 'cylinder',

    # Equipment (simplified shapes)
    'IfcValve': 'valve',  # Custom valve shape
    'IfcPump': 'box',
    'IfcFan': 'box',
    'IfcAirTerminal': 'box',
    'IfcFireSuppressionTerminal': 'cylinder',

    # Architecture
    'IfcWall': 'box',
    'IfcBeam': 'box',
    'IfcColumn': 'box',
    'IfcSlab': 'box',
    'IfcRoof': 'box',
    'IfcDoor': 'box',
    'IfcWindow': 'box',
    'IfcStair': 'box',
    'IfcRailing': 'box',

    # Structure
    'IfcFooting': 'box',
    'IfcPile': 'cylinder',

    # Fallback
    'DEFAULT': 'bbox',  # Bounding box wireframe
}

print(f"\nDefined shape templates: {len(SHAPE_TEMPLATES)}")

# ============================================================================
# Coverage Analysis
# ============================================================================

print("\n" + "=" * 80)
print("COVERAGE ANALYSIS")
print("=" * 80)

covered_elements = 0
uncovered_elements = 0
uncovered_classes = []

print(f"\n{'IFC Class':<40} {'Count':<10} {'Template':<15} {'Status':<10}")
print("-" * 80)

for ifc_class, count in ifc_classes:
    if ifc_class in SHAPE_TEMPLATES:
        template = SHAPE_TEMPLATES[ifc_class]
        status = "✅ Covered"
        covered_elements += count
    else:
        template = "DEFAULT (bbox)"
        status = "⚠️  Missing"
        uncovered_elements += count
        uncovered_classes.append((ifc_class, count))

    print(f"{ifc_class:<40} {count:<10,} {template:<15} {status:<10}")

# ============================================================================
# Summary
# ============================================================================

print("\n" + "=" * 80)
print("COVERAGE SUMMARY")
print("=" * 80)

coverage_pct = (covered_elements / total_elements) * 100 if total_elements > 0 else 0

print(f"\n📊 STATISTICS:")
print(f"  Total elements:        {total_elements:,}")
print(f"  Covered elements:      {covered_elements:,} ({coverage_pct:.1f}%)")
print(f"  Uncovered elements:    {uncovered_elements:,} ({100-coverage_pct:.1f}%)")
print(f"  Template types:        {len(set(SHAPE_TEMPLATES.values()))}")

if uncovered_classes:
    print(f"\n⚠️  MISSING TEMPLATES ({len(uncovered_classes)} classes):")
    print(f"\n{'IFC Class':<40} {'Count':<10} {'Impact':<10}")
    print("-" * 60)

    for ifc_class, count in sorted(uncovered_classes, key=lambda x: x[1], reverse=True):
        impact_pct = (count / total_elements) * 100
        print(f"{ifc_class:<40} {count:<10,} {impact_pct:<10.2f}%")

print(f"\n✅ VERDICT:")
if coverage_pct > 95:
    print(f"  ✅ EXCELLENT coverage ({coverage_pct:.1f}%)")
    print(f"  ✅ Most elements will have proper shapes")
    print(f"  ✅ Missing classes can use bbox fallback")
elif coverage_pct > 80:
    print(f"  ✅ GOOD coverage ({coverage_pct:.1f}%)")
    print(f"  ⚠️  Consider adding templates for major missing classes")
elif coverage_pct > 50:
    print(f"  ⚠️  MODERATE coverage ({coverage_pct:.1f}%)")
    print(f"  ⚠️  Should add more templates before implementation")
else:
    print(f"  ❌ POOR coverage ({coverage_pct:.1f}%)")
    print(f"  ❌ Need to add many more templates")

print(f"\n💡 RECOMMENDATIONS:")
if uncovered_classes:
    # Find top 5 uncovered by count
    top_uncovered = sorted(uncovered_classes, key=lambda x: x[1], reverse=True)[:5]
    print(f"  Add templates for these high-impact classes:")
    for ifc_class, count in top_uncovered:
        impact_pct = (count / total_elements) * 100
        print(f"    - {ifc_class} ({count:,} elements, {impact_pct:.1f}% of total)")

print("=" * 80)

conn.close()
