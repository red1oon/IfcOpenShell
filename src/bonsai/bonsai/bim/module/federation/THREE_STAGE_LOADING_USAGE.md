# Three-Stage Inference-Based Loading - Usage Guide

## Quick Start (Blender Console)

```python
from bonsai.bim.module.federation.loader import load_federation

# Load federation with default settings (Stage 1 + 2)
db_path = "/path/to/federatedmodel_merged_v2.db"
objects = load_federation(db_path)

# Now you can work with the model!
# - Objects are accessible in Outliner
# - Organized by discipline collections
# - Ready for routing, clashing, MEP calculations
```

## Advanced Usage

### Option 1: Full Control with FederationLoader Class

```python
from bonsai.bim.module.federation.loader import FederationLoader

# Initialize loader
db_path = "/path/to/federatedmodel_merged_v2.db"
loader = FederationLoader(db_path)

# Stage 1: Instant wireframes (<2 min for 44K elements)
wireframes = loader.load_stage1()
# User sees spatial layout immediately

# Stage 2: Semantic shapes (8-30s target, currently ~2-5 min)
shapes = loader.load_stage2()
# User can now work! (routing, clashing, reporting)

# Stage 3: Optional detailed shapes (default OFF)
loader.enable_stage3(enabled=True)
# Adds flanges, dampers, fittings (visible elements only)
```

### Option 2: Skip Stage 1, Load Stage 2 Directly

```python
loader = FederationLoader(db_path)
shapes = loader.load_stage2()  # Skip wireframes, go straight to working viz
```

## What Each Stage Provides

### Stage 1: Wireframe Visualization
- **Time**: <2 minutes for 44K elements (current), target <1s with optimizations
- **Purpose**: Instant visual feedback while Stage 2 loads
- **Geometry**: Edge-only (8 vertices, 12 edges, 0 faces)
- **Use**: Spatial layout overview

### Stage 2: Semantic Shapes (WORKING VISUALIZATION) ⭐
- **Time**: Currently ~2-5 min for 44K elements, target 8-30s with optimizations
- **Purpose**: Working visualization - USER CAN WORK after this!
- **Geometry**: Procedural Bmesh (cylinders for pipes, boxes for ducts/beams)
- **Features**:
  - Accurate positioning from database transforms
  - Discipline-based materials (10 colors)
  - Semantic types inferred from IFC class
  - Organized by discipline collections
  - Metadata stored (accessible like IFC objects)

**After Stage 2 completes, user can:**
- Route conduits
- Detect clashes
- Perform MEP calculations
- Generate reports
- Navigate and inspect

### Stage 3: Detailed Shapes (OPTIONAL, DEFAULT OFF)
- **Time**: 0.5s for ~1K visible elements
- **Purpose**: Enhanced visual detail for presentations/closeups
- **Geometry**: Level 2 detail (flanges, dampers, fittings)
- **Features**:
  - Higher segment count (24 vs 12)
  - Frustum culling (visible only)
  - Background processing (non-blocking)
  - Toggle on/off anytime

**Use cases for Stage 3:**
- Client presentations
- Closeup inspection
- Export for rendering
- NOT needed for routine coordination work

## Database Requirements

Requires database schema v2.0.0 with:
- `elements_meta` table (GUID, discipline, IFC class)
- `elements_rtree` table (spatial index, bounding boxes)
- `element_transforms` table (position, rotation, scale)
- `site_context` table (optional, for georeferencing)

Create database using:
```bash
python Scripts/federation_preprocessor.py \
  --files file1.ifc file2.ifc ... \
  --disciplines ACMV ARC CW ELEC FP SP STR \
  --output federatedmodel_merged_v2.db
```

## Performance Characteristics

### Current Performance (Validated)
- Stage 1: 122s for 44,190 wireframes (2.78ms per element)
- Stage 2: Estimated 2-5 min for 44,190 semantic shapes
- Stage 3: 0.5s for ~1,000 visible elements

### Target Performance (With Optimizations)
- Stage 1: <1s (GPU instancing or deferred scene updates)
- Stage 2: 8-30s (deferred scene updates, batch operations)
- Stage 3: <1s (optimized Bmesh generation)

### Memory Usage
- Stage 1 wireframes: ~20 MB
- Stage 2 semantic shapes: ~108 MB
- Total: ~128 MB (vs ~400 MB for linking 7 IFC files)

## Architecture: "NO BLOB" Approach

**Philosophy**: "Freeze the DB and infer to the max"

- Complete IFC file independence (no IFC files needed at runtime!)
- All geometry computed procedurally from semantic metadata
- Database as "translator" between IFC structure and efficient visualization
- Standard materials (10 discipline colors, reused for all elements)
- Semantic type inference (pipes→cylinders, ducts→boxes, beams→boxes)

**Benefits:**
- 33x smaller database (14.93 MB vs ~500 MB with BLOBs)
- Faster loading (procedural generation faster than BLOB deserialization)
- Flexible visualization (can change detail level on-the-fly)
- Database-first workflow (no .blend files needed)

## Troubleshooting

### "Database schema version mismatch"
- Ensure database is v2.0.0 (run `SELECT value FROM schema_info WHERE key='version'`)
- Regenerate database with latest preprocessor if needed

### Stage 2 is slow (>5 minutes)
- Expected on first run (Blender imports, scene setup)
- Future optimizations will reduce to 8-30s target
- For now, Stage 2 completes once per session, then you can work

### Objects not appearing in viewport
- Check collections are visible (Outliner → eye icon)
- Verify federation collection is linked to scene
- Check if objects are behind camera

### Alt-Z wireframe mode not working
- Should work automatically with Stage 1 and 2 objects
- If not, check Blender viewport shading settings

## Next Steps

After loading federation:
1. **Navigate**: Use Blender viewport (mouse/keyboard)
2. **Select by discipline**: Use Outliner → Collections
3. **Filter**: Objects have metadata (federation_discipline, federation_ifc_class, etc.)
4. **Work**: Route conduits, detect clashes, inspect elements
5. **Toggle Stage 3**: Enable detailed shapes if needed for presentations

## Future Enhancements

Planned optimizations (from progress work analysis):
- Deferred scene updates (78x speedup for Stage 2)
- GPU instancing for equipment (53x memory savings)
- Standard material palette optimization (100x faster assignment)
- Progressive loading (visible elements first)
- Frustum culling (only render what's in view)

Target: 20-30 seconds total load time (28x faster than current 10-minute IFC loading)
