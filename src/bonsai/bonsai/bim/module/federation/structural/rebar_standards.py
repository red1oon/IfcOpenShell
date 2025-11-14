"""
Reinforcement Standards Database
Malaysian MS 1347:2020 (Code of Practice for Structural Use of Concrete)
British BS 8110, Eurocode 2 references
Used for automatic rebar generation in concrete structures
"""

from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class ConcreteGrade(Enum):
    """Common concrete grades in Malaysia"""
    GRADE_20 = 20  # Non-structural
    GRADE_25 = 25  # Light duty
    GRADE_30 = 30  # Residential
    GRADE_35 = 35  # Commercial
    GRADE_40 = 40  # Airport/Infrastructure (HEAVY DUTY)
    GRADE_45 = 45  # Special structures


class ExposureClass(Enum):
    """Environmental exposure classifications (MS 1347:2020)"""
    XC1 = "Dry or permanently wet"
    XC2 = "Wet, rarely dry"
    XC3 = "Moderate humidity"
    XC4 = "Cyclic wet and dry"
    XD1 = "Moderate humidity with chlorides"  # Airport de-icing salts
    XD2 = "Wet, rarely dry with chlorides"
    XD3 = "Cyclic wet/dry with chlorides"
    XS1 = "Exposed to airborne salt"  # Coastal airports
    XS2 = "Permanently submerged in seawater"
    XS3 = "Tidal/splash zones"


class BarDiameter(Enum):
    """Standard rebar diameters (mm) - MS 146 / BS 4449"""
    T6 = 6    # Mesh, distribution bars
    T8 = 8    # Distribution bars
    T10 = 10  # Light reinforcement
    T12 = 12  # Common for slabs
    T16 = 16  # Beams, heavy slabs
    T20 = 20  # Main beams, columns
    T25 = 25  # Heavy columns
    T32 = 32  # Large columns
    T40 = 40  # Special applications


@dataclass
class RebarProperties:
    """Physical properties of reinforcement bars"""
    diameter_mm: int
    area_mm2: float
    weight_kg_per_m: float

    @staticmethod
    def from_diameter(diameter: int) -> 'RebarProperties':
        """Calculate properties from diameter"""
        import math
        area = math.pi * (diameter / 2) ** 2
        # Steel density: 7850 kg/m³
        weight = area * 0.00000785  # kg/mm
        return RebarProperties(
            diameter_mm=diameter,
            area_mm2=area,
            weight_kg_per_m=weight
        )


@dataclass
class CoverRequirements:
    """Minimum concrete cover requirements (mm) - MS 1347:2020 Table 4.2"""
    exposure_class: str
    min_cover_mm: int

    @staticmethod
    def get_cover(exposure_class: ExposureClass, element_type: str) -> int:
        """
        Get minimum cover based on exposure and element type
        MS 1347:2020 requirements for durability
        """
        # Base covers for different exposure classes
        base_covers = {
            ExposureClass.XC1: 20,
            ExposureClass.XC2: 25,
            ExposureClass.XC3: 25,
            ExposureClass.XC4: 30,
            ExposureClass.XD1: 40,  # Airport with de-icing
            ExposureClass.XD2: 45,
            ExposureClass.XD3: 50,
            ExposureClass.XS1: 45,
            ExposureClass.XS2: 50,
            ExposureClass.XS3: 55,
        }

        cover = base_covers.get(exposure_class, 30)

        # Additional cover for formwork type
        if element_type in ['IfcSlab', 'IfcBeam']:
            cover += 5  # Formwork tolerance
        elif element_type == 'IfcColumn':
            cover += 5  # Column formwork

        return cover


@dataclass
class SlabReinforcementRules:
    """MS 1347:2020 Clause 9.3 - Slabs"""

    # Minimum reinforcement ratio (As,min / Ac)
    MIN_REINFORCEMENT_RATIO = 0.0013  # 0.13% for Grade 500 steel

    # Maximum bar spacing (mm)
    MAX_SPACING_MAIN = 300  # Main bars (MS 1347:2020)
    MAX_SPACING_DIST = 400  # Distribution bars
    MAX_SPACING_3H = True   # Not exceeding 3× slab depth

    # Edge strips (airport slabs - heavier loads)
    EDGE_STRIP_WIDTH_MULTIPLIER = 0.15  # 15% of span
    EDGE_REINFORCEMENT_MULTIPLIER = 1.5  # 50% more bars at edges

    @staticmethod
    def calculate_reinforcement(
        slab_thickness_mm: float,
        slab_length_mm: float,
        slab_width_mm: float,
        concrete_grade: ConcreteGrade,
        exposure: ExposureClass,
        is_airport: bool = False
    ) -> Dict:
        """
        Calculate slab reinforcement requirements
        Returns dict with main bars, distribution bars, spacing
        """
        # Effective depth (d = h - cover - Ø/2)
        cover = CoverRequirements.get_cover(exposure, 'IfcSlab')
        effective_depth = slab_thickness_mm - cover - 6  # Assume T12 bars (6mm radius)

        # Select main bar diameter based on slab thickness
        if slab_thickness_mm <= 150:
            main_bar_dia = BarDiameter.T10.value
            dist_bar_dia = BarDiameter.T8.value
        elif slab_thickness_mm <= 250:
            main_bar_dia = BarDiameter.T12.value
            dist_bar_dia = BarDiameter.T10.value
        else:  # Heavy duty (airport terminals)
            main_bar_dia = BarDiameter.T16.value
            dist_bar_dia = BarDiameter.T12.value

        # Airport multiplier for heavy loads
        load_factor = 1.3 if is_airport else 1.0

        # Calculate minimum steel area required
        slab_area_mm2 = slab_length_mm * slab_width_mm
        min_steel_area = SlabReinforcementRules.MIN_REINFORCEMENT_RATIO * slab_thickness_mm * 1000  # per meter width

        # Bar properties
        main_bar_props = RebarProperties.from_diameter(main_bar_dia)
        dist_bar_props = RebarProperties.from_diameter(dist_bar_dia)

        # Calculate spacing to meet minimum reinforcement
        main_spacing = min(
            int((main_bar_props.area_mm2 / min_steel_area) * 1000 * load_factor),
            SlabReinforcementRules.MAX_SPACING_MAIN,
            int(3 * slab_thickness_mm)  # 3h rule
        )

        dist_spacing = min(
            SlabReinforcementRules.MAX_SPACING_DIST,
            int(3 * slab_thickness_mm)
        )

        # Calculate number of bars
        num_main_bars = int(slab_width_mm / main_spacing) + 1
        num_dist_bars = int(slab_length_mm / dist_spacing) + 1

        # Total lengths
        total_main_length = num_main_bars * slab_length_mm / 1000  # meters
        total_dist_length = num_dist_bars * slab_width_mm / 1000

        # Total weight
        total_weight = (
            total_main_length * main_bar_props.weight_kg_per_m +
            total_dist_length * dist_bar_props.weight_kg_per_m
        )

        return {
            'main_bars': {
                'diameter': main_bar_dia,
                'spacing': main_spacing,
                'count': num_main_bars,
                'length_total_m': total_main_length,
                'direction': 'longitudinal'
            },
            'distribution_bars': {
                'diameter': dist_bar_dia,
                'spacing': dist_spacing,
                'count': num_dist_bars,
                'length_total_m': total_dist_length,
                'direction': 'transverse'
            },
            'cover_mm': cover,
            'effective_depth_mm': effective_depth,
            'total_weight_kg': total_weight,
            'reinforcement_ratio': (main_bar_props.area_mm2 * num_main_bars) / (slab_width_mm * slab_thickness_mm)
        }


@dataclass
class BeamReinforcementRules:
    """MS 1347:2020 Clause 9.2 - Beams"""

    # Minimum reinforcement ratio
    MIN_TENSION_REINFORCEMENT_RATIO = 0.0013  # Bottom bars
    MIN_COMPRESSION_REINFORCEMENT_RATIO = 0.002  # Top bars (airport standard)

    # Maximum bar spacing
    MAX_SPACING_TENSION = 250  # mm
    MAX_SPACING_COMPRESSION = 300  # mm

    # Stirrups/links (shear reinforcement)
    MAX_STIRRUP_SPACING = 0.75  # × effective depth
    MIN_STIRRUP_DIAMETER = 8  # mm (T8)

    @staticmethod
    def calculate_reinforcement(
        beam_width_mm: float,
        beam_height_mm: float,
        beam_length_mm: float,
        concrete_grade: ConcreteGrade,
        exposure: ExposureClass,
        is_airport: bool = False
    ) -> Dict:
        """
        Calculate beam reinforcement requirements
        Returns dict with top bars, bottom bars, stirrups
        """
        # Cover
        cover = CoverRequirements.get_cover(exposure, 'IfcBeam')
        effective_depth = beam_height_mm - cover - 10  # Assume T20 bars (10mm radius)

        # Select bar diameters based on beam size
        if beam_height_mm <= 400:
            main_bar_dia = BarDiameter.T16.value
        elif beam_height_mm <= 600:
            main_bar_dia = BarDiameter.T20.value
        else:
            main_bar_dia = BarDiameter.T25.value

        stirrup_dia = BarDiameter.T10.value if beam_height_mm >= 450 else BarDiameter.T8.value

        # Calculate minimum steel area
        min_tension_area = BeamReinforcementRules.MIN_TENSION_REINFORCEMENT_RATIO * beam_width_mm * effective_depth
        min_compression_area = BeamReinforcementRules.MIN_COMPRESSION_REINFORCEMENT_RATIO * beam_width_mm * effective_depth

        # Bar properties
        main_bar_props = RebarProperties.from_diameter(main_bar_dia)
        stirrup_props = RebarProperties.from_diameter(stirrup_dia)

        # Number of bars required (minimum 2 top, 2 bottom for airport beams)
        num_bottom_bars = max(2, int(min_tension_area / main_bar_props.area_mm2) + 1)
        num_top_bars = max(2, int(min_compression_area / main_bar_props.area_mm2) + 1)

        # Stirrup spacing
        stirrup_spacing = min(
            int(BeamReinforcementRules.MAX_STIRRUP_SPACING * effective_depth),
            300  # Maximum 300mm for airport standard
        )

        num_stirrups = int(beam_length_mm / stirrup_spacing) + 1

        # Lengths
        bottom_bar_length = beam_length_mm / 1000  # meters
        top_bar_length = beam_length_mm / 1000

        # Stirrup perimeter (U-shape for typical beam)
        stirrup_length_each = (2 * beam_height_mm + beam_width_mm + 200) / 1000  # +200mm for hooks
        total_stirrup_length = num_stirrups * stirrup_length_each

        # Total weight
        total_weight = (
            num_bottom_bars * bottom_bar_length * main_bar_props.weight_kg_per_m +
            num_top_bars * top_bar_length * main_bar_props.weight_kg_per_m +
            total_stirrup_length * stirrup_props.weight_kg_per_m
        )

        return {
            'bottom_bars': {
                'diameter': main_bar_dia,
                'count': num_bottom_bars,
                'length_each_m': bottom_bar_length,
                'length_total_m': num_bottom_bars * bottom_bar_length
            },
            'top_bars': {
                'diameter': main_bar_dia,
                'count': num_top_bars,
                'length_each_m': top_bar_length,
                'length_total_m': num_top_bars * top_bar_length
            },
            'stirrups': {
                'diameter': stirrup_dia,
                'spacing': stirrup_spacing,
                'count': num_stirrups,
                'length_each_m': stirrup_length_each,
                'length_total_m': total_stirrup_length
            },
            'cover_mm': cover,
            'effective_depth_mm': effective_depth,
            'total_weight_kg': total_weight
        }


@dataclass
class ColumnReinforcementRules:
    """MS 1347:2020 Clause 9.5 - Columns"""

    # Minimum reinforcement ratio
    MIN_REINFORCEMENT_RATIO = 0.008  # 0.8% of gross area (airport standard)
    MAX_REINFORCEMENT_RATIO = 0.04   # 4% maximum

    # Minimum number of bars
    MIN_BARS_RECTANGULAR = 4
    MIN_BARS_CIRCULAR = 6

    # Links/ties
    MIN_LINK_DIAMETER = 8  # mm (T8)
    MAX_LINK_SPACING = 12  # × smallest longitudinal bar diameter

    @staticmethod
    def calculate_reinforcement(
        column_width_mm: float,
        column_depth_mm: float,
        column_height_mm: float,
        concrete_grade: ConcreteGrade,
        exposure: ExposureClass,
        is_airport: bool = False
    ) -> Dict:
        """
        Calculate column reinforcement requirements
        Returns dict with longitudinal bars, links/ties
        """
        # Cover
        cover = CoverRequirements.get_cover(exposure, 'IfcColumn')

        # Select bar diameter based on column size
        column_area = column_width_mm * column_depth_mm
        if column_area <= 250 * 250:
            main_bar_dia = BarDiameter.T16.value
        elif column_area <= 400 * 400:
            main_bar_dia = BarDiameter.T20.value
        elif column_area <= 600 * 600:
            main_bar_dia = BarDiameter.T25.value
        else:
            main_bar_dia = BarDiameter.T32.value

        link_dia = BarDiameter.T10.value

        # Calculate minimum steel area
        min_steel_area = ColumnReinforcementRules.MIN_REINFORCEMENT_RATIO * column_area

        # Bar properties
        main_bar_props = RebarProperties.from_diameter(main_bar_dia)
        link_props = RebarProperties.from_diameter(link_dia)

        # Number of longitudinal bars (minimum 4 corners + extras for large columns)
        num_bars = max(
            ColumnReinforcementRules.MIN_BARS_RECTANGULAR,
            int(min_steel_area / main_bar_props.area_mm2)
        )

        # Ensure even number for symmetry
        if num_bars % 2 != 0:
            num_bars += 1

        # Link spacing
        link_spacing = min(
            int(ColumnReinforcementRules.MAX_LINK_SPACING * main_bar_dia),
            min(column_width_mm, column_depth_mm),  # Smallest dimension
            300  # Maximum 300mm
        )

        num_links = int(column_height_mm / link_spacing) + 1

        # Lengths
        bar_length_each = column_height_mm / 1000  # meters
        total_bar_length = num_bars * bar_length_each

        # Link perimeter (rectangular)
        link_length_each = (2 * column_width_mm + 2 * column_depth_mm + 300) / 1000  # +300mm for hooks
        total_link_length = num_links * link_length_each

        # Total weight
        total_weight = (
            total_bar_length * main_bar_props.weight_kg_per_m +
            total_link_length * link_props.weight_kg_per_m
        )

        return {
            'longitudinal_bars': {
                'diameter': main_bar_dia,
                'count': num_bars,
                'length_each_m': bar_length_each,
                'length_total_m': total_bar_length,
                'arrangement': f'{num_bars} bars equally spaced'
            },
            'links': {
                'diameter': link_dia,
                'spacing': link_spacing,
                'count': num_links,
                'length_each_m': link_length_each,
                'length_total_m': total_link_length
            },
            'cover_mm': cover,
            'total_weight_kg': total_weight,
            'reinforcement_ratio': (num_bars * main_bar_props.area_mm2) / column_area
        }


# ============================================================================
# PRICING DATABASE (Malaysian Market 2024)
# ============================================================================

@dataclass
class RebarPricing:
    """
    Malaysian rebar pricing - November 2024
    Source: Local suppliers (YTL, Ann Joo, Megasteel)
    """

    # Prices in RM per tonne (delivered to site)
    PRICE_PER_TONNE = {
        'T6_T10': 3200,   # Small diameter bars (T6-T10)
        'T12_T16': 3100,  # Medium diameter bars (T12-T16)
        'T20_T25': 3050,  # Large diameter bars (T20-T25)
        'T32_T40': 3000,  # Extra large diameter bars (T32-T40)
    }

    # Labor rates for rebar work (RM per tonne installed)
    LABOR_CUTTING_BENDING = 280  # Bar preparation
    LABOR_FIXING = 450           # Installation & tying

    # Wastage factor
    WASTAGE_FACTOR = 1.07  # 7% wastage (cutting, overlaps)

    @staticmethod
    def get_price_per_kg(diameter: int) -> float:
        """Get price in RM per kg based on diameter"""
        if diameter <= 10:
            return RebarPricing.PRICE_PER_TONNE['T6_T10'] / 1000
        elif diameter <= 16:
            return RebarPricing.PRICE_PER_TONNE['T12_T16'] / 1000
        elif diameter <= 25:
            return RebarPricing.PRICE_PER_TONNE['T20_T25'] / 1000
        else:
            return RebarPricing.PRICE_PER_TONNE['T32_T40'] / 1000

    @staticmethod
    def calculate_total_cost(weight_kg: float, diameter: int) -> Dict[str, float]:
        """Calculate material + labor cost for rebar"""
        weight_with_wastage = weight_kg * RebarPricing.WASTAGE_FACTOR
        weight_tonnes = weight_with_wastage / 1000

        material_cost = weight_with_wastage * RebarPricing.get_price_per_kg(diameter)
        labor_cost = weight_tonnes * (RebarPricing.LABOR_CUTTING_BENDING + RebarPricing.LABOR_FIXING)

        return {
            'weight_net_kg': weight_kg,
            'weight_with_wastage_kg': weight_with_wastage,
            'material_cost_rm': material_cost,
            'labor_cost_rm': labor_cost,
            'total_cost_rm': material_cost + labor_cost,
            'unit_rate_rm_per_kg': (material_cost + labor_cost) / weight_kg
        }


if __name__ == '__main__':
    # Example usage
    print("=" * 80)
    print("REBAR STANDARDS DATABASE - QUICK TEST")
    print("=" * 80)

    # Test slab reinforcement
    print("\n1. SLAB REINFORCEMENT (250mm thick, 10m × 8m, Airport Terminal)")
    slab_rebar = SlabReinforcementRules.calculate_reinforcement(
        slab_thickness_mm=250,
        slab_length_mm=10000,
        slab_width_mm=8000,
        concrete_grade=ConcreteGrade.GRADE_40,
        exposure=ExposureClass.XD1,  # Airport with de-icing
        is_airport=True
    )
    print(f"   Main bars: T{slab_rebar['main_bars']['diameter']} @ {slab_rebar['main_bars']['spacing']}mm c/c")
    print(f"   Count: {slab_rebar['main_bars']['count']} bars × {slab_rebar['main_bars']['length_total_m']:.1f}m")
    print(f"   Distribution: T{slab_rebar['distribution_bars']['diameter']} @ {slab_rebar['distribution_bars']['spacing']}mm c/c")
    print(f"   Total weight: {slab_rebar['total_weight_kg']:.1f} kg")

    cost = RebarPricing.calculate_total_cost(slab_rebar['total_weight_kg'], slab_rebar['main_bars']['diameter'])
    print(f"   Total cost: RM {cost['total_cost_rm']:,.2f}")

    # Test beam reinforcement
    print("\n2. BEAM REINFORCEMENT (300mm × 600mm × 8m, Airport Terminal)")
    beam_rebar = BeamReinforcementRules.calculate_reinforcement(
        beam_width_mm=300,
        beam_height_mm=600,
        beam_length_mm=8000,
        concrete_grade=ConcreteGrade.GRADE_40,
        exposure=ExposureClass.XD1,
        is_airport=True
    )
    print(f"   Top bars: {beam_rebar['top_bars']['count']} × T{beam_rebar['top_bars']['diameter']}")
    print(f"   Bottom bars: {beam_rebar['bottom_bars']['count']} × T{beam_rebar['bottom_bars']['diameter']}")
    print(f"   Stirrups: T{beam_rebar['stirrups']['diameter']} @ {beam_rebar['stirrups']['spacing']}mm c/c")
    print(f"   Total weight: {beam_rebar['total_weight_kg']:.1f} kg")

    cost = RebarPricing.calculate_total_cost(beam_rebar['total_weight_kg'], beam_rebar['bottom_bars']['diameter'])
    print(f"   Total cost: RM {cost['total_cost_rm']:,.2f}")

    # Test column reinforcement
    print("\n3. COLUMN REINFORCEMENT (400mm × 400mm × 3.5m, Airport Terminal)")
    column_rebar = ColumnReinforcementRules.calculate_reinforcement(
        column_width_mm=400,
        column_depth_mm=400,
        column_height_mm=3500,
        concrete_grade=ConcreteGrade.GRADE_40,
        exposure=ExposureClass.XD1,
        is_airport=True
    )
    print(f"   Longitudinal: {column_rebar['longitudinal_bars']['count']} × T{column_rebar['longitudinal_bars']['diameter']}")
    print(f"   Links: T{column_rebar['links']['diameter']} @ {column_rebar['links']['spacing']}mm c/c")
    print(f"   Total weight: {column_rebar['total_weight_kg']:.1f} kg")
    print(f"   Reinforcement ratio: {column_rebar['reinforcement_ratio']:.3%}")

    cost = RebarPricing.calculate_total_cost(column_rebar['total_weight_kg'], column_rebar['longitudinal_bars']['diameter'])
    print(f"   Total cost: RM {cost['total_cost_rm']:,.2f}")

    print("\n" + "=" * 80)
    print("✅ Standards module ready for integration")
    print("=" * 80)
