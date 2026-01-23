# 2D to 3D Extraction Pipeline - Systematic Process

## Overview

This pipeline converts 2D Malaysian architectural floor plans (PDF) into 3D Blender models using a specs-derived approach. All positions are derived from raw Vision API pixel data - no hardcoding.

## Rule 0: Deterministic Output

Same input = Same output. AI is used only for recognition (text detection), not estimation. All geometric calculations are deterministic.

## Pipeline Stages

### Stage 0: PDF to Vision API (One-time)

**Script:** `scripts/batch_extract.py`

**Input:** `INPUT/TB-LKTN HOUSE.pdf` (8 pages)

**Output:** `OUTPUT/page_X_vision.json` (one per page)

**API Cost:** 6 calls for 8 pages (pages 1,8 cached as blank/cover)

**Data captured:**
- Text content with pixel bounding boxes
- Used for room names, dimensions, labels

### Stage 1: Fill House Template

**Script:** `scripts/fill_house_template.py`

**Input:**
- `config/house_template.json` (empty structure)
- `OUTPUT/page_X_vision.json` (raw API data)

**Output:** `OUTPUT/house_template_filled.json`

**6 House Elements:**

1. **outside_drain** - Perimeter drain around building
   - offset_from_wall_mm: typically 600mm
   - Source: page 6 (roof plan shows overhang)

2. **outer_walls** - 4 external walls forming rectangle
   - corners_m: A1, E1, A5, E5 positions
   - thickness_mm: 150mm (standard)
   - height_mm: 3000mm (standard)
   - Source: calibration data

3. **main_door** - Primary entrance (D1)
   - position_m: derived from ANJUNG room pixel position
   - width_mm, height_mm: 900x2100 standard
   - Source: page 2 (floor plan)

4. **outer_windows** - Windows on external walls
   - Types: W1 (1800x1000), W2 (1200x1000), W3 (600x500)
   - Positions derived from room pixel positions
   - Wall assignment via ROOM_WALL_MAP
   - Source: page 2 room positions

5. **roof** - Hip roof with overhang
   - overhang_mm: 600mm
   - pitch_degrees: 25
   - eave_height_mm, ridge_height_mm
   - Source: page 6 (roof plan)

6. **porch** - Front entrance cover (ANJUNG)
   - position_m: derived from ANJUNG pixel position
   - width_mm, depth_mm, roof_height_mm
   - columns: 2 support columns
   - Source: page 2 ANJUNG position

**Key Mappings:**

```
ROOM_WALL_MAP = {
    "ANJUNG": "FRONT",
    "RUANG TAMU": "FRONT",
    "BILIK UTAMA": "LEFT",
    "BILIK 1": "RIGHT",
    "BILIK 2": "RIGHT",
    "BILIK MANDI": "LEFT",
    "DAPUR": "BACK",
    "RUANG BASAH": "BACK"
}

ROOM_WINDOW_TYPE = {
    "RUANG TAMU": "W1",
    "BILIK UTAMA": "W1",
    "BILIK 1": "W2",
    "BILIK 2": "W2",
    "BILIK MANDI": "W3",
    "DAPUR": "W2"
}
```

**Pixel to Meter Conversion:**

```
x_m = (px_x - origin_px) * scale_x
y_m = -(px_y - origin_py) * scale_y
```

### Stage 2: Staged Extraction

**Script:** `staged_extraction_v2.py`

**Input:** `OUTPUT/house_template_filled.json`

**Output:** `OUTPUT/staged_extraction_v2_FINAL.json`

**Generates placements array:**
- 4 drain segments (FRONT, BACK, LEFT, RIGHT)
- 4 walls (EXT_WALL_FRONT, BACK, LEFT, RIGHT)
- 1 door (D1_main)
- N windows (W1_roomname, W2_roomname, etc)
- 1 roof (ROOF_MAIN)
- 1 porch (PORCH_FRONT) with columns

### Stage 3: Blender Proof

**Script:** `scripts/blender_staged_import.py`

**Input:** `OUTPUT/staged_extraction_v2_FINAL.json`

**Output:** `.blend` file with primitive geometry

**Collections created:**
- Drains (gray cubes at Z=-0.075)
- Walls (beige cubes)
- Doors (brown cubes)
- Windows (blue cubes)
- Roof (wireframe hip outline)
- Slabs (floor slab)

**Usage:**
```
blender --background --python blender_staged_import.py -- staged_extraction_v2_FINAL.json output.blend
```

Or via start-blender.bat:
```
start-blender.bat scripts/blender_staged_import.py OUTPUT/staged_extraction_v2_FINAL.json WORK_DIR/staged_proof_v2.blend
```

## File Structure

```
2dto3d/
  config/
    house_template.json       # Empty template structure
    calibration.json          # Pixel-to-meter calibration
  INPUT/
    TB-LKTN HOUSE.pdf         # Source floor plan
  OUTPUT/
    page_X_vision.json        # Raw Vision API output
    house_template_filled.json # Filled template
    staged_extraction_v2_FINAL.json # Placements for Blender
  scripts/
    batch_extract.py          # PDF to Vision API
    fill_house_template.py    # Fill template from raw data
    blender_staged_import.py  # Import to Blender
  staged_extraction_v2.py     # Generate placements from template
```

## Token/Cost Estimation

**Vision API:** 6 calls per PDF (once, cached forever)
**Claude AI:** Template filling requires human review for:
- Room-to-wall assignment (one-time mapping)
- Window type assignment (one-time mapping)
- Dimension extraction from text

Once mappings are established, pipeline is fully automated.

## Verification

1. Open .blend file in Blender
2. Check positions match floor plan:
   - Main door at correct X position (should align with ANJUNG)
   - Windows on correct walls
   - Porch in front of door
3. Check dimensions match specs:
   - Building 11.2m x 8.5m
   - Walls 3m high, 150mm thick
   - Drain offset 600mm from walls

## Future: LOD300 Objects

Replace primitives with library objects:
- door_single_900_lod300
- window_aluminum_3panel_1800x1000
- window_aluminum_2panel_1200x1000
- etc.

Object types are already tracked in placements JSON (object_type field).
