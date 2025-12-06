#!/usr/bin/env python3
"""
Extract the actual river mesh from klang_river_perfect.db (Blender source)
and create a proper outline GeoJSON matching what's shown in Blender
"""

import sqlite3
import json
import struct
import numpy as np

def extract_vertices_from_database(db_path):
    """Extract river vertices from database"""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get geometry data
    cursor.execute("SELECT vertices FROM base_geometries LIMIT 1")
    row = cursor.fetchone()

    if not row:
        print("No geometry found!")
        return None

    vertices_blob = row[0]

    # Unpack vertices (float32 × 3 per vertex)
    num_vertices = len(vertices_blob) // (4 * 3)
    vertices = struct.unpack(f'{num_vertices * 3}f', vertices_blob)
    vertices = np.array(vertices).reshape(-1, 3)

    conn.close()

    print(f"✓ Extracted {len(vertices)} vertices from database")
    print(f"  X range: {vertices[:, 0].min():.2f} to {vertices[:, 0].max():.2f}")
    print(f"  Y range: {vertices[:, 1].min():.2f} to {vertices[:, 1].max():.2f}")
    print(f"  Z range: {vertices[:, 2].min():.2f} to {vertices[:, 2].max():.2f}")

    return vertices

def create_alpha_shape(vertices, alpha=500):
    """Create concave hull (alpha shape) to preserve river curves"""

    # Use only X, Y coordinates
    points_2d = vertices[:, :2]

    # Simple approach: bin vertices by longitude and find min/max latitude
    # This creates top and bottom boundaries

    # Sort by X coordinate
    sorted_indices = np.argsort(points_2d[:, 0])
    sorted_points = points_2d[sorted_indices]

    # Create bins along X axis
    x_min, x_max = sorted_points[:, 0].min(), sorted_points[:, 0].max()
    num_bins = 200  # More bins = more detail
    bin_width = (x_max - x_min) / num_bins

    top_boundary = []
    bottom_boundary = []

    for bin_idx in range(num_bins + 1):
        bin_x = x_min + bin_idx * bin_width

        # Find points in this bin
        mask = (sorted_points[:, 0] >= bin_x - bin_width/2) & (sorted_points[:, 0] < bin_x + bin_width/2)
        bin_points = sorted_points[mask]

        if len(bin_points) > 0:
            # Top boundary: max Y
            max_idx = np.argmax(bin_points[:, 1])
            top_boundary.append(bin_points[max_idx])

            # Bottom boundary: min Y
            min_idx = np.argmin(bin_points[:, 1])
            bottom_boundary.append(bin_points[min_idx])

    # Combine: top boundary left to right + bottom boundary right to left
    outline = np.vstack([
        np.array(top_boundary),
        np.array(bottom_boundary[::-1])
    ])

    print(f"✓ Created alpha shape outline with {len(outline)} points")

    return outline

def simplify_polygon(vertices, tolerance=100):
    """Simplify polygon using Douglas-Peucker algorithm"""

    def perpendicular_distance(point, line_start, line_end):
        if np.array_equal(line_start, line_end):
            return np.linalg.norm(point - line_start)

        n = np.linalg.norm(line_end - line_start)
        return np.abs(np.cross(line_end - line_start, line_start - point)) / n

    def douglas_peucker(points, tolerance):
        if len(points) < 3:
            return points

        # Find point with maximum distance
        dmax = 0
        index = 0
        for i in range(1, len(points) - 1):
            d = perpendicular_distance(points[i], points[0], points[-1])
            if d > dmax:
                index = i
                dmax = d

        # If max distance is greater than tolerance, recursively simplify
        if dmax > tolerance:
            rec1 = douglas_peucker(points[:index+1], tolerance)
            rec2 = douglas_peucker(points[index:], tolerance)
            return np.vstack([rec1[:-1], rec2])
        else:
            return np.array([points[0], points[-1]])

    simplified = douglas_peucker(vertices, tolerance)
    print(f"✓ Simplified from {len(vertices)} to {len(simplified)} points")

    return simplified

def vertices_to_latlon(vertices):
    """Convert local GI coordinates to lat/lon"""

    # Get bounds
    x_min, x_max = vertices[:, 0].min(), vertices[:, 0].max()
    y_min, y_max = vertices[:, 1].min(), vertices[:, 1].max()

    print(f"  Local bounds: X [{x_min:.2f}, {x_max:.2f}], Y [{y_min:.2f}, {y_max:.2f}]")

    # Real Klang River lat/lon bounds (from actual OSM data)
    lon_min, lon_max = 101.308962, 101.589087
    lat_min, lat_max = 2.946933, 3.095605

    # Convert
    latlons = []
    for v in vertices:
        x_norm = (v[0] - x_min) / (x_max - x_min) if x_max != x_min else 0.5
        y_norm = (v[1] - y_min) / (y_max - y_min) if y_max != y_min else 0.5

        lon = lon_min + x_norm * (lon_max - lon_min)
        lat = lat_min + y_norm * (lat_max - lat_min)

        latlons.append([lon, lat])

    return latlons

def create_geojson(outline_coords, output_path):
    """Create GeoJSON polygon from outline coordinates"""

    # Close the ring
    if outline_coords[0] != outline_coords[-1]:
        outline_coords.append(outline_coords[0])

    geojson = {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [outline_coords]
        },
        "properties": {
            "name": "Klang River",
            "source": "klang_river_perfect.db (Blender mesh)",
            "length_km": 40.5,
            "vertices": len(outline_coords)
        }
    }

    with open(output_path, 'w') as f:
        json.dump(geojson, f, indent=2)

    print(f"\n✓ Created river outline GeoJSON: {output_path}")
    print(f"  Polygon: {len(outline_coords)} points")

if __name__ == "__main__":
    db_path = "/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db"
    output_path = "/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/output/geojson/river_from_blender.geojson"

    print("Extracting vertices from database...")
    vertices = extract_vertices_from_database(db_path)

    if vertices is None:
        exit(1)

    print("\nCreating concave outline (alpha shape)...")
    outline_2d = create_alpha_shape(vertices, alpha=500)

    print("\nSimplifying polygon...")
    simplified = simplify_polygon(outline_2d, tolerance=100)

    print("\nConverting to lat/lon...")
    latlon_coords = vertices_to_latlon(simplified)

    print("\nCreating GeoJSON...")
    create_geojson(latlon_coords, output_path)

    print("\n✓ Done! River outline extracted from Blender mesh.")
