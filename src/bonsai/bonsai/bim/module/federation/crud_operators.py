# Bonsai - OpenBIM Blender Add-on
# Copyright (C) 2025 Dion Moult, Yassine Oualid <dion@thinkmoult.com>
#
# This file is part of Bonsai.
#
# Bonsai is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
Qualified Path: src/bonsai/bonsai/bim/module/federation/crud_operators.py

Federation CRUD Operators
--------------------------
Create, Read, Update, Delete operators for manually adding elements to federation database.

This enables bi-directional federation workflow:
- IFC Sources → Federation DB → Blender (read-only)
- Blender → Federation DB (user additions via CRUD)

Use Cases:
- Add site equipment, gas tanks, temporary structures
- Add coordination geometry not in source IFC files
- Edit federated model in place without round-tripping to source files

Pattern:
1. User creates/modifies Blender object
2. Operator generates IFC-compliant metadata (GUID, class, discipline)
3. Insert/update federation database tables:
   - elements_meta (GUID, name, class, discipline, source='MANUAL')
   - elements_rtree (bbox for spatial queries)
   - element_transforms (position, rotation, scale)
4. Additions persist across sessions and participate in federation features
   (clash detection, routing, visualization)
"""

import bpy
import sqlite3
import os
from mathutils import Vector
from datetime import datetime


def get_bbox_from_object(obj):
    """
    Calculate world-space bounding box from Blender object.

    Args:
        obj: Blender object

    Returns:
        Tuple of (min_x, min_y, min_z, max_x, max_y, max_z)
    """
    # Get world-space bounding box
    bbox = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]

    min_x = min(v.x for v in bbox)
    max_x = max(v.x for v in bbox)
    min_y = min(v.y for v in bbox)
    max_y = max(v.y for v in bbox)
    min_z = min(v.z for v in bbox)
    max_z = max(v.z for v in bbox)

    return (min_x, min_y, min_z, max_x, max_y, max_z)


def get_transform_from_object(obj):
    """
    Extract transform data from Blender object.

    Returns:
        Dict with center, rotation, scale
    """
    loc = obj.matrix_world.to_translation()
    rot = obj.matrix_world.to_euler()
    scale = obj.scale

    bbox = get_bbox_from_object(obj)
    center_x = (bbox[0] + bbox[3]) / 2
    center_y = (bbox[1] + bbox[4]) / 2
    center_z = (bbox[2] + bbox[5]) / 2

    return {
        'center_x': center_x,
        'center_y': center_y,
        'center_z': center_z,
        'rotation_x': rot.x,
        'rotation_y': rot.y,
        'rotation_z': rot.z,
        'scale_x': scale.x,
        'scale_y': scale.y,
        'scale_z': scale.z,
    }


class BIM_OT_add_to_federation(bpy.types.Operator):
    """Add selected Blender object to federation database as new element"""
    bl_idname = "bim.add_to_federation"
    bl_label = "Add to Federation"
    bl_options = {'REGISTER', 'UNDO'}

    # Properties for user input
    ifc_class: bpy.props.EnumProperty(
        name="IFC Class",
        description="IFC entity type for this element",
        items=[
            ('IfcBuildingElementProxy', 'Proxy', 'Generic building element'),
            ('IfcColumn', 'Column', 'Structural column'),
            ('IfcBeam', 'Beam', 'Structural beam'),
            ('IfcWall', 'Wall', 'Wall'),
            ('IfcSlab', 'Slab', 'Slab/floor'),
            ('IfcRoof', 'Roof', 'Roof'),
            ('IfcDoor', 'Door', 'Door'),
            ('IfcWindow', 'Window', 'Window'),
            ('IfcStair', 'Stair', 'Stair'),
            ('IfcRailing', 'Railing', 'Railing/guardrail'),
            ('IfcPile', 'Pile', 'Foundation pile'),
            ('IfcFooting', 'Footing', 'Foundation footing'),
            ('IfcTank', 'Tank', 'Tank (gas, water, etc.)'),
            ('IfcPipeSegment', 'Pipe', 'Pipe segment'),
            ('IfcDuctSegment', 'Duct', 'Duct segment'),
            ('IfcCableSegment', 'Cable', 'Cable segment'),
            ('IfcFlowTerminal', 'Flow Terminal', 'HVAC terminal'),
            ('IfcEnergyConversionDevice', 'Energy Device', 'HVAC equipment'),
            ('IfcDistributionElement', 'MEP Element', 'Generic MEP element'),
            ('IfcFurnishingElement', 'Furniture', 'Furniture'),
            ('IfcTransportElement', 'Transport', 'Elevator, escalator'),
            ('IfcCivilElement', 'Civil Element', 'Infrastructure element'),
            ('IfcGeographicElement', 'Geographic', 'Terrain, landscape'),
        ],
        default='IfcBuildingElementProxy'
    )

    discipline: bpy.props.EnumProperty(
        name="Discipline",
        description="Engineering discipline for this element",
        items=[
            ('ADDITIONS', 'Additions', 'User-added coordination geometry'),
            ('ARC', 'Architecture', 'Architectural elements'),
            ('STR', 'Structural', 'Structural elements'),
            ('FP', 'Fire Protection', 'Fire protection systems'),
            ('ELEC', 'Electrical', 'Electrical systems'),
            ('ACMV', 'ACMV', 'Air conditioning & mechanical ventilation'),
            ('PLB', 'Plumbing', 'Plumbing/sanitary'),
            ('SITE', 'Site', 'Site works, civil'),
            ('TEMP', 'Temporary', 'Temporary structures'),
            ('COORD', 'Coordination', 'Coordination geometry'),
        ],
        default='ADDITIONS'
    )

    element_name: bpy.props.StringProperty(
        name="Element Name",
        description="Name for this element in the federation",
        default=""
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None

    def invoke(self, context, event):
        # Pre-populate element name from object name
        if context.active_object:
            self.element_name = context.active_object.name
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "element_name")
        layout.prop(self, "ifc_class")
        layout.prop(self, "discipline")

    def execute(self, context):
        obj = context.active_object
        if not obj:
            self.report({'ERROR'}, "No active object selected")
            return {'CANCELLED'}

        # Get federation database path
        props = context.scene.BIMFederationProperties
        db_path = bpy.path.abspath(props.federation_database_path) if props.federation_database_path else None

        if not db_path or not os.path.exists(db_path):
            self.report({'ERROR'}, "Federation database not found. Load a federation first.")
            return {'CANCELLED'}

        try:
            # Generate IFC GUID
            import ifcopenshell.guid
            new_guid = ifcopenshell.guid.new()

            # Calculate bbox and transform
            bbox = get_bbox_from_object(obj)
            transform = get_transform_from_object(obj)

            # Connect to database
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Check if schema has been migrated
            cursor.execute("PRAGMA table_info(elements_meta)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'source' not in columns:
                self.report({'ERROR'},
                    "Database schema needs migration. Run: sqlite3 DB < migrate_add_source_tracking.sql")
                conn.close()
                return {'CANCELLED'}

            # Insert into elements_meta
            timestamp = int(datetime.now().timestamp())
            cursor.execute("""
                INSERT INTO elements_meta (
                    guid, element_name, ifc_class, discipline,
                    source, created_timestamp, modified_timestamp
                ) VALUES (?, ?, ?, ?, 'MANUAL', ?, ?)
            """, (new_guid, self.element_name, self.ifc_class, self.discipline,
                  timestamp, timestamp))

            # Insert into elements_rtree
            cursor.execute("""
                INSERT INTO elements_rtree (
                    guid, min_x, min_y, min_z, max_x, max_y, max_z
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (new_guid, *bbox))

            # Insert into element_transforms
            cursor.execute("""
                INSERT INTO element_transforms (
                    guid, center_x, center_y, center_z,
                    rotation_x, rotation_y, rotation_z,
                    scale_x, scale_y, scale_z,
                    transform_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual_addition')
            """, (new_guid,
                  transform['center_x'], transform['center_y'], transform['center_z'],
                  transform['rotation_x'], transform['rotation_y'], transform['rotation_z'],
                  transform['scale_x'], transform['scale_y'], transform['scale_z']))

            conn.commit()
            conn.close()

            # Store GUID in object for future reference
            obj['ifc_guid'] = new_guid
            obj['ifc_class'] = self.ifc_class
            obj['discipline'] = self.discipline

            self.report({'INFO'},
                f"Added {self.element_name} to federation as {self.ifc_class} (GUID: {new_guid[:8]}...)")

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to add to federation: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}


class BIM_OT_update_federation_element(bpy.types.Operator):
    """Update federation database with current object transform"""
    bl_idname = "bim.update_federation_element"
    bl_label = "Update in Federation"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and 'ifc_guid' in obj

    def execute(self, context):
        obj = context.active_object
        guid = obj.get('ifc_guid')

        if not guid:
            self.report({'ERROR'}, "Object not tracked in federation (no GUID)")
            return {'CANCELLED'}

        # Get federation database path
        props = context.scene.BIMFederationProperties
        db_path = bpy.path.abspath(props.federation_database_path) if props.federation_database_path else None

        if not db_path or not os.path.exists(db_path):
            self.report({'ERROR'}, "Federation database not found")
            return {'CANCELLED'}

        try:
            # Calculate new bbox and transform
            bbox = get_bbox_from_object(obj)
            transform = get_transform_from_object(obj)

            # Connect to database
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Update element_transforms
            timestamp = int(datetime.now().timestamp())
            cursor.execute("""
                UPDATE element_transforms
                SET center_x = ?, center_y = ?, center_z = ?,
                    rotation_x = ?, rotation_y = ?, rotation_z = ?,
                    scale_x = ?, scale_y = ?, scale_z = ?
                WHERE guid = ?
            """, (transform['center_x'], transform['center_y'], transform['center_z'],
                  transform['rotation_x'], transform['rotation_y'], transform['rotation_z'],
                  transform['scale_x'], transform['scale_y'], transform['scale_z'],
                  guid))

            # Update elements_rtree
            cursor.execute("""
                UPDATE elements_rtree
                SET min_x = ?, min_y = ?, min_z = ?,
                    max_x = ?, max_y = ?, max_z = ?
                WHERE guid = ?
            """, (*bbox, guid))

            # Update modified timestamp
            cursor.execute("""
                UPDATE elements_meta
                SET modified_timestamp = ?
                WHERE guid = ?
            """, (timestamp, guid))

            if cursor.rowcount == 0:
                self.report({'WARNING'}, f"Element {guid[:8]}... not found in database")
                conn.close()
                return {'CANCELLED'}

            conn.commit()
            conn.close()

            self.report({'INFO'}, f"Updated element {guid[:8]}... in federation")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to update federation: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}


class BIM_OT_remove_from_federation(bpy.types.Operator):
    """Remove element from federation database"""
    bl_idname = "bim.remove_from_federation"
    bl_label = "Remove from Federation"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj is not None and 'ifc_guid' in obj

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)

    def execute(self, context):
        obj = context.active_object
        guid = obj.get('ifc_guid')

        if not guid:
            self.report({'ERROR'}, "Object not tracked in federation (no GUID)")
            return {'CANCELLED'}

        # Get federation database path
        props = context.scene.BIMFederationProperties
        db_path = bpy.path.abspath(props.federation_database_path) if props.federation_database_path else None

        if not db_path or not os.path.exists(db_path):
            self.report({'ERROR'}, "Federation database not found")
            return {'CANCELLED'}

        try:
            # Connect to database
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Check if this is a MANUAL addition (safety check)
            cursor.execute("SELECT source FROM elements_meta WHERE guid = ?", (guid,))
            row = cursor.fetchone()
            if not row:
                self.report({'WARNING'}, f"Element {guid[:8]}... not found in database")
                conn.close()
                return {'CANCELLED'}

            if row[0] != 'MANUAL':
                self.report({'ERROR'},
                    f"Cannot remove IFC-sourced element (source={row[0]}). Only MANUAL additions can be removed.")
                conn.close()
                return {'CANCELLED'}

            # Delete from all tables
            cursor.execute("DELETE FROM elements_meta WHERE guid = ?", (guid,))
            cursor.execute("DELETE FROM elements_rtree WHERE guid = ?", (guid,))
            cursor.execute("DELETE FROM element_transforms WHERE guid = ?", (guid,))

            # Try to delete from geometry cache if exists
            try:
                cursor.execute("DELETE FROM geometry_cache WHERE guid = ?", (guid,))
            except:
                pass  # Table might not exist

            conn.commit()
            conn.close()

            # Remove GUID from object
            del obj['ifc_guid']
            if 'ifc_class' in obj:
                del obj['ifc_class']
            if 'discipline' in obj:
                del obj['discipline']

            self.report({'INFO'}, f"Removed element {guid[:8]}... from federation")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to remove from federation: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}


class BIM_OT_query_federation_additions(bpy.types.Operator):
    """Query and display user-added elements in federation"""
    bl_idname = "bim.query_federation_additions"
    bl_label = "Query Additions"
    bl_options = {'REGISTER'}

    def execute(self, context):
        # Get federation database path
        props = context.scene.BIMFederationProperties
        db_path = bpy.path.abspath(props.federation_database_path) if props.federation_database_path else None

        if not db_path or not os.path.exists(db_path):
            self.report({'ERROR'}, "Federation database not found")
            return {'CANCELLED'}

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Query MANUAL additions
            cursor.execute("""
                SELECT guid, element_name, ifc_class, discipline,
                       created_timestamp, modified_timestamp
                FROM elements_meta
                WHERE source = 'MANUAL'
                ORDER BY created_timestamp DESC
            """)

            additions = cursor.fetchall()
            conn.close()

            if not additions:
                self.report({'INFO'}, "No manual additions found in federation")
                return {'FINISHED'}

            # Print to console
            print("\n" + "="*80)
            print(f"FEDERATION ADDITIONS ({len(additions)} elements)")
            print("="*80)
            print(f"{'GUID':<22} {'Name':<30} {'Class':<20} {'Discipline':<12}")
            print("-"*80)

            for guid, name, ifc_class, discipline, created, modified in additions:
                print(f"{guid[:20]:<22} {name[:28]:<30} {ifc_class[:18]:<20} {discipline:<12}")

            print("="*80)

            self.report({'INFO'}, f"Found {len(additions)} manual additions (see console)")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Query failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}


# Register operators
classes = (
    BIM_OT_add_to_federation,
    BIM_OT_update_federation_element,
    BIM_OT_remove_from_federation,
    BIM_OT_query_federation_additions,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
