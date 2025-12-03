#!/usr/bin/env python3
"""
Database Migration Script - Complete Federation Schema
=======================================================

Upgrades any federation database to the full schema supporting all features
up to Digital Twin IoT (7D BIM).

Features covered:
1. Core Federation (GI schema: base_geometries, element_instances, elements_meta, element_transforms)
2. Clash Detection (clash_status, clash_history, clash_groups, clash_group_members)
3. Resolution System (resolution_options, design_effort_estimates, discipline_rates, resolution_history)
4. 4D Scheduling (construction_schedule)
5. 6D Asset Management (assets, asset_properties, asset_documents, asset_history)
6. 6D Maintenance (pm_templates, work_orders, maintenance_log, technicians, pm_schedule_state)
7. 7D IoT Integration (sensors, sensor_readings, alert_rules, alerts)

Usage:
    python migrate_database_to_full_schema.py <database_path>

Example:
    python migrate_database_to_full_schema.py ~/WORK_DIR/databases/enhanced_federation_GI.db
"""

import sqlite3
import sys
from pathlib import Path
from datetime import datetime


class DatabaseMigrator:
    """Migrate federation database to full schema"""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {db_path}")

        self.conn = sqlite3.connect(str(self.db_path))
        self.cursor = self.conn.cursor()

    def get_existing_tables(self) -> set:
        """Get list of existing tables"""
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        return {row[0] for row in self.cursor.fetchall()}

    def create_clash_tables(self):
        """Create clash detection tables"""
        print("\n📊 Clash Detection Tables...")

        # Clash status (may already exist)
        self.cursor.executescript("""
            CREATE TABLE IF NOT EXISTS clash_status (
                clash_id TEXT PRIMARY KEY,
                guid_a TEXT NOT NULL,
                guid_b TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'NEW',
                assigned_to TEXT,
                comment TEXT,
                date_created TIMESTAMP NOT NULL,
                date_modified TIMESTAMP NOT NULL,
                is_ignored BOOLEAN DEFAULT 0,
                distance REAL,
                ifc_class_a TEXT,
                ifc_class_b TEXT,
                discipline_a TEXT,
                discipline_b TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_status ON clash_status(status);
            CREATE INDEX IF NOT EXISTS idx_guid_a ON clash_status(guid_a);
            CREATE INDEX IF NOT EXISTS idx_guid_b ON clash_status(guid_b);
            CREATE INDEX IF NOT EXISTS idx_date_created ON clash_status(date_created);

            CREATE TABLE IF NOT EXISTS clash_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                clash_id TEXT NOT NULL,
                old_status TEXT,
                new_status TEXT,
                changed_by TEXT,
                change_date TIMESTAMP NOT NULL,
                comment TEXT,
                FOREIGN KEY (clash_id) REFERENCES clash_status(clash_id)
            );

            CREATE INDEX IF NOT EXISTS idx_history_clash ON clash_history(clash_id);
            CREATE INDEX IF NOT EXISTS idx_history_date ON clash_history(change_date);

            CREATE TABLE IF NOT EXISTS clash_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT UNIQUE NOT NULL,
                cascade_element_guid TEXT NOT NULL,
                cascade_element_class TEXT,
                cascade_element_discipline TEXT,
                total_clashes INTEGER NOT NULL,
                affected_disciplines TEXT,
                affected_classes TEXT,
                status_summary TEXT,
                severity TEXT NOT NULL,
                date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                date_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS clash_group_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT NOT NULL,
                clash_id TEXT NOT NULL,
                FOREIGN KEY (group_id) REFERENCES clash_groups(group_id),
                FOREIGN KEY (clash_id) REFERENCES clash_status(clash_id),
                UNIQUE(group_id, clash_id)
            );
        """)
        print("  ✓ clash_status, clash_history, clash_groups, clash_group_members")

    def create_resolution_tables(self):
        """Create intelligent resolution system tables"""
        print("\n🧠 Resolution System Tables...")

        self.cursor.executescript("""
            CREATE TABLE IF NOT EXISTS resolution_options (
                option_id TEXT PRIMARY KEY,
                clash_id TEXT,
                group_id TEXT,
                option_type TEXT NOT NULL,
                description TEXT NOT NULL,
                recommendation_rank INTEGER,
                total_design_hours REAL NOT NULL,
                total_design_cost REAL NOT NULL,
                calendar_days_required REAL NOT NULL,
                schedule_delay_cost REAL,
                estimated_construction_cost REAL,
                exceeds_budget BOOLEAN DEFAULT 0,
                technically_feasible BOOLEAN DEFAULT 1,
                feasibility_notes TEXT,
                risk_score INTEGER,
                risk_category TEXT,
                risk_factors TEXT,
                affected_disciplines TEXT,
                clashes_resolved INTEGER,
                generated_date TIMESTAMP NOT NULL,
                generated_by TEXT,
                FOREIGN KEY (clash_id) REFERENCES clash_status(clash_id),
                FOREIGN KEY (group_id) REFERENCES clash_groups(group_id)
            );

            CREATE INDEX IF NOT EXISTS idx_resolution_clash ON resolution_options(clash_id);
            CREATE INDEX IF NOT EXISTS idx_resolution_group ON resolution_options(group_id);
            CREATE INDEX IF NOT EXISTS idx_resolution_rank ON resolution_options(recommendation_rank);

            CREATE TABLE IF NOT EXISTS design_effort_estimates (
                effort_id TEXT PRIMARY KEY,
                option_id TEXT NOT NULL,
                discipline TEXT NOT NULL,
                activity_type TEXT NOT NULL,
                estimated_hours REAL NOT NULL,
                skill_level TEXT NOT NULL,
                hourly_rate REAL NOT NULL,
                total_cost REAL NOT NULL,
                calendar_days_required REAL,
                can_parallel BOOLEAN DEFAULT 0,
                prerequisite_efforts TEXT,
                drawing_sheets_affected INTEGER DEFAULT 0,
                specification_sections_affected INTEGER DEFAULT 0,
                requires_approval BOOLEAN DEFAULT 0,
                approval_authority TEXT,
                typical_approval_days REAL,
                approval_rejection_risk REAL,
                confidence_level TEXT,
                basis_of_estimate TEXT,
                notes TEXT,
                FOREIGN KEY (option_id) REFERENCES resolution_options(option_id)
            );

            CREATE INDEX IF NOT EXISTS idx_effort_option ON design_effort_estimates(option_id);
            CREATE INDEX IF NOT EXISTS idx_effort_discipline ON design_effort_estimates(discipline);

            CREATE TABLE IF NOT EXISTS discipline_rates (
                rate_id INTEGER PRIMARY KEY AUTOINCREMENT,
                discipline TEXT NOT NULL,
                skill_level TEXT NOT NULL,
                hourly_rate REAL NOT NULL,
                modeling_productivity REAL,
                documentation_productivity REAL,
                coordination_overhead_factor REAL DEFAULT 1.15,
                typical_response_time_days REAL,
                effective_date DATE NOT NULL,
                source TEXT,
                region TEXT DEFAULT 'US',
                notes TEXT,
                UNIQUE(discipline, skill_level, effective_date)
            );

            CREATE TABLE IF NOT EXISTS resolution_history (
                history_id INTEGER PRIMARY KEY AUTOINCREMENT,
                option_id TEXT NOT NULL,
                selected_date TIMESTAMP NOT NULL,
                selected_by TEXT,
                selection_reason TEXT,
                actual_design_hours REAL,
                actual_design_cost REAL,
                actual_calendar_days REAL,
                actual_construction_cost REAL,
                design_hours_variance REAL,
                design_cost_variance REAL,
                schedule_variance REAL,
                successfully_resolved BOOLEAN,
                required_rework BOOLEAN DEFAULT 0,
                user_satisfaction_rating INTEGER,
                what_went_well TEXT,
                what_went_wrong TEXT,
                lessons_learned TEXT,
                FOREIGN KEY (option_id) REFERENCES resolution_options(option_id)
            );

            CREATE INDEX IF NOT EXISTS idx_history_option ON resolution_history(option_id);
            CREATE INDEX IF NOT EXISTS idx_history_date ON resolution_history(selected_date);
        """)
        print("  ✓ resolution_options, design_effort_estimates, discipline_rates, resolution_history")

    def create_schedule_tables(self):
        """Create 4D scheduling tables"""
        print("\n📅 4D Scheduling Tables...")

        self.cursor.executescript("""
            CREATE TABLE IF NOT EXISTS construction_schedule (
                task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                wbs_code TEXT NOT NULL,
                task_name TEXT NOT NULL,
                element_guid TEXT,
                ifc_class TEXT,
                discipline TEXT,
                storey TEXT,
                phase TEXT,
                sequence INTEGER,
                quantity REAL,
                uom TEXT,
                productivity_rate REAL,
                duration_days REAL,
                start_date TEXT,
                finish_date TEXT,
                predecessors TEXT,
                labor_resource TEXT,
                labor_crew_size INTEGER,
                equipment_resource TEXT,
                status TEXT DEFAULT 'Not Started',
                percent_complete REAL DEFAULT 0.0,
                early_start TEXT,
                early_finish TEXT,
                late_start TEXT,
                late_finish TEXT,
                total_float_days REAL,
                is_critical BOOLEAN DEFAULT 0,
                FOREIGN KEY (element_guid) REFERENCES elements_meta(guid)
            );

            CREATE INDEX IF NOT EXISTS idx_schedule_phase ON construction_schedule(phase);
            CREATE INDEX IF NOT EXISTS idx_schedule_discipline ON construction_schedule(discipline);
            CREATE INDEX IF NOT EXISTS idx_schedule_storey ON construction_schedule(storey);
            CREATE INDEX IF NOT EXISTS idx_schedule_sequence ON construction_schedule(sequence);
            CREATE INDEX IF NOT EXISTS idx_schedule_dates ON construction_schedule(start_date, finish_date);
            CREATE INDEX IF NOT EXISTS idx_schedule_critical ON construction_schedule(is_critical);
        """)
        print("  ✓ construction_schedule")

    def create_asset_tables(self):
        """Create 6D asset management tables"""
        print("\n🏗️  6D Asset Management Tables...")

        self.cursor.executescript("""
            CREATE TABLE IF NOT EXISTS assets (
                guid TEXT PRIMARY KEY,
                federation_element_id INTEGER,
                asset_tag TEXT UNIQUE,
                name TEXT NOT NULL,
                ifc_class TEXT NOT NULL,
                ifc_type TEXT,
                discipline TEXT,
                storey TEXT,
                space TEXT,
                manufacturer TEXT,
                model TEXT,
                serial_number TEXT,
                capacity TEXT,
                install_date DATE,
                warranty_start DATE,
                warranty_duration_months INTEGER,
                expected_lifespan_years INTEGER,
                replacement_cost REAL,
                status TEXT DEFAULT 'Active',
                condition TEXT DEFAULT 'Good',
                vendor_name TEXT,
                vendor_contact TEXT,
                vendor_contract_number TEXT,
                notes TEXT,
                created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_date TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (federation_element_id) REFERENCES elements_meta(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_assets_guid ON assets(guid);
            CREATE INDEX IF NOT EXISTS idx_assets_federation_element ON assets(federation_element_id);
            CREATE INDEX IF NOT EXISTS idx_assets_ifc_class ON assets(ifc_class);
            CREATE INDEX IF NOT EXISTS idx_assets_discipline ON assets(discipline);
            CREATE INDEX IF NOT EXISTS idx_assets_storey ON assets(storey);
            CREATE INDEX IF NOT EXISTS idx_assets_status ON assets(status);
            CREATE INDEX IF NOT EXISTS idx_assets_warranty_end ON assets(warranty_start, warranty_duration_months);

            CREATE TABLE IF NOT EXISTS asset_properties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_guid TEXT NOT NULL,
                property_name TEXT NOT NULL,
                property_value TEXT,
                property_type TEXT DEFAULT 'string',
                created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (asset_guid) REFERENCES assets(guid) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_asset_props_guid ON asset_properties(asset_guid);
            CREATE INDEX IF NOT EXISTS idx_asset_props_name ON asset_properties(property_name);

            CREATE TABLE IF NOT EXISTS asset_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_guid TEXT NOT NULL,
                document_type TEXT NOT NULL,
                file_name TEXT NOT NULL,
                file_path TEXT NOT NULL,
                file_size_kb INTEGER,
                mime_type TEXT,
                description TEXT,
                uploaded_by TEXT,
                uploaded_date TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (asset_guid) REFERENCES assets(guid) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_asset_docs_guid ON asset_documents(asset_guid);
            CREATE INDEX IF NOT EXISTS idx_asset_docs_type ON asset_documents(document_type);

            CREATE TABLE IF NOT EXISTS asset_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_guid TEXT NOT NULL,
                change_type TEXT NOT NULL,
                field_name TEXT,
                old_value TEXT,
                new_value TEXT,
                changed_by TEXT,
                changed_date TEXT DEFAULT CURRENT_TIMESTAMP,
                notes TEXT,
                FOREIGN KEY (asset_guid) REFERENCES assets(guid) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_asset_history_guid ON asset_history(asset_guid);
            CREATE INDEX IF NOT EXISTS idx_asset_history_date ON asset_history(changed_date);
        """)
        print("  ✓ assets, asset_properties, asset_documents, asset_history")

    def create_maintenance_tables(self):
        """Create 6D maintenance tables"""
        print("\n🔧 6D Maintenance Tables...")

        self.cursor.executescript("""
            CREATE TABLE IF NOT EXISTS pm_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                template_name TEXT NOT NULL UNIQUE,
                ifc_class TEXT,
                discipline TEXT,
                description TEXT,
                interval_type TEXT NOT NULL,
                interval_value INTEGER DEFAULT 1,
                estimated_hours REAL,
                required_skills TEXT,
                tasks TEXT NOT NULL,
                parts_list TEXT,
                created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            );

            CREATE INDEX IF NOT EXISTS idx_pm_templates_class ON pm_templates(ifc_class);
            CREATE INDEX IF NOT EXISTS idx_pm_templates_discipline ON pm_templates(discipline);
            CREATE INDEX IF NOT EXISTS idx_pm_templates_active ON pm_templates(is_active);

            CREATE TABLE IF NOT EXISTS work_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_order_number TEXT UNIQUE NOT NULL,
                asset_guid TEXT NOT NULL,
                work_type TEXT NOT NULL,
                priority TEXT DEFAULT 'Medium',
                title TEXT NOT NULL,
                description TEXT,
                pm_template_id INTEGER,
                scheduled_date DATE,
                due_date DATE,
                estimated_hours REAL,
                assigned_to TEXT,
                team TEXT,
                status TEXT DEFAULT 'Open',
                completion_date DATE,
                actual_hours REAL,
                labor_cost REAL,
                parts_cost REAL,
                total_cost REAL,
                created_by TEXT,
                created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_date TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (asset_guid) REFERENCES assets(guid) ON DELETE CASCADE,
                FOREIGN KEY (pm_template_id) REFERENCES pm_templates(id)
            );

            CREATE INDEX IF NOT EXISTS idx_wo_asset ON work_orders(asset_guid);
            CREATE INDEX IF NOT EXISTS idx_wo_status ON work_orders(status);
            CREATE INDEX IF NOT EXISTS idx_wo_due_date ON work_orders(due_date);
            CREATE INDEX IF NOT EXISTS idx_wo_assigned ON work_orders(assigned_to);
            CREATE INDEX IF NOT EXISTS idx_wo_type ON work_orders(work_type);
            CREATE INDEX IF NOT EXISTS idx_wo_priority ON work_orders(priority);

            CREATE TABLE IF NOT EXISTS maintenance_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_order_id INTEGER NOT NULL,
                asset_guid TEXT NOT NULL,
                work_performed TEXT NOT NULL,
                findings TEXT,
                corrective_actions TEXT,
                parts_used TEXT,
                technician TEXT NOT NULL,
                work_date DATE NOT NULL,
                hours_worked REAL,
                follow_up_required BOOLEAN DEFAULT 0,
                follow_up_notes TEXT,
                logged_by TEXT,
                logged_date TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (work_order_id) REFERENCES work_orders(id) ON DELETE CASCADE,
                FOREIGN KEY (asset_guid) REFERENCES assets(guid) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_maint_log_asset ON maintenance_log(asset_guid);
            CREATE INDEX IF NOT EXISTS idx_maint_log_date ON maintenance_log(work_date);
            CREATE INDEX IF NOT EXISTS idx_maint_log_wo ON maintenance_log(work_order_id);

            CREATE TABLE IF NOT EXISTS technicians (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                employee_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                email TEXT,
                phone TEXT,
                skills TEXT,
                certifications TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_date TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_technicians_active ON technicians(is_active);
            CREATE INDEX IF NOT EXISTS idx_technicians_employee_id ON technicians(employee_id);

            CREATE TABLE IF NOT EXISTS pm_schedule_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_guid TEXT NOT NULL,
                pm_template_id INTEGER NOT NULL,
                last_generated_date DATE,
                next_due_date DATE,
                FOREIGN KEY (asset_guid) REFERENCES assets(guid) ON DELETE CASCADE,
                FOREIGN KEY (pm_template_id) REFERENCES pm_templates(id) ON DELETE CASCADE,
                UNIQUE(asset_guid, pm_template_id)
            );

            CREATE INDEX IF NOT EXISTS idx_pm_state_asset ON pm_schedule_state(asset_guid);
            CREATE INDEX IF NOT EXISTS idx_pm_state_next_due ON pm_schedule_state(next_due_date);
        """)
        print("  ✓ pm_templates, work_orders, maintenance_log, technicians, pm_schedule_state")

    def create_iot_tables(self):
        """Create 7D IoT tables"""
        print("\n🌐 7D IoT Integration Tables...")

        self.cursor.executescript("""
            CREATE TABLE IF NOT EXISTS sensors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sensor_id TEXT UNIQUE NOT NULL,
                asset_guid TEXT NOT NULL,
                sensor_type TEXT NOT NULL,
                measurement_unit TEXT NOT NULL,
                protocol TEXT,
                topic TEXT,
                update_interval_seconds INTEGER DEFAULT 60,
                is_active BOOLEAN DEFAULT 1,
                last_reading_date TEXT,
                last_reading_value REAL,
                min_threshold REAL,
                max_threshold REAL,
                critical_min REAL,
                critical_max REAL,
                location_description TEXT,
                calibration_date DATE,
                calibration_due_date DATE,
                created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (asset_guid) REFERENCES assets(guid) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_sensors_asset ON sensors(asset_guid);
            CREATE INDEX IF NOT EXISTS idx_sensors_type ON sensors(sensor_type);
            CREATE INDEX IF NOT EXISTS idx_sensors_active ON sensors(is_active);
            CREATE INDEX IF NOT EXISTS idx_sensors_sensor_id ON sensors(sensor_id);

            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sensor_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                value REAL NOT NULL,
                quality TEXT DEFAULT 'good',
                FOREIGN KEY (sensor_id) REFERENCES sensors(sensor_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_readings_sensor ON sensor_readings(sensor_id);
            CREATE INDEX IF NOT EXISTS idx_readings_timestamp ON sensor_readings(timestamp);
            CREATE INDEX IF NOT EXISTS idx_readings_sensor_time ON sensor_readings(sensor_id, timestamp);

            CREATE TABLE IF NOT EXISTS alert_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rule_name TEXT NOT NULL,
                sensor_id TEXT,
                sensor_type TEXT,
                condition_type TEXT NOT NULL,
                threshold_value REAL,
                threshold_min REAL,
                threshold_max REAL,
                duration_seconds INTEGER DEFAULT 0,
                severity TEXT DEFAULT 'Warning',
                notify_email TEXT,
                notify_sms TEXT,
                auto_create_work_order BOOLEAN DEFAULT 0,
                is_active BOOLEAN DEFAULT 1,
                created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sensor_id) REFERENCES sensors(sensor_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_alert_rules_sensor ON alert_rules(sensor_id);
            CREATE INDEX IF NOT EXISTS idx_alert_rules_type ON alert_rules(sensor_type);
            CREATE INDEX IF NOT EXISTS idx_alert_rules_active ON alert_rules(is_active);

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alert_rule_id INTEGER NOT NULL,
                sensor_id TEXT NOT NULL,
                asset_guid TEXT NOT NULL,
                severity TEXT NOT NULL,
                message TEXT NOT NULL,
                trigger_value REAL,
                triggered_date TEXT NOT NULL,
                acknowledged_date TEXT,
                acknowledged_by TEXT,
                resolved_date TEXT,
                resolved_by TEXT,
                work_order_id INTEGER,
                notes TEXT,
                FOREIGN KEY (alert_rule_id) REFERENCES alert_rules(id),
                FOREIGN KEY (sensor_id) REFERENCES sensors(sensor_id),
                FOREIGN KEY (asset_guid) REFERENCES assets(guid),
                FOREIGN KEY (work_order_id) REFERENCES work_orders(id)
            );

            CREATE INDEX IF NOT EXISTS idx_alerts_sensor ON alerts(sensor_id);
            CREATE INDEX IF NOT EXISTS idx_alerts_asset ON alerts(asset_guid);
            CREATE INDEX IF NOT EXISTS idx_alerts_triggered ON alerts(triggered_date);
            CREATE INDEX IF NOT EXISTS idx_alerts_unresolved ON alerts(resolved_date) WHERE resolved_date IS NULL;
        """)
        print("  ✓ sensors, sensor_readings, alert_rules, alerts")

    def insert_default_data(self):
        """Insert default discipline rates"""
        print("\n📝 Inserting Default Data...")

        today = datetime.now().date().isoformat()

        default_rates = [
            ('ARC', 'senior', 175.0, today),
            ('ARC', 'intermediate', 135.0, today),
            ('ARC', 'junior', 95.0, today),
            ('STR', 'senior', 195.0, today),
            ('STR', 'intermediate', 165.0, today),
            ('STR', 'junior', 125.0, today),
            ('MEP', 'senior', 155.0, today),
            ('MEP', 'intermediate', 125.0, today),
            ('MEP', 'junior', 95.0, today),
            ('ELEC', 'senior', 150.0, today),
            ('ELEC', 'intermediate', 120.0, today),
            ('ACMV', 'senior', 160.0, today),
            ('ACMV', 'intermediate', 130.0, today),
            ('FP', 'senior', 145.0, today),
            ('FP', 'intermediate', 115.0, today),
        ]

        for discipline, skill, rate, date in default_rates:
            try:
                self.cursor.execute("""
                    INSERT OR IGNORE INTO discipline_rates (
                        discipline, skill_level, hourly_rate,
                        modeling_productivity, documentation_productivity,
                        coordination_overhead_factor, typical_response_time_days,
                        effective_date, source, region, notes
                    ) VALUES (?, ?, ?, 2.5, 0.5, 1.15, 2.0, ?, 'default', 'US', 'Default rates')
                """, (discipline, skill, rate, date))
            except:
                pass

        print("  ✓ Default discipline rates")

    def fix_existing_asset_tables(self):
        """Fix existing assets table to add missing federation_element_id column

        Note: SQLite doesn't support adding foreign key constraints via ALTER TABLE,
        so we add the column without the constraint. The constraint only exists
        for newly created tables.
        """
        print("\n🔧 Checking assets table for missing columns...")

        # Check if assets table exists
        self.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='assets'")
        if not self.cursor.fetchone():
            print("  ℹ️  assets table doesn't exist yet (will be created)")
            return

        # Check if federation_element_id column exists
        self.cursor.execute("PRAGMA table_info(assets)")
        columns = {row[1] for row in self.cursor.fetchall()}

        if 'federation_element_id' not in columns:
            print("  ⚠️  Adding missing federation_element_id column...")
            self.cursor.execute("ALTER TABLE assets ADD COLUMN federation_element_id INTEGER")
            self.cursor.execute("CREATE INDEX IF NOT EXISTS idx_assets_federation_element ON assets(federation_element_id)")
            print("  ✓ federation_element_id column added (FK constraint not added to existing tables)")
        else:
            print("  ✓ federation_element_id column exists")

    def add_schema_version(self):
        """Add schema version tracking"""
        # Update existing schema_version table (version, applied_date, description)
        self.cursor.execute("""
            UPDATE schema_version
            SET version = '7D_FULL',
                applied_date = ?,
                description = 'Full schema: Clash,Resolution,4D,Assets,Maintenance,IoT'
            WHERE rowid = 1
        """, (datetime.now().isoformat(),))

        # If no row was updated, insert one
        if self.cursor.rowcount == 0:
            self.cursor.execute("""
                INSERT INTO schema_version (version, applied_date, description)
                VALUES ('7D_FULL', ?, 'Full schema: Clash,Resolution,4D,Assets,Maintenance,IoT')
            """, (datetime.now().isoformat(),))

        print("\n📌 Schema version: 7D_FULL")

    def migrate(self):
        """Run full migration"""
        print("=" * 70)
        print("FEDERATION DATABASE MIGRATION - FULL SCHEMA (up to 7D IoT)")
        print("=" * 70)
        print(f"\nDatabase: {self.db_path}")

        existing = self.get_existing_tables()
        print(f"Existing tables: {len(existing)}")

        try:
            self.create_clash_tables()
            self.create_resolution_tables()
            self.create_schedule_tables()
            self.fix_existing_asset_tables()
            self.create_asset_tables()
            self.create_maintenance_tables()
            self.create_iot_tables()
            self.insert_default_data()
            self.add_schema_version()

            self.conn.commit()

            new_tables = self.get_existing_tables() - existing
            print(f"\n✅ Migration Complete!")
            print(f"   Total tables now: {len(self.get_existing_tables())}")
            if new_tables:
                print(f"   New tables added: {len(new_tables)}")

        except Exception as e:
            self.conn.rollback()
            print(f"\n❌ Migration failed: {e}")
            raise
        finally:
            self.conn.close()


def main():
    if len(sys.argv) < 2:
        print("Usage: python migrate_database_to_full_schema.py <database_path>")
        print("\nExample:")
        print("  python migrate_database_to_full_schema.py ~/WORK_DIR/databases/enhanced_federation_GI.db")
        sys.exit(1)

    db_path = sys.argv[1]

    migrator = DatabaseMigrator(db_path)
    migrator.migrate()


if __name__ == "__main__":
    main()
