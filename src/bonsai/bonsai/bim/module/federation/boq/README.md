# Data Intelligence BOQ Module
## Comprehensive Bill of Quantities Export System

**Location**: `~/Projects/IfcOpenShell/src/bonsai/bonsai/bim/module/federation/dataintelligence/`

**Date**: 2025-11-05
**Status**: Production Ready
**Standards**: PWD Form 203A Malaysia, CIDB 2024, SMM2

---

## Overview

The Data Intelligence BOQ Module is a comprehensive quantity take-off and cost estimation system built on top of the Federation database. It transforms BIM data into professional Bill of Quantities reports with Malaysian construction industry pricing standards.

### Key Features

1. **Two-Phase Architecture**
   - **Phase 1**: Data extraction from federation database (run once)
   - **Phase 2**: Excel report generation (run unlimited times)
   - Benefit: Generate multiple report formats without recalculating

2. **Cost Breakdown**
   - Materials (with Malaysian market rates 2024)
   - Labor (crew composition, productivity, man-days)
   - Equipment/Plant Hire (CIDB machinery rates)
   - Provisional Sums (finishes, furniture, fittings)

3. **Industry Standards Compliance**
   - PWD Form 203A (Malaysia Public Works Department)
   - CIDB Malaysia 2024 pricing
   - SMM2 (Standard Method of Measurement)
   - BCISM Cost Book 2022-2024

4. **Airport Terminal Specifications**
   - Higher grade materials and finishes
   - Enhanced structural requirements
   - Fire protection and safety systems
   - BMS integration and controls

---

## Scripts Overview

### 1. `simple_qto_extract.py`
**Purpose**: Extract quantities from federation database

**Input**: SQLite database path
**Output**: `simple_qto` table in database

**Features**:
- Extracts LINEAR quantities (M): Ducts, Pipes, Beams, Columns, Cable Trays
- Extracts AREA quantities (M²): Slabs, Walls, Roofs, Coverings
- Extracts VOLUME quantities (M³): Spaces, Footings
- Extracts COUNT quantities (EA): Doors, Windows, Fixtures
- Applies Malaysian Ringgit (RM) unit costs

**Usage**:
```bash
python3 simple_qto_extract.py <database_path>
```

**Example**:
```bash
python3 simple_qto_extract.py ~/Documents/bonsai/DatabaseFiles/sample_extracted_v3.db
```

---

### 2. `simple_excel_export.py`
**Purpose**: Basic Excel export with two sheets

**Input**: Database with `simple_qto` table
**Output**: Excel file with summary and discipline breakdown

**Sheets Created**:
1. QTO Summary - All elements with quantities
2. Summary by Discipline - Rolled-up totals

**Usage**:
```bash
python3 simple_excel_export.py <database_path> [output_file]
```

---

### 3. `comprehensive_boq_export.py`
**Purpose**: Full professional BOQ with Material/Labor/Equipment breakdown

**Input**: Database with `simple_qto` table
**Output**: Multi-sheet Excel workbook with formulas and charts

**Sheets Created**:
1. **Cover Sheet** - Methodology, standards, references
2. **Executive Summary** - Grand totals with pie/bar charts
3. **Material Summary** - All material costs by discipline
4. **Labor Summary** - Crew allocation and man-days
5. **Equipment Summary** - Plant hire requirements
6. **Provisional Sums** - Finishes, furniture, signage, FIDS
7. **BOQ - [Discipline]** - Detailed BOQ sheets per discipline (8 sheets)

**Usage**:
```bash
python3 comprehensive_boq_export.py <database_path> [project_name]
```

**Example**:
```bash
python3 comprehensive_boq_export.py \
  ~/Documents/bonsai/DatabaseFiles/sample_extracted_v3.db \
  "Terminal 1 Expansion Project"
```

---

## Cover Sheet Explained

![BOQ Cover Sheet - Screenshot from comprehensive export showing methodology and standards](../Pictures/Screenshots/Screenshot%20from%202025-11-05%2023-21-36.png)

### Content Structure

**1. COST BREAKDOWN METHODOLOGY**

- **Material Costs**
  - Source: CIDB National Construction Cost Centre (N3C) 2024
  - Reference: BCISM Cost Book 2022-2024 (inflated +3%)
  - Includes: Delivery, wastage allowance (5-10% by material type)

- **Labor Costs**
  - Source: MBAM-CIDB Labour Wage Survey 2024
  - Basis: Basic wage + 30% (EPF 13%, SOCSO 2%, benefits 15%)
  - Productivity: CIDB productivity standards by trade
  - Crew Composition: Skilled workers + helpers as per trade standards

- **Equipment/Plant Hire**
  - Source: CIDB N3C Machinery Hire Rates 2024
  - Allocation: Based on work type and duration requirements
  - Rates: Per day (8 hours), operator cost included where stated

**2. PRICING STANDARDS & REFERENCES**

- BOQ Format: PWD Form 203A Malaysia
- Measurement: SMM2 (Standard Method of Measurement)
- Pricing Date: Q4 2024
- Currency: Malaysian Ringgit (RM)
- Validity: 60 days from date of issue

**3. EXCLUSIONS**

- GST/SST (apply as per prevailing tax law)
- Preliminary & General items (add 8-12%)
- Profit & attendance (add 10-15%)
- Escalation beyond 60 days
- Site-specific conditions not shown in drawings

---

## Executive Summary Explained

![BOQ Executive Summary - Showing Material/Labor/Equipment breakdown with charts](../Pictures/Screenshots/Screenshot%20from%202025-11-05%2023-21-04.png)

### Summary Table Structure - What the Screenshot Shows

The Executive Summary displays the **Grand Total: RM 12,455,589.25** broken down as follows:

**Cost Components (from screenshot)**:
- **Material Costs**: RM 9,704,734.90 (78% of total)
- **Labor Costs**: RM 617,607.77 (5% of total)
- **Equipment Costs**: RM 371,196.50 (3% of total)
- **Provisional Sums (Finishes & Fittings)**: RM 1,762,050.07 (14% of total)

**Discipline Breakdown (from screenshot)**:

| Discipline | Material (RM) | Labor (RM) | Equipment (RM) | TOTAL (RM) | % of Total |
|------------|---------------|------------|----------------|------------|------------|
| **ARC** (Architecture) | 4,848,097.17 | 279,941.36 | 140,829.26 | **5,268,867.80** | **42.3%** |
| **STR** (Structural) | 3,020,322.95 | 295,445.93 | 230,367.24 | **3,546,136.12** | **28.5%** |
| **FINISHES & FITTINGS** | - | - | - | **1,762,050.07** | **14.1%** |
| **ELEC** (Electrical) | 682,940.00 | 14,245.00 | 0.00 | **697,185.00** | **5.6%** |
| **SP** (Sanitary Plumbing) | 536,861.19 | 3,059.01 | 0.00 | **539,920.20** | **4.3%** |
| **CW** (Cold Water) | 387,396.45 | 3,379.90 | 0.00 | **390,776.35** | **3.1%** |
| **ACMV** (HVAC) | 165,116.85 | 11,912.66 | 0.00 | **177,029.51** | **1.4%** |
| **FP** (Fire Protection) | 63,515.12 | 9,503.65 | 0.00 | **73,018.76** | **0.6%** |
| **LPG** (Gas) | 485.19 | 120.25 | 0.00 | **605.44** | **0.0%** |
| **GRAND TOTAL** | **9,704,734.90** | **617,607.77** | **371,196.50** | **12,455,589.25** | **100%** |

**Key Insights from the Data**:

1. **Architecture (ARC)** dominates at 42.3%, driven by:
   - Large floor areas (slabs): 8,278 M² @ RM 285/M²
   - Premium finishes: 5,377 M² @ RM 185/M²
   - Windows (236 units) and Doors (135 units)

2. **Structural (STR)** at 28.5% reflects:
   - Heavy steel columns: 969 M @ RM 1,250/M
   - Structural beams: 304 M @ RM 680/M
   - RC slabs: 5,619 M²
   - Equipment usage (crane hire RM 230K)

3. **Provisional Sums** at 14.1% include airport-specific items:
   - FIDS screens, check-in counters, seating
   - Painting, acoustic panels, safety flooring
   - Not in BIM model but calculated from areas

4. **Material-Heavy Project**: 78% materials vs 5% labor
   - Reflects airport terminal high-spec materials
   - Labor productivity optimized
   - Equipment usage concentrated on structural work

### Charts Included (Visible in Screenshot)

**1. Pie Chart - Cost Breakdown by Discipline** (Top Right)
- Visual representation showing ARC (red) dominates ~42% of the pie
- STR (pink/beige) is the second largest at ~28%
- FINISHES & FITTINGS (green) at ~14%
- Other disciplines (ELEC, SP, CW, ACMV, FP, LPG) make up the remaining ~16%
- **Purpose**: Instantly shows which disciplines consume the most budget
- **Executive Insight**: Architecture and Structure represent 70% of total cost

**2. Bar Chart - Cost Components by Discipline** (Bottom Left)
- Stacked vertical bars showing three cost layers:
  - **Blue** = Material (RM) - dominant in all disciplines
  - **Red/Orange** = Labor (RM) - visible but small
  - **Green** = Equipment (RM) - only in ARC and STR
- **ARC** and **STR** bars are tallest, matching the pie chart
- **FINISHES & FITTINGS** shows combined total (no M/L/E split)
- **Purpose**: Compare cost structures across disciplines
- **Key Observation**: All disciplines are material-heavy (blue dominates), with structural work requiring equipment (green portions)

### Key Features

- **Live Formulas**: All values link to detail sheets
- **Auto-Update**: Change any unit rate → summary updates instantly
- **Professional Format**: Color-coded (Green=Material, Orange=Labor, Blue=Equipment, Red=Total)
- **Freeze Panes**: Headers stay visible when scrolling

---

## Malaysian Pricing Standards (2024)

### Airport Terminal Grade Specifications

The module uses enhanced specifications for airport terminals:

#### Structural Components

| Component | Rate (RM) | Specification |
|-----------|-----------|---------------|
| Steel I-Beam | 680.00/M | Grade 50, shop fabrication, fire protection |
| Steel Column | 1,250.00/M | Grade 50, UC section, fire protection, heavy duty |
| RC Slab | 285.00/M² | Grade 40 concrete, heavy rebar, 250mm thick |

#### HVAC Systems

| Component | Rate (RM) | Specification |
|-----------|-----------|---------------|
| Ductwork | 165.00/M | Galvanized steel G550, 0.6mm thickness |
| Duct Fittings | 380.00/EA | Elbows, tees, galvanized steel |
| FCU/AHU Terminal | 3,500.00/EA | BMS integrated, VFD controls |

#### Electrical Systems

| Component | Rate (RM) | Specification |
|-----------|-----------|---------------|
| LED Fixtures | 485.00/EA | 48W, dimming control, emergency backup |
| Power Outlets | 125.00/EA | Stainless steel, USB charging ports |
| Cable Tray | 78.00/M | Aluminum ladder type, 300mm |

#### Architectural Finishes

| Component | Rate (RM) | Specification |
|-----------|-----------|---------------|
| Floor Finishes | 185.00/M² | Granite tiles 600×600 / Metal suspended ceiling |
| Doors | 2,850.00/EA | Fire-rated, access control, automatic closer |
| Windows | 1,580.00/EA | 12mm double glazed, acoustic, powder coated |

---

## Provisional Sums Breakdown

Items not explicitly modeled in BIM but calculated from built-up areas:

### P1: Painting - Walls and Ceilings
- **Quantity**: 637 M² × 2 sides = 1,274 M²
- **Material Rate**: RM 8.50/M²
- **Labor Rate**: RM 12.00/M²
- **Total**: ~RM 26,080
- **Spec**: Dulux/Nippon 2 coats emulsion, primer, preparation

### P2: Check-in Counters & Service Desks
- **Quantity**: 15 units
- **Material Rate**: RM 12,500/EA
- **Labor Rate**: RM 2,500/EA
- **Total**: RM 225,000
- **Spec**: Solid surface, modular system, cable management, branding

### P3: Passenger Seating - Waiting Areas
- **Quantity**: 250 seats
- **Material Rate**: RM 580/EA
- **Labor Rate**: RM 45/EA
- **Total**: RM 156,250
- **Spec**: Airport beam seating, 3-4 seater units, steel frame

### P4: Wayfinding Signage System
- **Quantity**: 80 signs
- **Material Rate**: RM 650/EA
- **Labor Rate**: RM 120/EA
- **Total**: RM 61,600
- **Spec**: Illuminated, bilingual, airport pictograms

### P5: Flight Information Display Systems (FIDS)
- **Quantity**: 25 screens
- **Material Rate**: RM 8,500/EA
- **Labor Rate**: RM 1,200/EA
- **Total**: RM 242,500
- **Spec**: 55" LED, networked, real-time updates

### P6: Baggage Trolley Storage Racks
- **Quantity**: 12 racks
- **Material Rate**: RM 1,850/EA
- **Labor Rate**: RM 350/EA
- **Total**: RM 26,400
- **Spec**: Stainless steel, capacity 30 trolleys each

### P7: Retail Kiosk Fit-outs (Shell)
- **Quantity**: 8 kiosks
- **Material Rate**: RM 22,000/EA
- **Labor Rate**: RM 5,500/EA
- **Total**: RM 220,000
- **Spec**: Structural frame, services rough-in, ready for tenant

### P8: Rubber Safety Flooring - High Traffic
- **Quantity**: 2,080 M² (15% of floor area)
- **Material Rate**: RM 95/M²
- **Labor Rate**: RM 28/M²
- **Total**: RM 255,840
- **Spec**: Anti-slip, heavy duty, transition zones

### P9: Acoustic Ceiling Panels - Special Areas
- **Quantity**: 2,774 M² (20% of floor area)
- **Material Rate**: RM 135/M²
- **Labor Rate**: RM 42/M²
- **Total**: RM 491,058
- **Spec**: High absorption, Class A, fire-rated

### P10: Bollards & Barriers - Security
- **Quantity**: 45 units
- **Material Rate**: RM 1,250/EA
- **Labor Rate**: RM 280/EA
- **Total**: RM 68,850
- **Spec**: Fixed/removable, stainless steel, crash-rated

**TOTAL PROVISIONAL SUMS**: ~RM 1,760,538

---

## Labor Productivity Standards

Based on CIDB/MBAM standards with crew composition:

| Trade | Rate/Day (RM) | Crew Size | Productivity Example |
|-------|---------------|-----------|---------------------|
| HVAC Technician | 185 | 2 | 18 M/day ductwork |
| Pipefitter | 165 | 2 | 25 M/day pipes |
| Electrician | 175 | 2 | 30 M/day cable tray |
| Steel Erector | 195 | 4 | 8 M/day beams (with crane) |
| Concrete Gang | 145 | 6 | 35 M²/day slabs |
| Mason | 155 | 3 | 12 M²/day blockwork |

**Notes**:
- Rates include EPF (13%), SOCSO (2%), benefits (15%)
- Crew size accounts for safety requirements
- Productivity based on 8-hour working day
- Gang composition: skilled + semi-skilled + laborers

---

## Equipment Allocation Rules

Equipment is allocated based on work type and duration:

| Work Type | Equipment | Duration Factor | Rate/Day (RM) |
|-----------|-----------|----------------|---------------|
| Steel Beams | Mobile Crane 20T | 50% of work | 1,850 |
| Steel Columns | Mobile Crane 20T | 50% of work | 1,850 |
| RC Slabs | Concrete Pump | 30% of work | 950 |
| Ductwork | Scissor Lift 8m | 40% of work | 285 |
| Cable Trays | Scissor Lift 8m | 30% of work | 285 |

**Duration Factor**: Equipment days = Labor days × Duration factor

**Example**:
- Steel beam installation: 10 labor-days
- Crane usage: 10 × 0.5 = 5 crane-days
- Cost: 5 × RM 1,850 = RM 9,250

---

## Workflow Example

### Step 1: Extract QTO Data
```bash
cd ~/Projects/IfcOpenShell/src/bonsai/bonsai/bim/module/federation/dataintelligence/

PYTHONPATH=/home/red1/Projects/IfcOpenShell/src python3 simple_qto_extract.py \
  ~/Documents/bonsai/DatabaseFiles/sample_extracted_v3.db
```

**Output**:
```
================================================================================
SIMPLE QTO EXTRACTION
================================================================================

Creating simple_qto table...
Extracting linear elements...
Extracting area elements...
Extracting volume elements...
Extracting count elements...

================================================================================
EXTRACTION COMPLETE
================================================================================

Total QTO line items: 29

Sample data:
--------------------------------------------------------------------------------
ARC      IfcSlab                    AREA         91 elements      8,278.10 M2
STR      IfcSlab                    AREA        614 elements      5,619.41 M2
ARC      IfcCovering                AREA         82 elements      5,376.53 M2
...
```

### Step 2: Generate Simple Excel Report
```bash
PYTHONPATH=/home/red1/Projects/IfcOpenShell/src python3 simple_excel_export.py \
  ~/Documents/bonsai/DatabaseFiles/sample_extracted_v3.db \
  "Terminal1_SimpleQTO.xlsx"
```

### Step 3: Generate Comprehensive BOQ
```bash
PYTHONPATH=/home/red1/Projects/IfcOpenShell/src python3 comprehensive_boq_export.py \
  ~/Documents/bonsai/DatabaseFiles/sample_extracted_v3.db \
  "Terminal 1 Expansion Project"
```

**Output File**: `BOQ_Comprehensive_YYYYMMDD_HHMMSS.xlsx`

### Step 4: Open and Review
```bash
libreoffice BOQ_Comprehensive_20251105_222307.xlsx
```

---

## Excel Features

### Live Formula System

All costs are calculated using Excel formulas for instant updates:

**Material Cost** (in detail sheets):
```excel
=C5*E5    // Quantity × Material Rate
```

**Total Cost** (in detail sheets):
```excel
=F5+G5+H5    // Material + Labor + Equipment
```

**Discipline Total** (in summary):
```excel
='BOQ - ACMV'!I25    // Link to detail sheet total
```

**Grand Total**:
```excel
=SUM(E4:E11)    // Sum all discipline totals
```

### Editable Cells

Yellow-highlighted cells are editable:
- Material rates in detail sheets
- Labor rates in provisional sums
- Material rates in provisional sums

**Benefit**: Change any rate → all totals recalculate automatically

### Number Formatting

All monetary values use: `#,##0.00`
- Displays: `1,234,567.89`
- Includes thousands separators
- Always 2 decimal places

---

## Database Schema Reference

### `simple_qto` Table Structure

```sql
CREATE TABLE simple_qto (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discipline TEXT,              -- 'ACMV', 'ARC', 'STR', etc.
    ifc_class TEXT,               -- 'IfcDuct', 'IfcBeam', etc.
    measurement_type TEXT,        -- 'LINEAR', 'AREA', 'VOLUME', 'COUNT'
    element_count INTEGER,        -- Number of elements
    total_quantity REAL,          -- Sum of quantities
    uom TEXT,                     -- 'M', 'M2', 'M3', 'EA'
    avg_quantity REAL,            -- Average per element
    unit_cost_rm REAL,            -- Unit cost in RM
    total_cost_rm REAL            -- Total cost (qty × unit)
);
```

### Query Examples

**Get total cost by discipline**:
```sql
SELECT discipline, SUM(total_cost_rm) AS total_cost
FROM simple_qto
GROUP BY discipline
ORDER BY total_cost DESC;
```

**Get all HVAC elements**:
```sql
SELECT ifc_class, element_count, total_quantity, uom, total_cost_rm
FROM simple_qto
WHERE discipline = 'ACMV'
ORDER BY total_cost_rm DESC;
```

**Get grand total**:
```sql
SELECT SUM(total_cost_rm) AS grand_total
FROM simple_qto;
```

---

## Customization Guide

### Adding New Material Types

Edit `comprehensive_boq_export.py`:

```python
MATERIAL_COSTS = {
    # Add new entry
    'IfcYourNewType': {
        'rate': 250.00,
        'unit': 'M',
        'desc': 'Description of the element',
        'spec': 'Technical specification'
    },
    # ... existing entries
}
```

### Adding New Labor Trades

```python
LABOR_RATES = {
    'YOUR_TRADE': {
        'rate_per_day': 175.00,
        'productivity': {
            'IfcYourNewType': 20.0,  # units per day
        },
        'crew_size': 2,
        'trade': 'Trade Name (Skilled)'
    },
}
```

### Adding Equipment Allocation

```python
EQUIPMENT_ALLOCATION = {
    'IfcYourNewType': {
        'equipment': 'MOBILE_CRANE_20T',  # Key from EQUIPMENT_RATES
        'duration_factor': 0.4  # 40% of labor duration
    },
}
```

### Adjusting Provisional Sums

Edit the `prov_items` list in `create_provisional_sums()`:

```python
prov_items = [
    {
        'item': 'P11',
        'desc': 'Your New Item',
        'qty': 50,
        'uom': 'EA',
        'mat_rate': 1000.00,
        'labor_rate': 200.00,
        'spec': 'Detailed specification'
    },
    # ... existing items
]
```

---

## Troubleshooting

### Issue: `simple_qto` table not found

**Cause**: Database hasn't been processed with `simple_qto_extract.py`

**Solution**:
```bash
python3 simple_qto_extract.py <database_path>
```

### Issue: Low/Zero costs in BOQ

**Cause**: IFC classes not mapped in `MATERIAL_COSTS` dictionary

**Solution**:
1. Check which IFC classes exist in database
2. Add missing entries to `MATERIAL_COSTS`
3. Re-run comprehensive export

### Issue: No labor costs showing

**Cause**: IFC classes not mapped in `LABOR_RATES` productivity

**Solution**: Add productivity entries for relevant IFC classes

### Issue: Excel formulas show as text

**Cause**: Cell format set to Text before formula entry

**Solution**:
- Select cells
- Format → Number → Number
- Re-enter formulas

---

## Future Enhancements

### Planned Features

1. **Currency Support**
   - Multi-currency pricing tables
   - Exchange rate integration
   - Regional rate variants (Peninsular, Sabah, Sarawak)

2. **Schedule Integration**
   - Duration estimates from labor days
   - Critical path calculation
   - Resource loading curves

3. **Rate Database**
   - SQLite database of current rates
   - Historical rate tracking
   - Inflation adjustment calculator

4. **Report Variants**
   - PWD Form 203B (Alternative format)
   - JKR standard format
   - Custom templates

5. **Cost Optimization**
   - Value engineering suggestions
   - Material alternatives
   - Cost benchmarking

6. **Integration with Bonsai UI**
   - Direct export from Federation panel
   - Interactive cost preview
   - Element selection → filtered BOQ

---

## References

### Standards Documents

- **PWD Form 203A**: Public Works Department Malaysia - Bill of Quantities Format
- **CIDB Malaysia**: Construction Industry Development Board - Cost Standards
- **SMM2**: Standard Method of Measurement 2nd Edition
- **BCISM**: Building Cost Information Service Malaysia Cost Book 2022-2024
- **MBAM**: Master Builders Association Malaysia - Labour Wage Survey 2024

### Online Resources

- CIDB N3C Portal: https://n3c.cidb.gov.my
- CIDB Productivity Standards: https://www.cidb.gov.my
- PWD Malaysia: https://www.pwd.gov.my

### Related Documentation

- `BonsaiFederationDatabaseSpecification_v1.0.md` - Database schema details
- `Federation README.md` - Federation module overview
- `PROGRESSIVE_LOADER_README.md` - Loading system architecture

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2025-11-05 | Initial release with comprehensive BOQ export |
| | | - Airport terminal grade pricing |
| | | - Provisional sums for finishes |
| | | - Live Excel formulas |
| | | - Material/Labor/Equipment breakdown |

---

## Contact & Support

For issues, enhancements, or questions:
- Repository: https://github.com/red1oon/IfcOpenShell
- Branch: `feature/IFC4_DB`
- Module Path: `src/bonsai/bonsai/bim/module/federation/dataintelligence/`

---

*Documentation generated: 2025-11-05*
*Last updated: 2025-11-05*
