"""
Concrete Mix Calculator & Logistics Planner
Malaysian concrete standards (MS 76, MS 522)
Calculates raw material requirements, costs, and mixer deployment
"""

import sqlite3
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class ConcreteGrade(Enum):
    """Malaysian concrete grades (MS 76:1972)"""
    GRADE_15 = 15  # Blinding/leveling
    GRADE_20 = 20  # Light duty foundations
    GRADE_25 = 25  # Residential foundations
    GRADE_30 = 30  # Standard structural
    GRADE_35 = 35  # Commercial buildings
    GRADE_40 = 40  # High-rise, airport, infrastructure
    GRADE_45 = 45  # Special structures
    GRADE_50 = 50  # Prestressed concrete


@dataclass
class ConcreteMixDesign:
    """
    Mix design for 1 m³ of concrete
    Based on Malaysian standards and local suppliers
    """
    grade: int
    cement_kg: float        # Portland cement (OPC/PPC)
    coarse_agg_kg: float    # 20mm granite aggregate
    fine_agg_kg: float      # Sand (river/manufactured)
    water_liters: float     # Potable water
    plasticizer_liters: float  # Superplasticizer/admixture

    # Typical strengths
    compressive_strength_mpa: int
    slump_mm: int           # Workability

    # Pricing (RM per m³) - November 2024 Malaysian market
    material_cost_per_m3: float
    labor_cost_per_m3: float
    equipment_cost_per_m3: float

    @staticmethod
    def get_mix_design(grade: ConcreteGrade) -> 'ConcreteMixDesign':
        """
        Get standard mix design for specified grade
        Source: CIDB Malaysia, Ready-mix suppliers (YTL, Lafarge, Cemex)
        """
        designs = {
            ConcreteGrade.GRADE_20: ConcreteMixDesign(
                grade=20,
                cement_kg=300,
                coarse_agg_kg=1150,
                fine_agg_kg=700,
                water_liters=185,
                plasticizer_liters=1.5,
                compressive_strength_mpa=20,
                slump_mm=75,
                material_cost_per_m3=240.00,  # RM per m³
                labor_cost_per_m3=45.00,      # Placement & finishing
                equipment_cost_per_m3=35.00   # Vibrator, tools
            ),
            ConcreteGrade.GRADE_25: ConcreteMixDesign(
                grade=25,
                cement_kg=340,
                coarse_agg_kg=1120,
                fine_agg_kg=690,
                water_liters=180,
                plasticizer_liters=1.8,
                compressive_strength_mpa=25,
                slump_mm=75,
                material_cost_per_m3=265.00,
                labor_cost_per_m3=48.00,
                equipment_cost_per_m3=35.00
            ),
            ConcreteGrade.GRADE_30: ConcreteMixDesign(
                grade=30,
                cement_kg=380,
                coarse_agg_kg=1100,
                fine_agg_kg=680,
                water_liters=175,
                plasticizer_liters=2.0,
                compressive_strength_mpa=30,
                slump_mm=100,
                material_cost_per_m3=290.00,
                labor_cost_per_m3=52.00,
                equipment_cost_per_m3=38.00
            ),
            ConcreteGrade.GRADE_35: ConcreteMixDesign(
                grade=35,
                cement_kg=420,
                coarse_agg_kg=1080,
                fine_agg_kg=670,
                water_liters=170,
                plasticizer_liters=2.3,
                compressive_strength_mpa=35,
                slump_mm=100,
                material_cost_per_m3=315.00,
                labor_cost_per_m3=55.00,
                equipment_cost_per_m3=40.00
            ),
            ConcreteGrade.GRADE_40: ConcreteMixDesign(
                grade=40,
                cement_kg=450,  # Higher cement content for airport
                coarse_agg_kg=1050,
                fine_agg_kg=660,
                water_liters=165,
                plasticizer_liters=2.5,
                compressive_strength_mpa=40,
                slump_mm=125,  # Higher slump for easier placement
                material_cost_per_m3=350.00,  # Premium grade
                labor_cost_per_m3=60.00,      # Skilled placement
                equipment_cost_per_m3=45.00   # Better equipment
            ),
            ConcreteGrade.GRADE_45: ConcreteMixDesign(
                grade=45,
                cement_kg=490,
                coarse_agg_kg=1030,
                fine_agg_kg=650,
                water_liters=160,
                plasticizer_liters=2.8,
                compressive_strength_mpa=45,
                slump_mm=125,
                material_cost_per_m3=385.00,
                labor_cost_per_m3=65.00,
                equipment_cost_per_m3=48.00
            ),
        }

        return designs.get(grade, designs[ConcreteGrade.GRADE_30])


@dataclass
class ConcreteElement:
    """Concrete element with volume and grade"""
    guid: str
    ifc_class: str
    element_name: str
    storey: str
    volume_m3: float
    grade: ConcreteGrade
    material_name: str


class ConcreteCalculator:
    """
    Calculate concrete requirements from database
    Provides material breakdown, cost analysis, logistics planning
    """

    def __init__(self, database_path: str):
        self.database_path = database_path
        self.conn = None
        self.wastage_factor = 1.05  # 5% wastage (spillage, over-excavation)

    def connect(self):
        """Connect to database"""
        self.conn = sqlite3.connect(self.database_path)
        self.conn.row_factory = sqlite3.Row

    def disconnect(self):
        """Disconnect from database"""
        if self.conn:
            self.conn.close()

    def get_concrete_elements(self) -> List[ConcreteElement]:
        """
        Get all concrete elements from database
        Returns list of ConcreteElement objects
        """
        cursor = self.conn.execute("""
            SELECT
                em.guid,
                em.ifc_class,
                em.element_name,
                em.storey,
                em.material_name,
                CAST(ep.property_value AS REAL) as volume_m3
            FROM elements_meta em
            JOIN element_properties ep ON em.guid = ep.guid
            WHERE em.discipline = 'STR'
            AND ep.property_name = 'NetVolume'
            AND em.material_name LIKE '%Concrete%'
            ORDER BY em.storey, em.ifc_class
        """)

        elements = []
        for row in cursor.fetchall():
            # Determine concrete grade from element type or material name
            grade = self._infer_concrete_grade(row['ifc_class'], row['material_name'])

            elements.append(ConcreteElement(
                guid=row['guid'],
                ifc_class=row['ifc_class'],
                element_name=row['element_name'] or 'Unnamed',
                storey=row['storey'] or 'Unknown',
                volume_m3=row['volume_m3'],
                grade=grade,
                material_name=row['material_name']
            ))

        return elements

    def _infer_concrete_grade(self, ifc_class: str, material_name: str) -> ConcreteGrade:
        """
        Infer concrete grade from element type or material name
        Default to Grade 40 for airport terminals
        """
        # Check material name for grade indicators
        material_lower = material_name.lower()

        if 'grade 20' in material_lower or 'g20' in material_lower:
            return ConcreteGrade.GRADE_20
        elif 'grade 25' in material_lower or 'g25' in material_lower:
            return ConcreteGrade.GRADE_25
        elif 'grade 30' in material_lower or 'g30' in material_lower:
            return ConcreteGrade.GRADE_30
        elif 'grade 35' in material_lower or 'g35' in material_lower:
            return ConcreteGrade.GRADE_35
        elif 'grade 40' in material_lower or 'g40' in material_lower:
            return ConcreteGrade.GRADE_40
        elif 'grade 45' in material_lower or 'g45' in material_lower:
            return ConcreteGrade.GRADE_45

        # Default based on element type (airport terminal assumptions)
        if ifc_class in ['IfcSlab', 'IfcBeam']:
            return ConcreteGrade.GRADE_40  # Airport heavy duty
        elif ifc_class == 'IfcColumn':
            return ConcreteGrade.GRADE_40  # Structural columns
        else:
            return ConcreteGrade.GRADE_30  # Default

    def calculate_materials(self, elements: List[ConcreteElement]) -> Dict:
        """
        Calculate total material requirements
        Returns breakdown by concrete grade
        """
        grade_totals = {}

        for element in elements:
            grade_key = element.grade.value

            if grade_key not in grade_totals:
                grade_totals[grade_key] = {
                    'grade': element.grade,
                    'volume_net_m3': 0,
                    'volume_with_wastage_m3': 0,
                    'element_count': 0,
                    'elements': [],
                    'cement_kg': 0,
                    'coarse_aggregate_kg': 0,
                    'fine_aggregate_kg': 0,
                    'water_liters': 0,
                    'plasticizer_liters': 0,
                    'material_cost_rm': 0,
                    'labor_cost_rm': 0,
                    'equipment_cost_rm': 0,
                    'total_cost_rm': 0
                }

            mix = ConcreteMixDesign.get_mix_design(element.grade)
            volume_with_wastage = element.volume_m3 * self.wastage_factor

            grade_totals[grade_key]['volume_net_m3'] += element.volume_m3
            grade_totals[grade_key]['volume_with_wastage_m3'] += volume_with_wastage
            grade_totals[grade_key]['element_count'] += 1
            grade_totals[grade_key]['elements'].append(element)

            # Materials (calculated with wastage)
            grade_totals[grade_key]['cement_kg'] += mix.cement_kg * volume_with_wastage
            grade_totals[grade_key]['coarse_aggregate_kg'] += mix.coarse_agg_kg * volume_with_wastage
            grade_totals[grade_key]['fine_aggregate_kg'] += mix.fine_agg_kg * volume_with_wastage
            grade_totals[grade_key]['water_liters'] += mix.water_liters * volume_with_wastage
            grade_totals[grade_key]['plasticizer_liters'] += mix.plasticizer_liters * volume_with_wastage

            # Costs
            grade_totals[grade_key]['material_cost_rm'] += mix.material_cost_per_m3 * volume_with_wastage
            grade_totals[grade_key]['labor_cost_rm'] += mix.labor_cost_per_m3 * element.volume_m3
            grade_totals[grade_key]['equipment_cost_rm'] += mix.equipment_cost_per_m3 * element.volume_m3
            grade_totals[grade_key]['total_cost_rm'] += (
                mix.material_cost_per_m3 * volume_with_wastage +
                mix.labor_cost_per_m3 * element.volume_m3 +
                mix.equipment_cost_per_m3 * element.volume_m3
            )

        return grade_totals

    def calculate_logistics(self, elements: List[ConcreteElement]) -> Dict:
        """
        Calculate concrete logistics by location (storey/zone)
        Helps plan mixer deployment and pour sequencing
        """
        location_groups = {}

        for element in elements:
            location = element.storey or 'Unknown'

            if location not in location_groups:
                location_groups[location] = {
                    'location': location,
                    'total_volume_m3': 0,
                    'element_count': 0,
                    'element_types': {},
                    'elements': []
                }

            location_groups[location]['total_volume_m3'] += element.volume_m3
            location_groups[location]['element_count'] += 1
            location_groups[location]['elements'].append(element)

            # Count by type
            if element.ifc_class not in location_groups[location]['element_types']:
                location_groups[location]['element_types'][element.ifc_class] = 0
            location_groups[location]['element_types'][element.ifc_class] += 1

        # Calculate mixer requirements for each location
        for location, data in location_groups.items():
            volume = data['total_volume_m3']

            # Typical ready-mix truck: 6-8 m³ capacity
            # Assume 7 m³ average per truck
            trucks_needed = int(volume / 7) + (1 if volume % 7 > 0 else 0)

            # Pour time estimation (assuming 10 m³/hour placement rate)
            pour_hours = volume / 10

            data['trucks_needed'] = trucks_needed
            data['estimated_pour_hours'] = pour_hours
            data['crew_size'] = max(4, int(pour_hours * 2))  # Minimum 4, scale up

        return location_groups

    def generate_full_report(self) -> Dict:
        """
        Generate comprehensive concrete report
        Includes materials, costs, logistics
        """
        self.connect()

        elements = self.get_concrete_elements()

        if not elements:
            self.disconnect()
            return {'error': 'No concrete elements found'}

        # Calculate materials by grade
        materials = self.calculate_materials(elements)

        # Calculate logistics by location
        logistics = self.calculate_logistics(elements)

        # Grand totals
        grand_totals = {
            'total_elements': len(elements),
            'total_volume_net_m3': sum(g['volume_net_m3'] for g in materials.values()),
            'total_volume_with_wastage_m3': sum(g['volume_with_wastage_m3'] for g in materials.values()),
            'total_cement_kg': sum(g['cement_kg'] for g in materials.values()),
            'total_cement_tonnes': sum(g['cement_kg'] for g in materials.values()) / 1000,
            'total_coarse_agg_kg': sum(g['coarse_aggregate_kg'] for g in materials.values()),
            'total_fine_agg_kg': sum(g['fine_aggregate_kg'] for g in materials.values()),
            'total_water_liters': sum(g['water_liters'] for g in materials.values()),
            'total_plasticizer_liters': sum(g['plasticizer_liters'] for g in materials.values()),
            'total_material_cost_rm': sum(g['material_cost_rm'] for g in materials.values()),
            'total_labor_cost_rm': sum(g['labor_cost_rm'] for g in materials.values()),
            'total_equipment_cost_rm': sum(g['equipment_cost_rm'] for g in materials.values()),
            'grand_total_cost_rm': sum(g['total_cost_rm'] for g in materials.values())
        }

        self.disconnect()

        return {
            'materials_by_grade': materials,
            'logistics_by_location': logistics,
            'grand_totals': grand_totals,
            'elements': elements
        }


def print_concrete_report(report: Dict):
    """Print human-readable concrete report"""
    if 'error' in report:
        print(f"❌ Error: {report['error']}")
        return

    print("\n" + "=" * 80)
    print("CONCRETE REQUIREMENTS REPORT")
    print("=" * 80)

    # Materials by grade
    print("\n📦 MATERIALS BY CONCRETE GRADE")
    print("-" * 80)
    for grade_num, data in sorted(report['materials_by_grade'].items()):
        print(f"\n   Grade {grade_num} ({data['element_count']} elements, {data['volume_net_m3']:.2f} m³)")
        print(f"      Cement:           {data['cement_kg']:>10,.0f} kg ({data['cement_kg']/1000:.2f} tonnes)")
        print(f"      Coarse aggregate: {data['coarse_aggregate_kg']:>10,.0f} kg")
        print(f"      Fine aggregate:   {data['fine_aggregate_kg']:>10,.0f} kg")
        print(f"      Water:            {data['water_liters']:>10,.0f} liters")
        print(f"      Plasticizer:      {data['plasticizer_liters']:>10,.1f} liters")
        print(f"      Total cost:       RM {data['total_cost_rm']:>10,.2f}")

    # Grand totals
    gt = report['grand_totals']
    print("\n" + "-" * 80)
    print("GRAND TOTALS")
    print("-" * 80)
    print(f"   Total elements:       {gt['total_elements']}")
    print(f"   Total volume (net):   {gt['total_volume_net_m3']:,.2f} m³")
    print(f"   Total volume (+5%):   {gt['total_volume_with_wastage_m3']:,.2f} m³")
    print(f"   Total cement:         {gt['total_cement_kg']:,.0f} kg ({gt['total_cement_tonnes']:.2f} tonnes)")
    print(f"   Total aggregates:     {(gt['total_coarse_agg_kg'] + gt['total_fine_agg_kg']):,.0f} kg")
    print(f"   Total water:          {gt['total_water_liters']:,.0f} liters")
    print(f"   Material cost:        RM {gt['total_material_cost_rm']:,.2f}")
    print(f"   Labor cost:           RM {gt['total_labor_cost_rm']:,.2f}")
    print(f"   Equipment cost:       RM {gt['total_equipment_cost_rm']:,.2f}")
    print(f"   GRAND TOTAL COST:     RM {gt['grand_total_cost_rm']:,.2f}")

    # Logistics
    print("\n🚚 LOGISTICS PLANNING BY LOCATION")
    print("-" * 80)
    for location, data in sorted(report['logistics_by_location'].items()):
        print(f"\n   {location}")
        print(f"      Volume:       {data['total_volume_m3']:>8.2f} m³")
        print(f"      Elements:     {data['element_count']:>8} ({', '.join(f'{t}: {c}' for t, c in data['element_types'].items())})")
        print(f"      Trucks:       {data['trucks_needed']:>8} (7 m³ ready-mix trucks)")
        print(f"      Pour time:    {data['estimated_pour_hours']:>8.1f} hours")
        print(f"      Crew needed:  {data['crew_size']:>8} workers")

    print("\n" + "=" * 80 + "\n")


if __name__ == '__main__':
    # Example usage
    import sys

    if len(sys.argv) < 2:
        print("Usage: python concrete_calculator.py <database_path>")
        print("Example: python concrete_calculator.py /path/to/database.db")
        sys.exit(1)

    db_path = sys.argv[1]

    print("=" * 80)
    print("BONSAI CONCRETE CALCULATOR - KILLER FEATURE")
    print("=" * 80)
    print(f"Database: {db_path}")
    print("=" * 80)

    calculator = ConcreteCalculator(db_path)
    report = calculator.generate_full_report()

    print_concrete_report(report)

    print("✅ Concrete calculation complete!")
    print("📊 Ready for BOQ export")
