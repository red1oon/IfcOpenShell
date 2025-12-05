# RIVER - Blosm to GI Federation Database

Geographic Information System (GIS) data imported via Blosm addon and converted to GI federation database format.

## 📁 Folder Structure

```
RIVER/
├── README.md                       # This file
├── prompt.txt                      # Current session context
│
├── 🎯 ACTIVE FILES (main workflow)
│   ├── klang_buildings_blosm.blend # Source: Blosm import (3,325 verts river)
│   ├── blosm_to_gi.py              # Converter: Blend → GI database
│   ├── coastal_oasis_gi.db         # Output: GI federation database (LATEST)
│   └── library.db                  # LOD300 component library (NEW!)
│
├── 📦 LIBRARY SYSTEM (NEW!)
│   ├── library.db                  # Component library database
│   ├── create_library_db.py        # Create library schema
│   ├── add_model_to_library.py     # Import models to library
│   ├── add_excavator_to_db.py      # Direct DB insertion (bypasses IFC)
│   ├── LIBRARY_SETUP.md            # Complete library workflow
│   ├── FREE_3D_MODELS_GUIDE.md     # Download sources
│   └── models/                     # Downloaded model .blend files
│
├── 📚 documentation/               # All docs, research prompts, progress logs
├── 🧪 test_scripts/                # Test/utility scripts (diagnostics, imports)
├── 🗄️  databases_old/              # Previous database versions (archived)
├── 🎨 blend_files/                 # Old/test blend files (archived)
├── 📦 archive/                     # Failed attempts, deprecated code
├── 🌐 resource/                    # Blosm addon assets
├── 💬 Opus/                        # Opus research outputs
└── 🗂️  database/                   # Database utilities (if any)
```

## 🚀 Main Workflow

**1. Import from OpenStreetMap via Blosm:**
```bash
# Open Blender → Blosm addon → Import OSM
# Output: klang_buildings_blosm.blend
```

**2. Convert to GI Database:**
```bash
~/blender-4.5.0/blender --background klang_buildings_blosm.blend \
  --python blosm_to_gi.py
# Output: coastal_oasis_gi.db
```

**3. Load in Bonsai Federation:**
```python
# Use blend_cache.py to load GI database elements
# Visualize in Blender via Bonsai Federation module
```

## 📊 Current Status

### ✅ WORKING
- **Geometry extraction:** Fixed! Now preserves Blosm's detailed mesh (3,325→6,303 verts with boundary duplication)
- **River segmentation:** 356 segments @ 100m intervals, 4-132 verts each (avg 18)
- **Database export:** 0.56 MB with full triangulated geometry
- **Construction equipment:** Direct database insertion with `add_excavator_to_db.py`
- **Complete scene:** 385 elements (384 GEO + 1 CW excavator) in `river_blosm_gi.db`

### 🔨 IN PROGRESS
- Buildings import (None_buildings object in blend file)
- Terrain support (optional)

### 💡 DIRECT DATABASE INSERTION
**Why bypass IFC?** For construction equipment without IFC source files, we can insert directly into the GI database:
- **Script:** `add_excavator_to_db.py`
- **Approach:** Creates database records (elements_meta, element_transforms, spatial index) without intermediate IFC
- **Use case:** LOD300 equipment from 3D model libraries (excavators, cranes, etc.)
- **Advantage:** Faster workflow, works with any mesh geometry
- **Visualization:** Use `blend_cache.py` to load from database and render in Blender
- **Example:** Caterpillar 336 Excavator added at (21.96, 6.54, 0.0) with CW discipline

### 📈 Results
| Metric | Before Fix | After Fix |
|--------|-----------|----------|
| Verts/segment | 5-6 | 4-132 (avg 18) |
| Total verts | Lost | 6,303 preserved |
| Total faces | Lost | 5,437 triangles |
| Detail quality | Blocky | Smooth, curved |

## 🔑 Key Technical Details

### Blosm River Mesh Structure
- **2 huge N-gons:** 1,467 and 1,862 vertices each
- **Triangulation:** Creates 3,325 triangular faces
- **Flat geometry:** Z-axis = 0.2m (2D water surface)

### Converter Fixes Applied
1. **Extraction:** Use `bm.from_mesh()` not `bm.from_object()` (latter fails on Blosm meshes)
2. **Segmentation:** Include faces that INTERSECT segments (not just fully contained)
3. **Boundary handling:** Duplicate vertices at segment edges for independent loading

## 📖 Documentation

See `documentation/` folder:
- `progress.md` - Complete development log
- `PROMPT_FOR_OPUS_BLOSM_GEOMETRY_EXPORT.md` - Research findings
- `PROJECT_BACKGROUND.md` - Coastal Oasis context

## 🧪 Test Scripts

See `test_scripts/` folder:
- `check_blosm_detail.py` - Diagnostic: base vs evaluated mesh
- `test_extract.py` - Test geometry extraction
- `enhance_geometry.py` - Procedural river generation (fallback)

## 🗄️ Archived Files

- `databases_old/` - Previous database versions (poc, gis, realistic_river)
- `blend_files/` - Test/intermediate blend files
- `archive/` - Failed attempts, deprecated approaches

## 🎯 Next Steps

1. Add buildings extraction to `blosm_to_gi.py`
2. Create loader script for visualization testing
3. Optionally: Add terrain support
4. Integration: Test with Bonsai Federation Full Load

---

**Last updated:** 2025-12-05
**Database version:** river_blosm_gi.db (444 KB, 385 elements: 384 GEO + 1 CW)
**Latest workflow:** BLOSM OSM → IFC → GI DB + Direct equipment insertion
