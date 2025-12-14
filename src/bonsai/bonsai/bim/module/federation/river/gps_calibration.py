# Bonsai - OpenBIM Blender Add-on
# River Equipment GPS Calibration Utilities

"""
GPS Calibration from Truth File
================================
Recalibrates equipment GPS coordinates using ground truth reference markers.
Updates only GPS custom properties in Blender objects (XYZ positions untouched).
"""

import bpy
import math
from pathlib import Path
from bpy.types import Operator


class BIM_OT_equipment_recalibrate_gps_from_truth(Operator):
    """Recalibrate GPS for latest additions using oldest markers as anchors"""
    bl_idname = "bim.equipment_recalibrate_gps_from_truth"
    bl_label = "Recalibrate For Latest Addition"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import sqlite3

        db_path = Path.home() / "Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db"

        if not db_path.exists():
            self.report({'ERROR'}, f"Database not found: {db_path}")
            return {'CANCELLED'}

        # Get oldest markers from database as anchors
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Find oldest creation date
        cursor.execute("""
            SELECT MIN(created_at) FROM project_markers
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        """)
        oldest_date = cursor.fetchone()[0]

        if not oldest_date:
            self.report({'ERROR'}, "No markers with timestamps found in database")
            conn.close()
            return {'CANCELLED'}

        print(f"\nOldest marker date: {oldest_date}")

        # Get anchor markers (oldest date, with GPS)
        cursor.execute("""
            SELECT name, location_x, location_y, latitude, longitude
            FROM project_markers
            WHERE created_at = ?
              AND latitude IS NOT NULL
              AND longitude IS NOT NULL
              AND location_x IS NOT NULL
              AND location_y IS NOT NULL
        """, (oldest_date,))

        anchor_rows = cursor.fetchall()
        conn.close()

        if len(anchor_rows) < 3:
            self.report({'ERROR'}, f"Need at least 3 anchor markers, found {len(anchor_rows)}")
            return {'CANCELLED'}

        # Build anchor dictionary
        anchor_markers = {row[0]: {'x': row[1], 'y': row[2], 'lat': row[3], 'lon': row[4]} for row in anchor_rows}

        self.report({'INFO'}, f"Using {len(anchor_markers)} oldest markers as anchors ({oldest_date})")

        # Get equipment objects from Blender
        equipment_objects = [obj for obj in bpy.data.objects
                            if obj.name.startswith(('BOOM_TRAP_', 'WATER_QUALITY_',
                                                   'POLLUTANT_SENSOR_', 'FLOOD_MONITOR_',
                                                   'WILDLIFE_CAMERA_', 'BIOCHAR_', 'MRF_'))]

        if not equipment_objects:
            self.report({'ERROR'}, "No equipment objects found in scene")
            return {'CANCELLED'}

        # CRITICAL: Verify XY positions match between Blender and Database
        # If XY differs, calibration is GIGO - abort immediately
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name, location_x, location_y FROM project_markers")
        db_positions = {row[0]: {'x': row[1], 'y': row[2]} for row in cursor.fetchall()}
        conn.close()

        xy_mismatches = []

        for obj in equipment_objects:
            if obj.name in db_positions:
                blend_x = obj.location.x
                blend_y = obj.location.y
                db_x = db_positions[obj.name]['x']
                db_y = db_positions[obj.name]['y']

                # Calculate differences
                diff_x = abs(blend_x - db_x)
                diff_y = abs(blend_y - db_y)

                # Only flag if difference rounds to non-zero (0.01m or larger)
                if round(diff_x, 2) > 0 or round(diff_y, 2) > 0:
                    xy_mismatches.append({
                        'name': obj.name,
                        'blend_x': blend_x,
                        'blend_y': blend_y,
                        'db_x': db_x,
                        'db_y': db_y,
                        'diff_x': diff_x,
                        'diff_y': diff_y
                    })

        if xy_mismatches:
            print("\n" + "=" * 80)
            print("❌ XY POSITION MISMATCH - ABORTING GPS CALIBRATION")
            print("=" * 80)
            print(f"\nFound {len(xy_mismatches)} markers with XY differences (exact match required):")
            print("\nBlender and Database XY positions must be IDENTICAL before GPS calibration.")
            print("Run 'Sync Blend → DB' first to fix XY positions.\n")

            for m in xy_mismatches[:10]:  # Show first 10
                print(f"{m['name']}:")
                print(f"  Blend: X={m['blend_x']:.2f}, Y={m['blend_y']:.2f}")
                print(f"  DB:    X={m['db_x']:.2f}, Y={m['db_y']:.2f}")
                print(f"  Diff:  ΔX={m['diff_x']:.2f}m, ΔY={m['diff_y']:.2f}m\n")

            if len(xy_mismatches) > 10:
                print(f"... and {len(xy_mismatches) - 10} more mismatches\n")

            print("=" * 80)

            self.report({'ERROR'}, f"XY mismatch detected on {len(xy_mismatches)} markers - sync Blend→DB first!")
            return {'CANCELLED'}

        # Build reference points from anchor markers (oldest dated markers from DB)
        references = []
        for obj in equipment_objects:
            if obj.name in anchor_markers:
                anchor = anchor_markers[obj.name]
                references.append({
                    'name': obj.name,
                    'x': obj.location.x,
                    'y': obj.location.y,
                    'lat': anchor['lat'],
                    'lon': anchor['lon']
                })

        if len(references) < 3:
            self.report({'ERROR'}, f"Need at least 3 anchor markers in scene, found {len(references)}")
            return {'CANCELLED'}

        print(f"Found {len(references)} anchor markers in Blender scene")
        self.report({'INFO'}, f"Building calibration from {len(references)} anchor markers")

        # Calculate affine transformation using least squares
        transform = self._calculate_affine_transform(references)

        if not transform:
            self.report({'ERROR'}, "Failed to calculate transformation - check console for details")
            return {'CANCELLED'}

        # Debug output
        print(f"\n=== GPS Calibration Transform ===")
        print(f"Longitude = {transform['a1']:.10f}*X + {transform['a2']:.10f}*Y + {transform['a3']:.6f}")
        print(f"Latitude  = {transform['b1']:.10f}*X + {transform['b2']:.10f}*Y + {transform['b3']:.6f}")
        print(f"=================================\n")

        # Apply transformation to all equipment objects (including anchor markers)
        # Anchor markers used to CALCULATE transform, but then same transform applied to all
        # This gives leeway/best-fit across all references using least squares
        updated_count = 0
        x_mean = transform['x_mean']
        y_mean = transform['y_mean']

        for obj in equipment_objects:
            x, y = obj.location.x, obj.location.y

            # Calculate GPS using CENTERED affine transformation for ALL objects
            lon = transform['a1'] * (x - x_mean) + transform['a2'] * (y - y_mean) + transform['a3']
            lat = transform['b1'] * (x - x_mean) + transform['b2'] * (y - y_mean) + transform['b3']

            # Update custom properties (GPS only, XYZ untouched)
            obj["latitude"] = lat
            obj["longitude"] = lon
            updated_count += 1

        print(f"\n✅ Updated GPS for {updated_count} equipment objects")
        print(f"   Calibration from {len(references)} anchor markers (oldest dated)")
        print(f"   Newer markers recalibrated, anchors unchanged\n")

        self.report({'INFO'}, f"Recalibrated {updated_count} objects using {len(references)} anchors")
        return {'FINISHED'}

    def _calculate_affine_transform(self, references):
        """
        Calculate affine transformation using CENTERED COORDINATES (numerically stable).
        lon = a1*(x - x_mean) + a2*(y - y_mean) + lon_mean
        lat = b1*(x - x_mean) + b2*(y - y_mean) + lat_mean
        """
        n = len(references)

        # Center the data for numerical stability (CRITICAL!)
        x_mean = sum(r['x'] for r in references) / n
        y_mean = sum(r['y'] for r in references) / n
        lon_mean = sum(r['lon'] for r in references) / n
        lat_mean = sum(r['lat'] for r in references) / n

        # Build sums for centered least squares
        sum_xx = sum_yy = sum_xy = 0
        sum_x_lon = sum_y_lon = sum_x_lat = sum_y_lat = 0

        for ref in references:
            x_c = ref['x'] - x_mean
            y_c = ref['y'] - y_mean
            lon_c = ref['lon'] - lon_mean
            lat_c = ref['lat'] - lat_mean

            sum_xx += x_c * x_c
            sum_yy += y_c * y_c
            sum_xy += x_c * y_c

            sum_x_lon += x_c * lon_c
            sum_y_lon += y_c * lon_c
            sum_x_lat += x_c * lat_c
            sum_y_lat += y_c * lat_c

        # Solve 2x2 system for centered coordinates
        det = sum_xx * sum_yy - sum_xy * sum_xy

        if abs(det) < 1e-10:
            self.report({'ERROR'}, "Matrix is singular - reference points may be collinear")
            return {}

        # Coefficients for longitude
        a1 = (sum_x_lon * sum_yy - sum_y_lon * sum_xy) / det
        a2 = (sum_y_lon * sum_xx - sum_x_lon * sum_xy) / det

        # Coefficients for latitude
        b1 = (sum_x_lat * sum_yy - sum_y_lat * sum_xy) / det
        b2 = (sum_y_lat * sum_xx - sum_x_lat * sum_xy) / det

        return {
            'a1': a1, 'a2': a2, 'a3': lon_mean,  # lon = a1*(x-x_mean) + a2*(y-y_mean) + a3
            'b1': b1, 'b2': b2, 'b3': lat_mean,  # lat = b1*(x-x_mean) + b2*(y-y_mean) + b3
            'x_mean': x_mean,
            'y_mean': y_mean
        }


class BIM_OT_equipment_compare_gps_blend_db(Operator):
    """Compare GPS coordinates between Blender and Database"""
    bl_idname = "bim.equipment_compare_gps_blend_db"
    bl_label = "Compare GPS: Blend ↔ DB"
    bl_options = {'REGISTER'}

    def execute(self, context):
        import sqlite3

        db_path = Path.home() / "Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db"

        if not db_path.exists():
            self.report({'ERROR'}, f"Database not found: {db_path}")
            return {'CANCELLED'}

        # Read GPS from database
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        cursor.execute("SELECT name, latitude, longitude FROM project_markers WHERE latitude IS NOT NULL")
        db_gps = {row[0]: {'lat': row[1], 'lon': row[2]} for row in cursor.fetchall()}
        conn.close()

        # Read GPS from Blender objects
        equipment_objects = [obj for obj in bpy.data.objects
                            if obj.name.startswith(('BOOM_TRAP_', 'WATER_QUALITY_',
                                                   'POLLUTANT_SENSOR_', 'FLOOD_MONITOR_',
                                                   'WILDLIFE_CAMERA_', 'BIOCHAR_', 'MRF_'))]

        # Compare
        log_lines = []
        log_lines.append("=" * 80)
        log_lines.append("GPS COMPARISON: Blender ↔ Database")
        log_lines.append("=" * 80)
        log_lines.append("")

        mismatch_count = 0
        match_count = 0
        missing_in_db = 0
        missing_in_blend = 0

        for obj in equipment_objects:
            if "latitude" not in obj or "longitude" not in obj:
                missing_in_blend += 1
                continue

            blend_lat = obj["latitude"]
            blend_lon = obj["longitude"]

            if obj.name not in db_gps:
                log_lines.append(f"⚠️  {obj.name}: Missing in DB")
                missing_in_db += 1
                continue

            db_lat = db_gps[obj.name]['lat']
            db_lon = db_gps[obj.name]['lon']

            # Calculate distance in km
            distance_km = self._haversine_distance(blend_lat, blend_lon, db_lat, db_lon)

            if distance_km > 0.001:  # More than 1 meter difference
                log_lines.append(f"❌ {obj.name}: Diff {distance_km:.3f} km")
                log_lines.append(f"   Blend: {blend_lat:.6f}, {blend_lon:.6f}")
                log_lines.append(f"   DB:    {db_lat:.6f}, {db_lon:.6f}")
                mismatch_count += 1
            else:
                match_count += 1

        log_lines.append("")
        log_lines.append("=" * 80)
        log_lines.append(f"✓ Matches: {match_count}")
        log_lines.append(f"❌ Mismatches: {mismatch_count}")
        log_lines.append(f"⚠️  Missing in DB: {missing_in_db}")
        log_lines.append(f"⚠️  Missing GPS in Blend: {missing_in_blend}")
        log_lines.append("=" * 80)

        # Write to log file
        log_path = Path.home() / "Documents/bonsai/consolelogs/gps_comparison.txt"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, 'w') as f:
            f.write('\n'.join(log_lines))

        # Print to console
        print('\n'.join(log_lines))

        self.report({'INFO'}, f"Comparison complete: {match_count} matches, {mismatch_count} mismatches. See {log_path}")
        return {'FINISHED'}

    def _haversine_distance(self, lat1, lon1, lat2, lon2):
        """Calculate distance between two GPS coordinates in kilometers"""
        R = 6371  # Earth radius in km

        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        dlat = math.radians(lat2 - lat1)
        dlon = math.radians(lon2 - lon1)

        a = math.sin(dlat / 2) ** 2 + \
            math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))

        return R * c


# Registration
classes = (
    BIM_OT_equipment_recalibrate_gps_from_truth,
    BIM_OT_equipment_compare_gps_blend_db,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
