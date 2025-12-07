"""
Place Equipment - SIMPLE (No Overcomplicated Conversions)
==========================================================
1. Read vertices from DB
2. Place equipment AT those coordinates
3. GPS is just metadata calculation
"""

import sqlite3
import struct
from pathlib import Path
from datetime import datetime


# GPS bounds for metadata calculation only
GPS_LON_MIN = 101.39
GPS_LON_MAX = 101.75
GPS_LAT_MIN = 3.00
GPS_LAT_MAX = 3.20


def get_river_vertices(db_path):
    """Read vertices directly from database"""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT vertices, vertex_count FROM base_geometries LIMIT 1")
    vertices_blob, vertex_count = cursor.fetchone()

    conn.close()

    # Decode vertices: X, Y, Z
    vertices = []
    for i in range(vertex_count):
        offset = i * 12  # 3 floats * 4 bytes
        x, y, z = struct.unpack('fff', vertices_blob[offset:offset+12])
        vertices.append((x, y, z))

    print(f"✓ Read {len(vertices)} vertices from river mesh")
    return vertices


def calculate_gps_metadata(x, y, x_min, x_max, y_min, y_max):
    """Calculate GPS coordinates for metadata (not used for placement)"""

    # Normalize to 0-1
    x_norm = (x - x_min) / (x_max - x_min)
    y_norm = (y - y_min) / (y_max - y_min)

    # Scale to GPS range
    lon = GPS_LON_MIN + x_norm * (GPS_LON_MAX - GPS_LON_MIN)
    lat = GPS_LAT_MIN + y_norm * (GPS_LAT_MAX - GPS_LAT_MIN)

    return lat, lon


def place_equipment(db_path, vertices, num_equipment=90):
    """Place equipment at vertex positions"""

    # Pick every Nth vertex
    step = len(vertices) // num_equipment

    # Get coordinate bounds for GPS calculation
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Delete old equipment
    cursor.execute("DELETE FROM project_markers WHERE marker_id >= 171")

    equipment_types = [
        ('boom_trap', 'Boom Station'),
        ('water_quality', 'WQ Sensor'),
        ('biochar', 'Biochar Unit'),
        ('mrf', 'MRF Facility'),
        ('pollutant_sensor', 'Pollutant Monitor'),
        ('flood_monitor', 'Flood Sensor'),
        ('wildlife_camera', 'Wildlife Cam')
    ]

    marker_id = 171
    for i in range(num_equipment):
        # Get vertex position
        vertex_idx = i * step
        if vertex_idx >= len(vertices):
            vertex_idx = len(vertices) - 1

        x, y, z = vertices[vertex_idx]

        # Calculate GPS metadata
        lat, lon = calculate_gps_metadata(x, y, x_min, x_max, y_min, y_max)

        # Equipment type
        eq_type, eq_name = equipment_types[i % len(equipment_types)]
        eq_num = (i // len(equipment_types)) + 1

        # Insert equipment AT vertex position
        cursor.execute("""
            INSERT INTO project_markers (
                marker_id, marker_type, name, description,
                location_x, location_y, location_z,
                latitude, longitude, gps_elevation,
                color, status, installation_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            marker_id,
            eq_type,
            f"{eq_name} {eq_num}",
            f"Klang River equipment {marker_id}",
            x, y, z,  # Use vertex coordinates directly
            lat, lon, 0.0,
            '#FF6B35',
            'ACTIVE',
            datetime.now().isoformat()
        ))

        marker_id += 1

    conn.commit()
    conn.close()

    print(f"✓ Placed {num_equipment} equipment at vertex positions")


def main():
    db_path = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db")

    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        return

    print("="*80)
    print("SIMPLE EQUIPMENT PLACEMENT")
    print("="*80)
    print("\n1. Read vertices from mesh")
    print("2. Place equipment at those positions")
    print("3. GPS is just metadata")
    print()

    # Step 1: Get vertices
    vertices = get_river_vertices(db_path)

    # Step 2: Place equipment
    place_equipment(db_path, vertices, num_equipment=90)

    print("\n" + "="*80)
    print("DONE")
    print("="*80)
    print("Equipment placed at river mesh vertex positions")
    print("No conversions, no transforms, no complexity")
    print("\nTest in Blender: Load from DB")


if __name__ == '__main__':
    main()
