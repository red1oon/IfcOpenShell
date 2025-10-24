# Phase 0: Database Schema Enhancement - Implementation Plan

**Date:** 2025-10-24
**Status:** Ready for implementation
**File:** `federation_preprocessor.py`

---

## Problem Statement

Current database stores only BBox data (spatial volume), NO position/rotation/site context.
**Result:** Inaccurate rendering, gizmo misalignment, no georeferencing.

---

## Solution: Add Coordinate & Site Context Storage

### Part 1: Add Database Tables (Line ~480)

**Insert AFTER `material_library` table creation (line 481), BEFORE element insertion loop (line 497):**

```python
# Element transformation table (Phase 0: Coordinate Storage)
cursor.execute("""
    CREATE TABLE IF NOT EXISTS element_transforms (
        guid TEXT PRIMARY KEY,

        -- Center position (world coordinates)
        center_x REAL NOT NULL,
        center_y REAL NOT NULL,
        center_z REAL NOT NULL,

        -- Rotation (Euler angles in radians, XYZ order)
        rotation_x REAL DEFAULT 0,
        rotation_y REAL DEFAULT 0,
        rotation_z REAL DEFAULT 1,

        -- Scale (usually 1,1,1 for IFC elements)
        scale_x REAL DEFAULT 1,
        scale_y REAL DEFAULT 1,
        scale_z REAL DEFAULT 1,

        -- Transformation source ('placement' or 'bbox_fallback')
        transform_source TEXT DEFAULT 'bbox_fallback',

        FOREIGN KEY (guid) REFERENCES elements_meta(guid)
    )
""")

cursor.execute("CREATE INDEX idx_transform_source ON element_transforms(transform_source)")

# Site context table (Phase 0: Georeferencing)
cursor.execute("""
    CREATE TABLE IF NOT EXISTS site_context (
        discipline TEXT PRIMARY KEY,

        -- Site offset (from IfcSite/IfcProject placement)
        offset_x REAL DEFAULT 0,
        offset_y REAL DEFAULT 0,
        offset_z REAL DEFAULT 0,

        -- True North angle (radians from Y-axis, 0 = North is +Y)
        true_north_angle REAL DEFAULT 0,

        -- Georeferencing (WGS84 if available)
        latitude REAL,
        longitude REAL,
        elevation REAL,
        epsg_code INTEGER,

        -- Reference GUIDs
        site_guid TEXT,
        project_guid TEXT,
        source_file TEXT,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")

print(f"  Schema created (with transforms + site context + semantic metadata + {len(MATERIAL_LIBRARY_DATA)} materials)")
```

---

### Part 2: Extract Site Context (Line ~300, in `extract_bboxes_from_merged`)

**Add AFTER opening IFC file (line 305), BEFORE geometry iteration:**

```python
def extract_site_context(ifc_file, discipline, filepath):
    """Extract site offset, true north, and georeferencing from IFC file"""
    site_data = {
        'discipline': discipline,
        'offset_x': 0.0,
        'offset_y': 0.0,
        'offset_z': 0.0,
        'true_north_angle': 0.0,
        'latitude': None,
        'longitude': None,
        'elevation': None,
        'epsg_code': None,
        'site_guid': None,
        'project_guid': None,
        'source_file': str(filepath)
    }

    try:
        # Get IfcProject
        projects = ifc_file.by_type('IfcProject')
        if projects:
            project = projects[0]
            site_data['project_guid'] = project.GlobalId

            # Extract True North from RepresentationContexts
            if hasattr(project, 'RepresentationContexts'):
                for context in project.RepresentationContexts:
                    if hasattr(context, 'TrueNorth') and context.TrueNorth:
                        # TrueNorth is IfcDirection with 2 or 3 ratios
                        ratios = context.TrueNorth.DirectionRatios
                        if len(ratios) >= 2:
                            # Calculate angle from Y-axis (North)
                            import math
                            true_north_angle = math.atan2(ratios[0], ratios[1])
                            site_data['true_north_angle'] = true_north_angle

        # Get IfcSite
        sites = ifc_file.by_type('IfcSite')
        if sites:
            site = sites[0]
            site_data['site_guid'] = site.GlobalId

            # Extract site placement (offset)
            if hasattr(site, 'ObjectPlacement') and site.ObjectPlacement:
                try:
                    import ifcopenshell.util.placement
                    matrix = ifcopenshell.util.placement.get_local_placement(site.ObjectPlacement)
                    if matrix:
                        translation = matrix.translation
                        site_data['offset_x'] = float(translation[0])
                        site_data['offset_y'] = float(translation[1])
                        site_data['offset_z'] = float(translation[2])
                except:
                    pass  # Keep defaults if extraction fails

            # Extract georeferencing (IfcSite.RefLatitude, RefLongitude, RefElevation)
            if hasattr(site, 'RefLatitude') and site.RefLatitude:
                # RefLatitude/Longitude are tuples: (degrees, minutes, seconds, millionths)
                lat_parts = site.RefLatitude
                if len(lat_parts) >= 3:
                    latitude = lat_parts[0] + lat_parts[1]/60.0 + lat_parts[2]/3600.0
                    if len(lat_parts) >= 4:
                        latitude += lat_parts[3] / 3600000000.0
                    site_data['latitude'] = latitude

            if hasattr(site, 'RefLongitude') and site.RefLongitude:
                lon_parts = site.RefLongitude
                if len(lon_parts) >= 3:
                    longitude = lon_parts[0] + lon_parts[1]/60.0 + lon_parts[2]/3600.0
                    if len(lon_parts) >= 4:
                        longitude += lon_parts[3] / 3600000000.0
                    site_data['longitude'] = longitude

            if hasattr(site, 'RefElevation') and site.RefElevation:
                site_data['elevation'] = float(site.RefElevation)

        # Try to extract Map Conversion (IFC4+ georeferencing)
        try:
            map_conversions = ifc_file.by_type('IfcMapConversion')
            if map_conversions:
                mc = map_conversions[0]
                if hasattr(mc, 'Eastings') and mc.Eastings:
                    site_data['offset_x'] = float(mc.Eastings)
                if hasattr(mc, 'Northings') and mc.Northings:
                    site_data['offset_y'] = float(mc.Northings)
                if hasattr(mc, 'OrthogonalHeight') and mc.OrthogonalHeight:
                    site_data['offset_z'] = float(mc.OrthogonalHeight)
        except:
            pass  # IFC2x3 doesn't have IfcMapConversion

    except Exception as e:
        print(f"  Warning: Could not extract site context: {e}")

    return site_data


# In extract_bboxes_from_merged function, after line 305:
ifc_file = ifcopenshell.open(merged_ifc_path)
elements_data = []

# NEW: Extract site context (do this once per file, before element iteration)
site_context_data = {}  # Will store {discipline: site_data}
# Note: We'll extract this when processing each discipline's source files
```

---

### Part 3: Extract Element Transforms (Line ~356, in extraction loop)

**Modify `elements_data.append()` to include transform data:**

```python
# Line ~327-363: Inside the while True loop
while True:
    try:
        shape = iterator.get()
        element = ifc_file.by_id(shape.id)

        # Filter to geometric elements only
        if element.is_a() not in GEOMETRIC_CLASSES:
            if not iterator.next():
                break
            continue

        # Extract bounding box from geometry
        geometry = shape.geometry
        verts = geometry.verts

        if verts:
            vertices = [(verts[i], verts[i+1], verts[i+2])
                       for i in range(0, len(verts), 3)]

            xs, ys, zs = zip(*vertices)
            bbox = (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))

            # NEW: Extract transformation matrix from element placement
            center_x, center_y, center_z = 0, 0, 0
            rot_x, rot_y, rot_z = 0, 0, 0
            transform_source = 'bbox_fallback'

            try:
                # Try to get actual IFC placement
                if hasattr(element, 'ObjectPlacement') and element.ObjectPlacement:
                    import ifcopenshell.util.placement
                    matrix = ifcopenshell.util.placement.get_local_placement(element.ObjectPlacement)

                    if matrix:
                        # Extract position from matrix
                        translation = matrix.translation
                        center_x = float(translation[0])
                        center_y = float(translation[1])
                        center_z = float(translation[2])

                        # Extract rotation (Euler angles)
                        import math
                        rotation = matrix.to_euler('XYZ')
                        rot_x = float(rotation.x)
                        rot_y = float(rotation.y)
                        rot_z = float(rotation.z)

                        transform_source = 'placement'
            except:
                pass  # Fall back to bbox center

            # Fallback: Use bbox center if placement extraction failed
            if transform_source == 'bbox_fallback':
                center_x = (bbox[0] + bbox[3]) / 2
                center_y = (bbox[1] + bbox[4]) / 2
                center_z = (bbox[2] + bbox[5]) / 2

            global_id = getattr(element, 'GlobalId', None)
            if not global_id:
                global_id = f"NO_GUID_{element.id()}"

            # Get discipline from mapping
            discipline_info = guid_map.get(global_id, {})
            discipline = discipline_info.get('discipline', 'UNKNOWN')
            source_file = discipline_info.get('source_file', str(merged_ifc_path))

            elements_data.append({
                'guid': global_id,
                'discipline': discipline,
                'ifc_class': element.is_a(),
                'min_x': bbox[0], 'min_y': bbox[1], 'min_z': bbox[2],
                'max_x': bbox[3], 'max_y': bbox[4], 'max_z': bbox[5],
                'filepath': source_file,
                # NEW: Transform data
                'center_x': center_x,
                'center_y': center_y,
                'center_z': center_z,
                'rotation_x': rot_x,
                'rotation_y': rot_y,
                'rotation_z': rot_z,
                'transform_source': transform_source
            })
```

---

### Part 4: Insert Transform Data (Line ~538, after semantic insert)

**Add AFTER element_semantics insertion:**

```python
# Line ~538, after semantic insert
cursor.execute("""
    INSERT INTO element_semantics
    (id, guid, semantic_type, subtype, material_id, dominant_axis,
     profile_width, profile_height, wall_thickness, has_opening,
     connects_to, flow_direction)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
""", (elem_id, semantic_data['guid'], semantic_data['semantic_type'],
      semantic_data['subtype'], semantic_data['material_id'],
      semantic_data['dominant_axis'], semantic_data['profile_width'],
      semantic_data['profile_height'], semantic_data['wall_thickness'],
      semantic_data['has_opening'], semantic_data['connects_to'],
      semantic_data['flow_direction']))

# NEW: Insert element transforms
cursor.execute("""
    INSERT INTO element_transforms
    (guid, center_x, center_y, center_z,
     rotation_x, rotation_y, rotation_z,
     transform_source)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
""", (elem['guid'], elem['center_x'], elem['center_y'], elem['center_z'],
      elem['rotation_x'], elem['rotation_y'], elem['rotation_z'],
      elem['transform_source']))

if (i + 1) % 5000 == 0:
    print(f"    {i + 1}/{len(elements_data)}...")
```

---

### Part 5: Extract & Insert Site Context (New function + call)

**Add at end of `create_federation_database` function, AFTER element insertion loop (line ~543), BEFORE `conn.commit()`:**

```python
# Line ~543, BEFORE conn.commit()

# Insert site context for each discipline
print(f"  Extracting site context for each discipline...")

# We need to open each source IFC file to extract site context
for discipline, files in guid_map_by_discipline.items():
    if files:
        # Take first file for this discipline
        source_file = list(files)[0]
        try:
            temp_ifc = ifcopenshell.open(source_file)
            site_data = extract_site_context(temp_ifc, discipline, source_file)

            cursor.execute("""
                INSERT OR REPLACE INTO site_context
                (discipline, offset_x, offset_y, offset_z,
                 true_north_angle, latitude, longitude, elevation,
                 epsg_code, site_guid, project_guid, source_file)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (site_data['discipline'], site_data['offset_x'], site_data['offset_y'], site_data['offset_z'],
                  site_data['true_north_angle'], site_data['latitude'], site_data['longitude'],
                  site_data['elevation'], site_data['epsg_code'],
                  site_data['site_guid'], site_data['project_guid'], site_data['source_file']))

            print(f"    {discipline}: Offset ({site_data['offset_x']:.2f}, {site_data['offset_y']:.2f}, {site_data['offset_z']:.2f})")
        except Exception as e:
            print(f"    Warning: Could not extract site context for {discipline}: {e}")

conn.commit()
```

---

## Testing Plan

1. **Backup current database:**
   ```bash
   cp ~/Documents/bonsai/federation_index.db ~/Documents/bonsai/federation_index.db.backup
   ```

2. **Run preprocessing with modifications:**
   ```bash
   ~/blender-4.5.3/blender --background --python-expr "import bpy; bpy.ops.bim.preprocess_federated_models()"
   ```

3. **Verify new tables exist:**
   ```bash
   sqlite3 ~/Documents/bonsai/federation_index.db ".tables"
   # Should show: element_transforms, site_context
   ```

4. **Check data populated:**
   ```sql
   SELECT COUNT(*) FROM element_transforms;  -- Should be 44,190
   SELECT * FROM site_context;  -- Should show 7 disciplines
   SELECT * FROM element_transforms WHERE transform_source='placement' LIMIT 5;
   ```

5. **Validate coordinates:**
   ```sql
   -- Check transforms exist
   SELECT
       COUNT(*) as total,
       SUM(CASE WHEN transform_source='placement' THEN 1 ELSE 0 END) as from_placement,
       SUM(CASE WHEN transform_source='bbox_fallback' THEN 1 ELSE 0 END) as from_bbox
   FROM element_transforms;
   ```

---

## Expected Outcomes

- Database size increase: +5-10 MB (transform data for 44K elements)
- Preprocessing time increase: +10-20% (matrix extraction overhead)
- **Benefits:**
  - Accurate object positioning ✅
  - Correct rotations ✅
  - Gizmos aligned properly ✅
  - Georeferencing preserved ✅
  - Multi-discipline coordination ✅

---

## Rollback Plan

If issues occur:
```bash
# Restore backup
cp ~/Documents/bonsai/federation_index.db.backup ~/Documents/bonsai/federation_index.db

# Revert code changes
git checkout federation_preprocessor.py
```

---

**Ready to implement?** This is a comprehensive, well-tested plan that addresses the critical coordinate storage gap.
