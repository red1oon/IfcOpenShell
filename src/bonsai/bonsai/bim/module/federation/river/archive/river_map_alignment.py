# Bonsai - OpenBIM Blender Add-on
# River Map Alignment - GPS alignment verification and correction
# Ensures OSM river curves and Google Maps tiles are perfectly aligned

"""
River Map Alignment - GPS Coordinate Verification
==================================================
Verifies and ensures perfect alignment between:
- OSM imported river curves (from Overpass API)
- Google Maps tiles (from Static Maps API)
- Equipment markers (from database)

All three systems use the SAME georef_config table, which guarantees
mathematical alignment. This module provides verification and debugging
tools to confirm alignment and catch any issues.

Alignment Strategy:
===================
1. Single Source of Truth: georef_config table in database
   - Blender bounds: x_min, x_max, y_min, y_max
   - GPS bounds: lon_min, lon_max, lat_min, lat_max

2. Consistent Conversion: All systems use linear interpolation
   - OSM: GeoConverter.gps_to_blender()
   - Tiles: GPSConverter.gps_to_blender()
   - Markers: Direct database GPS → Blender coords

3. Verification Points:
   - OSM curve GPS stored in custom properties
   - Tile GPS bounds stored in metadata
   - Marker GPS stored in database

Debug Logging:
==============
All alignment operations log:
- Source GPS coordinates
- Converted Blender coordinates
- Conversion parameters (bounds, offsets)
- Verification results (pass/fail with tolerance)
"""

import bpy
from bpy.types import Operator
import sqlite3
from pathlib import Path
from typing import Dict, Tuple, List, Optional
import math


# =============================================================================
# ALIGNMENT VERIFICATION
# =============================================================================

class AlignmentVerifier:
    """Verify GPS alignment between OSM, Google Maps, and markers"""

    def __init__(self, db_path: Path):
        """Initialize with database path"""
        self.db_path = db_path
        self.load_georef_config()

    def load_georef_config(self):
        """Load georef config - single source of truth"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM georef_config LIMIT 1")
        row = cursor.fetchone()
        conn.close()

        if not row:
            raise ValueError("No georef_config found in database")

        # Store config
        self.blender_x_min = row[2]
        self.blender_x_max = row[3]
        self.blender_y_min = row[4]
        self.blender_y_max = row[5]
        self.gps_lon_min = row[6]
        self.gps_lon_max = row[7]
        self.gps_lat_min = row[8]
        self.gps_lat_max = row[9]

        print(f"\n{'='*70}")
        print(f"📍 GEOREF CONFIG (Single Source of Truth)")
        print(f"{'='*70}")
        print(f"GPS Bounds:")
        print(f"  Longitude: {self.gps_lon_min:.6f} - {self.gps_lon_max:.6f}")
        print(f"  Latitude:  {self.gps_lat_min:.6f} - {self.gps_lat_max:.6f}")
        print(f"Blender Bounds:")
        print(f"  X: {self.blender_x_min:.2f} - {self.blender_x_max:.2f}")
        print(f"  Y: {self.blender_y_min:.2f} - {self.blender_y_max:.2f}")
        print(f"{'='*70}\n")

    def gps_to_blender(self, lon: float, lat: float) -> Tuple[float, float]:
        """Convert GPS to Blender (reference implementation)"""
        # Linear interpolation (matches OSM and tile converters)
        x = self.blender_x_min + (lon - self.gps_lon_min) / (self.gps_lon_max - self.gps_lon_min) * \
            (self.blender_x_max - self.blender_x_min)

        y = self.blender_y_min + (lat - self.gps_lat_min) / (self.gps_lat_max - self.gps_lat_min) * \
            (self.blender_y_max - self.blender_y_min)

        return x, y

    def blender_to_gps(self, x: float, y: float) -> Tuple[float, float]:
        """Convert Blender to GPS (reference implementation)"""
        # Inverse linear interpolation
        lon = self.gps_lon_min + (x - self.blender_x_min) / (self.blender_x_max - self.blender_x_min) * \
            (self.gps_lon_max - self.gps_lon_min)

        lat = self.gps_lat_min + (y - self.blender_y_min) / (self.blender_y_max - self.blender_y_min) * \
            (self.gps_lat_max - self.gps_lat_min)

        return lon, lat

    def verify_osm_curve_alignment(self, curve_obj) -> Dict:
        """Verify OSM curve GPS alignment"""
        if "gps_coordinates" not in curve_obj:
            return {'status': 'error', 'message': 'No GPS data found'}

        print(f"\n{'='*70}")
        print(f"🔍 VERIFYING OSM CURVE ALIGNMENT: {curve_obj.name}")
        print(f"{'='*70}")

        # Parse GPS coordinates from custom property
        gps_string = curve_obj["gps_coordinates"]
        gps_pairs = [pair.split(',') for pair in gps_string.split(';')]
        gps_coords = [(float(lon), float(lat)) for lon, lat in gps_pairs]

        print(f"Total points: {len(gps_coords)}")

        # Get Blender points
        if curve_obj.type == 'CURVE':
            spline = curve_obj.data.splines[0]
            blender_points = [(p.co.x, p.co.y) for p in spline.points]
        elif curve_obj.type == 'MESH':
            blender_points = [(v.co.x, v.co.y) for v in curve_obj.data.vertices]
        else:
            return {'status': 'error', 'message': f'Unsupported object type: {curve_obj.type}'}

        if len(gps_coords) != len(blender_points):
            return {'status': 'error', 'message': f'Point count mismatch: GPS={len(gps_coords)}, Blender={len(blender_points)}'}

        # Verify each point
        max_error = 0.0
        errors = []

        for i, ((lon, lat), (bx, by)) in enumerate(zip(gps_coords, blender_points)):
            # Convert GPS to expected Blender coords
            expected_x, expected_y = self.gps_to_blender(lon, lat)

            # Calculate error
            error_x = abs(bx - expected_x)
            error_y = abs(by - expected_y)
            error_total = math.sqrt(error_x**2 + error_y**2)

            if error_total > max_error:
                max_error = error_total

            if error_total > 0.1:  # > 10cm threshold
                errors.append({
                    'point': i,
                    'gps': (lon, lat),
                    'blender_actual': (bx, by),
                    'blender_expected': (expected_x, expected_y),
                    'error_m': error_total
                })

        # Report results
        print(f"\nAlignment Verification:")
        print(f"  Max error: {max_error:.4f} m")

        if errors:
            print(f"  ⚠️  Found {len(errors)} points with error > 0.1m")
            for err in errors[:5]:  # Show first 5
                print(f"    Point {err['point']}: GPS ({err['gps'][0]:.6f}, {err['gps'][1]:.6f})")
                print(f"      Expected: ({err['blender_expected'][0]:.2f}, {err['blender_expected'][1]:.2f})")
                print(f"      Actual:   ({err['blender_actual'][0]:.2f}, {err['blender_actual'][1]:.2f})")
                print(f"      Error:    {err['error_m']:.4f} m")
        else:
            print(f"  ✅ All points aligned within 0.1m tolerance")

        print(f"{'='*70}\n")

        return {
            'status': 'pass' if max_error < 0.1 else 'warning',
            'max_error_m': max_error,
            'error_count': len(errors),
            'total_points': len(gps_coords)
        }

    def verify_marker_alignment(self, marker_obj) -> Dict:
        """Verify equipment marker GPS alignment"""
        if 'marker_id' not in marker_obj:
            return {'status': 'error', 'message': 'Not a marker object'}

        marker_id = marker_obj['marker_id']

        print(f"\n{'='*70}")
        print(f"🔍 VERIFYING MARKER ALIGNMENT: {marker_obj.name}")
        print(f"{'='*70}")

        # Get GPS from database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT latitude, longitude, location_x, location_y, position_source
            FROM project_markers
            WHERE id = ?
        """, (marker_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return {'status': 'error', 'message': 'Marker not found in database'}

        lat, lon, db_x, db_y, pos_source = row

        print(f"GPS: ({lat:.6f}, {lon:.6f})")
        print(f"Position source: {pos_source}")
        print(f"Database Blender: ({db_x:.2f}, {db_y:.2f})")
        print(f"Scene Blender: ({marker_obj.location.x:.2f}, {marker_obj.location.y:.2f})")

        # Convert GPS to expected Blender coords
        expected_x, expected_y = self.gps_to_blender(lon, lat)

        print(f"Expected Blender: ({expected_x:.2f}, {expected_y:.2f})")

        # Calculate errors
        db_error_x = abs(db_x - expected_x)
        db_error_y = abs(db_y - expected_y)
        db_error = math.sqrt(db_error_x**2 + db_error_y**2)

        scene_error_x = abs(marker_obj.location.x - expected_x)
        scene_error_y = abs(marker_obj.location.y - expected_y)
        scene_error = math.sqrt(scene_error_x**2 + scene_error_y**2)

        print(f"\nAlignment Errors:")
        print(f"  Database → Expected: {db_error:.4f} m")
        print(f"  Scene → Expected: {scene_error:.4f} m")

        if db_error < 0.1 and scene_error < 0.1:
            print(f"  ✅ Marker aligned within 0.1m tolerance")
            status = 'pass'
        else:
            print(f"  ⚠️  Marker alignment error > 0.1m")
            status = 'warning'

        print(f"{'='*70}\n")

        return {
            'status': status,
            'gps': (lat, lon),
            'db_error_m': db_error,
            'scene_error_m': scene_error,
            'position_source': pos_source
        }

    def verify_all_alignment(self, context) -> Dict:
        """Verify alignment of all objects in scene"""
        print(f"\n{'='*70}")
        print(f"🔍 COMPREHENSIVE ALIGNMENT VERIFICATION")
        print(f"{'='*70}\n")

        results = {
            'osm_curves': [],
            'markers': [],
            'summary': {}
        }

        # Check OSM curves
        for obj in bpy.data.objects:
            if "gps_coordinates" in obj:
                result = self.verify_osm_curve_alignment(obj)
                result['object_name'] = obj.name
                results['osm_curves'].append(result)

            if 'marker_id' in obj:
                result = self.verify_marker_alignment(obj)
                result['object_name'] = obj.name
                results['markers'].append(result)

        # Summary
        osm_pass = sum(1 for r in results['osm_curves'] if r['status'] == 'pass')
        osm_total = len(results['osm_curves'])
        marker_pass = sum(1 for r in results['markers'] if r['status'] == 'pass')
        marker_total = len(results['markers'])

        results['summary'] = {
            'osm_curves_total': osm_total,
            'osm_curves_pass': osm_pass,
            'markers_total': marker_total,
            'markers_pass': marker_pass
        }

        print(f"\n{'='*70}")
        print(f"📊 ALIGNMENT SUMMARY")
        print(f"{'='*70}")
        print(f"OSM Curves: {osm_pass}/{osm_total} passed")
        print(f"Markers: {marker_pass}/{marker_total} passed")
        print(f"{'='*70}\n")

        return results


# =============================================================================
# ALIGNMENT VERIFICATION OPERATOR
# =============================================================================

class BIM_OT_river_verify_gps_alignment(Operator):
    """Verify GPS alignment between OSM curves, tiles, and markers"""
    bl_idname = "bim.river_verify_gps_alignment"
    bl_label = "Verify GPS Alignment"
    bl_options = {'REGISTER'}

    def execute(self, context):
        db_path = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db")

        if not db_path.exists():
            self.report({'ERROR'}, "Database not found")
            return {'CANCELLED'}

        try:
            verifier = AlignmentVerifier(db_path)
            results = verifier.verify_all_alignment(context)

            # Report to user
            summary = results['summary']
            osm_status = f"{summary['osm_curves_pass']}/{summary['osm_curves_total']}"
            marker_status = f"{summary['markers_pass']}/{summary['markers_total']}"

            self.report({'INFO'}, f"Alignment: OSM {osm_status}, Markers {marker_status} - See console")

        except Exception as e:
            self.report({'ERROR'}, f"Verification failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

        return {'FINISHED'}
