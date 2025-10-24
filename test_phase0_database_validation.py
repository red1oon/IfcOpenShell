#!/usr/bin/env python3
"""
Phase 0 Database Validation Test
Validates that coordinate and site context data was properly extracted and stored
"""

import sqlite3
import os
from pathlib import Path

print("=" * 80)
print("PHASE 0 DATABASE VALIDATION TEST")
print("=" * 80)

db_path = Path.home() / "Documents/bonsai/federation_index.db"

if not os.path.exists(db_path):
    print(f"❌ Database not found: {db_path}")
    print("   Run preprocessing first!")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

test_results = {}

# ============================================================================
# TEST 1: Schema Validation - New Tables Exist
# ============================================================================

print("\n" + "=" * 80)
print("TEST 1: Schema Validation")
print("=" * 80)

cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [row[0] for row in cursor.fetchall()]

required_tables = ['element_transforms', 'site_context', 'elements_meta',
                   'element_semantics', 'material_library']

print("\nRequired tables:")
for table in required_tables:
    exists = table in tables
    status = "✅" if exists else "❌"
    print(f"  {status} {table}")
    test_results[f'table_{table}'] = exists

if 'element_transforms' not in tables:
    print("\n❌ CRITICAL: element_transforms table missing!")
    print("   Phase 0 changes not applied!")
    exit(1)

if 'site_context' not in tables:
    print("\n❌ CRITICAL: site_context table missing!")
    print("   Phase 0 changes not applied!")
    exit(1)

# ============================================================================
# TEST 2: Data Population - Element Transforms
# ============================================================================

print("\n" + "=" * 80)
print("TEST 2: Element Transforms Data Population")
print("=" * 80)

# Check transform count
cursor.execute("SELECT COUNT(*) FROM element_transforms")
transform_count = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM elements_meta")
meta_count = cursor.fetchone()[0]

print(f"\nElement counts:")
print(f"  elements_meta:       {meta_count:,}")
print(f"  element_transforms:  {transform_count:,}")

if transform_count == meta_count:
    print(f"  ✅ All elements have transforms!")
    test_results['transforms_complete'] = True
else:
    print(f"  ⚠️  Missing transforms: {meta_count - transform_count:,} elements")
    test_results['transforms_complete'] = False

# Check transform sources
cursor.execute("""
    SELECT transform_source, COUNT(*) as count
    FROM element_transforms
    GROUP BY transform_source
""")
transform_sources = cursor.fetchall()

print(f"\nTransform sources:")
for source, count in transform_sources:
    pct = (count / transform_count * 100) if transform_count > 0 else 0
    print(f"  {source:<20} {count:>7,} ({pct:>5.1f}%)")

# Check for valid coordinates (not all zeros)
cursor.execute("""
    SELECT COUNT(*) FROM element_transforms
    WHERE center_x != 0 OR center_y != 0 OR center_z != 0
""")
non_zero_count = cursor.fetchone()[0]
non_zero_pct = (non_zero_count / transform_count * 100) if transform_count > 0 else 0

print(f"\nCoordinate validation:")
print(f"  Non-zero positions:  {non_zero_count:,} ({non_zero_pct:.1f}%)")

if non_zero_pct > 90:
    print(f"  ✅ Most elements have valid coordinates")
    test_results['coordinates_valid'] = True
else:
    print(f"  ⚠️  Many elements at origin (0,0,0) - check extraction logic")
    test_results['coordinates_valid'] = False

# Sample transforms
print(f"\nSample element transforms:")
cursor.execute("""
    SELECT e.guid, e.ifc_class, t.center_x, t.center_y, t.center_z,
           t.rotation_x, t.rotation_y, t.rotation_z, t.transform_source
    FROM element_transforms t
    JOIN elements_meta e ON t.guid = e.guid
    WHERE t.transform_source = 'placement'
    LIMIT 5
""")

print(f"\n{'GUID':<40} {'Class':<25} {'Position':<30} {'Source':<15}")
print("-" * 115)
for row in cursor.fetchall():
    guid, ifc_class, cx, cy, cz, rx, ry, rz, source = row
    print(f"{guid:<40} {ifc_class:<25} ({cx:>8.2f}, {cy:>8.2f}, {cz:>8.2f}) {source:<15}")

# ============================================================================
# TEST 3: Site Context Data
# ============================================================================

print("\n" + "=" * 80)
print("TEST 3: Site Context Data")
print("=" * 80)

cursor.execute("SELECT COUNT(*) FROM site_context")
site_count = cursor.fetchone()[0]

print(f"\nSite context entries: {site_count}")

if site_count > 0:
    print(f"  ✅ Site context data exists")
    test_results['site_context_exists'] = True
else:
    print(f"  ⚠️  No site context data found")
    test_results['site_context_exists'] = False

# Show all site contexts
cursor.execute("""
    SELECT discipline, offset_x, offset_y, offset_z,
           true_north_angle, latitude, longitude, elevation,
           site_guid, project_guid
    FROM site_context
    ORDER BY discipline
""")

print(f"\nSite context by discipline:")
print(f"\n{'Discipline':<12} {'Offset (X, Y, Z)':<35} {'True North':<12} {'Lat/Long':<25}")
print("-" * 90)

for row in cursor.fetchall():
    disc, ox, oy, oz, tn, lat, lon, elev, site_guid, proj_guid = row
    offset_str = f"({ox:>8.2f}, {oy:>8.2f}, {oz:>8.2f})"
    tn_str = f"{tn:>8.4f} rad" if tn != 0 else "0.0000 rad"
    latlon_str = f"{lat:.6f}, {lon:.6f}" if lat and lon else "N/A"
    print(f"{disc:<12} {offset_str:<35} {tn_str:<12} {latlon_str:<25}")

# Check if offsets are meaningful (not all zeros)
cursor.execute("""
    SELECT COUNT(*) FROM site_context
    WHERE offset_x != 0 OR offset_y != 0 OR offset_z != 0
""")
non_zero_offsets = cursor.fetchone()[0]

if site_count > 0:
    offset_pct = (non_zero_offsets / site_count * 100)
    print(f"\nOffset validation:")
    print(f"  Non-zero offsets: {non_zero_offsets}/{site_count} ({offset_pct:.0f}%)")

    if offset_pct > 50:
        print(f"  ✅ Site offsets detected")
        test_results['site_offsets_valid'] = True
    else:
        print(f"  ⚠️  Most sites at origin - may be correct or extraction issue")
        test_results['site_offsets_valid'] = False

# ============================================================================
# TEST 4: Data Integrity - Foreign Keys
# ============================================================================

print("\n" + "=" * 80)
print("TEST 4: Data Integrity")
print("=" * 80)

# Check that all transforms reference valid elements
cursor.execute("""
    SELECT COUNT(*) FROM element_transforms t
    LEFT JOIN elements_meta e ON t.guid = e.guid
    WHERE e.guid IS NULL
""")
orphan_transforms = cursor.fetchone()[0]

if orphan_transforms == 0:
    print(f"  ✅ All transforms have valid element references")
    test_results['integrity_transforms'] = True
else:
    print(f"  ⚠️  {orphan_transforms} orphan transforms (no matching element)")
    test_results['integrity_transforms'] = False

# Check coordinate ranges (sanity check)
cursor.execute("""
    SELECT
        MIN(center_x) as min_x, MAX(center_x) as max_x,
        MIN(center_y) as min_y, MAX(center_y) as max_y,
        MIN(center_z) as min_z, MAX(center_z) as max_z
    FROM element_transforms
""")
ranges = cursor.fetchone()
min_x, max_x, min_y, max_y, min_z, max_z = ranges

print(f"\nCoordinate ranges:")
print(f"  X: {min_x:>12.2f} to {max_x:>12.2f} ({max_x - min_x:>10.2f} span)")
print(f"  Y: {min_y:>12.2f} to {max_y:>12.2f} ({max_y - min_y:>10.2f} span)")
print(f"  Z: {min_z:>12.2f} to {max_z:>12.2f} ({max_z - min_z:>10.2f} span)")

# Typical building dimensions: 50-500m span
span_x = max_x - min_x
span_y = max_y - min_y
span_z = max_z - min_z

if 10 < span_x < 1000 and 10 < span_y < 1000 and 2 < span_z < 200:
    print(f"  ✅ Coordinate ranges appear reasonable for a building")
    test_results['coordinates_reasonable'] = True
else:
    print(f"  ⚠️  Unusual coordinate ranges - verify extraction")
    test_results['coordinates_reasonable'] = False

# ============================================================================
# TEST 5: Rotation Data
# ============================================================================

print("\n" + "=" * 80)
print("TEST 5: Rotation Data")
print("=" * 80)

# Check if rotations exist (not all zero)
cursor.execute("""
    SELECT COUNT(*) FROM element_transforms
    WHERE rotation_x != 0 OR rotation_y != 0 OR rotation_z != 0
""")
rotated_count = cursor.fetchone()[0]
rotated_pct = (rotated_count / transform_count * 100) if transform_count > 0 else 0

print(f"\nRotation statistics:")
print(f"  Elements with rotation: {rotated_count:,} ({rotated_pct:.1f}%)")

if rotated_pct > 5:
    print(f"  ✅ Rotations detected")
    test_results['rotations_exist'] = True
else:
    print(f"  ⚠️  Very few rotations - elements might be axis-aligned")
    test_results['rotations_exist'] = False

# Sample rotated elements
cursor.execute("""
    SELECT e.guid, e.ifc_class, t.rotation_x, t.rotation_y, t.rotation_z
    FROM element_transforms t
    JOIN elements_meta e ON t.guid = e.guid
    WHERE t.rotation_x != 0 OR t.rotation_y != 0 OR t.rotation_z != 0
    LIMIT 5
""")

print(f"\nSample rotated elements:")
print(f"{'GUID':<40} {'Class':<25} {'Rotation (X, Y, Z)':<30}")
print("-" * 100)
for row in cursor.fetchall():
    guid, ifc_class, rx, ry, rz = row
    print(f"{guid:<40} {ifc_class:<25} ({rx:>8.4f}, {ry:>8.4f}, {rz:>8.4f})")

# ============================================================================
# FINAL SUMMARY
# ============================================================================

print("\n" + "=" * 80)
print("VALIDATION SUMMARY")
print("=" * 80)

all_critical_passed = (
    test_results.get('table_element_transforms', False) and
    test_results.get('table_site_context', False) and
    test_results.get('transforms_complete', False) and
    test_results.get('coordinates_valid', False) and
    test_results.get('site_context_exists', False)
)

print(f"\n📊 TEST RESULTS:")
for test, passed in test_results.items():
    status = "✅ PASS" if passed else "⚠️  WARN"
    print(f"  {status:<12} {test}")

print(f"\n{'=' * 80}")
if all_critical_passed:
    print("✅ PHASE 0 VALIDATION PASSED!")
    print("   Database has coordinate and site context data")
    print("   Ready for Phase 1 visualization!")
else:
    print("⚠️  SOME TESTS FAILED")
    print("   Review results above and check extraction logic")
print("=" * 80)

conn.close()
