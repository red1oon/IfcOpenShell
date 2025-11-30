"""
Digital Twin - Alert Engine
Monitor sensor readings and trigger alerts based on thresholds

Checks:
- Sensor thresholds (min/max)
- Alert rules
- Create alerts for violations
"""

from datetime import datetime
from typing import Dict, List, Any, Optional
from .sensor_registry import SensorRegistry


class AlertEngine:
    """Monitor sensors and generate alerts"""

    def __init__(self, registry: SensorRegistry):
        """
        Initialize alert engine

        Args:
            registry: SensorRegistry instance
        """
        self.registry = registry

    def check_all_sensors(self, auto_create_wo: bool = False) -> Dict[str, Any]:
        """
        Check all active sensors against thresholds

        Args:
            auto_create_wo: Auto-create work orders for critical alerts

        Returns:
            Check statistics
        """
        sensors = self.registry.list_sensors(active_only=True)

        stats = {
            'sensors_checked': len(sensors),
            'alerts_created': 0,
            'by_severity': {},
        }

        for sensor in sensors:
            result = self.check_sensor(sensor['sensor_id'], auto_create_wo)
            if result:
                stats['alerts_created'] += 1
                severity = result.get('severity', 'Unknown')
                stats['by_severity'][severity] = stats['by_severity'].get(severity, 0) + 1

        return stats

    def check_sensor(self, sensor_id: str, auto_create_wo: bool = False) -> Optional[Dict[str, Any]]:
        """
        Check single sensor against thresholds

        Args:
            sensor_id: Sensor ID
            auto_create_wo: Auto-create work order if needed

        Returns:
            Alert data if created, None otherwise
        """
        sensor = self.registry.get_sensor(sensor_id)
        if not sensor:
            return None

        # Get latest reading
        reading = self.registry.get_latest_reading(sensor_id)
        if not reading:
            return None  # No data yet

        value = reading['value']

        # Check sensor's built-in thresholds first
        alert_data = None

        if sensor.get('critical_max') and value > sensor['critical_max']:
            alert_data = {
                'severity': 'Critical',
                'message': f"{sensor['sensor_type']} critical high: {value}{sensor['measurement_unit']} > {sensor['critical_max']}{sensor['measurement_unit']}",
                'threshold_violated': 'critical_max',
                'threshold_value': sensor['critical_max']
            }

        elif sensor.get('critical_min') and value < sensor['critical_min']:
            alert_data = {
                'severity': 'Critical',
                'message': f"{sensor['sensor_type']} critical low: {value}{sensor['measurement_unit']} < {sensor['critical_min']}{sensor['measurement_unit']}",
                'threshold_violated': 'critical_min',
                'threshold_value': sensor['critical_min']
            }

        elif sensor.get('max_threshold') and value > sensor['max_threshold']:
            alert_data = {
                'severity': 'Warning',
                'message': f"{sensor['sensor_type']} above threshold: {value}{sensor['measurement_unit']} > {sensor['max_threshold']}{sensor['measurement_unit']}",
                'threshold_violated': 'max_threshold',
                'threshold_value': sensor['max_threshold']
            }

        elif sensor.get('min_threshold') and value < sensor['min_threshold']:
            alert_data = {
                'severity': 'Warning',
                'message': f"{sensor['sensor_type']} below threshold: {value}{sensor['measurement_unit']} < {sensor['min_threshold']}{sensor['measurement_unit']}",
                'threshold_violated': 'min_threshold',
                'threshold_value': sensor['min_threshold']
            }

        # If threshold violated, create alert
        if alert_data:
            # Check if alert already exists for this condition
            existing = self.registry.get_active_alerts(sensor['asset_guid'])
            for alert in existing:
                if alert['sensor_id'] == sensor_id and alert['severity'] == alert_data['severity']:
                    return None  # Alert already active

            # Create new alert
            alert_full = {
                'alert_rule_id': 0,  # Direct threshold check, no rule
                'sensor_id': sensor_id,
                'asset_guid': sensor['asset_guid'],
                'severity': alert_data['severity'],
                'message': alert_data['message'],
                'trigger_value': value,
            }

            alert_id = self.registry.create_alert(alert_full)
            alert_full['id'] = alert_id

            return alert_full

        return None

    def check_alert_rules(self) -> Dict[str, Any]:
        """
        Check all alert rules

        Returns:
            Check statistics
        """
        rules = self.registry.list_alert_rules(active_only=True)

        stats = {
            'rules_checked': len(rules),
            'alerts_created': 0,
        }

        for rule in rules:
            result = self._check_rule(rule)
            if result:
                stats['alerts_created'] += 1

        return stats

    def _check_rule(self, rule: Dict[str, Any]) -> Optional[int]:
        """Check single alert rule"""
        # Get applicable sensors
        if rule.get('sensor_id'):
            sensors = [self.registry.get_sensor(rule['sensor_id'])]
        elif rule.get('sensor_type'):
            sensors = self.registry.list_sensors(sensor_type=rule['sensor_type'], active_only=True)
        else:
            return None

        for sensor in sensors:
            if not sensor:
                continue

            reading = self.registry.get_latest_reading(sensor['sensor_id'])
            if not reading:
                continue

            value = reading['value']
            condition_met = False

            # Check condition
            if rule['condition_type'] == 'Above' and rule.get('threshold_value'):
                condition_met = value > rule['threshold_value']

            elif rule['condition_type'] == 'Below' and rule.get('threshold_value'):
                condition_met = value < rule['threshold_value']

            elif rule['condition_type'] == 'OutOfRange':
                if rule.get('threshold_min') and rule.get('threshold_max'):
                    condition_met = value < rule['threshold_min'] or value > rule['threshold_max']

            # Create alert if condition met
            if condition_met:
                alert_data = {
                    'alert_rule_id': rule['id'],
                    'sensor_id': sensor['sensor_id'],
                    'asset_guid': sensor['asset_guid'],
                    'severity': rule.get('severity', 'Warning'),
                    'message': f"{rule['rule_name']}: {value}{sensor['measurement_unit']}",
                    'trigger_value': value,
                }

                return self.registry.create_alert(alert_data)

        return None

    def get_alert_summary(self) -> Dict[str, Any]:
        """Get summary of current alerts"""
        active_alerts = self.registry.get_active_alerts()

        summary = {
            'total_active': len(active_alerts),
            'by_severity': {},
            'recent': []
        }

        for alert in active_alerts:
            severity = alert['severity']
            summary['by_severity'][severity] = summary['by_severity'].get(severity, 0) + 1

        # Get most recent 5
        summary['recent'] = sorted(active_alerts, key=lambda x: x['triggered_date'], reverse=True)[:5]

        return summary
