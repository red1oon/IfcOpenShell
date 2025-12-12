# Bonsai River Equipment Management Module

**ALPHA VERSION - Proof of Concept Demo**

A Blender addon module for managing georeferenced river infrastructure equipment with GPS tracking, sensor monitoring, and HTML map visualization.

## Author & License

**Author:** Redhuan D. Oon (red1org@gmail.com)
**License:** GPL v3.0
**Status:** Alpha testing - Demo POC calibrated and working

## Overview

This module extends Bonsai BIM with river infrastructure management capabilities:

- **Equipment Placement**: Place markers for river infrastructure (boom traps, sensors, monitors)
- **GPS Synchronization**: Automatic GPS coordinate calculation from Blender positions
- **Sensor Tracking**: Attach sensor data to equipment markers
- **Database Integration**: SQLite database for equipment and sensor data
- **Export Formats**: HTML map viewer, KML (Google Earth), mobile HTML
- **Real-time Visualization**: Interactive HTML dashboard with OpenStreetMap overlay

## Demo Setup Included

This alpha release includes a calibrated demo for the **Klang River, Malaysia**:

- `river_ui/demo/klang_river_perfect.db` - Demo database (78 equipment markers)
- `river_ui/demo/klang_river_perfect_full.blend` - Demo Blender file
- `river_ui/demo/klang_river_equipment.kml` - Google Earth export
- `river_ui/map_klang_valley.png` - Background map image

## Installation

1. **Install Bonsai** from the main repository
2. The River module is automatically included at:
   ```
   bonsai/bim/module/federation/river/
   ```
3. **Setup WORK_DIR** (for your own projects):
   ```bash
   mkdir -p ~/WORK_DIR/RIVER/output/geojson
   mkdir -p ~/WORK_DIR/RIVER/databases
   ```

## N Panel Interface Guide

Open Blender → **N Panel** → **River Equipment** tab

### 📍 Equipment Placement Panel

**Place New Marker:**
1. Select equipment type from dropdown (Boom Trap, Water Quality, etc.)
2. Click **"Place Equipment Marker"**
3. Position in 3D viewport at desired location
4. GPS coordinates calculated automatically

**Marker Types:**
- `boom_trap` - Floating debris barriers
- `water_quality` - Water quality monitoring stations
- `pollutant_sensor` - Pollution detection sensors
- `wildlife_camera` - Wildlife observation cameras
- `flood_monitor` - Water level and flood sensors

**Equipment Management:**
- **Select Equipment** - Pick marker from list to select in viewport
- **Delete Selected** - Remove selected marker from scene and database
- **Update GPS for Selected** - Recalculate GPS if marker was moved

### 🌐 GPS Calibration Panel

**GPS Auto-Sync:**
- **Enable/Disable Auto-Sync** - Toggle automatic GPS updates when objects move
- **Update GPS for Selected** - Manual GPS recalculation
- **Recalibrate GPS Anchor** - Reset GPS transformation reference

**How GPS Calibration Works:**
1. Equipment positions in Blender viewport = source of truth
2. GPS coordinates calculated using georeferenced transformation
3. Anchor point (westmost-southmost equipment) maintains GPS reference
4. All other equipment GPS calculated relative to anchor

**Calibration Files:**
- Database stores `georef_config` table with GPS bounds
- `gps_calibration.py` handles transformation calculations
- Uses centered affine transformation for accuracy

### 📊 Sensor Management Panel

**Attach Sensors:**
1. Select equipment marker in viewport
2. Click **"Add Sensor"**
3. Choose sensor type (Temperature, pH, Flow Rate, etc.)
4. Sensor stored in database linked to marker

**Sensor Types Available:**
- Temperature, pH, Dissolved Oxygen
- Turbidity, Flow Rate, Water Level
- BOD, COD, Conductivity
- Ammonia, Nitrate, Phosphate

**View Sensor Data:**
- Sensors display in HTML map popups
- Real-time readings shown with timestamp
- Status indicators (active/maintenance/inactive)

### 📤 Export & Launch Panel

**Export & Launch HTML Map:**
1. Click **"Export & Launch HTML Map"**
2. Exports equipment GPS to GeoJSON format
3. Starts local web server on `localhost:8000`
4. Opens interactive HTML map in browser

**Export Options:**
- **Export to KML** - For Google Earth/Maps viewing
- **Export Mobile HTML** - Standalone offline-ready HTML file
- **Open in Google Maps** - Launch Google Maps with marker location

**HTML Map Features:**
- Interactive pan/zoom map viewer
- Equipment markers colored by type
- Click markers to view sensor data
- OSM river overlay for geographic reference
- Filter by equipment type
- Background satellite imagery

### 🔧 Database Utilities Panel

**Database Operations:**
- **Load from DB** - Import equipment from database to Blender
- **Sync Blend → DB** - Update database with current Blender positions
- **Export Equipment List** - Generate CSV/Excel report

## File Structure

```
river/
├── README.md (this file)
├── __init__.py                    # Module registration
├── equipment_placement.py.old     # Original monolithic file (archive)
├── equipment_operators.py         # Main N Panel operators
├── equipment_export.py            # Export operators (HTML, KML, mobile)
├── equipment_sensor.py            # Sensor management
├── equipment_ui.py                # N Panel UI definitions
├── equipment_config.py            # Shared configuration
├── equipment_logger.py            # Logging utilities
├── equipment_gizmo.py             # Viewport gizmos
├── equipment_maintenance.py       # Maintenance scheduling
├── gps_calibration.py             # GPS coordinate utilities
├── gps_sync_handler.py            # Auto GPS sync handlers
├── centerline_osm.py              # OSM river mesh integration
├── river_utils.py                 # Shared utilities
└── river_ui/                      # HTML map viewer
    ├── index.html                 # Main HTML viewer
    ├── viewer_static_map.js       # Map rendering engine
    ├── styles.css                 # UI styling
    ├── calculations.js            # Coordinate calculations
    ├── map_klang_valley.png       # Background map
    ├── README.md                  # HTML viewer documentation
    └── demo/                      # Demo assets
        ├── klang_river_perfect.db
        ├── klang_river_perfect_full.blend
        └── klang_river_equipment.kml
```

## Database Schema

**Tables:**
- `project_markers` - Equipment locations (X/Y/Z, GPS, type, status)
- `sensors` - Sensor data linked to equipment
- `georef_config` - GPS calibration bounds (Blender ↔ GPS)
- `element_transforms` - Mesh offset transformations

**Key Fields:**
```sql
project_markers:
  - id, name, location_x/y/z (Blender coords)
  - latitude, longitude (GPS coords)
  - marker_type, created_at

georef_config:
  - blender_x/y_min/max (Blender bounds)
  - gps_lon/lat_min/max (GPS bounds)
  - crs (coordinate system, EPSG:4326)
```

## Workflow Example

### Setting Up a New River Project

1. **Create Project Database:**
   ```bash
   cd ~/WORK_DIR/RIVER
   sqlite3 my_river.db < schema.sql
   ```

2. **Import River Mesh:**
   - Import IFC/OSM river geometry into Blender
   - Use `centerline_osm.py` for OSM data

3. **Set GPS Calibration:**
   - Place at least 2 reference markers at known GPS locations
   - Click **"Recalibrate GPS Anchor"**
   - System calculates transformation from Blender → GPS

4. **Place Equipment:**
   - Use **"Place Equipment Marker"** in N Panel
   - Position markers in 3D viewport along river
   - GPS auto-calculated and saved to database

5. **Add Sensors:**
   - Select equipment marker
   - Click **"Add Sensor"**
   - Enter sensor specifications and initial readings

6. **Export and View:**
   - Click **"Export & Launch HTML Map"**
   - Verify markers appear at correct GPS locations
   - Adjust scale/offset if needed in `viewer_static_map.js`

### Calibrating GPS for Your Region

The demo is calibrated for Klang River. For your own river:

1. **Get GPS Bounds:**
   - Open OpenStreetMap or Google Earth
   - Note GPS coordinates of river extent (min/max lat/lon)

2. **Update `georef_config` Table:**
   ```sql
   UPDATE georef_config SET
     blender_x_min = -1000, blender_x_max = 1000,  -- Your Blender bounds
     blender_y_min = -500, blender_y_max = 500,
     gps_lon_min = 101.3, gps_lon_max = 101.7,     -- Your GPS bounds
     gps_lat_min = 2.97, gps_lat_max = 3.25;
   ```

3. **Test with Reference Points:**
   - Place equipment at known GPS location
   - Verify GPS calculation matches expected coordinates
   - Adjust bounds if needed

## HTML Viewer Customization

**Scale/Offset Settings** (`viewer_static_map.js` lines 61-66):
```javascript
this.overlayScale = 1.95;     // Marker spread scale
this.riverScale = 2.3;        // River line scale
this.riverOffsetX = 207;      // River horizontal offset (px)
this.riverOffsetY = -130;     // River vertical offset (px)
```

**GPS Bounds** (lines 234-237):
```javascript
this.bounds.lon_min = 101.357;
this.bounds.lon_max = 101.781;
this.bounds.lat_min = 2.963;
this.bounds.lat_max = 3.244;
```

Adjust these values to align markers/river overlay for your region.

## Known Issues & Limitations

- **Alpha Status**: Not production-ready, expect bugs
- **Hardcoded Paths**: Some paths reference `/WORK_DIR/RIVER` (to be made configurable)
- **Single River**: Currently designed for one river per project
- **GPS Accuracy**: ±10m typical accuracy depending on calibration quality
- **Symlink Dependency**: `output` symlink must point to valid WORK_DIR path
- **Server Port**: localhost:8000 hardcoded (may conflict with other services)

## Troubleshooting

**HTML Map Blank:**
- Hard refresh browser: `Ctrl+Shift+R`
- Check browser console (F12) for JavaScript errors
- Verify `output/geojson/` contains data files
- Check server running: `lsof -i :8000`

**GPS Coordinates Wrong:**
- Recalibrate GPS anchor with reference points
- Check `georef_config` bounds match your region
- Verify Blender object positions are correct

**Export Fails:**
- Verify database path exists and is writable
- Check WORK_DIR structure created
- Ensure `output/geojson/` directory exists

**Markers Don't Appear:**
- Check `calculateBounds()` in `viewer_static_map.js`
- Verify GPS range matches exported marker coordinates
- Adjust `overlayScale` setting

## Development Roadmap

**Planned Features:**
- [ ] Multi-river project support
- [ ] User-configurable WORK_DIR paths
- [ ] 4D timeline visualization (sensor data over time)
- [ ] Clash detection with river mesh
- [ ] Mobile app integration (offline KML sync)
- [ ] Real-time sensor data streaming
- [ ] Maintenance scheduling workflow
- [ ] Equipment lifecycle tracking

## Contributing

This module is part of the Bonsai/IfcOpenShell project.

**Report Issues:**
- GitHub: https://github.com/IfcOpenShell/IfcOpenShell/issues
- Email: red1org@gmail.com

**Development Guidelines:**
- Follow Bonsai coding standards
- Test with demo database before committing
- Update README for new features
- Maintain GPL v3.0 compatibility

## References

**Related Modules:**
- `federation/` - Parent module for federated BIM models
- `federation/river/` - This module

**External Dependencies:**
- SQLite3 - Database backend
- OpenStreetMap - River geometry data
- Leaflet/OpenLayers - HTML map rendering (future)

## Credits

**Development:**
- Redhuan D. Oon - Core module development
- Claude Code - Code assistance and documentation

**Demo Data:**
- Klang River mesh from OpenStreetMap
- Equipment placement based on real-world locations
- Sensor specifications from environmental monitoring standards

## License

```
Bonsai River Equipment Management Module
Copyright (C) 2025 Redhuan D. Oon

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.
```

---

**Last Updated:** 2025-12-13
**Version:** 0.1.0-alpha
**Tested With:** Blender 4.2+, Bonsai 2024.12+
