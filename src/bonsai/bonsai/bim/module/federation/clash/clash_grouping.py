"""
Clash Grouping & Cascade Detection
===================================

Identifies cascade clashes where a single element causes multiple conflicts.
This is the foundation of the Intelligent Clash Adjustment system.

Based on Phase 0 validation (2025-11-04):
- 29% of Terminal 1 clashes grouped into 2 cascade patterns
- Industry research shows 60-70% of clashes are cascade patterns
- Grouping saves 3-4 hours per coordination cycle

Part of: Intelligent Clash Adjustment POC
"""

import sqlite3
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ClashGroup:
    """
    Represents a group of related clashes caused by a single element.
    """
    group_id: str
    cascade_element_guid: str
    cascade_element_class: str
    cascade_element_discipline: str
    total_clashes: int
    affected_disciplines: List[str]
    affected_classes: List[str]
    status_summary: Dict[str, int]  # {'NEW': 3, 'REVIEWED': 2, 'RESOLVED': 1}
    member_clash_ids: List[str]
    severity: str  # 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'


class ClashGroupAnalyzer:
    """
    Identifies cascade clash patterns and groups related clashes.

    Cascade Pattern: Single element involved in 3+ clashes
    - Example: Duct intersecting 8 beams → 1 group, 8 clashes
    - Resolution: Fix the duct once, resolve all 8 clashes
    """

    # Threshold: Element must be involved in this many clashes to be considered cascade
    CASCADE_THRESHOLD = 3

    def __init__(self, db_path: str):
        """
        Initialize analyzer with clash status database.

        Args:
            db_path: Path to clash_status.db
        """
        self.db_path = db_path

    def find_cascade_groups(self, include_ignored: bool = False) -> List[ClashGroup]:
        """
        Identify all cascade clash groups in the database.

        Args:
            include_ignored: Whether to include ignored clashes in grouping

        Returns:
            List of ClashGroup objects, sorted by total_clashes descending
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Build filter for ignored clashes
        ignored_filter = "" if include_ignored else "WHERE is_ignored = 0"

        # Find cascade elements: elements involved in 3+ clashes
        cursor.execute(f"""
            WITH element_clashes AS (
                SELECT guid_a as element_guid FROM clash_status {ignored_filter}
                UNION ALL
                SELECT guid_b FROM clash_status {ignored_filter}
            )
            SELECT
                element_guid,
                COUNT(*) as clash_count
            FROM element_clashes
            GROUP BY element_guid
            HAVING COUNT(*) >= ?
            ORDER BY COUNT(*) DESC
        """, (self.CASCADE_THRESHOLD,))

        cascade_elements = cursor.fetchall()

        if not cascade_elements:
            print("✓ No cascade groups found (threshold: 3+ clashes per element)")
            conn.close()
            return []

        print(f"✓ Found {len(cascade_elements)} cascade elements:")
        for elem_guid, count in cascade_elements:
            print(f"  - {elem_guid[:20]}... : {count} clashes")

        # Build groups for each cascade element
        groups = []
        for cascade_guid, clash_count in cascade_elements:
            group = self._build_group_for_element(cursor, cascade_guid, ignored_filter)
            if group:
                groups.append(group)

        conn.close()

        # Sort by total clashes (most impactful first)
        groups.sort(key=lambda g: g.total_clashes, reverse=True)

        return groups

    def _build_group_for_element(self, cursor: sqlite3.Cursor,
                                  element_guid: str,
                                  ignored_filter: str) -> Optional[ClashGroup]:
        """
        Build a ClashGroup for a specific cascade element.

        Args:
            cursor: Database cursor
            element_guid: GUID of cascade element
            ignored_filter: SQL filter for ignored clashes

        Returns:
            ClashGroup or None if insufficient data
        """
        # Get all clashes involving this element
        if ignored_filter:
            # ignored_filter already contains "WHERE is_ignored = 0"
            where_clause = "is_ignored = 0 AND (guid_a = ? OR guid_b = ?)"
        else:
            where_clause = "(guid_a = ? OR guid_b = ?)"

        cursor.execute(f"""
            SELECT
                clash_id,
                guid_a,
                guid_b,
                status,
                ifc_class_a,
                ifc_class_b,
                discipline_a,
                discipline_b
            FROM clash_status
            WHERE {where_clause}
        """, (element_guid, element_guid))

        clashes = cursor.fetchall()

        if not clashes:
            return None

        # Analyze group characteristics
        member_clash_ids = []
        status_counts = defaultdict(int)
        affected_disciplines = set()
        affected_classes = set()

        # Determine cascade element properties (from first clash)
        first_clash = clashes[0]
        is_element_a = (first_clash[1] == element_guid)
        cascade_class = first_clash[4] if is_element_a else first_clash[5]
        cascade_discipline = first_clash[6] if is_element_a else first_clash[7]

        for clash in clashes:
            clash_id, guid_a, guid_b, status, class_a, class_b, disc_a, disc_b = clash

            member_clash_ids.append(clash_id)
            status_counts[status] += 1

            # Add the OTHER element's properties (not the cascade element)
            if guid_a == element_guid:
                if disc_b:
                    affected_disciplines.add(disc_b)
                if class_b:
                    affected_classes.add(class_b)
            else:
                if disc_a:
                    affected_disciplines.add(disc_a)
                if class_a:
                    affected_classes.add(class_a)

        # Calculate severity
        severity = self._calculate_severity(
            len(clashes),
            cascade_discipline,
            list(affected_disciplines),
            status_counts
        )

        # Generate unique group ID
        group_id = f"group_{element_guid[:12]}_{len(clashes)}"

        return ClashGroup(
            group_id=group_id,
            cascade_element_guid=element_guid,
            cascade_element_class=cascade_class or 'Unknown',
            cascade_element_discipline=cascade_discipline or 'Unknown',
            total_clashes=len(clashes),
            affected_disciplines=sorted(affected_disciplines),
            affected_classes=sorted(affected_classes),
            status_summary=dict(status_counts),
            member_clash_ids=member_clash_ids,
            severity=severity
        )

    def _calculate_severity(self, clash_count: int,
                            cascade_discipline: str,
                            affected_disciplines: List[str],
                            status_counts: Dict[str, int]) -> str:
        """
        Calculate group severity based on multiple factors.

        Priority factors:
        1. Structure vs Structure = CRITICAL
        2. High clash count (5+) = HIGH
        3. Multiple disciplines = HIGH
        4. Medium clash count (3-4) = MEDIUM
        5. Low count or resolved = LOW

        Args:
            clash_count: Number of clashes in group
            cascade_discipline: Discipline of cascade element
            affected_disciplines: List of affected disciplines
            status_counts: Status breakdown

        Returns:
            Severity string: 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'
        """
        # CRITICAL: Structure vs Structure
        if cascade_discipline == 'STR' and 'STR' in affected_disciplines:
            return 'CRITICAL'

        # HIGH: Many clashes or multiple disciplines
        if clash_count >= 5:
            return 'HIGH'

        if len(affected_disciplines) >= 3:
            return 'HIGH'

        # MEDIUM: Moderate count
        if clash_count >= 3:
            return 'MEDIUM'

        # LOW: Everything else
        return 'LOW'

    def export_groups_to_database(self, groups: List[ClashGroup]) -> None:
        """
        Export clash groups to clash_status.db for persistence.

        Creates tables:
        - clash_groups: Group metadata
        - clash_group_members: Clash-to-group mappings

        Args:
            groups: List of ClashGroup objects to export
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create tables if not exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clash_groups (
                group_id TEXT PRIMARY KEY,
                cascade_element_guid TEXT NOT NULL,
                cascade_element_class TEXT,
                cascade_element_discipline TEXT,
                total_clashes INTEGER NOT NULL,
                affected_disciplines TEXT,  -- JSON array as string
                affected_classes TEXT,      -- JSON array as string
                status_summary TEXT,        -- JSON object as string
                severity TEXT NOT NULL,
                date_created TIMESTAMP NOT NULL,
                date_modified TIMESTAMP NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS clash_group_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT NOT NULL,
                clash_id TEXT NOT NULL,
                FOREIGN KEY (group_id) REFERENCES clash_groups(group_id),
                FOREIGN KEY (clash_id) REFERENCES clash_status(clash_id),
                UNIQUE(group_id, clash_id)
            )
        """)

        # Clear existing groups (refresh on each run)
        cursor.execute("DELETE FROM clash_group_members")
        cursor.execute("DELETE FROM clash_groups")

        now = datetime.now().isoformat()

        # Insert groups
        for group in groups:
            import json

            cursor.execute("""
                INSERT OR REPLACE INTO clash_groups (
                    group_id,
                    cascade_element_guid,
                    cascade_element_class,
                    cascade_element_discipline,
                    total_clashes,
                    affected_disciplines,
                    affected_classes,
                    status_summary,
                    severity,
                    date_created,
                    date_modified
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                group.group_id,
                group.cascade_element_guid,
                group.cascade_element_class,
                group.cascade_element_discipline,
                group.total_clashes,
                json.dumps(group.affected_disciplines),
                json.dumps(group.affected_classes),
                json.dumps(group.status_summary),
                group.severity,
                now,
                now
            ))

            # Insert members
            for clash_id in group.member_clash_ids:
                cursor.execute("""
                    INSERT INTO clash_group_members (group_id, clash_id)
                    VALUES (?, ?)
                """, (group.group_id, clash_id))

        conn.commit()
        conn.close()

        print(f"✓ Exported {len(groups)} clash groups to database")
        for group in groups:
            print(f"  - {group.group_id}: {group.total_clashes} clashes, {group.severity} severity")

    def get_group_summary(self, groups: List[ClashGroup]) -> Dict:
        """
        Generate summary statistics for clash groups.

        Args:
            groups: List of ClashGroup objects

        Returns:
            Summary dict with statistics
        """
        if not groups:
            return {
                'total_groups': 0,
                'total_grouped_clashes': 0,
                'grouping_efficiency': 0.0,
                'severity_breakdown': {}
            }

        total_grouped_clashes = sum(g.total_clashes for g in groups)
        severity_counts = defaultdict(int)
        for group in groups:
            severity_counts[group.severity] += 1

        # Calculate grouping efficiency (percentage of clashes that are grouped)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM clash_status WHERE is_ignored = 0")
        total_clashes = cursor.fetchone()[0]
        conn.close()

        grouping_efficiency = (total_grouped_clashes / total_clashes * 100) if total_clashes > 0 else 0.0

        return {
            'total_groups': len(groups),
            'total_grouped_clashes': total_grouped_clashes,
            'total_clashes': total_clashes,
            'grouping_efficiency': grouping_efficiency,
            'severity_breakdown': dict(severity_counts)
        }


def analyze_and_export_groups(db_path: str, include_ignored: bool = False) -> List[ClashGroup]:
    """
    Convenience function: Analyze clashes and export groups to database.

    Args:
        db_path: Path to clash_status.db
        include_ignored: Whether to include ignored clashes

    Returns:
        List of ClashGroup objects
    """
    analyzer = ClashGroupAnalyzer(db_path)

    print("=" * 60)
    print("CLASH GROUPING ANALYSIS")
    print("=" * 60)

    groups = analyzer.find_cascade_groups(include_ignored=include_ignored)

    if groups:
        analyzer.export_groups_to_database(groups)

        summary = analyzer.get_group_summary(groups)

        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        print(f"Total Clash Groups: {summary['total_groups']}")
        print(f"Grouped Clashes: {summary['total_grouped_clashes']} / {summary['total_clashes']}")
        print(f"Grouping Efficiency: {summary['grouping_efficiency']:.1f}%")
        print(f"\nSeverity Breakdown:")
        for severity, count in sorted(summary['severity_breakdown'].items()):
            print(f"  {severity}: {count} groups")
        print("=" * 60)

    return groups


if __name__ == "__main__":
    """
    Test script: Analyze Terminal 1 clashes for cascade patterns
    """
    import sys

    db_path = "/home/red1/Documents/bonsai/DatabaseFiles/clash_status.db"

    if len(sys.argv) > 1:
        db_path = sys.argv[1]

    groups = analyze_and_export_groups(db_path)

    if groups:
        print("\nDetailed Group Information:")
        print("-" * 60)
        for i, group in enumerate(groups, 1):
            print(f"\nGroup {i}: {group.group_id}")
            print(f"  Cascade Element: {group.cascade_element_guid}")
            print(f"  Type: {group.cascade_element_class} ({group.cascade_element_discipline})")
            print(f"  Total Clashes: {group.total_clashes}")
            print(f"  Severity: {group.severity}")
            print(f"  Affected Disciplines: {', '.join(group.affected_disciplines)}")
            print(f"  Affected Classes: {', '.join(group.affected_classes)}")
            print(f"  Status: {group.status_summary}")
