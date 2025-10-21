#!/usr/bin/env python3
"""
Benchmark: SQLite built-in R-tree vs rtree library

Compares performance of two spatial indexing approaches:
1. Python rtree library (libspatialindex wrapper, in-memory)
2. SQLite built-in R-tree module (persistent, on-disk)

Usage:
    python benchmark_rtree.py path/to/terminal1.sqlite
"""

import sys
import time
import sqlite3
import statistics
from pathlib import Path

try:
    from rtree import index as rtree_index
except ImportError:
    print("ERROR: rtree library not installed")
    print("Install with: pip install rtree")
    sys.exit(1)


def load_elements_from_db(db_path):
    """Load all elements with bboxes from existing database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT guid, discipline, ifc_class, 
               min_x, min_y, min_z, max_x, max_y, max_z, filepath
        FROM elements
    """)
    
    elements = []
    for row in cursor.fetchall():
        elements.append({
            'guid': row[0],
            'discipline': row[1],
            'ifc_class': row[2],
            'bbox': (row[3], row[4], row[5], row[6], row[7], row[8]),
            'filepath': row[9]
        })
    
    conn.close()
    return elements


def create_sqlite_rtree_db(elements, output_path):
    """Create SQLite database with R-tree virtual table."""
    if output_path.exists():
        output_path.unlink()
    
    conn = sqlite3.connect(str(output_path))
    cursor = conn.cursor()
    
    # Metadata table
    cursor.execute("""
        CREATE TABLE elements_meta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guid TEXT UNIQUE NOT NULL,
            discipline TEXT NOT NULL,
            ifc_class TEXT NOT NULL,
            filepath TEXT NOT NULL
        )
    """)
    
    # R-tree virtual table (3D bounding boxes)
    cursor.execute("""
        CREATE VIRTUAL TABLE elements_rtree USING rtree(
            id,
            min_x, max_x,
            min_y, max_y,
            min_z, max_z
        )
    """)
    
    # Insert data
    for elem in elements:
        cursor.execute("""
            INSERT INTO elements_meta (guid, discipline, ifc_class, filepath)
            VALUES (?, ?, ?, ?)
        """, (elem['guid'], elem['discipline'], elem['ifc_class'], elem['filepath']))
        
        elem_id = cursor.lastrowid
        bbox = elem['bbox']
        
        cursor.execute("""
            INSERT INTO elements_rtree (id, min_x, max_x, min_y, max_y, min_z, max_z)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (elem_id, bbox[0], bbox[3], bbox[1], bbox[4], bbox[2], bbox[5]))
    
    conn.commit()
    conn.close()


def build_rtree_index(elements):
    """Build in-memory rtree index (current approach)."""
    props = rtree_index.Property()
    props.dimension = 3
    props.leaf_capacity = 100
    props.fill_factor = 0.9
    
    idx = rtree_index.Index(properties=props)
    
    for i, elem in enumerate(elements):
        bbox = elem['bbox']
        # rtree expects (min_x, min_y, min_z, max_x, max_y, max_z)
        idx.insert(i, bbox, obj=elem['guid'])
    
    return idx


def query_sqlite_rtree(db_path, bbox):
    """Query SQLite R-tree."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT m.guid, m.discipline, m.ifc_class
        FROM elements_rtree r
        JOIN elements_meta m ON r.id = m.id
        WHERE r.min_x <= ? AND r.max_x >= ?
          AND r.min_y <= ? AND r.max_y >= ?
          AND r.min_z <= ? AND r.max_z >= ?
    """, (bbox[3], bbox[0], bbox[4], bbox[1], bbox[5], bbox[2]))
    
    results = cursor.fetchall()
    conn.close()
    return results


def query_rtree_library(idx, guid_to_elem, bbox):
    """Query rtree library index."""
    results = []
    for item in idx.intersection(bbox, objects=True):
        guid = item.object
        elem = guid_to_elem.get(guid)
        if elem:
            results.append((elem['guid'], elem['discipline'], elem['ifc_class']))
    return results


def generate_test_queries(elements, num_queries=20):
    """Generate test bounding boxes of various sizes."""
    import random
    
    # Get overall bounds
    all_min_x = min(e['bbox'][0] for e in elements)
    all_max_x = max(e['bbox'][3] for e in elements)
    all_min_y = min(e['bbox'][1] for e in elements)
    all_max_y = max(e['bbox'][4] for e in elements)
    all_min_z = min(e['bbox'][2] for e in elements)
    all_max_z = max(e['bbox'][5] for e in elements)
    
    queries = []
    
    # Small queries (10% of space)
    for _ in range(num_queries // 4):
        size_x = (all_max_x - all_min_x) * 0.1
        size_y = (all_max_y - all_min_y) * 0.1
        size_z = (all_max_z - all_min_z) * 0.1
        
        min_x = random.uniform(all_min_x, all_max_x - size_x)
        min_y = random.uniform(all_min_y, all_max_y - size_y)
        min_z = random.uniform(all_min_z, all_max_z - size_z)
        
        queries.append((min_x, min_y, min_z, min_x + size_x, min_y + size_y, min_z + size_z))
    
    # Medium queries (30% of space)
    for _ in range(num_queries // 4):
        size_x = (all_max_x - all_min_x) * 0.3
        size_y = (all_max_y - all_min_y) * 0.3
        size_z = (all_max_z - all_min_z) * 0.3
        
        min_x = random.uniform(all_min_x, all_max_x - size_x)
        min_y = random.uniform(all_min_y, all_max_y - size_y)
        min_z = random.uniform(all_min_z, all_max_z - size_z)
        
        queries.append((min_x, min_y, min_z, min_x + size_x, min_y + size_y, min_z + size_z))
    
    # Large queries (60% of space)
    for _ in range(num_queries // 4):
        size_x = (all_max_x - all_min_x) * 0.6
        size_y = (all_max_y - all_min_y) * 0.6
        size_z = (all_max_z - all_min_z) * 0.6
        
        min_x = random.uniform(all_min_x, all_max_x - size_x)
        min_y = random.uniform(all_min_y, all_max_y - size_y)
        min_z = random.uniform(all_min_z, all_max_z - size_z)
        
        queries.append((min_x, min_y, min_z, min_x + size_x, min_y + size_y, min_z + size_z))
    
    # Very large queries (full space slices)
    for _ in range(num_queries // 4):
        queries.append((all_min_x, all_min_y, all_min_z, all_max_x, all_max_y, all_max_z))
    
    return queries


def main():
    if len(sys.argv) < 2:
        print("Usage: python benchmark_rtree.py path/to/terminal1.sqlite")
        sys.exit(1)
    
    input_db = Path(sys.argv[1])
    if not input_db.exists():
        print(f"ERROR: Database not found: {input_db}")
        sys.exit(1)
    
    print("=" * 70)
    print("BENCHMARK: SQLite R-tree vs rtree Library")
    print("=" * 70)
    print()
    
    # Load data
    print("Loading elements from database...")
    elements = load_elements_from_db(input_db)
    print(f"  Loaded {len(elements):,} elements")
    print()
    
    # Setup SQLite R-tree
    print("Setting up SQLite R-tree...")
    sqlite_db = Path("benchmark_sqlite_rtree.db")
    start = time.time()
    create_sqlite_rtree_db(elements, sqlite_db)
    sqlite_setup_time = time.time() - start
    print(f"  Setup time: {sqlite_setup_time:.2f}s")
    print(f"  Database size: {sqlite_db.stat().st_size / 1024 / 1024:.1f} MB")
    print()
    
    # Setup rtree library
    print("Setting up rtree library index...")
    start = time.time()
    rtree_idx = build_rtree_index(elements)
    rtree_setup_time = time.time() - start
    print(f"  Setup time: {rtree_setup_time:.2f}s")
    print()
    
    # Generate test queries
    print("Generating test queries...")
    queries = generate_test_queries(elements, num_queries=100)
    print(f"  Generated {len(queries)} test queries")
    print()
    
    # Benchmark SQLite R-tree
    print("Benchmarking SQLite R-tree queries...")
    sqlite_times = []
    sqlite_results_count = []
    
    for bbox in queries:
        start = time.time()
        results = query_sqlite_rtree(sqlite_db, bbox)
        elapsed = time.time() - start
        sqlite_times.append(elapsed * 1000)  # Convert to ms
        sqlite_results_count.append(len(results))
    
    print(f"  Completed {len(queries)} queries")
    print()
    
    # Create lookup dictionary for fast guid->element access
    guid_to_elem = {e['guid']: e for e in elements}
    
    # Benchmark rtree library
    print("Benchmarking rtree library queries...")
    rtree_times = []
    rtree_results_count = []
    
    for bbox in queries:
        start = time.time()
        results = query_rtree_library(rtree_idx, guid_to_elem, bbox)
        elapsed = time.time() - start
        rtree_times.append(elapsed * 1000)  # Convert to ms
        rtree_results_count.append(len(results))
    
    print(f"  Completed {len(queries)} queries")
    print()
    
    # Results
    print("=" * 70)
    print("RESULTS")
    print("=" * 70)
    print()
    
    print(f"Dataset: {len(elements):,} elements")
    print()
    
    print("SETUP TIME (one-time cost):")
    print(f"  rtree library:  {rtree_setup_time:6.2f}s")
    print(f"  SQLite R-tree:  {sqlite_setup_time:6.2f}s")
    print(f"  Difference:     {rtree_setup_time - sqlite_setup_time:+6.2f}s")
    print()
    
    print("QUERY PERFORMANCE (100 queries):")
    print(f"  rtree library:")
    print(f"    Mean:   {statistics.mean(rtree_times):6.2f}ms")
    print(f"    Median: {statistics.median(rtree_times):6.2f}ms")
    print(f"    Min:    {min(rtree_times):6.2f}ms")
    print(f"    Max:    {max(rtree_times):6.2f}ms")
    print()
    print(f"  SQLite R-tree:")
    print(f"    Mean:   {statistics.mean(sqlite_times):6.2f}ms")
    print(f"    Median: {statistics.median(sqlite_times):6.2f}ms")
    print(f"    Min:    {min(sqlite_times):6.2f}ms")
    print(f"    Max:    {max(sqlite_times):6.2f}ms")
    print()
    
    mean_diff_pct = ((statistics.mean(sqlite_times) / statistics.mean(rtree_times)) - 1) * 100
    print(f"  SQLite vs rtree: {mean_diff_pct:+.1f}% per query")
    print()
    
    # Break-even analysis
    time_saved_on_setup = rtree_setup_time - sqlite_setup_time
    time_lost_per_query = (statistics.mean(sqlite_times) - statistics.mean(rtree_times)) / 1000
    
    if time_lost_per_query > 0:
        breakeven = int(time_saved_on_setup / time_lost_per_query)
        print(f"BREAK-EVEN ANALYSIS:")
        print(f"  Setup time saved: {time_saved_on_setup:.2f}s")
        print(f"  Per-query penalty: {time_lost_per_query*1000:.2f}ms")
        print(f"  Break-even point: {breakeven:,} queries")
        print(f"  (SQLite wins if fewer than {breakeven:,} queries per session)")
    else:
        print(f"ANALYSIS:")
        print(f"  SQLite R-tree is faster in both setup AND queries!")
    
    print()
    
    # Verify correctness
    print("CORRECTNESS CHECK:")
    mismatches = sum(1 for s, r in zip(sqlite_results_count, rtree_results_count) if s != r)
    if mismatches == 0:
        print("  ✓ Both methods returned identical result counts for all queries")
    else:
        print(f"  ✗ {mismatches}/{len(queries)} queries had different result counts")
        print("    (May be due to float precision differences)")
    
    print()
    print("=" * 70)
    # After line 240 in benchmark, add:
    if mismatches > 0:
        print("\n  All mismatches:")
        for i, (s, r) in enumerate(zip(sqlite_results_count, rtree_results_count)):
            if s != r:
                diff = abs(s - r)
                pct = (diff / max(s, r)) * 100
                print(f"    Query {i}: SQLite={s}, rtree={r}, diff={diff} ({pct:.2f}%)")
    # Cleanup
    sqlite_db.unlink()

if __name__ == "__main__":
    main()
