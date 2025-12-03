"""
Add Virtual IoT Sensors
=======================

Creates virtual sensor assets with 3D coordinates for visualization.

Virtual sensors are IoT devices that don't have corresponding IFC geometry
but need 3D visualization in the viewport overlay. They're added by:

1. Creating a virtual asset entry in element_transforms (with 3D coords)
2. Creating a virtual asset entry in elements_meta (metadata)
3. Linking sensors to these virtual assets via asset_guid

This allows the sensor overlay to query 3D positions from element_transforms
while keeping the IoT schema clean and focused on sensor data.

Usage:
    python3 add_virtual_sensors.py <database_path>

Example:
    python3 add_virtual_sensors.py ~/WORK_DIR/databases/enhanced_federation.db
"""

import sys
import sqlite3
from datetime import datetime, timedelta
import random


def add_virtual_sensor_asset(cursor, guid, name, location, discipline='FP'):
    """
    Add a virtual sensor asset to the database.

    Args:
        cursor: SQLite cursor
        guid: Unique GUID for the virtual asset
        name: Asset name
        location: Tuple of (x, y, z) coordinates
        discipline: Discipline code (default: FP for fire protection)
    """
    x, y, z = location

    # Check if exists
    cursor.execute("SELECT guid FROM element_transforms WHERE guid = ?", (guid,))
    if cursor.fetchone():
        print(f"⚠️  Virtual asset already exists: {guid}")
        return False

    # Add to element_transforms (3D position)
    cursor.execute("""
        INSERT INTO element_transforms (
            guid, center_x, center_y, center_z, transform_source
        ) VALUES (?, ?, ?, ?, ?)
    """, (guid, x, y, z, 'virtual_sensor'))

    # Add to elements_meta (metadata)
    cursor.execute("""
        INSERT INTO elements_meta (guid, element_name, ifc_class, discipline)
        VALUES (?, ?, ?, ?)
    """, (guid, name, 'IfcSensor', discipline))

    print(f"✓ Created virtual asset: {guid} at ({x:.1f}, {y:.1f}, {z:.1f})")
    return True


def add_sensor(cursor, sensor_config):
    """
    Add a sensor linked to a virtual asset.

    Args:
        cursor: SQLite cursor
        sensor_config: Dict with sensor configuration
    """
    # Check if sensor already exists
    cursor.execute("SELECT id FROM sensors WHERE sensor_id = ?", (sensor_config['sensor_id'],))
    if cursor.fetchone():
        print(f"⚠️  Sensor already exists: {sensor_config['sensor_id']}")
        return None

    # Insert sensor
    cursor.execute("""
        INSERT INTO sensors (
            sensor_id, asset_guid, sensor_type, measurement_unit,
            protocol, topic, min_threshold, max_threshold,
            location_description, created_date
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        sensor_config['sensor_id'],
        sensor_config['asset_guid'],
        sensor_config['sensor_type'],
        sensor_config['measurement_unit'],
        sensor_config.get('protocol', 'MQTT'),
        sensor_config.get('topic', ''),
        sensor_config.get('min_threshold'),
        sensor_config.get('max_threshold'),
        sensor_config.get('location_description', ''),
        datetime.now().isoformat()
    ))

    sensor_id = cursor.lastrowid
    print(f"✓ Created sensor: {sensor_config['sensor_id']}")
    return sensor_id


def generate_mock_readings(cursor, sensor_id, sensor_type, min_thresh, max_thresh,
                          hours=24, interval_minutes=5, anomaly_rate=0.05):
    """
    Generate mock sensor readings.

    Args:
        cursor: SQLite cursor
        sensor_id: Database ID of sensor
        sensor_type: Type of sensor (determines value generation)
        min_thresh: Minimum threshold
        max_thresh: Maximum threshold
        hours: Number of hours of historical data
        interval_minutes: Reading interval
        anomaly_rate: Probability of generating an anomaly (0-1)

    Returns:
        Tuple of (total_readings, alert_count)
    """
    now = datetime.now()
    total_readings = 0
    alert_count = 0

    for i in range(int(hours * 60 / interval_minutes)):
        timestamp = now - timedelta(minutes=i * interval_minutes)

        # Generate realistic values based on sensor type
        if sensor_type == 'Pressure':
            value = random.uniform(90, 120)  # Normal range PSI
            if random.random() < anomaly_rate:
                value = random.uniform(70, 85)  # Low pressure
        elif sensor_type == 'Smoke':
            value = random.uniform(0, 10)  # Normal PPM
            if random.random() < anomaly_rate:
                value = random.uniform(40, 60)  # Smoke detected
        elif sensor_type == 'Temperature':
            value = random.uniform(18, 24)  # Normal °C
            if random.random() < anomaly_rate:
                value = random.uniform(30, 40)  # High temp
        elif sensor_type == 'Water_Leak':
            value = 0.0  # Dry
            if random.random() < anomaly_rate:
                value = 1.0  # Wet
        elif sensor_type == 'CO2':
            value = random.uniform(400, 800)  # Normal PPM
            if random.random() < anomaly_rate:
                value = random.uniform(1200, 2000)  # Poor air quality
        elif sensor_type == 'Humidity':
            value = random.uniform(30, 60)  # Normal %
            if random.random() < anomaly_rate:
                value = random.uniform(70, 90)  # Too humid
        else:
            value = random.uniform(0, 100)  # Generic

        # Determine quality based on thresholds
        quality = 'good'
        if min_thresh is not None and value < min_thresh:
            quality = 'bad'
            alert_count += 1
        if max_thresh is not None and value > max_thresh:
            quality = 'bad'
            alert_count += 1

        cursor.execute("""
            INSERT INTO sensor_readings (sensor_id, timestamp, value, quality)
            VALUES (?, ?, ?, ?)
        """, (sensor_id, timestamp.isoformat(), value, quality))

        total_readings += 1

    return total_readings, alert_count


def add_main_hall_sensors(db_path):
    """
    Example: Add 4 sensors to main hall at strategic locations.

    This demonstrates the virtual sensor pattern for common building systems:
    - Fire sprinkler pressure (ceiling center - highly visible)
    - Smoke detector (ceiling near entrance)
    - Water leak detectors (floor corners)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("\n" + "="*60)
    print("ADDING MAIN HALL VIRTUAL SENSORS")
    print("="*60)

    # Define virtual sensor assets with 3D coordinates
    virtual_assets = [
        {
            'guid': 'VIRTUAL_SENSOR_SPRINKLER_CENTER',
            'name': 'Main Hall Sprinkler System',
            'location': (0.0, 0.0, 8.0),  # Center ceiling
            'discipline': 'FP'  # Fire Protection
        },
        {
            'guid': 'VIRTUAL_SENSOR_SMOKE_ENTRANCE',
            'name': 'Main Hall Smoke Detector',
            'location': (-5.0, 10.0, 8.0),  # Near entrance ceiling
            'discipline': 'FP'
        },
        {
            'guid': 'VIRTUAL_SENSOR_LEAK_NW',
            'name': 'Main Hall Water Leak NW',
            'location': (-15.0, 20.0, 0.1),  # Floor corner NW
            'discipline': 'FP'
        },
        {
            'guid': 'VIRTUAL_SENSOR_LEAK_SE',
            'name': 'Main Hall Water Leak SE',
            'location': (15.0, -20.0, 0.1),  # Floor corner SE
            'discipline': 'FP'
        }
    ]

    # Create virtual assets
    for asset in virtual_assets:
        add_virtual_sensor_asset(cursor, asset['guid'], asset['name'],
                                 asset['location'], asset['discipline'])

    conn.commit()

    # Define sensors linked to virtual assets
    sensors = [
        {
            'sensor_id': 'SPRINKLER-HALL-CENTER',
            'asset_guid': 'VIRTUAL_SENSOR_SPRINKLER_CENTER',
            'sensor_type': 'Pressure',
            'measurement_unit': 'PSI',
            'protocol': 'BACnet',
            'topic': 'building/fire_protection/sprinkler/pressure',
            'min_threshold': 80.0,
            'max_threshold': 150.0,
            'location_description': 'Main hall center ceiling (fire sprinkler system)'
        },
        {
            'sensor_id': 'SMOKE-HALL-ENTRANCE',
            'asset_guid': 'VIRTUAL_SENSOR_SMOKE_ENTRANCE',
            'sensor_type': 'Smoke',
            'measurement_unit': 'PPM',
            'protocol': 'MQTT',
            'topic': 'building/fire_alarm/smoke/entrance',
            'min_threshold': 0.0,
            'max_threshold': 50.0,
            'location_description': 'Main hall entrance ceiling (smoke detector)'
        },
        {
            'sensor_id': 'LEAK-HALL-NW',
            'asset_guid': 'VIRTUAL_SENSOR_LEAK_NW',
            'sensor_type': 'Water_Leak',
            'measurement_unit': 'Boolean',
            'protocol': 'MQTT',
            'topic': 'building/leak_detection/hall_nw',
            'min_threshold': 0.0,
            'max_threshold': 1.0,
            'location_description': 'Main hall NW floor corner (water leak detector)'
        },
        {
            'sensor_id': 'LEAK-HALL-SE',
            'asset_guid': 'VIRTUAL_SENSOR_LEAK_SE',
            'sensor_type': 'Water_Leak',
            'measurement_unit': 'Boolean',
            'protocol': 'MQTT',
            'topic': 'building/leak_detection/hall_se',
            'min_threshold': 0.0,
            'max_threshold': 1.0,
            'location_description': 'Main hall SE floor corner (water leak detector)'
        }
    ]

    # Add sensors
    added_sensors = []
    for sensor_config in sensors:
        sensor_id = add_sensor(cursor, sensor_config)
        if sensor_id:
            added_sensors.append({
                'id': sensor_id,
                'type': sensor_config['sensor_type'],
                'min': sensor_config.get('min_threshold'),
                'max': sensor_config.get('max_threshold')
            })

    conn.commit()

    print(f"\n✓ Added {len(added_sensors)} sensors")

    # Generate mock readings
    print("\nGenerating mock data (24 hours @ 5-min intervals)...")
    total_readings = 0
    total_alerts = 0

    for sensor in added_sensors:
        readings, alerts = generate_mock_readings(
            cursor, sensor['id'], sensor['type'],
            sensor['min'], sensor['max'],
            hours=24, interval_minutes=5, anomaly_rate=0.05
        )
        total_readings += readings
        total_alerts += alerts

    conn.commit()
    conn.close()

    print(f"✓ Generated {total_readings} readings")
    print(f"✓ Generated {total_alerts} alerts")

    print("\n" + "="*60)
    print("NEXT STEPS:")
    print("="*60)
    print("1. Open Blender with federation blend file")
    print("2. Go to: Digital Twin → IoT Command Center")
    print("3. Click 'Enable Sensor Overlay'")
    print("4. Look for animated spheres in main hall:")
    print("   - Pressure sensor (ceiling center)")
    print("   - Smoke detector (near entrance)")
    print("   - Water leak detectors (floor corners)")
    print("5. Click sensors to view details/create work orders")
    print("="*60)


if __name__ == "__main__":
    import os

    # Get database path from command line or use default
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        db_path = os.path.expanduser("~/Projects/IfcOpenShell/WORK_DIR/databases/enhanced_federation.db")

    if not os.path.exists(db_path):
        print("❌ Database not found!")
        print(f"   Looked for: {db_path}")
        print("\nUsage: python3 add_virtual_sensors.py <database_path>")
        sys.exit(1)

    print(f"Using database: {db_path}\n")
    add_main_hall_sensors(db_path)
