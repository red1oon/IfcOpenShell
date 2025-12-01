"""
Construction Theme Color Palette for BIM Federation
Interactive color chooser with discipline/type filters and undo
"""

import bpy
from bpy.props import (
    StringProperty,
    FloatVectorProperty,
    EnumProperty,
    BoolProperty,
    CollectionProperty
)
from bpy.types import PropertyGroup, Operator, Panel
import sqlite3
import os
from pathlib import Path


# Construction theme color presets
CONSTRUCTION_PALETTES = {
    "Realistic": {
        "name": "Realistic Materials",
        "colors": [
            ("Concrete", (0.75, 0.70, 0.65, 1.0)),
            ("Light Concrete", (0.85, 0.82, 0.78, 1.0)),
            ("Dark Concrete", (0.60, 0.55, 0.50, 1.0)),
            ("White Wall", (0.95, 0.95, 0.93, 1.0)),
            ("Off White", (0.90, 0.88, 0.85, 1.0)),
            ("Wood Light", (0.70, 0.55, 0.40, 1.0)),
            ("Wood Medium", (0.55, 0.35, 0.20, 1.0)),
            ("Wood Dark", (0.35, 0.25, 0.15, 1.0)),
            ("Steel", (0.50, 0.50, 0.52, 1.0)),
            ("Aluminum", (0.70, 0.72, 0.75, 1.0)),
            ("Glass Clear", (0.70, 0.85, 0.90, 1.0)),
            ("Glass Tinted", (0.40, 0.50, 0.55, 1.0)),
            ("Brick Red", (0.60, 0.30, 0.25, 1.0)),
            ("Roof Dark", (0.25, 0.22, 0.20, 1.0)),
            ("Insulation Pink", (0.95, 0.70, 0.75, 1.0)),
            ("Ground", (0.45, 0.40, 0.35, 1.0)),
        ]
    },
    "Construction Phase": {
        "name": "Phase Colors",
        "colors": [
            ("Foundation", (0.40, 0.35, 0.30, 1.0)),
            ("Structure", (0.70, 0.65, 0.60, 1.0)),
            ("Envelope", (0.85, 0.75, 0.65, 1.0)),
            ("Interior", (0.90, 0.85, 0.80, 1.0)),
            ("MEP Rough", (0.50, 0.60, 0.70, 1.0)),
            ("Finishes", (0.95, 0.90, 0.85, 1.0)),
            ("Phase 1", (0.80, 0.40, 0.40, 1.0)),
            ("Phase 2", (0.40, 0.70, 0.40, 1.0)),
            ("Phase 3", (0.40, 0.40, 0.80, 1.0)),
            ("Phase 4", (0.80, 0.80, 0.40, 1.0)),
            ("Temporary", (1.00, 0.50, 0.00, 1.0)),
            ("Existing", (0.60, 0.60, 0.60, 1.0)),
            ("Demolish", (1.00, 0.00, 0.00, 1.0)),
            ("New Work", (0.00, 1.00, 0.00, 1.0)),
            ("Future", (0.50, 0.50, 1.00, 1.0)),
            ("Complete", (0.30, 0.30, 0.30, 1.0)),
        ]
    },
    "Safety Status": {
        "name": "Safety Colors",
        "colors": [
            ("Safe Green", (0.00, 0.80, 0.00, 1.0)),
            ("Caution Yellow", (1.00, 0.90, 0.00, 1.0)),
            ("Warning Orange", (1.00, 0.60, 0.00, 1.0)),
            ("Danger Red", (1.00, 0.00, 0.00, 1.0)),
            ("Info Blue", (0.00, 0.50, 1.00, 1.0)),
            ("Inspected", (0.00, 0.60, 0.40, 1.0)),
            ("Not Inspected", (0.80, 0.80, 0.00, 1.0)),
            ("Failed", (0.80, 0.00, 0.00, 1.0)),
            ("Restricted", (0.60, 0.00, 0.60, 1.0)),
            ("Emergency", (1.00, 0.00, 0.50, 1.0)),
            ("Exit Route", (0.00, 1.00, 0.50, 1.0)),
            ("Fire Equipment", (1.00, 0.20, 0.20, 1.0)),
            ("First Aid", (1.00, 1.00, 1.00, 1.0)),
            ("PPE Required", (0.00, 0.00, 1.00, 1.0)),
            ("Hazard Zone", (1.00, 0.50, 0.00, 1.0)),
            ("Clear", (0.70, 0.70, 0.70, 1.0)),
        ]
    },
    "Discipline": {
        "name": "Discipline Colors",
        "colors": [
            ("Architecture", (0.80, 0.75, 0.70, 1.0)),
            ("Structure", (0.60, 0.65, 0.70, 1.0)),
            ("MEP", (0.40, 0.60, 0.80, 1.0)),
            ("Electrical", (1.00, 0.80, 0.00, 1.0)),
            ("Plumbing", (0.00, 0.60, 0.40, 1.0)),
            ("HVAC", (0.60, 0.80, 1.00, 1.0)),
            ("Fire Protection", (1.00, 0.20, 0.20, 1.0)),
            ("Civil", (0.50, 0.40, 0.30, 1.0)),
            ("Landscape", (0.30, 0.60, 0.30, 1.0)),
            ("Interiors", (0.90, 0.85, 0.80, 1.0)),
            ("Signage", (0.00, 0.40, 0.80, 1.0)),
            ("Equipment", (0.70, 0.70, 0.75, 1.0)),
            ("Furniture", (0.65, 0.50, 0.35, 1.0)),
            ("Technology", (0.40, 0.40, 0.50, 1.0)),
            ("Security", (0.20, 0.20, 0.30, 1.0)),
            ("Other", (0.75, 0.75, 0.75, 1.0)),
        ]
    }
}


class ColorHistoryItem(PropertyGroup):
    """Store color history for undo"""
    object_name: StringProperty()
    previous_color: FloatVectorProperty(size=4, default=(0.5, 0.5, 0.5, 1.0))


class BIMFederationColorProperties(PropertyGroup):
    """Color palette properties"""

    active_palette: EnumProperty(
        name="Color Palette",
        items=[
            ('Realistic', 'Realistic Materials', 'Realistic architectural materials'),
            ('Construction Phase', 'Construction Phases', 'Color by construction phase'),
            ('Safety Status', 'Safety Status', 'Safety and inspection colors'),
            ('Discipline', 'Disciplines', 'Color by building discipline'),
        ],
        default='Realistic'
    )

    selected_color: FloatVectorProperty(
        name="Selected Color",
        subtype='COLOR',
        size=4,
        min=0.0,
        max=1.0,
        default=(0.75, 0.75, 0.75, 1.0)
    )

    filter_discipline: EnumProperty(
        name="Filter Discipline",
        items=[
            ('ALL', 'All Disciplines', 'Show all disciplines'),
            ('ARC', 'Architecture', 'Architecture elements'),
            ('STR', 'Structure', 'Structural elements'),
            ('MEP', 'MEP', 'MEP elements'),
            ('ELEC', 'Electrical', 'Electrical elements'),
            ('PLB', 'Plumbing', 'Plumbing elements'),
            ('FP', 'Fire Protection', 'Fire protection'),
        ],
        default='ALL'
    )

    # Static cached IFC types (updated manually)
    cached_ifc_types: StringProperty(
        name="Cached IFC Types",
        description="Cached list of IFC types (comma-separated)",
        default="ALL"
    )

    def get_ifc_types_static(self, context):
        """Get IFC types from cache"""
        cached = self.cached_ifc_types
        if not cached or cached == "ALL":
            return [('ALL', 'All Types', 'Click Refresh to scan types')]

        items = [('ALL', 'All Types', 'Show all IFC types')]
        for ifc_type in cached.split(','):
            if ifc_type and ifc_type != 'ALL':
                items.append((ifc_type, ifc_type, f'Filter {ifc_type} elements'))
        return items

    filter_ifc_type: EnumProperty(
        name="Filter IFC Type",
        description="Filter by IFC class",
        items=get_ifc_types_static,
        default=0
    )

    auto_apply: BoolProperty(
        name="Auto Apply",
        description="Apply color immediately when selected",
        default=True
    )

    show_preview: BoolProperty(
        name="Show Preview",
        description="Preview color on hover",
        default=True
    )


class BIM_OT_apply_palette_color(Operator):
    """Apply selected color to filtered elements"""
    bl_idname = "bim.apply_palette_color"
    bl_label = "Apply Color"
    bl_options = {'REGISTER', 'UNDO'}

    color: FloatVectorProperty(size=4, default=(0.5, 0.5, 0.5, 1.0))
    apply_to_selected: BoolProperty(default=False)

    def execute(self, context):
        props = context.scene.BIMFederationColorProperties

        # Store history for undo
        color_history = []

        # Determine which objects to color
        if self.apply_to_selected and context.selected_objects:
            objects_to_color = context.selected_objects
        else:
            objects_to_color = context.scene.objects

        colored_count = 0

        for obj in objects_to_color:
            if obj.type != 'MESH':
                continue

            # Check discipline filter
            if props.filter_discipline != 'ALL':
                obj_discipline = obj.get('discipline', '')
                if obj_discipline != props.filter_discipline:
                    continue

            # Check IFC type filter
            if props.filter_ifc_type != 'ALL':
                obj_ifc_class = obj.get('ifc_class', '')
                if obj_ifc_class != props.filter_ifc_type:
                    continue

            # Store previous color
            color_history.append({
                'object': obj.name,
                'previous': obj.color[:]
            })

            # Apply new color
            obj.color = self.color
            colored_count += 1

        # Set viewport to show colors
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.color_type = 'OBJECT'

        self.report({'INFO'}, f"Applied color to {colored_count} objects")
        return {'FINISHED'}


class BIM_OT_refresh_ifc_types(Operator):
    """Scan model for IFC types (slow on large models)"""
    bl_idname = "bim.refresh_ifc_types"
    bl_label = "Refresh IFC Types"
    bl_options = {'REGISTER'}

    def execute(self, context):
        props = context.scene.BIMFederationColorProperties

        # Scan objects for unique IFC types
        types = set()
        for obj in context.scene.objects:
            if obj.type == 'MESH':
                ifc_class = obj.get('ifc_class', '')
                if ifc_class:
                    types.add(ifc_class)

        # Store as comma-separated string
        if types:
            props.cached_ifc_types = ','.join(sorted(types))
            self.report({'INFO'}, f"Found {len(types)} IFC types")
        else:
            props.cached_ifc_types = "ALL"
            self.report({'WARNING'}, "No IFC types found in model")

        return {'FINISHED'}


class BIM_OT_reset_colors(Operator):
    """Reset all colors to default gray"""
    bl_idname = "bim.reset_federation_colors"
    bl_label = "Reset Colors"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        default_color = (0.75, 0.75, 0.75, 1.0)

        reset_count = 0
        for obj in context.scene.objects:
            if obj.type == 'MESH':
                obj.color = default_color
                reset_count += 1

        self.report({'INFO'}, f"Reset {reset_count} objects to default color")
        return {'FINISHED'}


class BIM_OT_save_color_scheme(Operator):
    """Save current color scheme to database"""
    bl_idname = "bim.save_color_scheme"
    bl_label = "Save Color Scheme"
    bl_options = {'REGISTER'}

    scheme_name: StringProperty(name="Scheme Name", default="Custom Scheme")

    def execute(self, context):
        # Create color database if needed
        work_dir = Path.home() / 'Projects' / 'IfcOpenShell' / 'WORK_DIR' / 'databases'
        color_db = work_dir / 'DBCOLOR.db'

        conn = sqlite3.connect(str(color_db))
        cursor = conn.cursor()

        # Save current colors
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS saved_schemes (
                scheme_name TEXT,
                object_name TEXT,
                discipline TEXT,
                ifc_class TEXT,
                color_r REAL,
                color_g REAL,
                color_b REAL,
                color_a REAL,
                PRIMARY KEY (scheme_name, object_name)
            )
        """)

        # Delete existing scheme if exists
        cursor.execute("DELETE FROM saved_schemes WHERE scheme_name = ?", (self.scheme_name,))

        # Save all object colors
        saved_count = 0
        for obj in context.scene.objects:
            if obj.type == 'MESH':
                cursor.execute("""
                    INSERT INTO saved_schemes
                    (scheme_name, object_name, discipline, ifc_class, color_r, color_g, color_b, color_a)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    self.scheme_name,
                    obj.name,
                    obj.get('discipline', ''),
                    obj.get('ifc_class', ''),
                    obj.color[0], obj.color[1], obj.color[2], obj.color[3]
                ))
                saved_count += 1

        conn.commit()
        conn.close()

        self.report({'INFO'}, f"Saved color scheme '{self.scheme_name}' with {saved_count} objects")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class BIM_OT_load_color_scheme(Operator):
    """Load saved color scheme from database"""
    bl_idname = "bim.load_color_scheme"
    bl_label = "Load Color Scheme"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        work_dir = Path.home() / 'Projects' / 'IfcOpenShell' / 'WORK_DIR' / 'databases'
        color_db = work_dir / 'DBCOLOR.db'

        if not color_db.exists():
            self.report({'ERROR'}, "No saved color schemes found")
            return {'CANCELLED'}

        # TODO: Show scheme selector
        self.report({'INFO'}, "Load color scheme (feature coming soon)")
        return {'FINISHED'}


class BIM_PT_federation_color_palette(Panel):
    """Color palette panel - standalone outside Federation"""
    bl_label = "🎨 BIM Color Palette"
    bl_idname = "BIM_PT_federation_color_palette"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"
    bl_order = 100  # After other panels

    def draw(self, context):
        layout = self.layout
        props = context.scene.BIMFederationColorProperties

        # Palette selector
        box = layout.box()
        row = box.row()
        row.label(text="Theme:", icon='COLOR')
        row.prop(props, "active_palette", text="")

        # Color grid
        palette = CONSTRUCTION_PALETTES.get(props.active_palette, {})
        colors = palette.get("colors", [])

        grid_box = layout.box()
        grid_box.label(text="Quick Colors:", icon='BRUSHES_ALL')

        # Create color swatches (4 columns)
        col_count = 4
        for i in range(0, len(colors), col_count):
            row = grid_box.row(align=True)
            for j in range(col_count):
                if i + j < len(colors):
                    name, color = colors[i + j]
                    op = row.operator("bim.apply_palette_color", text="", icon='BLANK1')
                    op.color = color
                    # Show color as background (hacky but works)
                    col = row.column()
                    col.scale_x = 0.3
                    col.label(text=name[:8])

        # Custom color picker
        layout.separator()
        color_box = layout.box()
        color_box.label(text="Custom Color:", icon='EYEDROPPER')
        color_box.prop(props, "selected_color", text="")

        row = color_box.row(align=True)
        op = row.operator("bim.apply_palette_color", text="Apply Custom", icon='CHECKMARK')
        op.color = props.selected_color

        # Filters
        layout.separator()
        filter_box = layout.box()
        filter_box.label(text="Filters:", icon='FILTER')

        row = filter_box.row()
        row.prop(props, "filter_discipline", text="")

        row = filter_box.row()
        row.prop(props, "filter_ifc_type", text="", icon='OBJECT_DATA')

        # Refresh button
        row = filter_box.row()
        row.operator("bim.refresh_ifc_types", text="Refresh Types", icon='FILE_REFRESH')

        # Options
        row = filter_box.row()
        row.prop(props, "auto_apply", text="Auto Apply")
        row.prop(props, "show_preview", text="Preview")

        # Actions
        layout.separator()
        action_box = layout.box()
        action_box.label(text="Actions:", icon='TOOL_SETTINGS')

        row = action_box.row(align=True)
        op = row.operator("bim.apply_palette_color", text="Apply to Selected", icon='RESTRICT_SELECT_OFF')
        op.color = props.selected_color
        op.apply_to_selected = True

        row = action_box.row(align=True)
        row.operator("bim.reset_federation_colors", text="Reset All", icon='FILE_REFRESH')

        row = action_box.row(align=True)
        row.operator("bim.save_color_scheme", text="Save Scheme", icon='FILE_TICK')
        row.operator("bim.load_color_scheme", text="Load Scheme", icon='FILE_FOLDER')

        # Info
        info_box = layout.box()
        info_box.scale_y = 0.8
        info_text = info_box.column()
        info_text.label(text="💡 Tips:", icon='INFO')
        info_text.label(text="  • Use Solid shading mode")
        info_text.label(text="  • Alt+Z for X-ray view")
        info_text.label(text="  • Filter by discipline/type")


# Registration
classes = (
    ColorHistoryItem,
    BIMFederationColorProperties,
    BIM_OT_apply_palette_color,
    BIM_OT_refresh_ifc_types,
    BIM_OT_reset_colors,
    BIM_OT_save_color_scheme,
    BIM_OT_load_color_scheme,
    BIM_PT_federation_color_palette,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # Property registration handled by main federation module __init__.py


def unregister():
    # Property unregistration handled by main federation module __init__.py
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)