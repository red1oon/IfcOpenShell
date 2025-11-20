# Production BIM Object Library

**Version:** 1.0 (2025-11-21)
**Source:** Terminal 1 Airport Project (enhanced_federation.db)
**Total Objects:** 6,890 unique objects
**Database Size:** 123 MB

---

## Contents

This production library contains real-world LOD300-350 BIM objects extracted from professional consultant deliverables for the Terminal 1 airport project.

### Object Categories

| Category | Object Count | Description |
|----------|--------------|-------------|
| **Architectural** | 614 | Doors (135), Windows (236), Furniture (176), Stairs (32), Railings (34) |
| **MEP Lighting** | 814 | Light fixtures across all zones |
| **MEP HVAC** | 1,258 | Air terminals (289), Flow terminals (256), Duct fittings (713) |
| **MEP Plumbing** | 3,190 | Pipe fittings (3,058), Valves (111), Flow controllers (21) |
| **Fire Protection** | 989 | Sprinkler heads (899), Alarms (80) |
| **Electrical** | 25 | Electric appliances (19), Controllers (6) |

**Total:** 6,890 catalog entries referencing 6,303 unique geometries

---

## Database Schema

### Tables

#### `base_geometries`
Deduplicated 3D mesh geometry, centered at origin.

```sql
CREATE TABLE base_geometries (
    geometry_hash TEXT PRIMARY KEY,      -- SHA256 of vertices+faces
    vertices BLOB NOT NULL,              -- Float32 array (x,y,z,x,y,z,...)
    faces BLOB NOT NULL,                 -- Int32 array (i,j,k,l,i,j,k,l,...)
    normals BLOB,                        -- Float32 array (optional)
    vertex_count INTEGER NOT NULL,
    face_count INTEGER NOT NULL,
    bbox_width REAL,                     -- Meters
    bbox_depth REAL,                     -- Meters
    bbox_height REAL                     -- Meters
);
```

#### `object_catalog`
Metadata and categorization for each object.

```sql
CREATE TABLE object_catalog (
    catalog_id INTEGER PRIMARY KEY,
    geometry_hash TEXT NOT NULL,         -- FK to base_geometries
    ifc_class TEXT NOT NULL,             -- IfcDoor, IfcWindow, etc.
    object_type TEXT NOT NULL,           -- door_single, toilet, etc.
    category TEXT NOT NULL,              -- Architectural, MEP_HVAC, etc.
    width_mm INTEGER,                    -- Millimeters
    depth_mm INTEGER,
    height_mm INTEGER,
    description TEXT,
    source_guid TEXT,                    -- Original IFC GUID
    source_file TEXT,                    -- enhanced_federation.db
    extraction_date TIMESTAMP
);
```

---

## Usage Examples

### Query by Object Type

```python
import sqlite3

conn = sqlite3.connect('production_library.db')
cursor = conn.cursor()

# Find all single doors
cursor.execute("""
    SELECT catalog_id, width_mm, height_mm, geometry_hash
    FROM object_catalog
    WHERE object_type = 'door_single'
    ORDER BY width_mm
""")

for cat_id, width, height, geom_hash in cursor.fetchall():
    print(f"Door: {width}mm × {height}mm (hash: {geom_hash[:8]}...)")
```

### Import Geometry into Project

```python
def import_from_library(object_type: str, position: tuple):
    """Import object geometry from library at specified position"""

    # Query library
    cursor.execute("""
        SELECT bg.vertices, bg.faces, oc.width_mm, oc.height_mm
        FROM object_catalog oc
        JOIN base_geometries bg ON oc.geometry_hash = bg.geometry_hash
        WHERE oc.object_type = ?
        LIMIT 1
    """, (object_type,))

    vertices_blob, faces_blob, width, height = cursor.fetchone()

    # Unpack geometry
    import struct
    vertex_count = len(vertices_blob) // 4
    vertices = list(struct.unpack(f'<{vertex_count}f', vertices_blob))

    # Translate to position
    x, y, z = position
    for i in range(0, len(vertices), 3):
        vertices[i] += x      # Translate X
        vertices[i+1] += y    # Translate Y
        vertices[i+2] += z    # Translate Z

    return vertices, faces_blob
```

---

## Object Type Classification

Objects are classified based on IFC class + dimensions:

### Doors
- **door_single:** Width < 1.0m (122 objects, 147mm-950mm)
- **door_double:** Width 1.0-2.0m (13 objects, 1050mm-1849mm)
- **door_large:** Width > 2.0m

### Windows
- **window_single:** Width < 1.2m (102 objects)
- **window_wide:** Width ≥ 1.2m (134 objects)
- **window_low:** Height < 1.0m

### Plumbing
- **toilet:** IfcSanitaryTerminal with "WC" in description
- **basin:** IfcSanitaryTerminal with "basin" or "sink"
- **urinal:** IfcSanitaryTerminal with "urinal"
- **shower:** IfcSanitaryTerminal with "shower"

### HVAC
- **diffuser_small:** IfcAirTerminal width < 0.5m (65 objects)
- **diffuser_large:** IfcAirTerminal width ≥ 0.5m (224 objects)

### Fire Protection
- **sprinkler_head:** IfcFireSuppressionTerminal height < 0.3m (899 objects)
- **fire_suppression:** Larger fire protection equipment

---

## Geometry Format

### Vertices
- Format: `BLOB` of Float32 values
- Layout: `[x0, y0, z0, x1, y1, z1, ..., xn, yn, zn]`
- Units: **Meters**
- Origin: Geometry centered at (0, 0, 0)

### Faces
- Format: `BLOB` of Int32 values
- Layout: `[v0, v1, v2, v3, v0, v1, v2, v3, ...]` (quads)
- Indexing: Zero-based vertex indices

### Normals
- Format: `BLOB` of Float32 values (optional)
- Layout: `[nx0, ny0, nz0, nx1, ny1, nz1, ...]`
- Note: May be NULL (computed on-the-fly if needed)

---

## Extraction Details

**Source Files:**
```
~/Documents/bonsai/8_IFC/
├── SJTII-ARC-A-TER1-00-R0-Clean.ifc      (85 MB)  ← Architectural
├── SJTII-ACMV-A-TER1-00-R0-Clean.ifc     (61 MB)  ← HVAC
├── SJTII-FP-A-TER1-00-R0-Clean.ifc       (23 MB)  ← Fire Protection
├── SJTII-ELEC-A-TER1-00-R0-Clean.ifc     (3.4 MB) ← Electrical
└── [other disciplines...]
```

**Extraction Script:** `extract_all_library_objects.py`

**Process:**
1. Read from `enhanced_federation.db` (Terminal 1 federated model)
2. Query `element_instances` + `base_geometries` + `elements_meta`
3. Center geometry at origin (remove GPS offsets)
4. Deduplicate by SHA256 hash
5. Calculate bounding box dimensions
6. Classify by IFC class + dimensions
7. Store in production library

**Quality:** LOD300-350 (professional consultant deliverables)

---

## Maintenance

### Adding New Objects

```bash
# Extract from new IFC file
python3 extract_additional_objects.py \
  --source new_project.ifc \
  --library production_library.db \
  --category Architectural
```

### Backup

```bash
# Monthly backup with timestamp
cp production_library.db \
   ~/Documents/bonsai/Backup/ProductionLibrary/production_library_$(date +%Y%m%d).db
```

### Version Control

- **DO NOT** commit frequent changes to the 123MB .db file
- Instead: Commit extraction scripts and metadata
- Store database in LFS (Large File Storage) or external assets

---

## Limitations

### Missing Object Types

The following common objects are **not included** (Terminal 1 didn't have them):

- ❌ IfcSanitaryTerminal (toilets, sinks) - See note below
- ❌ IfcOutlet (electrical outlets)
- ❌ IfcSwitchingDevice (light switches)
- ❌ Beds, lamp shades (residential furniture)

**Note on Toilets:** While Terminal 1 has plumbing, they may be classified under different IFC types. Check `IfcFlowTerminal` or generate parametric models as needed.

### Coverage Gaps

- **Residential:** Limited residential-specific furniture (beds, wardrobes)
- **Landscaping:** No plants, outdoor furniture
- **Site Elements:** No vehicles, signage
- **Structural:** No reinforcement details (rebar patterns)

### Recommended Supplements

1. Generate parametric models for missing common objects
2. Extract from other project IFC files
3. Download from bSDD (buildingSMART Data Dictionary)
4. Convert manufacturer Revit families (.rfa)

---

## Legal & Attribution

**Source:** Terminal 1 Airport Project IFC deliverables
**Extraction Date:** 2025-11-21
**Extracted By:** Automated script (extract_all_library_objects.py)

**Note:** These geometries are extracted from professional consultant deliverables. Ensure proper licensing for commercial use. Objects are used for parametric generation and reference only.

---

## Contact

For questions or additions to this library:
- Maintainer: [Your Organization]
- Repository: https://github.com/red1oon/IfcOpenShell.git
- Branch: feature/IFC4_DB

---

**Last Updated:** 2025-11-21
