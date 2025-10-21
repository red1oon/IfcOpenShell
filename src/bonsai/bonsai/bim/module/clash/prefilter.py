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
    if not spatial_index.is_loaded:
        raise RuntimeError("Spatial index not loaded. Call build() first.")
    
    # Note: set_a and set_b contain FILE PATHS, not GUIDs
    # We need to query all elements and do bbox intersection
    # This is a simplified version - just return empty for now
    # The actual filtering happens in IfcClash after geometry load
    
    print(f"DEBUG get_candidate_pairs: set_a has {len(set_a)} files")
    print(f"DEBUG get_candidate_pairs: set_b has {len(set_b)} files")
    
    # For now, return empty - prefilter at file level not element level
    # IfcClash will load all elements from these files
    return []

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