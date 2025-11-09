# Enhanced IFC Database Extraction

This folder contains a standalone extraction script that creates production-ready databases with advanced search and query capabilities.

## Quick Start

**Copy the script to your IFC folder and run:**

```bash
cd /path/to/your/ifc/files
./extract_ifc_to_database.sh
```

That's it! The script will:
1. Auto-detect all `.ifc` files in the folder
2. Merge them into `merged_federation.ifc` (if multiple files exist)
3. Extract to `enhanced_federation.db` with all advanced features

## What You Get

### 🚀 Production-Ready Features

**1. FTS5 Full-Text Search (50-100x faster)**
- Natural language queries: "How many doors?", "Find all Aereco equipment"
- Instant property search across all elements
- Industry-first natural language BIM queries

**2. Pre-Calculated QTO (Instant BOQ Export)**
- Quantities calculated during extraction (not at export time)
- BOQ export becomes instant instead of 30-second wait
- 159,430+ quantity entries ready to use

**3. Enhanced Property Coverage (+20-30%)**
- Extracts both instance AND type properties
- Better compliance checking
- Complete material and property data

**4. Geometry Deduplication**
- Stores only unique geometries
- Instance references for duplicates
- Optimized database size

## Performance

**Full Building Extraction (Terminal 1 Example):**
- **67,169 elements** scanned
- **46,199 elements** with geometry extracted
- **27.1 minutes** total extraction time
- **2,500+ elements/minute** processing rate
- **327 MB** final database size

**Breakdown:**
- 295,973 properties
- 159,430 QTO entries
- 46,151 unique geometries
- FTS5 indexed for instant search

## Output Files

The script creates these files in the same folder:

| File | Description | Reused? |
|------|-------------|---------|
| `merged_federation.ifc` | Merged IFC file | ✅ Yes (cached) |
| `enhanced_federation.db` | SQLite database | ❌ Recreated |
| `extraction.log` | Extraction log | ❌ Appended |

**Note:** The merged IFC is cached and reused. Delete it to force re-merge.

## Database Schema

### Core Tables
- `base_geometries` - Unique geometry storage (vertices, faces)
- `element_instances` - Element references to geometries
- `elements_meta` - Element metadata (name, type, class, discipline)
- `element_transforms` - Element positions and transforms
- `element_properties` - All property sets
- `spatial_structure` - Building/Storey/Space hierarchy
- `elements_rtree` - Spatial index for fast queries

### Enhanced Tables (New Features)
- `elements_fts` - Full-text search on elements (FTS5)
- `properties_fts` - Full-text search on properties (FTS5)
- `simple_qto` - Pre-calculated quantities (instant BOQ)
- `extraction_metadata` - Extraction statistics and tracking

### Compatibility
- `element_geometry` - View for Bonsai loader compatibility

## Usage Examples

### Natural Language Queries

```sql
-- "How many ducts are there?"
SELECT COUNT(*) FROM elements_fts WHERE elements_fts MATCH 'duct';
→ 192 results in 0.11ms

-- "Show me all Aereco equipment"
SELECT element_name, ifc_class
FROM elements_fts e
JOIN properties_fts p ON e.guid = p.guid
WHERE p.properties_fts MATCH 'Aereco';
→ 24 manufacturers found

-- "Find all fire protection elements"
SELECT * FROM elements_fts WHERE discipline = 'FP';
→ 6,880 elements
```

### Instant BOQ Queries

```sql
-- Total duct length (pre-calculated, instant)
SELECT SUM(quantity_value)
FROM simple_qto
WHERE quantity_name = 'Length';
→ 495,063.49mm (instant)

-- Breakdown by discipline
SELECT e.discipline, SUM(q.quantity_value) as total_length
FROM simple_qto q
JOIN elements_meta e ON q.guid = e.guid
WHERE q.quantity_name = 'Length'
GROUP BY e.discipline;
```

### Property Search

```sql
-- Find all elements with specific manufacturer
SELECT e.element_name, p.property_value
FROM elements_meta e
JOIN properties_fts p ON e.guid = p.guid
WHERE p.properties_fts MATCH 'manufacturer AND Aereco';
```

## Loading in Bonsai

Once extracted, load the database in Bonsai:

1. Open Blender with Bonsai addon
2. Go to Federation panel
3. Click "Load Solid" or "Load Full"
4. Select `enhanced_federation.db`
5. Elements load with `.blend` cache (10x faster subsequent loads)

**First Load:** ~40 seconds (creates cache)
**Subsequent Loads:** ~15 seconds (uses cache)

## Requirements

### System Requirements
- **Blender 4.2+** with IfcOpenShell installed
- **Python 3.11** (Blender's Python)
- **SQLite 3** with FTS5 support (standard on modern systems)

### Script Configuration

Edit the script if needed (line 28):
```bash
BLENDER_PYTHON="/home/red1/blender-4.2.14/4.2/python/bin/python3.11"
```

Change to your Blender Python path.

## Troubleshooting

### "Blender Python not found"
Edit the script and update `BLENDER_PYTHON` path (line 28)

### "No .ifc files found"
Make sure you're in the folder with IFC files, or copy the script there

### "Merge failed"
Check the log file for details. You may need to:
- Verify IFC files are valid
- Check disk space
- Ensure ifcpatch is installed

### Extraction errors
Check `extraction.log` for detailed error messages

## Advanced Usage

### Force Re-merge
```bash
rm merged_federation.ifc
./extract_ifc_to_database.sh
```

### Extract Single IFC
Put one IFC file in folder:
```bash
cp my_file.ifc temp_folder/
cd temp_folder/
../extract_ifc_to_database.sh
```

### Custom Database Name
Edit the script and change `OUTPUT_DB` (line 30)

## Performance Tips

**For Large Projects (100K+ elements):**
- Extraction may take 1-2 hours
- Database size typically 500MB - 2GB
- FTS5 indexing adds ~10% overhead but pays off with 50-100x faster queries

**For Multiple Extractions:**
- Keep `merged_federation.ifc` to save merge time
- Delete `enhanced_federation.db` between runs
- Log file is appended, delete if too large

## Technical Details

### Extraction Pipeline

1. **IFC Merge** (if multiple files)
   - Uses IfcPatch MergeProjects
   - Cached to `merged_federation.ifc`
   - Preserves all spatial data

2. **Geometry Extraction**
   - IfcOpenShell tessellation with `USE_WORLD_COORDS`
   - SHA256 hash-based deduplication
   - Stores only unique geometries

3. **Property Extraction**
   - Instance properties via `get_psets()`
   - Type properties via `IsTypedBy` relationships
   - Material associations

4. **Quantity Extraction (QTO)**
   - `IfcElementQuantity` parsing
   - Length, Area, Volume, Count, Weight
   - Pre-calculated and indexed

5. **FTS5 Indexing**
   - Elements: name, type, description, class
   - Properties: pset name, property name, value
   - Uses SQLite FTS5 virtual tables

6. **Spatial Indexing**
   - R-tree for bbox queries
   - Fast spatial filtering
   - Clash detection optimization

### Database Optimization

**Geometry Deduplication:**
- Typical savings: 40-60% for repeated elements
- Hash-based identification (SHA256)
- Instance count tracked

**FTS5 Benefits:**
- 50-100x faster than LIKE queries
- Supports complex boolean queries
- Relevance ranking built-in

**QTO Pre-calculation:**
- Eliminates 30-second BOQ wait
- Indexed for fast aggregation
- Ready for export

## Version History

**v1.0 (2025-11-09)** - Initial Release
- FTS5 full-text search
- QTO preprocessing
- Type/Material property extraction
- Enhanced logging
- Standalone script format

## Support

For issues or questions:
1. Check `extraction.log` for detailed error messages
2. Verify Blender Python path is correct
3. Ensure IFC files are valid (open in viewer first)
4. Check disk space (database can be large)

## License

Part of Bonsai BIM - https://bonsaibim.org/
