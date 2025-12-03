"""
Hide non-Federation panels from Project Overview tab
"""
import bpy

def hide_other_project_panels():
    """Hide all non-Federation panels from Project Overview tab"""

    # List of panels to hide (non-Federation panels in Project Overview)
    panels_to_hide = [
        "BIM_PT_project",  # Current Project panel
        "BIM_PT_ifcgit",   # IFC Git panel
    ]

    for panel_name in panels_to_hide:
        if hasattr(bpy.types, panel_name):
            panel = getattr(bpy.types, panel_name)
            # Add poll method that returns False
            original_poll = getattr(panel, 'poll', None)

            @classmethod
            def disabled_poll(cls, context):
                return False  # Always hide

            panel.poll = disabled_poll
            print(f"✓ Disabled {panel_name}")