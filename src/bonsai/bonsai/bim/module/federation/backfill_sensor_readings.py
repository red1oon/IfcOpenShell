#!/usr/bin/env python3
"""
Backfill Sensor Readings with Day 1-7 Mock Data
================================================

Generates 7 days of sensor readings with "Day 1" through "Day 7" timestamps.
This format is used by the sensor dashboard for consistent mock data display.

Sensor Types:
- Accumulative: Values increase over days (e.g., flowrate, energy, mass)
- Non-accumulative: Random variation around baseline (e.g., temperature, pH, pressure)

Usage:
    python3 backfill_sensor_readings.py <database_path>

Example:
    python3 backfill_sensor_readings.py /path/to/klang_river_perfect.db
"""

import sqlite3
import random
import sys
from pathlib import Path


# Sensor type configurations
SENSOR_CONFIGS = {
    # Accumulative sensors - values increase over days
    'flowrate': {'accumulative': True, 'baseline': 100, 'daily_increment': (10, 30), 'unit': 'm³/day'},
    'energy': {'accumulative': True, 'baseline': 50, 'daily_increment': (5, 15), 'unit': 'kWh'},
    'feedstock_mass': {'accumulative': True, 'baseline': 200, 'daily_increment': (20, 50), 'unit': 'kg'},
    'biochar_yield': {'accumulative': True, 'baseline': 50, 'daily_increment': (5, 15), 'unit': 'kg'},
    'sorting_throughput': {'accumulative': True, 'baseline': 500, 'daily_increment': (50, 100), 'unit': 'kg'},
    'conveyor_load': {'accumulative': True, 'baseline': 300, 'daily_increment': (30, 80), 'unit': 'kg'},
    'species_count': {'accumulative': True, 'baseline': 5, 'daily_increment': (1, 3), 'unit': 'count'},
    'rainfall': {'accumulative': True, 'baseline': 0, 'daily_increment': (2, 15), 'unit': 'mm'},

    # Non-accumulative sensors - random variation
    'temperature': {'accumulative': False, 'baseline': 28, 'variation': 3, 'unit': '°C'},
    'ph': {'accumulative': False, 'baseline': 7.2, 'variation': 0.5, 'unit': 'pH'},
    'dissolvedoxygen': {'accumulative': False, 'baseline': 6.5, 'variation': 1.0, 'unit': 'mg/L'},
    'turbidity': {'accumulative': False, 'baseline': 25, 'variation': 8, 'unit': 'NTU'},
    'conductivity': {'accumulative': False, 'baseline': 500, 'variation': 100, 'unit': 'µS/cm'},
    'waterlevel': {'accumulative': False, 'baseline': 1.5, 'variation': 0.5, 'unit': 'm'},
    'flowvelocity': {'accumulative': False, 'baseline': 1.2, 'variation': 0.4, 'unit': 'm/s'},
    'loadcell': {'accumulative': False, 'baseline': 500, 'variation': 150, 'unit': 'kg'},
    'integrity': {'accumulative': False, 'baseline': 0.5, 'variation': 0.2, 'unit': 'strain'},
    'vibration': {'accumulative': False, 'baseline': 0.3, 'variation': 0.1, 'unit': 'g'},
    'barometric': {'accumulative': False, 'baseline': 1013, 'variation': 15, 'unit': 'hPa'},
    'pyrolysis_temp': {'accumulative': False, 'baseline': 450, 'variation': 50, 'unit': '°C'},
    'reactor_pressure': {'accumulative': False, 'baseline': 2.5, 'variation': 0.5, 'unit': 'bar'},
    'baler_pressure': {'accumulative': False, 'baseline': 150, 'variation': 30, 'unit': 'bar'},
    'contamination_rate': {'accumulative': False, 'baseline': 5, 'variation': 2, 'unit': '%'},
    'moisture': {'accumulative': False, 'baseline': 15, 'variation': 5, 'unit': '%'},
    'carbon_content': {'accumulative': False, 'baseline': 75, 'variation': 5, 'unit': '%'},
    'soil_moisture': {'accumulative': False, 'baseline': 35, 'variation': 10, 'unit': '%'},
    'canopy_height': {'accumulative': False, 'baseline': 12, 'variation': 2, 'unit': 'm'},
    'ndvi': {'accumulative': False, 'baseline': 0.6, 'variation': 0.1, 'unit': 'index'},
    'heavymetals': {'accumulative': False, 'baseline': 0.05, 'variation': 0.02, 'unit': 'mg/L'},
    'voc': {'accumulative': False, 'baseline': 10, 'variation': 5, 'unit': 'ppb'},
    'cod': {'accumulative': False, 'baseline': 30, 'variation': 10, 'unit': 'mg/L'},
    'bod': {'accumulative': False, 'baseline': 15, 'variation': 5, 'unit': 'mg/L'},
    'tss': {'accumulative': False, 'baseline': 50, 'variation': 15, 'unit': 'mg/L'},
    'oil_grease': {'accumulative': False, 'baseline': 5, 'variation': 2, 'unit': 'mg/L'},
    'cyanide': {'accumulative': False, 'baseline': 0.01, 'variation': 0.005, 'unit': 'mg/L'},
    'phenols': {'accumulative': False, 'baseline': 0.02, 'variation': 0.01, 'unit': 'mg/L'},
    'nitrate': {'accumulative': False, 'baseline': 8, 'variation': 3, 'unit': 'mg/L'},
    'phosphate': {'accumulative': False, 'baseline': 2, 'variation': 0.8, 'unit': 'mg/L'},
    'co2_emissions': {'accumulative': False, 'baseline': 50, 'variation': 15, 'unit': 'kg/h'},
    'particulate': {'accumulative': False, 'baseline': 20, 'variation': 8, 'unit': 'µg/m³'},
    'velocity_spike': {'accumulative': False, 'baseline': 0.2, 'variation': 0.1, 'unit': 'm/s'},
    'bridge_clearance': {'accumulative': False, 'baseline': 4.5, 'variation': 0.5, 'unit': 'm'},
    'gps_drift': {'accumulative': False, 'baseline': 0.5, 'variation': 0.3, 'unit': 'm'},
    'powerusage': {'accumulative': False, 'baseline': 25, 'variation': 8, 'unit': 'W'},
    'battery_level': {'accumulative': False, 'baseline': 85, 'variation': 10, 'unit': '%'},

    # Binary/status sensors
    'camera': {'accumulative': False, 'baseline': 1, 'variation': 0, 'unit': 'status'},
    'aicamera': {'accumulative': False, 'baseline': 1, 'variation': 0, 'unit': 'status'},
    'pirmotion': {'accumulative': False, 'baseline': 0, 'variation': 1, 'unit': 'detected'},
    'audiorecorder': {'accumulative': False, 'baseline': 1, 'variation': 0, 'unit': 'status'},
    'optical_sorter': {'accumulative': False, 'baseline': 1, 'variation': 0, 'unit': 'status'},
    'metal_detector': {'accumulative': False, 'baseline': 0, 'variation': 1, 'unit': 'detected'},
    'debris_radar': {'accumulative': False, 'baseline': 0, 'variation': 1, 'unit': 'detected'},
    'siren_status': {'accumulative': False, 'baseline': 0, 'variation': 1, 'unit': 'active'},
    'carbon_seq': {'accumulative': False, 'baseline': 10, 'variation': 3, 'unit': 'tCO2/ha'},
}


def generate_sensor_values(sensor_type, days=7):
    """
    Generate 7 days of sensor values based on type

    Args:
        sensor_type: Type of sensor (e.g., 'loadcell', 'waterlevel')
        days: Number of days to generate (default 7)

    Returns:
        List of values for Day 1 through Day 7
    """
    config = SENSOR_CONFIGS.get(sensor_type, {
        'accumulative': False,
        'baseline': 50,
        'variation': 10,
        'unit': 'units'
    })

    values = []

    if config['accumulative']:
        # Accumulative: start at baseline, increment each day
        current_value = config['baseline']
        for day in range(days):
            increment = random.uniform(*config['daily_increment'])
            current_value += increment
            values.append(round(current_value, 2))
    else:
        # Non-accumulative: random variation around baseline
        baseline = config['baseline']
        variation = config['variation']

        for day in range(days):
            if variation == 0:
                # Binary/status sensors
                values.append(random.choice([0, 1]) if baseline == 0 else 1)
            else:
                # Continuous sensors with variation
                value = baseline + random.uniform(-variation, variation)
                values.append(round(max(0, value), 2))  # Ensure non-negative

    return values


def clean_orphaned_sensors(conn, min_marker_id=261):
    """
    Remove sensors that reference non-existent markers

    Args:
        conn: Database connection
        min_marker_id: Minimum valid marker ID

    Returns:
        Number of orphaned sensors deleted
    """
    cursor = conn.cursor()

    # Delete orphaned sensor readings first
    cursor.execute("""
        DELETE FROM sensor_readings
        WHERE sensor_id IN (
            SELECT sensor_id FROM sensors
            WHERE equipment_marker_id < ?
        )
    """, (min_marker_id,))
    readings_deleted = cursor.rowcount

    # Delete orphaned sensors
    cursor.execute("DELETE FROM sensors WHERE equipment_marker_id < ?", (min_marker_id,))
    sensors_deleted = cursor.rowcount

    conn.commit()

    print(f"✓ Cleaned {sensors_deleted} orphaned sensors")
    print(f"✓ Cleaned {readings_deleted} orphaned sensor readings")

    return sensors_deleted


def backfill_sensor_readings(db_path, clean_orphans=True):
    """
    Backfill sensor readings with Day 1-7 data

    Args:
        db_path: Path to database file
        clean_orphans: Whether to clean orphaned sensors first
    """
    db_path = Path(db_path)
    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        return False

    print(f"\n📊 Backfilling sensor readings: {db_path.name}")
    print("=" * 70)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Step 1: Clean orphaned sensors if requested
    if clean_orphans:
        cursor.execute("SELECT MIN(marker_id) FROM project_markers")
        min_marker_id = cursor.fetchone()[0]
        print(f"\n1️⃣  Cleaning orphaned sensors (marker_id < {min_marker_id})...")
        clean_orphaned_sensors(conn, min_marker_id)

    # Step 2: Get all valid sensors
    print(f"\n2️⃣  Loading sensors...")
    cursor.execute("""
        SELECT sensor_id, sensor_type, equipment_marker_id
        FROM sensors
        ORDER BY equipment_marker_id, sensor_id
    """)
    sensors = cursor.fetchall()

    if not sensors:
        print("❌ No sensors found in database")
        conn.close()
        return False

    print(f"✓ Found {len(sensors)} sensors")

    # Step 3: Clear existing readings
    print(f"\n3️⃣  Clearing existing sensor readings...")
    cursor.execute("DELETE FROM sensor_readings")
    conn.commit()
    print(f"✓ Cleared all readings")

    # Step 4: Generate Day 1-7 readings for each sensor
    print(f"\n4️⃣  Generating Day 1-7 readings...")
    readings_count = 0

    for sensor_id, sensor_type, marker_id in sensors:
        values = generate_sensor_values(sensor_type, days=7)

        for day, value in enumerate(values, start=1):
            timestamp = f"Day {day}"
            status = 'OK'

            # Set warning/critical status for some readings (10% chance)
            if random.random() < 0.1:
                status = random.choice(['WARNING', 'CRITICAL'])

            cursor.execute("""
                INSERT INTO sensor_readings (sensor_id, timestamp, value, status)
                VALUES (?, ?, ?, ?)
            """, (sensor_id, timestamp, value, status))

            readings_count += 1

    conn.commit()
    conn.close()

    print(f"✓ Generated {readings_count} readings ({len(sensors)} sensors × 7 days)")
    print(f"\n{'=' * 70}")
    print(f"✅ Backfill complete! Sensor dashboard ready.\n")

    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 backfill_sensor_readings.py <database_path>")
        print("Example: python3 backfill_sensor_readings.py klang_river_perfect.db")
        sys.exit(1)

    db_path = sys.argv[1]
    success = backfill_sensor_readings(db_path, clean_orphans=True)

    sys.exit(0 if success else 1)
