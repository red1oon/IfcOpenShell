# Bonsai - OpenBIM Blender Add-on
# River Map Background - Google Maps Integration
# Separate module to keep river_equipment_placement.py manageable

"""
River Map Background - Google Maps Integration
==============================================
Fetches georeferenced satellite/terrain imagery from Google Maps API
and creates aligned plane meshes below the river model.

Features:
- One-click satellite/terrain layer loading
- Smart caching (API call only on first load)
- Perfect geo-alignment using database bounds
- Outliner organization with toggleable layers
- API credit tracking and logging
"""

import bpy
from bpy.types import Operator
from bpy.props import StringProperty, EnumProperty
import sqlite3
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime


# =============================================================================
# GOOGLE MAPS API CONFIGURATION
# =============================================================================

class GoogleMapsConfig:
    """Configuration and cost tracking for Google Maps API"""

    # API pricing (as of 2024)
    COST_PER_STATIC_MAP = 0.002  # $0.002 per map load
    FREE_TIER_MONTHLY = 200.0    # $200/month free credit

    # Zoom levels and coverage
    ZOOM_LEVELS = {
        'whole_river': 12,    # 40-50km width
        'sections': 15,        # 5-10km width
        'clusters': 18,        # 1-2km width
        'markers': 19          # 500m width
    }

    @staticmethod
    def get_cache_dir():
        """Get/create cache directory"""
        cache_dir = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/map_cache")
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    @staticmethod
    def get_api_log_path():
        """Get API usage log file path"""
        return GoogleMapsConfig.get_cache_dir() / "api_usage.log"

    @staticmethod
    def log_api_call(layer_type, cost, cached=False):
        """Log API call to track usage and costs"""
        log_file = GoogleMapsConfig.get_api_log_path()

        # Read existing log
        total_calls = 0
        total_cost = 0.0

        if log_file.exists():
            with open(log_file, 'r') as f:
                for line in f:
                    if line.startswith("TOTAL:"):
                        parts = line.split()
                        total_calls = int(parts[2])
                        total_cost = float(parts[5].replace('$', ''))

        # Update totals
        if not cached:
            total_calls += 1
            total_cost += cost

        # Calculate remaining credit
        remaining = GoogleMapsConfig.FREE_TIER_MONTHLY - total_cost

        # Write log entry
        with open(log_file, 'a') as f:
            timestamp = datetime.now().isoformat()
            status = "CACHED" if cached else "FETCHED"
            f.write(f"{timestamp} | {status} | {layer_type} | ${cost:.3f}\n")

            # Update summary line at end
            if not cached:
                f.write(f"TOTAL: {total_calls} calls | ${total_cost:.3f} used | ${remaining:.2f} remaining (this month)\n")

        # Print to console
        print(f"\n{'='*70}")
        print(f"🗺️  GOOGLE MAPS API USAGE")
        print(f"{'='*70}")
        print(f"Action: {status} {layer_type} layer")
        print(f"Cost: ${cost:.3f}")
        if not cached:
            print(f"Total API calls this month: {total_calls}")
            print(f"Total cost: ${total_cost:.3f}")
            print(f"💰 Remaining credit: ${remaining:.2f} / ${GoogleMapsConfig.FREE_TIER_MONTHLY:.2f}")
            print(f"   ({(remaining/GoogleMapsConfig.FREE_TIER_MONTHLY*100):.1f}% remaining)")
        else:
            print(f"✅ Using cached tile (FREE)")
        print(f"{'='*70}\n")

        return remaining


# =============================================================================
# RIVER MAP BACKGROUND OPERATOR
# =============================================================================

class BIM_OT_river_load_map_background(Operator):
    """Load georeferenced Google Maps satellite background for river"""
    bl_idname = "bim.river_load_map_background"
    bl_label = "Load River Map Background"
    bl_options = {'REGISTER', 'UNDO'}

    api_key: StringProperty(
        name="Google Maps API Key",
        description="Your Google Maps Static API key (get free key at console.cloud.google.com)",
        default=""
    )

    layer_type: EnumProperty(
        name="Layer Type",
        items=[
            ('satellite', "Satellite", "Photorealistic satellite imagery"),
            ('terrain', "Terrain", "Topographic/elevation view"),
            ('hybrid', "Hybrid", "Satellite + street labels")
        ],
        default='satellite'
    )

    def execute(self, context):
        print("\n" + "="*70)
        print("🗺️  RIVER MAP BACKGROUND - GOOGLE MAPS INTEGRATION")
        print("="*70)

        # Database path
        db_path = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db")
        cache_dir = GoogleMapsConfig.get_cache_dir()

        try:
            # Get georef bounds from database
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM georef_config LIMIT 1")
            row = cursor.fetchone()

            if not row:
                self.report({'ERROR'}, "No georef_config found in database")
                return {'CANCELLED'}

            # Parse georef data (id, crs, x_min, x_max, y_min, y_max, lon_min, lon_max, lat_min, lat_max, ...)
            lon_min, lon_max = row[6], row[7]
            lat_min, lat_max = row[8], row[9]
            blender_x_min, blender_x_max = row[2], row[3]
            blender_y_min, blender_y_max = row[4], row[5]

            print(f"📍 GPS Bounds: Lat {lat_min:.3f}-{lat_max:.3f}, Lon {lon_min:.3f}-{lon_max:.3f}")

            # Calculate plane dimensions
            plane_width = blender_x_max - blender_x_min
            plane_height = blender_y_max - blender_y_min
            plane_center_x = (blender_x_min + blender_x_max) / 2
            plane_center_y = (blender_y_min + blender_y_max) / 2

            print(f"📐 Plane size: {plane_width/1000:.1f}km × {plane_height/1000:.1f}km")

            # Get mesh offset for alignment
            cursor.execute("SELECT center_x, center_y, center_z FROM element_transforms LIMIT 1")
            transform_row = cursor.fetchone()
            mesh_offset = transform_row if transform_row else (0.0, 0.0, 0.0)

            conn.close()

            # Cache file path
            cache_file = cache_dir / f"river_base_{self.layer_type}.jpg"

            # Check if already cached
            cached = cache_file.exists()

            if cached:
                print(f"✅ Using cached map: {cache_file.name}")
                image_path = str(cache_file)
                GoogleMapsConfig.log_api_call(self.layer_type, 0.0, cached=True)
            else:
                # Need to fetch from Google Maps API
                if not self.api_key:
                    self.report({'ERROR'}, "Google Maps API key required. Get free key at: https://console.cloud.google.com/")
                    print("❌ ERROR: No API key provided")
                    print("   Get your free API key: https://console.cloud.google.com/")
                    print("   $200/month free tier = ~100,000 map loads!")
                    return {'CANCELLED'}

                # Build Google Static Maps API URL
                center_lat = (lat_min + lat_max) / 2
                center_lon = (lon_min + lon_max) / 2
                zoom = GoogleMapsConfig.ZOOM_LEVELS['whole_river']

                params = {
                    'center': f'{center_lat},{center_lon}',
                    'zoom': zoom,
                    'size': '2048x512',  # Max size (4:1 aspect for river)
                    'scale': 2,  # High DPI
                    'maptype': self.layer_type,
                    'key': self.api_key,
                    'format': 'jpg'
                }

                url = "https://maps.googleapis.com/maps/api/staticmap?" + urllib.parse.urlencode(params)

                print(f"🌐 Fetching from Google Maps API (zoom {zoom})...")
                print(f"   This will use 1 API call (~${GoogleMapsConfig.COST_PER_STATIC_MAP:.3f})")

                try:
                    # Download image
                    urllib.request.urlretrieve(url, cache_file)
                    print(f"✅ Map downloaded: {cache_file.name}")
                    print(f"   Size: {cache_file.stat().st_size / 1024:.1f} KB")
                    image_path = str(cache_file)

                    # Log API usage
                    GoogleMapsConfig.log_api_call(self.layer_type, GoogleMapsConfig.COST_PER_STATIC_MAP, cached=False)

                except Exception as e:
                    self.report({'ERROR'}, f"Failed to download map: {str(e)}")
                    print(f"❌ ERROR: {e}")
                    return {'CANCELLED'}

            # Create Blender plane mesh
            print("🔨 Creating georeferenced plane mesh...")

            bpy.ops.mesh.primitive_plane_add(
                size=1,
                location=(
                    plane_center_x + mesh_offset[0],
                    plane_center_y + mesh_offset[1],
                    -20.0 + mesh_offset[2]  # 20m below river
                )
            )

            plane = context.active_object
            plane.name = f"RiverMap_{self.layer_type.title()}"

            # Scale to match river bounds
            plane.scale = (plane_width / 2, plane_height / 2, 1.0)
            bpy.ops.object.transform_apply(scale=True)

            # Create material with image texture
            mat = bpy.data.materials.new(name=f"MapMaterial_{self.layer_type}")
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            nodes.clear()

            # Shader nodes
            node_tex = nodes.new('ShaderNodeTexImage')
            node_bsdf = nodes.new('ShaderNodeBsdfPrincipled')
            node_output = nodes.new('ShaderNodeOutputMaterial')

            # Load image
            img = bpy.data.images.load(image_path)
            node_tex.image = img

            # Connect nodes
            links = mat.node_tree.links
            links.new(node_tex.outputs['Color'], node_bsdf.inputs['Base Color'])
            links.new(node_bsdf.outputs['BSDF'], node_output.inputs['Surface'])

            # Assign material
            if plane.data.materials:
                plane.data.materials[0] = mat
            else:
                plane.data.materials.append(mat)

            # Add to collection
            collection_name = "River Map Layers"
            if collection_name in bpy.data.collections:
                collection = bpy.data.collections[collection_name]
            else:
                collection = bpy.data.collections.new(collection_name)
                context.scene.collection.children.link(collection)

            # Link plane to collection
            if plane.name in context.scene.collection.objects:
                context.scene.collection.objects.unlink(plane)
            collection.objects.link(plane)

            print(f"✅ Map layer created: {plane.name}")
            print(f"   Collection: {collection_name} (toggle in Outliner)")
            print(f"   Location: Z={-20.0 + mesh_offset[2]:.1f}m (below river)")
            print("="*70 + "\n")

            self.report({'INFO'}, f"River map loaded ({self.layer_type})")

        except Exception as e:
            self.report({'ERROR'}, f"Error: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

        return {'FINISHED'}


# =============================================================================
# API USAGE VIEWER OPERATOR
# =============================================================================

class BIM_OT_river_view_api_usage(Operator):
    """View Google Maps API usage and remaining credits"""
    bl_idname = "bim.river_view_api_usage"
    bl_label = "View API Usage"

    def execute(self, context):
        log_file = GoogleMapsConfig.get_api_log_path()

        if not log_file.exists():
            print("\n📊 No API usage yet. Load a map layer to start tracking!")
            self.report({'INFO'}, "No API usage yet")
            return {'FINISHED'}

        # Read and display log
        print("\n" + "="*70)
        print("📊 GOOGLE MAPS API USAGE REPORT")
        print("="*70)

        with open(log_file, 'r') as f:
            lines = f.readlines()

        # Show recent calls
        print("\nRecent API Calls:")
        for line in lines[-10:]:  # Last 10 entries
            if not line.startswith("TOTAL"):
                print(f"  {line.strip()}")

        # Show summary
        print("\nCurrent Month Summary:")
        for line in lines:
            if line.startswith("TOTAL"):
                print(f"  {line.strip()}")

        print("="*70 + "\n")

        self.report({'INFO'}, "Check console for API usage details")
        return {'FINISHED'}
