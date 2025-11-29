"""
MS Project (MPP) XML Exporter
------------------------------
Exports construction_schedule table to Microsoft Project XML format.

Compatible with:
- Microsoft Project 2010+
- Primavera P6 (via import)
- ProjectLibre (open source)
- Asta Powerproject
"""

import sqlite3
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List


# MS Project XML namespace
MS_PROJECT_NS = "http://schemas.microsoft.com/project"


def prettify_xml(elem):
    """Return a pretty-printed XML string."""
    rough_string = ET.tostring(elem, encoding='unicode')
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ")


def export_to_mpp_xml(
    db_path: str,
    output_path: str = None,
    project_name: str = "Terminal 1 Construction"
) -> str:
    """
    Export construction_schedule table to MS Project XML format.

    Args:
        db_path: Path to federation database with construction_schedule table
        output_path: Output XML file path (auto-generated if None)
        project_name: Project name for MPP file

    Returns:
        Path to generated XML file
    """
    if not Path(db_path).exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    # Auto-generate output path if not provided
    if not output_path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = f"Terminal1_Schedule_{timestamp}.xml"

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
    print(f"MS PROJECT XML EXPORT")
    print(f"{'='*80}")
    print(f"Database: {Path(db_path).name}")
    print(f"Tasks: {len(tasks)}")
    print(f"Output: {output_path}")
    print(f"{'='*80}\n")

    # Build XML structure
    root = ET.Element("Project", xmlns=MS_PROJECT_NS)

    # Project properties
    ET.SubElement(root, "Name").text = project_name
    ET.SubElement(root, "Title").text = project_name
    ET.SubElement(root, "CreationDate").text = datetime.now().isoformat()
    ET.SubElement(root, "LastSaved").text = datetime.now().isoformat()
    ET.SubElement(root, "ScheduleFromStart").text = "1"  # Schedule from start date
    ET.SubElement(root, "StartDate").text = tasks[0][9]  # First task start date
    ET.SubElement(root, "CurrencySymbol").text = "RM"
    ET.SubElement(root, "DefaultTaskType").text = "1"  # Fixed duration

    # Calendar (Malaysian construction: Mon-Sat)
    calendars = ET.SubElement(root, "Calendars")
    calendar = ET.SubElement(calendars, "Calendar")
    ET.SubElement(calendar, "UID").text = "1"
    ET.SubElement(calendar, "Name").text = "Standard"
    ET.SubElement(calendar, "IsBaseCalendar").text = "1"

    # Working days (Mon-Sat = 1-6, Sun = 7)
    weekdays = ET.SubElement(calendar, "WeekDays")
    for day in range(1, 8):  # 1=Sunday, 2=Monday, ..., 7=Saturday
        weekday = ET.SubElement(weekdays, "WeekDay")
        ET.SubElement(weekday, "DayType").text = str(day)
        if day == 1:  # Sunday = non-working
            ET.SubElement(weekday, "DayWorking").text = "0"
        else:  # Mon-Sat = working
            ET.SubElement(weekday, "DayWorking").text = "1"
            # Working time: 07:00-17:00 (10 hours, 8 productive)
            working_times = ET.SubElement(weekday, "WorkingTimes")
            working_time = ET.SubElement(working_times, "WorkingTime")
            ET.SubElement(working_time, "FromTime").text = "07:00:00"
            ET.SubElement(working_time, "ToTime").text = "17:00:00"

    # Tasks
    tasks_elem = ET.SubElement(root, "Tasks")

    # Add summary task (project root)
    summary_task = ET.SubElement(tasks_elem, "Task")
    ET.SubElement(summary_task, "UID").text = "0"
    ET.SubElement(summary_task, "ID").text = "0"
    ET.SubElement(summary_task, "Name").text = project_name
    ET.SubElement(summary_task, "Type").text = "1"  # Fixed duration
    ET.SubElement(summary_task, "IsNull").text = "0"
    ET.SubElement(summary_task, "CreateDate").text = datetime.now().isoformat()
    ET.SubElement(summary_task, "WBS").text = "0"
    ET.SubElement(summary_task, "OutlineLevel").text = "0"
    ET.SubElement(summary_task, "Priority").text = "500"
    ET.SubElement(summary_task, "Start").text = tasks[0][9] + "T07:00:00"
    ET.SubElement(summary_task, "Finish").text = tasks[-1][10] + "T17:00:00"

    # Calculate total project duration
    start_dt = datetime.fromisoformat(tasks[0][9])
    finish_dt = datetime.fromisoformat(tasks[-1][10])
    total_days = (finish_dt - start_dt).days + 1
    total_hours = int(total_days * 8)
    ET.SubElement(summary_task, "Duration").text = f"PT{total_hours}H0M0S"
    ET.SubElement(summary_task, "ManualDuration").text = "PT0H0M0S"

    # Resource tracking
    resources_map = {}  # {resource_name: resource_uid}
    next_resource_uid = 1

    # Add tasks
    for idx, task_row in enumerate(tasks, start=1):
        (task_id, wbs_code, task_name, phase, sequence,
         quantity, uom, productivity, duration_days,
         start_date, finish_date,
         labor_resource, labor_crew_size, equipment_resource,
         status, percent_complete,
         discipline, storey) = task_row

        task_elem = ET.SubElement(tasks_elem, "Task")
        ET.SubElement(task_elem, "UID").text = str(task_id)
        ET.SubElement(task_elem, "ID").text = str(idx)
        ET.SubElement(task_elem, "Name").text = task_name
        ET.SubElement(task_elem, "Type").text = "1"  # Fixed duration
        ET.SubElement(task_elem, "IsNull").text = "0"
        ET.SubElement(task_elem, "CreateDate").text = datetime.now().isoformat()
        ET.SubElement(task_elem, "WBS").text = wbs_code
        ET.SubElement(task_elem, "OutlineLevel").text = "1"
        ET.SubElement(task_elem, "Priority").text = "500"

        # Dates (convert to MS Project datetime format)
        start_dt = datetime.fromisoformat(start_date)
        finish_dt = datetime.fromisoformat(finish_date)
        ET.SubElement(task_elem, "Start").text = start_dt.strftime("%Y-%m-%dT07:00:00")
        ET.SubElement(task_elem, "Finish").text = finish_dt.strftime("%Y-%m-%dT17:00:00")

        # Duration (convert days to PT format: PT40H0M0S = 5 days × 8 hours)
        duration_hours = int(duration_days * 8)
        ET.SubElement(task_elem, "Duration").text = f"PT{duration_hours}H0M0S"
        ET.SubElement(task_elem, "ManualDuration").text = f"PT{duration_hours}H0M0S"

        # Status
        ET.SubElement(task_elem, "PercentComplete").text = str(int(percent_complete))
        ET.SubElement(task_elem, "PercentWorkComplete").text = str(int(percent_complete))

        # Custom fields (phase, discipline, storey)
        ET.SubElement(task_elem, "Text1").text = phase  # Custom field: Phase
        ET.SubElement(task_elem, "Text2").text = discipline  # Custom field: Discipline
        ET.SubElement(task_elem, "Text3").text = storey  # Custom field: Storey

        # Track resources
        if labor_resource and labor_resource not in resources_map:
            resources_map[labor_resource] = next_resource_uid
            next_resource_uid += 1
        if equipment_resource and equipment_resource not in resources_map:
            resources_map[equipment_resource] = next_resource_uid
            next_resource_uid += 1

        print(f"  [{wbs_code}] {task_name} | {duration_days:.1f} days")

    # Resources
    resources_elem = ET.SubElement(root, "Resources")
    for resource_name, resource_uid in resources_map.items():
        resource_elem = ET.SubElement(resources_elem, "Resource")
        ET.SubElement(resource_elem, "UID").text = str(resource_uid)
        ET.SubElement(resource_elem, "ID").text = str(resource_uid)
        ET.SubElement(resource_elem, "Name").text = resource_name
        ET.SubElement(resource_elem, "Type").text = "1"  # Work resource
        ET.SubElement(resource_elem, "IsNull").text = "0"

    # Assignments (optional - can enhance later)
    assignments_elem = ET.SubElement(root, "Assignments")

    # Write XML to file (use ElementTree's built-in pretty print)
    ET.indent(root, space="  ")  # Pretty print with 2-space indent
    tree = ET.ElementTree(root)
    tree.write(output_path, encoding='utf-8', xml_declaration=True)

    print(f"\n{'='*80}")
    print(f"✓ MS Project XML exported successfully!")
    print(f"  File: {output_path}")
    print(f"  Tasks: {len(tasks)}")
    print(f"  Resources: {len(resources_map)}")
    print(f"{'='*80}\n")
    print(f"Import this file into:")
    print(f"  • Microsoft Project (File → Open)")
    print(f"  • ProjectLibre (File → Open)")
    print(f"  • Primavera P6 (File → Import → MS Project XML)")
    print(f"{'='*80}\n")

    return output_path


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python mpp_export.py <database_path> [output_xml_path] [project_name]")
        print("Example: python mpp_export.py ~/Documents/bonsai/Terminal1_ARC_STR.db")
        sys.exit(1)

    db_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    project_name = sys.argv[3] if len(sys.argv) > 3 else "Terminal 1 Construction"

    export_to_mpp_xml(db_path, output_path, project_name)
