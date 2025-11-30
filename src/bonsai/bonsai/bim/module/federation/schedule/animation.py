"""
4D Construction Animation
-------------------------
Animates construction sequence in Blender viewport based on schedule data.

Sets visibility keyframes for elements based on their scheduled start/finish dates.
"""

import bpy
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


class ConstructionAnimator:
    """Handles 4D construction animation in Blender"""

    def __init__(self, db_path: str, frames_per_day: int = 2):
        """
        Initialize animator.

        Args:
            db_path: Path to federation database
            frames_per_day: How many Blender frames per calendar day (default: 2 = 12 frames/week)
        """
        self.db_path = db_path
        self.frames_per_day = frames_per_day
        self.project_start_date = None

    def get_schedule_data(self) -> List[Dict]:
        """
        Read schedule from database.

        Returns:
            List of tasks with start/finish dates and element matching criteria
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                task_id,
                task_name,
                ifc_class,
                discipline,
                storey,
                start_date,
                finish_date,
                phase
            FROM construction_schedule
            ORDER BY start_date, sequence
        """)

        tasks = []
        for row in cursor.fetchall():
            task = {
                'task_id': row[0],
                'task_name': row[1],
                'ifc_class': row[2],
                'discipline': row[3],
                'storey': row[4],
                'start_date': datetime.fromisoformat(row[5]) if row[5] else None,
                'finish_date': datetime.fromisoformat(row[6]) if row[6] else None,
                'phase': row[7],
            }
            tasks.append(task)

        conn.close()

        # Determine project start date (earliest task start)
        if tasks:
            self.project_start_date = min(t['start_date'] for t in tasks if t['start_date'])

        logger.info(f"📅 Loaded {len(tasks)} tasks, project starts {self.project_start_date}")
        return tasks

    def date_to_frame(self, date: datetime) -> int:
        """
        Convert date to Blender frame number.

        Args:
            date: Date to convert

        Returns:
            Frame number (1-based)
        """
        if not self.project_start_date:
            return 1

        days_elapsed = (date - self.project_start_date).days
        frame = 1 + (days_elapsed * self.frames_per_day)
        return int(frame)

    def get_element_objects(self, ifc_class: str, discipline: str, storey: str) -> List[bpy.types.Object]:
        """
        Find Blender objects matching task criteria.

        Args:
            ifc_class: IFC class (e.g., 'IfcDoor')
            discipline: Discipline code (e.g., 'ARC', 'STR')
            storey: Storey level (e.g., '1F', 'GF', 'ROOF', 'Unknown')

        Returns:
            List of matching Blender objects
        """
        objects = []

        # Check if storey matching should be skipped (Unknown or empty)
        skip_storey_match = storey in ('Unknown', '', None)

        # Handle multi-storey ranges (e.g., "4F-6F")
        storey_list = []
        if not skip_storey_match and '-' in storey:
            # Parse range like "4F-6F"
            parts = storey.split('-')
            start = parts[0]
            end = parts[1]
            # Extract floor numbers
            start_num = int(start.replace('F', ''))
            end_num = int(end.replace('F', ''))
            storey_list = [f"{i}F" for i in range(start_num, end_num + 1)]
        else:
            storey_list = [storey]

        for obj in bpy.context.scene.objects:
            # Check if object has minimum required properties
            if 'ifc_class' not in obj or 'discipline' not in obj:
                continue

            # Match by IFC class and discipline (always required)
            obj_ifc_class = obj.get('ifc_class', '')
            obj_discipline = obj.get('discipline', '')

            # Basic match
            if obj_ifc_class != ifc_class or obj_discipline != discipline:
                continue

            # Storey matching (if data available)
            if skip_storey_match:
                # Storey is Unknown - match all objects of this type/discipline
                objects.append(obj)
            elif 'storey' in obj:
                # Storey matching available
                obj_storey = obj.get('storey', '')
                if obj_storey in storey_list:
                    objects.append(obj)
            # If obj has no storey property but schedule requires it, skip object

        return objects

    def set_visibility_keyframes(self, obj: bpy.types.Object, start_frame: int, finish_frame: int):
        """
        Set visibility animation keyframes for an object.

        Animation pattern:
        - Frame 0: Hidden
        - Frame start_frame - 1: Hidden
        - Frame start_frame: Visible (construction starts)
        - Frame finish_frame: Visible (construction complete)
        - After: Remains visible

        Args:
            obj: Blender object
            start_frame: Frame when construction starts
            finish_frame: Frame when construction finishes
        """
        # Ensure object is valid and in scene
        if obj is None or obj.name not in bpy.context.scene.objects:
            return

        # Set initial state (hidden)
        obj.hide_viewport = True
        obj.hide_render = True
        obj.keyframe_insert(data_path="hide_viewport", frame=0)
        obj.keyframe_insert(data_path="hide_render", frame=0)

        # Hidden just before construction starts
        if start_frame > 1:
            obj.hide_viewport = True
            obj.hide_render = True
            obj.keyframe_insert(data_path="hide_viewport", frame=start_frame - 1)
            obj.keyframe_insert(data_path="hide_render", frame=start_frame - 1)

        # Visible when construction starts
        obj.hide_viewport = False
        obj.hide_render = False
        obj.keyframe_insert(data_path="hide_viewport", frame=start_frame)
        obj.keyframe_insert(data_path="hide_render", frame=start_frame)

        # Optional: Add fade-in effect using alpha (if material supports it)
        # For now, simple visibility toggle

        logger.debug(f"Set keyframes for {obj.name}: visible from frame {start_frame}")

    def animate_construction(self) -> Dict:
        """
        Create 4D construction animation.

        Returns:
            Statistics dict with animation info
        """
        # Load schedule
        tasks = self.get_schedule_data()

        if not tasks:
            logger.warning("No tasks found in schedule")
            return {'success': False, 'message': 'No tasks in schedule'}

        # Analyze scene objects
        scene_objects = [obj for obj in bpy.context.scene.objects if 'ifc_class' in obj and 'discipline' in obj]
        logger.info(f"📦 Scene has {len(scene_objects)} IFC objects (out of {len(bpy.context.scene.objects)} total)")

        if len(scene_objects) == 0:
            logger.warning("⚠ No objects have required properties (ifc_class, discipline)")
            logger.warning("   Animation will run but may not affect any objects")

        # Statistics
        stats = {
            'tasks_processed': 0,
            'objects_animated': 0,
            'start_frame': None,
            'end_frame': None,
            'project_duration_days': None,
        }

        # Process each task
        animated_objects = set()

        for task in tasks:
            if not task['start_date'] or not task['finish_date']:
                logger.warning(f"Task {task['task_name']} missing dates, skipping")
                continue

            # Convert dates to frames
            start_frame = self.date_to_frame(task['start_date'])
            finish_frame = self.date_to_frame(task['finish_date'])

            # Track timeline range
            if stats['start_frame'] is None or start_frame < stats['start_frame']:
                stats['start_frame'] = start_frame
            if stats['end_frame'] is None or finish_frame > stats['end_frame']:
                stats['end_frame'] = finish_frame

            # Find matching objects
            objects = self.get_element_objects(
                task['ifc_class'],
                task['discipline'],
                task['storey']
            )

            # Animate each object
            newly_animated = 0
            for obj in objects:
                if obj not in animated_objects:
                    self.set_visibility_keyframes(obj, start_frame, finish_frame)
                    animated_objects.add(obj)
                    newly_animated += 1

            stats['tasks_processed'] += 1

            # Log with more detail for debugging
            if newly_animated > 0:
                logger.info(f"✓ {task['task_name']}: {newly_animated} objects animated, frames {start_frame}-{finish_frame}")
            else:
                logger.debug(f"⚠ {task['task_name']}: No new objects (already animated or not found)")

        stats['objects_animated'] = len(animated_objects)

        # Set Blender timeline range
        if stats['start_frame'] and stats['end_frame']:
            bpy.context.scene.frame_start = 0
            bpy.context.scene.frame_end = stats['end_frame'] + 10  # Add padding
            bpy.context.scene.frame_current = 0

            # Calculate project duration
            total_frames = stats['end_frame'] - stats['start_frame']
            stats['project_duration_days'] = total_frames / self.frames_per_day

        stats['success'] = True
        stats['message'] = f"Animated {stats['objects_animated']} objects across {stats['tasks_processed']} tasks"

        logger.info(f"🎬 Animation complete: {stats['message']}")
        logger.info(f"Timeline: Frame 0 → {stats['end_frame']} ({stats['project_duration_days']:.1f} days)")

        return stats


def animate_construction_sequence(db_path: str, frames_per_day: int = 2) -> Dict:
    """
    Main entry point for construction animation.

    Args:
        db_path: Path to federation database
        frames_per_day: Blender frames per calendar day

    Returns:
        Statistics dict
    """
    animator = ConstructionAnimator(db_path, frames_per_day)
    return animator.animate_construction()
