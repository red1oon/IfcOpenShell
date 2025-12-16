# Bonsai - OpenBIM Blender Add-on
# River Carbon Credits - Blender Operators
# Interactive UI for carbon credit lifecycle management

"""
Carbon Credit Operators
========================
Blender N-Panel operators for creating and managing carbon credit batches.

UI Location: 3D Viewport N-Panel → River → Carbon Credits

Operators:
- Create Biochar Batch: Log new organic waste → biochar conversion
- Update Lab Results: Enter lab-verified carbon content
- Calculate LCA Emissions: Track transportation, energy use
"""

import bpy
from bpy.types import Operator, Panel
from bpy.props import FloatProperty, StringProperty, IntProperty, EnumProperty
import os
from pathlib import Path


class RIVER_OT_create_biochar_batch(Operator):
    """Create new biochar batch from selected equipment marker"""
    bl_idname = "river.create_biochar_batch"
    bl_label = "Create Biochar Batch"
    bl_description = "Log organic waste collection and calculate carbon sequestration"
    bl_options = {'REGISTER', 'UNDO'}

    # Input properties
    organic_waste_kg: FloatProperty(
        name="Organic Waste (kg)",
        description="Wet organic waste collected from boom site",
        default=1000.0,
        min=0.0,
        soft_max=10000.0
    )

    moisture_content_pct: FloatProperty(
        name="Moisture Content (%)",
        description="Moisture percentage before drying (40-60% typical)",
        default=50.0,
        min=0.0,
        max=100.0
    )

    processing_facility: EnumProperty(
        name="Processing Facility",
        description="Biochar production facility",
        items=[
            ('FACILITY_A', 'Facility A', 'Main pyrolysis plant'),
            ('FACILITY_B', 'Facility B', 'Secondary plant'),
            ('MOBILE_UNIT', 'Mobile Unit', 'Mobile pyrolysis unit')
        ],
        default='FACILITY_A'
    )

    boom_site_id: IntProperty(
        name="Boom Site ID",
        description="Equipment marker ID (auto-detected from selection)",
        default=1
    )

    @classmethod
    def poll(cls, context):
        """Only enable if in RIVER workspace or equipment marker selected"""
        return context.mode == 'OBJECT'

    def execute(self, context):
        """Create biochar batch in database"""
        try:
            # Import pipeline (lazy import to avoid Blender startup issues)
            from .biochar_pipeline import BiocharPipeline

            # Get database path from WORK_DIR (production database)
            work_dir = Path.home() / "Projects" / "IfcOpenShell" / "WORK_DIR" / "RIVER" / "databases"
            db_path = work_dir / "klang_river_perfect.db"

            if not db_path.exists():
                self.report({'ERROR'}, f"Database not found: {db_path}")
                return {'CANCELLED'}

            # Create pipeline and batch
            pipeline = BiocharPipeline(str(db_path))

            # Get GPS from selected object if available
            gps_lat, gps_lon = None, None
            if context.active_object and 'gps_lat' in context.active_object:
                gps_lat = context.active_object['gps_lat']
                gps_lon = context.active_object['gps_lon']

            # Create batch
            batch = pipeline.create_batch(
                boom_site_id=self.boom_site_id,
                organic_waste_kg=self.organic_waste_kg,
                moisture_content_pct=self.moisture_content_pct,
                processing_facility=self.processing_facility,
                gps_lat=gps_lat,
                gps_lon=gps_lon
            )

            # Store batch_id on active object for reference
            if context.active_object:
                context.active_object['latest_biochar_batch'] = batch.batch_id
                context.active_object['biochar_tco2e'] = round(batch.tco2e_sequestered, 3)

            self.report({'INFO'},
                f"✓ Batch {batch.batch_id} created | "
                f"{batch.biochar_output_kg:.1f}kg biochar | "
                f"{batch.tco2e_sequestered:.3f} tCO₂e | "
                f"RM {batch.revenue_rm:.2f} potential"
            )

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to create batch: {str(e)}")
            return {'CANCELLED'}


class RIVER_OT_update_biochar_lab_results(Operator):
    """Update biochar batch with lab-verified carbon content"""
    bl_idname = "river.update_biochar_lab_results"
    bl_label = "Update Lab Results"
    bl_description = "Enter lab-verified biochar properties and recalculate tCO₂e"
    bl_options = {'REGISTER', 'UNDO'}

    batch_id: StringProperty(
        name="Batch ID",
        description="Batch identifier (e.g., BIOCHAR_ABC12345)",
        default=""
    )

    actual_biochar_kg: FloatProperty(
        name="Actual Biochar (kg)",
        description="Lab-measured biochar output",
        default=250.0,
        min=0.0
    )

    carbon_content_pct: FloatProperty(
        name="Carbon Content (%)",
        description="Lab-verified carbon percentage (70-80% typical)",
        default=75.0,
        min=0.0,
        max=100.0
    )

    biochar_ph: FloatProperty(
        name="pH",
        description="Biochar pH (8-9 typical)",
        default=8.5,
        min=0.0,
        max=14.0
    )

    cation_exchange_capacity: FloatProperty(
        name="CEC (cmol/kg)",
        description="Cation Exchange Capacity for soil application",
        default=30.0,
        min=0.0
    )

    ash_content_pct: FloatProperty(
        name="Ash Content (%)",
        description="Ash percentage (10-20% typical)",
        default=15.0,
        min=0.0,
        max=100.0
    )

    def invoke(self, context, event):
        """Pre-fill batch_id from active object if available"""
        if context.active_object and 'latest_biochar_batch' in context.active_object:
            self.batch_id = context.active_object['latest_biochar_batch']
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        """Update batch with lab results"""
        try:
            from .biochar_pipeline import BiocharPipeline

            work_dir = Path.home() / "Projects" / "IfcOpenShell" / "WORK_DIR" / "RIVER" / "databases"
            db_path = work_dir / "klang_river_perfect.db"

            pipeline = BiocharPipeline(str(db_path))
            batch = pipeline.update_lab_results(
                batch_id=self.batch_id,
                actual_biochar_kg=self.actual_biochar_kg,
                carbon_content_pct=self.carbon_content_pct,
                biochar_ph=self.biochar_ph,
                cation_exchange_capacity=self.cation_exchange_capacity,
                ash_content_pct=self.ash_content_pct
            )

            # Update object properties
            if context.active_object:
                context.active_object['biochar_tco2e'] = round(batch.tco2e_sequestered, 3)

            self.report({'INFO'},
                f"✓ Lab results updated | "
                f"{batch.carbon_content_pct}% carbon | "
                f"{batch.tco2e_sequestered:.3f} tCO₂e"
            )

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to update lab results: {str(e)}")
            return {'CANCELLED'}


class RIVER_OT_calculate_lca_emissions(Operator):
    """Calculate 4-category LCA emissions for Puro.Earth certification"""
    bl_idname = "river.calculate_lca_emissions"
    bl_label = "Calculate LCA Emissions"
    bl_description = "Track transportation and energy use for Puro.Earth 2025 methodology"
    bl_options = {'REGISTER', 'UNDO'}

    batch_id: StringProperty(
        name="Batch ID",
        description="Batch identifier",
        default=""
    )

    transport_km: FloatProperty(
        name="Transport Distance (km)",
        description="Total transport distance (collection → facility → distribution)",
        default=50.0,
        min=0.0
    )

    diesel_liters: FloatProperty(
        name="Diesel Used (L)",
        description="Diesel fuel consumption for pyrolysis process",
        default=0.0,
        min=0.0
    )

    electricity_kwh: FloatProperty(
        name="Electricity (kWh)",
        description="Grid electricity consumed",
        default=500.0,
        min=0.0
    )

    natural_gas_m3: FloatProperty(
        name="Natural Gas (m³)",
        description="Natural gas for pyrolysis heating",
        default=100.0,
        min=0.0
    )

    def invoke(self, context, event):
        """Pre-fill batch_id from active object"""
        if context.active_object and 'latest_biochar_batch' in context.active_object:
            self.batch_id = context.active_object['latest_biochar_batch']
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        """Calculate and store LCA emissions"""
        try:
            from .biochar_pipeline import BiocharPipeline

            work_dir = Path.home() / "Projects" / "IfcOpenShell" / "WORK_DIR" / "RIVER" / "databases"
            db_path = work_dir / "klang_river_perfect.db"

            pipeline = BiocharPipeline(str(db_path))
            lca = pipeline.calculate_lca_emissions(
                batch_id=self.batch_id,
                transport_km=self.transport_km,
                diesel_liters=self.diesel_liters,
                electricity_kwh=self.electricity_kwh,
                natural_gas_m3=self.natural_gas_m3
            )

            # Store on object
            if context.active_object:
                context.active_object['net_carbon_removal'] = round(lca['net_carbon_removal'], 3)
                context.active_object['lca_total_emissions'] = round(lca['total_lca_emissions'], 3)

            self.report({'INFO'},
                f"✓ LCA calculated | "
                f"Total emissions: {lca['total_lca_emissions']:.3f} tCO₂e | "
                f"Net removal: {lca['net_carbon_removal']:.3f} tCO₂e "
                f"({lca['net_removal_pct']:.1f}% efficiency)"
            )

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to calculate LCA: {str(e)}")
            return {'CANCELLED'}


class RIVER_PT_carbon_credits(Panel):
    """N-Panel UI for carbon credit management"""
    bl_label = "Carbon Credits"
    bl_idname = "RIVER_PT_carbon_credits"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'River'
    bl_order = 2  # Position after equipment placement

    def draw(self, context):
        layout = self.layout
        obj = context.active_object

        # Header
        box = layout.box()
        box.label(text="🌱 Biochar Pipeline", icon='PLUGIN')

        # Show batch info if object has biochar data
        if obj and 'latest_biochar_batch' in obj:
            info_box = layout.box()
            info_box.label(text=f"Batch: {obj['latest_biochar_batch']}", icon='FILE_TICK')
            if 'biochar_tco2e' in obj:
                info_box.label(text=f"tCO₂e: {obj['biochar_tco2e']:.3f}")
            if 'net_carbon_removal' in obj:
                info_box.label(text=f"Net Removal: {obj['net_carbon_removal']:.3f} tCO₂e")

        # Operators
        layout.separator()
        layout.operator("river.create_biochar_batch", icon='ADD')
        layout.operator("river.update_biochar_lab_results", icon='EXPERIMENTAL')
        layout.operator("river.calculate_lca_emissions", icon='DRIVER')

        # Revenue summary
        layout.separator()
        revenue_box = layout.box()
        revenue_box.label(text="💰 Revenue Potential", icon='FUND')
        revenue_box.label(text="RM 630-850 per tCO₂e")
        revenue_box.label(text="Target: RM 201-488M/year")
