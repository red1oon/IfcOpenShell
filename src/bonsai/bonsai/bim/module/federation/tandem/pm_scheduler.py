"""
Digital Twin - PM Scheduler
Automatic preventive maintenance work order generation

Generates work orders based on:
- PM templates
- Asset types (IFC class, discipline)
- Maintenance intervals
"""

import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from .asset_registry import AssetRegistry
from .maintenance_manager import MaintenanceManager


class PMScheduler:
    """Automatic PM work order scheduling"""

    def __init__(self, registry: AssetRegistry, maintenance: MaintenanceManager):
        """
        Initialize PM scheduler

        Args:
            registry: AssetRegistry instance
            maintenance: MaintenanceManager instance
        """
        self.registry = registry
        self.maintenance = maintenance

    def generate_pm_schedule(self, days_ahead: int = 90,
                            progress_callback=None) -> Dict[str, Any]:
        """
        Generate PM work orders for next N days

        Args:
            days_ahead: How many days ahead to schedule
            progress_callback: Optional callback(current, total, message)

        Returns:
            Generation statistics
        """
        stats = {
            'templates_processed': 0,
            'assets_scanned': 0,
            'work_orders_created': 0,
            'work_orders_skipped': 0,
            'errors': 0
        }

        # Get all active PM templates
        templates = self.maintenance.list_pm_templates(active_only=True)
        stats['templates_processed'] = len(templates)

        if progress_callback:
            progress_callback(0, len(templates), "Loading PM templates")

        for idx, template in enumerate(templates):
            if progress_callback:
                progress_callback(idx + 1, len(templates), f"Processing: {template['template_name']}")

            try:
                # Find assets matching this template
                assets = self._find_matching_assets(template)
                stats['assets_scanned'] += len(assets)

                # Generate work orders for each asset
                for asset in assets:
                    result = self._generate_wo_for_asset(asset, template, days_ahead)
                    if result:
                        stats['work_orders_created'] += 1
                    else:
                        stats['work_orders_skipped'] += 1

            except Exception as e:
                stats['errors'] += 1
                print(f"Error processing template {template['template_name']}: {e}")

        return stats

    def _find_matching_assets(self, template: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Find assets that match PM template criteria"""
        filters = {}

        if template.get('ifc_class'):
            filters['ifc_class'] = template['ifc_class']

        if template.get('discipline'):
            filters['discipline'] = template['discipline']

        # Only active assets
        filters['status'] = 'Active'

        return self.registry.list_assets(**filters)

    def _generate_wo_for_asset(self, asset: Dict[str, Any], template: Dict[str, Any],
                               days_ahead: int) -> bool:
        """
        Generate work order for specific asset if due

        Returns:
            True if WO created, False if skipped
        """
        # Check if WO already exists for this asset/template combination
        pm_state = self._get_pm_state(asset['guid'], template['id'])

        # Calculate next due date
        if pm_state and pm_state['next_due_date']:
            next_due = datetime.fromisoformat(pm_state['next_due_date']).date()
        else:
            # First time - schedule based on current date
            next_due = self.maintenance._calculate_next_due_date(
                template['interval_type'],
                template.get('interval_value', 1)
            ).date()

        # Check if due within the scheduling window
        today = datetime.now().date()
        schedule_until = today + timedelta(days=days_ahead)

        if next_due > schedule_until:
            return False  # Not due yet

        # Check if WO already exists for this due date
        existing_wos = self.maintenance.list_work_orders(
            asset_guid=asset['guid'],
            work_type='PM',
            status='Open'
        )

        # Check if any existing WO is for this template
        for wo in existing_wos:
            if wo.get('pm_template_id') == template['id']:
                return False  # Already scheduled

        # Create work order
        wo_number = self.maintenance._generate_wo_number()

        wo_data = {
            'work_order_number': wo_number,
            'asset_guid': asset['guid'],
            'work_type': 'PM',
            'priority': 'Medium',
            'title': f"{template['template_name']} - {asset['name']}",
            'description': template.get('description', ''),
            'pm_template_id': template['id'],
            'scheduled_date': today.isoformat(),
            'due_date': next_due.isoformat(),
            'estimated_hours': template.get('estimated_hours'),
            'team': template.get('discipline'),
            'created_by': 'pm_scheduler',
        }

        wo_id = self.maintenance.create_work_order(wo_data)

        # Update PM state
        self._update_pm_state(
            asset['guid'],
            template['id'],
            today.isoformat(),
            next_due.isoformat()
        )

        return True

    def _get_pm_state(self, asset_guid: str, template_id: int) -> Optional[Dict[str, Any]]:
        """Get PM schedule state for asset/template"""
        conn = sqlite3.connect(self.maintenance.db_path)
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.execute(
                "SELECT * FROM pm_schedule_state WHERE asset_guid = ? AND pm_template_id = ?",
                (asset_guid, template_id)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def _update_pm_state(self, asset_guid: str, template_id: int,
                        last_generated: str, next_due: str):
        """Update PM schedule state"""
        conn = sqlite3.connect(self.maintenance.db_path)
        try:
            # Try insert first
            try:
                conn.execute(
                    "INSERT INTO pm_schedule_state (asset_guid, pm_template_id, last_generated_date, next_due_date) "
                    "VALUES (?, ?, ?, ?)",
                    (asset_guid, template_id, last_generated, next_due)
                )
            except sqlite3.IntegrityError:
                # Already exists, update
                conn.execute(
                    "UPDATE pm_schedule_state SET last_generated_date = ?, next_due_date = ? "
                    "WHERE asset_guid = ? AND pm_template_id = ?",
                    (last_generated, next_due, asset_guid, template_id)
                )
            conn.commit()
        finally:
            conn.close()

    def get_upcoming_pm_summary(self, days: int = 30) -> Dict[str, Any]:
        """
        Get summary of upcoming PM work

        Args:
            days: Number of days to look ahead

        Returns:
            Summary statistics
        """
        today = datetime.now().date()
        until_date = today + timedelta(days=days)

        # Get all PM work orders due in this period
        pm_wos = self.maintenance.list_work_orders(
            work_type='PM',
            status='Open',
            due_before=until_date.isoformat()
        )

        summary = {
            'total_upcoming': len(pm_wos),
            'by_discipline': {},
            'by_week': {},
            'overdue': 0,
            'due_this_week': 0,
            'due_next_week': 0
        }

        for wo in pm_wos:
            # Count by discipline
            team = wo.get('team', 'Unknown')
            summary['by_discipline'][team] = summary['by_discipline'].get(team, 0) + 1

            # Count by due date
            due_date = datetime.fromisoformat(wo['due_date']).date() if wo.get('due_date') else None
            if due_date:
                if due_date < today:
                    summary['overdue'] += 1
                elif due_date <= today + timedelta(days=7):
                    summary['due_this_week'] += 1
                elif due_date <= today + timedelta(days=14):
                    summary['due_next_week'] += 1

                # Count by week
                week_num = (due_date - today).days // 7
                week_label = f"Week {week_num + 1}"
                summary['by_week'][week_label] = summary['by_week'].get(week_label, 0) + 1

        return summary
