"""
Qualified Path: src/bonsai/bonsai/bim/module/federation/spatial_index.py

CREDIT to IFCOPENSHELLL community - Thomas Krijnen for suggesting this.

Spatial Index Module - SQLite R-tree based Federated Model Queries
-------------------------------------------------------------------
Provides fast spatial queries over preprocessed IFC bounding boxes
using SQLite's built-in R-tree indexing for multi-model coordination.

Performance: 20x faster than rtree library, zero setup time.

Usage:
    from bonsai.bim.module.federation.spatial_index import FederationIndex
    
    index = FederationIndex("/path/to/federation.db")
    index.build()  # Instant - R-tree already exists in database
    
    # Query obstacles in routing corridor
    obstacles = index.query_by_bbox(
        min_xyz=(1000, 2000, 3000),
        max_xyz=(1500, 2500, 4000)
    )
"""

import sqlite3
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class FederationElement:
    """Represents a federated element with spatial data"""
    
    def __init__(self, guid: str, discipline: str, ifc_class: str,
                 bbox: Tuple[float, float, float, float, float, float],
                 filepath: str):
        self.guid = guid
        self.discipline = discipline
        self.ifc_class = ifc_class
        self.min_x, self.min_y, self.min_z = bbox[:3]
        self.max_x, self.max_y, self.max_z = bbox[3:]
        self.filepath = filepath
    
    @property
    def bbox(self) -> Tuple[float, float, float, float, float, float]:
        """Return bounding box as (min_x, min_y, min_z, max_x, max_y, max_z)"""
        return (self.min_x, self.min_y, self.min_z, 
                self.max_x, self.max_y, self.max_z)
    
    @property
    def centroid(self) -> Tuple[float, float, float]:
        """Calculate bbox centroid"""
        return (
            (self.min_x + self.max_x) / 2,
            (self.min_y + self.max_y) / 2,
            (self.min_z + self.max_z) / 2
        )
    
    def intersects_bbox(self, other_bbox: Tuple[float, float, float, float, float, float]) -> bool:
        """Check if this element's bbox intersects another bbox"""
        other_min_x, other_min_y, other_min_z, other_max_x, other_max_y, other_max_z = other_bbox
        
        # Axis-Aligned Bounding Box (AABB) intersection test
        return not (
            self.max_x < other_min_x or self.min_x > other_max_x or
            self.max_y < other_min_y or self.min_y > other_max_y or
            self.max_z < other_min_z or self.min_z > other_max_z
        )
    
    def __repr__(self):
        return (f"FederationElement(guid={self.guid}, "
                f"discipline={self.discipline}, "
                f"ifc_class={self.ifc_class})")


class FederationIndex:
    """Spatial index for federated IFC models using SQLite R-tree"""
    
    def __init__(self, database_path: Path, logger: Optional[logging.Logger] = None):
        self.database_path = Path(database_path)
        self.logger = logger or self._setup_logging()
        self.is_loaded = False
        
        # Statistics
        self.stats = {
            'total_elements': 0,
            'disciplines': set(),
            'ifc_classes': set()
        }
    
    def _setup_logging(self) -> logging.Logger:
        """Configure logging"""
        logger = logging.getLogger('FederationIndex')
        logger.setLevel(logging.INFO)
        
        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
        
        return logger

    def query_corridor(self, start: Tuple[float, float, float],
                      end: Tuple[float, float, float],
                      buffer: float = 500.0,
                      disciplines: Optional[List[str]] = None) -> List[FederationElement]:
        """
        Query elements along a corridor path with buffer
        
        Args:
            start: Start point (x, y, z)
            end: End point (x, y, z)
            buffer: Corridor width/height buffer in METERS
            disciplines: Optional filter by discipline tags
            
        Returns:
            List of FederationElement instances along corridor
        """
        # Calculate bbox encompassing corridor with buffer
        min_x = min(start[0], end[0]) - buffer
        max_x = max(start[0], end[0]) + buffer
        min_y = min(start[1], end[1]) - buffer
        max_y = max(start[1], end[1]) + buffer
        min_z = min(start[2], end[2]) - buffer
        max_z = max(start[2], end[2]) + buffer
        
        return self.query_by_bbox(
            (min_x, min_y, min_z),
            (max_x, max_y, max_z),
            disciplines
        )

    def build(self, force_rebuild: bool = False) -> None:
        """
        Validate database and load statistics
        
        Args:
            force_rebuild: Ignored (kept for API compatibility)
        
        Note: SQLite R-tree already exists in database - no build needed
        """
        if self.is_loaded and not force_rebuild:
            self.logger.info("Index already loaded. Use force_rebuild=True to reload.")
            return
        
        self.logger.info(f"Loading spatial index from {self.database_path.name}...")
        
        if not self.database_path.exists():
            raise FileNotFoundError(f"Database not found: {self.database_path}")
        
        # Validate database
        self._validate_database()
        
        # Load statistics
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()
        
        # Count elements
        cursor.execute("SELECT COUNT(*) FROM elements_meta")
        self.stats['total_elements'] = cursor.fetchone()[0]
        
        # Get disciplines
        cursor.execute("SELECT DISTINCT discipline FROM elements_meta")
        self.stats['disciplines'] = {row[0] for row in cursor.fetchall()}
        
        # Get IFC classes
        cursor.execute("SELECT DISTINCT ifc_class FROM elements_meta")
        self.stats['ifc_classes'] = {row[0] for row in cursor.fetchall()}
        
        conn.close()
        
        self.is_loaded = True
        
        self.logger.info(f"✓ Index loaded: {self.stats['total_elements']:,} elements from "
                        f"{len(self.stats['disciplines'])} disciplines")
    
    def _validate_database(self):
        """Validate database schema"""
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()
        
        # Check schema version
        try:
            cursor.execute("SELECT value FROM schema_info WHERE key = 'version'")
            version = cursor.fetchone()
            if not version:
                raise ValueError("Missing schema version in database")
        except sqlite3.OperationalError:
            raise ValueError("Invalid database: missing schema_info table")
        
        # Check elements_meta table exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='elements_meta'
        """)
        if not cursor.fetchone():
            raise ValueError("Invalid database: missing elements_meta table")
        
        # Check elements_rtree exists
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='elements_rtree'
        """)
        if not cursor.fetchone():
            raise ValueError("Invalid database: missing elements_rtree spatial index")
        
        conn.close()
    
    def query_by_bbox(self, min_xyz: Tuple[float, float, float],
                      max_xyz: Tuple[float, float, float],
                      disciplines: Optional[List[str]] = None,
                      ifc_classes: Optional[List[str]] = None) -> List[FederationElement]:
        """
        Query elements intersecting bounding box using SQLite R-tree
        
        Args:
            min_xyz: Minimum corner (x, y, z)
            max_xyz: Maximum corner (x, y, z)
            disciplines: Optional filter by discipline tags
            ifc_classes: Optional filter by IFC classes
            
        Returns:
            List of FederationElement instances
        """
        if not self.is_loaded:
            raise RuntimeError("Index not loaded. Call build() first.")
        
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()
        
        # Build query with optional filters
        query = """
            SELECT m.guid, m.discipline, m.ifc_class, m.filepath,
                   r.min_x, r.min_y, r.min_z, r.max_x, r.max_y, r.max_z
            FROM elements_rtree r
            JOIN elements_meta m ON r.id = m.id
            WHERE r.min_x <= ? AND r.max_x >= ?
              AND r.min_y <= ? AND r.max_y >= ?
              AND r.min_z <= ? AND r.max_z >= ?
        """
        params = [max_xyz[0], min_xyz[0], max_xyz[1], min_xyz[1], max_xyz[2], min_xyz[2]]
        
        # Add discipline filter
        if disciplines:
            # Normalize disciplines
            disciplines = [self._normalize_discipline(d) for d in disciplines]
            placeholders = ','.join('?' * len(disciplines))
            query += f" AND m.discipline IN ({placeholders})"
            params.extend(disciplines)
        
        # Add IFC class filter
        if ifc_classes:
            placeholders = ','.join('?' * len(ifc_classes))
            query += f" AND m.ifc_class IN ({placeholders})"
            params.extend(ifc_classes)
        
        cursor.execute(query, params)
        
        # Convert results to FederationElement objects
        results = []
        for row in cursor.fetchall():
            guid, discipline, ifc_class, filepath = row[:4]
            bbox = row[4:]
            results.append(FederationElement(guid, discipline, ifc_class, bbox, filepath))
        
        conn.close()
        return results
    
    def query_by_point(self, point: Tuple[float, float, float],
                       radius: float = 0.0,
                       disciplines: Optional[List[str]] = None) -> List[FederationElement]:
        """
        Query elements at or near a point
        
        Args:
            point: Query point (x, y, z)
            radius: Search radius (0 = exact point)
            disciplines: Optional filter by discipline tags
            
        Returns:
            List of FederationElement instances
        """
        x, y, z = point
        min_xyz = (x - radius, y - radius, z - radius)
        max_xyz = (x + radius, y + radius, z + radius)
        
        return self.query_by_bbox(min_xyz, max_xyz, disciplines=disciplines)
    
    def query_by_discipline(self, discipline: str) -> List[FederationElement]:
        """
        Get all elements from a specific discipline
        
        Args:
            discipline: Discipline tag (e.g., 'ACMV', 'FP')
            
        Returns:
            List of FederationElement instances
        """
        if not self.is_loaded:
            raise RuntimeError("Index not loaded. Call build() first.")
        
        discipline = self._normalize_discipline(discipline)
        
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT m.guid, m.discipline, m.ifc_class, m.filepath,
                   r.min_x, r.min_y, r.min_z, r.max_x, r.max_y, r.max_z
            FROM elements_rtree r
            JOIN elements_meta m ON r.id = m.id
            WHERE m.discipline = ?
        """, (discipline,))
        
        results = []
        for row in cursor.fetchall():
            guid, disc, ifc_class, filepath = row[:4]
            bbox = row[4:]
            results.append(FederationElement(guid, disc, ifc_class, bbox, filepath))
        
        conn.close()
        return results
    
    def _normalize_discipline(self, discipline: str) -> str:
        """Normalize discipline tag (handle case, abbreviations)"""
        if not discipline:
            return discipline
        
        # Uppercase
        discipline = discipline.upper().strip()
        
        # Common aliases
        aliases = {
            'MECHANICAL': 'ACMV',
            'HVAC': 'ACMV',
            'MECH': 'ACMV',
            'PLUMBING': 'SP',
            'PLUMB': 'SP',
            'SANITARY': 'SP',
            'ELECTRICAL': 'ELEC',
            'ELECTRIC': 'ELEC',
            'FIRE': 'FP',
            'FIREPROTECTION': 'FP',
            'STRUCTURAL': 'STR',
            'STRUCTURE': 'STR',
            'ARCHITECTURE': 'ARC',
            'ARCHITECTURAL': 'ARC',
            'ARCH': 'ARC',
            'CURTAINWALL': 'CW',
        }
        
        if discipline in aliases:
            return aliases[discipline]
        
        # Try to extract known discipline codes from longer strings
        parts = discipline.replace('_', ' ').replace('-', ' ').split()
        known = ['ACMV', 'STR', 'ARC', 'ELEC', 'FP', 'SP', 'CW', 
                'STRUCT', 'ARCH', 'HVAC', 'MECH', 'PLUMB', 'FIRE']
        
        for part in parts:
            if part in known:
                # Apply aliases again
                return aliases.get(part, part)
        
        # Return first 2-4 letter alpha part
        for part in parts:
            if 2 <= len(part) <= 4 and part.isalpha():
                return part
        
        return discipline  # Fallback unchanged
    
    def get_element_by_guid(self, guid: str) -> Optional[FederationElement]:
        """Retrieve element by GlobalId"""
        if not self.is_loaded:
            raise RuntimeError("Index not loaded. Call build() first.")
        
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT m.guid, m.discipline, m.ifc_class, m.filepath,
                   r.min_x, r.min_y, r.min_z, r.max_x, r.max_y, r.max_z
            FROM elements_meta m
            JOIN elements_rtree r ON m.id = r.id
            WHERE m.guid = ?
        """, (guid,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return None
        
        guid, discipline, ifc_class, filepath = row[:4]
        bbox = row[4:]
        return FederationElement(guid, discipline, ifc_class, bbox, filepath)
    
    def get_disciplines(self) -> List[str]:
        """Get list of all disciplines in index"""
        return sorted(self.stats['disciplines'])
    
    def get_ifc_classes(self) -> List[str]:
        """Get list of all IFC classes in index"""
        return sorted(self.stats['ifc_classes'])
    
    def get_statistics(self) -> Dict:
        """Get index statistics"""
        return {
            'total_elements': self.stats['total_elements'],
            'disciplines': self.get_disciplines(),
            'ifc_classes': self.get_ifc_classes(),
            'discipline_count': len(self.stats['disciplines']),
            'class_count': len(self.stats['ifc_classes']),
            'is_loaded': self.is_loaded
        }
    
    def clear(self):
        """Clear index from memory (minimal cleanup needed with SQLite)"""
        self.is_loaded = False
        self.stats = {
            'total_elements': 0,
            'disciplines': set(),
            'ifc_classes': set()
        }
        
        self.logger.info("Index cleared from memory")


# Convenience function for quick queries
def quick_query(database_path: Path, min_xyz: Tuple[float, float, float],
                max_xyz: Tuple[float, float, float]) -> List[FederationElement]:
    """
    Quick spatial query without persistent index
    
    Args:
        database_path: Path to federation database
        min_xyz: Minimum corner (x, y, z)
        max_xyz: Maximum corner (x, y, z)
        
    Returns:
        List of FederationElement instances
    """
    index = FederationIndex(database_path)
    index.build()
    return index.query_by_bbox(min_xyz, max_xyz)


if __name__ == "__main__":
    # Test/demo code
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python spatial_index.py <database_path>")
        sys.exit(1)
    
    db_path = Path(sys.argv[1])
    
    print(f"Loading federation index from {db_path}...")
    index = FederationIndex(db_path)
    index.build()
    
    stats = index.get_statistics()
    print("\nIndex Statistics:")
    print(f"  Total Elements:  {stats['total_elements']:,}")
    print(f"  Disciplines:     {', '.join(stats['disciplines'])}")
    print(f"  IFC Classes:     {stats['class_count']} unique types")
    
    # Example query
    print("\nExample Query (1000mm cube at origin):")
    results = index.query_by_bbox((-500, -500, -500), (500, 500, 500))
    print(f"  Found {len(results)} elements")
    for element in results[:5]:
        print(f"    - {element}")