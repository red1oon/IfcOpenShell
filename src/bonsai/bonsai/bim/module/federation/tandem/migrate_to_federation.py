"""
Digital Twin - Migration Script
Migrate from standalone digital_twin.db to federation-integrated enhanced_federation.db

Usage:
    python migrate_to_federation.py [--dry-run] [--backup]

Options:
    --dry-run    Show what would be migrated without making changes
    --backup     Create backup of digital_twin.db before migration
"""

import sqlite3
import shutil
import sys
from pathlib import Path
from datetime import datetime


class FederationMigrator:
    """Migrate Digital Twin data from standalone DB to federation DB"""

    def __init__(self, work_dir: Path = None):
        if work_dir is None:
            work_dir = Path.home() / 'Projects' / 'IfcOpenShell' / 'WORK_DIR' / 'databases'

        self.work_dir = work_dir
        self.old_db = work_dir / 'digital_twin.db'
        self.new_db = work_dir / 'enhanced_federation.db'
        self.backup_db = work_dir / f'digital_twin_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'

    def validate_prerequisites(self):
        """Check if migration is possible"""
        issues = []

        if not self.old_db.exists():
            issues.append(f"Source database not found: {self.old_db}")

        if not self.new_db.exists():
            issues.append(f"Federation database not found: {self.new_db}")
            issues.append("Run federation module first to create enhanced_federation.db")

        return issues

    def analyze_data(self):
        """Analyze data to be migrated"""
        conn = sqlite3.connect(self.old_db)
        conn.row_factory = sqlite3.Row

        stats = {}

        try:
            # Count assets
            cursor = conn.execute("SELECT COUNT(*) FROM assets")
            stats['assets'] = cursor.fetchone()[0]

            # Count by discipline
            cursor = conn.execute("SELECT discipline, COUNT(*) FROM assets GROUP BY discipline")
            stats['by_discipline'] = {row[0]: row[1] for row in cursor.fetchall()}

            # Count properties
            cursor = conn.execute("SELECT COUNT(*) FROM asset_properties")
            stats['properties'] = cursor.fetchone()[0]

            # Count documents
            cursor = conn.execute("SELECT COUNT(*) FROM asset_documents")
            stats['documents'] = cursor.fetchone()[0]

            # Count work orders
            cursor = conn.execute("SELECT COUNT(*) FROM work_orders")
            stats['work_orders'] = cursor.fetchone()[0]

            # Count PM templates
            cursor = conn.execute("SELECT COUNT(*) FROM pm_templates")
            stats['pm_templates'] = cursor.fetchone()[0]

            # Count sensors
            cursor = conn.execute("SELECT COUNT(*) FROM sensors")
            stats['sensors'] = cursor.fetchone()[0]

            # Count sensor readings
            cursor = conn.execute("SELECT COUNT(*) FROM sensor_readings")
            stats['sensor_readings'] = cursor.fetchone()[0]

        except sqlite3.OperationalError as e:
            print(f"Warning: Could not analyze all tables: {e}")

        finally:
            conn.close()

        return stats

    def create_federation_schema(self):
        """Create Digital Twin schema in federation database"""
        schema_path = Path(__file__).parent / 'schema_federation_integrated.sql'

        if not schema_path.exists():
            raise FileNotFoundError(f"Schema file not found: {schema_path}")

        conn = sqlite3.connect(self.new_db)
        try:
            with open(schema_path, 'r') as f:
                schema_sql = f.read()
            conn.executescript(schema_sql)
            conn.commit()
            print("✓ Created Digital Twin schema in federation database")
        finally:
            conn.close()

    def migrate_assets(self):
        """Migrate assets table"""
        old_conn = sqlite3.connect(self.old_db)
        old_conn.row_factory = sqlite3.Row
        new_conn = sqlite3.connect(self.new_db)

        try:
            # Get all assets from old DB
            cursor = old_conn.execute("SELECT * FROM assets")
            assets = cursor.fetchall()

            migrated = 0
            skipped = 0
            errors = 0

            for asset in assets:
                try:
                    # Check if asset already exists
                    check = new_conn.execute("SELECT guid FROM assets WHERE guid = ?", (asset['guid'],))
                    if check.fetchone():
                        skipped += 1
                        continue

                    # Build insert statement (exclude federation_element_id - set to NULL)
                    fields = [key for key in asset.keys()]
                    placeholders = ','.join(['?' for _ in fields])

                    # Add federation_element_id field (NULL initially)
                    insert_fields = fields + ['federation_element_id']
                    insert_values = [asset[f] for f in fields] + [None]

                    sql = f"INSERT INTO assets ({','.join(insert_fields)}) VALUES ({placeholders},?)"
                    new_conn.execute(sql, insert_values)
                    migrated += 1

                except Exception as e:
                    print(f"Error migrating asset {asset['guid']}: {e}")
                    errors += 1

            new_conn.commit()
            print(f"✓ Assets: {migrated} migrated, {skipped} skipped, {errors} errors")

        finally:
            old_conn.close()
            new_conn.close()

    def migrate_table(self, table_name: str, display_name: str = None):
        """Generic table migration"""
        if display_name is None:
            display_name = table_name

        old_conn = sqlite3.connect(self.old_db)
        old_conn.row_factory = sqlite3.Row
        new_conn = sqlite3.connect(self.new_db)

        try:
            # Get all rows
            cursor = old_conn.execute(f"SELECT * FROM {table_name}")
            rows = cursor.fetchall()

            if not rows:
                print(f"  {display_name}: No data to migrate")
                return

            migrated = 0
            errors = 0

            for row in rows:
                try:
                    fields = list(row.keys())
                    placeholders = ','.join(['?' for _ in fields])
                    values = [row[f] for f in fields]

                    sql = f"INSERT INTO {table_name} ({','.join(fields)}) VALUES ({placeholders})"
                    new_conn.execute(sql, values)
                    migrated += 1

                except sqlite3.IntegrityError:
                    # Skip duplicates
                    pass
                except Exception as e:
                    print(f"  Error migrating {table_name} row: {e}")
                    errors += 1

            new_conn.commit()
            print(f"✓ {display_name}: {migrated} records migrated, {errors} errors")

        except sqlite3.OperationalError as e:
            print(f"  {display_name}: Table not found or error - {e}")

        finally:
            old_conn.close()
            new_conn.close()

    def migrate(self, dry_run=False, backup=True):
        """Perform migration"""
        print("=" * 60)
        print("Digital Twin - Federation Migration")
        print("=" * 60)
        print()

        # Validate
        issues = self.validate_prerequisites()
        if issues:
            print("❌ Migration cannot proceed:\n")
            for issue in issues:
                print(f"  - {issue}")
            return False

        # Analyze
        print("📊 Analyzing data to migrate...\n")
        stats = self.analyze_data()

        print(f"Source: {self.old_db}")
        print(f"Target: {self.new_db}")
        print()
        print("Data Summary:")
        print(f"  Assets: {stats.get('assets', 0)}")
        for disc, count in stats.get('by_discipline', {}).items():
            print(f"    {disc}: {count}")
        print(f"  Properties: {stats.get('properties', 0)}")
        print(f"  Documents: {stats.get('documents', 0)}")
        print(f"  Work Orders: {stats.get('work_orders', 0)}")
        print(f"  PM Templates: {stats.get('pm_templates', 0)}")
        print(f"  Sensors: {stats.get('sensors', 0)}")
        print(f"  Sensor Readings: {stats.get('sensor_readings', 0)}")
        print()

        if dry_run:
            print("🔍 DRY RUN - No changes will be made")
            return True

        # Confirm
        response = input("Proceed with migration? (yes/no): ")
        if response.lower() != 'yes':
            print("Migration cancelled")
            return False

        print()

        # Backup
        if backup:
            print(f"📦 Creating backup: {self.backup_db.name}")
            shutil.copy2(self.old_db, self.backup_db)
            print("✓ Backup created")
            print()

        # Create schema
        print("🏗️  Creating schema in federation database...")
        try:
            self.create_federation_schema()
        except Exception as e:
            print(f"Note: Schema may already exist - {e}")
        print()

        # Migrate tables
        print("📦 Migrating data...")
        print()

        self.migrate_assets()
        self.migrate_table('asset_properties', 'Asset Properties')
        self.migrate_table('asset_documents', 'Asset Documents')
        self.migrate_table('asset_history', 'Asset History')

        self.migrate_table('pm_templates', 'PM Templates')
        self.migrate_table('work_orders', 'Work Orders')
        self.migrate_table('maintenance_log', 'Maintenance Log')
        self.migrate_table('technicians', 'Technicians')
        self.migrate_table('pm_schedule_state', 'PM Schedule State')

        self.migrate_table('sensors', 'Sensors')
        self.migrate_table('sensor_readings', 'Sensor Readings')
        self.migrate_table('alert_rules', 'Alert Rules')
        self.migrate_table('alerts', 'Alerts')

        print()
        print("=" * 60)
        print("✅ Migration Complete!")
        print("=" * 60)
        print()
        print("Next Steps:")
        print(f"  1. Verify data in {self.new_db}")
        print("  2. Update Blender panels to use enhanced_federation.db")
        print("  3. Test all functionality")
        print(f"  4. Optional: Archive old DB {self.old_db}")
        if backup:
            print(f"  5. Backup saved at: {self.backup_db}")
        print()
        print("Note: Assets have federation_element_id = NULL")
        print("      Use 'Import from Federation DB' to re-link to elements table")

        return True


def main():
    """CLI entry point"""
    dry_run = '--dry-run' in sys.argv
    backup = '--backup' in sys.argv or '-b' in sys.argv

    migrator = FederationMigrator()
    success = migrator.migrate(dry_run=dry_run, backup=backup)

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
