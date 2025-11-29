"""
Database Schema for 4D Construction Scheduling
-----------------------------------------------
SQL schema definitions for construction_schedule table.
"""

import sqlite3
from pathlib import Path


CONSTRUCTION_SCHEDULE_SCHEMA = """
CREATE TABLE IF NOT EXISTS construction_schedule (
    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
    wbs_code TEXT NOT NULL,              -- Work Breakdown Structure code (e.g., '1.2.1.1')
    task_name TEXT NOT NULL,             -- Task description (e.g., 'Install Grid A-D Columns')
    element_guid TEXT,                   -- Link to elements_meta (NULL for summary tasks)
    ifc_class TEXT,                      -- IFC class type
    discipline TEXT,                     -- Discipline (ARC, STR, ELEC, etc.)
    storey TEXT,                         -- Building storey/level
    phase TEXT,                          -- Construction phase (Substructure, Superstructure, etc.)
    sequence INTEGER,                    -- Sequence number (1, 2, 3...)

    -- Duration calculation
    quantity REAL,                       -- From QTO (e.g., 250m, 100m², 50 EA)
    uom TEXT,                            -- Unit of measure (M, M2, M3, EA)
    productivity_rate REAL,              -- From labor productivity (e.g., 8 m/day)
    duration_days REAL,                  -- Calculated: quantity / productivity

    -- Dates
    start_date TEXT,                     -- ISO 8601: '2025-01-06'
    finish_date TEXT,                    -- ISO 8601: '2025-01-10'

    -- Dependencies (stored as JSON array)
    predecessors TEXT,                   -- JSON: '[{"task_id": 5, "type": "FS", "lag": 0}]'

    -- Resources
    labor_resource TEXT,                 -- Labor trade (e.g., 'STEEL_ERECTOR')
    labor_crew_size INTEGER,             -- Number of workers
    equipment_resource TEXT,             -- Equipment type (e.g., 'MOBILE_CRANE_20T')

    -- Status (for progress tracking)
    status TEXT DEFAULT 'Not Started',   -- 'Not Started', 'In Progress', 'Complete'
    percent_complete REAL DEFAULT 0.0,   -- 0.0 to 100.0

    -- Critical path analysis
    early_start TEXT,                    -- Early start date
    early_finish TEXT,                   -- Early finish date
    late_start TEXT,                     -- Late start date
    late_finish TEXT,                    -- Late finish date
    total_float_days REAL,               -- Total float (slack)
    is_critical BOOLEAN DEFAULT 0,       -- 1 if on critical path

    FOREIGN KEY (element_guid) REFERENCES elements_meta(guid)
);

CREATE INDEX IF NOT EXISTS idx_schedule_phase ON construction_schedule(phase);
CREATE INDEX IF NOT EXISTS idx_schedule_discipline ON construction_schedule(discipline);
CREATE INDEX IF NOT EXISTS idx_schedule_storey ON construction_schedule(storey);
CREATE INDEX IF NOT EXISTS idx_schedule_sequence ON construction_schedule(sequence);
CREATE INDEX IF NOT EXISTS idx_schedule_dates ON construction_schedule(start_date, finish_date);
CREATE INDEX IF NOT EXISTS idx_schedule_critical ON construction_schedule(is_critical);
"""


def initialize_schedule_schema(db_path: str) -> bool:
    """
    Initialize construction_schedule table in federation database.

    Args:
        db_path: Path to federation database

    Returns:
        True if schema created/exists successfully
    """
    if not Path(db_path).exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Execute schema creation
        cursor.executescript(CONSTRUCTION_SCHEDULE_SCHEMA)

        conn.commit()
        conn.close()

        print(f"✓ Construction schedule schema initialized in: {db_path}")
        return True

    except sqlite3.Error as e:
        print(f"✗ Error initializing schedule schema: {e}")
        return False


def check_schedule_table_exists(db_path: str) -> bool:
    """Check if construction_schedule table exists in database."""
    if not Path(db_path).exists():
        return False

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='construction_schedule'"
        )
        exists = cursor.fetchone() is not None
        conn.close()
        return exists
    except:
        return False


def get_schedule_task_count(db_path: str) -> int:
    """Get number of tasks in construction_schedule table."""
    if not check_schedule_table_exists(db_path):
        return 0

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("SELECT COUNT(*) FROM construction_schedule")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except:
        return 0


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python database_schema.py <database_path>")
        print("Example: python database_schema.py ~/Documents/bonsai/Terminal1_ARC_STR.db")
        sys.exit(1)

    db_path = sys.argv[1]
    initialize_schedule_schema(db_path)
