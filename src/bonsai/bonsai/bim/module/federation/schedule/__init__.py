"""
4D Construction Scheduling Module
----------------------------------
Generates construction schedules from federation database with duration estimation.
Includes 4D animation for visualizing construction sequences in Blender.

Performance: animation_optimized.py handles 50k+ elements efficiently (10-15 seconds).
"""

__all__ = ["schedule_generator", "mpp_export", "database_schema", "animation", "animation_optimized", "excel_export"]
