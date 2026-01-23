# Raster Scan PDF Topology Extraction
## Complete Method for Survey Elevation Extraction

**Validated:** 49 points extracted from 400x400 tile, ~90% accuracy, ±15-25px precision

---

## Core Concept: TV-Style Raster Scan

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

---

## Algorithm

### Phase 1: Generate Strips

```
Horizontal strips (detect Y position):
┌─────────────────────────────────────┐ Y=0
├─────────────────────────────────────┤ Y=step
├─────────────────────────────────────┤ Y=step*2
...

Vertical strips (detect X position):
┌─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┬─┐
│ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │ │
X=0 step                            X=max
```

**Parameters:**
| Parameter | Recommended | Rationale |
|-----------|-------------|-----------|
| Strip size | 40px | Fits one elevation label (~20px) with margin |
| Step size | 5-10px | Precision = ±step. Smaller = more strips but better accuracy |

**Strip generation:**
```bash
# Horizontal strips
for y in $(seq 0 $STEP $((IMG_H - STRIP_SIZE))); do
    convert image.png -crop ${IMG_W}x${STRIP_SIZE}+0+${y} +repage h_strips/h_${y}.png
done

# Vertical strips  
for x in $(seq 0 $STEP $((IMG_W - STRIP_SIZE))); do
    convert image.png -crop ${STRIP_SIZE}x${IMG_H}+${x}+0 +repage v_strips/v_${x}.png
done
```

### Phase 2: AI Reads Each Strip

**Prompt (same for all strips):**
```
Look at this strip from a survey drawing.
List ALL elevation numbers that are FULLY VISIBLE (not cut off at any edge).
Elevation format: XX.XXX (e.g., 44.673, 43.285)

Rules:
- Only report COMPLETE numbers (all digits visible)
- Ignore lot numbers (PT66100), road names, survey references
- Ignore numbers cut off at edges

Return JSON array: ["44.673", "43.285", ...]
Return empty array if none: []
```

**Data collection:**
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

### Phase 3: Calculate Positions

```python
STRIP_SIZE = 40

results = []
confirmed = set(h_sightings.keys()) & set(v_sightings.keys())

for z in confirmed:
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
```

### Phase 4: Output JSON → IFC

```json
{
  "metadata": {
    "source": "survey_image.png",
    "point_count": 49
  },
  "points": [
    {"z": 44.154, "x": 30.0, "y": 20.0, "y_blender": 380.0},
    {"z": 44.673, "x": 70.0, "y": 25.0, "y_blender": 375.0}
  ]
}
```

Feed to existing `topo_json_to_ifc.py` for IFC generation.

---

## Expected Accuracy

| Metric | Expected | Notes |
|--------|----------|-------|
| Z value accuracy | ~90% | JPEG compression causes ~10% reading errors |
| Position precision | ±step size | Step=10px → ±10-15px accuracy |
| Coverage | 95%+ | Some values only in H or V scan need review |
| User adjustment | Expected | Overlay dots may need manual fine-tuning |

**Error sources:**
1. JPEG compression - blurs digits (use PNG/PDF when possible)
2. Hatched areas - building patterns overlap text
3. Dense clusters - multiple values close together
4. AI reading mistakes - accumulate over many strips

**Acceptable:** 10% error rate. Users can manually adjust overlay dots in Blender.

---

## Practical Tips

### Image Preparation
- Use highest resolution available
- PNG preferred over JPEG
- Convert PDF pages: `convert -density 300 survey.pdf survey.png`

### Strip Parameters by Image Size
| Image Size | Strip Size | Step | Total Strips |
|------------|------------|------|--------------|
| 400x400 | 40 | 10 | ~74 |
| 1000x1000 | 40 | 5 | ~384 |
| 1316x924 | 40 | 5 | ~440 |

### Handling Gaps
```python
# Values only in H-scan (missing X)
h_only = set(h_sightings.keys()) - set(v_sightings.keys())
# → Need more V-strips or manual placement

# Values only in V-scan (missing Y)  
v_only = set(v_sightings.keys()) - set(h_sightings.keys())
# → Need more H-strips or manual placement
```

### Confidence Scoring
```python
# More sightings = higher confidence
confidence = min(len(y_range), len(x_range))
# confidence=1: marginal, may need verification
# confidence=3+: high confidence
```

---

## Quick Reference

```
1. Generate strips:
   convert image.png -crop WxH+X+Y +repage strip.png

2. AI prompt per strip:
   "List fully visible XX.XXX elevation numbers as JSON array"

3. Record sightings:
   h_sightings[z].append(y_pos)
   v_sightings[z].append(x_pos)

4. Calculate position:
   x = (min(x_range) + max(x_range) + strip_size) / 2
   y = (min(y_range) + max(y_range) + strip_size) / 2

5. Output JSON → IFC blender
```

---

## Summary

**Method:** Raster scan with overlapping strips
**AI task:** Binary detection only ("Is number fully visible?")
**Position:** Derived from strip intersection, not AI estimation
**Accuracy:** ~90% Z values correct, ±15-25px position
**User expectation:** Manual fine-tuning of overlay dots acceptable

**Key insight:** Decompose the problem. Don't ask AI to do Z + X + Y simultaneously. 
Solve Z first (verified list), then X (which column), then Y (which row).
Each axis solved independently with guaranteed overlap coverage.
