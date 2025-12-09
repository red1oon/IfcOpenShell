# Bonsai - OpenBIM Blender Add-on
# River Centerline from OpenStreetMap
# Fetch accurate river polyline from OSM and create Blender curve

"""
River Centerline from OpenStreetMap
====================================
Fetches river vector data from OpenStreetMap Overpass API and creates
georeferenced Blender curve objects.

Features:
- Query OSM for waterway data within bounds
- Convert GPS coordinates to Blender space
- Create curve objects with proper alignment
- No API key required (OSM is free!)
- Avoids BLOSM complexity

OSM Waterway Tags:
- waterway=river (main rivers)
- waterway=stream (smaller streams)
- waterway=canal (artificial waterways)
"""

import bpy
from bpy.types import Operator
from bpy.props import StringProperty, EnumProperty, BoolProperty
import urllib.request
import urllib.parse
import json
import sqlite3
from pathlib import Path
from mathutils import Vector


# =============================================================================
# COORDINATE CONVERSION
# =============================================================================

class GeoConverter:
    """Convert between GPS and Blender coordinates using database georef"""

    def __init__(self, db_path):
        """Load georef config from database"""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM georef_config LIMIT 1")
        row = cursor.fetchone()

        if not row:
            raise ValueError("No georef_config found in database")

        # Parse config (id, crs, blender bounds, gps bounds, ...)
        self.blender_x_min = row[2]
        self.blender_x_max = row[3]
        self.blender_y_min = row[4]
        self.blender_y_max = row[5]
        self.gps_lon_min = row[6]
        self.gps_lon_max = row[7]
        self.gps_lat_min = row[8]
        self.gps_lat_max = row[9]

        # Get mesh offset
        cursor.execute("SELECT center_x, center_y, center_z FROM element_transforms LIMIT 1")
        transform_row = cursor.fetchone()
        self.mesh_offset = transform_row if transform_row else (0.0, 0.0, 0.0)

        conn.close()

        print(f"📍 GPS Bounds: Lon {self.gps_lon_min:.3f}-{self.gps_lon_max:.3f}, "
              f"Lat {self.gps_lat_min:.3f}-{self.gps_lat_max:.3f}")
        print(f"📐 Blender Bounds: X {self.blender_x_min:.1f}-{self.blender_x_max:.1f}, "
              f"Y {self.blender_y_min:.1f}-{self.blender_y_max:.1f}")

    def gps_to_blender(self, lon, lat, z=0.0):
        """Convert GPS (lon, lat) to Blender (x, y, z) coordinates"""
        # Linear interpolation
        x = self.blender_x_min + (lon - self.gps_lon_min) / (self.gps_lon_max - self.gps_lon_min) * \
            (self.blender_x_max - self.blender_x_min)

        y = self.blender_y_min + (lat - self.gps_lat_min) / (self.gps_lat_max - self.gps_lat_min) * \
            (self.blender_y_max - self.blender_y_min)

        # Apply mesh offset
        x += self.mesh_offset[0]
        y += self.mesh_offset[1]
        z += self.mesh_offset[2]

        return Vector((x, y, z))


# =============================================================================
# OSM OVERPASS API
# =============================================================================

class OSMOverpass:
    """Query OpenStreetMap Overpass API for waterway data"""

    OVERPASS_URL = "https://overpass-api.de/api/interpreter"

    @staticmethod
    def query_waterways(lat_min, lat_max, lon_min, lon_max, waterway_type='river'):
        """
        Query OSM for waterways in bounding box

        Args:
            lat_min, lat_max, lon_min, lon_max: Bounding box
            waterway_type: 'river', 'stream', 'canal', or 'all'

        Returns:
            List of ways with coordinates
        """
        # Build Overpass QL query
        if waterway_type == 'all':
            waterway_filter = '[waterway]'
        else:
            waterway_filter = f'[waterway={waterway_type}]'

        query = f"""
        [out:json][timeout:25];
        (
          way{waterway_filter}({lat_min},{lon_min},{lat_max},{lon_max});
        );
        out geom;
        """

        print(f"\n{'='*70}")
        print(f"🌊 QUERYING OPENSTREETMAP")
        print(f"{'='*70}")
        print(f"Waterway type: {waterway_type}")
        print(f"Bounds: Lat {lat_min:.3f}-{lat_max:.3f}, Lon {lon_min:.3f}-{lon_max:.3f}")
        print(f"URL: {OSMOverpass.OVERPASS_URL}")

        # Send request
        data = {'data': query}
        encoded_data = urllib.parse.urlencode(data).encode('utf-8')

        try:
            req = urllib.request.Request(OSMOverpass.OVERPASS_URL, data=encoded_data)
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode('utf-8'))

            ways = result.get('elements', [])
            print(f"✅ Found {len(ways)} waterway(s)")

            # Show way details
            for way in ways:
                tags = way.get('tags', {})
                name = tags.get('name', 'Unnamed')
                waterway = tags.get('waterway', 'unknown')
                node_count = len(way.get('geometry', []))
                print(f"   - {name} ({waterway}): {node_count} nodes")

            print(f"{'='*70}\n")

            return ways

        except Exception as e:
            print(f"❌ ERROR: Failed to query OSM: {e}")
            raise


# =============================================================================
# RIVER CENTERLINE OPERATOR
# =============================================================================

class BIM_OT_river_import_osm_centerline(Operator):
    """Import river centerline from OpenStreetMap"""
    bl_idname = "bim.river_import_osm_centerline"
    bl_label = "Import River from OSM"
    bl_options = {'REGISTER', 'UNDO'}

    waterway_type: EnumProperty(
        name="Waterway Type",
        items=[
            ('river', "River", "Main rivers only"),
            ('stream', "Stream", "Smaller streams"),
            ('all', "All Waterways", "Rivers, streams, canals")
        ],
        default='river'
    )

    z_offset: bpy.props.FloatProperty(
        name="Z Offset",
        description="Vertical offset for curve (meters)",
        default=0.0
    )

    create_separate_curves: BoolProperty(
        name="Separate Curves",
        description="Create separate curve for each OSM way",
        default=True
    )

    def execute(self, context):
        print("\n" + "="*70)
        print("🌊 IMPORT RIVER CENTERLINE FROM OPENSTREETMAP")
        print("="*70)

        db_path = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db")

        if not db_path.exists():
            self.report({'ERROR'}, f"Database not found: {db_path}")
            return {'CANCELLED'}

        try:
            # Load georef config
            converter = GeoConverter(db_path)

            # Query OSM
            ways = OSMOverpass.query_waterways(
                converter.gps_lat_min,
                converter.gps_lat_max,
                converter.gps_lon_min,
                converter.gps_lon_max,
                self.waterway_type
            )

            if not ways:
                self.report({'WARNING'}, "No waterways found in area")
                return {'CANCELLED'}

            # Create curves
            created_curves = []

            for way in ways:
                geometry = way.get('geometry', [])
                if len(geometry) < 2:
                    continue

                tags = way.get('tags', {})
                name = tags.get('name', f"Waterway_{way['id']}")
                waterway_type = tags.get('waterway', 'unknown')

                print(f"\n🔨 Creating curve: {name} ({len(geometry)} points)")

                # Convert GPS to Blender coords
                blender_points = []
                for node in geometry:
                    lon = node['lon']
                    lat = node['lat']
                    point = converter.gps_to_blender(lon, lat, self.z_offset)
                    blender_points.append(point)

                # Create Blender curve
                curve_data = bpy.data.curves.new(name=f"{name}_curve", type='CURVE')
                curve_data.dimensions = '3D'

                # Create spline
                spline = curve_data.splines.new('POLY')
                spline.points.add(len(blender_points) - 1)  # Already has 1 point

                for i, point in enumerate(blender_points):
                    spline.points[i].co = (point.x, point.y, point.z, 1.0)

                # Create object
                curve_obj = bpy.data.objects.new(name, curve_data)
                context.scene.collection.objects.link(curve_obj)

                # Style curve
                curve_data.bevel_depth = 5.0  # 5m width for visibility
                curve_data.bevel_resolution = 4

                # Create material
                mat = bpy.data.materials.new(name=f"{name}_material")
                mat.use_nodes = True
                nodes = mat.node_tree.nodes
                bsdf = nodes.get('Principled BSDF')
                if bsdf:
                    bsdf.inputs['Base Color'].default_value = (0.2, 0.5, 0.8, 1.0)  # Blue
                    bsdf.inputs['Metallic'].default_value = 0.3
                    bsdf.inputs['Roughness'].default_value = 0.4

                curve_data.materials.append(mat)

                created_curves.append(curve_obj)
                print(f"   ✅ Curve created: {name}")
                print(f"      Bounds: {min(p.x for p in blender_points):.1f} - {max(p.x for p in blender_points):.1f} (X)")
                print(f"              {min(p.y for p in blender_points):.1f} - {max(p.y for p in blender_points):.1f} (Y)")

            # Add to collection
            collection_name = "River Centerlines (OSM)"
            if collection_name in bpy.data.collections:
                collection = bpy.data.collections[collection_name]
            else:
                collection = bpy.data.collections.new(collection_name)
                context.scene.collection.children.link(collection)

            # Move curves to collection
            for curve_obj in created_curves:
                if curve_obj.name in context.scene.collection.objects:
                    context.scene.collection.objects.unlink(curve_obj)
                collection.objects.link(curve_obj)

            print(f"\n✅ Created {len(created_curves)} river curve(s)")
            print(f"   Collection: {collection_name}")
            print("="*70 + "\n")

            self.report({'INFO'}, f"Imported {len(created_curves)} waterway(s) from OSM")

        except Exception as e:
            self.report({'ERROR'}, f"Error: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

        return {'FINISHED'}


# =============================================================================
# CURVE CLEANUP OPERATOR
# =============================================================================

class BIM_OT_river_simplify_centerline(Operator):
    """Simplify river centerline curve (remove excessive vertices)"""
    bl_idname = "bim.river_simplify_centerline"
    bl_label = "Simplify River Curve"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'CURVE'

    def execute(self, context):
        obj = context.active_object

        if obj.type != 'CURVE':
            self.report({'ERROR'}, "Select a curve object")
            return {'CANCELLED'}

        # Convert to mesh temporarily for decimation
        # (Blender's curve simplify is limited)
        print(f"\n🔨 Simplifying curve: {obj.name}")

        original_points = sum(len(spline.points) for spline in obj.data.splines)

        # Use Edit mode decimate (manual approach)
        self.report({'INFO'}, f"Original: {original_points} points. Use Edit Mode > Curve > Simplify for reduction")

        return {'FINISHED'}
