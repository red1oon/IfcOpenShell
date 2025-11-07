"""
Resolution System Database Schema
==================================

Database tables for Intelligent Clash Adjustment system.

Key Principle: Optimize for DESIGN EFFORT (person-hours × rates), not construction cost.
During design coordination, we're minimizing design fees and schedule delays.

Part of: Intelligent Clash Adjustment POC
"""

import sqlite3
from typing import Optional
from datetime import datetime


class ResolutionDatabase:
    """
    Manages database schema for resolution analysis system.
    """

    def __init__(self, db_path: str):
        """
        Initialize resolution database.

        Args:
            db_path: Path to clash_status.db (extends existing database)
        """
        self.db_path = db_path

    def verify_schema(self) -> bool:
        """
        Verify that required database tables exist.

        Returns:
            True if schema is valid, False otherwise

        Note:
            Database schema should be initialized manually using:
            sqlite3 database.db < Scripts/initialize_clash_database.sql
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        required_tables = [
            'clash_status',
            'clash_groups',
            'clash_group_members',
            'resolution_options',
            'design_effort_estimates',
            'discipline_rates'
        ]

        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = {row[0] for row in cursor.fetchall()}

            missing_tables = set(required_tables) - existing_tables

            if missing_tables:
                print(f"❌ Missing database tables: {', '.join(missing_tables)}")
                print(f"   Please run: sqlite3 {self.db_path} < Scripts/initialize_clash_database.sql")
                return False

            # Verify clash_status has correct schema (clash_id, not id)
            cursor.execute("PRAGMA table_info(clash_status)")
            columns = {row[1] for row in cursor.fetchall()}

            required_columns = {'clash_id', 'discipline_a', 'discipline_b'}
            if not required_columns.issubset(columns):
                print(f"❌ clash_status table has outdated schema")
                print(f"   Missing columns: {required_columns - columns}")
                print(f"   Please reinitialize: sqlite3 {self.db_path} < Scripts/initialize_clash_database.sql")
                return False

            return True

        finally:
            conn.close()

    def create_schema(self) -> None:
        """
        Create resolution system tables in clash database.

        Tables created:
        - resolution_options: Resolution alternatives for clashes/groups
        - design_effort_estimates: Design effort by discipline
        - discipline_rates: Billing rates by discipline
        - resolution_history: Track chosen options and actual outcomes
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # ========================================
        # Resolution Options
        # ========================================
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS resolution_options (
                option_id TEXT PRIMARY KEY,
                clash_id TEXT,  -- FK to clash_status.clash_id
                group_id TEXT,  -- FK to clash_groups.group_id (NULL if single clash)

                -- Option metadata
                option_type TEXT NOT NULL,  -- 'reroute_duct', 'lower_beam', 'coordinate_multi_discipline', etc
                description TEXT NOT NULL,
                recommendation_rank INTEGER,  -- 1 = recommended, 2 = alternative, etc

                -- Design effort (PRIMARY optimization target)
                total_design_hours REAL NOT NULL,
                total_design_cost REAL NOT NULL,  -- design_hours × rates

                -- Schedule impact (SECONDARY optimization target)
                calendar_days_required REAL NOT NULL,
                schedule_delay_cost REAL,  -- days × project_burn_rate

                -- Construction cost (CONSTRAINT, not optimization target)
                estimated_construction_cost REAL,
                exceeds_budget BOOLEAN DEFAULT 0,

                -- Technical feasibility
                technically_feasible BOOLEAN DEFAULT 1,
                feasibility_notes TEXT,

                -- Risk assessment
                risk_score INTEGER,  -- 0-100
                risk_category TEXT,  -- 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'
                risk_factors TEXT,  -- JSON: list of risk factor names

                -- Impact summary
                affected_disciplines TEXT,  -- JSON: ['ARC', 'STR', 'MEP']
                clashes_resolved INTEGER,  -- How many clashes does this fix

                -- Metadata
                generated_date TIMESTAMP NOT NULL,
                generated_by TEXT,

                FOREIGN KEY (clash_id) REFERENCES clash_status(clash_id),
                FOREIGN KEY (group_id) REFERENCES clash_groups(group_id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_resolution_clash ON resolution_options(clash_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_resolution_group ON resolution_options(group_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_resolution_rank ON resolution_options(recommendation_rank)
        """)

        # ========================================
        # Design Effort Estimates
        # ========================================
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS design_effort_estimates (
                effort_id TEXT PRIMARY KEY,
                option_id TEXT NOT NULL,

                -- Discipline and activity
                discipline TEXT NOT NULL,  -- 'ARCHITECTURE', 'STRUCTURE', 'MEP', etc
                activity_type TEXT NOT NULL,  -- 'modeling', 'documentation', 'calculation', 'review', 'approval', 'coordination'

                -- Effort quantification
                estimated_hours REAL NOT NULL,
                skill_level TEXT NOT NULL,  -- 'senior', 'intermediate', 'junior', 'drafter'
                hourly_rate REAL NOT NULL,
                total_cost REAL NOT NULL,  -- hours × rate

                -- Schedule
                calendar_days_required REAL,
                can_parallel BOOLEAN DEFAULT 0,  -- Can run simultaneously with other activities
                prerequisite_efforts TEXT,  -- JSON: array of effort_ids that must complete first

                -- Documentation impact
                drawing_sheets_affected INTEGER DEFAULT 0,
                specification_sections_affected INTEGER DEFAULT 0,

                -- Approval requirements
                requires_approval BOOLEAN DEFAULT 0,
                approval_authority TEXT,  -- 'structural_engineer', 'owner', 'architect'
                typical_approval_days REAL,
                approval_rejection_risk REAL,  -- 0.0 to 1.0 probability

                -- Metadata
                confidence_level TEXT,  -- 'low', 'medium', 'high'
                basis_of_estimate TEXT,
                notes TEXT,

                FOREIGN KEY (option_id) REFERENCES resolution_options(option_id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_effort_option ON design_effort_estimates(option_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_effort_discipline ON design_effort_estimates(discipline)
        """)

        # ========================================
        # Discipline Rates
        # ========================================
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS discipline_rates (
                rate_id INTEGER PRIMARY KEY AUTOINCREMENT,
                discipline TEXT NOT NULL,
                skill_level TEXT NOT NULL,

                -- Billing rate
                hourly_rate REAL NOT NULL,  -- Fully burdened (salary + benefits + overhead + profit)

                -- Productivity factors
                modeling_productivity REAL,  -- Elements per hour
                documentation_productivity REAL,  -- Sheet updates per hour
                coordination_overhead_factor REAL DEFAULT 1.15,  -- Multiplier for meetings, rework

                -- Availability
                typical_response_time_days REAL,

                -- Metadata
                effective_date DATE NOT NULL,
                source TEXT,  -- 'project_contract', 'company_standard', 'market_survey'
                region TEXT DEFAULT 'US',
                notes TEXT,

                UNIQUE(discipline, skill_level, effective_date)
            )
        """)

        # ========================================
        # Resolution History (Learning System)
        # ========================================
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS resolution_history (
                history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                option_id TEXT NOT NULL,

                -- Decision
                selected_date TIMESTAMP NOT NULL,
                selected_by TEXT,
                selection_reason TEXT,

                -- Actual outcomes (for learning)
                actual_design_hours REAL,
                actual_design_cost REAL,
                actual_calendar_days REAL,
                actual_construction_cost REAL,

                -- Variance analysis
                design_hours_variance REAL,  -- actual - estimated
                design_cost_variance REAL,
                schedule_variance REAL,

                -- Success metrics
                successfully_resolved BOOLEAN,
                required_rework BOOLEAN DEFAULT 0,
                user_satisfaction_rating INTEGER,  -- 1-5 scale

                -- Lessons learned
                what_went_well TEXT,
                what_went_wrong TEXT,
                lessons_learned TEXT,

                FOREIGN KEY (option_id) REFERENCES resolution_options(option_id)
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_option ON resolution_history(option_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_history_date ON resolution_history(selected_date)
        """)

        conn.commit()
        conn.close()

        print("✓ Resolution database schema created successfully")

    def insert_default_discipline_rates(self) -> None:
        """
        Insert default discipline rates based on US market averages.

        These are starting values - users should calibrate to their project/region.
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        today = datetime.now().date().isoformat()

        default_rates = [
            # Architecture
            ('ARCHITECTURE', 'senior', 175.0, 2.0, 0.4, 1.2, 2.0, 'market_survey', 'US_average'),
            ('ARCHITECTURE', 'intermediate', 135.0, 3.0, 0.5, 1.15, 1.5, 'market_survey', 'US_average'),
            ('ARCHITECTURE', 'junior', 95.0, 4.0, 0.6, 1.1, 1.0, 'market_survey', 'US_average'),
            ('ARCHITECTURE', 'drafter', 75.0, 5.0, 0.7, 1.0, 0.5, 'market_survey', 'US_average'),

            # Structure
            ('STRUCTURE', 'senior', 195.0, 1.5, 0.3, 1.25, 3.0, 'market_survey', 'US_average'),
            ('STRUCTURE', 'intermediate', 165.0, 2.5, 0.4, 1.2, 2.0, 'market_survey', 'US_average'),
            ('STRUCTURE', 'junior', 125.0, 3.5, 0.5, 1.15, 1.5, 'market_survey', 'US_average'),

            # MEP (generic)
            ('MEP', 'senior', 155.0, 2.0, 0.4, 1.2, 2.0, 'market_survey', 'US_average'),
            ('MEP', 'intermediate', 125.0, 3.0, 0.5, 1.15, 1.5, 'market_survey', 'US_average'),
            ('MEP', 'junior', 95.0, 4.0, 0.6, 1.1, 1.0, 'market_survey', 'US_average'),

            # Electrical
            ('ELECTRICAL', 'senior', 150.0, 2.5, 0.4, 1.2, 2.0, 'market_survey', 'US_average'),
            ('ELECTRICAL', 'intermediate', 120.0, 3.5, 0.5, 1.15, 1.5, 'market_survey', 'US_average'),
            ('ELECTRICAL', 'junior', 90.0, 4.5, 0.6, 1.1, 1.0, 'market_survey', 'US_average'),

            # ACMV
            ('ACMV', 'senior', 160.0, 2.0, 0.4, 1.2, 2.0, 'market_survey', 'US_average'),
            ('ACMV', 'intermediate', 130.0, 3.0, 0.5, 1.15, 1.5, 'market_survey', 'US_average'),
            ('ACMV', 'junior', 100.0, 4.0, 0.6, 1.1, 1.0, 'market_survey', 'US_average'),
        ]

        for (discipline, skill, rate, model_prod, doc_prod, coord_overhead,
             response_days, source, region) in default_rates:
            try:
                cursor.execute("""
                    INSERT INTO discipline_rates (
                        discipline, skill_level, hourly_rate,
                        modeling_productivity, documentation_productivity,
                        coordination_overhead_factor, typical_response_time_days,
                        effective_date, source, region,
                        notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    discipline, skill, rate,
                    model_prod, doc_prod, coord_overhead, response_days,
                    today, source, region,
                    'Default rates - calibrate to your project'
                ))
            except sqlite3.IntegrityError:
                # Already exists
                pass

        conn.commit()
        conn.close()

        print("✓ Default discipline rates inserted")

    def initialize_database(self) -> None:
        """
        Convenience method: Create schema and insert defaults.
        """
        self.create_schema()
        self.insert_default_discipline_rates()
        print("✓ Resolution database initialized")


def initialize_resolution_system(db_path: str) -> None:
    """
    Initialize the resolution system database schema and defaults.

    Args:
        db_path: Path to clash_status.db
    """
    db = ResolutionDatabase(db_path)
    db.initialize_database()


# ============================================================================
# Phase 1.5: Configuration System - 3-Tier Lookup Functions
# ============================================================================

def get_activity_duration(db_path: str, activity_type: str, ifc_class: str = None,
                          discipline: str = None, project_id: str = None) -> dict:
    """
    3-tier lookup: Learned → Project → Default

    Priority:
    1. Learned value for this project + class + discipline (highest confidence)
    2. Project-specific override (manual configuration)
    3. Default for class + discipline
    4. Default for activity type only (most generic)

    Args:
        db_path: Path to database
        activity_type: 'modeling', 'verification', 'documentation', 'coordination'
        ifc_class: Optional IFC class (e.g., 'IfcDuctSegment')
        discipline: Optional discipline (e.g., 'MEP')
        project_id: Optional project ID for project-specific overrides

    Returns:
        dict with keys: 'base_hours', 'complexity_multiplier', 'source', 'confidence_score'
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Priority 1: Learned value for this project + class + discipline
    if project_id and ifc_class and discipline:
        cursor.execute("""
            SELECT base_hours, complexity_multiplier, confidence_score, source, sample_size
            FROM activity_base_durations
            WHERE activity_type = ? AND ifc_class = ? AND discipline = ?
              AND project_id = ? AND source = 'learned'
            ORDER BY confidence_score DESC, last_updated DESC
            LIMIT 1
        """, (activity_type, ifc_class, discipline, project_id))

        row = cursor.fetchone()
        if row:
            conn.close()
            return dict(row)

    # Priority 2: Project-specific override (class + discipline)
    if project_id and ifc_class and discipline:
        cursor.execute("""
            SELECT base_hours, complexity_multiplier, confidence_score, source, sample_size
            FROM activity_base_durations
            WHERE activity_type = ? AND ifc_class = ? AND discipline = ?
              AND project_id = ? AND source = 'project'
            LIMIT 1
        """, (activity_type, ifc_class, discipline, project_id))

        row = cursor.fetchone()
        if row:
            conn.close()
            return dict(row)

    # Priority 3: Default for class + discipline (no project filter)
    if ifc_class and discipline:
        cursor.execute("""
            SELECT base_hours, complexity_multiplier, confidence_score, source, sample_size
            FROM activity_base_durations
            WHERE activity_type = ? AND ifc_class = ? AND discipline = ?
              AND source = 'default' AND project_id IS NULL
            LIMIT 1
        """, (activity_type, ifc_class, discipline))

        row = cursor.fetchone()
        if row:
            conn.close()
            return dict(row)

    # Priority 4: Default for activity type only (most generic)
    cursor.execute("""
        SELECT base_hours, complexity_multiplier, confidence_score, source, sample_size
        FROM activity_base_durations
        WHERE activity_type = ? AND ifc_class IS NULL AND discipline IS NULL
          AND source = 'default' AND project_id IS NULL
        LIMIT 1
    """, (activity_type,))

    row = cursor.fetchone()
    conn.close()

    if row:
        return dict(row)
    else:
        # Absolute fallback (shouldn't happen if defaults loaded)
        return {
            'base_hours': 2.0,
            'complexity_multiplier': 0.10,
            'confidence_score': 0,
            'source': 'hardcoded_fallback',
            'sample_size': 0
        }


def get_discipline_rate(db_path: str, discipline: str, skill_level: str = 'intermediate') -> float:
    """
    Get hourly rate from active preset.

    Args:
        db_path: Path to database
        discipline: Discipline code (e.g., 'MEP', 'ARCHITECTURE')
        skill_level: 'senior', 'intermediate', 'junior'

    Returns:
        Hourly rate (float)
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT pdr.hourly_rate
        FROM preset_discipline_rates pdr
        JOIN configuration_presets cp ON pdr.preset_id = cp.id
        WHERE cp.is_active = 1
          AND pdr.discipline = ?
          AND pdr.skill_level = ?
    """, (discipline, skill_level))

    row = cursor.fetchone()
    conn.close()

    return row[0] if row else 125.0  # Fallback rate


def get_active_preset(db_path: str) -> Optional[dict]:
    """
    Get currently active configuration preset.

    Returns:
        dict with 'id', 'preset_name', 'currency', or None
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, preset_name, description, currency
        FROM configuration_presets
        WHERE is_active = 1
        LIMIT 1
    """)

    row = cursor.fetchone()
    conn.close()

    return dict(row) if row else None


def set_active_preset(db_path: str, preset_name: str) -> bool:
    """
    Change active configuration preset.

    Args:
        db_path: Path to database
        preset_name: Name of preset to activate

    Returns:
        True if successful, False if preset not found
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if preset exists
    cursor.execute("SELECT id FROM configuration_presets WHERE preset_name = ?", (preset_name,))
    if not cursor.fetchone():
        conn.close()
        return False

    # Deactivate all presets
    cursor.execute("UPDATE configuration_presets SET is_active = 0")

    # Activate selected preset
    cursor.execute("UPDATE configuration_presets SET is_active = 1 WHERE preset_name = ?", (preset_name,))

    conn.commit()
    conn.close()

    return True


def get_all_presets(db_path: str) -> list:
    """
    Get list of all available configuration presets.

    Returns:
        List of dicts with 'preset_name', 'description', 'currency', 'is_active'
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT preset_name, description, currency, is_active
        FROM configuration_presets
        ORDER BY preset_name
    """)

    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


if __name__ == "__main__":
    """
    Initialize resolution database for Terminal 1
    """
    import sys

    db_path = "/home/red1/Documents/bonsai/DatabaseFiles/clash_status.db"

    if len(sys.argv) > 1:
        db_path = sys.argv[1]

    print("=" * 60)
    print("INITIALIZING RESOLUTION SYSTEM DATABASE")
    print("=" * 60)

    initialize_resolution_system(db_path)

    print("\nDatabase schema ready for Intelligent Clash Adjustment POC")
