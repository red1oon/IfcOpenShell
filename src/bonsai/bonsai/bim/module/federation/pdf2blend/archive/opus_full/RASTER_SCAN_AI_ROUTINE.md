# Raster Scan AI Routine - Claude Code Implementation Guide

## Overview

Extract elevation values (Z) with X,Y positions from survey images using TV-style raster scanning.

**Method:** Scan image in overlapping strips. For each strip, identify FULLY VISIBLE elevation numbers. The intersection of horizontal (Y) and vertical (X) strip ranges determines each point's position.

## Input

- Survey image (PNG/JPEG)
- Strip size: 40px (fits one elevation label comfortably)
- Step size: 5px (guarantees every value captured fully in at least one strip)

## Phase 1: Generate Strips

```bash
# Create output directories
mkdir -p raster_output/h_strips raster_output/v_strips

# Get image dimensions
IMG_W=$(identify -format "%w" survey_image.png)
IMG_H=$(identify -format "%h" survey_image.png)

# Generate horizontal strips (for Y detection)
for y in $(seq 0 5 $((IMG_H - 40))); do
    convert survey_image.png -crop ${IMG_W}x40+0+${y} +repage raster_output/h_strips/h_$(printf "%04d" $y).png
done

# Generate vertical strips (for X detection)
for x in $(seq 0 5 $((IMG_W - 40))); do
    convert survey_image.png -crop 40x${IMG_H}+${x}+0 +repage raster_output/v_strips/v_$(printf "%04d" $x).png
done
```

## Phase 2: AI Strip Reading

For EACH strip image, the AI task is simple and consistent:

### Prompt for Horizontal Strips:
```
Look at this horizontal strip from a survey drawing.
List ALL elevation numbers that are FULLY VISIBLE (not cut off at top or bottom).
Elevation format: XX.XXX (e.g., 44.673, 43.285)

Rules:
- Only report numbers that are COMPLETE (all digits visible)
- Ignore lot numbers (PT66100), road names, survey references
- Ignore numbers cut off at edges

Return as JSON array: ["44.673", "43.285", ...]
If no complete elevations visible, return: []
```

### Prompt for Vertical Strips:
```
Look at this vertical strip from a survey drawing.
List ALL elevation numbers that are FULLY VISIBLE (not cut off at left or right).
Elevation format: XX.XXX (e.g., 44.673, 43.285)

Rules:
- Only report numbers that are COMPLETE (all digits visible)
- Ignore lot numbers, road names, survey references
- Ignore numbers cut off at edges

Return as JSON array: ["44.673", "43.285", ...]
If no complete elevations visible, return: []
```

### Processing Loop:

```python
import json
from pathlib import Path

h_sightings = {}  # {z_value: [y_positions]}
v_sightings = {}  # {z_value: [x_positions]}

# Process horizontal strips
h_strips_dir = Path("raster_output/h_strips")
for strip_file in sorted(h_strips_dir.glob("h_*.png")):
    y_pos = int(strip_file.stem.split("_")[1])
    
    # AI reads this strip image
    z_list = ai_read_strip(strip_file, direction="horizontal")
    
    for z in z_list:
        if z not in h_sightings:
            h_sightings[z] = []
        h_sightings[z].append(y_pos)

# Process vertical strips
v_strips_dir = Path("raster_output/v_strips")
for strip_file in sorted(v_strips_dir.glob("v_*.png")):
    x_pos = int(strip_file.stem.split("_")[1])
    
    # AI reads this strip image
    z_list = ai_read_strip(strip_file, direction="vertical")
    
    for z in z_list:
        if z not in v_sightings:
            v_sightings[z] = []
        v_sightings[z].append(x_pos)

# Save intermediate results
with open("raster_output/h_sightings.json", "w") as f:
    json.dump(h_sightings, f, indent=2)
with open("raster_output/v_sightings.json", "w") as f:
    json.dump(v_sightings, f, indent=2)
```

## Phase 3: Calculate Positions

```python
STRIP_SIZE = 40
IMG_HEIGHT = 400  # From actual image

results = []

# Find Z values confirmed in BOTH scans
confirmed_z = set(h_sightings.keys()) & set(v_sightings.keys())

for z in sorted(confirmed_z, key=float):
    y_range = h_sightings[z]
    x_range = v_sightings[z]
    
    # Center of visibility range
    y_center = (min(y_range) + max(y_range) + STRIP_SIZE) / 2
    x_center = (min(x_range) + max(x_range) + STRIP_SIZE) / 2
    
    # Flip Y for Blender (origin bottom-left)
    y_blender = IMG_HEIGHT - y_center
    
    results.append({
        "z": float(z),
        "x": round(x_center, 1),
        "y": round(y_center, 1),
        "y_blender": round(y_blender, 1)
    })

# Save final output
with open("raster_output/z_positions.json", "w") as f:
    json.dump({"points": results}, f, indent=2)
```

## Phase 4: Generate IFC

Use existing `topo_json_to_ifc.py` or equivalent:

```bash
python topo_json_to_ifc.py raster_output/z_positions.json --output survey_points.ifc
```

## Output JSON Format

```json
{
  "metadata": {
    "source_image": "survey_image.png",
    "image_size": [1316, 924],
    "point_count": 287
  },
  "points": [
    {"z": 44.154, "x": 30.0, "y": 25.0, "y_blender": 375.0},
    {"z": 44.165, "x": 110.0, "y": 60.0, "y_blender": 340.0},
    ...
  ]
}
```

## Key Principles

1. **AI task is binary**: "Is this number FULLY visible?" - Yes/No
2. **Position derived from strips**: NOT estimated by AI
3. **Overlapping strips guarantee capture**: Every value fully visible in at least one strip
4. **Blanks are data**: Empty strips define boundaries
5. **Code handles all logic**: AI is stateless number detector

## Performance Notes

- 400x400 tile with step=5: ~150 strips total
- Full survey (1316x924) with step=5: ~450 strips
- Each strip = 1 AI call
- Parallelizable: strips are independent

## Error Handling

- Z in h_scan but not v_scan → Flag for manual review
- Fuzzy matching: "44.27" might match "44.270" 
- Duplicate Z values (same elevation twice) → Multiple position clusters
