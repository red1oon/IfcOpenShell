# PDF to Blender/IFC Topology Extractor

Converts topographic survey PDFs to Blender scenes and IFC files with proper elevation data.

## Features

- **PDF topology extraction** - Extract elevation points from survey PDFs
- **Blender integration** - Places PDF image at Z=40m with 3D points
- **IFC export** - Survey points as IFC elements
- **DXF export** - AutoCAD compatible format

---

## FULL WORKFLOW (Start to End)

```
1. PREPARE IMAGE
   - Convert PDF to high-res PNG: convert -density 300 survey.pdf survey.png
   - Or use existing survey_highres.png (9934x7017 @ 300 DPI)

2. EXTRACT ELEVATIONS (choose one method)

   A) TILE METHOD (35 tiles for large images):
      - Generate tiles: python extract_tiles.py survey.png
      - AI reads each tile, outputs JSON with x,y,z points

   B) RASTER SCAN METHOD (~1690 strips):
      - Generate strips: python raster_scan_pipeline.py survey.png --generate-only
      - AI reads strips, record h_sightings/v_sightings
      - Calculate positions with clustering (see README sections below)

3. CREATE JSON
   - Format: {"metadata": {...}, "ground_elevations": [{id, x, y, z}, ...]}
   - Mark uncertain digits with 'X' (e.g., "43.12X")
   - See JSON Format section below

4. GENERATE BLEND FILE
   blender --background --python survey_to_blend.py -- output.json survey.png output.blend

   ⚠️ ALWAYS use --background! NEVER launch Blender interactively.

5. VERIFY IN BLENDER (user opens manually)
   - Reference image Z = 40.000
   - Image matches points bounding box (no padding)
   - Points appear above image (Z > 40)
   - Check .debug.log if uncertain values exist

6. EXPORT (optional)
   - File > Export > IFC
   - File > Export > DXF
```

---

## CRITICAL REQUIREMENTS (AI MUST FOLLOW)

### survey_to_blend.py - Reference Image

| Requirement | Value | Notes |
|-------------|-------|-------|
| **Z Position** | `40.000` exactly | Not 40.0, must be 40.000 |
| **Image Width** | `max_x - min_x` | From points bounding box (NO padding) |
| **Image Height** | `max_y - min_y` | From points bounding box (NO padding) |
| **Image Center** | Points centroid | `((min_x+max_x)/2, (min_y+max_y)/2, 40.000)` |
| **Cropping** | NONE | Show FULL image, not cropped |
| **Aspect Ratio** | NOT preserved | Stretch full image to fit points bbox |

### Blender Empty Image Scaling

```python
# CORRECT scaling for image empty:
empty.empty_display_size = 1.0
empty.scale = (width, height, 1.0)  # width/height in meters

# WRONG (produces tiny image):
empty.empty_display_size = max(width, height)
empty.scale = (width / img.size[0], height / img.size[1], 1.0)
```

### Uncertainty Handling

- Unclear digit → replace with 'X' (e.g., `"43.12X"`)
- Multiple unclear → `"44.X5X"`
- Completely unreadable → `"XX.XXX"` → Z=41.000 placeholder
- All uncertain values logged in `.debug.log`

### JSON Format

```json
{
  "metadata": {
    "source": "survey_highres.png",
    "image_dimensions": {"width": 9934, "height": 7017},
    "scale": 0.01,
    "point_count": 287
  },
  "ground_elevations": [
    {"id": "PT_001", "x": 1120, "y": 740, "z": 44.096},
    {"id": "PT_002", "x": 1180, "y": 780, "z": "43.12X"}
  ]
}
```

Note: `z` can be float (certain) or string with X (uncertain)

---

## Extraction Rules

### Format Filter
```
ONLY accept: XX.XXX where XX is 40-50
  ✓ Accept: 44.673, 43.285, 45.008
  ✗ Reject: PT12676 (lot numbers)
  ✗ Reject: 1:500 (scale)
  ✗ Reject: 77-6 (grid references)
  ✗ Reject: PA 102500 (survey references)
```

### Color Separation
- **Black text** = Ground Elevations (extract these)
- **Cyan text** = Invert Levels (IL) - extract separately or ignore

---

## Raster Scan Method (TV-Style)

### Core Concept

```
Instead of AI estimating positions (unreliable):
  → Scan image in overlapping strips
  → AI only answers: "What complete numbers do you see?"
  → Position derived from WHICH strips report each Z value
```

**Why it works:**
- AI task is simple binary: "Is this number fully visible?"
- No position estimation by AI
- Code handles all math
- Overlapping strips guarantee every value captured at least once

### Parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Strip size | 40px | Fits one elevation label (~20px) with margin |
| Step size | 5-10px | Precision = ±step. Smaller = more accurate |

### Strip Generation

```bash
# Horizontal strips (detect Y position)
for y in $(seq 0 $STEP $((IMG_H - STRIP_SIZE))); do
    convert image.png -crop ${IMG_W}x${STRIP_SIZE}+0+${y} +repage h_strips/h_${y}.png
done

# Vertical strips (detect X position)
for x in $(seq 0 $STEP $((IMG_W - STRIP_SIZE))); do
    convert image.png -crop ${STRIP_SIZE}x${IMG_H}+${x}+0 +repage v_strips/v_${x}.png
done
```

### Expected Strip Counts

| Image Size | Step | H-Strips | V-Strips | Total |
|------------|------|----------|----------|-------|
| 400x400 | 10 | 37 | 37 | ~74 |
| 2000x1412 | 10 | 137 | 196 | ~333 |
| **9934x7017** | 10 | 699 | 991 | **~1690** |

Formula: `strips = (dimension - strip_size) / step + 1`

### AI Prompt (per strip)

```
Look at this strip from a survey drawing.
List ALL elevation numbers that are FULLY VISIBLE (not cut off).

FORMAT FILTER: Only XX.XXX where XX is 40-50
  ✓ Accept: 44.673, 43.285, 45.008
  ✗ Reject: PT12676 (lot), 1:500 (scale), coordinates

UNCERTAINTY: Replace unclear digits with X
  - Clear: "44.673"
  - Last digit unclear: "44.67X"
  - Multiple unclear: "44.6XX"

Return JSON array: ["44.673", "43.285", "44.67X", ...]
Return empty array if none: []
```

### Data Collection

```python
h_sightings = {}  # {z_value: [y_positions where seen]}
v_sightings = {}  # {z_value: [x_positions where seen]}

# Process horizontal strips
for strip_file in sorted(h_strips_dir.glob("h_*.png")):
    y_pos = int(strip_file.stem.split("_")[1])
    z_list = ai_read_strip(strip_file)
    for z in z_list:
        h_sightings.setdefault(z, []).append(y_pos)

# Process vertical strips  
for strip_file in sorted(v_strips_dir.glob("v_*.png")):
    x_pos = int(strip_file.stem.split("_")[1])
    z_list = ai_read_strip(strip_file)
    for z in z_list:
        v_sightings.setdefault(z, []).append(x_pos)
```

---

## CRITICAL: Duplicate Z Value Handling

### Problem

Same elevation (e.g., 44.071) can appear at TWO different locations along a contour line.

```
H-scan sees 44.071 in:  Y=200, Y=210  AND  Y=240, Y=250  (TWO clusters!)
V-scan sees 44.071 in:  X=150, X=160  AND  X=300, X=310  (TWO clusters!)

WRONG (naive approach):
  y_center = (200 + 250 + 40) / 2 = 245  ← midpoint of BOTH clusters = WRONG POSITION
  
RIGHT (with clustering):
  Cluster 1: Y=200-210, X=150-160 → Point A at (175, 225)
  Cluster 2: Y=240-250, X=300-310 → Point B at (325, 265)
```

### Solution: Cluster Sightings Before Position Calculation

```python
def cluster_sightings(positions, max_gap=30):
    """Split positions into separate clusters if gap > max_gap pixels"""
    if not positions:
        return []
    positions = sorted(positions)
    clusters = [[positions[0]]]
    
    for pos in positions[1:]:
        if pos - clusters[-1][-1] <= max_gap:
            clusters[-1].append(pos)
        else:
            clusters.append([pos])
    
    return clusters

# Usage example:
h_clusters = cluster_sightings(h_sightings["44.071"], max_gap=30)
# Input:  [200, 210, 240, 250]
# Output: [[200, 210], [240, 250]]  ← TWO separate clusters
```

### Enhanced Position Calculation

```python
STRIP_SIZE = 40

def calculate_positions(h_sightings, v_sightings, img_height):
    results = []
    confirmed = set(h_sightings.keys()) & set(v_sightings.keys())
    
    for z in confirmed:
        h_clusters = cluster_sightings(h_sightings[z])
        v_clusters = cluster_sightings(v_sightings[z])
        
        # Match clusters by proximity (simplified: assume same order)
        # For complex cases, use spatial proximity matching
        for i, h_cluster in enumerate(h_clusters):
            if i < len(v_clusters):
                v_cluster = v_clusters[i]
                
                y_center = (min(h_cluster) + max(h_cluster) + STRIP_SIZE) / 2
                x_center = (min(v_cluster) + max(v_cluster) + STRIP_SIZE) / 2
                y_blender = img_height - y_center
                
                results.append({
                    "z": float(z) if 'X' not in str(z) else z,
                    "x": round(x_center, 1),
                    "y": round(y_center, 1),
                    "y_blender": round(y_blender, 1),
                    "uncertain": 'X' in str(z)
                })
    
    return results
```

---

## Expected Accuracy

| Metric | Expected | Notes |
|--------|----------|-------|
| Z value accuracy | ~90% | 10% reading errors from compression/hatching |
| Position precision | ±step size | Step=10px → ±10-15px accuracy |
| Coverage | 95%+ | Some values only in H or V scan need review |
| User adjustment | Expected | Overlay dots may need manual fine-tuning |

### Error Sources

1. **JPEG compression** - blurs digits (3↔8, 1↔7 confusion)
2. **Hatched areas** - building patterns overlap text
3. **Dense clusters** - multiple values close together
4. **AI reading mistakes** - accumulate over many strips
5. **Duplicate Z values** - same elevation at different locations (solved with clustering)

### Acceptable Trade-off

10% error rate is acceptable. Users can manually adjust overlay dots in Blender.

---

## Usage

```bash
# Generate strips
python raster_scan_pipeline.py survey.png --generate-only --step 10

# AI reads strips (Claude Code processes each)
# Outputs: h_sightings.json, v_sightings.json

# Calculate positions
python raster_scan_pipeline.py --calculate h_sightings.json v_sightings.json

# Convert to Blender
blender --background --python survey_to_blend.py -- survey.json survey.png output.blend

# Export to IFC
blender --background output.blend --python survey_to_ifc.py
```

## Files

| File | Purpose |
|------|---------|
| `survey_to_blend.py` | JSON → Blender converter |
| `survey_to_ifc.py` | Blender → IFC exporter |
| `insert_text_to_dxf.py` | Add text labels to DXF |
| `raster_scan_pipeline.py` | Strip-based extraction |
| `extract_tiles.py` | Tile generation for AI |

---

## Alternative: Tile Method

For very large images, use tiles instead of strips:

| Image | Tile Size | Tiles |
|-------|-----------|-------|
| 9934x7017 | 1500x1500 | 35 tiles |

Layout (7 columns × 5 rows):
```
Row 0: tile_000 to tile_006 (y: 0-1500)
Row 1: tile_007 to tile_013 (y: 1500-3000)
Row 2: tile_014 to tile_020 (y: 3000-4500)
Row 3: tile_021 to tile_027 (y: 4500-6000)
Row 4: tile_028 to tile_034 (y: 6000-7017)
```

Global position: `x_global = tile_col * 1500 + x_in_tile`

---

## Verification Checklist

After running survey_to_blend.py, verify in Blender:
- [ ] Reference image Z location = 40.000
- [ ] Reference image covers exactly the points area (no padding)
- [ ] Points appear above the image (Z > 40)
- [ ] .debug.log generated if uncertain values exist
- [ ] Duplicate Z values create separate points (not merged)

---

## Key Insight

**Decompose the problem.** Don't ask AI to do Z + X + Y simultaneously.

1. Solve **Z** first (verified list from strips)
2. Then **X** (which vertical strips)
3. Then **Y** (which horizontal strips)
4. **Cluster** same-Z sightings before calculating positions
5. Each axis solved independently with guaranteed overlap coverage

---

## Validated Results

| Sample Area | Points Found | Accuracy |
|-------------|--------------|----------|
| 400×400 tile | 40-50 | ~90% |
| 2000×1412 full | 300-400 expected | TBD |

Processing time estimate: ~1-2 seconds per strip × 1690 strips ≈ 30-50 minutes for full image.
