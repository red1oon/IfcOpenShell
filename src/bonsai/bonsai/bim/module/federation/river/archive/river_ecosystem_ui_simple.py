# Simplified River Ecosystem UI that will load properly
# This version has minimal dependencies and proper structure

try:
    import bpy
    from bpy.types import Panel, Operator
    from pathlib import Path
except ImportError:
    # Not in Blender environment
    pass

class BIM_PT_river_ecosystem(Panel):
    """River Ecosystem Model - Dynamic 3D monitoring for Klang River"""
    bl_label = "11. River Ecosystem Model"
    bl_idname = "BIM_PT_river_ecosystem"
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "scene"
    bl_parent_id = "BIM_PT_tabs"
    bl_options = {"DEFAULT_CLOSED"}
    bl_order = 11

    def draw(self, context):
        layout = self.layout

        # Header
        header_box = layout.box()
        header_box.label(text="🌊 Klang River Ecosystem", icon="WORLD")

        # Quick Launch
        col = layout.column(align=True)
        col.scale_y = 1.5
        col.operator("bim.run_klang_realistic_monitor",
                     icon="OUTLINER_OB_LIGHT",
                     text="Launch Realistic Monitor")

        layout.separator()
        col = layout.column(align=True)
        col.operator("bim.run_infrastructure_model",
                     icon="SETTINGS",
                     text="Infrastructure Model")
        col.operator("bim.run_storm_simulation",
                     icon="LIGHT_HEMI",
                     text="Storm Simulation")


class BIM_OT_run_klang_realistic_monitor(Operator):
    bl_idname = "bim.run_klang_realistic_monitor"
    bl_label = "Run Klang River Monitor"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        script_path = "/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/RiverEcoModel/klang_river_realistic_monitor.py"
        try:
            with open(script_path, 'r') as f:
                exec(f.read(), {'__name__': '__main__'})
            self.report({'INFO'}, "✓ Monitor launched")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}


class BIM_OT_run_infrastructure_model(Operator):
    bl_idname = "bim.run_infrastructure_model"
    bl_label = "Run Infrastructure Model"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        script_path = "/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/RiverEcoModel/klang_infrastructure_model.py"
        try:
            with open(script_path, 'r') as f:
                exec(f.read(), {'__name__': '__main__'})
            self.report({'INFO'}, "✓ Infrastructure loaded")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}


class BIM_OT_run_storm_simulation(Operator):
    bl_idname = "bim.run_storm_simulation"
    bl_label = "Run Storm Simulation"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        script_path = "/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/RiverEcoModel/test_storm_scenario.py"
        try:
            with open(script_path, 'r') as f:
                exec(f.read(), {'__name__': '__main__'})
            self.report({'INFO'}, "✓ Storm simulation started")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}


# Registration
classes = (
    BIM_PT_river_ecosystem,
    BIM_OT_run_klang_realistic_monitor,
    BIM_OT_run_infrastructure_model,
    BIM_OT_run_storm_simulation,
)

def register():
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except:
            pass

def unregister():
    for cls in reversed(classes):
        try:
            bpy.utils.unregister_class(cls)
        except:
            pass