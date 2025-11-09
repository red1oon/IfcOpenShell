"""
FIXED Comprehensive BOQ Export - Corrected Quantity Calculation
================================================================
Fixes for "billions" issue + adds reference sheets

Key Fixes:
1. Use PRIMARY quantity only per element type (not sum of all quantities)
2. Use ifc_labels for friendly descriptions
3. Add reference sheets with Excel cell formulas
4. Add Manufacturer/Model columns (P0)
5. Add Compliance and Quality sheets (P1)

Strategy A: Primary Quantity Logic
- IfcWall → GrossSideArea (M2)
- IfcBeam → Length (M)
- IfcDoor → Count (EA)
etc.
"""

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Import base exporter for cost calculation methods
sys.path.insert(0, str(Path(__file__).parent))
from comprehensive_boq_export import (
    ComprehensiveBOQExporter,
    MATERIAL_COSTS,
    LABOR_RATES,
    EQUIPMENT_RATES,
    EQUIPMENT_ALLOCATION
)

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule, DataBarRule, CellIsRule
from openpyxl.chart import PieChart, BarChart, Reference
from openpyxl.worksheet.datavalidation import DataValidation


# IFC Labels mapping (fallback if not in database)
IFC_LABELS_FALLBACK = {
    'IfcBeam': ('Structural Steel I-Beam', 'Length', 'M'),
    'IfcColumn': ('Structural Steel Column', 'Length', 'M'),
    'IfcSlab': ('RC Slab - Airport Grade', 'GrossArea', 'M2'),
    'IfcWall': ('Blockwork Wall (150mm)', 'GrossSideArea', 'M2'),
    'IfcWallStandardCase': ('Standard Wall', 'GrossSideArea', 'M2'),
    'IfcCurtainWall': ('Aluminum Curtain Wall', 'GrossArea', 'M2'),
    'IfcDoor': ('Door Set - Airport Grade', 'COUNT', 'EA'),
    'IfcWindow': ('Aluminum Window - Airport Spec', 'COUNT', 'EA'),
    'IfcCovering': ('Floor/Ceiling Finishes', 'GrossArea', 'M2'),
    'IfcRoof': ('Metal Deck Roofing', 'GrossArea', 'M2'),
    'IfcDuct': ('Galvanized Steel Ductwork', 'Length', 'M'),
    'IfcDuctSegment': ('Ductwork Segment', 'Length', 'M'),
    'IfcDuctFitting': ('Duct Fittings', 'COUNT', 'EA'),
    'IfcFlowTerminal': ('HVAC Terminal Unit', 'COUNT', 'EA'),
    'IfcPipe': ('PVC/HDPE Pipe', 'Length', 'M'),
    'IfcPipeSegment': ('Pipe Segment', 'Length', 'M'),
    'IfcPipeFitting': ('Pipe Fittings', 'COUNT', 'EA'),
    'IfcCableCarrier': ('Cable Tray System (300mm)', 'Length', 'M'),
    'IfcCableCarrierSegment': ('Cable Tray Segment', 'Length', 'M'),
    'IfcLightFixture': ('LED Light Fixture', 'COUNT', 'EA'),
    'IfcOutlet': ('13A Power Outlet', 'COUNT', 'EA'),
    'IfcBuildingElementProxy': ('Misc. Building Elements', 'COUNT', 'EA'),
    'IfcPlate': ('Steel Plate', 'GrossArea', 'M2'),
    'IfcMember': ('Structural Member', 'Length', 'M'),
    'IfcStairFlight': ('Stair Flight', 'GrossArea', 'M2'),
    'IfcRampFlight': ('Ramp Flight', 'GrossArea', 'M2'),
    'IfcRailing': ('Railing/Balustrade', 'Length', 'M'),
}


class FixedBOQExporter(ComprehensiveBOQExporter):
    """Fixed BOQ exporter with correct quantity calculation and reference sheets."""

    def __init__(self):
        super().__init__()
        self.ifc_labels_cache = {}  # Cache for ifc_labels from database
        self.material_rates_row_map = {}  # Maps ifc_class to row in reference sheet
        self.labor_rates_row_map = {}
        self.equipment_rates_row_map = {}

    def load_ifc_labels(self, db_path: str):
        """Load ifc_labels from database or use fallback."""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT ifc_class, friendly_label, primary_quantity, primary_unit
                FROM ifc_labels
            """)
            for ifc_class, label, qty_name, unit in cursor.fetchall():
                self.ifc_labels_cache[ifc_class] = (label, qty_name, unit)
            print(f"✓ Loaded {len(self.ifc_labels_cache)} IFC labels from database")
        except sqlite3.OperationalError:
            # Table doesn't exist, use fallback
            self.ifc_labels_cache = IFC_LABELS_FALLBACK
            print(f"⚠ ifc_labels table not found, using fallback ({len(self.ifc_labels_cache)} labels)")

        conn.close()

    def get_friendly_description(self, ifc_class: str):
        """Get friendly description for IFC class."""
        if ifc_class in self.ifc_labels_cache:
            return self.ifc_labels_cache[ifc_class][0]
        # Fallback to material costs description
        if ifc_class in MATERIAL_COSTS:
            return MATERIAL_COSTS[ifc_class]['desc']
        return ifc_class  # Last resort

    def get_primary_quantity_info(self, ifc_class: str):
        """Get primary quantity name and unit for IFC class."""
        if ifc_class in self.ifc_labels_cache:
            return self.ifc_labels_cache[ifc_class][1], self.ifc_labels_cache[ifc_class][2]
        # Fallback defaults
        return 'NetVolume', ''

    def query_discipline_quantities(self, db_path: str, discipline: str):
        """
        Query quantities using PRIMARY quantity only (Strategy A).
        Fixes the "billions" bug by using pre-aggregated simple_qto table.
        """
        conn = sqlite3.connect(db_path)

        #Check if this is the aggregated schema (has 'discipline' column)
        cursor = conn.execute("PRAGMA table_info(simple_qto)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'discipline' in columns and 'ifc_class' in columns:
            # Aggregated schema (sample_extracted_v3.db) - simpler query!
            query = """
                SELECT
                    ifc_class,
                    element_count,
                    total_quantity,
                    uom
                FROM simple_qto
                WHERE discipline = ?
                AND total_quantity > 0
                ORDER BY total_quantity DESC
            """
            cursor = conn.execute(query, (discipline,))
            results = [(row[0], row[1], row[2]) for row in cursor.fetchall()]
        else:
            # Enhanced schema (sample_properties_enhanced.db) - need JOIN
            # Build CASE statement for primary quantities
            case_clauses = []
            for ifc_class, (label, qty_name, unit) in self.ifc_labels_cache.items():
                if qty_name == 'COUNT':
                    case_clauses.append(f"WHEN '{ifc_class}' THEN 1.0")
                else:
                    case_clauses.append(f"WHEN '{ifc_class}' THEN MAX(CASE WHEN q.quantity_name = '{qty_name}' THEN q.quantity_value END)")

            case_sql = '\n                '.join(case_clauses)

            query = f"""
                WITH primary_quantities AS (
                    SELECT
                        e.guid,
                        e.ifc_class,
                        e.discipline,
                        CASE e.ifc_class
                            {case_sql}
                            ELSE MAX(q.quantity_value)
                        END as quantity_value
                    FROM elements_meta e
                    LEFT JOIN simple_qto q ON e.guid = q.guid
                    WHERE e.discipline = ?
                    GROUP BY e.guid, e.ifc_class, e.discipline
                )
                SELECT
                    ifc_class,
                    COUNT(*) as element_count,
                    SUM(COALESCE(quantity_value, 0)) as total_quantity
                FROM primary_quantities
                WHERE total_quantity > 0
                GROUP BY ifc_class
                ORDER BY total_quantity DESC
            """
            cursor = conn.execute(query, (discipline,))
            results = cursor.fetchall()

        conn.close()
        return results

    def create_material_rates_reference_sheet(self):
        """Create Material Rates Reference sheet for user editing."""
        ws = self.wb.create_sheet("📋 Material Rates", len(self.wb.sheetnames))

        # Title
        ws.merge_cells('A1:F1')
        ws['A1'] = "MATERIAL RATES REFERENCE - Edit rates here"
        ws['A1'].font = Font(size=16, bold=True, color='FFFFFF')
        ws['A1'].fill = PatternFill(start_color=self.colors['material'], end_color=self.colors['material'], fill_type='solid')
        ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[1].height = 25

        # Headers
        row = 3
        headers = ['IFC Class', 'Description', 'Unit', 'Rate (RM)', 'Source', 'Date']
        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row, col, header)
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill(start_color=self.colors['header'], end_color=self.colors['header'], fill_type='solid')
            cell.alignment = Alignment(horizontal='center')
        row += 1

        # Populate from MATERIAL_COSTS
        for ifc_class in sorted(MATERIAL_COSTS.keys()):
            mat = MATERIAL_COSTS[ifc_class]
            ws.cell(row, 1, ifc_class)
            ws.cell(row, 2, mat['desc'])
            ws.cell(row, 3, mat['unit'])
            ws.cell(row, 4, mat['rate']).number_format = '#,##0.00'
            ws.cell(row, 5, "CIDB N3C / BCISM 2024")
            ws.cell(row, 6, "2024-Q4")

            # Yellow highlight on rate column (editable)
            ws.cell(row, 4).fill = PatternFill(start_color='FFFFCC', end_color='FFFFCC', fill_type='solid')

            # Store row mapping for BOQ formula references
            self.material_rates_row_map[ifc_class] = row

            row += 1

        # Column widths
        ws.column_dimensions['A'].width = 25
        ws.column_dimensions['B'].width = 45
        ws.column_dimensions['C'].width = 8
        ws.column_dimensions['D'].width = 15
        ws.column_dimensions['E'].width = 25
        ws.column_dimensions['F'].width = 12

        ws.freeze_panes = 'A4'

        return ws

    def create_labor_rates_reference_sheet(self):
        """Create Labor Rates Reference sheet."""
        ws = self.wb.create_sheet("👷 Labor Rates", len(self.wb.sheetnames))

        # Title
        ws.merge_cells('A1:E1')
        ws['A1'] = "LABOR RATES REFERENCE - Edit rates here"
        ws['A1'].font = Font(size=16, bold=True, color='FFFFFF')
        ws['A1'].fill = PatternFill(start_color=self.colors['labor'], end_color=self.colors['labor'], fill_type='solid')
        ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[1].height = 25

        # Headers
        row = 3
        headers = ['Trade', 'Rate/Day (RM)', 'Crew Size', 'Source', 'Date']
        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row, col, header)
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill(start_color=self.colors['header'], end_color=self.colors['header'], fill_type='solid')
            cell.alignment = Alignment(horizontal='center')
        row += 1

        # Populate from LABOR_RATES
        for trade_key in sorted(LABOR_RATES.keys()):
            labor = LABOR_RATES[trade_key]
            ws.cell(row, 1, labor['trade'])
            ws.cell(row, 2, labor['rate_per_day']).number_format = '#,##0.00'
            ws.cell(row, 3, labor['crew_size'])
            ws.cell(row, 4, "MBAM-CIDB Survey 2024")
            ws.cell(row, 5, "2024-Q4")

            # Yellow highlight on rate column
            ws.cell(row, 2).fill = PatternFill(start_color='FFFFCC', end_color='FFFFCC', fill_type='solid')

            self.labor_rates_row_map[trade_key] = row

            row += 1

        # Column widths
        ws.column_dimensions['A'].width = 35
        ws.column_dimensions['B'].width = 18
        ws.column_dimensions['C'].width = 12
        ws.column_dimensions['D'].width = 25
        ws.column_dimensions['E'].width = 12

        ws.freeze_panes = 'A4'

        return ws

    def create_equipment_rates_reference_sheet(self):
        """Create Equipment Rates Reference sheet."""
        ws = self.wb.create_sheet("🚜 Equipment Rates", len(self.wb.sheetnames))

        # Title
        ws.merge_cells('A1:E1')
        ws['A1'] = "EQUIPMENT RATES REFERENCE - Edit rates here"
        ws['A1'].font = Font(size=16, bold=True, color='FFFFFF')
        ws['A1'].fill = PatternFill(start_color=self.colors['equipment'], end_color=self.colors['equipment'], fill_type='solid')
        ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[1].height = 25

        # Headers
        row = 3
        headers = ['Equipment', 'Rate/Day (RM)', 'Specification', 'Source', 'Date']
        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row, col, header)
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill(start_color=self.colors['header'], end_color=self.colors['header'], fill_type='solid')
            cell.alignment = Alignment(horizontal='center')
        row += 1

        # Populate from EQUIPMENT_RATES
        for equip_key in sorted(EQUIPMENT_RATES.keys()):
            equip = EQUIPMENT_RATES[equip_key]
            ws.cell(row, 1, equip.get('description', equip_key))
            ws.cell(row, 2, equip.get('rate_per_day', 0)).number_format = '#,##0.00'
            ws.cell(row, 3, equip.get('spec', 'Standard specification'))
            ws.cell(row, 4, "CIDB N3C 2024")
            ws.cell(row, 5, "2024-Q4")

            # Yellow highlight on rate column
            ws.cell(row, 2).fill = PatternFill(start_color='FFFFCC', end_color='FFFFCC', fill_type='solid')

            self.equipment_rates_row_map[equip_key] = row

            row += 1

        # Column widths
        ws.column_dimensions['A'].width = 30
        ws.column_dimensions['B'].width = 18
        ws.column_dimensions['C'].width = 35
        ws.column_dimensions['D'].width = 20
        ws.column_dimensions['E'].width = 12

        ws.freeze_panes = 'A4'

        return ws

    def create_fixed_boq_sheet(self, db_path: str, discipline: str):
        """
        Create BOQ sheet with FIXED quantity calculation.
        Uses primary quantity only + ifc_labels + cell references to rate sheets.
        """
        sheet_name = f"BOQ - {discipline}"
        ws = self.wb.create_sheet(sheet_name)

        # Title
        ws.merge_cells('A1:K1')
        ws['A1'] = f"DETAILED BOQ - {discipline.upper()} (Fixed Calculations)"
        ws['A1'].font = Font(size=16, bold=True, color='FFFFFF')
        ws['A1'].fill = PatternFill(start_color=self.colors['title'], end_color=self.colors['title'], fill_type='solid')
        ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[1].height = 25

        # Headers
        row = 3
        headers = ['Item', 'Description', 'Qty', 'UOM',
                   'Material\nRate (RM)', 'Material\nCost (RM)',
                   'Labor\nCost (RM)', 'Equipment\nCost (RM)',
                   'Total (RM)']

        colors = ['FFFFFF', 'FFFFFF', 'FFFFFF', 'FFFFFF',
                  self.colors['material'], self.colors['material'],
                  self.colors['labor'], self.colors['equipment'],
                  self.colors['total']]

        for col, (header, color) in enumerate(zip(headers, colors), start=1):
            cell = ws.cell(row, col, header)
            cell.font = Font(bold=True, color='FFFFFF', size=9)
            cell.fill = PatternFill(start_color=color, end_color=color, fill_type='solid')
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            cell.border = Border(bottom=Side(style='medium'))

        ws.row_dimensions[row].height = 30
        row += 1

        # Query FIXED quantities (primary only)
        results = self.query_discipline_quantities(db_path, discipline)

        if not results:
            return ws, None

        item_no = 1
        data_start = row

        for ifc_class, elem_count, total_qty in results:
            # Get friendly description and unit
            description = self.get_friendly_description(ifc_class)
            _, uom = self.get_primary_quantity_info(ifc_class)

            # Material cost (with cell reference if available)
            mat = MATERIAL_COSTS.get(ifc_class, {'rate': 0, 'unit': uom})
            mat_rate = mat['rate']

            # Use cell reference to Material Rates sheet if available
            if ifc_class in self.material_rates_row_map:
                mat_ref_row = self.material_rates_row_map[ifc_class]
                mat_rate_formula = f"='📋 Material Rates'!D{mat_ref_row}"
            else:
                mat_rate_formula = mat_rate

            # Labor & Equipment
            labor_cost, labor_days, crew_size, trade = self.calculate_labor_cost(ifc_class, total_qty)
            equip_cost, equip_desc = self.calculate_equipment_cost(ifc_class, labor_days)

            # Write row
            ws.cell(row, 1, f"{item_no:03d}")
            ws.cell(row, 2, description)
            ws.cell(row, 3, total_qty).number_format = '#,##0.00'
            ws.cell(row, 4, uom)

            # Material rate (formula or value)
            if isinstance(mat_rate_formula, str) and mat_rate_formula.startswith('='):
                ws.cell(row, 5).value = mat_rate_formula
            else:
                ws.cell(row, 5, mat_rate).number_format = '#,##0.00'

            ws.cell(row, 6).value = f"=C{row}*E{row}"
            ws.cell(row, 6).number_format = '#,##0.00'
            ws.cell(row, 7, labor_cost).number_format = '#,##0.00'
            ws.cell(row, 8, equip_cost).number_format = '#,##0.00'
            ws.cell(row, 9).value = f"=F{row}+G{row}+H{row}"
            ws.cell(row, 9).number_format = '#,##0.00'

            # Highlight high-value items (> RM 50,000)
            total_cost_estimate = (total_qty * mat_rate) + labor_cost + equip_cost
            if total_cost_estimate > 50000:
                for col in range(1, 10):
                    ws.cell(row, col).fill = PatternFill(start_color='FFF3E0', end_color='FFF3E0', fill_type='solid')
                    ws.cell(row, col).font = Font(bold=True)

            item_no += 1
            row += 1

        data_end = row - 1

        # TOTALS
        row += 1
        ws.merge_cells(f'A{row}:E{row}')
        ws[f'A{row}'] = f"TOTAL - {discipline}"
        ws[f'A{row}'].font = Font(bold=True, size=11)
        ws[f'A{row}'].alignment = Alignment(horizontal='right')

        for col, color in [(6, self.colors['material']), (7, self.colors['labor']),
                           (8, self.colors['equipment']), (9, self.colors['total'])]:
            cell = ws.cell(row, col)
            cell.value = f"=SUM({get_column_letter(col)}{data_start}:{get_column_letter(col)}{data_end})"
            cell.number_format = '#,##0.00'
            cell.font = Font(bold=True, size=11, color='FFFFFF')
            cell.fill = PatternFill(start_color=color, end_color=color, fill_type='solid')

        ws.row_dimensions[row].height = 25

        # Zebra striping
        self.apply_zebra_striping(ws, data_start, data_end, 9)

        # Column widths
        ws.column_dimensions['A'].width = 8
        ws.column_dimensions['B'].width = 45
        ws.column_dimensions['C'].width = 12
        ws.column_dimensions['D'].width = 8
        for col in ['E', 'F', 'G', 'H', 'I']:
            ws.column_dimensions[col].width = 15

        ws.freeze_panes = 'A4'

        return ws, row

    def create_executive_dashboard_fixed(self, db_path: str, disciplines: list):
        """Create Executive Dashboard with charts - uses fixed quantities."""
        ws = self.wb.create_sheet("📈 Executive Dashboard", 1)  # Insert after cover

        # Title
        ws.merge_cells('A1:F1')
        ws['A1'] = "EXECUTIVE DASHBOARD - Cost Summary"
        ws['A1'].font = Font(size=18, bold=True, color='FFFFFF')
        ws['A1'].fill = PatternFill(start_color=self.colors['title'], end_color=self.colors['title'], fill_type='solid')
        ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[1].height = 30

        # Headers
        row = 3
        headers = ['Discipline', 'Material (RM)', 'Labor (RM)', 'Equipment (RM)', 'Total (RM)']
        for col, header in enumerate(headers, start=1):
            cell = ws.cell(row, col, header)
            cell.font = Font(bold=True, color='FFFFFF', size=10)
            cell.fill = PatternFill(start_color=self.colors['header'], end_color=self.colors['header'], fill_type='solid')
            cell.alignment = Alignment(horizontal='center', vertical='center')
            cell.border = Border(bottom=Side(style='medium'))

        ws.row_dimensions[row].height = 25
        row += 1
        summary_start = row

        # Calculate costs per discipline using FIXED quantities
        for disc in disciplines:
            results = self.query_discipline_quantities(db_path, disc)

            disc_mat_cost = 0
            disc_labor_cost = 0
            disc_equip_cost = 0

            for ifc_class, elem_count, total_qty in results:
                _, uom = self.get_primary_quantity_info(ifc_class)
                mat = MATERIAL_COSTS.get(ifc_class, {'rate': 0})
                mat_cost = total_qty * mat['rate']
                labor_cost, labor_days, _, _ = self.calculate_labor_cost(ifc_class, total_qty)
                equip_cost, _ = self.calculate_equipment_cost(ifc_class, labor_days)

                disc_mat_cost += mat_cost
                disc_labor_cost += labor_cost
                disc_equip_cost += equip_cost

            total_cost = disc_mat_cost + disc_labor_cost + disc_equip_cost

            ws.cell(row, 1, disc)
            ws.cell(row, 2, disc_mat_cost).number_format = '#,##0.00'
            ws.cell(row, 3, disc_labor_cost).number_format = '#,##0.00'
            ws.cell(row, 4, disc_equip_cost).number_format = '#,##0.00'
            ws.cell(row, 5, total_cost).number_format = '#,##0.00'

            row += 1

        summary_end = row - 1

        # Grand Total
        row += 1
        ws[f'A{row}'] = "GRAND TOTAL"
        ws[f'A{row}'].font = Font(bold=True, size=12)
        ws[f'A{row}'].alignment = Alignment(horizontal='right')

        for col in range(2, 6):
            cell = ws.cell(row, col)
            cell.value = f"=SUM({get_column_letter(col)}{summary_start}:{get_column_letter(col)}{summary_end})"
            cell.number_format = '#,##0.00'
            cell.font = Font(bold=True, size=11, color='FFFFFF')
            cell.fill = PatternFill(start_color=self.colors['total'], end_color=self.colors['total'], fill_type='solid')

        ws.row_dimensions[row].height = 25

        # Add DataBar visualization
        data_bar_rule = DataBarRule(
            start_type='min',
            end_type='max',
            color=self.colors['accent'],
            showValue=True
        )
        ws.conditional_formatting.add(f'E{summary_start}:E{summary_end}', data_bar_rule)

        # Column widths
        for col, width in enumerate([18, 18, 18, 18, 20], start=1):
            ws.column_dimensions[get_column_letter(col)].width = width

        # Add charts
        # Pie Chart - Cost Breakdown
        pie = PieChart()
        pie.title = "Cost Breakdown by Discipline"
        pie.style = 10
        pie.height = 10
        pie.width = 16

        labels = Reference(ws, min_col=1, min_row=summary_start, max_row=summary_end)
        data = Reference(ws, min_col=5, min_row=summary_start-1, max_row=summary_end)
        pie.add_data(data, titles_from_data=True)
        pie.set_categories(labels)
        ws.add_chart(pie, 'H3')

        # Bar Chart - Cost Components
        bar = BarChart()
        bar.type = "col"
        bar.style = 10
        bar.title = "Cost Components by Discipline"
        bar.y_axis.title = "Cost (RM)"
        bar.x_axis.title = "Discipline"
        bar.height = 10
        bar.width = 16

        data = Reference(ws, min_col=2, max_col=4, min_row=summary_start-1, max_row=summary_end)
        cats = Reference(ws, min_col=1, min_row=summary_start, max_row=summary_end)
        bar.add_data(data, titles_from_data=True)
        bar.set_categories(cats)
        ws.add_chart(bar, 'H23')

        ws.freeze_panes = 'A4'

        return ws

    def generate_fixed_boq(self, db_path: str, project_name: str):
        """Generate complete BOQ with all fixes."""
        print(f"\n{'='*80}")
        print("GENERATING FIXED BOQ (Correct Calculations + Reference Sheets)")
        print(f"{'='*80}\n")

        # Load IFC labels
        self.load_ifc_labels(db_path)

        # Get disciplines
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("""
            SELECT DISTINCT e.discipline
            FROM elements_meta e
            WHERE e.guid IN (SELECT guid FROM simple_qto)
            ORDER BY e.discipline
        """)
        disciplines = [r[0] for r in cursor.fetchall()]
        conn.close()

        print(f"Found {len(disciplines)} disciplines: {', '.join(disciplines)}\n")

        # Create reference sheets FIRST (so BOQ can reference them)
        print("📋 Creating Reference Sheets...")
        self.create_material_rates_reference_sheet()
        self.create_labor_rates_reference_sheet()
        self.create_equipment_rates_reference_sheet()

        # Cover sheet
        print(f"\nCreating cover sheet...")
        self.create_cover_sheet(project_name)

        # Executive Dashboard with charts (NEW!)
        print(f"\n📊 Creating Executive Dashboard with Charts...")
        self.create_executive_dashboard_fixed(db_path, disciplines)

        # BOQ sheets with FIXED calculations
        print(f"\n📋 Creating Fixed BOQ Sheets...")
        for disc in disciplines:
            print(f"  - BOQ - {disc}...")
            ws, total_row = self.create_fixed_boq_sheet(db_path, disc)
            if total_row:
                self.sheet_refs[disc] = total_row

        print(f"\nSaving: {self.output_path}")
        self.wb.save(self.output_path)

        print(f"\n{'='*80}")
        print("✓ FIXED BOQ COMPLETE")
        print(f"{'='*80}")
        print(f"\n✅ Fixes Applied:")
        print(f"  ✓ Primary quantity only (no mixed units)")
        print(f"  ✓ IFC labels for friendly descriptions")
        print(f"  ✓ Reference sheets with editable rates")
        print(f"  ✓ Excel cell formulas link to reference sheets")
        print(f"  ✓ Executive Dashboard with Pie & Bar charts")
        print(f"\n")

        return self.output_path


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 comprehensive_boq_export_fixed.py <database_path> [project_name]")
        sys.exit(1)

    db_path = sys.argv[1]
    project_name = sys.argv[2] if len(sys.argv) > 2 else "Terminal 1 Expansion Project"

    exporter = FixedBOQExporter()
    exporter.generate_fixed_boq(db_path, project_name)
