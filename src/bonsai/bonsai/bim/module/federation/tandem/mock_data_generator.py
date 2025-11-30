"""
Digital Twin - Mock Data Generator
Generate simulated sensor data for testing

Creates realistic temperature, pressure, flow readings with:
- Normal variation
- Trending patterns
- Occasional anomalies
"""

import random
import math
from datetime import datetime, timedelta
from typing import Dict, List, Any
from .sensor_registry import SensorRegistry


class MockDataGenerator:
    """Generate simulated IoT sensor data"""

    # Sensor type baseline values and ranges
    SENSOR_PROFILES = {
        'Temperature': {'baseline': 22.0, 'variation': 2.0, 'unit': '°C'},
        'Pressure': {'baseline': 4.5, 'variation': 0.3, 'unit': 'bar'},
        'Flow': {'baseline': 1000.0, 'variation': 100.0, 'unit': 'm³/h'},
        'Humidity': {'baseline': 50.0, 'variation': 10.0, 'unit': '%'},
        'CO2': {'baseline': 600.0, 'variation': 100.0, 'unit': 'ppm'},
        'Power': {'baseline': 25.0, 'variation': 5.0, 'unit': 'kW'},
    }

    def __init__(self, registry: SensorRegistry):
        """
        Initialize mock data generator

        Args:
            registry: SensorRegistry instance
        """
        self.registry = registry
        self.last_values = {}  # Track last value per sensor for continuity

    def generate_reading(self, sensor_id: str, sensor_type: str,
                        anomaly_probability: float = 0.05) -> float:
        """
        Generate single sensor reading

        Args:
            sensor_id: Sensor ID
            sensor_type: Type of sensor
            anomaly_probability: Chance of generating anomaly (0-1)

        Returns:
            Sensor value
        """
        profile = self.SENSOR_PROFILES.get(sensor_type)
        if not profile:
            return 0.0

        baseline = profile['baseline']
        variation = profile['variation']

        # Get last value for continuity
        last_value = self.last_values.get(sensor_id, baseline)

        # Normal variation (small change from last value)
        change = random.gauss(0, variation * 0.2)
        new_value = last_value + change

        # Add slight drift back to baseline
        drift = (baseline - new_value) * 0.1
        new_value += drift

        # Occasional anomaly
        if random.random() < anomaly_probability:
            anomaly_factor = random.choice([-1, 1]) * random.uniform(1.5, 2.5)
            new_value = baseline + (variation * anomaly_factor)

        # Store for next reading
        self.last_values[sensor_id] = new_value

        return round(new_value, 2)

    def generate_batch(self, hours: int = 24, interval_minutes: int = 5,
                      anomaly_probability: float = 0.05) -> Dict[str, Any]:
        """
        Generate batch of readings for all sensors

        Args:
            hours: Hours of history to generate
            interval_minutes: Minutes between readings
            anomaly_probability: Chance of anomalies

        Returns:
            Generation statistics
        """
        sensors = self.registry.list_sensors(active_only=True)
        if not sensors:
            return {'error': 'No active sensors found'}

        stats = {
            'sensors_processed': len(sensors),
            'readings_generated': 0,
            'anomalies_created': 0,
            'start_time': None,
            'end_time': None
        }

        # Calculate time points
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=hours)
        interval = timedelta(minutes=interval_minutes)

        stats['start_time'] = start_time.isoformat()
        stats['end_time'] = end_time.isoformat()

        # Generate for each sensor
        for sensor in sensors:
            sensor_id = sensor['sensor_id']
            sensor_type = sensor['sensor_type']

            current_time = start_time
            while current_time <= end_time:
                # Generate value
                value = self.generate_reading(sensor_id, sensor_type, anomaly_probability)

                # Store reading
                self.registry.add_reading(
                    sensor_id,
                    value,
                    current_time.isoformat()
                )

                stats['readings_generated'] += 1
                current_time += interval

        return stats

    def create_mock_sensors_for_asset(self, asset: Dict[str, Any]) -> List[str]:
        """
        Create mock sensors for an asset based on its type

        Args:
            asset: Asset dictionary

        Returns:
            List of created sensor IDs
        """
        ifc_class = asset.get('ifc_class', '')
        asset_guid = asset['guid']
        asset_name = asset['name']

        sensor_configs = self._get_sensor_configs_for_asset_type(ifc_class)
        created_sensors = []

        for config in sensor_configs:
            sensor_id = f"{config['type'][:4].upper()}-{asset_guid[:8]}-{config['suffix']}"

            sensor_data = {
                'sensor_id': sensor_id,
                'asset_guid': asset_guid,
                'sensor_type': config['type'],
                'measurement_unit': self.SENSOR_PROFILES[config['type']]['unit'],
                'protocol': 'MQTT',
                'topic': f"building/{asset_name.replace(' ', '_')}/{config['suffix'].lower()}",
                'update_interval_seconds': 60,
                'min_threshold': config.get('min_threshold'),
                'max_threshold': config.get('max_threshold'),
                'location_description': f"{config['location']} - {asset_name}"
            }

            try:
                self.registry.create_sensor(sensor_data)
                created_sensors.append(sensor_id)
            except Exception as e:
                print(f"Warning: Could not create sensor {sensor_id}: {e}")

        return created_sensors

    def _get_sensor_configs_for_asset_type(self, ifc_class: str) -> List[Dict[str, Any]]:
        """Get sensor configurations based on asset type"""

        # AHU sensors
        if 'AirHandlingUnit' in ifc_class or 'AHU' in ifc_class:
            return [
                {'type': 'Temperature', 'suffix': 'SUPPLY', 'location': 'Supply Air',
                 'min_threshold': 10.0, 'max_threshold': 25.0},
                {'type': 'Temperature', 'suffix': 'RETURN', 'location': 'Return Air',
                 'min_threshold': 18.0, 'max_threshold': 28.0},
                {'type': 'Pressure', 'suffix': 'STATIC', 'location': 'Static Pressure',
                 'min_threshold': 3.0, 'max_threshold': 6.0},
                {'type': 'Flow', 'suffix': 'AIRFLOW', 'location': 'Air Flow',
                 'min_threshold': 800.0, 'max_threshold': 1200.0},
            ]

        # Chiller sensors
        elif 'Chiller' in ifc_class:
            return [
                {'type': 'Temperature', 'suffix': 'CHW_SUP', 'location': 'Chilled Water Supply',
                 'min_threshold': 5.0, 'max_threshold': 10.0},
                {'type': 'Temperature', 'suffix': 'CHW_RET', 'location': 'Chilled Water Return',
                 'min_threshold': 10.0, 'max_threshold': 15.0},
                {'type': 'Pressure', 'suffix': 'REFRIG', 'location': 'Refrigerant Pressure',
                 'min_threshold': 4.0, 'max_threshold': 5.5},
                {'type': 'Power', 'suffix': 'POWER', 'location': 'Power Consumption',
                 'min_threshold': 15.0, 'max_threshold': 35.0},
            ]

        # Generic equipment
        else:
            return [
                {'type': 'Temperature', 'suffix': 'AMBIENT', 'location': 'Ambient',
                 'min_threshold': 15.0, 'max_threshold': 30.0},
            ]
