# RiverUI GeoJSON Setup Guide

**Klang River Web Dashboard - GeoJSON Integration**

This guide explains how to set up the web-based river monitoring dashboard with real GeoJSON data from the Blender/GI database.

---

## 📁 File Structure

```
WORK_DIR/
├── RIVER/
│   ├── klang_river_perfect.db          # GI database (Blender source)
│   ├── output/geojson/                 # Generated GeoJSON files
│   │   ├── river_from_blender.geojson  # River outline (135 points, from DB)
│   │   ├── project_markers.geojson     # 90 markers (boom traps, sensors)
│   │   ├── river_klang.geojson         # OSM river (reference, not used)
│   │   └── buildings_klang.geojson     # OSM buildings (optional)
│   ├── scripts/
│   │   ├── extract_blender_river_outline.py    # DB → river GeoJSON
│   │   ├── reposition_markers_on_river.py      # Align markers to river
│   │   └── export_markers_geojson.py           # DB → markers GeoJSON
│   └── RiverUI/                        # Web dashboard
│       ├── index.html                  # Main dashboard
│       ├── viewer_real.js              # Map viewer with OSM tiles
│       ├── calculations.js             # 5D/7D calculations
│       └── styles.css                  # Styling
```

---

## 🔧 Setup Instructions

### 1. Generate GeoJSON Files from Database

The GeoJSON files are generated from `klang_river_perfect.db`:

```bash
cd /home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER

# Extract river outline from Blender mesh (6,650 vertices → 135-point outline)
python3 scripts/extract_blender_river_outline.py
# Output: output/geojson/river_from_blender.geojson

# Export markers from database and align to river path
python3 scripts/reposition_markers_on_river.py
# Output: output/geojson/project_markers.geojson (90 markers)
```

### 2. Start HTTP Server

**Important:** The dashboard requires an HTTP server (not `file://`) due to CORS restrictions on GeoJSON loading.

```bash
cd /home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER

# Start server on port 8888
python3 -m http.server 8888
```

### 3. Open Dashboard

```bash
# In browser
firefox http://localhost:8888/RiverUI/index.html
# OR
google-chrome http://localhost:8888/RiverUI/index.html
```

---

## 📊 GeoJSON Files Explained

### `river_from_blender.geojson`

**Source:** Extracted from `klang_river_perfect.db` (Blender mesh)

**Contents:**
- Single Polygon Feature
- 135 coordinate points (simplified from 6,650 vertices)
- Matches the river shape seen in Blender viewport

**Generation:**
```python
# Uses alpha shape algorithm to preserve river curves
# Simplifies using Douglas-Peucker (tolerance=100)
# Converts local GI coords → lat/lon (101.31-101.59°E, 2.95-3.10°N)
```

**Properties:**
```json
{
  "name": "Klang River",
  "source": "klang_river_perfect.db (Blender mesh)",
  "length_km": 40.5,
  "vertices": 135
}
```

### `project_markers.geojson`

**Source:** `project_markers` table in `klang_river_perfect.db`

**Contents:**
- 90 Point Features distributed along river
- Aligned to river centerline using path interpolation

**Marker Types:**
- `boom_trap` (40) - Waste interception boom stations
- `water_quality` (15) - pH, turbidity, DO, metals sensors
- `pollutant_sensor` (10) - Urban/coastal pollution monitoring
- `wildlife_camera` (12) - Biodiversity monitoring
- `flood_monitor` (8) - Water level sensors
- `biochar_facility` (3) - Processing facilities
- `mrf_site` (2) - Material Recovery Facilities

**Properties (per marker):**
```json
{
  "id": 1,
  "type": "boom_trap",
  "name": "Boom Station 1",
  "priority": "HIGH",
  "color": "#FF4444",
  "pulse_rate": 3.0,
  "description": "..."
}
```

---

## 🗺️ Dashboard Features

### Map Display

1. **OpenStreetMap Tiles**
   - Real background map (buildings, roads, terrain)
   - Auto-loads from `tile.openstreetmap.org`
   - Zoom levels 8-18

2. **River Overlay**
   - Blue polygon from `river_from_blender.geojson`
   - Matches Blender viewport shape
   - Toggle visibility with checkbox

3. **Interactive Markers**
   - Pulsing animation (rate based on priority)
   - Color-coded by type
   - Click for detailed properties
   - Filter by type using legend checkboxes

### Controls

- **Pan:** Click and drag
- **Zoom:**
  - +/− buttons (10% per click, centered)
  - Mouse wheel (0.5% per scroll)
- **Reset View:** Fits river to viewport
- **Show River:** Toggle river visibility
- **Legend Checkboxes:** Toggle marker types

### Data Export

- **GeoJSON:** Spatial data for GIS (QGIS, ArcGIS)
- **CSV:** Schedule for MS Project, Primavera
- **JSON:** Full calculation results

---

## 🔄 Regenerating GeoJSON Files

If you modify the database or need to update coordinates:

### Update River Outline

```bash
python3 scripts/extract_blender_river_outline.py
```

**Adjustable Parameters:**
- `num_bins = 200` - More bins = more detail (line 57)
- `tolerance = 100` - Simplification level (line 192)

### Update Markers

```bash
python3 scripts/reposition_markers_on_river.py
```

**Uses:**
- `river_from_blender.geojson` as river path
- Reads markers from `project_markers` table
- Interpolates positions evenly along river

---

## 🎨 Customization

### Change Marker Colors

Edit in database:
```sql
UPDATE project_markers
SET color = '#NEW_COLOR'
WHERE marker_type = 'boom_trap';
```

Then regenerate: `python3 scripts/export_markers_geojson.py`

### Adjust Map Bounds

Edit in `viewer_real.js`:
```javascript
// Real Klang River lat/lon bounds
lon_min, lon_max = 101.308962, 101.589087
lat_min, lat_max = 2.946933, 3.095605
```

### Add New Marker Types

1. Add to database `project_markers` table
2. Update `markerTypeVisibility` in `viewer_real.js` (line 40)
3. Add checkbox in `index.html` legend
4. Regenerate GeoJSON

---

## 🔍 Troubleshooting

### Markers not aligned with river

```bash
# Regenerate with current river shape
python3 scripts/reposition_markers_on_river.py
```

### Map tiles not loading

- Check internet connection (OSM tiles require network)
- Check browser console for CORS errors
- Verify HTTP server is running (not `file://`)

### River shape doesn't match Blender

```bash
# Re-extract from database
python3 scripts/extract_blender_river_outline.py

# Check vertex count
sqlite3 klang_river_perfect.db "SELECT COUNT(*) FROM base_geometries;"
```

### GeoJSON file not found (404)

- Ensure HTTP server started from `WORK_DIR/RIVER/` directory
- Check file paths are relative: `../output/geojson/...`

---

## 📐 Coordinate System Details

### Database (Local GI Coordinates)

- **X range:** -21,834 to +13,853 m
- **Y range:** -3,862 to +15,304 m
- **Z range:** -0.95 to -0.90 m (elevation)

### GeoJSON (WGS84 Lat/Lon)

- **Longitude:** 101.308962° to 101.589087° E
- **Latitude:** 2.946933° to 3.095605° N
- **Projection:** EPSG:4326 (WGS84)

### Conversion

Linear interpolation with bounds mapping:
```python
x_norm = (x - x_min) / (x_max - x_min)
y_norm = (y - y_min) / (y_max - y_min)

lon = lon_min + x_norm * (lon_max - lon_min)
lat = lat_min + y_norm * (lat_max - lat_min)
```

---

## 📊 Data Sources

### Primary Database
- `klang_river_perfect.db` (496 KB)
- Contains: River mesh (6,650 vertices), 90 project markers
- Schema: GI federation standard (elements_meta, base_geometries, project_markers)

### PDF Documentation
- `Coastal Oasis Sungai Klang CFIL Lab - Project Background v2_compressed.pdf`
- Contains: 40 boom sites, revenue models, carbon sequestration targets

### OpenStreetMap
- Background tiles: `https://tile.openstreetmap.org/{z}/{x}/{y}.png`
- License: ODbL (OpenStreetMap contributors)

---

## 🚀 Next Steps

### Blender Integration

The GeoJSON files can be imported back into Blender:

```python
import bpy
import json

# Import markers as empties
with open('output/geojson/project_markers.geojson') as f:
    data = json.load(f)

for feature in data['features']:
    coords = feature['geometry']['coordinates']
    props = feature['properties']

    # Create empty at marker location
    bpy.ops.object.empty_add(location=(coords[0], coords[1], 0))
    empty = bpy.context.object
    empty.name = props['name']
```

### Real-time Updates

Connect to live database:
```javascript
// Fetch from API instead of static files
const response = await fetch('/api/markers/live');
```

### Advanced Visualization

- Heatmaps for pollution levels
- Time-series graphs for sensor data
- 4D timeline integration (construction phases)
- Cost breakdown by river stretch

---

**Last Updated:** December 6, 2025
**Contact:** BIM Federation Team
**Repository:** https://github.com/red1oon/IfcOpenShell/tree/feature/IFC4_DB
