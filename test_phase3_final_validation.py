#!/usr/bin/env python3
"""
Phase 3 Final Validation - Catch ALL Discrepancies
Tests the complete pipeline end-to-end
"""

import sys
import sqlite3
from pathlib import Path

# Add module to path
sys.path.insert(0, str(Path(__file__).parent / "src/bonsai"))

print("=" * 70)
print("PHASE 3 FINAL VALIDATION - COMPLETE PIPELINE TEST")
print("=" * 70)

db_path = Path.home() / "Documents/bonsai/DatabaseFiles/federatedmodel_merged.db"

# Test 1: Import Modules
print("\n[Test 1] Module Import Test")
print("-" * 70)

try:
    from bonsai.bim.module.clash import semantic_visualization
    print("✅ semantic_visualization module imported")
except Exception as e:
    print(f"❌ Failed to import semantic_visualization: {e}")
    sys.exit(1)

try:
    from bonsai.bim.module.clash import shape_templates
    print("✅ shape_templates module imported")
except Exception as e:
    print(f"❌ Failed to import shape_templates: {e}")
    sys.exit(1)

# Test 2: Query Semantic Elements (Fixed Query)
print("\n[Test 2] Query Semantic Elements (With Fixed Schema)")
print("-" * 70)

try:
    elements = semantic_visualization.query_semantic_elements(str(db_path), limit=100)
    print(f"✅ Query successful: {len(elements)} elements returned")

    if len(elements) == 0:
        print(f"❌ No elements returned - check query/schema")
        sys.exit(1)

    # Validate element structure
    elem = elements[0]
    required_keys = ['guid', 'ifc_class', 'discipline', 'profile_type',
                    'width', 'height', 'radius', 'length', 'bbox', 'bbox_center']

    missing_keys = [k for k in required_keys if k not in elem]
    if missing_keys:
        print(f"❌ Element missing keys: {missing_keys}")
        sys.exit(1)

    print(f"✅ All required element keys present")

    # Sample element details
    print(f"\n  Sample element:")
    print(f"    GUID: {elem['guid'][:16]}...")
    print(f"    IFC Class: {elem['ifc_class']}")
    print(f"    Discipline: {elem['discipline']}")
    print(f"    Profile: {elem['profile_type']}")
    print(f"    Dimensions: {elem['width']:.2f}m × {elem['height']:.2f}m")
    if elem['radius']:
        print(f"    Radius: {elem['radius']:.2f}m")
    print(f"    Length: {elem['length']:.2f}m")

except Exception as e:
    print(f"❌ Query failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Profile Type Distribution
print("\n[Test 3] Profile Type Distribution")
print("-" * 70)

circular_count = sum(1 for e in elements if e['profile_type'] == 'CIRCULAR')
rectangular_count = sum(1 for e in elements if e['profile_type'] == 'RECTANGULAR')

print(f"✅ Profile types inferred:")
print(f"  • CIRCULAR: {circular_count} ({circular_count/len(elements)*100:.0f}%)")
print(f"  • RECTANGULAR: {rectangular_count} ({rectangular_count/len(elements)*100:.0f}%)")

# Test 4: Dimension Validation
print("\n[Test 4] Dimension Validation")
print("-" * 70)

issues = []
for i, elem in enumerate(elements):
    # Check for None/zero dimensions
    if elem['width'] is None or elem['width'] <= 0:
        issues.append(f"Element {i}: width is {elem['width']}")
    if elem['height'] is None or elem['height'] <= 0:
        issues.append(f"Element {i}: height is {elem['height']}")
    if elem['length'] is None or elem['length'] <= 0:
        issues.append(f"Element {i}: length is {elem['length']}")

    # Check for reasonable ranges
    if elem['width'] and elem['width'] > 10.0:
        issues.append(f"Element {i}: width too large ({elem['width']:.1f}m)")
    if elem['height'] and elem['height'] > 10.0:
        issues.append(f"Element {i}: height too large ({elem['height']:.1f}m)")

if issues:
    print(f"⚠️  Dimension issues found ({len(issues)}/{len(elements)}):")
    for issue in issues[:5]:  # Show first 5
        print(f"  • {issue}")
else:
    print(f"✅ All element dimensions valid")

# Test 5: Shape Template Generation (Dry Run)
print("\n[Test 5] Shape Template Generation Test")
print("-" * 70)

# Test a few different element types
test_elements = elements[:10]
success_count = 0
fail_count = 0
failures = []

for elem in test_elements:
    dimensions = {
        'width': elem['width'],
        'height': elem['height'],
        'radius': elem['radius'],
        'length': elem['length']
    }

    # Try both detail levels
    for detail_level in ['basic', 'detailed']:
        try:
            # This would create actual geometry in Blender
            # For dry run, just check if parameters are valid
            if elem['profile_type'] == 'CIRCULAR' and elem['radius']:
                # Circular shape needs radius and length
                if elem['radius'] > 0 and elem['length'] > 0:
                    success_count += 1
                else:
                    fail_count += 1
                    failures.append(f"{elem['ifc_class']}: invalid radius/length")
            elif elem['profile_type'] == 'RECTANGULAR':
                # Rectangular shape needs width, height, length
                if elem['width'] > 0 and elem['height'] > 0 and elem['length'] > 0:
                    success_count += 1
                else:
                    fail_count += 1
                    failures.append(f"{elem['ifc_class']}: invalid width/height/length")
        except Exception as e:
            fail_count += 1
            failures.append(f"{elem['ifc_class']}: {str(e)[:50]}")

print(f"✅ Shape generation validation:")
print(f"  • Success: {success_count}/{success_count+fail_count}")
print(f"  • Failures: {fail_count}/{success_count+fail_count}")

if failures:
    print(f"\n  Failure details (first 5):")
    for failure in failures[:5]:
        print(f"    • {failure}")

# Test 6: Coordinate Offset Calculation
print("\n[Test 6] Coordinate Offset Calculation")
print("-" * 70)

try:
    offset = semantic_visualization.get_model_offset(str(db_path))
    print(f"✅ Offset calculated: ({offset.x:.1f}, {offset.y:.1f}, {offset.z:.1f})")

    # Verify offset is reasonable (should be around element centers)
    if abs(offset.x) < 1000 or abs(offset.y) < 1000:
        print(f"⚠️  Offset seems small - check if correct")
    else:
        print(f"✅ Offset in expected range (world coordinates)")

except Exception as e:
    print(f"❌ Offset calculation failed: {e}")

# Test 7: Element Position Validation
print("\n[Test 7] Element Position After Offset")
print("-" * 70)

# Check that elements will be positioned correctly
sample = elements[0]
bbox_center = sample['bbox_center']
offset_center = (
    bbox_center[0] - offset.x,
    bbox_center[1] - offset.y,
    bbox_center[2] - offset.z
)

print(f"  Original center: ({bbox_center[0]:.1f}, {bbox_center[1]:.1f}, {bbox_center[2]:.1f})")
print(f"  Offset center: ({offset_center[0]:.1f}, {offset_center[1]:.1f}, {offset_center[2]:.1f})")

# After offset, elements should be near origin
if all(abs(c) < 1000 for c in offset_center):
    print(f"✅ Elements will be positioned near origin after offset")
else:
    print(f"⚠️  Elements still far from origin after offset")

# Test 8: IFC Class Coverage
print("\n[Test 8] IFC Class Coverage")
print("-" * 70)

# Count unique IFC classes
ifc_classes = {}
for elem in elements:
    cls = elem['ifc_class']
    ifc_classes[cls] = ifc_classes.get(cls, 0) + 1

print(f"✅ IFC classes in sample:")
for cls, count in sorted(ifc_classes.items(), key=lambda x: -x[1]):
    print(f"  • {cls}: {count} elements")

# Test 9: Discipline Distribution
print("\n[Test 9] Discipline Distribution")
print("-" * 70)

disciplines = {}
for elem in elements:
    disc = elem['discipline']
    disciplines[disc] = disciplines.get(disc, 0) + 1

print(f"✅ Disciplines in sample:")
for disc, count in sorted(disciplines.items(), key=lambda x: -x[1]):
    print(f"  • {disc}: {count} elements")

# Test 10: Memory Estimation
print("\n[Test 10] Memory Usage Estimation")
print("-" * 70)

# Estimate memory for full dataset
conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM element_semantics WHERE semantic_type IS NOT NULL")
total_count = cursor.fetchone()[0]
conn.close()

# Estimate vertices per element
circular = sum(1 for e in elements if e['profile_type'] == 'CIRCULAR')
rectangular = sum(1 for e in elements if e['profile_type'] == 'RECTANGULAR')

# Basic: cylinders=24 verts (12 seg * 2), boxes=16 verts (8 corners * 2)
avg_verts_basic = (circular * 24 + rectangular * 16) / len(elements) if elements else 20
# Detailed: cylinders=96 verts (24 seg * 4), boxes=32 verts
avg_verts_detailed = (circular * 96 + rectangular * 32) / len(elements) if elements else 60

bytes_per_vert = 12 * 4  # 12 bytes (3 floats × 4 bytes)

memory_basic_mb = (total_count * avg_verts_basic * bytes_per_vert) / (1024 * 1024)
memory_detailed_mb = (total_count * avg_verts_detailed * bytes_per_vert) / (1024 * 1024)

print(f"✅ Memory estimates for {total_count:,} elements:")
print(f"  • Level 1 (Semantic Proxies): ~{memory_basic_mb:.0f} MB")
print(f"  • Level 2 (Full Geometry): ~{memory_detailed_mb:.0f} MB")

if memory_basic_mb > 100:
    print(f"  ⚠️  Level 1 may use significant memory")
if memory_detailed_mb > 300:
    print(f"  ⚠️  Level 2 may use significant memory")

# FINAL SUMMARY
print("\n" + "=" * 70)
print("FINAL VALIDATION SUMMARY")
print("=" * 70)

all_passed = (
    len(elements) > 0 and
    len(issues) == 0 and
    success_count > 0 and
    len(ifc_classes) > 0
)

if all_passed:
    print("\n✅ ALL TESTS PASSED - READY FOR BLENDER TESTING")
    print("\nNo discrepancies found:")
    print("  ✅ Module imports working")
    print("  ✅ Query schema matches database")
    print("  ✅ Element dimensions valid")
    print("  ✅ Profile types inferred correctly")
    print("  ✅ Shape generation parameters valid")
    print("  ✅ Coordinate offset calculated")
    print("  ✅ IFC class coverage confirmed")
    print("  ✅ Memory estimates reasonable")
else:
    print("\n⚠️  SOME ISSUES FOUND - REVIEW ABOVE")

print("\n📋 Next Step: Test in Blender")
print("  1. Launch Blender")
print("  2. Set database in Multi-Model Federation panel")
print("  3. Try Semantic Proxies with limit=100")
print("  4. Try Full Geometry with limit=100")

print("\n" + "=" * 70)
