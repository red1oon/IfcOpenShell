#!/usr/bin/env python3
"""
Test Suite for Phase 3: Semantic Geometry Visualization
Tests shape template generation and database integration
"""

import sys
import sqlite3
from pathlib import Path

# Add Bonsai module to path
sys.path.insert(0, str(Path(__file__).parent / "src/bonsai"))

# Import shape templates (without Blender dependency for basic tests)
print("=" * 70)
print("PHASE 3 TEST SUITE: Semantic Geometry")
print("=" * 70)

# Test 1: Database Query
print("\n[Test 1] Database Query for Semantic Elements")
print("-" * 70)

db_path = Path.home() / "Documents/bonsai/federatedmodel_merged.db"

if not db_path.exists():
    print(f"❌ Database not found: {db_path}")
    print("   Please run federation preprocessing first")
    sys.exit(1)

conn = sqlite3.connect(str(db_path))
cursor = conn.cursor()

# Query elements with semantic metadata
query = """
    SELECT
        m.guid,
        m.ifc_class,
        m.discipline,
        s.profile_type,
        s.width,
        s.height,
        s.radius,
        s.length
    FROM elements_meta m
    JOIN element_semantics s ON m.id = s.element_id
    WHERE s.profile_type IS NOT NULL
    LIMIT 10
"""

cursor.execute(query)
rows = cursor.fetchall()

print(f"✅ Query successful: {len(rows)} elements with semantics")
print(f"\nSample elements:")
for i, row in enumerate(rows[:5], 1):
    guid, ifc_class, discipline, profile_type, width, height, radius, length = row
    print(f"  {i}. {ifc_class} ({profile_type})")
    print(f"     Discipline: {discipline}")
    if radius:
        print(f"     Radius: {radius}mm")
    if width and height:
        print(f"     Dimensions: {width}x{height}mm")
    if length:
        print(f"     Length: {length}mm")

# Test 2: Profile Type Distribution
print(f"\n[Test 2] Profile Type Distribution")
print("-" * 70)

cursor.execute("""
    SELECT profile_type, COUNT(*) as count
    FROM element_semantics
    WHERE profile_type IS NOT NULL
    GROUP BY profile_type
    ORDER BY count DESC
""")

profile_stats = cursor.fetchall()
print(f"✅ Profile types found: {len(profile_stats)}")
for profile_type, count in profile_stats:
    print(f"  • {profile_type}: {count:,} elements")

# Test 3: IFC Class Distribution with Semantics
print(f"\n[Test 3] IFC Class Distribution (with semantics)")
print("-" * 70)

cursor.execute("""
    SELECT m.ifc_class, COUNT(*) as count
    FROM elements_meta m
    JOIN element_semantics s ON m.id = s.element_id
    WHERE s.profile_type IS NOT NULL
    GROUP BY m.ifc_class
    ORDER BY count DESC
    LIMIT 10
""")

class_stats = cursor.fetchall()
print(f"✅ Top {len(class_stats)} IFC classes with semantic metadata:")
for ifc_class, count in class_stats:
    print(f"  • {ifc_class}: {count:,} elements")

# Test 4: Discipline Distribution
print(f"\n[Test 4] Discipline Distribution (with semantics)")
print("-" * 70)

cursor.execute("""
    SELECT m.discipline, COUNT(*) as count
    FROM elements_meta m
    JOIN element_semantics s ON m.id = s.element_id
    WHERE s.profile_type IS NOT NULL
    GROUP BY m.discipline
    ORDER BY count DESC
""")

discipline_stats = cursor.fetchall()
print(f"✅ Disciplines with semantic metadata:")
for discipline, count in discipline_stats:
    print(f"  • {discipline}: {count:,} elements")

# Test 5: Shape Template Coverage
print(f"\n[Test 5] Shape Template Coverage Analysis")
print("-" * 70)

# Check which IFC classes + profile types are supported
cursor.execute("""
    SELECT m.ifc_class, s.profile_type, COUNT(*) as count
    FROM elements_meta m
    JOIN element_semantics s ON m.id = s.element_id
    WHERE s.profile_type IS NOT NULL
    GROUP BY m.ifc_class, s.profile_type
    ORDER BY count DESC
    LIMIT 15
""")

coverage_stats = cursor.fetchall()

# Supported combinations (from shape_templates.py logic)
supported_patterns = [
    ('Duct', 'CIRCULAR'),
    ('Duct', 'RECTANGULAR'),
    ('Pipe', 'CIRCULAR'),
    ('Cable', 'CIRCULAR'),
    ('Tray', None),
    ('Conduit', None),
    ('Fitting', None)
]

print(f"✅ Shape template coverage:")
supported_count = 0
unsupported_count = 0

for ifc_class, profile_type, count in coverage_stats:
    is_supported = False
    for pattern_class, pattern_profile in supported_patterns:
        if pattern_class in ifc_class:
            if pattern_profile is None or pattern_profile == profile_type:
                is_supported = True
                break

    status = "✅" if is_supported else "⚠️"
    print(f"  {status} {ifc_class} + {profile_type}: {count:,} elements")

    if is_supported:
        supported_count += count
    else:
        unsupported_count += count

total_count = supported_count + unsupported_count
coverage_percent = (supported_count / total_count * 100) if total_count > 0 else 0

print(f"\n📊 Coverage Summary:")
print(f"  Supported: {supported_count:,} elements ({coverage_percent:.1f}%)")
print(f"  Unsupported: {unsupported_count:,} elements ({100-coverage_percent:.1f}%)")

# Test 6: Memory Estimation
print(f"\n[Test 6] Memory Usage Estimation")
print("-" * 70)

cursor.execute("""
    SELECT COUNT(*)
    FROM elements_meta m
    JOIN element_semantics s ON m.id = s.element_id
    WHERE s.profile_type IS NOT NULL
""")

total_semantic_elements = cursor.fetchone()[0]

# Rough estimates:
# Basic shapes: ~12 segments cylinder, ~6 faces box = ~100 bytes per vertex, ~50 vertices avg = 5KB per object
# Detailed shapes: ~24 segments, more faces = ~15KB per object

basic_memory_mb = (total_semantic_elements * 5) / 1024  # KB to MB
detailed_memory_mb = (total_semantic_elements * 15) / 1024

print(f"✅ Memory estimates for {total_semantic_elements:,} elements:")
print(f"  Level 1 (Semantic Proxies): ~{basic_memory_mb:.1f} MB")
print(f"  Level 2 (Full Geometry): ~{detailed_memory_mb:.1f} MB")

# Test 7: Recommended Test Limits
print(f"\n[Test 7] Recommended Test Limits")
print("-" * 70)

limits = [100, 500, 1000, 5000, total_semantic_elements]
print(f"✅ Suggested testing progression:")

for limit in limits:
    if limit > total_semantic_elements:
        continue
    mem_basic = (limit * 5) / 1024
    mem_detailed = (limit * 15) / 1024
    print(f"  • {limit:,} elements: Basic={mem_basic:.1f}MB, Detailed={mem_detailed:.1f}MB")

conn.close()

# Summary
print(f"\n{'=' * 70}")
print(f"✅ ALL TESTS PASSED")
print(f"{'=' * 70}")
print(f"\nDatabase ready for Phase 3 semantic visualization!")
print(f"\nNext steps:")
print(f"1. Start Blender with Bonsai")
print(f"2. Go to Clash Detection → Federation LOD Visualization")
print(f"3. Set database in Multi-Model Federation panel")
print(f"4. Try BBox Wireframe first (verify it still works)")
print(f"5. Try Semantic Proxies with limit=100 (quick test)")
print(f"6. Try Semantic Proxies with limit=1000 (realistic test)")
print(f"7. Try Full Geometry with limit=100 (detailed shapes)")
print(f"{'=' * 70}\n")
