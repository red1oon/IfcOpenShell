# Bonsai - OpenBIM Blender Add-on
# Copyright (C) 2025 Your Engineering Firm
#
# This file is part of Bonsai.
#
# Bonsai is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
Clash Resolution Report Generation Module
==========================================

Generates professional Markdown reports for clash resolution meetings.

Files:
- report_generator.py: Main report generation logic (queries DB, renders Markdown)
- snapshot_manager.py: Snapshot rendering (before/after images)
- templates/report_template.md.j2: Jinja2 template for report structure
"""

from .report_generator import ReportGenerator

__all__ = ["ReportGenerator"]
