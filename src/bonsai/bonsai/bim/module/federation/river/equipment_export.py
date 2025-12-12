# Bonsai - OpenBIM Blender Add-on
# River Equipment Export Module
# Extracted from equipment_placement.py

"""
Equipment Export Operators
===========================
Export operators for equipment data visualization and mobile delivery:
- Google Maps navigation
- HTML map viewer export
- KML export for mobile apps
- Mobile-optimized HTML export
"""

import bpy
from bpy.types import Operator
from pathlib import Path
from datetime import datetime

# Import shared configuration
from .equipment_logger import LOGGER
from .equipment_config import EQUIPMENT_TYPES


# =============================================================================
# GOOGLE MAPS NAVIGATION OPERATOR
# =============================================================================

class BIM_OT_equipment_open_google_maps(Operator):
    """Open Google Maps with directions from office to equipment location"""
    bl_idname = "bim.equipment_open_google_maps"
    bl_label = "Get Directions"
    bl_options = {'REGISTER'}

    latitude: bpy.props.FloatProperty()
    longitude: bpy.props.FloatProperty()

    def execute(self, context):
        import webbrowser

        props = context.scene.BIMFederationProperties
        office_address = props.office_address

        if not office_address:
            self.report({'WARNING'}, "Please set Office/Depot Address in N Panel first")
            return {'CANCELLED'}

        if not self.latitude or not self.longitude:
            self.report({'ERROR'}, "Equipment has no GPS coordinates")
            return {'CANCELLED'}

        # Build Google Maps directions URL
        # Format: https://www.google.com/maps/dir/?api=1&origin=ADDRESS&destination=LAT,LON
        origin = office_address.replace(' ', '+')
        destination = f"{self.latitude},{self.longitude}"

        url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={destination}"

        LOGGER.log(f"Opening Google Maps directions: {office_address} → {destination}")
        webbrowser.open(url)

        self.report({'INFO'}, f"Opened directions in browser")
        return {'FINISHED'}


# =============================================================================
# HTML MAP EXPORT AND LAUNCH OPERATOR
# =============================================================================

class BIM_OT_equipment_export_and_launch_html(Operator):
    """Export equipment GPS from Blender and launch HTML viewer"""
    bl_idname = "bim.equipment_export_and_launch_html"
    bl_label = "Export & Launch HTML Map"
    bl_options = {'REGISTER'}

    def execute(self, context):
        import json
        import webbrowser
        import sqlite3
        from pathlib import Path

        # Paths
        script_dir = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER")
        output_path = script_dir / "output/geojson/project_markers.geojson"
        html_path = script_dir / "RiverUI/index.html"
        db_path = script_dir / "klang_river_perfect.db"

        from . import river_utils

        # Connect to database (GPS source of truth)
        conn = None
        try:
            conn = sqlite3.connect(str(db_path))
        except Exception as e:
            self.report({'ERROR'}, f"Could not connect to database: {e}")
            return {'CANCELLED'}

        cursor = conn.cursor()

        # Get all markers from database
        cursor.execute("""
            SELECT id, name, marker_type, latitude, longitude
            FROM project_markers
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            ORDER BY name
        """)

        markers = cursor.fetchall()

        if not markers:
            self.report({'WARNING'}, "No markers with GPS found in database")
            conn.close()
            return {'CANCELLED'}

        features = []
        exported = 0
        skipped = 0

        for marker_id, name, marker_type, lat, lon in markers:
            eq_type = marker_type
            color = river_utils.EQUIPMENT_COLORS_HEX.get(eq_type, '#FF6B35')

            # Get sensor data from database
            sensors = []
            try:
                sensors = river_utils.fetch_sensor_data_from_db(cursor, name)
            except Exception as e:
                LOGGER.log(f"Warning: Could not fetch sensors for {name}: {e}")

            sensor_count = len(sensors)
            sensor_summary = river_utils.create_sensor_summary(sensors)

            feature = river_utils.create_geojson_feature(name, eq_type, color, lat, lon, sensors)
            features.append(feature)
            exported += 1

        # Create GeoJSON
        geojson = river_utils.create_geojson_collection(features)

        # Close database connection
        if conn:
            conn.close()

        # Write to file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w') as f:
            json.dump(geojson, f, indent=2)

        LOGGER.log(f"Exported {exported} equipment markers to GeoJSON")
        LOGGER.log(f"Skipped {skipped} markers (missing GPS)")

        # Log GPS bounds for debugging
        if features:
            lats = [f["geometry"]["coordinates"][1] for f in features]
            lons = [f["geometry"]["coordinates"][0] for f in features]
            LOGGER.log(f"GPS Bounds: Lat [{min(lats):.6f}, {max(lats):.6f}], Lon [{min(lons):.6f}, {max(lons):.6f}]")

        # Launch HTML with local server
        if html_path.exists():
            import subprocess
            import time
            from pathlib import Path

            server_port = 8000
            # Always use WORK_DIR
            server_dir = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/RiverUI")

            try:
                # Check if server already running
                check = subprocess.run(['lsof', '-ti', f':{server_port}'],
                                     capture_output=True, text=True)

                if not check.stdout.strip():
                    # No server running, start one
                    subprocess.Popen(
                        ['python3', '-m', 'http.server', str(server_port)],
                        cwd=str(server_dir),
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    time.sleep(1)

                # Open in browser
                url = f"http://localhost:{server_port}/index.html"
                webbrowser.open(url)
                self.report({'INFO'}, f"Exported {exported} markers and launched at {url}")
            except Exception as e:
                webbrowser.open(f"file://{html_path}")
                self.report({'INFO'}, f"Exported {exported} markers (using file://)")
        else:
            self.report({'WARNING'}, f"Exported {exported} markers but HTML not found at {html_path}")

        return {'FINISHED'}


# =============================================================================
# KML EXPORT OPERATOR
# =============================================================================

class BIM_OT_equipment_export_kml(Operator):
    """Export equipment to KML for Google Earth, Avenza Maps, Maps.me, OsmAnd"""
    bl_idname = "bim.equipment_export_kml"
    bl_label = "Export KML for Mobile Apps"
    bl_options = {'REGISTER'}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    SENSOR_RANGES = {
        'pH': (0, 14),
        'Temperature': (0, 50),
        'Turbidity': (0, 100),
        'Dissolved_Oxygen': (0, 15),
        'Load_Cell': (0, 500),
        'Water_Level': (0, 5)
    }

    @staticmethod
    def create_kml_styles(document, colors):
        """Create KML styles for each equipment type."""
        import xml.etree.ElementTree as ET
        for eq_type, color in colors.items():
            style = ET.SubElement(document, 'Style', id=eq_type)
            icon_style = ET.SubElement(style, 'IconStyle')
            ET.SubElement(icon_style, 'color').text = color
            ET.SubElement(icon_style, 'scale').text = '0.8'
            icon = ET.SubElement(icon_style, 'Icon')
            ET.SubElement(icon, 'href').text = 'http://maps.google.com/mapfiles/kml/paddle/wht-blank.png'
            label_style = ET.SubElement(style, 'LabelStyle')
            ET.SubElement(label_style, 'scale').text = '0'

    @staticmethod
    def get_sensor_trend(cursor, sensor_id, last_reading):
        """Calculate sensor trend from 7-day average."""
        try:
            cursor.execute("""
                SELECT AVG(value) FROM sensor_readings
                WHERE sensor_id = ? AND value IS NOT NULL LIMIT 7
            """, (sensor_id,))
            avg_row = cursor.fetchone()
            if avg_row and avg_row[0] and last_reading:
                seven_day_avg = avg_row[0]
                diff_pct = ((last_reading - seven_day_avg) / seven_day_avg) * 100
                if diff_pct > 5:
                    return "↗️", f"+{diff_pct:.0f}%", seven_day_avg
                elif diff_pct < -5:
                    return "↘️", f"{diff_pct:.0f}%", seven_day_avg
                else:
                    return "→", "stable", seven_day_avg
        except:
            pass
        return "", "", None

    @staticmethod
    def get_sensor_bar_color(sensor_type, last_reading):
        """Determine bar color based on sensor type and value."""
        if 'pH' in sensor_type:
            return "#4caf50" if 6.5 <= last_reading <= 8.5 else "#ff9800"
        elif 'Temperature' in sensor_type:
            return "#ff5722" if last_reading > 30 else "#2196f3"
        return "#2196f3"

    def generate_sensor_html(self, cursor, marker_id):
        """Generate HTML for sensor data display."""
        cursor.execute("""
            SELECT id, sensor_name, sensor_type, unit, last_reading, status
            FROM sensors WHERE equipment_marker_id = ?
            AND UPPER(status) = 'ACTIVE' ORDER BY sensor_type
        """, (marker_id,))

        sensor_rows = cursor.fetchall()
        if not sensor_rows:
            return ""

        html = f"""
<div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-top: 10px;">
    <h3 style="color: #2c5364; margin: 0 0 15px 0; font-size: 16px;">📊 Active Sensors ({len(sensor_rows)})</h3>
    <table style="width: 100%; border-collapse: collapse;">
"""
        for idx, (sensor_id, sensor_name, sensor_type, unit, last_reading, status) in enumerate(sensor_rows):
            value_str = f"{last_reading:.2f}" if last_reading else "N/A"
            bg_color = "#ffffff" if idx % 2 == 0 else "#f0f0f0"

            trend_arrow, trend_text, seven_day_avg = self.get_sensor_trend(cursor, sensor_id, last_reading)

            bar_width = 0
            bar_color = "#2196f3"
            if last_reading:
                min_val, max_val = self.SENSOR_RANGES.get(sensor_type.replace(' ', '_'), (0, 100))
                bar_width = min(100, max(0, (last_reading - min_val) / (max_val - min_val) * 100))
                bar_color = self.get_sensor_bar_color(sensor_type, last_reading)

            trend_html = f' <span style="font-size: 14px;">{trend_arrow} <span style="color: #666; font-size: 11px;">{trend_text}</span></span>' if trend_arrow else ''
            avg_html = f'<div style="font-size: 10px; color: #999; margin-top: 3px;">7d avg: {seven_day_avg:.2f} {unit or ""}</div>' if seven_day_avg else ''

            html += f"""
        <tr style="background: {bg_color};">
            <td style="padding: 10px; vertical-align: top;">
                <div style="font-weight: bold; margin-bottom: 5px;">
                    {sensor_type.replace('_', ' ').title()}{trend_html}
                </div>
                <div style="background: #ddd; border-radius: 10px; height: 8px; overflow: hidden;">
                    <div style="background: {bar_color}; height: 100%; width: {bar_width}%; transition: width 0.3s;"></div>
                </div>
                {avg_html}
            </td>
            <td style="padding: 10px; text-align: right; vertical-align: top;">
                <span style="color: {bar_color}; font-size: 18px; font-weight: bold;">{value_str}</span>
                <span style="color: #666; font-size: 12px; display: block; margin-top: 2px;">{unit or ''}</span>
            </td>
        </tr>
"""
        html += """
    </table>
</div>"""
        return html

    def generate_description_html(self, obj_name, eq_type, lat, lon, sensor_html):
        """Generate full description HTML for KML placemark."""
        sensor_content = sensor_html if sensor_html else '<p style="color: #999; font-style: italic;">No sensor data available</p>'
        return f"""
<div style="font-family: Arial, sans-serif; width: 350px; padding: 15px;">
    <h2 style="color: #2c5364; margin: 0 0 15px 0; font-size: 20px; border-bottom: 2px solid #4fc3f7; padding-bottom: 10px;">
        {obj_name}
    </h2>
    <table style="width: 100%; border-collapse: collapse; margin-bottom: 15px;">
        <tr style="background: #f0f0f0;">
            <td style="padding: 10px; font-weight: bold; width: 40%;">Type:</td>
            <td style="padding: 10px;">{eq_type.replace('_', ' ').title()}</td>
        </tr>
        <tr>
            <td style="padding: 10px; font-weight: bold;">Location:</td>
            <td style="padding: 10px; font-size: 12px;">{lat:.6f}°N<br>{lon:.6f}°E</td>
        </tr>
    </table>
    {sensor_content}
</div>"""

    def fetch_sensor_data(self, conn, obj_name):
        """Fetch sensor data HTML from database."""
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM project_markers WHERE name = ?", (obj_name,))
            marker_row = cursor.fetchone()
            if marker_row:
                return self.generate_sensor_html(cursor, marker_row[0])
        except Exception as e:
            LOGGER.log(f"Warning: Could not fetch sensors for {obj_name}: {e}")
        return ""

    def invoke(self, context, event):
        import os
        downloads_path = os.path.expanduser("~/Downloads")
        self.filepath = os.path.join(downloads_path, f"river_equipment_{datetime.now().strftime('%Y%m%d_%H%M%S')}.kml")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        import sqlite3
        from pathlib import Path
        import xml.etree.ElementTree as ET
        from . import river_utils

        # Setup paths and database
        script_dir = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER")
        db_path = script_dir / "klang_river_perfect.db"

        # Connect to database (GPS source of truth)
        conn = None
        try:
            conn = sqlite3.connect(str(db_path))
        except Exception as e:
            self.report({'ERROR'}, f"Could not connect to database: {e}")
            return {'CANCELLED'}

        cursor = conn.cursor()

        # Get all markers from database
        cursor.execute("""
            SELECT id, name, marker_type, latitude, longitude
            FROM project_markers
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
            ORDER BY name
        """)

        markers = cursor.fetchall()

        if not markers:
            self.report({'WARNING'}, "No markers with GPS found in database")
            conn.close()
            return {'CANCELLED'}

        # Build KML structure
        kml = ET.Element('kml', xmlns="http://www.opengis.net/kml/2.2")
        document = ET.SubElement(kml, 'Document')
        ET.SubElement(document, 'name').text = 'River Equipment Monitoring'
        ET.SubElement(document, 'description').text = 'Equipment sensors and monitoring stations'

        # Create styles
        self.create_kml_styles(document, river_utils.EQUIPMENT_COLORS_KML)

        # Export placemarks
        exported = 0
        skipped = 0

        # Track GPS bounds for debugging
        lats = []
        lons = []

        for marker_id, name, marker_type, lat, lon in markers:
            # DEBUG: Check BOOM_TRAP_040 specifically
            if name == "BOOM_TRAP_040":
                LOGGER.log(f"🔍 DEBUG BOOM_TRAP_040:")
                LOGGER.log(f"    name = {name}")
                LOGGER.log(f"    lat from DB = {lat}")
                LOGGER.log(f"    lon from DB = {lon}")

            if lat is None or lon is None:
                LOGGER.log(f"Skipping {name}: missing GPS (lat={lat}, lon={lon})")
                skipped += 1
                continue

            # Log first 3 markers for debugging
            if exported < 3:
                LOGGER.log(f"KML Export: {name} → lat={lat:.6f}, lon={lon:.6f}")

            lats.append(lat)
            lons.append(lon)

            eq_type = marker_type
            sensor_html = self.fetch_sensor_data(conn, name) if conn else ""

            # Create placemark
            placemark = ET.SubElement(document, 'Placemark')
            ET.SubElement(placemark, 'name').text = ''  # Hide label on map
            ET.SubElement(placemark, 'styleUrl').text = f'#{eq_type}'

            # Add description with sensor data
            description_elem = ET.SubElement(placemark, 'description')
            description_html = self.generate_description_html(name, eq_type, lat, lon, sensor_html)
            description_elem.text = f"<![CDATA[{description_html}]]>"

            # Add point coordinates
            point = ET.SubElement(placemark, 'Point')
            coord_string = f'{lon},{lat},0'
            ET.SubElement(point, 'coordinates').text = coord_string

            # DEBUG: Log anything east of BOOM_TRAP_040 + 10km (lon=101.771064 + ~0.09° ≈ 101.86)
            # 10km east ≈ 0.09° longitude at this latitude
            if lon > 101.86:
                LOGGER.log(f"⚠️  >10KM EAST OF BOOM_TRAP_040: {name} writing to KML: {coord_string}")
                LOGGER.log(f"    Read from DB: lat={lat}, lon={lon}")

            exported += 1

        if conn:
            conn.close()

        # Log GPS bounds for debugging
        if lats and lons:
            LOGGER.log(f"KML GPS Bounds: Lat [{min(lats):.6f}, {max(lats):.6f}], Lon [{min(lons):.6f}, {max(lons):.6f}]")
            LOGGER.log(f"Expected: Klang River area ~Lat [2.97, 3.26], Lon [101.37, 101.77]")

        # Write KML file with CDATA handling
        tree = ET.ElementTree(kml)
        ET.indent(tree, space="  ")

        import io
        output = io.BytesIO()
        tree.write(output, encoding='utf-8', xml_declaration=True)
        kml_content = output.getvalue().decode('utf-8')

        # Fix CDATA escaping
        kml_content = kml_content.replace('&lt;![CDATA[', '<![CDATA[')
        kml_content = kml_content.replace(']]&gt;', ']]>')
        kml_content = kml_content.replace('&lt;', '<')
        kml_content = kml_content.replace('&gt;', '>')

        with open(self.filepath, 'w', encoding='utf-8') as f:
            f.write(kml_content)

        LOGGER.log(f"Exported KML: {self.filepath}")
        LOGGER.log(f"Exported {exported} equipment markers (skipped {skipped})")

        # Show simple completion dialog
        def draw_info(self, context):
            layout = self.layout
            layout.label(text=f"✅ Exported {exported} equipment markers", icon='CHECKMARK')
            layout.separator()

            box = layout.box()
            box.label(text="📤 Share the KML file:", icon='INFO')
            box.label(text="  • WhatsApp / Email / USB")
            box.label(text="  • Open on phone with Google Earth")

            layout.separator()
            box = layout.box()
            box.label(text="📱 Recommended App:", icon='VIEWZOOM')
            box.label(text="  Google Earth (Free)")
            box.label(text="  - Android: Play Store")
            box.label(text="  - iOS: App Store")

            layout.separator()
            box = layout.box()
            box.label(text="💡 Tips:", icon='QUESTION')
            box.label(text="  • Tap markers for sensor data")
            box.label(text="  • Swipe down panel for fullscreen")
            box.label(text="  • Pinch to zoom")

        context.window_manager.popup_menu(draw_info, title="KML Export Complete", icon='CHECKMARK')

        self.report({'INFO'}, f"Exported {exported} markers to KML. Share via WhatsApp/Email!")

        return {'FINISHED'}


# =============================================================================
# MOBILE HTML EXPORT OPERATOR
# =============================================================================

class BIM_OT_equipment_export_mobile_html(Operator):
    """Export standalone mobile HTML with all data embedded (offline-ready)"""
    bl_idname = "bim.equipment_export_mobile_html"
    bl_label = "Export Mobile HTML"
    bl_options = {'REGISTER'}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def invoke(self, context, event):
        # Set default filename to Downloads folder
        import os
        downloads_path = os.path.expanduser("~/Downloads")
        self.filepath = os.path.join(downloads_path, f"river_mobile_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        import json
        import sqlite3
        from pathlib import Path

        # Paths
        script_dir = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER")
        db_path = script_dir / "klang_river_perfect.db"
        river_ui_path = script_dir / "RiverUI"

        # Read source files
        try:
            with open(river_ui_path / "styles.css", 'r') as f:
                css_content = f.read()
            with open(river_ui_path / "viewer_static_map.js", 'r') as f:
                viewer_js = f.read()
            with open(river_ui_path / "calculations.js", 'r') as f:
                calc_js = f.read()
        except Exception as e:
            self.report({'ERROR'}, f"Failed to read source files: {e}")
            return {'CANCELLED'}

        from . import river_utils

        # Get equipment objects
        equipment_objects = river_utils.get_all_equipment_objects()

        if not equipment_objects:
            self.report({'WARNING'}, "No equipment objects found in scene")
            return {'CANCELLED'}

        # Connect to database for sensor data
        conn = None
        try:
            conn = sqlite3.connect(str(db_path))
        except Exception as e:
            LOGGER.log(f"Warning: Could not connect to database: {e}")

        features = []
        exported = 0
        skipped = 0

        for obj in equipment_objects:
            lat = obj.get('latitude')
            lon = obj.get('longitude')

            if lat is None or lon is None:
                skipped += 1
                continue

            eq_type = river_utils.get_equipment_type(obj.name)
            color = river_utils.EQUIPMENT_COLORS_HEX.get(eq_type, '#FF6B35')

            # Get sensor data from database
            sensors = []
            if conn:
                try:
                    sensors = river_utils.fetch_sensor_data_from_db(conn.cursor(), obj.name)
                except Exception as e:
                    LOGGER.log(f"Warning: Could not fetch sensors for {obj.name}: {e}")

            feature = river_utils.create_geojson_feature(obj.name, eq_type, color, lat, lon, sensors)
            features.append(feature)
            exported += 1

        # Create markers GeoJSON
        markers_geojson = river_utils.create_geojson_collection(features)

        # Get river geometry if exists
        river_geojson_path = script_dir / "output/geojson/river_from_blender.geojson"
        river_geojson = {"type": "FeatureCollection", "features": []}
        if river_geojson_path.exists():
            try:
                with open(river_geojson_path, 'r') as f:
                    river_geojson = json.load(f)
            except:
                pass

        # Close database
        if conn:
            conn.close()

        # Build single-file HTML
        html_content = self.build_inline_html(css_content, viewer_js, calc_js, markers_geojson, river_geojson)

        # Write file
        try:
            with open(self.filepath, 'w', encoding='utf-8') as f:
                f.write(html_content)

            LOGGER.log(f"Exported mobile HTML: {self.filepath}")
            LOGGER.log(f"Exported {exported} equipment markers (skipped {skipped})")
            self.report({'INFO'}, f"Exported {exported} markers to {self.filepath}")

            # Open in browser
            import webbrowser
            webbrowser.open(f"file://{self.filepath}")

        except Exception as e:
            self.report({'ERROR'}, f"Failed to write file: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}

    def build_inline_html(self, css, viewer_js, calc_js, markers_data, river_data):
        """Build a single-file HTML with all assets embedded"""
        import json
        import base64
        from pathlib import Path

        # Embed background image as base64
        bg_image_base64 = ""
        bg_image_path = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/RiverUI/map_klang_valley.png")
        if bg_image_path.exists():
            try:
                with open(bg_image_path, 'rb') as img_file:
                    bg_image_base64 = base64.b64encode(img_file.read()).decode('utf-8')
                LOGGER.log(f"Embedded background image ({bg_image_path.stat().st_size // 1024}KB)")
            except Exception as e:
                LOGGER.log(f"Warning: Could not embed background image: {e}")

        # Create embedded data script
        embedded_data_js = f"""
// Embedded data for offline mode
const EMBEDDED_RIVER_DATA = {json.dumps(river_data)};
const EMBEDDED_MARKERS_DATA = {json.dumps(markers_data)};
"""

        # Modify viewer_js to use embedded data
        modified_viewer_js = viewer_js.replace(
            "async loadData() {",
            """async loadData() {
        // Use embedded data (offline mode)
        try {
            console.log('🔄 Loading embedded data...');
            const riverData = EMBEDDED_RIVER_DATA;
            const markersData = EMBEDDED_MARKERS_DATA;
"""
        ).replace(
            "const riverResponse = await fetch('output/geojson/river_from_blender.geojson?v=' + Date.now());",
            "// River data embedded"
        ).replace(
            "console.log('  River response status:', riverResponse.status);",
            ""
        ).replace(
            "const riverData = await riverResponse.json();",
            "// const riverData = EMBEDDED_RIVER_DATA; (already set above)"
        ).replace(
            "const markersResponse = await fetch('output/geojson/project_markers.geojson?v=' + Date.now());",
            "// Markers data embedded"
        ).replace(
            "console.log('  Markers response status:', markersResponse.status);",
            ""
        ).replace(
            "const markersData = await markersResponse.json();",
            "// const markersData = EMBEDDED_MARKERS_DATA; (already set above)"
        ).replace(
            "console.log('  Markers data features:', markersData.features ? markersData.features.length : 'NONE');",
            "console.log('  ✓ Embedded markers:', markersData.features ? markersData.features.length : 0);"
        )

        # Replace background image path with base64 data
        if bg_image_base64:
            modified_viewer_js = modified_viewer_js.replace(
                "this.bgImageSrc = 'map_klang_valley.png';",
                f"this.bgImageSrc = 'data:image/png;base64,{bg_image_base64}';"
            )
        else:
            # No background image - disable it
            modified_viewer_js = modified_viewer_js.replace(
                "this.showBackground = true;",
                "this.showBackground = false;"
            )

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <meta name="theme-color" content="#1e3c72">
    <title>Klang River - Mobile Viewer (Offline)</title>
    <style>
{css}

/* Mobile-specific enhancements */
@media (max-width: 768px) {{
    body {{
        padding: 0;
        margin: 0;
    }}

    .container {{
        padding: 10px;
    }}

    .header {{
        padding: 15px;
        border-radius: 8px;
    }}

    .header-content h1 {{
        font-size: 1.5rem;
    }}

    .header-content .subtitle {{
        font-size: 0.75rem;
    }}

    .stat-box {{
        padding: 8px 12px;
    }}

    .stat-value {{
        font-size: 1.25rem;
    }}

    #riverMap {{
        cursor: pointer;
        touch-action: none;
        width: 100%;
        height: auto;
        max-height: 50vh;
    }}

    .map-legend {{
        flex-wrap: wrap;
        gap: 12px;
        padding: 12px;
    }}

    .legend-item {{
        font-size: 0.75rem;
        min-width: 45%;
    }}

    .property-panel {{
        width: 95vw;
        max-width: 95vw;
        left: 2.5vw;
        right: 2.5vw;
        top: 10%;
        transform: translateY(0);
        max-height: 80vh;
    }}

    .property-panel.hidden {{
        transform: translateY(-150%);
    }}

    .property-content {{
        max-height: 60vh;
    }}

    .close-btn {{
        font-size: 2rem;
        padding: 0 10px;
        cursor: pointer;
    }}

    .panel-header h2 {{
        font-size: 1.25rem;
    }}

    .calc-panel {{
        display: none; /* Hide calculations on mobile to focus on map */
    }}
}}

/* Touch-friendly button sizing */
button, .btn-primary, .btn-export {{
    min-height: 44px;
    min-width: 44px;
    touch-action: manipulation;
}}

/* Prevent text selection during touch interactions */
.map-panel, #riverMap, .legend-item {{
    -webkit-user-select: none;
    user-select: none;
    -webkit-tap-highlight-color: transparent;
}}
    </style>
</head>
<body>
    <div class="container">
        <!-- Header (simplified for mobile) -->
        <header class="header" style="padding: 15px; text-align: center;">
            <div class="header-content">
                <h1 style="font-size: 1.5rem; margin-bottom: 5px;">River Equipment Monitor</h1>
                <p class="subtitle" style="font-size: 0.85rem;">Tap markers to view sensor data (offline mode)</p>
            </div>
        </header>

        <!-- Main Content Grid -->
        <div class="main-grid" style="grid-template-columns: 1fr;">
            <!-- Left Panel: Map View -->
            <div class="panel map-panel">
                <div class="panel-header">
                    <h2>River Corridor Map</h2>
                    <label style="color: white;">
                        <input type="checkbox" id="toggleRiver" checked style="margin-right: 4px;">
                        Show River
                    </label>
                </div>
                <div class="panel-content">
                    <canvas id="riverMap" width="800" height="530"></canvas>
                </div>
                <div class="map-legend">
                    <div class="legend-item">
                        <input type="checkbox" id="toggle_boom_trap" checked>
                        <span class="marker-dot" style="background: #FF4444;"></span>
                        <span>Boom Traps (40)</span>
                    </div>
                    <div class="legend-item">
                        <input type="checkbox" id="toggle_water_quality" checked>
                        <span class="marker-dot" style="background: #44AAFF;"></span>
                        <span>Water Quality (15)</span>
                    </div>
                    <div class="legend-item">
                        <input type="checkbox" id="toggle_pollutant_sensor" checked>
                        <span class="marker-dot" style="background: #FF9944;"></span>
                        <span>Pollutant Sensors (10)</span>
                    </div>
                    <div class="legend-item">
                        <input type="checkbox" id="toggle_wildlife_camera" checked>
                        <span class="marker-dot" style="background: #44FF44;"></span>
                        <span>Wildlife (12)</span>
                    </div>
                    <div class="legend-item">
                        <input type="checkbox" id="toggle_flood_monitor" checked>
                        <span class="marker-dot" style="background: #9944FF;"></span>
                        <span>Flood Monitors (8)</span>
                    </div>
                    <div class="legend-item">
                        <input type="checkbox" id="toggle_biochar_facility" checked>
                        <span class="marker-dot" style="background: #FFAA44;"></span>
                        <span>Biochar (3)</span>
                    </div>
                    <div class="legend-item">
                        <input type="checkbox" id="toggle_mrf_site" checked>
                        <span class="marker-dot" style="background: #FF44AA;"></span>
                        <span>MRF Sites (2)</span>
                    </div>
                </div>
            </div>

        </div>

        <!-- Property Panel (for marker details) -->
        <div id="propertyPanel" class="property-panel hidden">
            <div class="property-header">
                <h3 id="propertyTitle">Equipment Details</h3>
                <button id="closeProperty" class="close-btn">×</button>
            </div>
            <div id="propertyContent" class="property-content">
                <!-- Populated by JavaScript -->
            </div>
        </div>
    </div>

    <script>
// Embedded data must be loaded first
{embedded_data_js}
    </script>
    <script>
{calc_js}
    </script>
    <script>
{modified_viewer_js}
    </script>
    <script>
        // Initialize on load
        document.addEventListener('DOMContentLoaded', () => {{
            console.log('🚀 Initializing mobile viewer...');
            initRealViewer();
        }});
    </script>
</body>
</html>"""
        return html
