"""
Digital Twin - Maintenance Manager
Preventive maintenance scheduling and work order management

Provides:
- PM template CRUD
- Work order CRUD
- Maintenance logging
- PM schedule generation
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from pathlib import Path


class MaintenanceManager:
    """Manages maintenance operations and work orders"""

    def __init__(self, db_path: str):
        """
        Initialize maintenance manager

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._ensure_database()

    def _ensure_database(self):
        """Create maintenance tables if they don't exist"""
        conn = self._get_connection()
        try:
            # Read and execute maintenance schema
            schema_path = Path(__file__).parent / "schema_maintenance.sql"
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
    # PM TEMPLATES
    # =========================================================================

    def create_pm_template(self, template_data: Dict[str, Any]) -> int:
        """
        Create preventive maintenance template

        Args:
            template_data: Template fields

        Returns:
            Template ID

        Example:
            template = {
                'template_name': 'AHU Filter Replacement',
                'ifc_class': 'IfcAirHandlingUnit',
                'discipline': 'ACMV',
                'description': 'Replace air filters',
                'interval_type': 'Quarterly',
                'interval_value': 1,
                'estimated_hours': 2.5,
                'tasks': json.dumps(['Remove old filters', 'Install new filters']),
            }
        """
        required = ['template_name', 'interval_type', 'tasks']
        for field in required:
            if field not in template_data:
                raise ValueError(f"Missing required field: {field}")

        conn = self._get_connection()
        try:
            fields = list(template_data.keys())
            placeholders = ','.join(['?' for _ in fields])
            sql = f"INSERT INTO pm_templates ({','.join(fields)}) VALUES ({placeholders})"

            cursor = conn.execute(sql, [template_data[f] for f in fields])
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_pm_template(self, template_id: int) -> Optional[Dict[str, Any]]:
        """Get PM template by ID"""
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT * FROM pm_templates WHERE id = ?", (template_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_pm_templates(self, discipline: Optional[str] = None,
                          ifc_class: Optional[str] = None,
                          active_only: bool = True) -> List[Dict[str, Any]]:
        """List PM templates with optional filters"""
        conn = self._get_connection()
        try:
            where_clauses = []
            params = []

            if active_only:
                where_clauses.append("is_active = 1")
            if discipline:
                where_clauses.append("discipline = ?")
                params.append(discipline)
            if ifc_class:
                where_clauses.append("ifc_class = ?")
                params.append(ifc_class)

            where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
            sql = f"SELECT * FROM pm_templates{where_sql} ORDER BY template_name"

            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def update_pm_template(self, template_id: int, updates: Dict[str, Any]) -> bool:
        """Update PM template"""
        conn = self._get_connection()
        try:
            set_clause = ','.join([f"{k} = ?" for k in updates.keys()])
            sql = f"UPDATE pm_templates SET {set_clause} WHERE id = ?"

            values = list(updates.values()) + [template_id]
            cursor = conn.execute(sql, values)
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def delete_pm_template(self, template_id: int) -> bool:
        """Delete PM template"""
        conn = self._get_connection()
        try:
            cursor = conn.execute("DELETE FROM pm_templates WHERE id = ?", (template_id,))
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    # =========================================================================
    # WORK ORDERS
    # =========================================================================

    def create_work_order(self, wo_data: Dict[str, Any]) -> int:
        """
        Create work order

        Args:
            wo_data: Work order fields

        Returns:
            Work order ID

        Example:
            wo = {
                'work_order_number': 'WO-2025-001',
                'asset_guid': 'ABC123',
                'work_type': 'PM',
                'priority': 'Medium',
                'title': 'Quarterly Filter Replacement',
                'due_date': '2025-12-15',
                'assigned_to': 'tech_john',
            }
        """
        required = ['work_order_number', 'asset_guid', 'work_type', 'title']
        for field in required:
            if field not in wo_data:
                raise ValueError(f"Missing required field: {field}")

        conn = self._get_connection()
        try:
            fields = list(wo_data.keys())
            placeholders = ','.join(['?' for _ in fields])
            sql = f"INSERT INTO work_orders ({','.join(fields)}) VALUES ({placeholders})"

            cursor = conn.execute(sql, [wo_data[f] for f in fields])
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_work_order(self, wo_id: int) -> Optional[Dict[str, Any]]:
        """Get work order by ID"""
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT * FROM work_orders WHERE id = ?", (wo_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_work_order_by_number(self, wo_number: str) -> Optional[Dict[str, Any]]:
        """Get work order by number"""
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT * FROM work_orders WHERE work_order_number = ?", (wo_number,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def list_work_orders(self,
                        status: Optional[str] = None,
                        work_type: Optional[str] = None,
                        asset_guid: Optional[str] = None,
                        assigned_to: Optional[str] = None,
                        due_before: Optional[str] = None) -> List[Dict[str, Any]]:
        """List work orders with filters"""
        conn = self._get_connection()
        try:
            where_clauses = []
            params = []

            if status:
                where_clauses.append("status = ?")
                params.append(status)
            if work_type:
                where_clauses.append("work_type = ?")
                params.append(work_type)
            if asset_guid:
                where_clauses.append("asset_guid = ?")
                params.append(asset_guid)
            if assigned_to:
                where_clauses.append("assigned_to = ?")
                params.append(assigned_to)
            if due_before:
                where_clauses.append("due_date <= ?")
                params.append(due_before)

            where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
            sql = f"SELECT * FROM work_orders{where_sql} ORDER BY due_date, priority DESC"

            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def update_work_order(self, wo_id: int, updates: Dict[str, Any]) -> bool:
        """Update work order"""
        conn = self._get_connection()
        try:
            updates['updated_date'] = datetime.now().isoformat()

            set_clause = ','.join([f"{k} = ?" for k in updates.keys()])
            sql = f"UPDATE work_orders SET {set_clause} WHERE id = ?"

            values = list(updates.values()) + [wo_id]
            cursor = conn.execute(sql, values)
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()

    def complete_work_order(self, wo_id: int, actual_hours: Optional[float] = None,
                           labor_cost: Optional[float] = None,
                           parts_cost: Optional[float] = None) -> bool:
        """Mark work order as completed"""
        updates = {
            'status': 'Completed',
            'completion_date': datetime.now().date().isoformat(),
        }

        if actual_hours:
            updates['actual_hours'] = actual_hours
        if labor_cost:
            updates['labor_cost'] = labor_cost
        if parts_cost:
            updates['parts_cost'] = parts_cost
        if labor_cost and parts_cost:
            updates['total_cost'] = labor_cost + parts_cost

        return self.update_work_order(wo_id, updates)

    # =========================================================================
    # MAINTENANCE LOGGING
    # =========================================================================

    def log_maintenance(self, log_data: Dict[str, Any]) -> int:
        """
        Log completed maintenance work

        Args:
            log_data: Maintenance log fields

        Returns:
            Log entry ID
        """
        required = ['work_order_id', 'asset_guid', 'work_performed', 'technician', 'work_date']
        for field in required:
            if field not in log_data:
                raise ValueError(f"Missing required field: {field}")

        conn = self._get_connection()
        try:
            fields = list(log_data.keys())
            placeholders = ','.join(['?' for _ in fields])
            sql = f"INSERT INTO maintenance_log ({','.join(fields)}) VALUES ({placeholders})"

            cursor = conn.execute(sql, [log_data[f] for f in fields])
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_maintenance_history(self, asset_guid: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get maintenance history for an asset"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM maintenance_log WHERE asset_guid = ? ORDER BY work_date DESC LIMIT ?",
                (asset_guid, limit)
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    # =========================================================================
    # TECHNICIANS
    # =========================================================================

    def create_technician(self, tech_data: Dict[str, Any]) -> int:
        """Create technician"""
        required = ['employee_id', 'name']
        for field in required:
            if field not in tech_data:
                raise ValueError(f"Missing required field: {field}")

        conn = self._get_connection()
        try:
            fields = list(tech_data.keys())
            placeholders = ','.join(['?' for _ in fields])
            sql = f"INSERT INTO technicians ({','.join(fields)}) VALUES ({placeholders})"

            cursor = conn.execute(sql, [tech_data[f] for f in fields])
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def list_technicians(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """List technicians"""
        conn = self._get_connection()
        try:
            if active_only:
                cursor = conn.execute(
                    "SELECT * FROM technicians WHERE is_active = 1 ORDER BY name"
                )
            else:
                cursor = conn.execute("SELECT * FROM technicians ORDER BY name")

            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    # =========================================================================
    # STATISTICS
    # =========================================================================

    def get_maintenance_statistics(self) -> Dict[str, Any]:
        """Get maintenance statistics"""
        conn = self._get_connection()
        try:
            stats = {}

            # Total work orders
            cursor = conn.execute("SELECT COUNT(*) FROM work_orders")
            stats['total_work_orders'] = cursor.fetchone()[0]

            # By status
            cursor = conn.execute("SELECT status, COUNT(*) FROM work_orders GROUP BY status")
            stats['by_status'] = {row[0]: row[1] for row in cursor.fetchall()}

            # By type
            cursor = conn.execute("SELECT work_type, COUNT(*) FROM work_orders GROUP BY work_type")
            stats['by_type'] = {row[0]: row[1] for row in cursor.fetchall()}

            # By priority
            cursor = conn.execute("SELECT priority, COUNT(*) FROM work_orders GROUP BY priority")
            stats['by_priority'] = {row[0]: row[1] for row in cursor.fetchall()}

            # Overdue work orders
            today = datetime.now().date().isoformat()
            cursor = conn.execute(
                "SELECT COUNT(*) FROM work_orders WHERE status != 'Completed' AND due_date < ?",
                (today,)
            )
            stats['overdue_count'] = cursor.fetchone()[0]

            # Total PM templates
            cursor = conn.execute("SELECT COUNT(*) FROM pm_templates WHERE is_active = 1")
            stats['total_pm_templates'] = cursor.fetchone()[0]

            return stats
        finally:
            conn.close()

    # =========================================================================
    # PM SCHEDULING HELPERS
    # =========================================================================

    def _calculate_next_due_date(self, interval_type: str, interval_value: int,
                                  from_date: Optional[datetime] = None) -> datetime:
        """Calculate next PM due date based on interval"""
        if from_date is None:
            from_date = datetime.now()

        if interval_type == 'Daily':
            return from_date + timedelta(days=interval_value)
        elif interval_type == 'Weekly':
            return from_date + timedelta(weeks=interval_value)
        elif interval_type == 'Monthly':
            # Approximate (30 days per month)
            return from_date + timedelta(days=30 * interval_value)
        elif interval_type == 'Quarterly':
            return from_date + timedelta(days=90 * interval_value)
        elif interval_type == 'Annually':
            return from_date + timedelta(days=365 * interval_value)
        else:
            raise ValueError(f"Unknown interval type: {interval_type}")

    def _generate_wo_number(self) -> str:
        """Generate unique work order number"""
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT COUNT(*) FROM work_orders")
            count = cursor.fetchone()[0]
            return f"WO-{datetime.now().strftime('%Y%m%d')}-{count + 1:04d}"
        finally:
            conn.close()
