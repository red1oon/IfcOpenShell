#!/usr/bin/env python3
"""
Database Query Speed Test
Tests how fast we can query 44K elements from federation database
"""

import sqlite3
import time
import os

print("=" * 80)
print("DATABASE QUERY SPEED TEST")
print("=" * 80)

db_path = os.path.expanduser("~/Documents/bonsai/federation_index.db")

if not os.path.exists(db_path):
    print(f"❌ Database not found: {db_path}")
    print("   Run preprocessing script first!")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# ============================================================================
# TEST 1: Query All Elements (Sequential)
# ============================================================================

print("\n" + "=" * 80)
print("TEST 1: Query All Elements from element_semantics (Sequential)")
print("=" * 80)

start = time.time()
cursor.execute("SELECT * FROM element_semantics")
elements = cursor.fetchall()
elapsed = time.time() - start

count = len(elements)
time_per_element = (elapsed / count) * 1000 if count > 0 else 0

print(f"\n✅ Fetched {count:,} elements in {elapsed:.3f}s")
print(f"   Time per element: {time_per_element:.4f}ms")

if elapsed < 1.0:
    print(f"   ✅ EXCELLENT! (<1 second)")
elif elapsed < 5.0:
    print(f"   ✅ GOOD! (<5 seconds)")
else:
    print(f"   ⚠️  SLOW! (>{elapsed:.1f} seconds)")

# ============================================================================
# TEST 2: Query with Filtering (Discipline)
# ============================================================================

print("\n" + "=" * 80)
print("TEST 2: Query Elements by Discipline (Indexed)")
print("=" * 80)

disciplines = ['ELEC', 'FP', 'ACMV', 'SP', 'CW']
discipline_times = {}

for disc in disciplines:
    start = time.time()
    cursor.execute("SELECT * FROM element_semantics WHERE discipline = ?", (disc,))
    disc_elements = cursor.fetchall()
    elapsed = time.time() - start

    count = len(disc_elements)
    discipline_times[disc] = (count, elapsed)

    print(f"{disc:<8} {count:>6,} elements  {elapsed*1000:>8.2f}ms")

# ============================================================================
# TEST 3: Query with Spatial Index (BBox)
# ============================================================================

print("\n" + "=" * 80)
print("TEST 3: Spatial Query (R-tree BBox Search)")
print("=" * 80)

# Query elements in a specific region
bbox = (0, 0, 0, 100, 100, 50)  # Example bounding box

start = time.time()
cursor.execute("""
    SELECT e.guid, e.semantic_type, e.discipline
    FROM element_semantics e
    JOIN elements_rtree r ON e.rowid = r.rowid
    WHERE r.minx >= ? AND r.maxx <= ?
      AND r.miny >= ? AND r.maxy <= ?
      AND r.minz >= ? AND r.maxz <= ?
""", bbox)
bbox_elements = cursor.fetchall()
elapsed = time.time() - start

count = len(bbox_elements)
print(f"\n✅ Spatial query found {count:,} elements in {elapsed*1000:.2f}ms")

if elapsed < 0.1:
    print(f"   ✅ INSTANT! (<100ms)")
elif elapsed < 0.5:
    print(f"   ✅ FAST! (<500ms)")
else:
    print(f"   ⚠️  SLOW! (>{elapsed*1000:.0f}ms)")

# ============================================================================
# TEST 4: Batch Query vs Sequential Query
# ============================================================================

print("\n" + "=" * 80)
print("TEST 4: Batch Query vs Sequential (1000 elements)")
print("=" * 80)

# Get 1000 GUIDs
cursor.execute("SELECT guid FROM element_semantics LIMIT 1000")
test_guids = [row[0] for row in cursor.fetchall()]

# Method 1: Sequential (1 query per GUID)
print("\nMethod 1: Sequential queries (1000 individual queries)...")
start = time.time()
for guid in test_guids:
    cursor.execute("SELECT * FROM element_semantics WHERE guid = ?", (guid,))
    cursor.fetchone()
elapsed_sequential = time.time() - start

print(f"   Time: {elapsed_sequential:.3f}s")

# Method 2: Batch (1 query with IN clause)
print("\nMethod 2: Batch query (1 query with IN clause)...")
start = time.time()
placeholders = ','.join(['?'] * len(test_guids))
cursor.execute(f"SELECT * FROM element_semantics WHERE guid IN ({placeholders})", test_guids)
batch_results = cursor.fetchall()
elapsed_batch = time.time() - start

print(f"   Time: {elapsed_batch:.3f}s")

speedup = elapsed_sequential / elapsed_batch if elapsed_batch > 0 else 0
print(f"\n📊 Batch query is {speedup:.1f}x FASTER than sequential!")

# ============================================================================
# TEST 5: Material Library Query
# ============================================================================

print("\n" + "=" * 80)
print("TEST 5: Material Library Query")
print("=" * 80)

try:
    start = time.time()
    cursor.execute("SELECT COUNT(*) FROM material_library")
    mat_count = cursor.fetchone()[0]
    elapsed = time.time() - start

    print(f"\n✅ Material library has {mat_count:,} entries")
    print(f"   Query time: {elapsed*1000:.2f}ms")
except Exception as e:
    print(f"⚠️  Material library query failed: {e}")

# ============================================================================
# SUMMARY
# ============================================================================

print("\n" + "=" * 80)
print("DATABASE QUERY PERFORMANCE SUMMARY")
print("=" * 80)

total_elements = count
query_time = elapsed

print(f"\n📊 CORE METRICS:")
print(f"  Total elements:       {total_elements:,}")
print(f"  Full query time:      {query_time:.3f}s")
print(f"  Time per element:     {time_per_element:.4f}ms")
print(f"  Batch speedup:        {speedup:.1f}x over sequential")

print(f"\n✅ VERDICT:")
if query_time < 1.0:
    print(f"  ✅ Database queries are FAST! (<1 second for all elements)")
    print(f"  ✅ Database I/O will NOT be a bottleneck")
    db_overhead = query_time
elif query_time < 5.0:
    print(f"  ✅ Database queries are acceptable (<5 seconds)")
    print(f"  ⚠️  Add ~{query_time:.1f}s to loading time")
    db_overhead = query_time
else:
    print(f"  ❌ Database queries are SLOW! (>{query_time:.1f} seconds)")
    print(f"  ❌ This will add significant overhead to loading!")
    print(f"  💡 Consider optimizations:")
    print(f"     - Add database indexes")
    print(f"     - Use batch queries (demonstrated {speedup:.1f}x speedup!)")
    print(f"     - Cache frequently accessed data")
    db_overhead = query_time

print(f"\n⏱️  PROJECTED LOADING TIME:")
print(f"  Database query:       {db_overhead:.1f}s")
print(f"  Object creation:      8s (from previous test)")
print(f"  Scene updates:        13s (from previous test)")
print(f"  Material assignment:  ~0.04s (standard palette)")
print(f"  {'─' * 40}")
print(f"  TOTAL ESTIMATED:      ~{db_overhead + 8 + 13 + 0.04:.1f}s")

print("=" * 80)

conn.close()
