#!/usr/bin/env python3
"""
Semantic Shape Quality Test Suite
Tests shapeliness, element fit, alignment, and geometric accuracy
"""

import sys
import sqlite3
from pathlib import Path
from math import sqrt, pi

print("=" * 70)
print("SEMANTIC SHAPE QUALITY TEST")
print("=" * 70)

# Test 1: Database Setup
print("\n[Test 1] Database Schema Validation")
print("-" * 70)

db_path = Path.home() / "Documents/bonsai/DatabaseFiles/federatedmodel_merged.db"

if not db_path.exists():
    print(f"❌ Database not found: {db_path}")
    sys.exit(1)

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# Check required tables
required_tables = ['elements_meta', 'elements_rtree']
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
existing_tables = [row[0] for row in cursor.fetchall()]

print(f"✅ Database found: {db_path.name}")
for table in required_tables:
    status = "✅" if table in existing_tables else "❌"
    print(f"  {status} Table '{table}': {'exists' if table in existing_tables else 'MISSING'}")

has_semantics = 'element_semantics' in existing_tables
if has_semantics:
    print(f"  ✅ Table 'element_semantics': exists (Phase 1 complete)")
else:
    print(f"  ⚠️  Table 'element_semantics': MISSING (Phase 1 prerequisite)")
    print(f"\n⚠️  WARNING: Phase 1 semantic metadata not found!")
    print(f"  This test will use bbox-based shape validation only.")
    print(f"  For full semantic testing, run Phase 1 database upgrade first.\n")

# Test 2: Element Sample Collection
print(f"\n[Test 2] Element Sample Collection")
print("-" * 70)

query = """
    SELECT
        m.guid,
        m.ifc_class,
        m.discipline,
        r.min_x, r.min_y, r.min_z,
        r.max_x, r.max_y, r.max_z
    FROM elements_meta m
    JOIN elements_rtree r ON m.id = r.id
    WHERE m.ifc_class LIKE '%Flow%'
       OR m.ifc_class LIKE '%Duct%'
       OR m.ifc_class LIKE '%Pipe%'
       OR m.ifc_class LIKE '%Cable%'
    LIMIT 100
"""

cursor.execute(query)
elements = cursor.fetchall()

print(f"✅ Collected {len(elements)} MEP elements for analysis")
print(f"  Sample classes: {', '.join(set(e[1] for e in elements[:10]))}")

# Test 3: Shapeliness - Dimensional Consistency
print(f"\n[Test 3] Shapeliness - Dimensional Consistency")
print("-" * 70)

shape_issues = []
reasonable_shapes = 0

for guid, ifc_class, discipline, min_x, min_y, min_z, max_x, max_y, max_z in elements:
    # Calculate dimensions
    width = max_x - min_x
    height = max_y - min_y
    length = max_z - min_z

    # Identify dominant axis (length)
    dimensions = sorted([width, height, length])
    cross_section_1 = dimensions[0]
    cross_section_2 = dimensions[1]
    element_length = dimensions[2]

    # Shapeliness checks
    issues = []

    # Check 1: Degenerate dimensions (too small)
    if any(d < 1.0 for d in [width, height, length]):
        issues.append(f"Degenerate dimension (<1mm): W={width:.1f}, H={height:.1f}, L={length:.1f}")

    # Check 2: Extreme aspect ratios (too thin/flat)
    if cross_section_1 > 0 and element_length / cross_section_1 > 10000:
        issues.append(f"Extreme aspect ratio: {element_length/cross_section_1:.0f}:1")

    # Check 3: Unreasonable cross-section ratio (too flat)
    if cross_section_1 > 0 and cross_section_2 / cross_section_1 > 100:
        issues.append(f"Flat cross-section: {cross_section_2/cross_section_1:.0f}:1")

    # Check 4: Typical duct/pipe size ranges
    if 'Duct' in ifc_class or 'Pipe' in ifc_class:
        typical_min = 50   # 50mm minimum diameter/width
        typical_max = 2000 # 2000mm maximum diameter/width

        if cross_section_1 < typical_min or cross_section_1 > typical_max:
            issues.append(f"Atypical cross-section size: {cross_section_1:.0f}mm")

    if issues:
        shape_issues.append((guid[:8], ifc_class, issues))
    else:
        reasonable_shapes += 1

pass_rate = (reasonable_shapes / len(elements) * 100) if elements else 0
print(f"✅ Shapeliness check: {reasonable_shapes}/{len(elements)} elements ({pass_rate:.1f}%) have reasonable geometry")

if shape_issues[:5]:
    print(f"\n  Issues found (showing first 5/{len(shape_issues)}):")
    for guid_short, ifc_class, issues in shape_issues[:5]:
        print(f"  ⚠️  {ifc_class} ({guid_short}):")
        for issue in issues:
            print(f"      • {issue}")

# Test 4: Element Fit - Proximity Analysis
print(f"\n[Test 4] Element Fit - Proximity Analysis")
print("-" * 70)

# Find elements that are close to each other (potential connections)
query_proximity = """
    SELECT
        m1.guid, m1.ifc_class, m1.discipline,
        m2.guid, m2.ifc_class, m2.discipline,
        r1.min_x, r1.min_y, r1.min_z, r1.max_x, r1.max_y, r1.max_z,
        r2.min_x, r2.min_y, r2.min_z, r2.max_x, r2.max_y, r2.max_z
    FROM elements_meta m1
    JOIN elements_rtree r1 ON m1.id = r1.id
    JOIN elements_rtree r2 ON (
        r1.min_x <= r2.max_x AND r1.max_x >= r2.min_x AND
        r1.min_y <= r2.max_y AND r1.max_y >= r2.min_y AND
        r1.min_z <= r2.max_z AND r1.max_z >= r2.min_z
    )
    JOIN elements_meta m2 ON m2.id = r2.id
    WHERE m1.id < m2.id
      AND (m1.ifc_class LIKE '%Flow%' OR m1.ifc_class LIKE '%Duct%' OR m1.ifc_class LIKE '%Pipe%')
      AND (m2.ifc_class LIKE '%Flow%' OR m2.ifc_class LIKE '%Duct%' OR m2.ifc_class LIKE '%Pipe%')
      AND m1.discipline = m2.discipline
    LIMIT 50
"""

cursor.execute(query_proximity)
proximity_pairs = cursor.fetchall()

print(f"✅ Found {len(proximity_pairs)} element pairs in proximity (potential connections)")

if proximity_pairs:
    # Analyze connection quality
    good_fits = 0
    alignment_issues = 0
    gap_issues = 0

    for pair in proximity_pairs[:20]:  # Analyze first 20 pairs
        guid1, class1, disc1, guid2, class2, disc2 = pair[:6]
        bbox1 = pair[6:12]
        bbox2 = pair[12:18]

        # Calculate bbox centers
        center1 = [
            (bbox1[0] + bbox1[3]) / 2,
            (bbox1[1] + bbox1[4]) / 2,
            (bbox1[2] + bbox1[5]) / 2
        ]
        center2 = [
            (bbox2[0] + bbox2[3]) / 2,
            (bbox2[1] + bbox2[4]) / 2,
            (bbox2[2] + bbox2[5]) / 2
        ]

        # Distance between centers
        distance = sqrt(
            (center2[0] - center1[0])**2 +
            (center2[1] - center1[1])**2 +
            (center2[2] - center1[2])**2
        )

        # Calculate bbox sizes
        size1 = max(bbox1[3] - bbox1[0], bbox1[4] - bbox1[1], bbox1[5] - bbox1[2])
        size2 = max(bbox2[3] - bbox2[0], bbox2[4] - bbox2[1], bbox2[5] - bbox2[2])

        # Connection quality metrics
        overlap_threshold = (size1 + size2) / 4  # Should be close

        if distance < overlap_threshold:
            good_fits += 1
        elif distance < overlap_threshold * 2:
            alignment_issues += 1
        else:
            gap_issues += 1

    print(f"\n  Connection quality analysis (sample of {min(20, len(proximity_pairs))}):")
    print(f"  ✅ Good fit: {good_fits} pairs (close alignment)")
    print(f"  ⚠️  Alignment issues: {alignment_issues} pairs (minor gaps)")
    print(f"  ❌ Gap issues: {gap_issues} pairs (significant gaps)")

# Test 5: Cross-Section Estimation
print(f"\n[Test 5] Cross-Section Profile Estimation")
print("-" * 70)

# Analyze bbox aspect ratios to estimate circular vs rectangular profiles
circular_estimate = 0
rectangular_estimate = 0
unknown = 0

for guid, ifc_class, discipline, min_x, min_y, min_z, max_x, max_y, max_z in elements:
    width = max_x - min_x
    height = max_y - min_y
    length = max_z - min_z

    # Find cross-section dimensions (2 smallest)
    dimensions = sorted([width, height, length])
    dim1, dim2 = dimensions[0], dimensions[1]

    if dim1 > 0:
        ratio = dim2 / dim1

        # Circular profile: ratio close to 1.0
        if 0.8 <= ratio <= 1.2:
            circular_estimate += 1
        # Rectangular profile: ratio > 1.2
        elif ratio > 1.2:
            rectangular_estimate += 1
        else:
            unknown += 1
    else:
        unknown += 1

if len(elements) > 0:
    print(f"✅ Profile estimation from bbox aspect ratios:")
    print(f"  • Circular: {circular_estimate} elements ({circular_estimate/len(elements)*100:.1f}%)")
    print(f"  • Rectangular: {rectangular_estimate} elements ({rectangular_estimate/len(elements)*100:.1f}%)")
    print(f"  • Unknown: {unknown} elements ({unknown/len(elements)*100:.1f}%)")
else:
    print(f"⚠️  No elements to analyze (check IFC class filter)")

# Test 6: Discipline Grouping Quality
print(f"\n[Test 6] Discipline Grouping Quality")
print("-" * 70)

cursor.execute("""
    SELECT discipline, COUNT(*) as count,
           AVG(max_x - min_x) as avg_width,
           AVG(max_y - min_y) as avg_height,
           AVG(max_z - min_z) as avg_length
    FROM elements_meta m
    JOIN elements_rtree r ON m.id = r.id
    WHERE m.ifc_class LIKE '%Flow%'
       OR m.ifc_class LIKE '%Duct%'
       OR m.ifc_class LIKE '%Pipe%'
    GROUP BY discipline
    ORDER BY count DESC
""")

discipline_stats = cursor.fetchall()

print(f"✅ Discipline statistics:")
for discipline, count, avg_w, avg_h, avg_l in discipline_stats:
    print(f"  • {discipline}: {count:,} elements")
    print(f"    Avg dimensions: {avg_w:.0f} x {avg_h:.0f} x {avg_l:.0f} mm")

# Test 7: Memory & Performance Estimation
print(f"\n[Test 7] Rendering Performance Estimation")
print("-" * 70)

cursor.execute("""
    SELECT COUNT(*)
    FROM elements_meta
    WHERE ifc_class LIKE '%Flow%'
       OR ifc_class LIKE '%Duct%'
       OR ifc_class LIKE '%Pipe%'
       OR ifc_class LIKE '%Cable%'
""")

total_mep = cursor.fetchone()[0]

# Vertex count estimates
vertices_basic = circular_estimate * 24 + rectangular_estimate * 16  # Cylinders: 12 segments * 2, Boxes: 8 corners * 2
vertices_detailed = circular_estimate * 96 + rectangular_estimate * 32  # More detail

memory_basic = (vertices_basic * 12 * 4) / (1024 * 1024)  # 12 bytes per vertex (3 floats), 4 bytes per float
memory_detailed = (vertices_detailed * 12 * 4) / (1024 * 1024)

if len(elements) > 0:
    print(f"✅ Performance estimates for {len(elements)} elements:")
    print(f"  Level 1 (Semantic Proxies):")
    print(f"    • Vertices: ~{vertices_basic:,}")
    print(f"    • Memory: ~{memory_basic:.1f} MB")
    print(f"    • Expected FPS: 30-60 (depends on GPU)")
    print(f"  Level 2 (Full Geometry):")
    print(f"    • Vertices: ~{vertices_detailed:,}")
    print(f"    • Memory: ~{memory_detailed:.1f} MB")
    print(f"    • Expected FPS: 15-30 (depends on GPU)")

    print(f"\n  Full dataset estimate ({total_mep:,} MEP elements):")
    full_vertices_basic = int(vertices_basic * (total_mep / len(elements)))
    full_vertices_detailed = int(vertices_detailed * (total_mep / len(elements)))
    full_memory_basic = (full_vertices_basic * 12 * 4) / (1024 * 1024)
    full_memory_detailed = (full_vertices_detailed * 12 * 4) / (1024 * 1024)

    print(f"    • Level 1: ~{full_memory_basic:.0f} MB, {full_vertices_basic:,} vertices")
    print(f"    • Level 2: ~{full_memory_detailed:.0f} MB, {full_vertices_detailed:,} vertices")
else:
    print(f"⚠️  Cannot estimate performance (no elements found)")

# Test 8: Semantic Metadata Availability (if Phase 1 complete)
if has_semantics:
    print(f"\n[Test 8] Semantic Metadata Quality")
    print("-" * 70)

    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN profile_type IS NOT NULL THEN 1 ELSE 0 END) as with_profile,
            SUM(CASE WHEN width IS NOT NULL OR radius IS NOT NULL THEN 1 ELSE 0 END) as with_dimensions
        FROM element_semantics
    """)

    stats = cursor.fetchone()
    total, with_profile, with_dims = stats

    if total > 0:
        print(f"✅ Semantic metadata coverage:")
        print(f"  • Total elements: {total:,}")
        print(f"  • With profile type: {with_profile:,} ({with_profile/total*100:.1f}%)")
        print(f"  • With dimensions: {with_dims:,} ({with_dims/total*100:.1f}%)")
    else:
        print(f"⚠️  No semantic metadata found (table exists but empty)")

conn.close()

# Summary
print(f"\n{'=' * 70}")
print(f"✅ SHAPE QUALITY TEST COMPLETE")
print(f"{'=' * 70}")

if len(elements) > 0:
    summary_status = "✅ PASS" if pass_rate >= 80 else "⚠️  MARGINAL" if pass_rate >= 60 else "❌ FAIL"
    print(f"\nOverall Assessment: {summary_status}")
    print(f"  • Shapeliness: {pass_rate:.1f}% elements have reasonable geometry")
    print(f"  • Proximity: {len(proximity_pairs)} connection candidates identified")
    print(f"  • Profile estimation: {circular_estimate + rectangular_estimate}/{len(elements)} classified")
else:
    print(f"\n⚠️  Overall Assessment: INCOMPLETE (no elements found for analysis)")

if not has_semantics:
    print(f"\n⚠️  PREREQUISITE: Run Phase 1 semantic metadata extraction")
    print(f"  Without semantic metadata, shape quality will be limited to bbox-based templates")

print(f"\n{'=' * 70}\n")
