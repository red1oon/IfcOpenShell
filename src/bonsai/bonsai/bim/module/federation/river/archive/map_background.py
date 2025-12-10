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
                        try:
                            parts = line.split()
                            # Parse: "TOTAL: 1 calls | $0.002 used | $200.00 remaining (this month)"
                            total_calls = int(parts[1])  # First number after "TOTAL:"
                            # Find the cost (after first $)
                            for i, part in enumerate(parts):
                                if part.startswith('$') and 'used' in parts[i+1] if i+1 < len(parts) else False:
                                    total_cost = float(part.replace('$', ''))
                                    break
                        except (ValueError, IndexError):
                            # If parsing fails, keep defaults (0, 0.0)
                            pass

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


# =============================================================================
# VIEWPORT TILE LOADING OPERATOR
# =============================================================================

class BIM_OT_river_load_viewport_tiles(Operator):
    """Load Google Maps tiles for current viewport"""
    bl_idname = "bim.river_load_viewport_tiles"
    bl_label = "Load Viewport Tiles"
    bl_options = {'REGISTER', 'UNDO'}

    api_key: StringProperty(
        name="Google Maps API Key",
        description="Your Google Maps Static API key",
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

    auto_zoom: bpy.props.BoolProperty(
        name="Auto Zoom",
        description="Automatically select zoom level based on viewport",
        default=True
    )

    manual_zoom: bpy.props.IntProperty(
        name="Manual Zoom",
        description="Manual zoom level (1-20)",
        default=15,
        min=1,
        max=20
    )

    max_tiles: bpy.props.IntProperty(
        name="Max Tiles",
        description="Maximum number of tiles to load in one operation (safety limit to prevent quota exhaustion)",
        default=300,
        min=1,
        max=500
    )

    def execute(self, context):
        print("\n" + "="*70)
        print("🗺️  VIEWPORT TILE LOADING - Google Maps Integration")
        print("="*70)

        try:
            from . import river_map_viewport, river_map_cache

            # Paths
            db_path = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db")
            cache_dir = GoogleMapsConfig.get_cache_dir()

            # Initialize components
            print("Initializing GPS converter...")
            gps_converter = river_map_viewport.GPSConverter(db_path)

            print("Detecting viewport bounds...")
            blender_bounds = river_map_viewport.ViewportBoundsDetector.calculate_viewport_blender_bounds(context)

            if not blender_bounds:
                self.report({'ERROR'}, "Could not detect viewport bounds")
                return {'CANCELLED'}

            gps_bounds = gps_converter.blender_bounds_to_gps_bounds(
                blender_bounds['x_min'],
                blender_bounds['x_max'],
                blender_bounds['y_min'],
                blender_bounds['y_max']
            )

            # Calculate zoom level
            if self.auto_zoom:
                zoom = river_map_viewport.ZoomLevelCalculator.select_zoom_auto(blender_bounds)
            else:
                zoom = self.manual_zoom

            print(f"Using zoom level: {zoom}")

            # Generate tile grid
            tiles = river_map_viewport.TileGridGenerator.generate_tile_grid(gps_bounds, zoom)

            # Safety limit - prevent excessive API usage
            # User can adjust this in the operator properties
            if len(tiles) > self.max_tiles:
                cost_estimate = len(tiles) * 0.002
                self.report({'WARNING'}, f"Would load {len(tiles)} tiles (~${cost_estimate:.2f}) - exceeds limit of {self.max_tiles}")
                print(f"⚠️  {len(tiles)} tiles would exceed limit (max {self.max_tiles})")
                print(f"   Estimated cost: ${cost_estimate:.2f}")
                print(f"   Options:")
                print(f"   1. Zoom in to reduce viewport area")
                print(f"   2. Load river in sections (pan and load multiple times)")
                print(f"   3. Increase 'Max Tiles' limit (F9 to adjust last operation)")
                return {'CANCELLED'}

            if not self.api_key:
                self.report({'ERROR'}, "Google Maps API key required")
                print("❌ No API key provided")
                return {'CANCELLED'}

            # Initialize tile loader
            tile_loader = river_map_cache.TileLoader(cache_dir, self.api_key)

            # Get mesh offset for alignment
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT center_x, center_y, center_z FROM element_transforms LIMIT 1")
            transform_row = cursor.fetchone()
            mesh_offset = transform_row if transform_row else (0.0, 0.0, 0.0)
            conn.close()

            # Load tiles
            print(f"\n📥 Loading {len(tiles)} tiles...")

            # Create collection for tiles
            collection_name = "Viewport Map Tiles"
            if collection_name in bpy.data.collections:
                collection = bpy.data.collections[collection_name]
            else:
                collection = bpy.data.collections.new(collection_name)
                context.scene.collection.children.link(collection)

            loaded_count = 0
            cached_count = 0

            for i, tile in enumerate(tiles):
                print(f"\nTile {i+1}/{len(tiles)}: lat={tile['lat']:.6f}, lon={tile['lon']:.6f}")

                # Load tile (from cache or API)
                tile_path, cached = tile_loader.load_tile(
                    tile['lat'], tile['lon'], tile['zoom'],
                    maptype=self.layer_type
                )

                if cached:
                    cached_count += 1

                # Calculate tile size in Blender coordinates
                lat_center = (tile['lat_min'] + tile['lat_max']) / 2
                lon_center = (tile['lon_min'] + tile['lon_max']) / 2

                # Convert tile corners to Blender coords
                x_min, y_min = gps_converter.gps_to_blender(tile['lat_min'], tile['lon_min'])
                x_max, y_max = gps_converter.gps_to_blender(tile['lat_max'], tile['lon_max'])

                tile_width = x_max - x_min
                tile_height = y_max - y_min
                tile_center_x = (x_min + x_max) / 2
                tile_center_y = (y_min + y_max) / 2

                # Create plane mesh
                bpy.ops.mesh.primitive_plane_add(
                    size=1,
                    location=(
                        tile_center_x + mesh_offset[0],
                        tile_center_y + mesh_offset[1],
                        -20.0 + mesh_offset[2]
                    )
                )

                plane = context.active_object
                plane.name = f"Tile_{tile['ix']}_{tile['iy']}_z{zoom}"

                # Scale to match tile bounds
                plane.scale = (tile_width / 2, tile_height / 2, 1.0)
                bpy.ops.object.transform_apply(scale=True)

                # Create material with image texture
                mat = bpy.data.materials.new(name=f"TileMat_{tile['ix']}_{tile['iy']}")
                mat.use_nodes = True
                nodes = mat.node_tree.nodes
                nodes.clear()

                node_tex = nodes.new('ShaderNodeTexImage')
                node_bsdf = nodes.new('ShaderNodeBsdfPrincipled')
                node_output = nodes.new('ShaderNodeOutputMaterial')

                # Load image
                img = bpy.data.images.load(tile_path)
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

                # Link to collection
                if plane.name in context.scene.collection.objects:
                    context.scene.collection.objects.unlink(plane)
                collection.objects.link(plane)

                loaded_count += 1

            # Show statistics
            print(f"\n✅ Loaded {loaded_count} tiles:")
            print(f"   Cached: {cached_count} ({cached_count/loaded_count*100:.1f}%)")
            print(f"   Fetched: {loaded_count - cached_count}")

            # Show API usage
            usage_stats = tile_loader.get_api_usage_stats()
            print(f"\n💰 API Usage:")
            print(f"   Total API calls: {usage_stats['api_calls']}")
            print(f"   Total cost: ${usage_stats['total_cost']:.3f}")
            print(f"   Remaining: ${usage_stats['remaining']:.2f} / ${usage_stats['free_tier']:.2f}")
            print(f"   Cache hit rate: {usage_stats['cache_hit_rate']:.1f}%")

            print("="*70 + "\n")

            self.report({'INFO'}, f"Loaded {loaded_count} tiles ({cached_count} cached)")

        except Exception as e:
            self.report({'ERROR'}, f"Error: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

        return {'FINISHED'}


# =============================================================================
# CLEAR TILE CACHE OPERATOR
# =============================================================================

class BIM_OT_river_clear_tile_cache(Operator):
    """Clear all cached map tiles"""
    bl_idname = "bim.river_clear_tile_cache"
    bl_label = "Clear Tile Cache"
    bl_options = {'REGISTER'}

    def execute(self, context):
        try:
            from . import river_map_cache

            cache_dir = GoogleMapsConfig.get_cache_dir()
            tile_loader = river_map_cache.TileLoader(cache_dir, "")

            # Get stats before clearing
            stats = tile_loader.get_cache_stats()

            print(f"\n🗑️  Clearing tile cache...")
            print(f"   Cached tiles: {stats['count']}")
            print(f"   Cache size: {stats['size_mb']:.1f} MB")

            tile_loader.clear_cache()

            print(f"✅ Cache cleared!\n")

            self.report({'INFO'}, f"Cleared {stats['count']} tiles ({stats['size_mb']:.1f} MB)")

        except Exception as e:
            self.report({'ERROR'}, f"Error: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

        return {'FINISHED'}



# =============================================================================
# CACHE ARCHIVE OPERATORS
# =============================================================================

class BIM_OT_river_export_tile_cache(Operator):
    """Export tile cache to archive file for backup/sharing"""
    bl_idname = "bim.river_export_tile_cache"
    bl_label = "Export Tile Cache"
    bl_options = {'REGISTER'}

    filepath: StringProperty(
        name="Archive Path",
        description="Path to save cache archive",
        subtype='FILE_PATH',
        default="//river_map_cache.tar.gz"
    )

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        try:
            from . import river_map_cache
            from pathlib import Path

            cache_dir = GoogleMapsConfig.get_cache_dir()
            tile_cache = river_map_cache.TileCache(cache_dir)

            archive_path = Path(bpy.path.abspath(self.filepath))
            result = tile_cache.export_cache_archive(archive_path)

            self.report({'INFO'}, f"Exported {result['tile_count']} tiles ({result['archive_size_mb']:.1f} MB)")

        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

        return {'FINISHED'}


class BIM_OT_river_import_tile_cache(Operator):
    """Import tile cache from archive file"""
    bl_idname = "bim.river_import_tile_cache"
    bl_label = "Import Tile Cache"
    bl_options = {'REGISTER'}

    filepath: StringProperty(
        name="Archive Path",
        description="Path to cache archive",
        subtype='FILE_PATH'
    )

    verify_georef: bpy.props.BoolProperty(
        name="Verify Georef Bounds",
        description="Verify that archive georef bounds match current database (recommended)",
        default=True
    )

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        try:
            from . import river_map_cache
            from pathlib import Path

            cache_dir = GoogleMapsConfig.get_cache_dir()
            tile_cache = river_map_cache.TileCache(cache_dir)

            archive_path = Path(bpy.path.abspath(self.filepath))
            result = tile_cache.import_cache_archive(archive_path, verify_georef=self.verify_georef)

            self.report({'INFO'}, f"Imported {result['imported_tiles']} tiles - See console for details")

        except Exception as e:
            self.report({'ERROR'}, f"Import failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

        return {'FINISHED'}

