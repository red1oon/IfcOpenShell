"""
SQLite database for persistent clash status tracking

Stores clash status, comments, assignments across Blender sessions and
IFC file reloads. Enables BCF export and backroom processing intelligence.
"""

import sqlite3
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import bpy


def get_clash_database_path() -> Path:
    """Get path to clash status database (same dir as federation.db)"""
    fed_props = bpy.context.scene.BIMFederationProperties

    if fed_props.federation_database_path:
        fed_db = Path(fed_props.federation_database_path)
        # Create clash_status.db in same directory
        return fed_db.parent / "clash_status.db"
    else:
        # Fallback: use Bonsai documents folder
        return Path.home() / "Documents" / "bonsai" / "clash_status.db"


def get_clash_id(guid_a: str, guid_b: str) -> str:
    """Generate stable clash ID from element GUIDs

    Ensures A-B and B-A clashes get same ID (sorted GUIDs)
    """
    guids = sorted([guid_a, guid_b])
    clash_key = f"{guids[0]}_{guids[1]}"
    return hashlib.md5(clash_key.encode()).hexdigest()


def initialize_database() -> sqlite3.Connection:
    """Create or open clash status database, ensure schema exists"""
    db_path = get_clash_database_path()

    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row  # Enable dict-like access

    # Create schema if not exists
    conn.executescript("""
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

            -- Additional metadata for intelligence
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

        -- Audit log for status changes (backroom processing intelligence)
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
    """)

    conn.commit()
    # Removed spam log - only log on actual first use, not every call
    return conn


def get_clash_status(guid_a: str, guid_b: str) -> Optional[Dict]:
    """Get status for a clash, returns None if not in database"""
    clash_id = get_clash_id(guid_a, guid_b)

    conn = initialize_database()
    row = conn.execute(
        "SELECT * FROM clash_status WHERE clash_id = ?",
        (clash_id,)
    ).fetchone()
    conn.close()

    if row:
        return dict(row)
    return None


def set_clash_status(
    guid_a: str,
    guid_b: str,
    status: str,
    comment: str = None,
    assigned_to: str = None,
    distance: float = None,
    ifc_class_a: str = None,
    ifc_class_b: str = None,
    discipline_a: str = None,
    discipline_b: str = None,
    changed_by: str = "User"
) -> str:
    """Set or update clash status, returns clash_id"""
    clash_id = get_clash_id(guid_a, guid_b)
    now = datetime.now().isoformat()

    conn = initialize_database()

    # Check if clash exists
    existing = conn.execute(
        "SELECT status FROM clash_status WHERE clash_id = ?",
        (clash_id,)
    ).fetchone()

    if existing:
        # Update existing clash
        old_status = existing['status']

        conn.execute("""
            UPDATE clash_status SET
                status = ?,
                comment = COALESCE(?, comment),
                assigned_to = COALESCE(?, assigned_to),
                distance = COALESCE(?, distance),
                date_modified = ?
            WHERE clash_id = ?
        """, (status, comment, assigned_to, distance, now, clash_id))

        # Log status change to history
        if old_status != status:
            conn.execute("""
                INSERT INTO clash_history (clash_id, old_status, new_status, changed_by, change_date, comment)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (clash_id, old_status, status, changed_by, now, comment))

    else:
        # Insert new clash
        conn.execute("""
            INSERT INTO clash_status (
                clash_id, guid_a, guid_b, status,
                comment, assigned_to, distance,
                ifc_class_a, ifc_class_b,
                discipline_a, discipline_b,
                date_created, date_modified
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            clash_id, guid_a, guid_b, status,
            comment, assigned_to, distance,
            ifc_class_a, ifc_class_b,
            discipline_a, discipline_b,
            now, now
        ))

        # Log creation
        conn.execute("""
            INSERT INTO clash_history (clash_id, old_status, new_status, changed_by, change_date, comment)
            VALUES (?, NULL, ?, ?, ?, ?)
        """, (clash_id, status, changed_by, now, f"Clash detected"))

    conn.commit()
    conn.close()

    return clash_id


def bulk_update_status(clash_ids: List[str], new_status: str, changed_by: str = "User") -> int:
    """Update status for multiple clashes, returns count updated"""
    if not clash_ids:
        return 0

    conn = initialize_database()
    now = datetime.now().isoformat()
    count = 0

    for clash_id in clash_ids:
        # Get old status
        row = conn.execute("SELECT status FROM clash_status WHERE clash_id = ?", (clash_id,)).fetchone()
        if row and row['status'] != new_status:
            old_status = row['status']

            # Update status
            conn.execute(
                "UPDATE clash_status SET status = ?, date_modified = ? WHERE clash_id = ?",
                (new_status, now, clash_id)
            )

            # Log change
            conn.execute("""
                INSERT INTO clash_history (clash_id, old_status, new_status, changed_by, change_date)
                VALUES (?, ?, ?, ?, ?)
            """, (clash_id, old_status, new_status, changed_by, now))

            count += 1

    conn.commit()
    conn.close()

    return count


def get_all_clashes(status_filter: List[str] = None) -> List[Dict]:
    """Get all clashes, optionally filtered by status"""
    conn = initialize_database()

    if status_filter:
        placeholders = ','.join('?' * len(status_filter))
        rows = conn.execute(
            f"SELECT * FROM clash_status WHERE status IN ({placeholders}) ORDER BY date_created DESC",
            status_filter
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM clash_status ORDER BY date_created DESC").fetchall()

    conn.close()
    return [dict(row) for row in rows]


def get_clash_history(clash_id: str) -> List[Dict]:
    """Get history of status changes for a clash"""
    conn = initialize_database()
    rows = conn.execute(
        "SELECT * FROM clash_history WHERE clash_id = ? ORDER BY change_date DESC",
        (clash_id,)
    ).fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_statistics() -> Dict:
    """Get clash statistics for reporting"""
    conn = initialize_database()

    stats = {}

    # Count by status
    status_counts = conn.execute("""
        SELECT status, COUNT(*) as count FROM clash_status
        GROUP BY status
    """).fetchall()
    stats['by_status'] = {row['status']: row['count'] for row in status_counts}

    # Total clashes
    stats['total'] = sum(stats['by_status'].values())

    # Count by discipline
    discipline_counts = conn.execute("""
        SELECT discipline_a, discipline_b, COUNT(*) as count FROM clash_status
        WHERE discipline_a IS NOT NULL AND discipline_b IS NOT NULL
        GROUP BY discipline_a, discipline_b
    """).fetchall()
    stats['by_discipline'] = [(row['discipline_a'], row['discipline_b'], row['count']) for row in discipline_counts]

    conn.close()
    return stats


def cleanup_resolved_clashes(days_old: int = 30) -> int:
    """Archive old resolved clashes (backroom processing)"""
    conn = initialize_database()
    cutoff_date = datetime.now().replace(day=datetime.now().day - days_old).isoformat()

    result = conn.execute("""
        DELETE FROM clash_status
        WHERE status = 'RESOLVED' AND date_modified < ?
    """, (cutoff_date,))

    count = result.rowcount
    conn.commit()
    conn.close()

    return count


# Quick test function
if __name__ == "__main__":
    # Test database creation
    conn = initialize_database()

    # Test inserting a clash
    set_clash_status(
        "test-guid-a",
        "test-guid-b",
        "NEW",
        distance=0.05,
        ifc_class_a="IfcWall",
        ifc_class_b="IfcDoor"
    )

    # Test retrieving
    status = get_clash_status("test-guid-a", "test-guid-b")
    print(f"Retrieved status: {status}")

    # Test statistics
    stats = get_statistics()
    print(f"Statistics: {stats}")

    conn.close()
