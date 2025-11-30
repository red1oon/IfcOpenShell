"""
Digital Twin - Asset Registry
Core CRUD operations for asset management

Provides database access layer for assets, properties, documents, and history.
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path


class AssetRegistry:
    """Manages asset data in the digital twin database"""

    def __init__(self, db_path: str):
        """
        Initialize asset registry

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._ensure_database()

    def _ensure_database(self):
        """Create database and tables if they don't exist"""
        conn = self._get_connection()
        try:
            # Read and execute schema
            schema_path = Path(__file__).parent / "schema.sql"
            with open(schema_path, 'r') as f:
                schema_sql = f.read()
            conn.executescript(schema_sql)
            conn.commit()
        finally:
            conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        return conn

    # =========================================================================
    # ASSET CRUD OPERATIONS
    # =========================================================================

    def create_asset(self, asset_data: Dict[str, Any]) -> str:
        """
        Create a new asset

        Args:
            asset_data: Dictionary with asset fields

        Returns:
            Asset GUID

        Example:
            asset = {
                'guid': '2O2Fr$t4X7Zf8NOew3FNr2',
                'name': 'Air Handling Unit - Level 3',
                'ifc_class': 'IfcAirHandlingUnit',
                'discipline': 'ACMV',
                ...
            }
        """
        required_fields = ['guid', 'name', 'ifc_class']
        for field in required_fields:
            if field not in asset_data:
                raise ValueError(f"Missing required field: {field}")

        conn = self._get_connection()
        try:
            # Build INSERT statement dynamically
            fields = list(asset_data.keys())
            placeholders = ','.join(['?' for _ in fields])
            sql = f"INSERT INTO assets ({','.join(fields)}) VALUES ({placeholders})"

            conn.execute(sql, [asset_data[f] for f in fields])

            # Log creation
            self._log_history(
                conn,
                asset_data['guid'],
                'Created',
                None, None, None,
                'system',
                'Asset imported from IFC model'
            )

            conn.commit()
            return asset_data['guid']
        finally:
            conn.close()

    def get_asset(self, guid: str) -> Optional[Dict[str, Any]]:
        """
        Get asset by GUID

        Args:
            guid: Asset GUID

        Returns:
            Asset dictionary or None if not found
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute("SELECT * FROM assets WHERE guid = ?", (guid,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        finally:
            conn.close()

    def update_asset(self, guid: str, updates: Dict[str, Any], changed_by: str = 'system') -> bool:
        """
        Update asset fields

        Args:
            guid: Asset GUID
            updates: Dictionary of fields to update
            changed_by: User making the change

        Returns:
            True if updated, False if not found
        """
        # Get current values for history
        current = self.get_asset(guid)
        if not current:
            return False

        conn = self._get_connection()
        try:
            # Build UPDATE statement
            set_clause = ','.join([f"{k} = ?" for k in updates.keys()])
            sql = f"UPDATE assets SET {set_clause}, updated_date = CURRENT_TIMESTAMP WHERE guid = ?"

            values = list(updates.values()) + [guid]
            conn.execute(sql, values)

            # Log each changed field
            for field, new_value in updates.items():
                old_value = current.get(field)
                if old_value != new_value:
                    self._log_history(
                        conn, guid, 'Updated',
                        field, str(old_value), str(new_value),
                        changed_by, None
                    )

            conn.commit()
            return True
        finally:
            conn.close()

    def delete_asset(self, guid: str) -> bool:
        """
        Delete asset (cascades to properties, documents, history)

        Args:
            guid: Asset GUID

        Returns:
            True if deleted, False if not found
        """
        conn = self._get_connection()
        try:
            cursor = conn.execute("DELETE FROM assets WHERE guid = ?", (guid,))
            deleted = cursor.rowcount > 0
            conn.commit()
            return deleted
        finally:
            conn.close()

    def list_assets(self,
                    discipline: Optional[str] = None,
                    ifc_class: Optional[str] = None,
                    status: Optional[str] = None,
                    storey: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List assets with optional filters

        Args:
            discipline: Filter by discipline (ACMV, ELEC, etc.)
            ifc_class: Filter by IFC class
            status: Filter by status (Active, Inactive, etc.)
            storey: Filter by storey

        Returns:
            List of asset dictionaries
        """
        conn = self._get_connection()
        try:
            where_clauses = []
            params = []

            if discipline:
                where_clauses.append("discipline = ?")
                params.append(discipline)
            if ifc_class:
                where_clauses.append("ifc_class = ?")
                params.append(ifc_class)
            if status:
                where_clauses.append("status = ?")
                params.append(status)
            if storey:
                where_clauses.append("storey = ?")
                params.append(storey)

            where_sql = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
            sql = f"SELECT * FROM assets{where_sql} ORDER BY name"

            cursor = conn.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    # =========================================================================
    # ASSET PROPERTIES
    # =========================================================================

    def add_property(self, asset_guid: str, name: str, value: str,
                     property_type: str = 'string') -> int:
        """Add custom property to asset"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "INSERT INTO asset_properties (asset_guid, property_name, property_value, property_type) "
                "VALUES (?, ?, ?, ?)",
                (asset_guid, name, value, property_type)
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_properties(self, asset_guid: str) -> List[Dict[str, Any]]:
        """Get all custom properties for an asset"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM asset_properties WHERE asset_guid = ? ORDER BY property_name",
                (asset_guid,)
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    # =========================================================================
    # ASSET DOCUMENTS
    # =========================================================================

    def add_document(self, asset_guid: str, document_type: str, file_name: str,
                     file_path: str, description: str = '', uploaded_by: str = 'system') -> int:
        """Attach document to asset"""
        file_size_kb = 0
        if os.path.exists(file_path):
            file_size_kb = os.path.getsize(file_path) // 1024

        mime_type = self._guess_mime_type(file_name)

        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "INSERT INTO asset_documents "
                "(asset_guid, document_type, file_name, file_path, file_size_kb, mime_type, description, uploaded_by) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (asset_guid, document_type, file_name, file_path, file_size_kb, mime_type, description, uploaded_by)
            )
            conn.commit()
            return cursor.lastrowid
        finally:
            conn.close()

    def get_documents(self, asset_guid: str, document_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get documents for an asset"""
        conn = self._get_connection()
        try:
            if document_type:
                cursor = conn.execute(
                    "SELECT * FROM asset_documents WHERE asset_guid = ? AND document_type = ? ORDER BY uploaded_date DESC",
                    (asset_guid, document_type)
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM asset_documents WHERE asset_guid = ? ORDER BY uploaded_date DESC",
                    (asset_guid,)
                )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    # =========================================================================
    # ASSET HISTORY
    # =========================================================================

    def get_history(self, asset_guid: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get change history for an asset"""
        conn = self._get_connection()
        try:
            cursor = conn.execute(
                "SELECT * FROM asset_history WHERE asset_guid = ? ORDER BY changed_date DESC LIMIT ?",
                (asset_guid, limit)
            )
            return [dict(row) for row in cursor.fetchall()]
        finally:
            conn.close()

    def _log_history(self, conn: sqlite3.Connection, asset_guid: str, change_type: str,
                     field_name: Optional[str], old_value: Optional[str], new_value: Optional[str],
                     changed_by: str, notes: Optional[str]):
        """Internal: Log change to history table"""
        conn.execute(
            "INSERT INTO asset_history "
            "(asset_guid, change_type, field_name, old_value, new_value, changed_by, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (asset_guid, change_type, field_name, old_value, new_value, changed_by, notes)
        )

    # =========================================================================
    # STATISTICS
    # =========================================================================

    def get_statistics(self) -> Dict[str, Any]:
        """Get asset registry statistics"""
        conn = self._get_connection()
        try:
            stats = {}

            # Total assets
            cursor = conn.execute("SELECT COUNT(*) FROM assets")
            stats['total_assets'] = cursor.fetchone()[0]

            # By discipline
            cursor = conn.execute("SELECT discipline, COUNT(*) FROM assets GROUP BY discipline")
            stats['by_discipline'] = {row[0]: row[1] for row in cursor.fetchall() if row[0]}

            # By status
            cursor = conn.execute("SELECT status, COUNT(*) FROM assets GROUP BY status")
            stats['by_status'] = {row[0]: row[1] for row in cursor.fetchall() if row[0]}

            # By condition
            cursor = conn.execute("SELECT condition, COUNT(*) FROM assets GROUP BY condition")
            stats['by_condition'] = {row[0]: row[1] for row in cursor.fetchall() if row[0]}

            return stats
        finally:
            conn.close()

    # =========================================================================
    # UTILITIES
    # =========================================================================

    def _guess_mime_type(self, filename: str) -> str:
        """Guess MIME type from file extension"""
        ext = filename.lower().split('.')[-1] if '.' in filename else ''
        mime_types = {
            'pdf': 'application/pdf',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'xls': 'application/vnd.ms-excel',
            'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }
        return mime_types.get(ext, 'application/octet-stream')
