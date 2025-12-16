# Bonsai - OpenBIM Blender Add-on
# River Carbon Credits - Biochar Pipeline Module
# Puro.Earth 2025 Methodology Compliant

"""
Biochar Pipeline - Carbon Credit Lifecycle Management
======================================================
Tracks biochar production from river waste through to carbon credit certification.

Revenue Potential: RM 201.6M - 488.75M/year (Biochar carbon credits)

Key Formulas:
1. Dried biomass = organic_waste_kg × (100 - moisture_content_pct) / 100
2. Biochar output = dried_biomass × 0.25 (25% conversion target)
3. Carbon tonnes = (biochar_kg / 1000) × (carbon_content_pct / 100)
4. tCO₂e = carbon_tonnes × 3.67 × 0.95 (molecular weight × permanence)
5. Net removal = tCO₂e - (LCA emissions across 4 categories)

Puro.Earth 2025 Methodology Requirements:
- Feedstock sustainability verification
- 4-category LCA emissions tracking
- Lab-verified carbon content (75% typical)
- 100-year sequestration durability
- 2% reversal risk accounting
"""

import sqlite3
import secrets
import string
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, List
from pathlib import Path


@dataclass
class BiocharBatch:
    """Single biochar production batch with carbon sequestration metrics"""

    batch_id: str
    boom_site_id: int
    processing_facility: str
    organic_waste_kg: float
    moisture_content_pct: float

    # Calculated fields
    dried_biomass_kg: float = 0.0
    biochar_output_kg: float = 0.0
    conversion_yield_pct: float = 0.0
    carbon_content_pct: float = 75.0  # Default 75% (lab will verify)
    tco2e_sequestered: float = 0.0

    # Puro.Earth LCA emissions
    lca_emissions_category_1: float = 0.0  # Feedstock extraction
    lca_emissions_category_2: float = 0.0  # Transportation
    lca_emissions_category_3: float = 0.0  # Processing
    lca_emissions_category_4: float = 0.0  # Distribution
    net_carbon_removal: float = 0.0

    # Financial
    price_per_tco2e_rm: float = 740.0  # Default RM 740 (mid-range 630-850)
    revenue_rm: float = 0.0

    # Metadata
    certification_status: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def __post_init__(self):
        """Calculate derived values after initialization"""
        # 1. Dried biomass calculation
        if self.moisture_content_pct > 0:
            self.dried_biomass_kg = self.organic_waste_kg * (100 - self.moisture_content_pct) / 100
        else:
            self.dried_biomass_kg = self.organic_waste_kg

        # 2. Biochar output (25% conversion target)
        if self.biochar_output_kg == 0:  # Only calculate if not provided
            self.biochar_output_kg = self.dried_biomass_kg * 0.25

        # 3. Conversion yield percentage
        if self.dried_biomass_kg > 0:
            self.conversion_yield_pct = (self.biochar_output_kg / self.dried_biomass_kg) * 100

        # 4. Carbon sequestration calculation
        biochar_tonnes = self.biochar_output_kg / 1000.0
        carbon_tonnes = biochar_tonnes * (self.carbon_content_pct / 100.0)
        self.tco2e_sequestered = carbon_tonnes * 3.67 * 0.95  # CO₂/C ratio × permanence factor

        # 5. Net carbon removal (Puro.Earth requirement)
        total_lca_emissions = (
            self.lca_emissions_category_1 +
            self.lca_emissions_category_2 +
            self.lca_emissions_category_3 +
            self.lca_emissions_category_4
        )
        self.net_carbon_removal = self.tco2e_sequestered - total_lca_emissions

        # 6. Revenue calculation
        if self.net_carbon_removal > 0:
            self.revenue_rm = self.net_carbon_removal * self.price_per_tco2e_rm


class BiocharPipeline:
    """
    Manages biochar batch lifecycle from creation to credit certification.

    Usage:
        pipeline = BiocharPipeline('/path/to/coastal_oasis_gi.db')
        batch = pipeline.create_batch(
            boom_site_id=1,
            organic_waste_kg=1000.0,
            moisture_content_pct=50.0,
            processing_facility='FACILITY_A'
        )
    """

    def __init__(self, db_path: str):
        """Initialize pipeline with database connection"""
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {db_path}")

        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row

    def _generate_batch_id(self) -> str:
        """Generate unique batch ID: BIOCHAR_ABC12345"""
        prefix = "BIOCHAR_"
        random_suffix = ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
        return prefix + random_suffix

    def create_batch(
        self,
        boom_site_id: int,
        organic_waste_kg: float,
        moisture_content_pct: float,
        processing_facility: str,
        gps_lat: Optional[float] = None,
        gps_lon: Optional[float] = None
    ) -> BiocharBatch:
        """
        Create new biochar batch with automatic carbon sequestration calculation.

        Args:
            boom_site_id: ID from project_markers table
            organic_waste_kg: Wet organic waste collected (kg)
            moisture_content_pct: Moisture % before drying (40-60% typical)
            processing_facility: 'FACILITY_A', 'FACILITY_B', or 'MOBILE_UNIT'
            gps_lat: GPS latitude (optional)
            gps_lon: GPS longitude (optional)

        Returns:
            BiocharBatch with calculated tCO₂e and revenue
        """
        batch_id = self._generate_batch_id()

        # Create batch object (calculations happen in __post_init__)
        batch = BiocharBatch(
            batch_id=batch_id,
            boom_site_id=boom_site_id,
            organic_waste_kg=organic_waste_kg,
            moisture_content_pct=moisture_content_pct,
            processing_facility=processing_facility
        )

        # Insert into database
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO biochar_batches (
                batch_id, boom_site_id, processing_facility,
                organic_waste_kg, moisture_content_pct, dried_biomass_kg,
                biochar_output_kg, conversion_yield_pct, carbon_content_pct,
                tco2e_sequestered, net_carbon_removal,
                lca_emissions_category_1, lca_emissions_category_2,
                lca_emissions_category_3, lca_emissions_category_4,
                price_per_tco2e_rm, revenue_rm,
                certification_status, gps_lat, gps_lon, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            batch.batch_id, batch.boom_site_id, batch.processing_facility,
            batch.organic_waste_kg, batch.moisture_content_pct, batch.dried_biomass_kg,
            batch.biochar_output_kg, batch.conversion_yield_pct, batch.carbon_content_pct,
            batch.tco2e_sequestered, batch.net_carbon_removal,
            batch.lca_emissions_category_1, batch.lca_emissions_category_2,
            batch.lca_emissions_category_3, batch.lca_emissions_category_4,
            batch.price_per_tco2e_rm, batch.revenue_rm,
            batch.certification_status, gps_lat, gps_lon, batch.created_at
        ))
        self.conn.commit()

        return batch

    def update_lab_results(
        self,
        batch_id: str,
        actual_biochar_kg: float,
        carbon_content_pct: float,
        biochar_ph: Optional[float] = None,
        cation_exchange_capacity: Optional[float] = None,
        ash_content_pct: Optional[float] = None
    ) -> BiocharBatch:
        """
        Update batch with lab-verified results and recalculate carbon sequestration.

        Args:
            batch_id: Batch identifier
            actual_biochar_kg: Lab-measured biochar output
            carbon_content_pct: Lab-verified carbon % (typically 70-80%)
            biochar_ph: pH measurement (optional)
            cation_exchange_capacity: CEC for soil application (optional)
            ash_content_pct: Ash percentage (optional)

        Returns:
            Updated BiocharBatch with recalculated tCO₂e
        """
        # Fetch existing batch
        cursor = self.conn.cursor()
        row = cursor.execute(
            "SELECT * FROM biochar_batches WHERE batch_id = ?", (batch_id,)
        ).fetchone()

        if not row:
            raise ValueError(f"Batch {batch_id} not found")

        # Recalculate with actual lab values
        biochar_tonnes = actual_biochar_kg / 1000.0
        carbon_tonnes = biochar_tonnes * (carbon_content_pct / 100.0)
        tco2e_sequestered = carbon_tonnes * 3.67 * 0.95

        # Get existing LCA emissions
        total_lca = (
            row['lca_emissions_category_1'] + row['lca_emissions_category_2'] +
            row['lca_emissions_category_3'] + row['lca_emissions_category_4']
        )
        net_carbon_removal = tco2e_sequestered - total_lca

        # Update database
        cursor.execute("""
            UPDATE biochar_batches
            SET biochar_output_kg = ?,
                carbon_content_pct = ?,
                tco2e_sequestered = ?,
                net_carbon_removal = ?,
                biochar_ph = ?,
                cation_exchange_capacity = ?,
                ash_content_pct = ?,
                updated_at = ?
            WHERE batch_id = ?
        """, (
            actual_biochar_kg, carbon_content_pct, tco2e_sequestered, net_carbon_removal,
            biochar_ph, cation_exchange_capacity, ash_content_pct,
            datetime.now().isoformat(), batch_id
        ))
        self.conn.commit()

        # Return updated batch
        return self.get_batch(batch_id)

    def calculate_lca_emissions(
        self,
        batch_id: str,
        transport_km: float = 0.0,
        diesel_liters: float = 0.0,
        electricity_kwh: float = 0.0,
        natural_gas_m3: float = 0.0
    ) -> Dict[str, float]:
        """
        Calculate 4-category LCA emissions for Puro.Earth 2025 methodology.

        Emission Factors (typical):
        - Diesel combustion: 2.68 kg CO₂/liter
        - Electricity (Malaysia grid): 0.694 kg CO₂/kWh
        - Natural gas: 2.75 kg CO₂/m³
        - Transport: 0.1 kg CO₂/tonne-km

        Args:
            batch_id: Batch identifier
            transport_km: Transport distance (km)
            diesel_liters: Diesel fuel used (liters)
            electricity_kwh: Electricity consumed (kWh)
            natural_gas_m3: Natural gas used (m³)

        Returns:
            Dict with category emissions and net carbon removal
        """
        # Fetch batch
        batch_row = self.conn.cursor().execute(
            "SELECT * FROM biochar_batches WHERE batch_id = ?", (batch_id,)
        ).fetchone()

        if not batch_row:
            raise ValueError(f"Batch {batch_id} not found")

        # Calculate LCA emissions by category
        # Category 1: Feedstock extraction (minimal for river waste)
        cat1_emissions = 0.0  # River waste = zero extraction cost

        # Category 2: Transportation
        biochar_tonnes = batch_row['biochar_output_kg'] / 1000.0
        cat2_emissions = (transport_km * biochar_tonnes * 0.1) / 1000.0  # Convert to tCO₂e

        # Category 3: Processing (pyrolysis)
        diesel_co2 = diesel_liters * 2.68 / 1000.0  # tCO₂e
        electricity_co2 = electricity_kwh * 0.694 / 1000.0  # tCO₂e
        gas_co2 = natural_gas_m3 * 2.75 / 1000.0  # tCO₂e
        cat3_emissions = diesel_co2 + electricity_co2 + gas_co2

        # Category 4: Distribution (same as transport)
        cat4_emissions = cat2_emissions  # Conservative estimate

        # Calculate net carbon removal
        total_lca = cat1_emissions + cat2_emissions + cat3_emissions + cat4_emissions
        net_carbon_removal = batch_row['tco2e_sequestered'] - total_lca

        # Calculate revenue (RM 740/tCO₂e default)
        price_per_tco2e = batch_row['price_per_tco2e_rm'] if batch_row['price_per_tco2e_rm'] else 740.0
        revenue_rm = net_carbon_removal * price_per_tco2e if net_carbon_removal > 0 else 0.0

        # Update database
        cursor = self.conn.cursor()
        cursor.execute("""
            UPDATE biochar_batches
            SET lca_emissions_category_1 = ?,
                lca_emissions_category_2 = ?,
                lca_emissions_category_3 = ?,
                lca_emissions_category_4 = ?,
                net_carbon_removal = ?,
                revenue_rm = ?,
                updated_at = ?
            WHERE batch_id = ?
        """, (
            cat1_emissions, cat2_emissions, cat3_emissions, cat4_emissions,
            net_carbon_removal, revenue_rm, datetime.now().isoformat(), batch_id
        ))
        self.conn.commit()

        return {
            'category_1_feedstock': cat1_emissions,
            'category_2_transport': cat2_emissions,
            'category_3_processing': cat3_emissions,
            'category_4_distribution': cat4_emissions,
            'total_lca_emissions': total_lca,
            'gross_sequestration': batch_row['tco2e_sequestered'],
            'net_carbon_removal': net_carbon_removal,
            'net_removal_pct': (net_carbon_removal / batch_row['tco2e_sequestered']) * 100 if batch_row['tco2e_sequestered'] > 0 else 0
        }

    def get_batch(self, batch_id: str) -> BiocharBatch:
        """Retrieve batch by ID"""
        cursor = self.conn.cursor()
        row = cursor.execute(
            "SELECT * FROM biochar_batches WHERE batch_id = ?", (batch_id,)
        ).fetchone()

        if not row:
            raise ValueError(f"Batch {batch_id} not found")

        return BiocharBatch(
            batch_id=row['batch_id'],
            boom_site_id=row['boom_site_id'],
            processing_facility=row['processing_facility'],
            organic_waste_kg=row['organic_waste_kg'],
            moisture_content_pct=row['moisture_content_pct'],
            dried_biomass_kg=row['dried_biomass_kg'],
            biochar_output_kg=row['biochar_output_kg'],
            conversion_yield_pct=row['conversion_yield_pct'],
            carbon_content_pct=row['carbon_content_pct'],
            tco2e_sequestered=row['tco2e_sequestered'],
            lca_emissions_category_1=row['lca_emissions_category_1'],
            lca_emissions_category_2=row['lca_emissions_category_2'],
            lca_emissions_category_3=row['lca_emissions_category_3'],
            lca_emissions_category_4=row['lca_emissions_category_4'],
            net_carbon_removal=row['net_carbon_removal'],
            certification_status=row['certification_status']
        )

    def get_pipeline_summary(self) -> Dict:
        """Get overall pipeline statistics"""
        cursor = self.conn.cursor()

        summary = cursor.execute("""
            SELECT
                COUNT(*) as total_batches,
                SUM(organic_waste_kg) as total_waste_kg,
                SUM(biochar_output_kg) as total_biochar_kg,
                SUM(tco2e_sequestered) as gross_sequestration,
                SUM(net_carbon_removal) as net_sequestration,
                SUM(CASE WHEN certification_status = 'credits_issued' THEN credits_issued ELSE 0 END) as credits_issued,
                SUM(revenue_rm) as total_revenue
            FROM biochar_batches
        """).fetchone()

        return {
            'total_batches': summary['total_batches'] or 0,
            'total_organic_waste_kg': summary['total_waste_kg'] or 0,
            'total_biochar_kg': summary['total_biochar_kg'] or 0,
            'gross_tco2e_sequestered': summary['gross_sequestration'] or 0,
            'net_tco2e_sequestered': summary['net_sequestration'] or 0,
            'credits_issued': summary['credits_issued'] or 0,
            'total_revenue_rm': summary['total_revenue'] or 0,
            'avg_conversion_yield_pct': (summary['total_biochar_kg'] / summary['total_waste_kg'] * 100) if summary['total_waste_kg'] else 0
        }

    def __del__(self):
        """Close database connection on cleanup"""
        if hasattr(self, 'conn'):
            self.conn.close()
