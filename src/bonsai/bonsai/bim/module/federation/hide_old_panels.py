"""
Temporary patch to hide old Project Overview panels for clean POC
==================================================================
This module modifies poll methods to hide clutter during POC testing.
"""

import bpy

def hide_old_project_panels():
    """Hide old Project Overview panels that aren't needed for POC"""

    # List of panel classes to hide
    panels_to_hide = [
        "BIM_PT_project",  # Project info panel
        "BIM_PT_project_library",  # Library references
        "BIM_PT_bsdd",  # buildingSMART Data Dictionary
        "BIM_PT_classification",  # Classification systems
        "BIM_PT_pset_template",  # Pset templates
        "BIM_PT_document_information",  # Document management
        "BIM_PT_constraint",  # Constraints
        "BIM_PT_ifcgit",  # IFC Git (kept if needed)
        "BIM_PT_attributes",  # Attribute editor
    ]

    # Disable by overriding poll methods
    for panel_name in panels_to_hide:
        panel_class = getattr(bpy.types, panel_name, None)
        if panel_class:
            # Save original poll method
            if not hasattr(panel_class, '_original_poll'):
                panel_class._original_poll = panel_class.poll
            # Override with always-false poll
            panel_class.poll = classmethod(lambda cls, context: False)
            print(f"Hidden: {panel_name}")

def restore_old_project_panels():
    """Restore old Project panels if needed"""

    panels = [
        "BIM_PT_project",
        "BIM_PT_project_library",
        "BIM_PT_bsdd",
        "BIM_PT_classification",
        "BIM_PT_pset_template",
        "BIM_PT_document_information",
        "BIM_PT_constraint",
        "BIM_PT_ifcgit",
        "BIM_PT_attributes",
    ]

    for panel_name in panels:
        panel_class = getattr(bpy.types, panel_name, None)
        if panel_class and hasattr(panel_class, '_original_poll'):
            panel_class.poll = panel_class._original_poll
            delattr(panel_class, '_original_poll')
            print(f"Restored: {panel_name}")