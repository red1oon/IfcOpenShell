# 📊 BOQ System User Guide for Accountants & Quantity Surveyors

**Document Version:** 1.0
**Date:** 09 November 2024
**Audience:** Accountants, Quantity Surveyors, Cost Estimators, Project Managers

---

## 🎯 Executive Summary

This Bill of Quantities (BOQ) system automatically generates comprehensive cost estimates from 3D Building Information Models (BIM). It extracts building element quantities and applies Malaysian construction industry pricing standards to produce professional Excel reports ready for tender submissions.

**Key Benefits:**
- **Time Savings:** Reduces BOQ preparation from days to minutes
- **Accuracy:** Eliminates manual quantity take-off errors
- **Compliance:** Follows PWD Form 203A & SMM2 Malaysian standards
- **Transparency:** Full cost breakdown (Materials, Labor, Equipment)
- **Professional:** Publication-ready Excel reports with charts

---

## 📋 Table of Contents

1. [Understanding the BOQ System](#1-understanding-the-boq-system)
2. [Database Schema Overview](#2-database-schema-overview)
3. [Excel Report Structure](#3-excel-report-structure)
4. [Cost Calculation Methodology](#4-cost-calculation-methodology)
5. [How to Use the Reports](#5-how-to-use-the-reports)
6. [Adjusting Rates & Markups](#6-adjusting-rates--markups)
7. [Common Accounting Tasks](#7-common-accounting-tasks)
8. [Limitations & Exclusions](#8-limitations--exclusions)

---

## 1. Understanding the BOQ System

### What is BIM-Based BOQ?

Traditional quantity surveying requires manual measurement from 2D drawings. This system uses **3D Building Information Models (BIM)** which already contain:
- Every structural element (beams, columns, slabs)
- All MEP systems (ducts, pipes, cables)
- Architectural components (walls, doors, windows)
- Exact dimensions and material specifications

The system **extracts** this data, **calculates** costs, and **generates** Excel reports automatically.

### The 3-Step Process

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│  1. EXTRACTION  │ ───> │  2. CALCULATION  │ ───> │  3. REPORTING   │
│                 │      │                  │      │                 │
│ BIM Model (.ifc)│      │ Material rates   │      │ Excel BOQ       │
│ → Database      │      │ Labor costs      │      │ with charts     │
│                 │      │ Equipment hire   │      │                 │
└─────────────────┘      └──────────────────┘      └─────────────────┘
```

**Step 1 - Extraction:** Read IFC files, store quantities in SQLite database
**Step 2 - Calculation:** Apply Malaysian construction pricing rates
**Step 3 - Reporting:** Generate formatted Excel workbook with summaries

---

## 2. Database Schema Overview

The system uses a **SQLite database** (`.db` file) to store extracted quantities. Here's what accountants need to know:

### Main Table: `simple_qto` (Quantity Take-Off)

This is the **core table** containing all measured quantities from the BIM model.

#### Table Structure:

| Column Name       | Data Type | Description                                  | Example         |
|-------------------|-----------|----------------------------------------------|-----------------|
| `id`              | INTEGER   | Unique record identifier                     | 1, 2, 3...      |
| `discipline`      | TEXT      | Construction trade/discipline                | "STR", "ACMV"   |
| `ifc_class`       | TEXT      | BIM element type (IFC schema)                | "IfcBeam"       |
| `total_quantity`  | REAL      | Measured quantity (sum of all instances)     | 1250.5          |
| `uom`             | TEXT      | Unit of measurement                          | "M", "M2", "EA" |
| `element_count`   | INTEGER   | Number of individual elements                | 45              |

#### Example Records:

```sql
SELECT * FROM simple_qto WHERE discipline = 'STR' LIMIT 3;
```

| id  | discipline | ifc_class  | total_quantity | uom | element_count |
|-----|------------|------------|----------------|-----|---------------|
| 1   | STR        | IfcBeam    | 1250.50        | M   | 45            |
| 2   | STR        | IfcColumn  | 380.25         | M   | 28            |
| 3   | STR        | IfcSlab    | 4580.00        | M2  | 12            |

**Interpretation:**
- Row 1: 45 steel beams totaling 1,250.5 meters
- Row 2: 28 columns totaling 380.25 meters
- Row 3: 12 slab sections totaling 4,580 m²

### Discipline Codes

| Code  | Full Name                     | Typical Elements                  |
|-------|-------------------------------|-----------------------------------|
| STR   | Structural                    | Beams, Columns, Slabs             |
| ARC   | Architectural                 | Walls, Doors, Windows, Roofs      |
| ACMV  | Air Conditioning & Mech. Vent | Ducts, Air Handlers, FCUs         |
| ELEC  | Electrical                    | Cable Trays, Light Fixtures       |
| SP    | Sanitary Plumbing             | Pipes, Drains, Sanitary Fixtures  |
| FP    | Fire Protection               | Sprinkler Pipes, Fire Extinguishers|
| LPG   | Liquefied Petroleum Gas       | LPG Piping, Storage               |
| CW    | Civil Works                   | Earthworks, Paving                |

### Unit of Measurement (UOM)

| UOM | Description           | Used For                              |
|-----|-----------------------|---------------------------------------|
| M   | Meters (linear)       | Beams, columns, pipes, ducts, cables  |
| M2  | Square meters         | Slabs, walls, roofs, finishes         |
| M3  | Cubic meters          | Earthworks, concrete volume           |
| EA  | Each (pieces)         | Doors, windows, fixtures, equipment   |

### Supporting Tables

#### `ifc_labels` (Friendly Names)
Makes technical IFC codes readable:

| ifc_class     | friendly_label          | description                              |
|---------------|-------------------------|------------------------------------------|
| IfcBeam       | Structural Steel Beam   | I-beam or universal beam for support     |
| IfcDuct       | HVAC Ductwork          | Galvanized steel air distribution duct   |
| IfcDoor       | Door Assembly          | Complete door set with frame & hardware  |

#### `discipline_rates` (Professional Service Rates) **⭐ IMPORTANT FOR COST UPDATES**
Stores hourly billing rates for design professionals by discipline and skill level.

**Table Structure:**
| Column         | Type      | Description                                   | Example                    |
|----------------|-----------|-----------------------------------------------|----------------------------|
| rate_id        | INTEGER   | Unique rate identifier                        | 1, 2, 3...                 |
| discipline     | TEXT      | Design discipline                             | ARCHITECTURE, STRUCTURE, MEP|
| skill_level    | TEXT      | Professional experience level                 | senior, intermediate, junior|
| hourly_rate    | REAL      | Billing rate in RM/hour or USD/hour           | 165.0, 95.0                |
| region         | TEXT      | Geographic region for rate applicability      | US, MY, SG                 |
| effective_date | TIMESTAMP | Date rate became effective                    | 2025-11-06 00:18:05        |
| notes          | TEXT      | Additional details about the rate             | Principal architect, 15+ years|

**Sample Data:**
```sql
SELECT * FROM discipline_rates LIMIT 3;
```
| rate_id | discipline    | skill_level  | hourly_rate | region | notes                        |
|---------|---------------|--------------|-------------|--------|------------------------------|
| 1       | ARCHITECTURE  | senior       | 165.0       | US     | Principal architect, 15+ yrs |
| 2       | ARCHITECTURE  | intermediate | 135.0       | US     | Project architect, 5-15 yrs  |
| 8       | MEP           | senior       | 155.0       | US     | Senior MEP engineer          |

**How This Table is Used:**
- **Design-Build Contracts:** Calculate professional service fees for engineering teams
- **Budget Planning:** Estimate man-hours × hourly rates for design phases
- **Outsourcing Decisions:** Compare in-house rates vs. consultant quotes

**Current Contents:** 14 rates across 3 disciplines (Architecture, Structure, MEP)

**To Update Rates:**
```sql
-- Update rate for senior architects
UPDATE discipline_rates
SET hourly_rate = 175.0, effective_date = CURRENT_TIMESTAMP
WHERE discipline = 'ARCHITECTURE' AND skill_level = 'senior';
```

**Page Reference:** Section 6.3 explains how to edit rates via SQL

---

#### `material_assignments` (Visual Materials)
Stores material visual properties (colors, textures) for 3D rendering purposes only.

**Table Structure:**
| Column        | Type | Description                          | Example                        |
|---------------|------|--------------------------------------|--------------------------------|
| guid          | TEXT | Unique element identifier            | 2O2Fr$t4X7Zf8NOew3FLOH        |
| material_name | TEXT | Material description                 | Steel, Concrete, Gypsum        |
| rgba          | TEXT | Color in RGBA format (hex)           | #808080FF (gray with full opacity)|

**Note:** This table does NOT contain pricing information. It's used for 3D visualization only.

---

#### `clash_status` (Quality Control)
Tracks design conflicts detected during analysis (not used in BOQ costing directly).

---

## 3. Excel Report Structure

The generated BOQ Excel file contains **7-10 sheets** organized for different audiences:

### Sheet 1: 📄 Cover Sheet
**Purpose:** Methodology explanation, pricing standards documentation

**Contents:**
- Project details and date
- Cost breakdown methodology (where rates come from)
- Malaysian standards references (CIDB, BCISM, PWD)
- Report structure explanation
- Important exclusions and disclaimers

**Who uses it:** Project managers, auditors, tender reviewers

---

### Sheet 2: 📈 Executive Summary
**Purpose:** High-level summary for decision makers

**Contents:**

#### A) Discipline Summary Table
| Discipline | Material (RM) | Labor (RM) | Equipment (RM) | TOTAL (RM) |
|------------|---------------|------------|----------------|------------|
| STR        | 850,000       | 380,000    | 95,000         | 1,325,000  |
| ACMV       | 520,000       | 280,000    | 45,000         | 845,000    |
| ARC        | 450,000       | 195,000    | 12,000         | 657,000    |
| **TOTAL**  | **2,120,000** | **1,580,000** | **285,000** | **4,850,000** |

**NEW FEATURES:**
- **Data Bars:** Visual bar charts in Total column showing relative cost
- **Linked Formulas:** Totals automatically link to detail BOQ sheets

#### B) Charts
- **Pie Chart:** Cost breakdown by discipline
- **Bar Chart:** Material/Labor/Equipment breakdown per discipline

**Who uses it:** Senior management, finance directors, tender evaluation teams

---

### Sheet 3: 💼 Work Packages
**Purpose:** Construction scheduling & phasing (NEW FEATURE)

Groups work by **construction sequence** instead of discipline:

| Package | Description           | Elements Included           | Total Cost |
|---------|-----------------------|-----------------------------|------------|
| 1       | Substructure          | Foundations, columns, beams | RM 850K    |
| 2       | Superstructure        | Slabs, walls, roof          | RM 1.2M    |
| 3       | MEP Rough-in          | Ducts, pipes, cable trays   | RM 680K    |
| 4       | Finishes              | Floors, ceilings, doors     | RM 920K    |
| 5       | MEP Final Fix         | Fixtures, lights, terminals | RM 450K    |

**Who uses it:** Project schedulers, construction managers, procurement teams

**Accounting Use:**
- Map packages to **milestone payments** in contracts
- Track **progress billing** by completed packages
- Budget allocation for **staged procurement**

---

### Sheet 4: 💰 Material Summary
**Purpose:** Detailed material cost breakdown

**Columns:**
- Discipline
- IFC Class (element type)
- Quantity
- UOM
- Unit Rate (RM)
- Total Material Cost (RM)

**Sample:**
| Discipline | IFC Class | Quantity | UOM | Unit Rate | Total Material |
|------------|-----------|----------|-----|-----------|----------------|
| STR        | IfcBeam   | 1,250.50 | M   | 680.00    | 850,340        |
| STR        | IfcColumn | 380.25   | M   | 1,250.00  | 475,312        |

**Accounting Use:**
- **Material procurement budgets**
- **Supplier quote comparisons** (check if rates are competitive)
- **Variance analysis** (actual vs estimated material costs)

---

### Sheet 5: 👷 Labor Summary
**Purpose:** Crew allocation and man-day calculations

**Columns:**
- Discipline
- IFC Class
- Quantity
- UOM
- Trade (skill type)
- Crew Size
- Man-Days
- Labor Cost (RM)

**Sample:**
| Discipline | IFC Class | Qty   | Trade              | Crew | Man-Days | Labor Cost |
|------------|-----------|-------|--------------------|------|----------|------------|
| STR        | IfcBeam   | 1,250 | Steel Erector      | 4    | 156.3    | 121,905    |
| ACMV       | IfcDuct   | 850   | HVAC Technician    | 2    | 47.2     | 17,464     |

**Accounting Use:**
- **Payroll forecasting** (total man-days × daily rates)
- **Labor cost tracking** by trade
- **Productivity benchmarking** (actual days vs estimated)

---

### Sheet 6: 🚜 Equipment Summary
**Purpose:** Plant hire and machinery requirements

**Columns:**
- Discipline
- IFC Class
- Equipment Type
- Duration (days)
- Rate/Day (RM)
- Total Equipment Cost (RM)

**Sample:**
| Discipline | IFC Class | Equipment           | Days | Rate/Day | Total Cost |
|------------|-----------|---------------------|------|----------|------------|
| STR        | IfcBeam   | Mobile Crane 20T    | 78.1 | 1,850.00 | 144,485    |
| STR        | IfcSlab   | Concrete Pump       | 39.3 | 950.00   | 37,335     |

**Accounting Use:**
- **Equipment rental budgets**
- **Capital vs operational expense** decisions
- **Rental vs purchase** cost analysis

---

### Sheets 7+: 📋 BOQ - [Discipline]
**Purpose:** Line-by-line detailed BOQ per discipline (contractual document)

**Columns:**
| Item | Description                        | Qty   | UOM | Mat Rate | Mat Cost | Labor Cost | Equip Cost | **Total** |
|------|------------------------------------|-------|-----|----------|----------|------------|------------|-----------|
| 001  | Structural Steel I-Beam - Airport  | 1,250 | M   | 680.00   | 850,000  | 121,905    | 144,485    | 1,116,390 |
| 002  | Structural Steel Column - Airport  | 380   | M   | 1,250.00 | 475,000  | 74,100     | 72,242     | 621,342   |
| ...  | ...                                | ...   | ... | ...      | ...      | ...        | ...        | ...       |

**✨ NEW PROFESSIONAL FEATURES (2024):**

#### 🎨 Visual Enhancements
- **Zebra Striping:** Alternating light gray rows for easier reading
- **Color-Coded Headers:** Material (green), Labor (orange), Equipment (blue), Total (red)
- **Conditional Formatting:** High-value items (>RM 50,000) highlighted in light yellow with bold font

#### 🔒 Data Quality Controls
- **Yellow Cells = Editable:** Material rate column can be adjusted
- **Data Validation:** Prevents negative or zero rates (shows error message)
- **Auto-Calculate:** All totals update instantly when you change rates

#### 🖨️ Print Optimization
- **Landscape Layout:** Better fit for wide BOQ tables
- **A4 Paper Size:** Standard Malaysian format
- **Fit to Width:** Entire table fits on one page width
- **Professional Headers/Footers:**
  - Header: "BOQ - [Discipline Name]"
  - Footer Left: "Terminal 1 Expansion Project"
  - Footer Center: "Page X of Y"
  - Footer Right: "Generated: DD/MM/YYYY"

**Who uses it:** Quantity surveyors, tender evaluation, contract pricing

**Accounting Use:**
- **Tender preparation** (submit to contractors)
- **Cost control** (compare quoted vs estimated)
- **Change order pricing** (variations & amendments)
- **Print-ready professional documents** for contract submissions

---

## 4. Cost Calculation Methodology

### Material Costs

**Source:** CIDB National Construction Cost Centre (N3C) 2024 + BCISM Cost Book 2022-2024

**Calculation:**
```
Material Cost = Quantity × Unit Rate
```

**Example:**
```
Element: IfcBeam (Structural Steel I-Beam)
Quantity: 1,250.5 meters
Unit Rate: RM 680.00 /meter (includes material + fabrication + fire protection)
Material Cost: 1,250.5 × 680 = RM 850,340
```

**What's Included in Rates:**
- Raw material cost
- Fabrication/manufacturing
- Delivery to site
- Wastage allowance (5-10%)
- Site handling

**What's NOT Included:**
- Installation labor (separate calculation)
- GST/SST tax
- Preliminaries & overheads

### Labor Costs

**Source:** MBAM-CIDB Labour Wage Survey 2024 + CIDB Productivity Standards

**Calculation:**
```
Step 1: Days Needed = Quantity ÷ Productivity Rate
Step 2: Labor Cost = Days Needed × Crew Size × Daily Rate
```

**Example:**
```
Element: IfcBeam (Steel I-Beam)
Quantity: 1,250.5 meters
Productivity: 8 meters/day (per crew)
Crew Size: 4 workers (steel erectors)
Daily Rate: RM 195/worker (includes EPF, SOCSO, benefits)

Days Needed: 1,250.5 ÷ 8 = 156.3 days
Labor Cost: 156.3 × 4 × 195 = RM 121,914
```

**Daily Rate Breakdown:**
| Component          | Amount     | Notes                                |
|--------------------|------------|--------------------------------------|
| Basic Wage         | RM 150/day | Market rate for skilled worker       |
| EPF (13%)          | RM 19.50   | Employee Provident Fund              |
| SOCSO (2%)         | RM 3.00    | Social Security Organisation         |
| Benefits (15%)     | RM 22.50   | Insurance, medical, uniform, tools   |
| **Total**          | **RM 195** | All-in labor cost per worker per day |

**Productivity Standards:**
Based on CIDB industry benchmarks for average crew performance under normal site conditions.

### Equipment Costs

**Source:** CIDB N3C Machinery Hire Rates 2024

**Calculation:**
```
Equipment Cost = Labor Days × Duration Factor × Equipment Daily Rate
```

**Example:**
```
Element: IfcBeam (Steel I-Beam installation)
Labor Days: 156.3 days
Duration Factor: 0.5 (crane needed 50% of work time)
Equipment: Mobile Crane 20T
Daily Rate: RM 1,850/day (operator included)

Equipment Days: 156.3 × 0.5 = 78.15 days
Equipment Cost: 78.15 × 1,850 = RM 144,578
```

**Duration Factors (Typical):**
| Work Type          | Equipment           | Factor | Reason                             |
|--------------------|---------------------|--------|------------------------------------|
| Beam installation  | Mobile Crane        | 50%    | Crane for lifting only, not 24/7   |
| Slab concreting    | Concrete Pump       | 30%    | Pump used during pour only         |
| Duct installation  | Scissor Lift        | 40%    | Access equipment part-time         |

---

## 5. How to Use the Reports

### For Budget Preparation

**Task:** Prepare project budget for tender submission

**Steps:**
1. Open **📈 Executive Dashboard** → Note grand total in KPI card
2. Review **discipline percentages** → Identify largest cost drivers
3. Check **💼 Work Packages** → Map to payment milestones
4. Open **📋 BOQ - [Discipline]** sheets → Review yellow-highlighted rates
5. Adjust rates if needed → Update to your company's actual costs
6. Add markup in separate sheet:
   ```
   Base Cost (from BOQ):    RM 4,850,000
   Preliminaries (10%):     RM   485,000
   Profit (12%):            RM   582,000
   ───────────────────────────────────────
   Tender Price:            RM 5,917,000
   ```

### For Cost Control

**Task:** Track actual vs estimated costs during construction

**Steps:**
1. Export **💰 Material Summary** to CSV
2. Import into your accounting system
3. Create columns: `Estimated`, `Actual`, `Variance`, `%Variance`
4. Update `Actual` as invoices received:
   ```
   | Item    | Estimated | Actual  | Variance | % Var |
   |---------|-----------|---------|----------|-------|
   | IfcBeam | 850,340   | 820,500 | -29,840  | -3.5% |
   ```
5. Flag variances > 5% for investigation

### For Progress Claims

**Task:** Calculate progress payment based on work completed

**Steps:**
1. Use **💼 Work Packages** as payment schedule
2. Measure completed work by package
3. Calculate payment:
   ```
   Package 2 - Superstructure:     RM 1,200,000 (100% complete)
   Package 3 - MEP Rough-in:       RM   680,000 (60% complete)

   Payment Due:
   - Package 2: RM 1,200,000 × 100% = RM 1,200,000
   - Package 3: RM   680,000 × 60%  = RM   408,000
   ──────────────────────────────────────────────────
   Total Claim:                      RM 1,608,000
   ```

---

## 6. Adjusting Rates & Markups

### Editable Cells (Yellow Highlighted)

**Material Rates Column:**
- You can change unit rates to match your supplier quotes
- Formulas auto-recalculate totals
- Example: Change RM 680/meter to RM 720/meter for beams

**Notes Column:**
- Add remarks, supplier names, quote references
- Example: "Rate from supplier XYZ, quote #12345"

### Adding Markups

The BOQ shows **direct costs only**. Add these in your final pricing:

#### Preliminaries & General Conditions (8-12%)
Covers:
- Site supervision & management
- Temporary facilities (office, toilets, storage)
- Utilities (water, power during construction)
- Insurance & bonds
- Quality control testing

#### Profit & Attendance (10-15%)
Your company's margin

#### Contingency (5-10%)
Risk allowance for unforeseen conditions

**Example Markup Calculation:**
```
Base BOQ Total:              RM 4,850,000
─────────────────────────────────────────
Preliminaries (10%):         RM   485,000
Subtotal:                    RM 5,335,000
Profit (12%):                RM   640,200
─────────────────────────────────────────
Subtotal before Tax:         RM 5,975,200
GST (6%) [if applicable]:    RM   358,512
─────────────────────────────────────────
FINAL TENDER PRICE:          RM 6,333,712
```

---

## 7. Common Accounting Tasks

### Task 1: Extract Data for ERP Import

**Goal:** Import BOQ data into SAP/Oracle/QuickBooks

**Method:**
1. Open **💰 Material Summary** sheet
2. Save As → CSV format
3. Import CSV into your ERP:
   - Map `discipline` → Cost Center
   - Map `ifc_class` → Account Code
   - Map `total_material` → Budget Amount

### Task 2: Compare Multiple Quotes

**Goal:** Check if quoted prices are reasonable

**Method:**
1. Export **📋 BOQ - [Discipline]** to PDF
2. Send to 3 contractors for quotes
3. Compare received quotes against BOQ rates:
   ```
   | Item    | BOQ Estimate | Contractor A | Contractor B | Lowest |
   |---------|--------------|--------------|--------------|--------|
   | IfcBeam | RM 680/m     | RM 720/m     | RM 695/m     | B      |
   | IfcSlab | RM 285/m²    | RM 275/m²    | RM 290/m²    | A      |
   ```

### Task 3: Prepare Monthly Cost Report

**Goal:** Report to management on project spending

**Method:**
1. Copy **📈 Executive Dashboard** discipline table
2. Add columns: `Budget`, `Spent to Date`, `Remaining`, `%Complete`
3. Update monthly:
   ```
   | Discipline | Budget     | Spent       | Remaining  | %Complete |
   |------------|------------|-------------|------------|-----------|
   | STR        | 1,325,000  | 850,000     | 475,000    | 64.2%     |
   | ACMV       | 845,000    | 320,000     | 525,000    | 37.9%     |
   ```

---

## 8. Limitations & Exclusions

### ❌ NOT Included in BOQ Costs

| Item                              | Reason                                              | Typical % |
|-----------------------------------|-----------------------------------------------------|-----------|
| GST/SST Tax                       | Tax rates vary by project type and timing           | 6%        |
| Preliminaries                     | Site-specific, varies by project duration           | 8-12%     |
| Profit & Overheads                | Company margin                                      | 10-15%    |
| Contingency                       | Risk allowance                                      | 5-10%     |
| Professional Fees                 | Architect, engineer consultant fees                | Separate  |
| Authority Fees                    | Building permits, approvals                         | Separate  |
| Financing Costs                   | Interest on construction loans                      | Separate  |

### ⚠️ Assumptions & Disclaimers

**Pricing Date:**
- Rates are Q4 2024 Malaysian market prices
- Valid for 60 days from report date
- Subject to material price fluctuations

**Quantities:**
- Based on BIM model as of extraction date
- Assumes model is **100% coordinated** (no clashes)
- Does not include rework due to design changes

**Productivity:**
- Based on CIDB average rates
- Assumes normal site conditions
- Weather delays, site access issues not included

**Site Conditions:**
- Assumes level site with good access
- No contaminated soil or rock excavation
- Utilities available at property boundary

### 📊 Recommended Next Steps

After receiving BOQ:

1. **Verify Quantities** → Cross-check with 2D drawings for major items
2. **Update Rates** → Replace with actual supplier quotes
3. **Add Project-Specific Costs** → Preliminaries, profit, contingency
4. **Get Approvals** → Submit for management review
5. **Use for Tender** → Attach to tender documents (if bidding out)
6. **Set as Budget Baseline** → Lock in accounting system for cost control

---

## 📞 Support & Questions

**For Technical Issues (Database/Software):**
- Check extraction logs in `~/Documents/bonsai/consolelogs/`
- Verify database file exists and is not corrupted
- Re-run extraction if data seems incomplete

**For Accounting Questions:**
- Refer to PWD Form 203A guidelines
- Consult CIDB pricing standards
- Review BCISM Cost Book for material rates

**For Custom Rates:**
- Edit yellow-highlighted cells directly in Excel
- Or modify Python pricing dictionaries:
  - `MATERIAL_COSTS` (line 21)
  - `LABOR_RATES` (line 67)
  - `EQUIPMENT_RATES` (line 147)

---

## 📚 Reference Standards

| Standard | Full Name                                      | Purpose                          |
|----------|------------------------------------------------|----------------------------------|
| PWD 203A | Public Works Department Form 203A              | Standard BOQ format Malaysia     |
| SMM2     | Standard Method of Measurement (2nd Edition)   | Quantity measurement rules       |
| CIDB N3C | CIDB National Construction Cost Centre         | Material & equipment rates       |
| BCISM    | Building Cost Information Services Malaysia    | Cost benchmarking                |
| MBAM     | Master Builders Association Malaysia           | Labor wage survey                |

---

## 📑 APPENDIX A: Cost Calculation Reference Tables

### Where to Customize Rates

All pricing rates are defined in the Python script:
```
File Location: src/bonsai/bonsai/bim/module/federation/dataintelligence/comprehensive_boq_export.py
```

**Three main pricing dictionaries:**
1. `MATERIAL_COSTS` (starts at line ~23)
2. `LABOR_RATES` (starts at line ~69)
3. `EQUIPMENT_RATES` (starts at line ~147)

---

### A1. Material Costs Reference Table

**Source:** CIDB N3C + BCISM Cost Book 2022-2024 (inflated +3% for 2024)

#### HVAC Ductwork (Galvanized Steel)
| IFC Class        | Rate (RM) | Unit | Description                      | Specification                    |
|------------------|-----------|------|----------------------------------|----------------------------------|
| IfcDuct          | 165.00    | M    | Galvanized Steel Ductwork        | G550, 0.6mm thickness, avg 400mm |
| IfcDuctSegment   | 165.00    | M    | Ductwork Segment                 | G550, 0.6mm thickness            |
| IfcDuctFitting   | 380.00    | EA   | Duct Fittings (elbows, tees)     | Galvanized steel                 |

#### Plumbing (PVC/HDPE Pipes)
| IFC Class        | Rate (RM) | Unit | Description                      | Specification                    |
|------------------|-----------|------|----------------------------------|----------------------------------|
| IfcPipe          | 48.50     | M    | PVC/HDPE Pipe (avg 100mm)        | Schedule 40, Class E             |
| IfcPipeSegment   | 48.50     | M    | Pipe Segment                     | Schedule 40                      |
| IfcPipeFitting   | 95.00     | EA   | Pipe Fittings                    | PVC/brass mix                    |

#### Electrical Cable Management
| IFC Class            | Rate (RM) | Unit | Description                  | Specification                    |
|----------------------|-----------|------|------------------------------|----------------------------------|
| IfcCableCarrier      | 78.00     | M    | Cable Tray System (300mm)    | Aluminum ladder type             |
| IfcCableCarrierSegment| 78.00    | M    | Cable Tray Segment           | Aluminum                         |

#### Structural Steel
| IFC Class  | Rate (RM) | Unit | Description                           | Specification                                          |
|------------|-----------|------|---------------------------------------|--------------------------------------------------------|
| IfcBeam    | 680.00    | M    | Structural Steel I-Beam - Airport     | Grade 50, shop fabrication, fire protection            |
| IfcColumn  | 1,250.00  | M    | Structural Steel Column - Airport     | Grade 50, UC section, fire protection, heavy duty      |

**Basis:** Mild steel @ RM 3,800/tonne (2024 market)
- I-Beam 400x200: ~66kg/m → RM 250/m material + RM 300/m fabrication + RM 130/m fire protection
- Column 400x400: ~146kg/m → RM 555/m material + RM 450/m fabrication + RM 245/m fire protection

#### Concrete & Slabs
| IFC Class  | Rate (RM) | Unit | Description                        | Specification                                        |
|------------|-----------|------|------------------------------------|------------------------------------------------------|
| IfcSlab    | 285.00    | M2   | RC Slab - Airport Grade (250mm)    | Grade 40 concrete, heavy rebar, formwork, curing     |

#### Walls
| IFC Class          | Rate (RM) | Unit | Description                    | Specification                                |
|--------------------|-----------|------|--------------------------------|----------------------------------------------|
| IfcWall            | 145.00    | M2   | Blockwork Wall (150mm)         | Cement block, plastered one side             |
| IfcWallStandardCase| 145.00    | M2   | Standard Wall                  | Blockwork                                    |
| IfcCurtainWall     | 750.00    | M2   | Aluminum Curtain Wall          | Double glazed, powder coated                 |

#### Finishes
| IFC Class   | Rate (RM) | Unit | Description                              | Specification                                      |
|-------------|-----------|------|------------------------------------------|----------------------------------------------------|
| IfcCovering | 185.00    | M2   | Floor/Ceiling Finishes - Airport Grade   | Granite tiles 600x600 / Metal suspended ceiling    |
| IfcRoof     | 238.00    | M2   | Metal Deck Roofing with Insulation       | Standing seam, insulation, waterproofing           |

#### Fixtures & Fittings
| IFC Class               | Rate (RM) | Unit | Description                          | Specification                                     |
|-------------------------|-----------|------|--------------------------------------|---------------------------------------------------|
| IfcLightFixture         | 485.00    | EA   | LED Light Fixture - Airport Grade    | Commercial 48W, dimming control, emergency backup |
| IfcOutlet               | 125.00    | EA   | 13A Power Outlet - Airport Spec      | Stainless steel plate, USB charging ports         |
| IfcDoor                 | 2,850.00  | EA   | Door Set - Airport Grade             | Fire-rated, access control, automatic closer      |
| IfcWindow               | 1,580.00  | EA   | Aluminum Window - Airport Spec       | Powder coated, 12mm double glazed, acoustic       |
| IfcBuildingElementProxy | 850.00    | EA   | Misc. Building Elements              | Various fittings, furniture, signage              |
| IfcFlowTerminal         | 3,500.00  | EA   | HVAC Terminal (FCU/AHU/VAV)          | BMS integrated, VFD controls                      |

**How to Update:**
Edit file: `comprehensive_boq_export.py` around line 23-65
```python
MATERIAL_COSTS = {
    'IfcBeam': {'rate': 680.00, 'unit': 'M', 'desc': '...', 'spec': '...'},
    # Change rate here ↑
}
```

---

### A2. Labor Rates Reference Table

**Source:** MBAM-CIDB Labour Wage Survey 2024

#### Rate Structure (Daily Rate per Worker)
All rates include:
- Basic wage (8 hours)
- EPF (Employee Provident Fund) 13%
- SOCSO (Social Security) 2%
- Benefits (insurance, medical, uniform, tools) 15%

#### HVAC Installation
| Trade         | Rate/Day (RM) | Crew Size | Productivity                           |
|---------------|---------------|-----------|----------------------------------------|
| HVAC Tech     | 185.00        | 2 workers | IfcDuct: 18 m/day                      |
|               |               |           | IfcDuctSegment: 18 m/day               |
|               |               |           | IfcDuctFitting: 12 EA/day              |

**Calculation Example:**
```
1,000 meters of duct
Productivity: 18 m/day per crew
Days needed: 1,000 ÷ 18 = 55.6 days
Labor cost: 55.6 days × 2 workers × RM 185/day = RM 20,572
```

#### Plumbing Installation
| Trade         | Rate/Day (RM) | Crew Size | Productivity                           |
|---------------|---------------|-----------|----------------------------------------|
| Pipefitter    | 165.00        | 2 workers | IfcPipe: 25 m/day                      |
|               |               |           | IfcPipeSegment: 25 m/day               |
|               |               |           | IfcPipeFitting: 15 EA/day              |

#### Electrical Installation
| Trade         | Rate/Day (RM) | Crew Size | Productivity                           |
|---------------|---------------|-----------|----------------------------------------|
| Electrician   | 175.00        | 2 workers | IfcCableCarrier: 30 m/day              |
|               |               |           | IfcCableCarrierSegment: 30 m/day       |
|               |               |           | IfcLightFixture: 20 EA/day             |
|               |               |           | IfcOutlet: 25 EA/day                   |

#### Structural Steel Erection
| Trade         | Rate/Day (RM) | Crew Size | Productivity                           |
|---------------|---------------|-----------|----------------------------------------|
| Steel Erector | 195.00        | 4 workers | IfcBeam: 8 m/day                       |
|               |               |           | IfcColumn: 4 m/day                     |

**Note:** Airport terminal spec requires higher safety standards, hence lower productivity vs standard warehouse.

#### Concrete Works
| Trade         | Rate/Day (RM) | Crew Size | Productivity                           |
|---------------|---------------|-----------|----------------------------------------|
| Concreter     | 155.00        | 6 workers | IfcSlab: 25 m²/day                     |

**Note:** Heavy slabs (250mm+ thickness) require larger crew for screeding and finishing.

#### General Carpentry & Finishing
| Trade         | Rate/Day (RM) | Crew Size | Productivity                           |
|---------------|---------------|-----------|----------------------------------------|
| Carpenter     | 145.00        | 2 workers | IfcDoor: 4 EA/day                      |
|               |               |           | IfcWindow: 5 EA/day                    |
| Mason         | 135.00        | 2 workers | IfcWall: 12 m²/day                     |
| Finisher      | 125.00        | 2 workers | IfcCovering: 20 m²/day                 |
| Roofer        | 150.00        | 3 workers | IfcRoof: 15 m²/day                     |

**How to Update:**
Edit file: `comprehensive_boq_export.py` around line 69-145
```python
LABOR_RATES = {
    'HVAC_TECH': {
        'rate_per_day': 185.00,  # ← Change rate here
        'productivity': {
            'IfcDuct': 18.0,  # ← Change productivity here
        },
        'crew_size': 2,  # ← Change crew size here
        'trade': 'HVAC Technician (Skilled)'
    },
}
```

---

### A3. Equipment Rates Reference Table

**Source:** CIDB N3C Machinery Hire Rates 2024

#### Heavy Lifting Equipment
| Equipment                  | Rate/Day (RM) | Specification                                       |
|----------------------------|---------------|-----------------------------------------------------|
| Mobile Crane 20T           | 1,850.00      | 20-tonne capacity, operator included, 10-hour day   |
| Mobile Crane 50T           | 2,800.00      | 50-tonne capacity, operator included, 10-hour day   |
| Tower Crane                | 2,200.00      | Static crane, operator + signalman, monthly rate    |

#### Concrete Equipment
| Equipment                  | Rate/Day (RM) | Specification                                       |
|----------------------------|---------------|-----------------------------------------------------|
| Concrete Pump (Trailer)    | 950.00        | 60m boom, operator included, diesel                 |
| Concrete Mixer 1m³         | 180.00        | Diesel, self-operated                               |

#### Access Equipment
| Equipment                  | Rate/Day (RM) | Specification                                       |
|----------------------------|---------------|-----------------------------------------------------|
| Scissor Lift 8m            | 280.00        | Electric, 8m working height, battery included       |
| Boom Lift 15m              | 450.00        | Diesel, 15m working height, operator extra          |
| Scaffolding (per m²)       | 12.00         | Modular scaffold system, monthly rate per m²        |

#### General Tools
| Equipment                  | Rate/Day (RM) | Specification                                       |
|----------------------------|---------------|-----------------------------------------------------|
| Welding Machine            | 85.00         | 200A inverter, cables included, no operator         |
| Compressor 10HP            | 120.00        | Diesel air compressor, with tools                   |

#### Equipment Allocation by Work Type

| IFC Class     | Equipment Type          | Duration Factor | Explanation                                    |
|---------------|-------------------------|-----------------|------------------------------------------------|
| IfcBeam       | Mobile Crane 20T        | 50%             | Crane needed for lifting only, not 24/7        |
| IfcColumn     | Mobile Crane 20T        | 50%             | Crane for lifting, rest is alignment/welding   |
| IfcSlab       | Concrete Pump           | 30%             | Pump only during pour, not curing period       |
| IfcDuct       | Scissor Lift 8m         | 40%             | Access equipment for overhead work             |
| IfcPipe       | Scissor Lift 8m         | 30%             | Some at grade, some overhead                   |
| IfcCableCarrier| Scissor Lift 8m        | 40%             | Most cable trays are overhead                  |

**Duration Factor Calculation:**
```
Equipment Days = Labor Days × Duration Factor

Example:
Labor Days: 156.3 days (steel beam installation)
Duration Factor: 0.5 (crane needed 50% of time)
Equipment Days: 156.3 × 0.5 = 78.15 days
Equipment Cost: 78.15 × RM 1,850/day = RM 144,578
```

**How to Update:**
Edit file: `comprehensive_boq_export.py` around line 147-190 (rates) and 192-230 (allocation)

```python
# Equipment rates
EQUIPMENT_RATES = {
    'CRANE_20T': {
        'rate_per_day': 1850.00,  # ← Change rate here
        'description': 'Mobile Crane 20-tonne',
    },
}

# Equipment allocation
EQUIPMENT_ALLOCATION = {
    'IfcBeam': {
        'equipment': 'CRANE_20T',
        'duration_factor': 0.50  # ← Change factor here (0.0 to 1.0)
    },
}
```

---

### A4. Quick Reference: Where to Make Changes

#### To Change Material Rates (e.g., supplier quotes changed)
**File:** `comprehensive_boq_export.py`
**Line:** ~23-65
**Example:**
```python
'IfcDuct': {'rate': 165.00, 'unit': 'M', ...},
# Change to:
'IfcDuct': {'rate': 180.00, 'unit': 'M', ...},  # Updated supplier quote
```

#### To Change Labor Productivity (e.g., your crew is faster)
**File:** `comprehensive_boq_export.py`
**Line:** ~69-145
**Example:**
```python
'productivity': {
    'IfcDuct': 18.0,  # meters per day
}
# Change to:
'productivity': {
    'IfcDuct': 22.0,  # Your crew installs 22m/day instead
}
```

#### To Change Equipment Hire Rates (e.g., different rental company)
**File:** `comprehensive_boq_export.py`
**Line:** ~147-190
**Example:**
```python
'CRANE_20T': {'rate_per_day': 1850.00, ...},
# Change to:
'CRANE_20T': {'rate_per_day': 1600.00, ...},  # New rental company cheaper
```

#### To Add New Material Type
**File:** `comprehensive_boq_export.py`
**Line:** Add to `MATERIAL_COSTS` dictionary
**Example:**
```python
MATERIAL_COSTS = {
    # ... existing entries ...
    'IfcChiller': {
        'rate': 125000.00,
        'unit': 'EA',
        'desc': 'Water-Cooled Chiller 500RT',
        'spec': 'Centrifugal type, R134a refrigerant'
    },
}
```

---

### A5. Validation & Quality Checks

Before using BOQ rates, verify:

#### Material Rates Checklist
- [ ] Rates are current (within 60 days)
- [ ] Includes delivery to site (not ex-factory)
- [ ] Wastage allowance included (5-10%)
- [ ] Specification matches project requirements
- [ ] Currency is MYR (Malaysian Ringgit)

#### Labor Rates Checklist
- [ ] Statutory contributions included (EPF, SOCSO)
- [ ] Productivity suits your site conditions
- [ ] Crew size matches your work method
- [ ] Safety requirements considered (airport = stricter)

#### Equipment Rates Checklist
- [ ] Operator included or excluded (check description)
- [ ] Fuel/diesel included or excluded
- [ ] Mobilization/demobilization costs separate
- [ ] Minimum hire period considered (daily/weekly/monthly)

---

### A6. Regional Rate Adjustments

Malaysian construction costs vary by region. Adjust rates for:

| Region               | Adjustment Factor | Reason                                    |
|----------------------|-------------------|-------------------------------------------|
| Klang Valley (KL/PJ) | 1.00              | Base rates (highest costs)                |
| Penang               | 0.95              | Good infrastructure, competitive market   |
| Johor Bahru          | 0.92              | Proximity to Singapore materials          |
| East Malaysia        | 1.15-1.25         | Logistics costs, limited suppliers        |
| Rural areas          | 0.85-0.90         | Lower wages, but logistics premium        |

**How to Apply:**
Multiply all rates in BOQ by adjustment factor after generation.

**Example:**
```
Project in Kuching, Sarawak (East Malaysia)
BOQ shows: RM 4,850,000
Regional factor: 1.20 (20% increase)
Adjusted total: RM 4,850,000 × 1.20 = RM 5,820,000
```

---

### A7. Inflation Adjustment

Rates are Q4 2024. For future projects:

**CIDB Forecast:**
- 2025: +3.0% inflation
- 2026: +2.5% inflation
- 2027: +2.5% inflation

**How to Escalate:**
```python
# For 2025 project
Original Rate (2024): RM 680.00
Escalated (2025):     RM 680 × 1.03 = RM 700.40

# For 2026 project
Original Rate (2024): RM 680.00
Escalated (2026):     RM 680 × 1.03 × 1.025 = RM 717.91
```

**Automatic Escalation Code:**
```python
import datetime
base_year = 2024
current_year = datetime.datetime.now().year
years_elapsed = current_year - base_year

escalation_factors = {1: 1.03, 2: 1.03 * 1.025, 3: 1.03 * 1.025 * 1.025}
factor = escalation_factors.get(years_elapsed, 1.0)

escalated_rate = base_rate * factor
```

---

**End of Appendix A**

---

**End of User Guide**

*This document is part of the Bonsai BIM Federation System.*
*For software updates, visit: https://github.com/IfcOpenShell/IfcOpenShell*
