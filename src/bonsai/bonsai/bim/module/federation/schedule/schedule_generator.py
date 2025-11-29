"""
4D Construction Schedule Generator
-----------------------------------
Generates construction schedules from federation database using productivity rates.

Uses labor productivity data from comprehensive_boq_export.py to calculate task durations.
"""

import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Tuple, Optional

# Import labor productivity data from BOQ module
import sys
boq_path = Path(__file__).parent.parent / "boq"
sys.path.insert(0, str(boq_path))

try:
    from comprehensive_boq_export import LABOR_RATES, EQUIPMENT_ALLOCATION
except ImportError:
    try:
        from bonsai.bim.module.federation.boq.comprehensive_boq_export import LABOR_RATES, EQUIPMENT_ALLOCATION
    except ImportError:
        print("⚠ Warning: Could not import BOQ productivity data. Using defaults.")
        LABOR_RATES = {}
        EQUIPMENT_ALLOCATION = {}


# Construction sequence rules (precedence relationships)
CONSTRUCTION_SEQUENCE_RULES = {
    # Structural sequence (bottom-up by storey)
    'IfcFooting': {'phase': 'Substructure', 'sequence': 1, 'predecessors': [], 'resource': 'CONCRETE_GANG'},
    'IfcColumn': {'phase': 'Superstructure', 'sequence': 2, 'predecessors': ['IfcFooting'], 'resource': 'STEEL_ERECTOR'},
    'IfcBeam': {'phase': 'Superstructure', 'sequence': 3, 'predecessors': ['IfcColumn'], 'resource': 'STEEL_ERECTOR'},
    'IfcSlab': {'phase': 'Superstructure', 'sequence': 4, 'predecessors': ['IfcBeam'], 'resource': 'CONCRETE_GANG'},

    # MEP rough-in (after structure complete)
    'IfcDuct': {'phase': 'MEP Rough-in', 'sequence': 5, 'predecessors': ['IfcSlab'], 'resource': 'HVAC_TECH'},
    'IfcDuctSegment': {'phase': 'MEP Rough-in', 'sequence': 5, 'predecessors': ['IfcSlab'], 'resource': 'HVAC_TECH'},
    'IfcDuctFitting': {'phase': 'MEP Rough-in', 'sequence': 5, 'predecessors': ['IfcSlab'], 'resource': 'HVAC_TECH'},
    'IfcPipe': {'phase': 'MEP Rough-in', 'sequence': 5, 'predecessors': ['IfcSlab'], 'resource': 'PLUMBER'},
    'IfcPipeSegment': {'phase': 'MEP Rough-in', 'sequence': 5, 'predecessors': ['IfcSlab'], 'resource': 'PLUMBER'},
    'IfcPipeFitting': {'phase': 'MEP Rough-in', 'sequence': 5, 'predecessors': ['IfcSlab'], 'resource': 'PLUMBER'},
    'IfcCableCarrier': {'phase': 'MEP Rough-in', 'sequence': 5, 'predecessors': ['IfcSlab'], 'resource': 'ELECTRICIAN'},
    'IfcCableCarrierSegment': {'phase': 'MEP Rough-in', 'sequence': 5, 'predecessors': ['IfcSlab'], 'resource': 'ELECTRICIAN'},

    # Architecture (after rough-in)
    'IfcWall': {'phase': 'Architecture', 'sequence': 6, 'predecessors': ['IfcDuct', 'IfcPipe'], 'resource': 'MASON'},
    'IfcWallStandardCase': {'phase': 'Architecture', 'sequence': 6, 'predecessors': ['IfcDuct', 'IfcPipe'], 'resource': 'MASON'},
    'IfcDoor': {'phase': 'Architecture', 'sequence': 7, 'predecessors': ['IfcWall'], 'resource': 'CARPENTER'},
    'IfcWindow': {'phase': 'Architecture', 'sequence': 7, 'predecessors': ['IfcWall'], 'resource': 'CARPENTER'},
    'IfcStairFlight': {'phase': 'Architecture', 'sequence': 7, 'predecessors': ['IfcSlab'], 'resource': 'CARPENTER'},
    'IfcRoof': {'phase': 'Architecture', 'sequence': 8, 'predecessors': ['IfcWall'], 'resource': 'ROOFER'},

    # MEP final fix
    'IfcLightFixture': {'phase': 'MEP Final', 'sequence': 9, 'predecessors': ['IfcWall'], 'resource': 'ELECTRICIAN'},
    'IfcOutlet': {'phase': 'MEP Final', 'sequence': 9, 'predecessors': ['IfcWall'], 'resource': 'ELECTRICIAN'},
    'IfcElectricAppliance': {'phase': 'MEP Final', 'sequence': 9, 'predecessors': ['IfcWall'], 'resource': 'ELECTRICIAN'},
    'IfcFlowTerminal': {'phase': 'MEP Final', 'sequence': 9, 'predecessors': ['IfcDuct'], 'resource': 'HVAC_TECH'},

    # Finishes (last)
    'IfcCovering': {'phase': 'Finishes', 'sequence': 10, 'predecessors': ['IfcLightFixture'], 'resource': 'FINISHER'},
    'IfcFurniture': {'phase': 'Finishes', 'sequence': 11, 'predecessors': ['IfcCovering'], 'resource': 'FINISHER'},
}


# Default productivity rates (fallback if not in BOQ data)
DEFAULT_PRODUCTIVITY = {
    'IfcColumn': 6.0,  # m/day
    'IfcBeam': 8.0,    # m/day
    'IfcSlab': 35.0,   # m²/day
    'IfcWall': 12.0,   # m²/day
    'IfcDoor': 5.0,    # EA/day
    'IfcWindow': 5.0,  # EA/day
    'IfcDuct': 18.0,   # m/day
    'IfcPipe': 25.0,   # m/day
    'IfcCableCarrier': 30.0,  # m/day
    'IfcLightFixture': 20.0,  # EA/day
    'IfcOutlet': 25.0,  # EA/day
    'IfcFurniture': 8.0,  # EA/day
    'IfcStairFlight': 2.0,  # EA/day
    'IfcRoof': 25.0,   # m²/day
}


# Project calendar (Malaysian construction industry standard)
PROJECT_CALENDAR = {
    'working_days': [0, 1, 2, 3, 4, 5],  # Mon-Sat (0=Monday in Python)
    'non_working_days': [6],  # Sunday
    'hours_per_day': 8,  # Productive hours
}


def get_productivity_rate(ifc_class: str) -> float:
    """
    Get productivity rate for an IFC class from BOQ data or defaults.

    Returns:
        Units per day (m/day, m²/day, or EA/day depending on element type)
    """
    # Try to get from BOQ labor rates
    for resource_name, resource_data in LABOR_RATES.items():
        productivity = resource_data.get('productivity', {})
        if ifc_class in productivity:
            return productivity[ifc_class]

    # Fallback to defaults
    return DEFAULT_PRODUCTIVITY.get(ifc_class, 10.0)  # 10 units/day as last resort


def calculate_working_days(start_date: datetime, duration_days: float) -> datetime:
    """
    Calculate finish date accounting for non-working days.

    Args:
        start_date: Start date
        duration_days: Duration in working days

    Returns:
        Finish date (datetime)
    """
    current_date = start_date
    remaining_days = duration_days

    while remaining_days > 0:
        # Check if current day is a working day
        if current_date.weekday() in PROJECT_CALENDAR['working_days']:
            remaining_days -= 1
        current_date += timedelta(days=1)

    return current_date


def generate_construction_schedule(
    db_path: str,
    project_start_date: str = '2025-01-06',
    project_name: str = 'Terminal 1 Construction'
) -> int:
    """
    Generate construction schedule from federation database.

    Algorithm:
    1. Read elements from elements_meta (group by storey, discipline, IFC class)
    2. Calculate quantities (count for EA, use transforms for M/M²)
    3. Calculate durations using productivity rates
    4. Apply construction sequence rules
    5. Calculate dates based on predecessors
    6. Insert into construction_schedule table

    Args:
        db_path: Path to federation database
        project_start_date: Project start date (ISO 8601)
        project_name: Project name for summary task

    Returns:
        Number of tasks created
    """
    if not Path(db_path).exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    # Ensure schema exists
    try:
        from .database_schema import initialize_schedule_schema
    except ImportError:
        # Running as script, not as module
        from database_schema import initialize_schedule_schema
    initialize_schedule_schema(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Clear existing schedule
    cursor.execute("DELETE FROM construction_schedule")

    # Parse start date
    start_date = datetime.fromisoformat(project_start_date)

    # Task ID counter
    task_id_map = {}  # {(ifc_class, storey): task_id}
    next_task_id = 1

    # 1. Get elements grouped by (storey, discipline, ifc_class)
    cursor.execute("""
        SELECT
            COALESCE(storey, 'Unknown') as storey,
            discipline,
            ifc_class,
            COUNT(*) as element_count
        FROM elements_meta
        WHERE ifc_class IS NOT NULL
        GROUP BY storey, discipline, ifc_class
        ORDER BY storey, ifc_class
    """)

    activities = cursor.fetchall()

    print(f"\n{'='*80}")
    print(f"4D CONSTRUCTION SCHEDULE GENERATION")
    print(f"{'='*80}")
    print(f"Project: {project_name}")
    print(f"Start Date: {project_start_date}")
    print(f"Database: {Path(db_path).name}")
    print(f"Activities found: {len(activities)}")
    print(f"{'='*80}\n")

    # 2. Create tasks for each activity group
    tasks_created = 0
    for storey, discipline, ifc_class, element_count in activities:
        # Get sequence rules
        rules = CONSTRUCTION_SEQUENCE_RULES.get(ifc_class, {
            'phase': 'Unknown',
            'sequence': 99,
            'predecessors': [],
            'resource': None
        })

        phase = rules['phase']
        sequence = rules['sequence']
        resource = rules['resource']

        # Calculate quantity and duration
        quantity = element_count  # For COUNT elements (EA)
        productivity = get_productivity_rate(ifc_class)
        duration_days = max(1.0, quantity / productivity)  # Minimum 1 day

        # Get crew size
        crew_size = 2  # Default
        if resource and resource in LABOR_RATES:
            crew_size = LABOR_RATES[resource].get('crew_size', 2)

        # Get equipment
        equipment = None
        if ifc_class in EQUIPMENT_ALLOCATION:
            equipment = EQUIPMENT_ALLOCATION[ifc_class].get('equipment')

        # Calculate start/finish dates (simple sequential for now)
        # TODO: Implement proper critical path scheduling
        task_start = start_date + timedelta(days=sequence * 5)  # Rough offset by sequence
        task_finish = calculate_working_days(task_start, duration_days)

        # Build task name
        task_name = f"{storey} - Install {ifc_class.replace('Ifc', '')} ({discipline})"

        # Build WBS code
        wbs_code = f"1.{sequence}.{tasks_created}"

        # Build predecessors JSON
        predecessors_json = json.dumps([])  # Empty for now - will enhance later

        # Insert task
        cursor.execute("""
            INSERT INTO construction_schedule (
                wbs_code, task_name, ifc_class, discipline, storey,
                phase, sequence,
                quantity, uom, productivity_rate, duration_days,
                start_date, finish_date,
                predecessors,
                labor_resource, labor_crew_size, equipment_resource,
                status, percent_complete
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            wbs_code, task_name, ifc_class, discipline, storey,
            phase, sequence,
            quantity, 'EA', productivity, duration_days,
            task_start.isoformat(), task_finish.isoformat(),
            predecessors_json,
            resource, crew_size, equipment,
            'Not Started', 0.0
        ))

        # Store task ID for predecessor lookups
        task_id_map[(ifc_class, storey)] = cursor.lastrowid
        tasks_created += 1

        # Print task
        print(f"  [{wbs_code}] {task_name}")
        print(f"    Quantity: {element_count} EA | Duration: {duration_days:.1f} days | {task_start.date()} → {task_finish.date()}")
        print(f"    Resource: {resource} (crew: {crew_size}) | Equipment: {equipment or 'None'}")
        print()

    conn.commit()
    conn.close()

    print(f"\n{'='*80}")
    print(f"✓ Schedule generated successfully!")
    print(f"  Total tasks created: {tasks_created}")
    print(f"  Database: {db_path}")
    print(f"{'='*80}\n")

    return tasks_created


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python schedule_generator.py <database_path> [start_date] [project_name]")
        print("Example: python schedule_generator.py ~/Documents/bonsai/Terminal1_ARC_STR.db 2025-01-06")
        sys.exit(1)

    db_path = sys.argv[1]
    start_date = sys.argv[2] if len(sys.argv) > 2 else '2025-01-06'
    project_name = sys.argv[3] if len(sys.argv) > 3 else 'Terminal 1 Construction'

    generate_construction_schedule(db_path, start_date, project_name)
