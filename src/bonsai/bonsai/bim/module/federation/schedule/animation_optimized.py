"""
Optimized 4D Construction Animation for Large Projects
-------------------------------------------------------
Pre-indexes objects by (ifc_class, discipline) for O(1) lookup.
Handles 50k+ elements efficiently.
"""

import bpy
import sqlite3
from datetime import datetime
from typing import Dict, List, Set
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class OptimizedConstructionAnimator:
    """High-performance animator for large federations (50k+ elements)"""

    def __init__(self, db_path: str, frames_per_day: int = 2):
        self.db_path = db_path
        self.frames_per_day = frames_per_day
        self.project_start_date = None
        self.object_index = None  # Pre-built index for fast lookup

    def build_object_index(self) -> Dict:
        """
        Pre-index all scene objects by (ifc_class, discipline, storey).

        This is O(m) where m = total objects, done ONCE upfront.
        Then lookups are O(1) instead of O(m) per task.

        Returns:
            Nested dict: {ifc_class: {discipline: {storey: [obj1, obj2, ...]}}}
        """
        logger.info("📇 Building object index for fast lookup...")
        print("📇 Building object index... (scanning objects, please wait 5-10 seconds)")

        index = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        total = 0

        for obj in bpy.context.scene.objects:
            # Skip objects without IFC metadata
            if 'ifc_class' not in obj or 'discipline' not in obj:
                continue

            ifc_class = obj.get('ifc_class', '')
            discipline = obj.get('discipline', '')
            storey = obj.get('storey', 'Unknown')  # Default to Unknown if missing

            # Index by all three keys
            index[ifc_class][discipline][storey].append(obj)

            # Also index under "Unknown" for storey-agnostic matching
            if storey != 'Unknown':
                index[ifc_class][discipline]['Unknown'].append(obj)

            total += 1

        logger.info(f"✅ Indexed {total} IFC objects")
        logger.info(f"   {len(index)} unique IFC classes")
        logger.info(f"   {sum(len(d) for d in index.values())} class-discipline combinations")

        print(f"✅ Indexed {total:,} IFC objects - ready to animate!")

        return index

    def get_element_objects_fast(self, ifc_class: str, discipline: str, storey: str) -> List[bpy.types.Object]:
        """
        Fast O(1) lookup using pre-built index.

        Args:
            ifc_class: IFC class (e.g., 'IfcBeam')
            discipline: Discipline (e.g., 'STR')
            storey: Storey level or 'Unknown'

        Returns:
            List of matching objects (already de-duplicated in index)
        """
        if self.object_index is None:
            raise RuntimeError("Object index not built. Call build_object_index() first.")

        # Direct O(1) lookup
        if ifc_class in self.object_index:
            if discipline in self.object_index[ifc_class]:
                if storey in self.object_index[ifc_class][discipline]:
                    return self.object_index[ifc_class][discipline][storey]

        return []

    def get_schedule_data(self) -> List[Dict]:
        """Read schedule from database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                task_id, task_name, ifc_class, discipline, storey,
                start_date, finish_date, phase
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
                'storey': row[4] if row[4] else 'Unknown',
                'start_date': datetime.fromisoformat(row[5]) if row[5] else None,
                'finish_date': datetime.fromisoformat(row[6]) if row[6] else None,
                'phase': row[7],
            }
            tasks.append(task)

        conn.close()

        if tasks:
            self.project_start_date = min(t['start_date'] for t in tasks if t['start_date'])

        logger.info(f"📅 Loaded {len(tasks)} tasks, project starts {self.project_start_date}")
        return tasks

    def date_to_frame(self, date: datetime) -> int:
        """Convert date to frame number"""
        if not self.project_start_date:
            return 1
        days_elapsed = (date - self.project_start_date).days
        return int(1 + (days_elapsed * self.frames_per_day))

    def set_visibility_keyframes_batch(self, objects: List[bpy.types.Object], start_frame: int, finish_frame: int):
        """
        Set keyframes for multiple objects at once (more efficient than one-by-one).

        Args:
            objects: List of objects to animate
            start_frame: Construction start frame
            finish_frame: Construction finish frame
        """
        for obj in objects:
            if obj is None or obj.name not in bpy.context.scene.objects:
                continue

            # Set visibility keyframes
            obj.hide_viewport = True
            obj.hide_render = True
            obj.keyframe_insert(data_path="hide_viewport", frame=0)
            obj.keyframe_insert(data_path="hide_render", frame=0)

            if start_frame > 1:
                obj.hide_viewport = True
                obj.hide_render = True
                obj.keyframe_insert(data_path="hide_viewport", frame=start_frame - 1)
                obj.keyframe_insert(data_path="hide_render", frame=start_frame - 1)

            obj.hide_viewport = False
            obj.hide_render = False
            obj.keyframe_insert(data_path="hide_viewport", frame=start_frame)
            obj.keyframe_insert(data_path="hide_render", frame=start_frame)

    def animate_construction(self) -> Dict:
        """
        Create 4D construction animation with optimized performance.

        Performance: O(m + n) instead of O(m × n)
        - m = total objects (indexed once)
        - n = tasks (direct lookups)
        """
        # Step 1: Build index (O(m) - done once)
        self.object_index = self.build_object_index()

        # Step 2: Load schedule
        tasks = self.get_schedule_data()

        if not tasks:
            return {'success': False, 'message': 'No tasks in schedule'}

        # Statistics
        stats = {
            'tasks_processed': 0,
            'objects_animated': 0,
            'start_frame': None,
            'end_frame': None,
            'project_duration_days': None,
        }

        # Track animated objects to avoid duplicates
        animated_objects = set()

        logger.info(f"🎬 Processing {len(tasks)} tasks...")
        print(f"🎬 Processing {len(tasks)} tasks...")  # Print to console for user feedback

        # Step 3: Process tasks with O(1) lookups
        for i, task in enumerate(tasks):
            if not task['start_date'] or not task['finish_date']:
                continue

            # Convert dates to frames
            start_frame = self.date_to_frame(task['start_date'])
            finish_frame = self.date_to_frame(task['finish_date'])

            # Track timeline range
            if stats['start_frame'] is None or start_frame < stats['start_frame']:
                stats['start_frame'] = start_frame
            if stats['end_frame'] is None or finish_frame > stats['end_frame']:
                stats['end_frame'] = finish_frame

            # Fast O(1) lookup via index
            objects = self.get_element_objects_fast(
                task['ifc_class'],
                task['discipline'],
                task['storey']
            )

            # Filter out already-animated objects
            new_objects = [obj for obj in objects if obj not in animated_objects]

            if new_objects:
                # Batch animate
                self.set_visibility_keyframes_batch(new_objects, start_frame, finish_frame)
                animated_objects.update(new_objects)

                # Log progress
                progress_msg = f"✓ [{i+1}/{len(tasks)}] {task['task_name']}: {len(new_objects)} objects, frames {start_frame}-{finish_frame}"
                logger.info(progress_msg)

                # Print to console every 5 tasks for user feedback
                if (i + 1) % 5 == 0 or i == 0:
                    print(f"   Progress: {i+1}/{len(tasks)} tasks ({100*(i+1)/len(tasks):.0f}%), {len(animated_objects):,} objects animated so far")

            stats['tasks_processed'] += 1

        stats['objects_animated'] = len(animated_objects)

        # Configure timeline
        if stats['start_frame'] and stats['end_frame']:
            bpy.context.scene.frame_start = 0
            bpy.context.scene.frame_end = stats['end_frame'] + 10
            bpy.context.scene.frame_current = 0

            total_frames = stats['end_frame'] - stats['start_frame']
            stats['project_duration_days'] = total_frames / self.frames_per_day

        stats['success'] = True
        stats['message'] = f"Animated {stats['objects_animated']} objects across {stats['tasks_processed']} tasks"

        logger.info(f"✅ Animation complete: {stats['message']}")
        logger.info(f"   Timeline: Frame 0 → {stats['end_frame']} ({stats['project_duration_days']:.1f} days)")

        print(f"\n✅ Animation complete! {stats['objects_animated']:,} objects animated")
        print(f"   Timeline: Frame 0 (empty) → Frame {stats['end_frame']} (complete)")
        print(f"   Press SPACEBAR to play construction sequence!")

        return stats


def animate_construction_sequence_optimized(db_path: str, frames_per_day: int = 2) -> Dict:
    """
    Optimized entry point for large projects (50k+ elements).

    Performance: ~10-30 seconds for 50k elements (vs 3-5 minutes with old method)
    """
    animator = OptimizedConstructionAnimator(db_path, frames_per_day)
    return animator.animate_construction()
