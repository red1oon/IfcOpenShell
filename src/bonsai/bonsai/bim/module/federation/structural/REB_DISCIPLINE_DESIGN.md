# REB Discipline Implementation Design

## Overview
Add reinforcement bars as a separate "REB" discipline in the federation database, enabling:
- Discipline-based filtering and visualization
- Clash detection: "ELEC vs REB", "ACMV vs REB"
- Rebar-aware conduit routing
- Layer-based coordination (toggle REB on/off independently)

---

## Database Schema Changes

### 1. Add REB Elements to `elements_meta`

**Strategy:** Create **synthetic REB elements** representing bar groups, not individual bars.

**Grouping approach:**
- One REB element per **bar type per parent element**
- Example: Slab with GUID `xxx` gets:
  - `REB-xxx-MAIN` → All main bars as one element
  - `REB-xxx-DIST` → All distribution bars as one element

**Why group?**
- Scale: 39,975 individual bars → ~3,000-5,000 bar groups
- Performance: Manageable element count
- Visualization: Show bar groups as clusters, not individual lines

### 2. REB Element Schema

```sql
-- Insert into elements_meta
INSERT INTO elements_meta (
    guid,                    -- REB-{parent_guid}-{bar_type}
    discipline,              -- 'REB'
    ifc_class,              -- 'IfcReinforcingBar'
    element_name,           -- 'Y12@200 Main Bars (120 bars, 285kg)'
    element_type,           -- 'MAIN' | 'DISTRIBUTION' | 'BOTTOM' | 'TOP' | 'STIRRUP' | 'LONGITUDINAL'
    element_description,    -- Bar specs: diameter, spacing, count
    ifc_file_id             -- Same as parent element
) VALUES (...);
```

### 3. Geometry Representation

**Option A: Simplified Bounding Box (RECOMMENDED for Phase 1)**
```sql
-- Store in elements_rtree
INSERT INTO elements_rtree (
    id,                     -- Links to elements_meta.id
    minX, maxX,            -- Parent element bbox (slightly inset for cover)
    minY, maxY,
    minZ, maxZ
);
```

**Rationale:**
- Fast rendering (bbox is lightweight)
- Clash detection works (R-tree queries)
- Shows "rebar zone" without individual bar geometry

**Option B: Representative Lines (Phase 2)**
```sql
-- Future: Store actual bar positions as line segments
CREATE TABLE rebar_geometry (
    rebar_guid TEXT,
    bar_index INTEGER,      -- Which bar in the group
    start_x REAL, start_y REAL, start_z REAL,
    end_x REAL, end_y REAL, end_z REAL
);
```

### 4. Linking Tables

**Map REB discipline elements to detailed bar data:**
```sql
CREATE TABLE rebar_discipline_map (
    rebar_guid TEXT PRIMARY KEY,           -- REB-xxx-MAIN
    parent_str_guid TEXT NOT NULL,         -- Original concrete element
    bar_type TEXT NOT NULL,                -- MAIN, DISTRIBUTION, etc.
    reinforcement_summary_guid TEXT,       -- Link to reinforcement_summary table
    bar_count INTEGER,
    total_weight_kg REAL,
    diameter_mm INTEGER,
    spacing_mm INTEGER,
    FOREIGN KEY (parent_str_guid) REFERENCES elements_meta(guid)
);
```

---

## Implementation Steps

### Phase 1: Database Population (Immediate)

**File:** `structural/rebar_to_discipline.py`

```python
def save_rebar_as_discipline(database_path, rebar_results):
    """
    Convert rebar calculation results to REB discipline elements

    Args:
        rebar_results: Dict from RebarGenerator.generate_all_rebar()
                      {'slabs': [...], 'beams': [...], 'columns': [...]}
    """
    conn = sqlite3.connect(database_path)

    # Create mapping table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rebar_discipline_map (
            rebar_guid TEXT PRIMARY KEY,
            parent_str_guid TEXT NOT NULL,
            bar_type TEXT NOT NULL,
            bar_count INTEGER,
            total_weight_kg REAL,
            diameter_mm INTEGER,
            spacing_mm INTEGER
        )
    """)

    # Process slabs
    for slab in rebar_results['slabs']:
        # Main bars
        create_reb_element(conn, slab, 'MAIN', slab['main_bars'])

        # Distribution bars
        create_reb_element(conn, slab, 'DISTRIBUTION', slab['distribution_bars'])

    # Process beams
    for beam in rebar_results['beams']:
        create_reb_element(conn, beam, 'BOTTOM', beam['bottom_bars'])
        create_reb_element(conn, beam, 'TOP', beam['top_bars'])
        create_reb_element(conn, beam, 'STIRRUP', beam['stirrups'])

    # Process columns
    for column in rebar_results['columns']:
        create_reb_element(conn, column, 'LONGITUDINAL', column['longitudinal_bars'])
        create_reb_element(conn, column, 'TIES', column['ties'])

    conn.commit()
    conn.close()


def create_reb_element(conn, parent_element, bar_type, bar_spec):
    """Create one REB discipline element for a bar group"""

    parent_guid = parent_element['element_guid']
    rebar_guid = f"REB-{parent_guid}-{bar_type}"

    # Get parent element info
    parent = conn.execute("""
        SELECT id, ifc_file_id, element_name
        FROM elements_meta WHERE guid = ?
    """, (parent_guid,)).fetchone()

    if not parent:
        return  # Parent not found

    parent_id, file_id, parent_name = parent

    # Create descriptive name
    element_name = (
        f"Y{bar_spec['diameter']} "
        f"{'@' + str(bar_spec.get('spacing', 0)) + 'mm' if 'spacing' in bar_spec else ''} "
        f"{bar_type.title()} Bars "
        f"({bar_spec['count']} bars)"
    )

    # Insert into elements_meta
    cursor = conn.execute("""
        INSERT INTO elements_meta (
            guid, discipline, ifc_class, element_name, element_type, ifc_file_id
        ) VALUES (?, 'REB', 'IfcReinforcingBar', ?, ?, ?)
    """, (rebar_guid, element_name, bar_type, file_id))

    reb_id = cursor.lastrowid

    # Get parent bbox and inset by cover
    parent_bbox = conn.execute("""
        SELECT minX, maxX, minY, maxY, minZ, maxZ
        FROM elements_rtree WHERE id = ?
    """, (parent_id,)).fetchone()

    if parent_bbox:
        # Inset by cover (convert mm to meters)
        cover_m = parent_element.get('cover_mm', 40) / 1000.0
        minX, maxX, minY, maxY, minZ, maxZ = parent_bbox

        # Insert into rtree (rebar zone bbox)
        conn.execute("""
            INSERT INTO elements_rtree (
                id, minX, maxX, minY, maxY, minZ, maxZ
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            reb_id,
            minX + cover_m,
            maxX - cover_m,
            minY + cover_m,
            maxY - cover_m,
            minZ + cover_m,
            maxZ - cover_m
        ))

    # Store mapping
    weight = bar_spec.get('weight_kg', 0) or (
        bar_spec.get('count', 0) * bar_spec.get('length_total_m', 0) / bar_spec.get('count', 1) *
        get_bar_weight_per_m(bar_spec['diameter'])
    )

    conn.execute("""
        INSERT INTO rebar_discipline_map (
            rebar_guid, parent_str_guid, bar_type,
            bar_count, total_weight_kg, diameter_mm, spacing_mm
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        rebar_guid,
        parent_guid,
        bar_type,
        bar_spec['count'],
        weight,
        bar_spec['diameter'],
        bar_spec.get('spacing', 0)
    ))


def get_bar_weight_per_m(diameter_mm):
    """Get bar weight in kg/m from diameter"""
    # Steel density: 7850 kg/m³
    # Weight = π * (d/2)² * length * density
    radius_m = (diameter_mm / 1000.0) / 2
    area_m2 = 3.14159 * radius_m * radius_m
    return area_m2 * 7850
```

### Phase 2: Operator Integration

**Update:** `operator.py` - BIM_OT_generate_rebar_structural

```python
# After generate_all_rebar()
results = generator.generate_all_rebar()

# EXISTING: Save to detail tables
generator.save_to_database(results)

# NEW: Save as REB discipline
from bonsai.bim.module.federation.structural.rebar_to_discipline import save_rebar_as_discipline
save_rebar_as_discipline(db_path, results)

logger.info(f"✅ Created REB discipline elements in database")
```

### Phase 3: Visualization

**Existing federation viewer should work automatically!**

REB elements will appear in:
- Discipline filter dropdown
- Element count statistics
- 3D viewport (as bboxes initially)
- Clash detection discipline selector

**Color coding:**
```python
# Add to color scheme
REB_COLOR = (0.96, 0.49, 0.22, 1.0)  # Orange/rust color
```

### Phase 4: Clash Detection Integration

**No code changes needed!** Existing clash detector will automatically support:
```python
# These work immediately:
"ELEC vs REB"
"ACMV vs REB"
"FP vs REB"
```

---

## Testing Plan

### 1. Database Verification
```sql
-- Check REB elements created
SELECT COUNT(*) FROM elements_meta WHERE discipline = 'REB';
-- Expected: ~3,000-5,000 elements

-- Check discipline distribution
SELECT discipline, COUNT(*) FROM elements_meta GROUP BY discipline;

-- Sample REB elements
SELECT guid, element_name, element_type
FROM elements_meta
WHERE discipline = 'REB'
LIMIT 10;

-- Check mapping
SELECT * FROM rebar_discipline_map LIMIT 5;
```

### 2. Visualization Test
- Load database in Blender
- Filter by discipline: Select "REB" only
- Verify orange/rust colored bboxes appear
- Toggle REB on/off

### 3. Clash Detection Test
- Run clash test: "ELEC vs REB"
- Verify clashes detected
- Check clash report lists REB elements correctly

---

## Performance Considerations

**Element count impact:**
- Before: 49,059 elements
- After: ~52,000-54,000 elements (+6-10%)
- Impact: Minimal (within acceptable range)

**Memory footprint:**
- Bbox geometry: ~100 bytes per element
- Total added: ~500KB (negligible)

**Rendering speed:**
- Bboxes are fast to render
- No mesh tessellation needed
- Expected: <5% performance impact

---

## Future Enhancements (Phase 2+)

### 1. Detailed Bar Geometry
Replace bboxes with actual bar line segments:
```python
# Calculate actual bar positions
for i in range(bar_count):
    position = start + (spacing * i)
    create_line_segment(position, direction, length)
```

### 2. Bar Scheduling Integration
```python
# Export bar schedule per bar group
def export_bar_schedule(rebar_guid):
    """Generate BS8666 bar bending schedule"""
```

### 3. Rebar Density Heat Map
```python
def generate_rebar_density_grid(zone_bbox):
    """Return 3D grid showing bars/m³ for routing"""
```

### 4. Intelligent Clash Resolution
```python
def resolve_elec_reb_clash(clash):
    if clash.reb_element.bar_type == 'MAIN':
        return "Cannot cut main bars - relocate conduit"
    else:
        return "Local bar adjustment possible"
```

---

## Migration Path

**For existing databases:**
```python
# Run migration script
python migrate_add_reb_discipline.py /path/to/database.db
```

**Script will:**
1. Check if rebar data exists in reinforcement_bars table
2. Convert to REB discipline elements
3. Create mapping table
4. Update statistics
5. Preserve existing data

---

## Success Metrics

- ✅ REB discipline appears in viewer
- ✅ ~3,000-5,000 REB elements created
- ✅ Clash detection "ELEC vs REB" works
- ✅ Toggle REB visibility works
- ✅ No performance degradation
- ✅ Existing features still work

---

## Timeline

- **Day 1 (Now):** Implement `rebar_to_discipline.py` module
- **Day 1 (1 hour):** Integrate into operator
- **Day 1 (30 min):** Test with sample database
- **Day 1 (15 min):** Verify visualization
- **Day 1 (15 min):** Test clash detection

**Total: ~2 hours to working prototype!**

---

**Ready to implement?** This will be a game-changer for BIM coordination! 🚀
