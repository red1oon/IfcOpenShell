#!/usr/bin/env python3
"""
Reposition project markers along the actual river path from OSM GeoJSON
This fixes the alignment issue where markers don't follow the river
"""

import sqlite3
import json
import math

def distance_2d(p1, p2):
    """Calculate 2D distance"""
    return math.sqrt((p2[0] - p1[0])**2 + (p2[1] - p1[1])**2)

def extract_river_path(geojson_path):
    """Extract a representative path through river polygons"""

    with open(geojson_path) as f:
        data = json.load(f)

    # Handle both Feature and FeatureCollection
    features = data['features'] if 'features' in data else [data]

    # Collect all river polygon coordinates
    all_coords = []
    for feature in features:
        geom = feature['geometry']
        if geom['type'] == 'Polygon':
            coords = geom['coordinates'][0]
            all_coords.extend(coords)
        elif geom['type'] == 'MultiPolygon':
            for poly_coords in geom['coordinates']:
                coords = poly_coords[0]
                all_coords.extend(coords)

    if not all_coords:
        print("No coordinates found!")
        return None

    print(f"✓ Loaded {len(all_coords)} total coordinates from river polygons")

    # Get bounds
    lons = [c[0] for c in all_coords]
    lats = [c[1] for c in all_coords]

    print(f"  Lon range: {min(lons):.6f} to {max(lons):.6f}")
    print(f"  Lat range: {min(lats):.6f} to {max(lats):.6f}")

    # Create path by sorting coordinates from west to east (following river flow direction)
    # Group by longitude bins
    num_bins = 100
    lon_min, lon_max = min(lons), max(lons)
    bin_width = (lon_max - lon_min) / num_bins

    bins = {}
    for coord in all_coords:
        bin_idx = int((coord[0] - lon_min) / bin_width) if bin_width > 0 else 0
        if bin_idx not in bins:
            bins[bin_idx] = []
        bins[bin_idx].append(coord)

    # Create path using bin centroids
    path = []
    for bin_idx in sorted(bins.keys()):
        coords_in_bin = bins[bin_idx]
        # Use centroid of coords in this bin
        avg_lon = sum(c[0] for c in coords_in_bin) / len(coords_in_bin)
        avg_lat = sum(c[1] for c in coords_in_bin) / len(coords_in_bin)
        path.append([avg_lon, avg_lat])

    print(f"  Created path with {len(path)} points")

    return path

def get_markers_from_database(db_path):
    """Get marker metadata from database"""

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            marker_id,
            marker_type,
            name,
            description,
            color,
            pulse_rate,
            priority
        FROM project_markers
        ORDER BY marker_id
    """)

    markers = [dict(row) for row in cursor.fetchall()]
    conn.close()

    return markers

def interpolate_along_path(path, distance_fraction):
    """Interpolate a point along a path at given fraction (0.0 to 1.0)"""

    # Calculate cumulative distances
    distances = [0.0]
    for i in range(1, len(path)):
        d = distance_2d(path[i-1], path[i])
        distances.append(distances[-1] + d)

    total_length = distances[-1]
    target_distance = distance_fraction * total_length

    # Find segment containing target distance
    for i in range(1, len(distances)):
        if distances[i] >= target_distance:
            # Interpolate between path[i-1] and path[i]
            segment_start = distances[i-1]
            segment_length = distances[i] - distances[i-1]
            segment_fraction = (target_distance - segment_start) / segment_length if segment_length > 0 else 0.0

            lon = path[i-1][0] + segment_fraction * (path[i][0] - path[i-1][0])
            lat = path[i-1][1] + segment_fraction * (path[i][1] - path[i-1][1])

            return [lon, lat]

    # If beyond end, return last point
    return path[-1]

def position_markers_on_path(markers, path):
    """Position markers evenly along path"""

    num_markers = len(markers)
    positioned = []

    for i, marker in enumerate(markers):
        # Position along path (evenly spaced)
        fraction = i / (num_markers - 1) if num_markers > 1 else 0.5
        point = interpolate_along_path(path, fraction)

        marker_copy = marker.copy()
        marker_copy['lon'] = point[0]
        marker_copy['lat'] = point[1]

        positioned.append(marker_copy)

    return positioned

def create_geojson(markers, output_path):
    """Create GeoJSON from positioned markers"""

    features = []

    for marker in markers:
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [marker['lon'], marker['lat']]
            },
            "properties": {
                "id": marker['marker_id'],
                "type": marker['marker_type'],
                "name": marker['name'],
                "priority": marker['priority'],
                "color": marker['color'],
                "pulse_rate": marker['pulse_rate'],
                "description": marker['description']
            }
        }
        features.append(feature)

    geojson = {
        "type": "FeatureCollection",
        "features": features
    }

    with open(output_path, 'w') as f:
        json.dump(geojson, f, indent=2)

    print(f"\n✓ Created {len(features)} positioned markers")
    print(f"  Output: {output_path}")

if __name__ == "__main__":
    river_geojson = "/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/output/geojson/river_from_blender.geojson"
    db_path = "/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db"
    output_path = "/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/output/geojson/project_markers.geojson"

    print("Extracting river path...")
    river_path = extract_river_path(river_geojson)

    if river_path is None:
        print("Failed to extract path")
        exit(1)

    print("\nGetting markers from database...")
    markers = get_markers_from_database(db_path)
    print(f"✓ Found {len(markers)} markers")

    print("\nPositioning markers along river...")
    positioned_markers = position_markers_on_path(markers, river_path)

    print("\nCreating GeoJSON...")
    create_geojson(positioned_markers, output_path)

    print("\n✓ Done! Markers now aligned with river path.")
