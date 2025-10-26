"""
Coordinate System Utilities for IFC Federation
===============================================

Manages conversions between IFC, database, and viewport coordinate systems.

Coordinate Systems:
  - IFC:      Absolute world coords in METERS (e.g., -50433, 34188, 8)
  - Database: Absolute world coords in MILLIMETERS (e.g., -50433000, 34188000, 8000)
  - Viewport: Offset-relative coords in METERS (e.g., 0, 0, 0 at site center)

The global offset is stored in the database's `global_offset` table and represents
the site center point. All viewport coordinates have this offset subtracted to
center the model at the origin for better navigation in Blender.

Usage:
    from coordinate_utils import CoordinateSystem

    coords = CoordinateSystem("/path/to/federation.db")

    # User clicks at (50, 30, 12) in viewport
    click_pos = (50, 30, 12)

    # Query R-tree for obstacles (need millimeters)
    query_bbox_mm = coords.viewport_to_db(click_pos)
    # Returns absolute coords in mm for database query

    # Convert database result back to viewport
    db_bbox = (-50383500, 34218100, 20400, -50383000, 34218600, 20900)  # mm
    viewport_bbox = coords.db_bbox_to_viewport(db_bbox)
    # Returns offset-relative coords in meters for Blender
"""

import sqlite3
from typing import Tuple, List, Optional


class CoordinateSystem:
    """
    Coordinate system manager for IFC federation database.

    Handles conversions between three coordinate systems:
    1. IFC absolute (meters) - from IFC files
    2. Database R-tree (millimeters) - stored in database
    3. Viewport offset-relative (meters) - displayed in Blender
    """

    def __init__(self, db_path: str):
        """
        Load global offset from database.

        Args:
            db_path: Path to federation database

        Raises:
            ValueError: If global offset not found in database
        """
        self.db_path = db_path
        self._load_offset()

    def _load_offset(self):
        """Load offset from database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT offset_x, offset_y, offset_z FROM global_offset WHERE id = 1")
            row = cursor.fetchone()

            if not row:
                raise ValueError(
                    f"Global offset not found in database: {self.db_path}\n"
                    "Run extraction script to calculate offset."
                )

            self.offset_x, self.offset_y, self.offset_z = row
        finally:
            conn.close()

    def get_offset(self) -> Tuple[float, float, float]:
        """
        Get the global offset in meters.

        Returns:
            (offset_x, offset_y, offset_z) in meters
        """
        return (self.offset_x, self.offset_y, self.offset_z)

    # =========================================================================
    # IFC ↔ Viewport Conversions (both in meters)
    # =========================================================================

    def ifc_to_viewport(self, xyz: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """
        Convert IFC absolute coords (meters) to viewport offset-relative (meters).

        Args:
            xyz: (x, y, z) in IFC absolute coordinates

        Returns:
            (x, y, z) in viewport offset-relative coordinates
        """
        x, y, z = xyz
        return (
            x - self.offset_x,
            y - self.offset_y,
            z - self.offset_z
        )

    def viewport_to_ifc(self, xyz: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """
        Convert viewport offset-relative (meters) to IFC absolute (meters).

        Args:
            xyz: (x, y, z) in viewport offset-relative coordinates

        Returns:
            (x, y, z) in IFC absolute coordinates
        """
        x, y, z = xyz
        return (
            x + self.offset_x,
            y + self.offset_y,
            z + self.offset_z
        )

    # =========================================================================
    # Viewport ↔ Database Conversions (meters ↔ millimeters)
    # =========================================================================

    def viewport_to_db(self, xyz: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """
        Convert viewport (meters) to database R-tree coords (millimeters).

        Args:
            xyz: (x, y, z) in viewport offset-relative meters

        Returns:
            (x, y, z) in database absolute millimeters
        """
        # First convert to IFC absolute meters
        ifc_coords = self.viewport_to_ifc(xyz)
        # Then convert to millimeters
        return (
            ifc_coords[0] * 1000,
            ifc_coords[1] * 1000,
            ifc_coords[2] * 1000
        )

    def db_to_viewport(self, xyz: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """
        Convert database R-tree coords (millimeters) to viewport (meters).

        Args:
            xyz: (x, y, z) in database absolute millimeters

        Returns:
            (x, y, z) in viewport offset-relative meters
        """
        # First convert to meters
        ifc_coords = (
            xyz[0] / 1000,
            xyz[1] / 1000,
            xyz[2] / 1000
        )
        # Then convert to viewport offset-relative
        return self.ifc_to_viewport(ifc_coords)

    # =========================================================================
    # IFC ↔ Database Conversions (meters ↔ millimeters)
    # =========================================================================

    def ifc_to_db(self, xyz: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """
        Convert IFC absolute (meters) to database (millimeters).

        Args:
            xyz: (x, y, z) in IFC absolute meters

        Returns:
            (x, y, z) in database absolute millimeters
        """
        return (xyz[0] * 1000, xyz[1] * 1000, xyz[2] * 1000)

    def db_to_ifc(self, xyz: Tuple[float, float, float]) -> Tuple[float, float, float]:
        """
        Convert database (millimeters) to IFC absolute (meters).

        Args:
            xyz: (x, y, z) in database absolute millimeters

        Returns:
            (x, y, z) in IFC absolute meters
        """
        return (xyz[0] / 1000, xyz[1] / 1000, xyz[2] / 1000)

    # =========================================================================
    # Bounding Box Conversions
    # =========================================================================

    def viewport_bbox_to_db(self, bbox: Tuple[float, float, float, float, float, float]
                           ) -> Tuple[float, float, float, float, float, float]:
        """
        Convert viewport bbox to database bbox.

        Args:
            bbox: (min_x, min_y, min_z, max_x, max_y, max_z) in viewport meters

        Returns:
            (min_x, min_y, min_z, max_x, max_y, max_z) in database millimeters
        """
        min_x, min_y, min_z, max_x, max_y, max_z = bbox

        min_db = self.viewport_to_db((min_x, min_y, min_z))
        max_db = self.viewport_to_db((max_x, max_y, max_z))

        return (min_db[0], min_db[1], min_db[2], max_db[0], max_db[1], max_db[2])

    def db_bbox_to_viewport(self, bbox: Tuple[float, float, float, float, float, float]
                           ) -> Tuple[float, float, float, float, float, float]:
        """
        Convert database bbox to viewport bbox.

        Args:
            bbox: (min_x, min_y, min_z, max_x, max_y, max_z) in database millimeters

        Returns:
            (min_x, min_y, min_z, max_x, max_y, max_z) in viewport meters
        """
        min_x, min_y, min_z, max_x, max_y, max_z = bbox

        min_viewport = self.db_to_viewport((min_x, min_y, min_z))
        max_viewport = self.db_to_viewport((max_x, max_y, max_z))

        return (min_viewport[0], min_viewport[1], min_viewport[2],
                max_viewport[0], max_viewport[1], max_viewport[2])

    # =========================================================================
    # List Conversions (for multiple points)
    # =========================================================================

    def viewport_points_to_db(self, points: List[Tuple[float, float, float]]
                             ) -> List[Tuple[float, float, float]]:
        """
        Convert list of viewport points to database coords.

        Args:
            points: List of (x, y, z) in viewport meters

        Returns:
            List of (x, y, z) in database millimeters
        """
        return [self.viewport_to_db(p) for p in points]

    def db_points_to_viewport(self, points: List[Tuple[float, float, float]]
                             ) -> List[Tuple[float, float, float]]:
        """
        Convert list of database points to viewport coords.

        Args:
            points: List of (x, y, z) in database millimeters

        Returns:
            List of (x, y, z) in viewport meters
        """
        return [self.db_to_viewport(p) for p in points]

    # =========================================================================
    # Utility Functions
    # =========================================================================

    def expand_bbox(self, bbox: Tuple[float, float, float, float, float, float],
                   margin: float) -> Tuple[float, float, float, float, float, float]:
        """
        Expand bounding box by margin (in same units as bbox).

        Args:
            bbox: (min_x, min_y, min_z, max_x, max_y, max_z)
            margin: Amount to expand in each direction

        Returns:
            Expanded bbox
        """
        min_x, min_y, min_z, max_x, max_y, max_z = bbox
        return (
            min_x - margin,
            min_y - margin,
            min_z - margin,
            max_x + margin,
            max_y + margin,
            max_z + margin
        )

    def bbox_center(self, bbox: Tuple[float, float, float, float, float, float]
                   ) -> Tuple[float, float, float]:
        """
        Calculate center point of bbox.

        Args:
            bbox: (min_x, min_y, min_z, max_x, max_y, max_z)

        Returns:
            (center_x, center_y, center_z)
        """
        min_x, min_y, min_z, max_x, max_y, max_z = bbox
        return (
            (min_x + max_x) / 2,
            (min_y + max_y) / 2,
            (min_z + max_z) / 2
        )

    def bbox_dimensions(self, bbox: Tuple[float, float, float, float, float, float]
                       ) -> Tuple[float, float, float]:
        """
        Calculate dimensions of bbox.

        Args:
            bbox: (min_x, min_y, min_z, max_x, max_y, max_z)

        Returns:
            (width, depth, height)
        """
        min_x, min_y, min_z, max_x, max_y, max_z = bbox
        return (
            max_x - min_x,
            max_y - min_y,
            max_z - min_z
        )

    def __repr__(self) -> str:
        """String representation."""
        return f"CoordinateSystem(offset=({self.offset_x:.2f}, {self.offset_y:.2f}, {self.offset_z:.2f})m)"


# =============================================================================
# Standalone Functions (for use without object instantiation)
# =============================================================================

def meters_to_mm(value: float) -> float:
    """Convert meters to millimeters."""
    return value * 1000

def mm_to_meters(value: float) -> float:
    """Convert millimeters to meters."""
    return value / 1000

def meters_to_mm_vec(xyz: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Convert (x,y,z) from meters to millimeters."""
    return (xyz[0] * 1000, xyz[1] * 1000, xyz[2] * 1000)

def mm_to_meters_vec(xyz: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Convert (x,y,z) from millimeters to meters."""
    return (xyz[0] / 1000, xyz[1] / 1000, xyz[2] / 1000)


# =============================================================================
# Testing / Example Usage
# =============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python coordinate_utils.py <database_path>")
        print("\nExample:")
        print("  python coordinate_utils.py /home/red1/Documents/bonsai/DatabaseFiles/IFCmigrated_IFC4_v2.db")
        sys.exit(1)

    db_path = sys.argv[1]

    try:
        coords = CoordinateSystem(db_path)
        print(f"\n{coords}")
        print(f"\nOffset: ({coords.offset_x:.2f}, {coords.offset_y:.2f}, {coords.offset_z:.2f}) meters")

        # Example conversions
        print("\n" + "="*80)
        print("Example Conversions:")
        print("="*80)

        # Viewport point
        viewport_point = (50.0, 30.0, 12.0)
        print(f"\nViewport point: {viewport_point}")

        # To IFC
        ifc_point = coords.viewport_to_ifc(viewport_point)
        print(f"  → IFC absolute: ({ifc_point[0]:.2f}, {ifc_point[1]:.2f}, {ifc_point[2]:.2f}) meters")

        # To Database
        db_point = coords.viewport_to_db(viewport_point)
        print(f"  → Database: ({db_point[0]:.0f}, {db_point[1]:.0f}, {db_point[2]:.0f}) millimeters")

        # Back to viewport
        back_to_viewport = coords.db_to_viewport(db_point)
        print(f"  → Back to viewport: ({back_to_viewport[0]:.2f}, {back_to_viewport[1]:.2f}, {back_to_viewport[2]:.2f}) meters")

        # Verify round-trip
        assert abs(back_to_viewport[0] - viewport_point[0]) < 0.001
        assert abs(back_to_viewport[1] - viewport_point[1]) < 0.001
        assert abs(back_to_viewport[2] - viewport_point[2]) < 0.001
        print("  ✓ Round-trip conversion verified!")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
