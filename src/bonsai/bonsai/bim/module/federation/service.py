# Bonsai - OpenBIM Blender Add-on
# Copyright (C) 2025 Your Engineering Firm
#
# This file is part of Bonsai.
#
# Bonsai is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
Federation Data Service
-----------------------
Singleton service providing centralized access to federation data for all Bonsai modules.

This service acts as a bridge between the federation database and other Bonsai modules
(clash, qto, sequence, etc.), allowing them to leverage federated data without tight coupling.

Usage:
    from bonsai.bim.module.federation.service import FederationDataService

    service = FederationDataService.get_instance()
    if service.is_available():
        candidates = service.get_clash_candidates()
"""

from __future__ import annotations
import bpy
from pathlib import Path
from typing import Optional, List, Dict, Tuple, Any
import sqlite3


class FederationDataService:
    """
    Singleton service for accessing federation data across Bonsai modules.

    Provides:
    - Clash candidate queries (for clash module speedup)
    - Quantity aggregation (for qto module)
    - Spatial zone queries (for sequence module)
    - IFC synchronization (sync DB ↔ IFC after edits)
    """

    _instance: Optional[FederationDataService] = None

    def __init__(self):
        """Private constructor - use get_instance() instead"""
        self._db_path: Optional[str] = None
        self._connection: Optional[sqlite3.Connection] = None

    @classmethod
    def get_instance(cls) -> FederationDataService:
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """Reset singleton (for testing or reload)"""
        if cls._instance and cls._instance._connection:
            cls._instance._connection.close()
        cls._instance = None

    # =========================================================================
    # Lifecycle Management
    # =========================================================================

    def initialize(self, db_path: str) -> bool:
        """
        Initialize service with federation database

        Args:
            db_path: Absolute path to federation SQLite database

        Returns:
            True if initialized successfully
        """
        if not Path(db_path).exists():
            print(f"⚠ FederationDataService: Database not found: {db_path}")
            return False

        try:
            self._db_path = db_path
            self._connection = sqlite3.connect(db_path)
            self._connection.row_factory = sqlite3.Row  # Enable column access by name
            print(f"✓ FederationDataService initialized: {db_path}")
            return True
        except Exception as e:
            print(f"⚠ FederationDataService initialization failed: {e}")
            self._db_path = None
            self._connection = None
            return False

    def is_available(self) -> bool:
        """Check if service is ready to use"""
        return self._connection is not None

    def close(self):
        """Close database connection"""
        if self._connection:
            self._connection.close()
            self._connection = None
            self._db_path = None

    # =========================================================================
    # Clash Detection Speedup
    # =========================================================================

    def get_clash_candidates(
        self,
        discipline_a: Optional[str] = None,
        discipline_b: Optional[str] = None,
        bbox_filter: Optional[Tuple[float, float, float, float, float, float]] = None
    ) -> List[Dict[str, Any]]:
        """
        Get clash candidates with optional filtering

        This is the primary speedup for clash detection - pre-filters elements
        from the database before expensive geometric clash tests.

        Args:
            discipline_a: Filter for first discipline (e.g., "ACMV")
            discipline_b: Filter for second discipline (e.g., "STR")
            bbox_filter: (min_x, min_y, min_z, max_x, max_y, max_z) spatial filter

        Returns:
            List of element dicts with keys: global_id, ifc_class, discipline, bbox
        """
        if not self.is_available():
            return []

        try:
            query = "SELECT global_id, ifc_class, discipline, min_x, min_y, min_z, max_x, max_y, max_z FROM elements WHERE 1=1"
            params = []

            if discipline_a:
                query += " AND discipline = ?"
                params.append(discipline_a)

            if bbox_filter:
                min_x, min_y, min_z, max_x, max_y, max_z = bbox_filter
                query += """ AND NOT (
                    max_x < ? OR min_x > ? OR
                    max_y < ? OR min_y > ? OR
                    max_z < ? OR min_z > ?
                )"""
                params.extend([min_x, max_x, min_y, max_y, min_z, max_z])

            cursor = self._connection.cursor()
            cursor.execute(query, params)

            results = []
            for row in cursor.fetchall():
                results.append({
                    'global_id': row['global_id'],
                    'ifc_class': row['ifc_class'],
                    'discipline': row['discipline'],
                    'bbox': (
                        row['min_x'], row['min_y'], row['min_z'],
                        row['max_x'], row['max_y'], row['max_z']
                    )
                })

            return results

        except Exception as e:
            print(f"⚠ FederationDataService.get_clash_candidates failed: {e}")
            return []

    # =========================================================================
    # Quantity Aggregation (for QTO module)
    # =========================================================================

    def aggregate_quantities(
        self,
        ifc_class: Optional[str] = None,
        discipline: Optional[str] = None
    ) -> Dict[str, Dict[str, float]]:
        """
        Aggregate quantities from federation database

        Args:
            ifc_class: Filter by IFC class (e.g., "IfcWall")
            discipline: Filter by discipline (e.g., "ARC")

        Returns:
            Dict mapping IFC class to aggregated quantities:
            {
                "IfcWall": {"count": 150, "volume": 2500.5, "area": 3200.0},
                "IfcSlab": {"count": 25, "volume": 1800.2, "area": 2100.0}
            }
        """
        if not self.is_available():
            return {}

        try:
            query = "SELECT ifc_class, COUNT(*) as count FROM elements WHERE 1=1"
            params = []

            if ifc_class:
                query += " AND ifc_class = ?"
                params.append(ifc_class)

            if discipline:
                query += " AND discipline = ?"
                params.append(discipline)

            query += " GROUP BY ifc_class"

            cursor = self._connection.cursor()
            cursor.execute(query, params)

            results = {}
            for row in cursor.fetchall():
                results[row['ifc_class']] = {
                    'count': row['count'],
                    # TODO: Add volume/area once stored in DB
                }

            return results

        except Exception as e:
            print(f"⚠ FederationDataService.aggregate_quantities failed: {e}")
            return {}

    # =========================================================================
    # Spatial Zone Queries (for Sequence/4D module)
    # =========================================================================

    def get_elements_in_zone(
        self,
        zone_bbox: Tuple[float, float, float, float, float, float],
        discipline: Optional[str] = None
    ) -> List[str]:
        """
        Get element GlobalIds within a spatial zone (for 4D scheduling)

        Args:
            zone_bbox: (min_x, min_y, min_z, max_x, max_y, max_z) zone bounds
            discipline: Optional discipline filter

        Returns:
            List of GlobalIds of elements within the zone
        """
        if not self.is_available():
            return []

        try:
            min_x, min_y, min_z, max_x, max_y, max_z = zone_bbox

            query = """
                SELECT global_id FROM elements WHERE
                NOT (max_x < ? OR min_x > ? OR
                     max_y < ? OR min_y > ? OR
                     max_z < ? OR min_z > ?)
            """
            params = [min_x, max_x, min_y, max_y, min_z, max_z]

            if discipline:
                query += " AND discipline = ?"
                params.append(discipline)

            cursor = self._connection.cursor()
            cursor.execute(query, params)

            return [row['global_id'] for row in cursor.fetchall()]

        except Exception as e:
            print(f"⚠ FederationDataService.get_elements_in_zone failed: {e}")
            return []

    # =========================================================================
    # IFC Synchronization
    # =========================================================================

    def sync_from_ifc(self, ifc_file_path: str):
        """
        Sync federation database from IFC file after Bonsai edits

        This should be called after user edits in Bonsai to update the
        federation database with latest changes.

        Args:
            ifc_file_path: Path to IFC file that was edited
        """
        if not self.is_available():
            print("⚠ FederationDataService not available for sync")
            return

        # TODO: Implement using federation_preprocessor.py logic
        print(f"TODO: Sync federation DB from {ifc_file_path}")

    def export_to_ifc(self, global_id: str, changes: Dict[str, Any]) -> bool:
        """
        Export database changes back to IFC using ifcopenshell.api.run()

        Args:
            global_id: Element GlobalId to update
            changes: Dict of property changes to apply

        Returns:
            True if successful
        """
        if not self.is_available():
            print("⚠ FederationDataService not available for export")
            return False

        # TODO: Implement using ifcopenshell.api.run() to modify source IFC
        print(f"TODO: Export changes for {global_id}: {changes}")
        return False

    # =========================================================================
    # Database Statistics
    # =========================================================================

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get federation database statistics

        Returns:
            Dict with keys: total_elements, disciplines, ifc_classes
        """
        if not self.is_available():
            return {'total_elements': 0, 'disciplines': [], 'ifc_classes': []}

        try:
            cursor = self._connection.cursor()

            # Total elements
            cursor.execute("SELECT COUNT(*) as count FROM elements")
            total = cursor.fetchone()['count']

            # Disciplines
            cursor.execute("SELECT DISTINCT discipline FROM elements ORDER BY discipline")
            disciplines = [row['discipline'] for row in cursor.fetchall()]

            # IFC classes
            cursor.execute("SELECT DISTINCT ifc_class FROM elements ORDER BY ifc_class")
            ifc_classes = [row['ifc_class'] for row in cursor.fetchall()]

            return {
                'total_elements': total,
                'disciplines': disciplines,
                'ifc_classes': ifc_classes
            }

        except Exception as e:
            print(f"⚠ FederationDataService.get_statistics failed: {e}")
            return {'total_elements': 0, 'disciplines': [], 'ifc_classes': []}


# =============================================================================
# Blender Integration Helpers
# =============================================================================

def get_service_from_context() -> Optional[FederationDataService]:
    """
    Get FederationDataService instance from Blender context

    Automatically initializes from scene properties if available.

    Returns:
        FederationDataService instance or None if not available
    """
    service = FederationDataService.get_instance()

    # Auto-initialize from scene if not already initialized
    if not service.is_available() and hasattr(bpy.context, 'scene'):
        props = bpy.context.scene.BIMFederationProperties
        if props.federation_database_path:
            db_path = bpy.path.abspath(props.federation_database_path)
            service.initialize(db_path)

    return service if service.is_available() else None
