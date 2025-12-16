# Bonsai - OpenBIM Blender Add-on
# River Carbon Credits Module
# Phase 1: Biochar, Mangrove, and Plastic Credits Tracking

"""
Carbon Credits System
=====================
Monitoring, Reporting, and Verification (MRV) for circular economy revenue streams.

Revenue Potential:
- Biochar Carbon Credits: RM 201.6M - 488.75M/year
- Mangrove Blue Carbon: RM 4.5M - 11.55M/year
- Plastic Credits: RM 11.75M - 70.5M/year

Modules:
- biochar_pipeline: Biochar batch tracking with Puro.Earth 2025 methodology
- credit_operators: Blender operators for carbon credit workflows
"""

from . import biochar_pipeline
from . import credit_operators

# Expose classes for registration
classes = (
    credit_operators.RIVER_OT_create_biochar_batch,
    credit_operators.RIVER_OT_update_biochar_lab_results,
    credit_operators.RIVER_OT_calculate_lca_emissions,
    credit_operators.RIVER_PT_carbon_credits,
)


def register():
    """Called when carbon_credits module is registered"""
    pass


def unregister():
    """Called when carbon_credits module is unregistered"""
    pass
