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

                # Convert GPS to Blender coords and store GPS data
                blender_points = []
                gps_coords = []  # Store original GPS for each point
                for node in geometry:
                    lon = node['lon']
                    lat = node['lat']
                    point = converter.gps_to_blender(lon, lat, self.z_offset)
                    blender_points.append(point)
                    gps_coords.append((lon, lat))

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

                # Store GPS coordinates as custom properties
                # Format: "lon1,lat1;lon2,lat2;lon3,lat3;..."
                gps_string = ";".join([f"{lon:.6f},{lat:.6f}" for lon, lat in gps_coords])
                curve_obj["gps_coordinates"] = gps_string
                curve_obj["gps_lon_min"] = min(lon for lon, lat in gps_coords)
                curve_obj["gps_lon_max"] = max(lon for lon, lat in gps_coords)
                curve_obj["gps_lat_min"] = min(lat for lon, lat in gps_coords)
                curve_obj["gps_lat_max"] = max(lat for lon, lat in gps_coords)
                curve_obj["osm_id"] = way['id']
                curve_obj["osm_waterway_type"] = waterway_type

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
                print(f"      Blender Bounds: X {min(p.x for p in blender_points):.1f} - {max(p.x for p in blender_points):.1f}")
                print(f"                      Y {min(p.y for p in blender_points):.1f} - {max(p.y for p in blender_points):.1f}")
                print(f"      GPS Bounds: Lon {curve_obj['gps_lon_min']:.6f} - {curve_obj['gps_lon_max']:.6f}")
                print(f"                  Lat {curve_obj['gps_lat_min']:.6f} - {curve_obj['gps_lat_max']:.6f}")
                print(f"      OSM ID: {curve_obj['osm_id']}")
                print(f"      Points: {len(gps_coords)} vertices with GPS coords")

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


# =============================================================================
# GPS UTILITY FUNCTIONS
# =============================================================================

def get_gps_bounds_from_object(obj):
    """
    Get GPS bounds from a curve/mesh object with stored GPS coordinates

    Args:
        obj: Blender object with GPS custom properties

    Returns:
        dict: {'lon_min', 'lon_max', 'lat_min', 'lat_max'} or None
    """
    if not obj:
        return None

    # Check if GPS bounds are stored as custom properties
    if all(key in obj for key in ['gps_lon_min', 'gps_lon_max', 'gps_lat_min', 'gps_lat_max']):
        return {
            'lon_min': obj['gps_lon_min'],
            'lon_max': obj['gps_lon_max'],
            'lat_min': obj['gps_lat_min'],
            'lat_max': obj['gps_lat_max']
        }

    return None


def get_gps_coordinates_from_object(obj):
    """
    Parse GPS coordinates string from object custom properties

    Args:
        obj: Blender object with gps_coordinates property

    Returns:
        list: [(lon, lat), (lon, lat), ...] or None
    """
    if not obj or "gps_coordinates" not in obj:
        return None

    gps_string = obj["gps_coordinates"]
    coords = []

    for pair in gps_string.split(";"):
        if pair.strip():
            lon_str, lat_str = pair.split(",")
            coords.append((float(lon_str), float(lat_str)))

    return coords


def get_tile_bounds_for_object(obj, padding_percent=10):
    """
    Get GPS bounds with padding for map tile fetching

    Args:
        obj: Blender object with GPS bounds
        padding_percent: Add N% padding around bounds

    Returns:
        dict: Padded GPS bounds for tile queries
    """
    bounds = get_gps_bounds_from_object(obj)
    if not bounds:
        return None

    # Calculate padding
    lon_range = bounds['lon_max'] - bounds['lon_min']
    lat_range = bounds['lat_max'] - bounds['lat_min']

    lon_padding = lon_range * (padding_percent / 100.0)
    lat_padding = lat_range * (padding_percent / 100.0)

    return {
        'lon_min': bounds['lon_min'] - lon_padding,
        'lon_max': bounds['lon_max'] + lon_padding,
        'lat_min': bounds['lat_min'] - lat_padding,
        'lat_max': bounds['lat_max'] + lat_padding,
        'center_lon': (bounds['lon_min'] + bounds['lon_max']) / 2,
        'center_lat': (bounds['lat_min'] + bounds['lat_max']) / 2
    }


# =============================================================================
# DATABASE STORAGE OPERATOR
# =============================================================================

class BIM_OT_river_save_to_database(Operator):
    """Save OSM river curve to database with GPS metadata"""
    bl_idname = "bim.river_save_to_database"
    bl_label = "Save River to Database"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return obj and "gps_coordinates" in obj

    def execute(self, context):
        obj = context.active_object

        if "gps_coordinates" not in obj:
            self.report({'ERROR'}, "Selected object has no GPS data")
            return {'CANCELLED'}

        db_path = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db")

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Create table if not exists
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS osm_river_centerlines (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    osm_id INTEGER,
                    waterway_type TEXT,
                    gps_lon_min REAL,
                    gps_lon_max REAL,
                    gps_lat_min REAL,
                    gps_lat_max REAL,
                    gps_coordinates TEXT,
                    point_count INTEGER,
                    blender_object_name TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    notes TEXT
                )
            """)

            # Insert river data
            gps_coords_string = obj.get("gps_coordinates", "")
            point_count = len(gps_coords_string.split(";")) if gps_coords_string else 0

            cursor.execute("""
                INSERT INTO osm_river_centerlines
                (name, osm_id, waterway_type, gps_lon_min, gps_lon_max, gps_lat_min, gps_lat_max,
                 gps_coordinates, point_count, blender_object_name)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                obj.name,
                obj.get("osm_id"),
                obj.get("osm_waterway_type", "river"),
                obj.get("gps_lon_min"),
                obj.get("gps_lon_max"),
                obj.get("gps_lat_min"),
                obj.get("gps_lat_max"),
                gps_coords_string,
                point_count,
                obj.name
            ))

            conn.commit()
            row_id = cursor.lastrowid
            conn.close()

            print(f"\n✅ Saved river to database:")
            print(f"   Name: {obj.name}")
            print(f"   Database ID: {row_id}")
            print(f"   Points: {point_count}")
            print(f"   GPS Bounds: {obj['gps_lon_min']:.6f},{obj['gps_lat_min']:.6f} - "
                  f"{obj['gps_lon_max']:.6f},{obj['gps_lat_max']:.6f}")

            self.report({'INFO'}, f"Saved {obj.name} to database (ID: {row_id})")

        except Exception as e:
            self.report({'ERROR'}, f"Database error: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

        return {'FINISHED'}
