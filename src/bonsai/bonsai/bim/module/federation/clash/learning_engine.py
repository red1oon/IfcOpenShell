"""
Learning Engine for Clash Resolution System (Phase 2)
======================================================

Implements Bayesian-inspired learning from actual vs estimated outcomes.
Updates activity duration estimates based on user feedback.

Key Concept: Higher-rated resolutions get more weight in the learning process.

Part of: Intelligent Clash Adjustment System - Phase 2
"""

import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple


def update_learned_estimates(db_path: str, resolution_history_id: int,
                             actual_hours: float, user_rating: int,
                             project_id: str = None) -> int:
    """
    Update learned estimates based on actual outcome feedback.

    Implements weighted Bayesian update:
    - Higher-rated resolutions (4-5 stars) get more weight
    - More samples = higher confidence
    - Rolling window of last 20 samples to adapt to changing conditions

    Args:
        db_path: Path to database
        resolution_history_id: ID from resolution_history table
        actual_hours: Actual total hours spent (user-reported)
        user_rating: 1-5 stars (quality weight)
        project_id: Optional project ID for project-specific learning

    Returns:
        Number of activity estimates updated (typically 4: modeling, verification, documentation, coordination)
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get resolution details
    cursor.execute("""
        SELECT ro.option_id, ro.group_id, ro.total_design_hours
        FROM resolution_history rh
        JOIN resolution_options ro ON rh.option_id = ro.option_id
        WHERE rh.history_id = ?
    """, (resolution_history_id,))

    resolution_row = cursor.fetchone()
    if not resolution_row:
        conn.close()
        return 0

    option_id = resolution_row['option_id']
    total_estimated = resolution_row['total_design_hours']

    # Get design effort estimates for this resolution
    cursor.execute("""
        SELECT effort_id, discipline, activity_type, estimated_hours
        FROM design_effort_estimates
        WHERE option_id = ?
    """, (option_id,))

    effort_estimates = cursor.fetchall()

    if not effort_estimates:
        conn.close()
        return 0

    # Distribute actual hours proportionally across activities
    # (In POC: we don't track per-activity actual hours, so we distribute proportionally)
    total_estimated_sum = sum(e['estimated_hours'] for e in effort_estimates)
    activity_proportion = {
        e['effort_id']: e['estimated_hours'] / total_estimated_sum if total_estimated_sum > 0 else 0.25
        for e in effort_estimates
    }

    updates_count = 0

    for effort in effort_estimates:
        activity_type = effort['activity_type']
        discipline = effort['discipline']
        estimated_hours = effort['estimated_hours']

        # Proportional actual hours for this activity
        activity_actual_hours = actual_hours * activity_proportion[effort['effort_id']]

        # Calculate variance
        variance_hours = activity_actual_hours - estimated_hours
        variance_percent = (variance_hours / estimated_hours) * 100 if estimated_hours > 0 else 0

        # Record in learning_metrics
        cursor.execute("""
            INSERT INTO learning_metrics
            (resolution_id, activity_type, ifc_class, discipline, estimated_hours,
             actual_hours, variance_hours, variance_percent, user_rating, project_id)
            VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)
        """, (resolution_history_id, activity_type, discipline, estimated_hours,
              activity_actual_hours, variance_hours, variance_percent, user_rating, project_id))

        # Get historical data for this activity type + discipline
        cursor.execute("""
            SELECT actual_hours, user_rating, estimated_hours
            FROM learning_metrics
            WHERE activity_type = ? AND discipline = ?
              AND (project_id = ? OR project_id IS NULL OR ? IS NULL)
            ORDER BY recorded_at DESC
            LIMIT 20  -- Rolling window of last 20 samples
        """, (activity_type, discipline, project_id, project_id))

        historical = cursor.fetchall()

        if len(historical) >= 3:  # Need at least 3 samples to learn
            # Weighted average: Higher ratings get more weight
            weighted_sum = 0
            weight_total = 0

            for record in historical:
                rating_weight = record['user_rating']  # 1-5 stars
                weighted_sum += record['actual_hours'] * rating_weight
                weight_total += rating_weight

            new_base_estimate = weighted_sum / weight_total if weight_total > 0 else estimated_hours

            # Calculate confidence (more samples + higher avg rating = higher confidence)
            sample_size = len(historical)
            avg_rating = sum(r['user_rating'] for r in historical) / sample_size
            confidence = min(100, (sample_size * 5) + (avg_rating * 10))  # Cap at 100%

            # Get current complexity multiplier (keep it, only update base_hours)
            # Try to get from learned first, then default
            cursor.execute("""
                SELECT complexity_multiplier FROM activity_base_durations
                WHERE activity_type = ? AND discipline = ?
                  AND (source = 'learned' OR source = 'default')
                ORDER BY CASE WHEN source = 'learned' THEN 0 ELSE 1 END
                LIMIT 1
            """, (activity_type, discipline))

            multiplier_row = cursor.fetchone()
            complexity_multiplier = multiplier_row['complexity_multiplier'] if multiplier_row else 0.10

            # Upsert learned estimate (project-specific)
            project_clause = project_id if project_id else 'global'
            cursor.execute("""
                INSERT INTO activity_base_durations
                (activity_type, ifc_class, discipline, base_hours, complexity_multiplier,
                 source, project_id, confidence_score, sample_size, last_updated)
                VALUES (?, NULL, ?, ?, ?, 'learned', ?, ?, ?, ?)
                ON CONFLICT(activity_type, ifc_class, discipline, project_id, source)
                DO UPDATE SET
                    base_hours = excluded.base_hours,
                    confidence_score = excluded.confidence_score,
                    sample_size = excluded.sample_size,
                    last_updated = excluded.last_updated
            """, (activity_type, discipline, new_base_estimate, complexity_multiplier,
                  project_id, confidence, sample_size, datetime.now()))

            updates_count += 1

    conn.commit()
    conn.close()

    return updates_count


def record_resolution_feedback(db_path: str, resolution_history_id: int,
                               user_rating: int, actual_hours: float,
                               variance_notes: str = None) -> bool:
    """
    Update resolution_history with user feedback.

    This is called AFTER the user completes the resolution work and
    provides feedback on how it went.

    Args:
        db_path: Path to database
        resolution_history_id: ID from resolution_history table
        user_rating: 1-5 stars
        actual_hours: Actual total hours spent
        variance_notes: Optional notes explaining variance

    Returns:
        True if successful, False if resolution_history_id not found
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if resolution exists
    cursor.execute("SELECT option_id FROM resolution_history WHERE history_id = ?",
                  (resolution_history_id,))
    if not cursor.fetchone():
        conn.close()
        return False

    # Get estimated hours for comparison
    cursor.execute("""
        SELECT ro.total_design_hours
        FROM resolution_history rh
        JOIN resolution_options ro ON rh.option_id = ro.option_id
        WHERE rh.history_id = ?
    """, (resolution_history_id,))

    row = cursor.fetchone()
    estimated_hours = row[0] if row else 0.0

    # Calculate variance
    variance_hours = actual_hours - estimated_hours
    variance_cost = 0.0  # TODO: Calculate based on discipline rates

    # Update resolution_history
    cursor.execute("""
        UPDATE resolution_history
        SET actual_design_hours = ?,
            user_rating = ?,
            implemented_date = ?,
            variance_hours = ?,
            variance_cost = ?,
            lessons_learned = ?
        WHERE history_id = ?
    """, (actual_hours, user_rating, datetime.now(), variance_hours, variance_cost,
          variance_notes, resolution_history_id))

    conn.commit()
    conn.close()

    return True


def get_learning_summary(db_path: str, activity_type: str = None,
                        discipline: str = None, project_id: str = None) -> List[Dict]:
    """
    Get learning metrics summary for dashboard/reporting.

    Args:
        db_path: Path to database
        activity_type: Optional filter by activity type
        discipline: Optional filter by discipline
        project_id: Optional filter by project

    Returns:
        List of dicts with variance statistics
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
        SELECT
            activity_type,
            discipline,
            COUNT(*) as sample_count,
            AVG(estimated_hours) as avg_estimated,
            AVG(actual_hours) as avg_actual,
            AVG(variance_percent) as avg_variance_pct,
            AVG(user_rating) as avg_rating,
            MIN(recorded_at) as first_sample,
            MAX(recorded_at) as latest_sample
        FROM learning_metrics
        WHERE 1=1
    """

    params = []

    if activity_type:
        query += " AND activity_type = ?"
        params.append(activity_type)

    if discipline:
        query += " AND discipline = ?"
        params.append(discipline)

    if project_id:
        query += " AND project_id = ?"
        params.append(project_id)

    query += """
        GROUP BY activity_type, discipline
        HAVING sample_count >= 3
        ORDER BY sample_count DESC
    """

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_confidence_indicator(db_path: str, activity_type: str, discipline: str,
                            project_id: str = None) -> Dict:
    """
    Get confidence indicator for a specific activity/discipline estimate.

    Returns confidence score, sample size, and source (learned vs default).

    Args:
        db_path: Path to database
        activity_type: Activity type
        discipline: Discipline
        project_id: Optional project filter

    Returns:
        dict with 'confidence_score', 'sample_size', 'source', 'base_hours'
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Try learned first
    cursor.execute("""
        SELECT base_hours, confidence_score, sample_size, source
        FROM activity_base_durations
        WHERE activity_type = ? AND discipline = ?
          AND source = 'learned'
          AND (project_id = ? OR ? IS NULL)
        ORDER BY confidence_score DESC
        LIMIT 1
    """, (activity_type, discipline, project_id, project_id))

    row = cursor.fetchone()

    if not row:
        # Fall back to default
        cursor.execute("""
            SELECT base_hours, confidence_score, sample_size, source
            FROM activity_base_durations
            WHERE activity_type = ? AND discipline = ?
              AND source = 'default'
            LIMIT 1
        """, (activity_type, discipline))

        row = cursor.fetchone()

    conn.close()

    if row:
        return dict(row)
    else:
        return {
            'base_hours': 0.0,
            'confidence_score': 0,
            'sample_size': 0,
            'source': 'none'
        }


if __name__ == "__main__":
    """
    Test learning engine with simulated feedback
    """
    import sys

    db_path = "/home/red1/Documents/bonsai/DatabaseFiles/clash_status.db"

    if len(sys.argv) > 1:
        db_path = sys.argv[1]

    print("=" * 60)
    print("LEARNING ENGINE TEST")
    print("=" * 60)

    # Get learning summary
    summary = get_learning_summary(db_path)

    if summary:
        print(f"\nLearning Metrics Summary ({len(summary)} activities):")
        for item in summary:
            print(f"\n  {item['activity_type']} ({item['discipline']})")
            print(f"    Samples: {item['sample_count']}")
            print(f"    Avg Estimated: {item['avg_estimated']:.1f}h")
            print(f"    Avg Actual: {item['avg_actual']:.1f}h")
            print(f"    Avg Variance: {item['avg_variance_pct']:.1f}%")
            print(f"    Avg Rating: {item['avg_rating']:.1f}⭐")
    else:
        print("\nNo learning metrics recorded yet.")
        print("Apply resolution options and submit feedback to start learning.")

    print("\n" + "=" * 60)
