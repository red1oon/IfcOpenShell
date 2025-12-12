# Bonsai - OpenBIM Blender Add-on
# River Map Viewport - Viewport-aware tile system for Google Maps
# Implements intelligent tile loading based on 3D viewport bounds

"""
River Map Viewport - Viewport-aware Tile System
===============================================
Dynamically loads Google Maps tiles based on current 3D viewport bounds,
providing seamless georeferenced background imagery at any zoom level.

Features:
- Automatic viewport bounds detection
- GPS coordinate conversion (Blender XY ↔ lat/lon)
- Intelligent zoom level selection
- Tile grid generation for coverage
- Aggressive caching with cost tracking
"""

import bpy
from mathutils import Vector
from bpy_extras.view3d_utils import region_2d_to_location_3d, region_2d_to_vector_3d
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import math


# =============================================================================
# GPS COORDINATE CONVERTER
# =============================================================================

class GPSConverter:
    """Convert between Blender XY coordinates and GPS lat/lon"""

    def __init__(self, db_path: Path):
        """Initialize converter with georef config from database"""
        self.db_path = db_path
        self.load_georef_config()

    def load_georef_config(self):
        """Load georeferencing configuration from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM georef_config LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise ValueError("No georef_config found in database")

        # Parse georef data (id, crs, x_min, x_max, y_min, y_max, lon_min, lon_max, lat_min, lat_max)
        self.blender_x_min = row[2]
        self.blender_x_max = row[3]
        self.blender_y_min = row[4]
        self.blender_y_max = row[5]
        self.lon_min = row[6]
        self.lon_max = row[7]
        self.lat_min = row[8]
        self.lat_max = row[9]

        # Calculate conversion factors
        self.blender_x_range = self.blender_x_max - self.blender_x_min
        self.blender_y_range = self.blender_y_max - self.blender_y_min
        self.lon_range = self.lon_max - self.lon_min
        self.lat_range = self.lat_max - self.lat_min

        print(f"GPSConverter initialized:")
        print(f"  Blender bounds: X={self.blender_x_min:.1f}-{self.blender_x_max:.1f}, Y={self.blender_y_min:.1f}-{self.blender_y_max:.1f}")
        print(f"  GPS bounds: Lat={self.lat_min:.6f}-{self.lat_max:.6f}, Lon={self.lon_min:.6f}-{self.lon_max:.6f}")

    def blender_to_gps(self, x: float, y: float) -> Tuple[float, float]:
        """Convert Blender XY to GPS lat/lon"""
        # Normalize to 0-1 range
        norm_x = (x - self.blender_x_min) / self.blender_x_range
        norm_y = (y - self.blender_y_min) / self.blender_y_range

        # Map to GPS coordinates
        lon = self.lon_min + norm_x * self.lon_range
        lat = self.lat_min + norm_y * self.lat_range

        return lat, lon

    def gps_to_blender(self, lat: float, lon: float) -> Tuple[float, float]:
        """Convert GPS lat/lon to Blender XY"""
        # Normalize to 0-1 range
        norm_lon = (lon - self.lon_min) / self.lon_range
        norm_lat = (lat - self.lat_min) / self.lat_range

        # Map to Blender coordinates
        x = self.blender_x_min + norm_lon * self.blender_x_range
        y = self.blender_y_min + norm_lat * self.blender_y_range

        return x, y

    def blender_bounds_to_gps_bounds(self, x_min: float, x_max: float, y_min: float, y_max: float) -> Dict[str, float]:
        """Convert Blender bounding box to GPS bounds"""
        # Get all four corners
        lat_sw, lon_sw = self.blender_to_gps(x_min, y_min)  # Southwest
        lat_ne, lon_ne = self.blender_to_gps(x_max, y_max)  # Northeast

        return {
            'lat_min': lat_sw,
            'lat_max': lat_ne,
            'lon_min': lon_sw,
            'lon_max': lon_ne
        }


# =============================================================================
# VIEWPORT BOUNDS DETECTOR
# =============================================================================

class ViewportBoundsDetector:
    """Detect 3D viewport bounds and calculate GPS coverage"""

    @staticmethod
    def get_viewport_region(context):
        """Get 3D viewport region"""
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        for space in area.spaces:
                            if space.type == 'VIEW_3D':
                                return region, space.region_3d
        return None, None

    @staticmethod
    def calculate_viewport_blender_bounds(context) -> Optional[Dict[str, float]]:
        """Calculate viewport bounds in Blender coordinates (projected to Z=0)"""
        region, rv3d = ViewportBoundsDetector.get_viewport_region(context)

        if not region or not rv3d:
            print("❌ Could not find 3D viewport")
            return None

        # Get viewport corners (2D screen coordinates)
        width = region.width
        height = region.height

        corners_2d = [
            (0, 0),           # Bottom-left
            (width, 0),       # Bottom-right
            (width, height),  # Top-right
            (0, height)       # Top-left
        ]

        # Project corners to 3D world space at Z=0 (river plane)
        corners_3d = []
        for x, y in corners_2d:
            # Get ray from screen point
            view_vector = region_2d_to_vector_3d(region, rv3d, (x, y))
            ray_origin = rv3d.view_matrix.inverted().translation

            # Intersect with Z=0 plane
            # ray_origin + t * view_vector, where Z = 0
            # ray_origin.z + t * view_vector.z = 0
            # t = -ray_origin.z / view_vector.z

            if abs(view_vector.z) > 1e-6:  # Avoid division by zero
                t = -ray_origin.z / view_vector.z
                intersection = ray_origin + t * view_vector
                corners_3d.append(intersection)
            else:
                # Parallel to Z=0, use fallback
                intersection = region_2d_to_location_3d(region, rv3d, (x, y), Vector((0, 0, 0)))
                corners_3d.append(intersection)

        # Extract X and Y bounds
        x_coords = [p.x for p in corners_3d]
        y_coords = [p.y for p in corners_3d]

        bounds = {
            'x_min': min(x_coords),
            'x_max': max(x_coords),
            'y_min': min(y_coords),
            'y_max': max(y_coords)
        }

        # Calculate viewport width for zoom level selection
        width_m = bounds['x_max'] - bounds['x_min']
        height_m = bounds['y_max'] - bounds['y_min']

        print(f"Viewport bounds (Blender): X=[{bounds['x_min']:.1f}, {bounds['x_max']:.1f}], Y=[{bounds['y_min']:.1f}, {bounds['y_max']:.1f}]")
        print(f"Viewport size: {width_m/1000:.2f}km × {height_m/1000:.2f}km")

        return bounds

    @staticmethod
    def get_viewport_gps_bounds(context, gps_converter: GPSConverter) -> Optional[Dict[str, float]]:
        """Get viewport bounds in GPS coordinates"""
        blender_bounds = ViewportBoundsDetector.calculate_viewport_blender_bounds(context)

        if not blender_bounds:
            return None

        gps_bounds = gps_converter.blender_bounds_to_gps_bounds(
            blender_bounds['x_min'],
            blender_bounds['x_max'],
            blender_bounds['y_min'],
            blender_bounds['y_max']
        )

        print(f"Viewport bounds (GPS): Lat=[{gps_bounds['lat_min']:.6f}, {gps_bounds['lat_max']:.6f}], Lon=[{gps_bounds['lon_min']:.6f}, {gps_bounds['lon_max']:.6f}]")

        return gps_bounds


# =============================================================================
# ZOOM LEVEL CALCULATOR
# =============================================================================

class ZoomLevelCalculator:
    """Calculate appropriate Google Maps zoom level for viewport"""

    @staticmethod
    def meters_per_pixel(lat: float, zoom: int) -> float:
        """Calculate meters per pixel at given latitude and zoom"""
        # Earth circumference at equator
        earth_circumference = 40075017  # meters

        # Meters per pixel = (Earth circumference * cos(latitude)) / (2^(zoom + 8))
        # Formula from Google Maps documentation
        meters_per_px = (earth_circumference * math.cos(math.radians(lat))) / (2 ** (zoom + 8))
        return meters_per_px

    @staticmethod
    def calculate_zoom_for_viewport(gps_bounds: Dict[str, float], viewport_width_m: float, tile_size_px: int = 640) -> int:
        """Calculate best zoom level to fill viewport with tiles"""
        # Use center latitude for calculation
        center_lat = (gps_bounds['lat_min'] + gps_bounds['lat_max']) / 2

        # Try different zoom levels and find best fit
        best_zoom = 12

        for zoom in range(1, 21):
            m_per_px = ZoomLevelCalculator.meters_per_pixel(center_lat, zoom)
            tile_coverage_m = tile_size_px * m_per_px

            # We want viewport to be covered by 2-4 tiles
            tiles_needed = viewport_width_m / tile_coverage_m

            if 2 <= tiles_needed <= 4:
                best_zoom = zoom
                break
            elif tiles_needed < 2:
                # Too zoomed in, use previous zoom
                best_zoom = max(1, zoom - 1)
                break

        return best_zoom

    @staticmethod
    def select_zoom_auto(blender_bounds: Dict[str, float]) -> int:
        """Automatically select zoom level based on viewport size"""
        width_m = blender_bounds['x_max'] - blender_bounds['x_min']

        # Zoom level strategy from spec
        if width_m > 50000:      # > 50km
            zoom = 12
        elif width_m > 10000:    # 10-50km
            zoom = 15
        elif width_m > 2000:     # 2-10km
            zoom = 18
        else:                    # < 2km
            zoom = 19

        print(f"Auto zoom: viewport width {width_m/1000:.2f}km → zoom {zoom}")
        return zoom


# =============================================================================
# TILE GRID GENERATOR
# =============================================================================

class TileGridGenerator:
    """Generate grid of map tiles to cover viewport"""

    @staticmethod
    def get_tile_size_degrees(zoom: int) -> float:
        """Calculate tile coverage in degrees at zoom level"""
        # Google Maps tile size at zoom level (approximate)
        # Each zoom level doubles resolution
        tile_size_deg = 360.0 / (2 ** zoom)
        return tile_size_deg

    @staticmethod
    def get_tile_size_meters(lat: float, zoom: int, tile_size_px: int = 640) -> Tuple[float, float]:
        """Calculate tile size in meters at given latitude and zoom"""
        m_per_px = ZoomLevelCalculator.meters_per_pixel(lat, zoom)

        # Tile size in meters
        tile_width_m = tile_size_px * m_per_px

        # Height varies with latitude (latitude lines get closer at poles)
        # For simplicity, use same as width (good enough for equatorial regions like Malaysia)
        tile_height_m = tile_width_m

        return tile_width_m, tile_height_m

    @staticmethod
    def generate_tile_grid(gps_bounds: Dict[str, float], zoom: int) -> List[Dict]:
        """Generate grid of tiles to cover GPS bounds"""
        lat_min = gps_bounds['lat_min']
        lat_max = gps_bounds['lat_max']
        lon_min = gps_bounds['lon_min']
        lon_max = gps_bounds['lon_max']

        # Calculate tile size in degrees
        tile_size_deg = TileGridGenerator.get_tile_size_degrees(zoom)

        # Calculate number of tiles needed
        lat_span = lat_max - lat_min
        lon_span = lon_max - lon_min

        tiles_y = int(lat_span / tile_size_deg) + 2  # +2 for overlap
        tiles_x = int(lon_span / tile_size_deg) + 2

        print(f"Tile grid: {tiles_x}×{tiles_y} tiles at zoom {zoom}")
        print(f"  Tile size: {tile_size_deg:.6f}° (≈{tile_size_deg*111:.1f}km at equator)")

        tiles = []
        for iy in range(tiles_y):
            for ix in range(tiles_x):
                # Tile center coordinates
                tile_lat = lat_min + (iy + 0.5) * tile_size_deg
                tile_lon = lon_min + (ix + 0.5) * tile_size_deg

                # Tile bounds
                tile = {
                    'lat': tile_lat,
                    'lon': tile_lon,
                    'lat_min': tile_lat - tile_size_deg / 2,
                    'lat_max': tile_lat + tile_size_deg / 2,
                    'lon_min': tile_lon - tile_size_deg / 2,
                    'lon_max': tile_lon + tile_size_deg / 2,
                    'zoom': zoom,
                    'ix': ix,
                    'iy': iy
                }

                tiles.append(tile)

        print(f"Generated {len(tiles)} tiles")
        return tiles


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_db_path() -> Path:
    """Get database path"""
    return Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db")


def test_viewport_detection(context):
    """Test function to verify viewport detection"""
    print("\n" + "="*70)
    print("🧪 TESTING VIEWPORT DETECTION")
    print("="*70)

    # Initialize converter
    db_path = get_db_path()
    converter = GPSConverter(db_path)

    # Get viewport bounds
    blender_bounds = ViewportBoundsDetector.calculate_viewport_blender_bounds(context)

    if not blender_bounds:
        print("❌ Failed to detect viewport bounds")
        return

    # Convert to GPS
    gps_bounds = ViewportBoundsDetector.get_viewport_gps_bounds(context, converter)

    # Calculate zoom level
    width_m = blender_bounds['x_max'] - blender_bounds['x_min']
    zoom = ZoomLevelCalculator.select_zoom_auto(blender_bounds)

    # Generate tile grid
    tiles = TileGridGenerator.generate_tile_grid(gps_bounds, zoom)

    print("\n✅ Viewport detection test complete!")
    print(f"   Viewport: {width_m/1000:.2f}km wide, zoom {zoom}, {len(tiles)} tiles")
    print("="*70 + "\n")
