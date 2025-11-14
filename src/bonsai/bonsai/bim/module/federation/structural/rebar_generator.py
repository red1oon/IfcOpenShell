"""
Rebar Generator - Creates IFC reinforcement entities from structural elements
Integrates with Bonsai Federation Module database
Generates IfcReinforcingBar and IfcReinforcingMesh entities
"""

import sqlite3
import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.api
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import uuid
import math

from .rebar_standards import (
    SlabReinforcementRules,
    BeamReinforcementRules,
    ColumnReinforcementRules,
    ConcreteGrade,
    ExposureClass,
    RebarProperties,
    RebarPricing
)


@dataclass
class BoundingBox:
    """Simple bounding box for element dimensions"""
    min_x: float
    min_y: float
    min_z: float
    max_x: float
    max_y: float
    max_z: float

    @property
    def length(self) -> float:
        return self.max_x - self.min_x

    @property
    def width(self) -> float:
        return self.max_y - self.min_y

    @property
    def height(self) -> float:
        return self.max_z - self.min_z


class RebarGenerator:
    """
    Main rebar generation engine
    Reads STR elements from database, applies rules, creates rebar entities
    """

    def __init__(self, database_path: str, is_airport: bool = False):
        """
        Initialize generator
        Args:
            database_path: Path to federation database
            is_airport: Use airport-grade standards (heavier reinforcement)
        """
        self.database_path = database_path
        self.is_airport = is_airport
        self.conn = None
        self.concrete_grade = ConcreteGrade.GRADE_40 if is_airport else ConcreteGrade.GRADE_30
        self.exposure_class = ExposureClass.XD1 if is_airport else ExposureClass.XC3

    def connect(self):
        """Connect to database"""
        self.conn = sqlite3.connect(self.database_path)
        self.conn.row_factory = sqlite3.Row

    def disconnect(self):
        """Disconnect from database"""
        if self.conn:
            self.conn.close()

    def get_element_dimensions(self, guid: str) -> Optional[BoundingBox]:
        """
        Get element bounding box from database
        Uses base_geometries table for bbox data
        """
        cursor = self.conn.execute("""
            SELECT bbox_min_x, bbox_min_y, bbox_min_z,
                   bbox_max_x, bbox_max_y, bbox_max_z
            FROM base_geometries
            WHERE guid = ?
        """, (guid,))

        row = cursor.fetchone()
        if not row:
            return None

        return BoundingBox(
            min_x=row['bbox_min_x'],
            min_y=row['bbox_min_y'],
            min_z=row['bbox_min_z'],
            max_x=row['bbox_max_x'],
            max_y=row['bbox_max_y'],
            max_z=row['bbox_max_z']
        )

    def get_element_volume(self, guid: str) -> Optional[float]:
        """Get element volume from properties (m³)"""
        cursor = self.conn.execute("""
            SELECT property_value
            FROM element_properties
            WHERE guid = ? AND property_name = 'NetVolume'
        """, (guid,))

        row = cursor.fetchone()
        if row:
            return float(row['property_value'])
        return None

    def get_str_elements(self, ifc_class: Optional[str] = None) -> List[Dict]:
        """
        Get all STR elements from database
        Args:
            ifc_class: Filter by specific IFC class (IfcSlab, IfcBeam, IfcColumn)
        Returns:
            List of element dictionaries
        """
        query = """
            SELECT guid, ifc_class, element_name, element_type,
                   storey, material_name
            FROM elements_meta
            WHERE discipline = 'STR'
        """

        if ifc_class:
            query += f" AND ifc_class = '{ifc_class}'"

        query += " ORDER BY ifc_class, guid"

        cursor = self.conn.execute(query)
        return [dict(row) for row in cursor.fetchall()]

    def generate_slab_rebar(self, element: Dict) -> Dict:
        """
        Generate reinforcement for a slab element
        Returns rebar specification dictionary
        """
        guid = element['guid']
        bbox = self.get_element_dimensions(guid)
        volume = self.get_element_volume(guid)

        if not bbox:
            return {'error': 'No geometry found'}

        # Get dimensions (convert to mm)
        thickness_mm = bbox.height * 1000
        length_mm = bbox.length * 1000
        width_mm = bbox.width * 1000

        # Generate rebar using standards
        rebar_spec = SlabReinforcementRules.calculate_reinforcement(
            slab_thickness_mm=thickness_mm,
            slab_length_mm=length_mm,
            slab_width_mm=width_mm,
            concrete_grade=self.concrete_grade,
            exposure=self.exposure_class,
            is_airport=self.is_airport
        )

        # Add element info
        rebar_spec['element_guid'] = guid
        rebar_spec['element_name'] = element['element_name']
        rebar_spec['element_type'] = element['element_type']
        rebar_spec['ifc_class'] = element['ifc_class']
        rebar_spec['concrete_volume_m3'] = volume

        # Add cost breakdown
        cost = RebarPricing.calculate_total_cost(
            rebar_spec['total_weight_kg'],
            rebar_spec['main_bars']['diameter']
        )
        rebar_spec['cost'] = cost

        return rebar_spec

    def generate_beam_rebar(self, element: Dict) -> Dict:
        """
        Generate reinforcement for a beam element
        Returns rebar specification dictionary
        """
        guid = element['guid']
        bbox = self.get_element_dimensions(guid)
        volume = self.get_element_volume(guid)

        if not bbox:
            return {'error': 'No geometry found'}

        # Get dimensions (convert to mm)
        # For beams: length is along longest axis
        dims = sorted([bbox.length, bbox.width, bbox.height])
        width_mm = dims[0] * 1000   # Smallest = width
        height_mm = dims[1] * 1000  # Middle = height
        length_mm = dims[2] * 1000  # Largest = length

        # Generate rebar using standards
        rebar_spec = BeamReinforcementRules.calculate_reinforcement(
            beam_width_mm=width_mm,
            beam_height_mm=height_mm,
            beam_length_mm=length_mm,
            concrete_grade=self.concrete_grade,
            exposure=self.exposure_class,
            is_airport=self.is_airport
        )

        # Add element info
        rebar_spec['element_guid'] = guid
        rebar_spec['element_name'] = element['element_name']
        rebar_spec['element_type'] = element['element_type']
        rebar_spec['ifc_class'] = element['ifc_class']
        rebar_spec['concrete_volume_m3'] = volume

        # Add cost breakdown
        cost = RebarPricing.calculate_total_cost(
            rebar_spec['total_weight_kg'],
            rebar_spec['bottom_bars']['diameter']
        )
        rebar_spec['cost'] = cost

        return rebar_spec

    def generate_column_rebar(self, element: Dict) -> Dict:
        """
        Generate reinforcement for a column element
        Returns rebar specification dictionary
        """
        guid = element['guid']
        bbox = self.get_element_dimensions(guid)
        volume = self.get_element_volume(guid)

        if not bbox:
            return {'error': 'No geometry found'}

        # Get dimensions (convert to mm)
        # For columns: height is along tallest axis
        dims = sorted([bbox.length, bbox.width, bbox.height])
        width_mm = dims[0] * 1000   # Smallest = width
        depth_mm = dims[1] * 1000   # Middle = depth
        height_mm = dims[2] * 1000  # Largest = height

        # Generate rebar using standards
        rebar_spec = ColumnReinforcementRules.calculate_reinforcement(
            column_width_mm=width_mm,
            column_depth_mm=depth_mm,
            column_height_mm=height_mm,
            concrete_grade=self.concrete_grade,
            exposure=self.exposure_class,
            is_airport=self.is_airport
        )

        # Add element info
        rebar_spec['element_guid'] = guid
        rebar_spec['element_name'] = element['element_name']
        rebar_spec['element_type'] = element['element_type']
        rebar_spec['ifc_class'] = element['ifc_class']
        rebar_spec['concrete_volume_m3'] = volume

        # Add cost breakdown
        cost = RebarPricing.calculate_total_cost(
            rebar_spec['total_weight_kg'],
            rebar_spec['longitudinal_bars']['diameter']
        )
        rebar_spec['cost'] = cost

        return rebar_spec

    def generate_all_rebar(self, progress_callback=None) -> Dict[str, List[Dict]]:
        """
        Generate rebar for all STR elements in database
        Args:
            progress_callback: Optional function(current, total, message)
        Returns:
            Dictionary with rebar specs organized by element type
        """
        self.connect()

        results = {
            'slabs': [],
            'beams': [],
            'columns': [],
            'errors': []
        }

        # Process slabs
        slabs = self.get_str_elements('IfcSlab')
        print(f"\n🏗️  Processing {len(slabs)} slabs...")
        for idx, slab in enumerate(slabs):
            if progress_callback:
                progress_callback(idx + 1, len(slabs), f"Slab {slab['guid'][:8]}...")

            try:
                rebar = self.generate_slab_rebar(slab)
                if 'error' not in rebar:
                    results['slabs'].append(rebar)
                else:
                    results['errors'].append({'element': slab, 'error': rebar['error']})
            except Exception as e:
                results['errors'].append({'element': slab, 'error': str(e)})

        # Process beams
        beams = self.get_str_elements('IfcBeam')
        print(f"\n🏗️  Processing {len(beams)} beams...")
        for idx, beam in enumerate(beams):
            if progress_callback:
                progress_callback(idx + 1, len(beams), f"Beam {beam['guid'][:8]}...")

            try:
                rebar = self.generate_beam_rebar(beam)
                if 'error' not in rebar:
                    results['beams'].append(rebar)
                else:
                    results['errors'].append({'element': beam, 'error': rebar['error']})
            except Exception as e:
                results['errors'].append({'element': beam, 'error': str(e)})

        # Process columns
        columns = self.get_str_elements('IfcColumn')
        print(f"\n🏗️  Processing {len(columns)} columns...")
        for idx, column in enumerate(columns):
            if progress_callback:
                progress_callback(idx + 1, len(columns), f"Column {column['guid'][:8]}...")

            try:
                rebar = self.generate_column_rebar(column)
                if 'error' not in rebar:
                    results['columns'].append(rebar)
                else:
                    results['errors'].append({'element': column, 'error': rebar['error']})
            except Exception as e:
                results['errors'].append({'element': column, 'error': str(e)})

        self.disconnect()

        return results

    def save_to_database(self, rebar_results: Dict[str, List[Dict]]):
        """
        Save generated rebar to database
        Creates/updates reinforcement tables
        """
        self.connect()

        # Create tables if they don't exist
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS reinforcement_bars (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_guid TEXT NOT NULL,
                bar_type TEXT NOT NULL,
                diameter_mm INTEGER NOT NULL,
                count INTEGER NOT NULL,
                length_each_m REAL NOT NULL,
                length_total_m REAL NOT NULL,
                weight_kg REAL NOT NULL,
                spacing_mm INTEGER,
                direction TEXT,
                FOREIGN KEY (parent_guid) REFERENCES elements_meta(guid)
            )
        """)

        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS reinforcement_summary (
                parent_guid TEXT PRIMARY KEY,
                ifc_class TEXT NOT NULL,
                element_name TEXT,
                total_weight_kg REAL NOT NULL,
                total_length_m REAL NOT NULL,
                total_bars INTEGER NOT NULL,
                concrete_volume_m3 REAL,
                material_cost_rm REAL NOT NULL,
                labor_cost_rm REAL NOT NULL,
                total_cost_rm REAL NOT NULL,
                generated_timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (parent_guid) REFERENCES elements_meta(guid)
            )
        """)

        # Clear existing data (regeneration)
        self.conn.execute("DELETE FROM reinforcement_bars")
        self.conn.execute("DELETE FROM reinforcement_summary")

        # Insert slab rebar
        for slab in rebar_results['slabs']:
            self._insert_slab_rebar(slab)

        # Insert beam rebar
        for beam in rebar_results['beams']:
            self._insert_beam_rebar(beam)

        # Insert column rebar
        for column in rebar_results['columns']:
            self._insert_column_rebar(column)

        self.conn.commit()
        self.disconnect()

        print(f"\n✅ Saved {len(rebar_results['slabs'])} slabs, {len(rebar_results['beams'])} beams, {len(rebar_results['columns'])} columns to database")

    def _insert_slab_rebar(self, spec: Dict):
        """Insert slab rebar into database"""
        guid = spec['element_guid']

        # Main bars
        self.conn.execute("""
            INSERT INTO reinforcement_bars
            (parent_guid, bar_type, diameter_mm, count, length_each_m, length_total_m,
             weight_kg, spacing_mm, direction)
            VALUES (?, 'MAIN', ?, ?, ?, ?, ?, ?, ?)
        """, (
            guid,
            spec['main_bars']['diameter'],
            spec['main_bars']['count'],
            spec['main_bars']['length_total_m'] / spec['main_bars']['count'],
            spec['main_bars']['length_total_m'],
            spec['total_weight_kg'] * 0.6,  # Approx 60% in main bars
            spec['main_bars']['spacing'],
            spec['main_bars']['direction']
        ))

        # Distribution bars
        self.conn.execute("""
            INSERT INTO reinforcement_bars
            (parent_guid, bar_type, diameter_mm, count, length_each_m, length_total_m,
             weight_kg, spacing_mm, direction)
            VALUES (?, 'DISTRIBUTION', ?, ?, ?, ?, ?, ?, ?)
        """, (
            guid,
            spec['distribution_bars']['diameter'],
            spec['distribution_bars']['count'],
            spec['distribution_bars']['length_total_m'] / spec['distribution_bars']['count'],
            spec['distribution_bars']['length_total_m'],
            spec['total_weight_kg'] * 0.4,  # Approx 40% in distribution bars
            spec['distribution_bars']['spacing'],
            spec['distribution_bars']['direction']
        ))

        # Summary
        self.conn.execute("""
            INSERT INTO reinforcement_summary
            (parent_guid, ifc_class, element_name, total_weight_kg, total_length_m,
             total_bars, concrete_volume_m3, material_cost_rm, labor_cost_rm, total_cost_rm)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            guid,
            spec['ifc_class'],
            spec['element_name'],
            spec['total_weight_kg'],
            spec['main_bars']['length_total_m'] + spec['distribution_bars']['length_total_m'],
            spec['main_bars']['count'] + spec['distribution_bars']['count'],
            spec['concrete_volume_m3'],
            spec['cost']['material_cost_rm'],
            spec['cost']['labor_cost_rm'],
            spec['cost']['total_cost_rm']
        ))

    def _insert_beam_rebar(self, spec: Dict):
        """Insert beam rebar into database"""
        guid = spec['element_guid']

        # Bottom bars
        self.conn.execute("""
            INSERT INTO reinforcement_bars
            (parent_guid, bar_type, diameter_mm, count, length_each_m, length_total_m,
             weight_kg, direction)
            VALUES (?, 'BOTTOM', ?, ?, ?, ?, ?, 'longitudinal')
        """, (
            guid,
            spec['bottom_bars']['diameter'],
            spec['bottom_bars']['count'],
            spec['bottom_bars']['length_each_m'],
            spec['bottom_bars']['length_total_m'],
            spec['total_weight_kg'] * 0.4
        ))

        # Top bars
        self.conn.execute("""
            INSERT INTO reinforcement_bars
            (parent_guid, bar_type, diameter_mm, count, length_each_m, length_total_m,
             weight_kg, direction)
            VALUES (?, 'TOP', ?, ?, ?, ?, ?, 'longitudinal')
        """, (
            guid,
            spec['top_bars']['diameter'],
            spec['top_bars']['count'],
            spec['top_bars']['length_each_m'],
            spec['top_bars']['length_total_m'],
            spec['total_weight_kg'] * 0.35
        ))

        # Stirrups
        self.conn.execute("""
            INSERT INTO reinforcement_bars
            (parent_guid, bar_type, diameter_mm, count, length_each_m, length_total_m,
             weight_kg, spacing_mm, direction)
            VALUES (?, 'STIRRUP', ?, ?, ?, ?, ?, ?, 'transverse')
        """, (
            guid,
            spec['stirrups']['diameter'],
            spec['stirrups']['count'],
            spec['stirrups']['length_each_m'],
            spec['stirrups']['length_total_m'],
            spec['total_weight_kg'] * 0.25,
            spec['stirrups']['spacing']
        ))

        # Summary
        total_bars = spec['bottom_bars']['count'] + spec['top_bars']['count'] + spec['stirrups']['count']
        total_length = spec['bottom_bars']['length_total_m'] + spec['top_bars']['length_total_m'] + spec['stirrups']['length_total_m']

        self.conn.execute("""
            INSERT INTO reinforcement_summary
            (parent_guid, ifc_class, element_name, total_weight_kg, total_length_m,
             total_bars, concrete_volume_m3, material_cost_rm, labor_cost_rm, total_cost_rm)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            guid,
            spec['ifc_class'],
            spec['element_name'],
            spec['total_weight_kg'],
            total_length,
            total_bars,
            spec['concrete_volume_m3'],
            spec['cost']['material_cost_rm'],
            spec['cost']['labor_cost_rm'],
            spec['cost']['total_cost_rm']
        ))

    def _insert_column_rebar(self, spec: Dict):
        """Insert column rebar into database"""
        guid = spec['element_guid']

        # Longitudinal bars
        self.conn.execute("""
            INSERT INTO reinforcement_bars
            (parent_guid, bar_type, diameter_mm, count, length_each_m, length_total_m,
             weight_kg, direction)
            VALUES (?, 'LONGITUDINAL', ?, ?, ?, ?, ?, 'vertical')
        """, (
            guid,
            spec['longitudinal_bars']['diameter'],
            spec['longitudinal_bars']['count'],
            spec['longitudinal_bars']['length_each_m'],
            spec['longitudinal_bars']['length_total_m'],
            spec['total_weight_kg'] * 0.7
        ))

        # Links/ties
        self.conn.execute("""
            INSERT INTO reinforcement_bars
            (parent_guid, bar_type, diameter_mm, count, length_each_m, length_total_m,
             weight_kg, spacing_mm, direction)
            VALUES (?, 'LINK', ?, ?, ?, ?, ?, ?, 'horizontal')
        """, (
            guid,
            spec['links']['diameter'],
            spec['links']['count'],
            spec['links']['length_each_m'],
            spec['links']['length_total_m'],
            spec['total_weight_kg'] * 0.3,
            spec['links']['spacing']
        ))

        # Summary
        total_bars = spec['longitudinal_bars']['count'] + spec['links']['count']
        total_length = spec['longitudinal_bars']['length_total_m'] + spec['links']['length_total_m']

        self.conn.execute("""
            INSERT INTO reinforcement_summary
            (parent_guid, ifc_class, element_name, total_weight_kg, total_length_m,
             total_bars, concrete_volume_m3, material_cost_rm, labor_cost_rm, total_cost_rm)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            guid,
            spec['ifc_class'],
            spec['element_name'],
            spec['total_weight_kg'],
            total_length,
            total_bars,
            spec['concrete_volume_m3'],
            spec['cost']['material_cost_rm'],
            spec['cost']['labor_cost_rm'],
            spec['cost']['total_cost_rm']
        ))


def print_summary_report(results: Dict[str, List[Dict]]):
    """Print human-readable summary of generated rebar"""
    print("\n" + "=" * 80)
    print("REBAR GENERATION SUMMARY REPORT")
    print("=" * 80)

    # Slabs summary
    if results['slabs']:
        print(f"\n📋 SLABS ({len(results['slabs'])} elements)")
        total_weight = sum(s['total_weight_kg'] for s in results['slabs'])
        total_cost = sum(s['cost']['total_cost_rm'] for s in results['slabs'])
        print(f"   Total weight: {total_weight:,.1f} kg ({total_weight/1000:.2f} tonnes)")
        print(f"   Total cost: RM {total_cost:,.2f}")

    # Beams summary
    if results['beams']:
        print(f"\n🏗️  BEAMS ({len(results['beams'])} elements)")
        total_weight = sum(b['total_weight_kg'] for b in results['beams'])
        total_cost = sum(b['cost']['total_cost_rm'] for b in results['beams'])
        print(f"   Total weight: {total_weight:,.1f} kg ({total_weight/1000:.2f} tonnes)")
        print(f"   Total cost: RM {total_cost:,.2f}")

    # Columns summary
    if results['columns']:
        print(f"\n🏢 COLUMNS ({len(results['columns'])} elements)")
        total_weight = sum(c['total_weight_kg'] for c in results['columns'])
        total_cost = sum(c['cost']['total_cost_rm'] for c in results['columns'])
        print(f"   Total weight: {total_weight:,.1f} kg ({total_weight/1000:.2f} tonnes)")
        print(f"   Total cost: RM {total_cost:,.2f}")

    # Grand total
    print(f"\n" + "-" * 80)
    total_elements = len(results['slabs']) + len(results['beams']) + len(results['columns'])
    grand_weight = sum(s['total_weight_kg'] for s in results['slabs']) + \
                   sum(b['total_weight_kg'] for b in results['beams']) + \
                   sum(c['total_weight_kg'] for c in results['columns'])
    grand_cost = sum(s['cost']['total_cost_rm'] for s in results['slabs']) + \
                 sum(b['cost']['total_cost_rm'] for b in results['beams']) + \
                 sum(c['cost']['total_cost_rm'] for c in results['columns'])

    print(f"GRAND TOTAL ({total_elements} elements)")
    print(f"   Total rebar weight: {grand_weight:,.1f} kg ({grand_weight/1000:.2f} tonnes)")
    print(f"   Total rebar cost: RM {grand_cost:,.2f}")
    print(f"   Average: RM {grand_cost/grand_weight:.2f} per kg")

    # Errors
    if results['errors']:
        print(f"\n⚠️  ERRORS ({len(results['errors'])} elements)")
        for err in results['errors'][:5]:  # Show first 5
            print(f"   - {err['element']['ifc_class']} {err['element']['guid'][:8]}: {err['error']}")
        if len(results['errors']) > 5:
            print(f"   ... and {len(results['errors']) - 5} more")

    print("=" * 80 + "\n")


if __name__ == '__main__':
    # Example usage
    import sys

    if len(sys.argv) < 2:
        print("Usage: python rebar_generator.py <database_path> [--airport]")
        print("Example: python rebar_generator.py /path/to/database.db --airport")
        sys.exit(1)

    db_path = sys.argv[1]
    is_airport = '--airport' in sys.argv

    print("=" * 80)
    print("BONSAI REBAR GENERATOR - KILLER FEATURE")
    print("=" * 80)
    print(f"Database: {db_path}")
    print(f"Standards: {'Airport Grade (MS 1347:2020 + Heavy Duty)' if is_airport else 'Standard (MS 1347:2020)'}")
    print("=" * 80)

    # Generate rebar
    generator = RebarGenerator(db_path, is_airport=is_airport)
    results = generator.generate_all_rebar()

    # Print summary
    print_summary_report(results)

    # Save to database
    print("💾 Saving to database...")
    generator.save_to_database(results)

    print("\n✅ Rebar generation complete!")
    print("📊 Check database tables: reinforcement_bars, reinforcement_summary")
