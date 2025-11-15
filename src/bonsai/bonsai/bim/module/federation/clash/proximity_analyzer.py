"""
Proximity Analyzer - Spatial Intelligence for Clash Resolution
==============================================================

Analyzes the "blast radius" of moving elements during clash resolution.
Uses R-tree spatial indexing to find nearby elements and predict impact.

Key Features:
- Find elements within radius of a point
- Calculate clearances and potential new clashes
- Warn about connected/linked elements (MEP systems, structural supports)
- Rank resolution options by minimal disruption

Integration: Enhances clash group resolution with proximity awareness
"""

import sqlite3
import math
from typing import List, Dict, Tuple, Optional
from datetime import datetime
from pathlib import Path


class ProximityAnalyzer:
    """
    Analyzes spatial proximity for intelligent clash resolution

    Uses SQLite R-tree index for fast spatial queries
    """

    def __init__(self, database_path: str):
        """
        Initialize proximity analyzer

        Args:
            database_path: Path to federation database with R-tree index
        """
        self.database_path = database_path
        self._ensure_proximity_table_exists()

    def _ensure_proximity_table_exists(self):
        """Create proximity_analysis table if it doesn't exist"""
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS proximity_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clash_group_id INTEGER,
                cascade_guid TEXT,
                nearby_guid TEXT,
                distance_mm REAL,
                clearance_mm REAL,
                is_potential_clash INTEGER,
                analysis_timestamp TEXT,
                FOREIGN KEY (clash_group_id) REFERENCES clash_groups(group_id)
            )
        """)

        # Create index for fast lookup
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_proximity_clash_group
            ON proximity_analysis(clash_group_id)
        """)

        conn.commit()
        conn.close()

    def calculate_distance_mm(
        self,
        point_a_mm: Tuple[float, float, float],
        point_b_mm: Tuple[float, float, float]
    ) -> float:
        """
        Calculate 3D Euclidean distance between two points

        Args:
            point_a_mm: First point (x, y, z) in millimeters
            point_b_mm: Second point (x, y, z) in millimeters

        Returns:
            Distance in millimeters
        """
        dx = point_b_mm[0] - point_a_mm[0]
        dy = point_b_mm[1] - point_a_mm[1]
        dz = point_b_mm[2] - point_a_mm[2]

        return math.sqrt(dx*dx + dy*dy + dz*dz)

    def find_nearby_elements(
        self,
        center_mm: Tuple[float, float, float],
        radius_mm: float
    ) -> List[Dict]:
        """
        Find all elements within radius of center point

        Args:
            center_mm: Center point (x, y, z) in millimeters
            radius_mm: Search radius in millimeters

        Returns:
            List of dicts with element info:
            [
                {
                    'guid': str,
                    'discipline': str,
                    'ifc_class': str,
                    'distance_mm': float,
                    'bbox_center_mm': tuple
                },
                ...
            ]
        """
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()

        # Use R-tree to find elements in bounding box
        # R-tree uses min/max coords, so create box around center ± radius
        min_x = center_mm[0] - radius_mm
        max_x = center_mm[0] + radius_mm
        min_y = center_mm[1] - radius_mm
        max_y = center_mm[1] + radius_mm
        min_z = center_mm[2] - radius_mm
        max_z = center_mm[2] + radius_mm

        cursor.execute("""
            SELECT
                m.guid,
                m.discipline,
                m.ifc_class,
                r.minX, r.maxX,
                r.minY, r.maxY,
                r.minZ, r.maxZ
            FROM elements_rtree r
            JOIN elements_meta m ON r.id = m.guid
            WHERE
                r.minX <= ? AND r.maxX >= ? AND
                r.minY <= ? AND r.maxY >= ? AND
                r.minZ <= ? AND r.maxZ >= ?
        """, (max_x, min_x, max_y, min_y, max_z, min_z))

        results = []
        for row in cursor.fetchall():
            guid = row[0]
            discipline = row[1]
            ifc_class = row[2]

            # Calculate bbox center
            bbox_center = (
                (row[3] + row[4]) / 2.0,  # (min_x + max_x) / 2
                (row[5] + row[6]) / 2.0,  # (min_y + max_y) / 2
                (row[7] + row[8]) / 2.0   # (min_z + max_z) / 2
            )

            # Calculate actual distance from center to bbox center
            distance = self.calculate_distance_mm(center_mm, bbox_center)

            # Only include if within radius (R-tree gives us candidates, we filter exactly)
            if distance <= radius_mm:
                results.append({
                    'guid': guid,
                    'discipline': discipline,
                    'ifc_class': ifc_class,
                    'distance_mm': distance,
                    'bbox_center_mm': bbox_center
                })

        conn.close()

        # Sort by distance (closest first)
        results.sort(key=lambda x: x['distance_mm'])

        return results

    def analyze_impact_radius(
        self,
        element_guid: str,
        current_position_mm: Tuple[float, float, float],
        proposed_position_mm: Tuple[float, float, float],
        check_radius_mm: float = 2000  # Default 2 meters
    ) -> Dict:
        """
        Analyze impact of moving an element to a new position

        Args:
            element_guid: GUID of element being moved
            current_position_mm: Current position (x, y, z) in mm
            proposed_position_mm: Proposed new position (x, y, z) in mm
            check_radius_mm: Radius to check for nearby elements (default 2m)

        Returns:
            Dict with impact analysis:
            {
                'nearby_count': int,
                'potential_clashes': list,
                'clearance_warnings': list,
                'linked_elements': list
            }
        """
        # Find elements near proposed position
        nearby = self.find_nearby_elements(proposed_position_mm, check_radius_mm)

        # Analyze potential clashes (elements too close)
        MIN_CLEARANCE_MM = 50  # 50mm minimum clearance
        potential_clashes = []
        clearance_warnings = []

        for element in nearby:
            # Skip self
            if element['guid'] == element_guid:
                continue

            distance = element['distance_mm']

            # Potential clash if too close
            if distance < MIN_CLEARANCE_MM:
                potential_clashes.append({
                    'guid': element['guid'],
                    'discipline': element['discipline'],
                    'ifc_class': element['ifc_class'],
                    'clearance_mm': distance,
                    'severity': 'HIGH'
                })
            # Warning if marginal clearance
            elif distance < 200:  # 200mm warning threshold
                clearance_warnings.append({
                    'guid': element['guid'],
                    'discipline': element['discipline'],
                    'ifc_class': element['ifc_class'],
                    'clearance_mm': distance,
                    'severity': 'MEDIUM'
                })

        return {
            'nearby_count': len(nearby),
            'potential_clashes': potential_clashes,
            'clearance_warnings': clearance_warnings,
            'linked_elements': []  # TODO: Detect linked elements (MEP systems, etc.)
        }

    def analyze_and_store(
        self,
        clash_group_id: int,
        cascade_guid: str,
        cascade_position_mm: Tuple[float, float, float],
        check_radius_mm: float = 2000
    ):
        """
        Analyze proximity and store results to database

        Args:
            clash_group_id: ID of clash group being analyzed
            cascade_guid: GUID of cascade element
            cascade_position_mm: Position of cascade element (x, y, z) in mm
            check_radius_mm: Radius to check (default 2m)
        """
        # Find nearby elements
        nearby = self.find_nearby_elements(cascade_position_mm, check_radius_mm)

        # Store results
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()

        timestamp = datetime.now().isoformat()

        for element in nearby:
            # Skip self
            if element['guid'] == cascade_guid:
                continue

            distance = element['distance_mm']
            clearance = distance  # Same as distance for now
            is_potential_clash = 1 if distance < 50 else 0  # 50mm threshold

            cursor.execute("""
                INSERT INTO proximity_analysis
                (clash_group_id, cascade_guid, nearby_guid, distance_mm,
                 clearance_mm, is_potential_clash, analysis_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                clash_group_id,
                cascade_guid,
                element['guid'],
                distance,
                clearance,
                is_potential_clash,
                timestamp
            ))

        conn.commit()
        conn.close()

    def get_proximity_data_for_group(self, clash_group_id: int) -> List[Dict]:
        """
        Retrieve stored proximity analysis for a clash group

        Args:
            clash_group_id: ID of clash group

        Returns:
            List of proximity analysis records
        """
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                nearby_guid,
                distance_mm,
                clearance_mm,
                is_potential_clash,
                analysis_timestamp
            FROM proximity_analysis
            WHERE clash_group_id = ?
            ORDER BY distance_mm ASC
        """, (clash_group_id,))

        results = []
        for row in cursor.fetchall():
            results.append({
                'nearby_guid': row[0],
                'distance_mm': row[1],
                'clearance_mm': row[2],
                'is_potential_clash': bool(row[3]),
                'timestamp': row[4]
            })

        conn.close()
        return results

    def generate_proximity_report(
        self,
        clash_group_id: str,
        cascade_guid: str,
        output_path: Optional[str] = None
    ) -> Dict:
        """
        Generate proximity analysis report for a clash group

        Creates comprehensive report showing:
        - Nearby elements within impact radius
        - Potential new clashes if element is moved
        - Clearance warnings
        - Affected disciplines

        Args:
            clash_group_id: ID of clash group
            cascade_guid: GUID of cascade element
            output_path: Optional path to save report JSON

        Returns:
            Report dict with analysis results
        """
        # Get proximity data from database
        proximity_data = self.get_proximity_data_for_group(clash_group_id)

        # Get element metadata
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT discipline, ifc_class
            FROM elements_meta
            WHERE guid = ?
        """, (cascade_guid,))
        cascade_meta = cursor.fetchone()

        cascade_discipline = cascade_meta[0] if cascade_meta else 'Unknown'
        cascade_class = cascade_meta[1] if cascade_meta else 'Unknown'

        # Categorize nearby elements
        potential_clashes = []
        clearance_warnings = []
        nearby_by_discipline = {}

        for elem in proximity_data:
            # Get element details
            cursor.execute("""
                SELECT discipline, ifc_class
                FROM elements_meta
                WHERE guid = ?
            """, (elem['nearby_guid'],))
            elem_meta = cursor.fetchone()

            if elem_meta:
                discipline = elem_meta[0] or 'Unknown'
                ifc_class = elem_meta[1] or 'Unknown'

                # Categorize by clearance
                if elem['is_potential_clash']:
                    potential_clashes.append({
                        'guid': elem['nearby_guid'],
                        'discipline': discipline,
                        'ifc_class': ifc_class,
                        'clearance_mm': elem['clearance_mm'],
                        'severity': 'HIGH'
                    })
                elif elem['distance_mm'] < 200:  # Warning threshold
                    clearance_warnings.append({
                        'guid': elem['nearby_guid'],
                        'discipline': discipline,
                        'ifc_class': ifc_class,
                        'clearance_mm': elem['clearance_mm'],
                        'severity': 'MEDIUM'
                    })

                # Count by discipline
                if discipline not in nearby_by_discipline:
                    nearby_by_discipline[discipline] = 0
                nearby_by_discipline[discipline] += 1

        conn.close()

        # Build report
        report = {
            'clash_group_id': clash_group_id,
            'cascade_element': {
                'guid': cascade_guid,
                'discipline': cascade_discipline,
                'ifc_class': cascade_class
            },
            'analysis_summary': {
                'total_nearby_elements': len(proximity_data),
                'potential_new_clashes': len(potential_clashes),
                'clearance_warnings': len(clearance_warnings),
                'affected_disciplines': list(nearby_by_discipline.keys()),
                'discipline_breakdown': nearby_by_discipline
            },
            'potential_clashes': potential_clashes,
            'clearance_warnings': clearance_warnings,
            'timestamp': datetime.now().isoformat()
        }

        # Save to file if requested
        if output_path:
            import json
            with open(output_path, 'w') as f:
                json.dump(report, f, indent=2)

        return report

    def generate_proximity_report_for_all_groups(
        self,
        output_dir: Optional[str] = None
    ) -> List[Dict]:
        """
        Generate proximity reports for all clash groups

        Args:
            output_dir: Optional directory to save individual report JSONs

        Returns:
            List of report dicts, one per group
        """
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()

        # Get all clash groups
        cursor.execute("""
            SELECT group_id, cascade_element_guid
            FROM clash_groups
        """)
        groups = cursor.fetchall()
        conn.close()

        reports = []
        for group_id, cascade_guid in groups:
            # Generate report
            report_path = None
            if output_dir:
                from pathlib import Path
                Path(output_dir).mkdir(parents=True, exist_ok=True)
                report_path = str(Path(output_dir) / f"proximity_report_{group_id}.json")

            report = self.generate_proximity_report(
                clash_group_id=group_id,
                cascade_guid=cascade_guid,
                output_path=report_path
            )
            reports.append(report)

        return reports
