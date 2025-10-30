# Federation Sample Testing Suite

This directory contains scripts for validating IFC federation sample extraction and rendering.

## Overview

The sample testing suite provides a **5-stage pipeline** for testing IFC federation workflows:

1. **Recon Stage** - Scan storey density to find optimal sample locations
2. **Extraction Stage** - Extract geometry and metadata to database
3. **Loading Stage** - Load federation into Blender scene
4. **Camera/Viewport Stage** - Position camera for visualization
5. **Rendering Stage** - Generate validation snapshot

## Files

- `scan_storey_density.py` - Stage 1: Analyze IFC storeys to find multi-discipline areas
- `test_sample_with_snapshot.py` - Stages 3-5: Load, frame, and render validation
- `sample_config.json` - Configuration for sample extraction parameters

## Workflow

### Step 1: Recon - Find Optimal Storey

```bash
python scan_storey_density.py
```

**Output:** Identifies storey with highest multi-discipline density (e.g., "Aras Tanah" with 6 disciplines)

### Step 2: Configure Sample Extraction

Edit `sample_config.json`:
```json
{
  "storey_filter": "Aras Tanah",
  "max_elements": 800,
  "output_db": "sample_extracted.db"
}
```

### Step 3: Extract Sample

```bash
PYTHONPATH=/path/to/IfcOpenShell/src \
  python3 ../../scripts/extract_tessellation_to_db_v2.py \
  --sample \
  --output /path/to/sample_extracted.db
```

**Output:** Database with extracted elements (e.g., 2627 elements, 53MB)

### Step 4: Test Sample with Snapshot

```bash
blender --background --python test_sample_with_snapshot.py
```

**Output:**
- Loads federation (2627 mesh objects)
- Positions camera with proper orientation
- Renders PNG snapshot for validation

## Pipeline Validation

The pipeline is considered **successful** when:

✅ Stage 1: Recon finds storey with 3+ disciplines
✅ Stage 2: Extraction completes without errors
✅ Stage 3: All elements load as mesh objects
✅ Stage 4: Camera properly frames geometry
✅ Stage 5: Rendered PNG shows visible, recognizable geometry

## Key Features

### Recon Stage
- Scans IfcBuildingStorey relationships (metadata only, no geometry)
- Ranks storeys by multi-discipline density
- Fast: ~5 seconds for full project scan

### Extraction Stage
- Storey-based filtering (`STOREY_FILTER` mode)
- Parallel geometry processing
- Full metadata preservation (materials, properties, spatial structure)

### Loading Stage
- GPU-based instancing (1.7× efficiency)
- Parallel mesh creation (8 workers)
- Fast: ~2.5 seconds for 2627 elements

### Rendering Stage
- **Fixed camera orientation** (uses `-Z` axis for camera view)
- Automatic scene framing (0.8× distance multiplier)
- Cycles rendering with denoising

## Known Issues & Fixes

### Issue: Blank PNG Render
**Symptom:** Render completes but PNG is gray/blank
**Cause:** Camera orientation using `'Z'` instead of `'-Z'` in `to_track_quat()`
**Fix:** Line 95 in test_sample_with_snapshot.py:
```python
# CORRECT:
camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()

# WRONG:
camera.rotation_euler = direction.to_track_quat('Z', 'Y').to_euler()
```

## Future Development

This testing suite will be integrated into the Bonsai UI to allow users to:
- Dynamically select sample regions
- Preview federation quality before full load
- Validate multi-discipline coordination
- Generate proof-of-concept renders

## Integration with UI

The sample workflow is designed to eventually become part of the federation UI:
1. User selects project
2. UI runs recon (shows storey options)
3. User picks storey or custom region
4. Extraction runs with progress bar
5. Preview render shown in viewport
6. User confirms or adjusts before full federation load
