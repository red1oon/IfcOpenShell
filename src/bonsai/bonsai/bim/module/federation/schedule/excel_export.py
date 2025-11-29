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
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
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

            # Align numbers right
            if col_idx in [6, 8, 9, 13, 16]:
                cell.alignment = Alignment(horizontal='right')

        print(f"  [{wbs_code}] {task_name} | {duration_days:.1f} days | {start_date} → {finish_date}")

    # Auto-size columns
    for col_idx in range(1, len(headers) + 1):
        ws_schedule.column_dimensions[get_column_letter(col_idx)].width = 15

    # Widen task name column
    ws_schedule.column_dimensions['B'].width = 40

    # Sheet 2: Summary
    ws_summary = wb.create_sheet("Project Summary")

    # Project info
    summary_data = [
        ["Project Name", project_name],
        ["Database", Path(db_path).name],
        ["Total Tasks", len(tasks)],
        ["Project Start", tasks[0][9] if tasks else "N/A"],
        ["Project Finish", tasks[-1][10] if tasks else "N/A"],
        ["Generated", datetime.now().strftime("%Y-%m-%d %H:%M:%S")],
        [],
        ["Phase Summary", "Task Count"],
    ]

    # Count tasks by phase
    phase_counts = {}
    for task in tasks:
        phase = task[3]
        phase_counts[phase] = phase_counts.get(phase, 0) + 1

    for phase, count in sorted(phase_counts.items()):
        summary_data.append([phase, count])

    summary_data.extend([
        [],
        ["Discipline Summary", "Task Count"],
    ])

    # Count tasks by discipline
    discipline_counts = {}
    for task in tasks:
        discipline = task[16]
        discipline_counts[discipline] = discipline_counts.get(discipline, 0) + 1

    for discipline, count in sorted(discipline_counts.items()):
        summary_data.append([discipline, count])

    # Write summary
    for row_idx, row_data in enumerate(summary_data, 1):
        for col_idx, value in enumerate(row_data, 1):
            cell = ws_summary.cell(row=row_idx, column=col_idx)
            cell.value = value

            # Style headers
            if row_idx in [1, 8, 8 + len(phase_counts) + 2]:
                cell.font = Font(bold=True)

    ws_summary.column_dimensions['A'].width = 25
    ws_summary.column_dimensions['B'].width = 20

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
