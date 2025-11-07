"""
Snapshot Manager for Clash Resolution Reports

Manages before/after snapshot generation for clash groups using the
existing BCF snapshot renderer. Creates visual documentation showing
clashes and their proposed resolutions.
"""

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import mathutils

# Import BCF snapshot renderer
try:
    from ...bcf.snapshot_renderer import SnapshotRenderer
    BCF_AVAILABLE = True
except ImportError:
    BCF_AVAILABLE = False
    print("Warning: BCF snapshot renderer not available")


class SnapshotManager:
    """
    Manages snapshot generation for clash resolution reports.

    Creates before/after images showing:
    - Before: Current state with clashes highlighted
    - After: Proposed resolution (conceptual - same view for now)
    """

    def __init__(self, database_path: str):
        """
        Initialize snapshot manager.

        Args:
            database_path: Path to clash detection database
        """
        self.database_path = database_path
        self.renderer = None

        if BCF_AVAILABLE:
            self.renderer = SnapshotRenderer(database_path)
        else:
            print("⚠️  Snapshot generation requires BCF module")
            print("   Snapshots will be skipped in report")

    def generate_group_snapshots(
        self,
        group_id: int,
        output_dir: Path,
        width: int = 1920,
        height: int = 1080
    ) -> Tuple[bool, str]:
        """
        Generate clash overview snapshot for a clash group.

        Shows current state with clashes highlighted in red.
        Engineers visualize proposed changes in their BIM software.

        Args:
            group_id: Clash group ID
            output_dir: Directory to save snapshots
            width: Image width in pixels
            height: Image height in pixels

        Returns:
            Tuple of (success: bool, message: str)
        """
        if not BCF_AVAILABLE or not self.renderer:
            return False, "BCF snapshot renderer not available"

        try:
            # Get clash group data
            conn = sqlite3.connect(self.database_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get root element for camera positioning
            cursor.execute("""
                SELECT
                    cascade_element_guid as root_element_guid,
                    cascade_element_class as root_element_type
                FROM clash_groups
                WHERE group_id = ?
            """, (group_id,))

            group = cursor.fetchone()
            if not group:
                conn.close()
                return False, f"Group {group_id} not found"

            # Get ALL clashes in this cascade group (not just one representative)
            cursor.execute("""
                SELECT cs.guid_a, cs.guid_b
                FROM clash_group_members cgm
                JOIN clash_status cs ON cgm.clash_id = cs.clash_id
                WHERE cgm.group_id = ?
            """, (group_id,))

            clash_rows = cursor.fetchall()
            if not clash_rows:
                conn.close()
                return False, f"No clashes found for group {group_id}"

            # Collect all unique GUIDs from all clashes in the group
            all_guids = set()
            for row in clash_rows:
                all_guids.add(row['guid_a'])
                all_guids.add(row['guid_b'])
            all_guids = list(all_guids)

            print(f"  Cascade group {group_id}: {len(clash_rows)} clashes, {len(all_guids)} unique elements")

            # Get element position from database
            cursor.execute("""
                SELECT center_x, center_y, center_z
                FROM element_transforms
                WHERE guid = ?
            """, (group['root_element_guid'],))

            transform = cursor.fetchone()
            if not transform:
                conn.close()
                return False, f"Element transform not found for {group['root_element_guid']}"

            conn.close()

            # Calculate camera viewpoint (isometric view)
            element_center = mathutils.Vector((
                transform['center_x'],
                transform['center_y'],
                transform['center_z']
            ))

            # Isometric camera offset (45° horizontal, 35° vertical)
            camera_distance = 10.0  # meters
            camera_offset = mathutils.Vector((
                camera_distance * 0.707,  # cos(45°)
                camera_distance * 0.707,  # sin(45°)
                camera_distance * 0.574   # sin(35°)
            ))

            camera_location = element_center + camera_offset

            viewpoint_data = {
                'camera_location': list(camera_location),
                'target_location': list(element_center),
                'camera_up_vector': [0, 0, 1],  # Z-up
            }

            # Generate cascade group snapshot showing ALL affected elements
            # Highlights all elements in cascade group (not just one clash pair)
            # Note: Engineers visualize proposed changes in their BIM software (Revit/Blender)
            # No "after" snapshot needed for POC
            snapshot_file = output_dir / f"group_{group_id}_overview.png"
            snapshot_bytes = self.renderer.render_group_snapshot(
                guids=all_guids,  # All unique GUIDs from cascade group
                viewpoint_data=viewpoint_data,
                width=width,
                height=height,
                target_size_kb=300
            )

            if snapshot_bytes:
                snapshot_file.write_bytes(snapshot_bytes)
                return True, f"Snapshot created: {snapshot_file.name}"
            else:
                return False, f"Failed to render snapshot for group {group_id}"

        except Exception as e:
            return False, f"Snapshot generation failed: {str(e)}"

    def generate_all_group_snapshots(
        self,
        output_dir: Path,
        width: int = 1920,
        height: int = 1080,
        progress_callback=None
    ) -> Tuple[int, int, List[str]]:
        """
        Generate snapshots for all clash groups in database.

        Args:
            output_dir: Directory to save snapshots
            width: Image width
            height: Image height
            progress_callback: Optional callback function(current, total, message)

        Returns:
            Tuple of (successful: int, failed: int, error_messages: List[str])
        """
        if not BCF_AVAILABLE or not self.renderer:
            return 0, 0, ["BCF snapshot renderer not available"]

        # Get all group IDs
        conn = sqlite3.connect(self.database_path)
        cursor = conn.cursor()
        cursor.execute("SELECT group_id FROM clash_groups ORDER BY group_id")
        group_ids = [row[0] for row in cursor.fetchall()]
        conn.close()

        if not group_ids:
            return 0, 0, ["No clash groups found"]

        # Create snapshots directory
        snapshots_dir = output_dir / "snapshots"
        snapshots_dir.mkdir(parents=True, exist_ok=True)

        # Generate snapshots for each group
        successful = 0
        failed = 0
        error_messages = []

        total = len(group_ids)
        for idx, group_id in enumerate(group_ids, 1):
            if progress_callback:
                progress_callback(idx, total, f"Generating snapshots for group {group_id}...")

            success, message = self.generate_group_snapshots(
                group_id,
                snapshots_dir,
                width,
                height
            )

            if success:
                successful += 1
            else:
                failed += 1
                error_messages.append(f"Group {group_id}: {message}")

        return successful, failed, error_messages

    def estimate_snapshot_time(self, num_groups: int) -> float:
        """
        Estimate time to generate snapshots for given number of groups.

        Args:
            num_groups: Number of clash groups

        Returns:
            Estimated time in seconds
        """
        # Fast mode: ~1 second per snapshot
        # Each group needs 1 snapshot (overview with clashes highlighted)
        seconds_per_snapshot = 1.0
        snapshots_per_group = 1

        return num_groups * snapshots_per_group * seconds_per_snapshot

    def check_snapshot_feasibility(
        self,
        num_groups: int,
        max_time_seconds: float = 300
    ) -> Tuple[bool, str]:
        """
        Check if snapshot generation is feasible within time limit.

        Args:
            num_groups: Number of groups to generate snapshots for
            max_time_seconds: Maximum acceptable time (default 5 minutes)

        Returns:
            Tuple of (feasible: bool, message: str)
        """
        estimated_time = self.estimate_snapshot_time(num_groups)

        if estimated_time <= max_time_seconds:
            return True, f"Estimated time: {estimated_time:.0f}s (within {max_time_seconds:.0f}s limit)"
        else:
            return False, f"Estimated time: {estimated_time:.0f}s (exceeds {max_time_seconds:.0f}s limit)"
