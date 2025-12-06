#!/usr/bin/env python3
"""
Export project markers from klang_river_perfect.db to GeoJSON format
For use in RiverUI web viewer
"""

import sqlite3
import json
import sys

def export_markers_to_geojson(db_path, output_path):
    """Export project_markers table to GeoJSON FeatureCollection"""

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Query all markers
    cursor.execute("""
        SELECT
            marker_id,
            marker_type,
            name,
            location_x,
            location_y,
            priority,
            color,
            pulse_rate,
            description
        FROM project_markers
        ORDER BY marker_id
    """)

    markers = cursor.fetchall()

    # Convert local coordinates to lat/lon
    # Based on Klang River actual bounds (from river_klang.geojson)
    # Local coords: X: -21834 to +13853 (~35.7km), Y: -3915 to +14898 (~18.8km)
    # Lat/Lon bounds: Lon: 101.38 to 101.61, Lat: 2.93 to 3.04

    # Get marker bounds
    xs = [m['location_x'] for m in markers]
    ys = [m['location_y'] for m in markers]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    # Klang River lat/lon bounds (approximate)
    lon_min, lon_max = 101.38, 101.61
    lat_min, lat_max = 2.93, 3.04

    def local_to_latlon(x, y):
        """Convert local GI coordinates to lat/lon"""
        # Normalize to 0-1
        x_norm = (x - x_min) / (x_max - x_min) if x_max != x_min else 0.5
        y_norm = (y - y_min) / (y_max - y_min) if y_max != y_min else 0.5

        # Map to lat/lon
        lon = lon_min + x_norm * (lon_max - lon_min)
        lat = lat_min + y_norm * (lat_max - lat_min)

        return lon, lat

    # Build GeoJSON FeatureCollection
    features = []
    for marker in markers:
        lon, lat = local_to_latlon(marker['location_x'], marker['location_y'])

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat]
            },
            "properties": {
                "id": marker['marker_id'],
                "type": marker['marker_type'],
                "name": marker['name'],
                "priority": marker['priority'],
                "color": marker['color'],
                "pulse_rate": marker['pulse_rate'],
                "description": marker['description'],
                "local_x": round(marker['location_x'], 2),
                "local_y": round(marker['location_y'], 2)
            }
        }
        features.append(feature)

    geojson = {
        "type": "FeatureCollection",
        "features": features
    }

    # Write to file
    with open(output_path, 'w') as f:
        json.dump(geojson, f, indent=2)

    conn.close()

    print(f"✓ Exported {len(features)} markers to {output_path}")
    print(f"\nMarker types:")

    # Summary
    types = {}
    for marker in markers:
        mtype = marker['marker_type']
        types[mtype] = types.get(mtype, 0) + 1

    for mtype, count in sorted(types.items()):
        print(f"  {mtype:20s}: {count:3d}")

    print(f"\nTotal: {len(features)} markers")

if __name__ == "__main__":
    db_path = "/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db"
    output_path = "/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/output/geojson/project_markers.geojson"

    if len(sys.argv) > 1:
        output_path = sys.argv[1]

    export_markers_to_geojson(db_path, output_path)
