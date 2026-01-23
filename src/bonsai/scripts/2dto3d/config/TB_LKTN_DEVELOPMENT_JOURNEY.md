# TB-LKTN 2D-to-3D Development Journey

## Project Goal
Convert 2D PDF floor plans (TB-LKTN Malaysian affordable housing design) into 3D Blender/IFC models using an AI-assisted pipeline.

## The Pipeline Strategy

### Phase 1: PDF Extraction
- Use Google Vision API to extract text, dimensions, and spatial relationships from PDF floor plans
- Vision API returns raw OCR data with bounding boxes and text content

### Phase 2: Preprocessing (AI Interpretation)
- Feed Vision API output to an LLM (Opus) with a specialized prompt (VISION_PREPROCESSOR_PROMPT.md)
- LLM interprets the architectural drawing semantics:
  - Grid system (columns A-E, rows 1-5)
  - Room labels and boundaries
  - Wall positions and types (exterior vs interior)
  - Door/window placements with swing directions
  - Dimensional annotations

### Phase 3: Structured JSON Output
- LLM produces structured JSON with:
  - Grid calibration (column/row positions in meters)
  - Wall placements (start_point, end_point, thickness, height)
  - Opening placements (doors, windows with host_wall references)
  - Roof geometry
  - Room/space definitions

### Phase 4: Blender Import
- Python script (blender_staged_import.py) reads the JSON
- Creates 3D geometry in Blender
- Outputs .blend file for manual review

## The TB-LKTN Floor Plan

### Building Overview
- Malaysian affordable housing single-story design
- Approximately 11.2m x 8.5m overall lot
- Hip roof with front porch

### Grid System
```
Columns (X-axis):
  A = 0mm (left edge)
  B = 1300mm
  C = 4400mm
  D = 8100mm
  E = 11200mm (right edge)

Rows (Y-axis):
  Row 1 = Front (drain line, exterior to building)
  Row 2 = Front wall line
  Row 3 = Interior division
  Row 4 = Kitchen/wet area division
  Row 5 = Back wall line
```

### Room Layout (approximate)
- BILIK UTAMA (Master Bedroom) - left side
- BILIK MANDI (Bathroom) - left rear corner
- DAPUR (Kitchen) - center rear
- RUANG MAKAN (Dining) - center
- RUANG TAMU (Living) - center front
- BILIK 2, BILIK 3 (Bedrooms) - right side
- ANJUNG (Porch) - front center

## Critical Discovery: Coordinate System Conflicts

### The Core Problem
Multiple JSON interpretations existed with INCOMPATIBLE coordinate systems:

**Interpretation A (blender_staged_import convention):**
- Origin at back-left corner of building
- Y = 0 at back wall
- Y becomes negative toward front (Y = -8.5 at front)
- Building envelope: x=0 to x=11.2

**Interpretation B (Opus preprocessing):**
- Origin at front-left corner
- Y = 0 at front (row 1)
- Y becomes positive toward back (Y = 8500mm at row 5)
- Building envelope may start at column B (x=1300), not column A

### Why This Matters
- These aren't just different origins - they imply different building boundaries
- Converting between them requires knowing which interpretation matches the actual PDF
- Without resolving this, every "fix" just transforms the error

### The Building Envelope Question
**Unresolved:** Does the actual building (walls) span:
- Column A to E (11.2m total)? or
- Column B to E (9.9m, with column A being exterior/drain setback)?

The original PDF is the ground truth, but different AI interpretations gave different answers.

## Pattern of Failure (Lessons Learned)

### What Went Wrong
1. **Multiple "sources of truth"** - Different JSON files represented different interpretations
2. **Incremental patching** - Each fix addressed one symptom but broke something else
3. **No baseline verification** - Never confirmed which JSON actually matched the PDF
4. **Coordinate transforms without understanding** - Applied math without knowing if the input was correct

### The Vicious Cycle
```
Try JSON file A -> Generate blend -> "Doors rotated wrong"
  -> Try JSON file B -> Generate blend -> "Interior walls transposed"
    -> Convert coordinates -> Generate blend -> "Terrible"
      -> Try different conversion -> Generate blend -> "Nope"
        -> (User stops the cycle)
```

### What Should Have Happened
1. Pick ONE authoritative source (the original PDF)
2. Create ONE JSON interpretation
3. Verify that JSON against the PDF visually BEFORE generating 3D
4. Only then run the Blender import
5. If errors, trace back to the JSON interpretation, not create new JSONs

## The Blender Import Script

### Location
`C:\Dev\bonsai-extensions\IfcOpenShell\src\bonsai\scripts\2dto3d\scripts\blender_staged_import.py`

### Expected JSON Format
```json
{
  "metadata": {
    "building_width_m": 11.2,
    "building_depth_m": 8.5
  },
  "placements": [
    {
      "name": "WALL_NAME",
      "type": "wall",
      "start_point": [x, y],
      "end_point": [x, y],
      "thickness": 0.15,
      "height": 3.0,
      "is_interior": false
    },
    {
      "name": "DOOR_NAME",
      "type": "door",
      "position": [x, y, z],
      "width": 0.9,
      "height": 2.1,
      "host_wall": "WALL_NAME"
    },
    {
      "name": "WINDOW_NAME",
      "type": "window",
      "position": [x, y, z],
      "width": 1.2,
      "height": 1.0,
      "sill_height": 0.9,
      "host_wall": "WALL_NAME"
    },
    {
      "name": "ROOF_NAME",
      "type": "roof",
      "bounds": {"min_x":, "max_x": , "min_y": , "max_y": },
      "ridge_height": 4.5,
      "eave_height": 3.0
    }
  ]
}
```

### Coordinate Convention (Script Expects)
- Y = 0 at back of building
- Y negative toward front
- X = 0 at left side
- X positive toward right

## Files Created During This Effort

### Config Folder
`C:\Dev\bonsai-extensions\IfcOpenShell\src\bonsai\scripts\2dto3d\config\`
- VISION_PREPROCESSOR_PROMPT.md - Instructions for LLM to interpret Vision API output
- TB_LKTN_LAYOUT_VERIFICATION.txt - ASCII art floor plan for verification
- DICTIONARY_ADDITIONS.json - Malaysian/architectural vocabulary
- TB_LKTN_INSTANCE.json - Comprehensive instance data from Opus

### Output Folder
`C:\Dev\bonsai-extensions\IfcOpenShell\src\bonsai\scripts\2dto3d\OUTPUT\`
- Multiple JSON attempts (to be cleaned up)
- staged_extraction_v2_FINAL.json - Dec 20 baseline attempt

### Work Directory
`C:\Dev\bonsai-extensions\WORK_DIR\`
- Multiple .blend attempts (to be cleaned up)
- TB_LKTN_corrected.json - coordinate conversion attempt

## Recommendations for Next Attempt

### 1. Establish Ground Truth First
- Get the original TB-LKTN PDF
- Manually verify key dimensions:
  - Total building width (is it 9.9m or 11.2m?)
  - Where does column A fall (exterior drain or building wall)?
  - Row 1 vs Row 2 (which is the actual front wall?)

### 2. Create Single Authoritative JSON
- Based on verified dimensions
- Use the coordinate system the script expects (Y=0 at back, negative toward front)
- Document every placement with reference to the PDF

### 3. Visual Verification Before 3D
- Create a 2D plot of the JSON placements
- Overlay on or compare to the PDF
- Confirm walls, doors, windows are in correct positions

### 4. Incremental Building
- Start with just exterior walls
- Verify in Blender
- Add interior walls, verify
- Add openings, verify
- Add roof, verify

### 5. Lock Each Stage
- Once a stage is verified correct, lock it
- Don't modify locked stages when fixing later stages
- If a locked stage needs change, understand WHY before changing

## Key Vocabulary (Malaysian)

- BILIK = Room
- BILIK UTAMA = Master Bedroom
- BILIK MANDI = Bathroom
- TANDAS = Toilet
- DAPUR = Kitchen
- RUANG TAMU = Living Room
- RUANG MAKAN = Dining Room
- ANJUNG = Porch/Veranda
- RUANG BASAH = Wet Area

## Date of This Document
December 22, 2025

## Status
Development paused to establish proper baseline before continuing.
The strategy is sound; the execution needs a verified starting point.
