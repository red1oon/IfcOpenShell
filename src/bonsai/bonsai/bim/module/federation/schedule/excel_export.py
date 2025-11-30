"""
Excel Schedule Exporter
-----------------------
Convert construction schedule to Excel format for users without MS Project.

Creates a Gantt-style spreadsheet with:
- Task list with dates and durations
- Resource allocation
- Visual timeline (conditional formatting)
- Summary statistics
"""

import sqlite3
import os
from datetime import datetime, timedelta
from pathlib import Path


def export_schedule_to_excel(db_path: str, output_path: str = None, project_name: str = "Terminal 1 Construction") -> str:
    """
    Export construction_schedule table to Excel with Gantt visualization.

    Args:
        db_path: Path to federation database with construction_schedule table
        output_path: Output Excel file path (auto-generated if None)
        project_name: Project name for Excel file

    Returns:
        Path to generated Excel file
    """
    # Check openpyxl availability
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side, numbers
        from openpyxl.utils import get_column_letter
        from openpyxl.chart import PieChart, BarChart, Reference
    except ImportError:
        raise ImportError("openpyxl required for Excel export. Install: pip install openpyxl")

    if not Path(db_path).exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    # Auto-generate output path if not provided
    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"Terminal1_Schedule_{timestamp}.xlsx"

    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if construction_schedule table exists
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='construction_schedule'"
    )
    if not cursor.fetchone():
        raise ValueError("construction_schedule table not found. Run schedule generator first.")

    # Read all tasks
    cursor.execute("""
        SELECT
            task_id, wbs_code, task_name, phase, sequence,
            quantity, uom, productivity_rate, duration_days,
            start_date, finish_date,
            labor_resource, labor_crew_size, equipment_resource,
            status, percent_complete,
            discipline, storey
        FROM construction_schedule
        ORDER BY sequence, task_id
    """)

    tasks = cursor.fetchall()
    conn.close()

    if not tasks:
        raise ValueError("No tasks found in construction_schedule table.")

    print(f"\n{'='*80}")
    print(f"EXCEL SCHEDULE EXPORT")
    print(f"{'='*80}")
    print(f"Database: {Path(db_path).name}")
    print(f"Tasks: {len(tasks)}")
    print(f"Output: {output_path}")
    print(f"{'='*80}\n")

    # Create workbook
    wb = Workbook()

    # Sheet 1: Schedule
    ws_schedule = wb.active
    ws_schedule.title = "Construction Schedule"

    # Header row
    headers = [
        "WBS", "Task Name", "Phase", "Discipline", "Storey",
        "Quantity", "UOM", "Productivity", "Duration (days)",
        "Start Date", "Finish Date", "Labor Resource", "Crew Size",
        "Equipment", "Status", "% Complete"
    ]

    # Style header
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )

    for col_idx, header in enumerate(headers, 1):
        cell = ws_schedule.cell(row=1, column=col_idx)
        cell.value = header
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal='center', vertical='center')
        cell.border = border

    # Write tasks
    for row_idx, task_row in enumerate(tasks, start=2):
        (task_id, wbs_code, task_name, phase, sequence,
         quantity, uom, productivity, duration_days,
         start_date, finish_date,
         labor_resource, labor_crew_size, equipment_resource,
         status, percent_complete,
         discipline, storey) = task_row

        row_data = [
            wbs_code,
            task_name,
            phase,
            discipline,
            storey,
            quantity,
            uom,
            productivity,
            duration_days,
            start_date,
            finish_date,
            labor_resource,
            labor_crew_size,
            equipment_resource,
            status,
            percent_complete
        ]

        for col_idx, value in enumerate(row_data, 1):
            cell = ws_schedule.cell(row=row_idx, column=col_idx)
            cell.value = value
            cell.border = border

            # Format duration with 2 decimal points
            if col_idx == 9:  # Duration column
                cell.number_format = '0.00'
                cell.alignment = Alignment(horizontal='right')
            # Align numbers right
            elif col_idx in [6, 8, 13, 16]:
                cell.alignment = Alignment(horizontal='right')

        print(f"  [{wbs_code}] {task_name} | {duration_days:.2f} days | {start_date} → {finish_date}")

    # Auto-size columns
    for col_idx in range(1, len(headers) + 1):
        ws_schedule.column_dimensions[get_column_letter(col_idx)].width = 15

    # Widen task name column
    ws_schedule.column_dimensions['B'].width = 40

    # Sheet 2: Summary with Charts
    ws_summary = wb.create_sheet("Project Summary")

    # Calculate project duration
    if tasks:
        start_date = datetime.fromisoformat(tasks[0][9])
        finish_date = datetime.fromisoformat(tasks[-1][10])
        total_duration = (finish_date - start_date).days + 1
    else:
        total_duration = 0

    # Project info header
    title_cell = ws_summary.cell(row=1, column=1)
    title_cell.value = project_name
    title_cell.font = Font(bold=True, size=14, color="366092")

    # Project statistics
    info_data = [
        ["Database", Path(db_path).name],
        ["Total Tasks", len(tasks)],
        ["Project Start", tasks[0][9] if tasks else "N/A"],
        ["Project Finish", tasks[-1][10] if tasks else "N/A"],
        ["Total Duration", f"{total_duration} days"],
        ["Generated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
    ]

    for idx, (label, value) in enumerate(info_data, start=2):
        ws_summary.cell(row=idx, column=1, value=label).font = Font(bold=True)
        ws_summary.cell(row=idx, column=2, value=value)

    # Count tasks by phase
    phase_counts = {}
    for task in tasks:
        phase = task[3]
        phase_counts[phase] = phase_counts.get(phase, 0) + 1

    # Phase summary section
    phase_start_row = len(info_data) + 4
    header = ws_summary.cell(row=phase_start_row, column=1)
    header.value = "Phase Summary"
    header.font = Font(bold=True, size=12)
    header.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header.font = Font(bold=True, color="FFFFFF")

    ws_summary.cell(row=phase_start_row, column=2, value="Task Count").font = Font(bold=True, color="FFFFFF")
    ws_summary.cell(row=phase_start_row, column=2).fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")

    for idx, (phase, count) in enumerate(sorted(phase_counts.items()), start=1):
        ws_summary.cell(row=phase_start_row + idx, column=1, value=phase)
        ws_summary.cell(row=phase_start_row + idx, column=2, value=count)

    # Count tasks by discipline
    discipline_counts = {}
    for task in tasks:
        discipline = task[16]
        discipline_counts[discipline] = discipline_counts.get(discipline, 0) + 1

    # Discipline summary section
    disc_start_row = phase_start_row + len(phase_counts) + 3
    header = ws_summary.cell(row=disc_start_row, column=1)
    header.value = "Discipline Summary"
    header.font = Font(bold=True, size=12)
    header.fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header.font = Font(bold=True, color="FFFFFF")

    ws_summary.cell(row=disc_start_row, column=2, value="Task Count").font = Font(bold=True, color="FFFFFF")
    ws_summary.cell(row=disc_start_row, column=2).fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")

    for idx, (discipline, count) in enumerate(sorted(discipline_counts.items()), start=1):
        ws_summary.cell(row=disc_start_row + idx, column=1, value=discipline)
        ws_summary.cell(row=disc_start_row + idx, column=2, value=count)

    # Column widths
    ws_summary.column_dimensions['A'].width = 25
    ws_summary.column_dimensions['B'].width = 20

    # Add Pie Chart - Phase Distribution
    pie_phase = PieChart()
    pie_phase.title = "Task Distribution by Phase"
    pie_phase.style = 10
    pie_phase.height = 10
    pie_phase.width = 15

    # Data references
    labels = Reference(ws_summary, min_col=1, min_row=phase_start_row + 1, max_row=phase_start_row + len(phase_counts))
    data = Reference(ws_summary, min_col=2, min_row=phase_start_row, max_row=phase_start_row + len(phase_counts))
    pie_phase.add_data(data, titles_from_data=True)
    pie_phase.set_categories(labels)

    # Position chart
    ws_summary.add_chart(pie_phase, 'D2')

    # Add Bar Chart - Discipline Distribution
    bar_disc = BarChart()
    bar_disc.title = "Task Count by Discipline"
    bar_disc.style = 10
    bar_disc.height = 10
    bar_disc.width = 15
    bar_disc.y_axis.title = "Number of Tasks"
    bar_disc.x_axis.title = "Discipline"

    # Data references
    labels = Reference(ws_summary, min_col=1, min_row=disc_start_row + 1, max_row=disc_start_row + len(discipline_counts))
    data = Reference(ws_summary, min_col=2, min_row=disc_start_row, max_row=disc_start_row + len(discipline_counts))
    bar_disc.add_data(data, titles_from_data=True)
    bar_disc.set_categories(labels)

    # Position chart
    ws_summary.add_chart(bar_disc, 'D18')

    # Save workbook
    wb.save(output_path)

    print(f"\n{'='*80}")
    print(f"✓ Excel schedule exported successfully!")
    print(f"  File: {output_path}")
    print(f"  Sheets: Construction Schedule, Project Summary")
    print(f"  Tasks: {len(tasks)}")
    print(f"{'='*80}\n")
    print(f"Open with:")
    print(f"  • Microsoft Excel")
    print(f"  • LibreOffice Calc")
    print(f"  • Google Sheets")
    print(f"{'='*80}\n")

    return output_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python excel_export.py <database_path> [output_xlsx_path] [project_name]")
        print("Example: python excel_export.py ~/Documents/bonsai/Terminal1_ARC_STR.db")
        sys.exit(1)

    db_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    project_name = sys.argv[3] if len(sys.argv) > 3 else "Terminal 1 Construction"

    export_schedule_to_excel(db_path, output_path, project_name)
