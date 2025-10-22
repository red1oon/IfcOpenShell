# Bonsai - OpenBIM Blender Add-on
# Copyright (C) 2025 Bonsai Contributors
#
# This file is part of Bonsai.
#
# Bonsai is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Bonsai is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Bonsai.  If not, see <http://www.gnu.org/licenses/>.

"""
Bbox-based pre-broadphase filtering for clash detection.

This module provides spatial prefiltering to reduce geometry loading
before IfcClash's broadphase/narrowphase collision detection.
"""

from typing import List, Set, Tuple, Optional
from pathlib import Path


def bboxes_intersect(bbox_a: Tuple[float, ...], bbox_b: Tuple[float, ...], tolerance: float = 0.0) -> bool:
    """
    Check if two bounding boxes intersect with optional tolerance.
    
    Args:
        bbox_a: (min_x, min_y, min_z, max_x, max_y, max_z)
        bbox_b: (min_x, min_y, min_z, max_x, max_y, max_z)
        tolerance: Clearance distance (negative = require overlap)
        
    Returns:
        True if bboxes intersect considering tolerance
    """
    min_xa, min_ya, min_za, max_xa, max_ya, max_za = bbox_a
    min_xb, min_yb, min_zb, max_xb, max_yb, max_zb = bbox_b
    
    # Expand bbox_a by tolerance
    min_xa -= tolerance
    min_ya -= tolerance
    min_za -= tolerance
    max_xa += tolerance
    max_ya += tolerance
    max_za += tolerance
    
    # Check separation on all axes
    if max_xa < min_xb or min_xa > max_xb:
        return False
    if max_ya < min_yb or min_ya > max_yb:
        return False
    if max_za < min_zb or min_za > max_zb:
        return False
    
    return True


def get_candidate_pairs(
    set_a: List[str],
    set_b: List[str],
    spatial_index,
    tolerance: float = 0.0
) -> List[Tuple[str, str]]:
    """
    Get element pairs whose bboxes intersect (candidates for geometry clash).

    Args:
        set_a: List of IFC file paths for clash set A
        set_b: List of IFC file paths for clash set B
        spatial_index: FederationIndex instance
        tolerance: Clearance distance in model units

    Returns:
        List of (guid_a, guid_b) pairs where bboxes intersect
    """
    import logging

    logger = logging.getLogger('BboxPrefilter')
    logger.setLevel(logging.INFO)

    # Setup file logging
    log_path = Path.home() / "Documents" / "bonsai.log"
    if not logger.handlers:
        file_handler = logging.FileHandler(str(log_path), mode='a')
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.info("=" * 70)
    logger.info("BBOX PREFILTERING - Clash Detection")
    logger.info("=" * 70)

    if not spatial_index.is_loaded:
        error_msg = "Spatial index not loaded. Call build() first."
        logger.error(error_msg)
        raise RuntimeError(error_msg)

    logger.info(f"Set A files: {len(set_a)}")
    logger.info(f"Set B files: {len(set_b)}")

    # Extract discipline codes from file paths
    # Assumption: file paths contain discipline codes (e.g., "ARC", "STR", "MEP")
    # For now, we'll use a simple heuristic: query all elements and do bbox tests

    # Get all elements from spatial index
    all_elements_a = []
    all_elements_b = []

    # Query by file paths - extract disciplines from filenames
    for file_path in set_a:
        # Try to extract discipline from filename (e.g., "Terminal_ARC.ifc" -> "ARC")
        filename = Path(file_path).stem.upper()
        for disc in ['ARC', 'STR', 'MEP', 'ACMV', 'ELEC', 'FP', 'SP', 'CW']:
            if disc in filename:
                logger.info(f"Set A: Querying discipline {disc} from {Path(file_path).name}")
                elements = spatial_index.query_by_discipline(disc)
                all_elements_a.extend(elements)
                logger.info(f"  Found {len(elements)} elements")
                break

    for file_path in set_b:
        filename = Path(file_path).stem.upper()
        for disc in ['ARC', 'STR', 'MEP', 'ACMV', 'ELEC', 'FP', 'SP', 'CW']:
            if disc in filename:
                logger.info(f"Set B: Querying discipline {disc} from {Path(file_path).name}")
                elements = spatial_index.query_by_discipline(disc)
                all_elements_b.extend(elements)
                logger.info(f"  Found {len(elements)} elements")
                break

    # If we couldn't extract disciplines, query all available disciplines
    if not all_elements_a:
        logger.warning("Could not extract disciplines from Set A files, querying all disciplines")
        for disc in spatial_index.stats['disciplines']:
            elements = spatial_index.query_by_discipline(disc)
            all_elements_a.extend(elements)
            logger.info(f"  Set A - {disc}: {len(elements)} elements")

    if not all_elements_b:
        logger.warning("Could not extract disciplines from Set B files, querying all disciplines")
        for disc in spatial_index.stats['disciplines']:
            elements = spatial_index.query_by_discipline(disc)
            all_elements_b.extend(elements)
            logger.info(f"  Set B - {disc}: {len(elements)} elements")

    logger.info(f"Total Set A elements: {len(all_elements_a)}")
    logger.info(f"Total Set B elements: {len(all_elements_b)}")

    # Find bbox intersections
    import time
    start_time = time.time()

    candidates = []
    for elem_a in all_elements_a:
        for elem_b in all_elements_b:
            # Use bboxes_intersect helper with tolerance
            if bboxes_intersect(elem_a.bbox, elem_b.bbox, tolerance=tolerance):
                candidates.append((elem_a.guid, elem_b.guid))

    analysis_time = time.time() - start_time

    # Calculate statistics
    total_combinations = len(all_elements_a) * len(all_elements_b)
    if total_combinations > 0:
        reduction = 100 * (1 - len(candidates) / total_combinations)
    else:
        reduction = 0

    logger.info("=" * 70)
    logger.info("PREFILTER RESULTS:")
    logger.info(f"Total combinations: {total_combinations:,}")
    logger.info(f"Bbox candidates:    {len(candidates):,}")
    logger.info(f"Reduction:          {reduction:.1f}%")
    logger.info(f"Analysis time:      {analysis_time:.2f} seconds")
    logger.info("=" * 70)

    print(f"\n{'=' * 70}")
    print("BBOX PREFILTER RESULTS:")
    print(f"  Total combinations: {total_combinations:,}")
    print(f"  Bbox candidates:    {len(candidates):,}")
    print(f"  Reduction:          {reduction:.1f}%")
    print(f"  Analysis time:      {analysis_time:.2f} seconds")
    print(f"{'=' * 70}\n")

    return candidates

def validate_spatial_index(database_path: Path) -> bool:
    """
    Validate that spatial index database exists and is loadable.
    """
    if not database_path.exists():
        return False
    
    if not database_path.is_file():
        return False
    
    if database_path.suffix != '.db':
        return False
    
    try:
        import sqlite3
        conn = sqlite3.connect(str(database_path))
        cursor = conn.cursor()
        
        # Check schema version
        cursor.execute("SELECT value FROM schema_info WHERE key = 'version'")
        version = cursor.fetchone()
        if not version:
            conn.close()
            return False
        
        # Check elements_meta table (NEW SCHEMA)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='elements_meta'")
        if not cursor.fetchone():
            conn.close()
            return False
        
        # Check elements_rtree table (NEW SCHEMA)
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='elements_rtree'")
        if not cursor.fetchone():
            conn.close()
            return False
        
        conn.close()
        return True
        
    except Exception:
        return False
    
def debug_database_schema(database_path: Path):
    """Debug helper to inspect database schema"""
    import sqlite3
    
    print(f"\n=== DATABASE SCHEMA DEBUG ===")
    print(f"Path: {database_path}")
    print(f"Exists: {database_path.exists()}")
    
    if not database_path.exists():
        return
    
    try:
        conn = sqlite3.connect(str(database_path))
        cursor = conn.cursor()
        
        # List all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"Tables: {tables}")
        
        # Check schema_info
        try:
            cursor.execute("SELECT key, value FROM schema_info")
            schema_info = cursor.fetchall()
            print(f"Schema info: {schema_info}")
        except:
            print("Schema info: NOT FOUND")
        
        # Count elements in each possible table
        for table in ['elements', 'elements_meta']:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"{table}: {count} rows")
            except:
                print(f"{table}: NOT FOUND")
        
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")
    
    print(f"=== END DEBUG ===\n")