"""
Digital Twin - Sensor Registry
IoT sensor management and data logging

Provides:
- Sensor CRUD operations
- Sensor readings (time-series)
- Alert rules
- Alert management
"""

import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path


class SensorRegistry:
    """Manages IoT sensors and readings"""

    def __init__(self, db_path: str):
        """
        Initialize sensor registry

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._ensure_database()

    def _ensure_database(self):
        """Create IoT tables if they don't exist"""
        conn = self._get_connection()
        try:
            # Read and execute IoT schema
            schema_path = Path(__file__).parent / "schema_iot.sql"
            with open(schema_path, 'r') as f:
                schema_sql = f.read()
            conn.executescript(schema_sql)
            conn.commit()
        finally:
            conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    # =========================================================================
    # SENSORS
    # =========================================================================

    def create_sensor(self, sensor_data: Dict[str, Any]) -> int:
        """
        Create sensor

        Args:
            sensor_data: Sensor fields

        Returns:
            Sensor ID

        Example:
            sensor = {
                'sensor_id': 'TEMP-AHU01-SUPPLY',
                'asset_guid': 'ABC123',
                'sensor_type': 'Temperature',
                'measurement_unit': '°C',
                'protocol': 'MQTT',
                'topic': 'building/level3/ahu01/supply_temp',
                'min_threshold': 10.0,
                'max_threshold': 25.0
            }
        """
        required = ['sensor_id', 'asset_guid', 'sensor_type', 'measurement_unit']
        for field in required:
            if field not in sensor_data:
                raise ValueError(f"Missing required field: {field}")

        conn = self._get_connection()
        try:
            fields = list(sensor_data.keys())
            placeholders = ','.join(['?' for _ in fields])
            sql = f"INSERT INTO sensors ({','.join(fields)}) VALUES ({placeholders})"

            cursor = conn.execute(sql, [sensor_data[f] for f in fields])
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_sensor(self, sensor_id: str) -> Optional[Dict[str, Any]]:
        """Get sensor by ID"""
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT * FROM sensors WHERE sensor_id = ?", (sensor_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_sensors(self,
                    asset_guid: Optional[str] = None,
                    sensor_type: Optional[str] = None,
                    active_only: bool = True) -> List[Dict[str, Any]]:
        """List sensors with filters"""
        conn = self._get_connection()
        try:
            where_clauses = []
            params = []

            if active_only:
                where_clauses.append("is_active = 1")
            if asset_guid:
                where_clauses.append("asset_guid = ?")
                params.append(asset_guid)
            if sensor_type:
                where_clauses.append("sensor_type = ?")
                params.append(sensor_type)

            where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
            sql = f"SELECT * FROM sensors{where_sql} ORDER BY sensor_id"

            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def update_sensor(self, sensor_id: str, updates: Dict[str, Any]) -> bool:
        """Update sensor"""
        conn = self._get_connection()
        try:
            set_clause = ','.join([f"{k} = ?" for k in updates.keys()])
            sql = f"UPDATE sensors SET {set_clause} WHERE sensor_id = ?"

            values = list(updates.values()) + [sensor_id]
            cursor = conn.execute(sql, values)
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def delete_sensor(self, sensor_id: str) -> bool:
        """Delete sensor"""
        conn = self._get_connection()
        try:
            cursor = conn.execute("DELETE FROM sensors WHERE sensor_id = ?", (sensor_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # =========================================================================
    # SENSOR READINGS
    # =========================================================================

    def add_reading(self, sensor_id: str, value: float,
                   timestamp: Optional[str] = None,
                   quality: str = 'good', commit: bool = True) -> int:
        """
        Add sensor reading

        Args:
            sensor_id: Sensor ID
            value: Reading value
            timestamp: ISO timestamp (defaults to now)
            quality: Data quality (good, uncertain, bad)
            commit: Whether to commit immediately (set False for batch operations)

        Returns:
            Reading ID
        """
        if timestamp is None:
            timestamp = datetime.now().isoformat()

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "INSERT INTO sensor_readings (sensor_id, timestamp, value, quality) VALUES (?, ?, ?, ?)",
                (sensor_id, timestamp, value, quality)
            )

            # Update sensor's last reading (less frequently)
            if commit:
                conn.execute(
                    "UPDATE sensors SET last_reading_date = ?, last_reading_value = ? WHERE sensor_id = ?",
                    (timestamp, value, sensor_id)
                )
                conn.commit()

            return cursor.lastrowid
        finally:
            if commit:
                conn.close()

    def get_latest_reading(self, sensor_id: str) -> Optional[Dict[str, Any]]:
        """Get most recent reading for sensor"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM sensor_readings WHERE sensor_id = ? ORDER BY timestamp DESC LIMIT 1",
                (sensor_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_readings(self, sensor_id: str,
                    since: Optional[str] = None,
                    until: Optional[str] = None,
                    limit: int = 1000) -> List[Dict[str, Any]]:
        """
        Get historical readings for sensor

        Args:
            sensor_id: Sensor ID
            since: Start timestamp (ISO format)
            until: End timestamp (ISO format)
            limit: Max readings to return

        Returns:
            List of readings
        """
        conn = self._get_connection()
        try:
            where_clauses = ["sensor_id = ?"]
            params = [sensor_id]

            if since:
                where_clauses.append("timestamp >= ?")
                params.append(since)
            if until:
                where_clauses.append("timestamp <= ?")
                params.append(until)

            where_sql = " WHERE " + " AND ".join(where_clauses)
            sql = f"SELECT * FROM sensor_readings{where_sql} ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)

            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def get_reading_statistics(self, sensor_id: str,
                               since: Optional[str] = None) -> Dict[str, Any]:
        """Calculate statistics for sensor readings"""
        conn = self._get_connection()
        try:
            where_clause = "sensor_id = ?"
            params = [sensor_id]

            if since:
                where_clause += " AND timestamp >= ?"
                params.append(since)

            cursor = conn.execute(
                f"SELECT COUNT(*), MIN(value), MAX(value), AVG(value) "
                f"FROM sensor_readings WHERE {where_clause}",
                params
            )
            row = cursor.fetchone()

            return {
                'count': row[0],
                'min': row[1],
                'max': row[2],
                'avg': row[3]
            } if row else {}
        finally:
            conn.close()

    # =========================================================================
    # ALERT RULES
    # =========================================================================

    def create_alert_rule(self, rule_data: Dict[str, Any]) -> int:
        """
        Create alert rule

        Args:
            rule_data: Alert rule fields

        Returns:
            Rule ID
        """
        required = ['rule_name', 'condition_type']
        for field in required:
            if field not in rule_data:
                raise ValueError(f"Missing required field: {field}")

        conn = self._get_connection()
        try:
            fields = list(rule_data.keys())
            placeholders = ','.join(['?' for _ in fields])
            sql = f"INSERT INTO alert_rules ({','.join(fields)}) VALUES ({placeholders})"

            cursor = conn.execute(sql, [rule_data[f] for f in fields])
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def list_alert_rules(self, sensor_id: Optional[str] = None,
                        active_only: bool = True) -> List[Dict[str, Any]]:
        """List alert rules"""
        conn = self._get_connection()
        try:
            where_clauses = []
            params = []

            if active_only:
                where_clauses.append("is_active = 1")
            if sensor_id:
                where_clauses.append("(sensor_id = ? OR sensor_id IS NULL)")
                params.append(sensor_id)

            where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
            sql = f"SELECT * FROM alert_rules{where_sql} ORDER BY rule_name"

            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def update_alert_rule(self, rule_id: int, updates: Dict[str, Any]) -> bool:
        """Update alert rule"""
        conn = self._get_connection()
        try:
            set_clause = ','.join([f"{k} = ?" for k in updates.keys()])
            sql = f"UPDATE alert_rules SET {set_clause} WHERE id = ?"

            values = list(updates.values()) + [rule_id]
            cursor = conn.execute(sql, values)
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # =========================================================================
    # ALERTS
    # =========================================================================

    def create_alert(self, alert_data: Dict[str, Any]) -> int:
        """
        Create alert

        Args:
            alert_data: Alert fields

        Returns:
            Alert ID
        """
        required = ['alert_rule_id', 'sensor_id', 'asset_guid', 'severity', 'message', 'trigger_value']
        for field in required:
            if field not in alert_data:
                raise ValueError(f"Missing required field: {field}")

        if 'triggered_date' not in alert_data:
            alert_data['triggered_date'] = datetime.now().isoformat()

        conn = self._get_connection()
        try:
            fields = list(alert_data.keys())
            placeholders = ','.join(['?' for _ in fields])
            sql = f"INSERT INTO alerts ({','.join(fields)}) VALUES ({placeholders})"

            cursor = conn.execute(sql, [alert_data[f] for f in fields])
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_active_alerts(self, asset_guid: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get unresolved alerts"""
        conn = self._get_connection()
        try:
            where_clause = "resolved_date IS NULL"
            params = []

            if asset_guid:
                where_clause += " AND asset_guid = ?"
                params.append(asset_guid)

            cursor = conn.execute(
                f"SELECT * FROM alerts WHERE {where_clause} ORDER BY triggered_date DESC",
                params
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def acknowledge_alert(self, alert_id: int, acknowledged_by: str) -> bool:
        """Acknowledge alert"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "UPDATE alerts SET acknowledged_date = ?, acknowledged_by = ? WHERE id = ?",
                (datetime.now().isoformat(), acknowledged_by, alert_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def resolve_alert(self, alert_id: int, resolved_by: str, notes: Optional[str] = None) -> bool:
        """Resolve alert"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "UPDATE alerts SET resolved_date = ?, resolved_by = ?, notes = ? WHERE id = ?",
                (datetime.now().isoformat(), resolved_by, notes, alert_id)
            )
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # =========================================================================
    # STATISTICS
    # =========================================================================

    def get_iot_statistics(self) -> Dict[str, Any]:
        """Get IoT system statistics"""
        conn = self._get_connection()
        try:
            stats = {}

            # Total sensors
            cursor = conn.execute("SELECT COUNT(*) FROM sensors WHERE is_active = 1")
            stats['total_sensors'] = cursor.fetchone()[0]

            # By type
            cursor = conn.execute("SELECT sensor_type, COUNT(*) FROM sensors WHERE is_active = 1 GROUP BY sensor_type")
            stats['by_type'] = {row[0]: row[1] for row in cursor.fetchall()}

            # Active alerts
            cursor = conn.execute("SELECT COUNT(*) FROM alerts WHERE resolved_date IS NULL")
            stats['active_alerts'] = cursor.fetchone()[0]

            # By severity
            cursor = conn.execute(
                "SELECT severity, COUNT(*) FROM alerts WHERE resolved_date IS NULL GROUP BY severity"
            )
            stats['alerts_by_severity'] = {row[0]: row[1] for row in cursor.fetchall()}

            # Total readings
            cursor = conn.execute("SELECT COUNT(*) FROM sensor_readings")
            stats['total_readings'] = cursor.fetchone()[0]

            return stats
        finally:
            conn.close()
