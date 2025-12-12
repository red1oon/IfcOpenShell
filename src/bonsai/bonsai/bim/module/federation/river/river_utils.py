#!/usr/bin/env python3
"""
River Utilities

Collection of utility functions for river monitoring equipment management
and validation in Blender federation models.
"""

import bpy
from collections import defaultdict
from pathlib import Path


# Path constants
RIVER_WORK_DIR = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER")
RIVER_DB_PATH = RIVER_WORK_DIR / "klang_river_perfect.db"

# Equipment type constants
EQUIPMENT_TYPE_MAPPING = {
    'boom_trap': ['boom_trap'],
    'water_quality': ['water_quality'],
    'biodiversity': ['biodiversity'],
    'wildlife_camera': ['wildlife'],
    'biochar_facility': ['biochar'],
    'mrf_site': ['mrf'],
    'pollutant_sensor': ['pollutant'],
    'flood_monitor': ['flood']
}

EQUIPMENT_COLORS_HEX = {
    'boom_trap': '#FF6B35',
    'water_quality': '#4ECDC4',
    'biodiversity': '#00FF00',
    'wildlife_camera': '#00FF00',
    'biochar_facility': '#99EDD9',
    'mrf_site': '#FFBFCC',
    'pollutant_sensor': '#AB96D7',
    'flood_monitor': '#5D9DD5'
}

EQUIPMENT_COLORS_KML = {
    'boom_trap': 'ff356bff',
    'water_quality': 'ffc4cd4e',
    'biodiversity': 'ff00ff00',
    'wildlife_camera': 'ff00ff00',
    'biochar_facility': 'ffd9ed99',
    'mrf_site': 'ffccbfff',
    'pollutant_sensor': 'ffd796ab',
    'flood_monitor': 'ffd59d5d'
}


def get_equipment_type(obj_name):
    """
    Determine equipment type from object name.

    Args:
        obj_name: Name of the equipment object

    Returns:
        str: Equipment type identifier
    """
    name_lower = obj_name.lower()
    for eq_type, keywords in EQUIPMENT_TYPE_MAPPING.items():
        if any(keyword in name_lower for keyword in keywords):
            return eq_type
    return 'boom_trap'  # Default fallback


def get_all_equipment_objects():
    """
    Get all equipment objects from the Blender scene.

    Returns:
        list: List of equipment objects
    """
    return [obj for obj in bpy.data.objects
            if obj.name.startswith(('BOOM_TRAP_', 'WATER_QUALITY_',
                                   'BIODIVERSITY_', 'WILDLIFE_',
                                   'BIOCHAR_', 'MRF_',
                                   'POLLUTANT_', 'FLOOD_MONITOR_'))]


def fetch_sensor_data_from_db(cursor, marker_name):
    """
    Fetch sensor data for a given equipment marker.

    Args:
        cursor: Database cursor
        marker_name: Name of the equipment marker

    Returns:
        list: List of sensor dictionaries with sensor data
    """
    cursor.execute("SELECT id FROM project_markers WHERE name = ?", (marker_name,))
    marker_row = cursor.fetchone()

    if not marker_row:
        return []

    marker_id = marker_row[0]
    cursor.execute("""
        SELECT id, sensor_name, sensor_type, unit, last_reading, status
        FROM sensors
        WHERE equipment_marker_id = ?
        AND UPPER(status) = 'ACTIVE'
        ORDER BY sensor_type
    """, (marker_id,))

    sensor_rows = cursor.fetchall()
    sensors = []

    for sensor_id, sensor_name, sensor_type, unit, last_reading, status in sensor_rows:
        # Get 7-day historical readings
        cursor.execute("""
            SELECT value, day_label
            FROM sensor_readings
            WHERE sensor_id = ?
            ORDER BY timestamp
            LIMIT 7
        """, (sensor_id,))

        history_rows = cursor.fetchall()
        history = [{'value': round(val, 2) if val else None, 'day': day}
                  for val, day in history_rows]

        sensors.append({
            'name': sensor_name,
            'type': sensor_type,
            'unit': unit or '',
            'value': round(last_reading, 2) if last_reading else None,
            'status': status,
            'history': history
        })

    return sensors


def create_sensor_summary(sensors, max_display=3):
    """
    Create a summary string from sensor data.

    Args:
        sensors: List of sensor dictionaries
        max_display: Maximum number of sensors to display in summary

    Returns:
        str: Sensor summary string
    """
    summary_parts = []
    for s in sensors[:max_display]:
        if s['value'] is not None:
            summary_parts.append(f"{s['type']}: {s['value']}{s['unit']}")
    if len(sensors) > max_display:
        summary_parts.append(f"(+{len(sensors)-max_display} more)")
    return " | ".join(summary_parts) if summary_parts else "No sensor data"


def rgb_to_hex(r, g, b):
    """
    Convert RGB float values (0.0-1.0) to hex color string.

    Args:
        r, g, b: RGB values as floats (0.0 to 1.0)

    Returns:
        str: Hex color string (e.g., '#FF6B35')
    """
    return '#{:02x}{:02x}{:02x}'.format(
        int(r * 255),
        int(g * 255),
        int(b * 255)
    )


def save_marker_to_db(cursor, marker_id, equipment_type, name, description,
                      x, y, z, latitude, longitude, elevation, color_hex):
    """
    Save an equipment marker to the database.

    Args:
        cursor: Database cursor
        marker_id: Unique marker ID
        equipment_type: Type of equipment
        name: Marker name
        description: Marker description
        x, y, z: Blender coordinates
        latitude, longitude, elevation: GPS coordinates
        color_hex: Color in hex format
    """
    from datetime import datetime

    cursor.execute("""
        INSERT OR REPLACE INTO project_markers (
            marker_id, marker_type, name, description,
            location_x, location_y, location_z,
            latitude, longitude, gps_elevation,
            color, priority, status,
            installation_date, position_source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        marker_id, equipment_type, name, description,
        x, y, z, latitude, longitude, elevation,
        color_hex, 'MEDIUM', 'ACTIVE',
        datetime.now().isoformat(), 'manual'
    ))


def save_sensor_to_db(cursor, sensor_data):
    """
    Save a sensor to the database.

    Args:
        cursor: Database cursor
        sensor_data: Dictionary containing sensor information
    """
    cursor.execute("""
        INSERT OR REPLACE INTO sensors (
            sensor_id, equipment_marker_id, sensor_type, sensor_name, unit,
            api_endpoint, mqtt_topic,
            threshold_min, threshold_max, calibration_date,
            manufacturer, model, installation_date, status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        sensor_data['sensor_id'],
        sensor_data['equipment_marker_id'],
        sensor_data['sensor_type'],
        sensor_data['sensor_name'],
        sensor_data['unit'],
        sensor_data['api_endpoint'],
        sensor_data['mqtt_topic'],
        sensor_data['threshold_min'],
        sensor_data['threshold_max'],
        sensor_data['calibration_date'],
        sensor_data['manufacturer'],
        sensor_data['model'],
        sensor_data['installation_date'],
        sensor_data['status'],
    ))


def create_geojson_feature(obj_name, eq_type, color, lat, lon, sensors=None):
    """
    Create a GeoJSON feature for an equipment marker.

    Args:
        obj_name: Name of the equipment object
        eq_type: Equipment type
        color: Color in hex format
        lat, lon: GPS coordinates
        sensors: List of sensor dictionaries (optional)

    Returns:
        dict: GeoJSON feature
    """
    sensor_count = len(sensors) if sensors else 0
    sensor_summary = create_sensor_summary(sensors) if sensors else ""

    return {
        "type": "Feature",
        "properties": {
            "id": obj_name,
            "name": obj_name,
            "type": eq_type,
            "color": color,
            "priority": "MEDIUM",
            "status": "ACTIVE",
            "pulse_rate": 3.0,
            "description": f"{eq_type.replace('_', ' ').title()}",
            "sensor_count": sensor_count,
            "sensor_summary": sensor_summary,
            "sensors": sensors or []
        },
        "geometry": {
            "type": "Point",
            "coordinates": [lon, lat]
        }
    }


def create_geojson_collection(features):
    """
    Create a GeoJSON FeatureCollection.

    Args:
        features: List of GeoJSON features

    Returns:
        dict: GeoJSON FeatureCollection
    """
    return {
        "type": "FeatureCollection",
        "features": features
    }


def check_duplicate_equipment():
    """
    Check for equipment objects sharing the same location.

    Returns:
        tuple: (duplicates_found: bool, duplicate_locations: dict)

    Usage:
        duplicates, locations = check_duplicate_equipment()
        if duplicates:
            for loc, items in locations.items():
                print(f"Duplicate at {loc}: {items}")
    """
    # Dictionary to group equipment by location
    location_groups = defaultdict(list)

    # Collect all equipment objects
    for obj in bpy.data.objects:
        # Match equipment naming pattern (contains 'Equipment' or ends with _NNN)
        if 'Equipment' in obj.name or obj.name.split('_')[-1].isdigit():
            # Round location to 3 decimal places to handle floating point precision
            loc = tuple(round(coord, 3) for coord in obj.location)
            location_groups[loc].append(obj.name)

    # Find locations with multiple equipment
    duplicate_locations = {
        loc: items for loc, items in location_groups.items() if len(items) > 1
    }

    return len(duplicate_locations) > 0, duplicate_locations


def print_duplicate_equipment_report():
    """Print a formatted report of duplicate equipment locations."""
    duplicates_found, duplicate_locations = check_duplicate_equipment()

    if not duplicates_found:
        print('✓ No equipment found at the same location.')
        return

    print('\n⚠ DUPLICATE EQUIPMENT LOCATIONS FOUND:\n')
    for location, equipment in sorted(duplicate_locations.items()):
        print(f'Location {location}:')
        for item in sorted(equipment):
            print(f'  - {item}')

    print(f'\n⚠ Locations with duplicates: {len(duplicate_locations)}')


# Standalone script mode
if __name__ == "__main__":
    print_duplicate_equipment_report()
