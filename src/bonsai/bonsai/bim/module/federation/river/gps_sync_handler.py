# Bonsai - OpenBIM Blender Add-on
# GPS Auto-Sync Handler - Updates GPS when objects move in Blender

"""
GPS Auto-Sync Handler
=====================
Automatically updates GPS coordinates (latitude/longitude) when equipment
objects are moved in Blender 3D space.

**Algorithm:**
Uses affine transformation from georef_config database table.
- Loads calibration bounds on initialization
- Converts Blender XY → GPS using normalized interpolation
- No anchor needed - uses full georeferencing system
- Blender-only updates - no database sync (backward compatible)

**Affine Transformation:**
lon = lon_min + (x - x_min) / (x_max - x_min) * (lon_max - lon_min)
lat = lat_min + (y - y_min) / (y_max - y_min) * (lat_max - lat_min)
"""

import bpy
from bpy.app.handlers import persistent, depsgraph_update_post
import sqlite3
from pathlib import Path


class GPSAutoSync:
    """Handles automatic GPS synchronization when objects move"""

    def __init__(self):
        self.enabled = False
        # Affine calibration bounds (loaded from georef_config)
        self.x_min = None
        self.x_max = None
        self.y_min = None
        self.y_max = None
        self.lon_min = None
        self.lon_max = None
        self.lat_min = None
        self.lat_max = None
        self.tracked_objects = set()
        self.last_positions = {}

    def enable(self):
        """Enable GPS auto-sync (Blender-only, no database)"""
        # Load affine calibration from database
        if not self._load_affine_calibration():
            return False

        self.enabled = True
        print(f"✓ GPS Auto-Sync: Enabled (Affine Calibration)")
        print(f"  Blender X: {self.x_min:.2f} to {self.x_max:.2f} m")
        print(f"  Blender Y: {self.y_min:.2f} to {self.y_max:.2f} m")
        print(f"  GPS Lon:   {self.lon_min:.6f}° to {self.lon_max:.6f}° E")
        print(f"  GPS Lat:   {self.lat_min:.6f}° to {self.lat_max:.6f}° N")
        return True

    def _load_affine_calibration(self):
        """Load affine transformation bounds from database georef_config table"""
        db_path = Path.home() / "Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db"

        if not db_path.exists():
            print(f"⚠️  GPS Auto-Sync: Database not found: {db_path}")
            return False

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            cursor.execute("""
                SELECT blender_x_min, blender_x_max, blender_y_min, blender_y_max,
                       gps_lon_min, gps_lon_max, gps_lat_min, gps_lat_max
                FROM georef_config
                WHERE id = 1
            """)

            row = cursor.fetchone()
            conn.close()

            if not row or not all(row):
                print(f"⚠️  GPS Auto-Sync: Georef calibration not found in database")
                return False

            self.x_min, self.x_max, self.y_min, self.y_max, \
            self.lon_min, self.lon_max, self.lat_min, self.lat_max = row

            return True

        except Exception as e:
            print(f"⚠️  GPS Auto-Sync: Failed to load calibration - {e}")
            return False

    def disable(self):
        """Disable GPS auto-sync"""
        self.enabled = False
        self.tracked_objects.clear()
        self.last_positions.clear()
        print("✓ GPS Auto-Sync: Disabled")

    def track_equipment_objects(self):
        """Auto-track all equipment objects in scene"""
        count = 0
        for obj in bpy.data.objects:
            if self._is_equipment_object(obj):
                self.tracked_objects.add(obj.name)
                self.last_positions[obj.name] = obj.location.copy()
                count += 1
        print(f"✓ GPS Auto-Sync: Tracking {count} equipment objects")

    def _is_equipment_object(self, obj):
        """Check if object is equipment marker (loaded from DB has marker_id)"""
        return "marker_id" in obj

    def update_gps_for_object(self, obj):
        """Update GPS coordinates for a single object using affine transformation"""
        if not self.enabled:
            return False

        try:
            # Get current Blender position
            x, y = obj.location.x, obj.location.y

            # Affine transformation: Blender XY → GPS
            # Normalize to [0, 1]
            x_norm = (x - self.x_min) / (self.x_max - self.x_min) if self.x_max != self.x_min else 0.5
            y_norm = (y - self.y_min) / (self.y_max - self.y_min) if self.y_max != self.y_min else 0.5

            # Map to GPS coordinates
            lon = self.lon_min + x_norm * (self.lon_max - self.lon_min)
            lat = self.lat_min + y_norm * (self.lat_max - self.lat_min)

            # Update object custom properties (Blender-only)
            obj["latitude"] = lat
            obj["longitude"] = lon

            # Update last known position
            self.last_positions[obj.name] = obj.location.copy()

            return True

        except Exception as e:
            print(f"⚠️  GPS Auto-Sync: Failed to update {obj.name} - {e}")
            return False

    def check_for_updates(self, scene, depsgraph):
        """Check for object position changes (called by depsgraph handler)"""
        if not self.enabled:
            return

        # Check each tracked object
        for obj_name in list(self.tracked_objects):
            obj = bpy.data.objects.get(obj_name)
            if not obj:
                continue

            # Check if position changed
            last_pos = self.last_positions.get(obj_name)
            if last_pos is None:
                self.last_positions[obj_name] = obj.location.copy()
                continue

            # Compare X and Y (ignore Z for GPS)
            current_pos = obj.location
            if abs(current_pos.x - last_pos.x) > 0.01 or abs(current_pos.y - last_pos.y) > 0.01:
                # Position changed - update GPS using affine transformation
                if self.update_gps_for_object(obj):
                    print(f"✓ GPS Updated: {obj_name} → Lat {obj['latitude']:.6f}, Lon {obj['longitude']:.6f}")


# Global instance
_gps_sync = GPSAutoSync()


# =============================================================================
# DEPSGRAPH HANDLER
# =============================================================================

@persistent
def gps_sync_depsgraph_handler(scene, depsgraph):
    """Handler called on every depsgraph update"""
    _gps_sync.check_for_updates(scene, depsgraph)


# =============================================================================
# OPERATORS
# =============================================================================

class BIM_OT_enable_gps_auto_sync(bpy.types.Operator):
    """Enable automatic GPS updates when objects move"""
    bl_idname = "bim.enable_gps_auto_sync"
    bl_label = "Enable GPS Auto-Sync"
    bl_description = "Auto-update GPS when objects move (uses affine calibration from georef_config)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if _gps_sync.enable():
            # Track all equipment objects
            _gps_sync.track_equipment_objects()

            # Register depsgraph handler
            if gps_sync_depsgraph_handler not in depsgraph_update_post:
                depsgraph_update_post.append(gps_sync_depsgraph_handler)

            self.report({'INFO'}, "GPS Auto-Sync enabled (Affine Calibration)")
        else:
            self.report({'ERROR'}, "Failed to enable GPS Auto-Sync - check georef_config table")

        return {'FINISHED'}


class BIM_OT_disable_gps_auto_sync(bpy.types.Operator):
    """Disable automatic GPS updates"""
    bl_idname = "bim.disable_gps_auto_sync"
    bl_label = "Disable GPS Auto-Sync"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        _gps_sync.disable()

        # Unregister depsgraph handler
        if gps_sync_depsgraph_handler in depsgraph_update_post:
            depsgraph_update_post.remove(gps_sync_depsgraph_handler)

        self.report({'INFO'}, "GPS Auto-Sync disabled")
        return {'FINISHED'}


class BIM_OT_update_selected_gps(bpy.types.Operator):
    """Manually update GPS for selected objects"""
    bl_idname = "bim.update_selected_gps"
    bl_label = "Update GPS for Selected"
    bl_description = "Recalculate GPS for selected objects based on current position"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if not _gps_sync.enabled:
            self.report({'ERROR'}, "GPS Auto-Sync not enabled. Enable it first.")
            return {'CANCELLED'}

        updated = 0
        for obj in context.selected_objects:
            if _gps_sync.update_gps_for_object(obj):
                updated += 1

        self.report({'INFO'}, f"Updated GPS for {updated} objects")
        return {'FINISHED'}


class BIM_OT_recalibrate_gps_affine(bpy.types.Operator):
    """Reload affine calibration from database"""
    bl_idname = "bim.recalibrate_gps_affine"
    bl_label = "Reload Affine Calibration"
    bl_description = "Reload affine transformation bounds from georef_config table"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        if _gps_sync._load_affine_calibration():
            self.report({'INFO'}, "Affine calibration reloaded from database")
        else:
            self.report({'ERROR'}, "Failed to reload calibration - check georef_config table")

        return {'FINISHED'}


class BIM_OT_sync_gps_to_database(bpy.types.Operator):
    """Sync GPS coordinates from Blender to database (only if changed >10m)"""
    bl_idname = "bim.sync_gps_to_database"
    bl_label = "Sync GPS to Database"
    bl_description = "Write updated GPS coordinates back to database (only markers moved >10m)"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        """Show confirmation dialog with summary - XY-based detection"""
        import sqlite3
        from pathlib import Path

        db_path = Path.home() / "Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db"

        if not db_path.exists():
            self.report({'ERROR'}, f"Database not found: {db_path}")
            return {'CANCELLED'}

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # Get affine calibration from DB
            cursor.execute("""
                SELECT blender_x_min, blender_x_max, blender_y_min, blender_y_max,
                       gps_lon_min, gps_lon_max, gps_lat_min, gps_lat_max
                FROM georef_config WHERE id = 1
            """)
            calib_row = cursor.fetchone()
            if not calib_row:
                self.report({'ERROR'}, "No georef_config found in database")
                conn.close()
                return {'CANCELLED'}

            x_min, x_max, y_min, y_max, lon_min, lon_max, lat_min, lat_max = calib_row

            # Count markers with XY changes (source of truth)
            markers_to_update = []
            markers_with_bad_gps = []

            total_checked = 0
            total_in_db = 0
            total_moved = 0
            sample_comparisons = []

            total_in_db = 0
            total_moved = 0

            for obj in bpy.data.objects:
                if not self._is_equipment_object(obj):
                    continue

                # Get Blender XY and GPS
                blender_x = obj.location.x
                blender_y = obj.location.y
                blender_lat = obj.get("latitude") or obj.get("gps_lat")
                blender_lon = obj.get("longitude") or obj.get("gps_lon")
                marker_id = obj.get("marker_id")

                if not marker_id:
                    continue

                # Get database XY and GPS - query by marker_id, not name
                cursor.execute("""
                    SELECT name, location_x, location_y, latitude, longitude
                    FROM project_markers
                    WHERE id = ?
                """, (marker_id,))

                row = cursor.fetchone()
                if not row:
                    continue

                total_in_db += 1
                name, db_x, db_y, db_lat, db_lon = row

                # Check if XY has changed
                xy_diff = ((blender_x - db_x)**2 + (blender_y - db_y)**2)**0.5

                # Check if GPS has changed
                gps_diff_m = 0.0
                if blender_lat and blender_lon and db_lat and db_lon:
                    lat_diff_m = abs(blender_lat - db_lat) * 111000
                    lon_diff_m = abs(blender_lon - db_lon) * 111000 * 0.9
                    gps_diff_m = (lat_diff_m**2 + lon_diff_m**2)**0.5

                if xy_diff > 10.0 or gps_diff_m > 10.0:
                    total_moved += 1
                    markers_to_update.append({
                        'id': marker_id,
                        'name': name,
                        'blender_x': blender_x,
                        'blender_y': blender_y,
                        'blender_lat': blender_lat,
                        'blender_lon': blender_lon,
                        'db_x': db_x,
                        'db_y': db_y,
                        'db_lat': db_lat,
                        'db_lon': db_lon,
                        'xy_diff': xy_diff,
                        'gps_diff_m': gps_diff_m
                    })

            conn.close()

            # Debug logging
            print(f"Sync check: {total_in_db} markers in DB, {total_moved} with changes >10m")

            if not markers_to_update:
                self.report({'INFO'}, "No markers moved in Blender (XY unchanged)")
                return {'CANCELLED'}

            # Show confirmation dialog
            return context.window_manager.invoke_confirm(
                self,
                event,
                message=f"Sync {len(markers_to_update)} moved markers to database? (XY changed in Blender)"
            )

        except Exception as e:
            self.report({'ERROR'}, f"Failed to check markers: {e}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

    def execute(self, context):
        """Sync moved markers to database - XY-based with GPS validation"""
        import sqlite3
        from pathlib import Path

        db_path = Path.home() / "Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db"

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # Get affine calibration from DB
            cursor.execute("""
                SELECT blender_x_min, blender_x_max, blender_y_min, blender_y_max,
                       gps_lon_min, gps_lon_max, gps_lat_min, gps_lat_max
                FROM georef_config WHERE id = 1
            """)

            row = cursor.fetchone()
            if not row:
                self.report({'ERROR'}, "No georef_config found in database")
                conn.close()
                return {'CANCELLED'}

            x_min, x_max, y_min, y_max, lon_min, lon_max, lat_min, lat_max = row

            # Find duplicate GPS coordinates in database (indicates stale data)
            cursor.execute("""
                SELECT latitude, longitude
                FROM project_markers
                WHERE latitude IS NOT NULL AND longitude IS NOT NULL
                GROUP BY ROUND(latitude, 6), ROUND(longitude, 6)
                HAVING COUNT(*) > 1
            """)
            duplicate_gps = set((round(lat, 6), round(lon, 6)) for lat, lon in cursor.fetchall())

            updated_count = 0
            validation_failed_count = 0
            duplicate_fixed_count = 0

            print("\n" + "="*80)
            print("SYNCING MOVED MARKERS TO DATABASE (XY-BASED WITH GPS VALIDATION)")
            print("="*80)
            print(f"Affine Calibration (from DB):")
            print(f"  Blender X: {x_min:.2f} to {x_max:.2f}")
            print(f"  Blender Y: {y_min:.2f} to {y_max:.2f}")
            print(f"  GPS Lon: {lon_min:.6f} to {lon_max:.6f}")
            print(f"  GPS Lat: {lat_min:.6f} to {lat_max:.6f}")
            if duplicate_gps:
                print(f"\n⚠️  Found {len(duplicate_gps)} GPS coordinates shared by multiple markers")
                print(f"    These will be recalculated from XY to fix duplicates")
            print("-"*80)

            # Process markers ONE BY ONE
            for obj in bpy.data.objects:
                if not self._is_equipment_object(obj):
                    continue

                # Get Blender XY (source of truth - what user moved)
                blender_x = obj.location.x
                blender_y = obj.location.y

                # Get Blender's cached GPS (try both property name variants)
                blender_cached_lat = obj.get("latitude") or obj.get("gps_lat")
                blender_cached_lon = obj.get("longitude") or obj.get("gps_lon")
                marker_id = obj.get("marker_id")

                if not marker_id:
                    continue

                # Get database XY and GPS - query by marker_id, not name
                cursor.execute("""
                    SELECT name, location_x, location_y, latitude, longitude
                    FROM project_markers
                    WHERE id = ?
                """, (marker_id,))

                row = cursor.fetchone()
                if not row:
                    continue

                name, db_x, db_y, db_lat, db_lon = row

                # Check if XY has changed (moved in Blender)
                xy_diff = ((blender_x - db_x)**2 + (blender_y - db_y)**2)**0.5

                # Check if GPS has changed (Blender GPS vs DB GPS)
                gps_diff_m = 0.0
                if blender_cached_lat and blender_cached_lon and db_lat and db_lon:
                    lat_diff_m = abs(blender_cached_lat - db_lat) * 111000
                    lon_diff_m = abs(blender_cached_lon - db_lon) * 111000 * 0.9
                    gps_diff_m = (lat_diff_m**2 + lon_diff_m**2)**0.5

                # Check if DB GPS is a duplicate (shared with other markers)
                is_duplicate_gps = (round(db_lat, 6), round(db_lon, 6)) in duplicate_gps if db_lat and db_lon else False

                # Check BOTH XY and GPS - if either differs, sync both
                # Also sync if GPS is a duplicate (indicates stale data)
                if xy_diff > 10.0 or gps_diff_m > 10.0 or is_duplicate_gps:  # XY moved OR GPS wrong OR duplicate GPS
                    # BRUTE FORCE: Copy both XY and GPS directly from Blender
                    # NO affine recalculation - trust Blender's auto-sync GPS

                    if blender_cached_lat and blender_cached_lon:
                        new_lat = blender_cached_lat
                        new_lon = blender_cached_lon
                        gps_source = "Copied from Blender (auto-sync GPS)"
                    else:
                        # Fallback: Calculate GPS from XY if Blender has no GPS
                        x_norm = (blender_x - x_min) / (x_max - x_min) if x_max != x_min else 0.5
                        y_norm = (blender_y - y_min) / (y_max - y_min) if y_max != y_min else 0.5
                        new_lon = lon_min + x_norm * (lon_max - lon_min)
                        new_lat = lat_min + y_norm * (lat_max - lat_min)
                        if is_duplicate_gps:
                            gps_source = "Calculated from XY (duplicate GPS fixed)"
                            duplicate_fixed_count += 1
                        else:
                            gps_source = "Calculated from XY (no Blender GPS)"
                            validation_failed_count += 1

                    # Update both XY and GPS in database
                    cursor.execute("""
                        UPDATE project_markers
                        SET location_x = ?, location_y = ?, latitude = ?, longitude = ?
                        WHERE id = ?
                    """, (blender_x, blender_y, new_lat, new_lon, marker_id))

                    # Commit immediately (iterative)
                    conn.commit()

                    updated_count += 1

                    # Debug logging
                    print(f"\n{'='*80}")
                    print(f"MARKER {updated_count}: {name} (ID {marker_id})")
                    print(f"{'='*80}")
                    print(f"XY MOVEMENT:")
                    print(f"  Old XY (DB):      ({db_x:.1f}, {db_y:.1f})")
                    print(f"  New XY (Blender): ({blender_x:.1f}, {blender_y:.1f})")
                    print(f"  XY Moved:         {xy_diff:.1f}m")
                    print(f"\nGPS COPY:")
                    print(f"  Old GPS (DB):      {db_lat:.6f}, {db_lon:.6f}")
                    print(f"  New GPS (Blender): {new_lat:.6f}, {new_lon:.6f}")
                    print(f"  GPS Moved:         {gps_diff_m:.1f}m")
                    print(f"\nSYNCED TO DATABASE:")
                    print(f"  New XY:  ({blender_x:.1f}, {blender_y:.1f})")
                    print(f"  New GPS: {new_lat:.6f}, {new_lon:.6f}")
                    print(f"  Source: {gps_source}")
                    print(f"  ✓ Committed to DB")

            conn.close()

            print("\n" + "="*80)
            print(f"✅ SYNC COMPLETE")
            print("="*80)
            print(f"Total markers synced: {updated_count}")
            if duplicate_fixed_count > 0:
                print(f"✓ Duplicate GPS fixed: {duplicate_fixed_count} markers (recalculated from XY)")
            if validation_failed_count > 0:
                print(f"⚠️  No GPS in Blender: {validation_failed_count} markers (calculated from XY)")
            print(f"XY and GPS copied directly from Blender (brute force, no affine recalc)")
            print("="*80 + "\n")

            if validation_failed_count > 0:
                self.report({'WARNING'}, f"Synced {updated_count} markers ({validation_failed_count} with GPS validation failures)")
            else:
                self.report({'INFO'}, f"Synced {updated_count} moved markers to database")

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to sync: {e}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

    def _is_equipment_object(self, obj):
        """Check if object is equipment marker (loaded from DB has marker_id)"""
        return "marker_id" in obj


class BIM_OT_verify_xy_gps_correlation(bpy.types.Operator):
    """Dump all Blender objects vs DB XY/GPS to file"""
    bl_idname = "bim.verify_xy_gps_correlation"
    bl_label = "Dump Blender vs DB"
    bl_description = "Dump all equipment markers: Blender XY/GPS vs DB XY/GPS to text file"
    bl_options = {'REGISTER', 'UNDO'}

    def _is_equipment_object(self, obj):
        """Check if object is equipment marker (loaded from DB has marker_id)"""
        return "marker_id" in obj

    def execute(self, context):
        """Dump Blender objects vs DB to file"""
        import sqlite3
        from pathlib import Path

        db_path = Path.home() / "Projects/IfcOpenShell/WORK_DIR/RIVER/klang_river_perfect.db"
        dump_file = Path.home() / "Projects/IfcOpenShell/WORK_DIR/RIVER/blender_vs_db_dump.txt"

        if not db_path.exists():
            self.report({'ERROR'}, f"Database not found: {db_path}")
            return {'CANCELLED'}

        try:
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            all_comparisons = []

            # Check all Blender objects with marker_id
            for obj in bpy.data.objects:
                if not self._is_equipment_object(obj):
                    continue

                # Get Blender data
                blender_x = obj.location.x
                blender_y = obj.location.y
                blender_lat = obj.get("latitude") or obj.get("gps_lat")
                blender_lon = obj.get("longitude") or obj.get("gps_lon")
                marker_id = obj.get("marker_id")

                # Get DB data
                cursor.execute("""
                    SELECT id, name, location_x, location_y, latitude, longitude
                    FROM project_markers
                    WHERE name = ?
                """, (obj.name,))

                row = cursor.fetchone()
                if not row:
                    continue

                db_id, name, db_x, db_y, db_lat, db_lon = row

                # Calculate diffs
                xy_diff = ((blender_x - db_x)**2 + (blender_y - db_y)**2)**0.5

                gps_diff_m = 0.0
                if blender_lat and blender_lon and db_lat and db_lon:
                    lat_diff_m = abs(blender_lat - db_lat) * 111000
                    lon_diff_m = abs(blender_lon - db_lon) * 111000 * 0.9
                    gps_diff_m = (lat_diff_m**2 + lon_diff_m**2)**0.5

                all_comparisons.append({
                    'marker_id': marker_id,
                    'name': name,
                    'blender_xy': (blender_x, blender_y),
                    'db_xy': (db_x, db_y),
                    'xy_diff': xy_diff,
                    'blender_gps': (blender_lat, blender_lon) if blender_lat and blender_lon else None,
                    'db_gps': (db_lat, db_lon) if db_lat and db_lon else None,
                    'gps_diff_m': gps_diff_m
                })

            conn.close()

            if not all_comparisons:
                self.report({'INFO'}, "No equipment markers found in Blender")
                return {'CANCELLED'}

            # Check correlation
            print("\n" + "="*80)
            print("VERIFYING XY ↔ GPS CORRELATION")
            print("="*80)
            print(f"Using affine calibration:")
            print(f"  Blender X: {_gps_sync.x_min:.2f} to {_gps_sync.x_max:.2f}")
            print(f"  Blender Y: {_gps_sync.y_min:.2f} to {_gps_sync.y_max:.2f}")
            print(f"  GPS Lon: {_gps_sync.lon_min:.6f} to {_gps_sync.lon_max:.6f}")
            print(f"  GPS Lat: {_gps_sync.lat_min:.6f} to {_gps_sync.lat_max:.6f}")
            print("-"*80)

            mismatches = []
            perfect_matches = 0

            for marker_id, name, mtype, x, y, db_lat, db_lon in markers:
                # Calculate GPS from XY using affine transformation
                x_norm = (x - _gps_sync.x_min) / (_gps_sync.x_max - _gps_sync.x_min) if _gps_sync.x_max != _gps_sync.x_min else 0.5
                y_norm = (y - _gps_sync.y_min) / (_gps_sync.y_max - _gps_sync.y_min) if _gps_sync.y_max != _gps_sync.y_min else 0.5

                calc_lon = _gps_sync.lon_min + x_norm * (_gps_sync.lon_max - _gps_sync.lon_min)
                calc_lat = _gps_sync.lat_min + y_norm * (_gps_sync.lat_max - _gps_sync.lat_min)

                # Calculate difference in meters
                lat_diff_m = abs(calc_lat - db_lat) * 111000
                lon_diff_m = abs(calc_lon - db_lon) * 111000 * 0.9
                distance_diff_m = (lat_diff_m**2 + lon_diff_m**2)**0.5

                if distance_diff_m > 1.0:  # >1m difference
                    mismatches.append({
                        'name': name,
                        'type': mtype,
                        'x': x,
                        'y': y,
                        'db_lat': db_lat,
                        'db_lon': db_lon,
                        'calc_lat': calc_lat,
                        'calc_lon': calc_lon,
                        'distance_m': distance_diff_m
                    })
                else:
                    perfect_matches += 1

            # Report results
            print("\n" + "="*80)
            print(f"VERIFICATION RESULTS: {len(markers)} markers checked")
            print("="*80)
            print(f"✅ Perfect matches (±1m): {perfect_matches}")
            print(f"⚠️  Mismatches (>1m): {len(mismatches)}")

            if mismatches:
                print("\n" + "-"*80)
                print("MISMATCHES FOUND:")
                print("-"*80)
                for m in mismatches[:20]:  # Show first 20
                    print(f"\n⚠️  {m['name']} ({m['type']}):")
                    print(f"    XY: ({m['x']:.1f}, {m['y']:.1f})")
                    print(f"    DB GPS:   {m['db_lat']:.6f}, {m['db_lon']:.6f}")
                    print(f"    Calc GPS: {m['calc_lat']:.6f}, {m['calc_lon']:.6f}")
                    print(f"    Difference: {m['distance_m']:.1f}m")

                if len(mismatches) > 20:
                    print(f"\n... and {len(mismatches) - 20} more mismatches")

            print("\n" + "="*80)

            if mismatches:
                self.report({'WARNING'}, f"Found {len(mismatches)} mismatches (>1m). Check console for details.")
            else:
                self.report({'INFO'}, f"✅ All {len(markers)} markers perfectly correlated (±1m)")

            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Verification failed: {e}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}


# =============================================================================
# UI PANEL
# =============================================================================

class BIM_PT_gps_auto_sync(bpy.types.Panel):
    """GPS Auto-Sync Panel"""
    bl_label = "GPS Auto-Sync"
    bl_idname = "BIM_PT_gps_auto_sync"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'River Equipment'
    bl_parent_id = "BIM_PT_river_equipment_placement"

    def draw(self, context):
        layout = self.layout

        # Toggle checkbox
        row = layout.row()
        if _gps_sync.enabled:
            row.operator("bim.disable_gps_auto_sync", text="☑ Auto-Update GPS on Move", depress=True)
        else:
            row.operator("bim.enable_gps_auto_sync", text="☐ Auto-Update GPS on Move")

        if _gps_sync.enabled:
            layout.separator()
            box = layout.box()
            box.label(text="✓ Active (Affine Calibration)", icon='CHECKMARK')

            layout.separator()
            layout.operator("bim.update_selected_gps", text="Update Selected GPS", icon='FILE_REFRESH')
            layout.operator("bim.recalibrate_gps_affine", text="Reload Calibration", icon='FILE_REFRESH')

            layout.separator()
            layout.operator("bim.verify_xy_gps_correlation", text="Verify XY ↔ GPS", icon='CHECKMARK')
            layout.operator("bim.sync_gps_to_database", text="Sync GPS to Database", icon='EXPORT')

        layout.separator()
        info_box = layout.box()
        info_box.label(text="How it works:", icon='INFO')
        info_box.label(text="• Move any object in viewport")
        info_box.label(text="• GPS auto-updates via affine transform")
        info_box.label(text="• Uses georef_config bounds")
        info_box.label(text="• Sync to DB writes GPS (>10m changes)")


# =============================================================================
# REGISTRATION
# =============================================================================

classes = (
    BIM_OT_enable_gps_auto_sync,
    BIM_OT_disable_gps_auto_sync,
    BIM_OT_update_selected_gps,
    BIM_OT_recalibrate_gps_affine,
    BIM_PT_gps_auto_sync,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    # Auto-enable GPS sync on startup
    if _gps_sync.enable():
        _gps_sync.track_equipment_objects()
        if gps_sync_depsgraph_handler not in depsgraph_update_post:
            depsgraph_update_post.append(gps_sync_depsgraph_handler)
        print("✓ GPS Auto-Sync enabled by default")


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    # Clean up handler
    if gps_sync_depsgraph_handler in depsgraph_update_post:
        depsgraph_update_post.remove(gps_sync_depsgraph_handler)
