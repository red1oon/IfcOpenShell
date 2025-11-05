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
