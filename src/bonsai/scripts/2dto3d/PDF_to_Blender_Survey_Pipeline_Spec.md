# PDF-to-Blender Survey Pipeline Specification

## Version: 1.0 (December 2025)
## Status: Production-Ready

---

## Executive Summary

This specification documents a robust pipeline for extracting ground elevation points from topographic survey PDFs and visualizing them in Blender. The pipeline uses Google Cloud Vision API for OCR and handles Malaysian survey drawings at scales up to 1:500.

**Key Achievement:** 557+ elevation points extracted and plotted with pixel-perfect alignment.

---

## Pipeline Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   survey.pdf    │────►│ survey.png      │────►│ Google Vision   │
│   (from CAD)    │     │ (300+ DPI)      │     │ API             │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  survey.blend   │◄────│ survey_to_blend │◄────│ survey.json     │
│  (final output) │     │ .py             │     │ (cached coords) │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

### Cost Model

| Step | API Calls | Cost |
|------|-----------|------|
| Initial extraction | 1 per survey | Free (first 1000/month) |
| Re-generation | 0 | Free (uses cached JSON) |
| Scale/transform fixes | 0 | Free (uses cached JSON) |

---

## Phase 1: PDF to PNG Conversion

### Requirements

- **Resolution:** 300-600 DPI recommended
- **Format:** PNG (lossless)
- **Color:** RGB or Grayscale (both work)
- **Max Size:** Under 75 megapixels (Vision API limit)

### Verification

```bash
# Check image dimensions and DPI
identify -verbose survey.png | grep -E "(Geometry|Resolution|Units)"

# Example output:
#   Geometry: 9934x7017
#   Resolution: 300x300
#   Units: PixelsPerInch
```

---

## Phase 2: Google Vision API Extraction

### API Configuration

```python
from google.cloud import vision

client = vision.ImageAnnotatorClient()

# DOCUMENT_TEXT_DETECTION is better for dense survey text
response = client.document_text_detection(image=image)
```

### Critical: Decimal Separator Handling

Google Vision sometimes reads decimal points as commas. **MUST accept both:**

```python
# CORRECT - accepts both formats
pattern = re.compile(r'^[2-5][0-9][.,][0-9]{2,3}$')

if pattern.match(text):
    z_value = float(text.replace(',', '.'))  # Normalize to period
```

**Bug Found:** "44.317" was returned as "44,317" and rejected by period-only regex.

### Critical: Image Dimensions from PIL (Not API)

```python
# CORRECT - use actual image file
from PIL import Image
img = Image.open(image_path)
width, height = img.size

# WRONG - Vision API text bounds are SMALLER than image
# This caused 9598 vs 9934 mismatch (336 pixel error!)
width = max(v.x for annotations)   # DON'T DO THIS
height = max(v.y for annotations)  # DON'T DO THIS
```

**Bug Found:** Using API text bounds gave 9598×6777 instead of actual 9934×7017.

### Output JSON Format

```json
{
  "metadata": {
    "source": "survey.png",
    "image_dimensions": {"width": 9934, "height": 7017},
    "scale": 0.0423,
    "point_count": 557,
    "extraction_method": "google_vision_api"
  },
  "ground_elevations": [
    {
      "id": "GL_0001",
      "x": 1156.5,
      "y": 763.0,
      "z": 44.096,
      "text": "44.096",
      "type": "ground_level"
    }
  ]
}
```

---

## Phase 3: Blender Import

### Critical: Image Empty Scale Bug

**This is the most important fix in the entire pipeline.**

Blender's image empty normalizes the image to its longest dimension, then applies scale. Using `(width, height)` applies aspect ratio TWICE.

```python
# ═══════════════════════════════════════════════════════════════════
# CRITICAL BLENDER BUG FIX - DO NOT CHANGE
# ═══════════════════════════════════════════════════════════════════
#
# Blender's empty_display_size=1.0 normalizes image to longest dimension
# e.g., 9934×7017 becomes 1.0 × 0.706 internally
#
# If we set scale = (420, 297, 1):
#   Result: 420 × (0.706 × 297) = 420 × 209.7  ← WRONG!
#
# If we set scale = (420, 420, 1):
#   Result: 420 × (0.706 × 420) = 420 × 296.5  ← CORRECT!
#
# Blender handles aspect ratio. We provide target WIDTH for both axes.
# ═══════════════════════════════════════════════════════════════════

empty.empty_display_size = 1.0
empty.scale = (world_width, world_width, 1.0)  # USE WIDTH FOR BOTH!
```

### Coordinate Transform

```python
def pixel_to_world(px, py, image_height, scale):
    """
    Convert pixel coordinates to Blender world coordinates.
    
    - Image origin: top-left (pixel 0,0)
    - Blender origin: bottom-left (world 0,0)
    - Therefore: Y must be flipped
    """
    x = px * scale
    y = (image_height - py) * scale  # Flip Y axis
    return (x, y)
```

### Image Anchor Point

```python
# Image empty MUST be anchored at bottom-left (0, 0)
bpy.ops.object.empty_add(type='IMAGE', location=(0, 0, 40.0))
empty = bpy.context.active_object
empty.empty_image_offset = (0, 0)  # Bottom-left anchor, NOT default (-0.5, -0.5)
```

---

## Validation Checks

### Pre-Blender Validation

```python
def validate_extraction(json_data, image_path):
    """
    Run BEFORE Blender generation to catch errors early.
    """
    from PIL import Image
    img = Image.open(image_path)
    errors = []
    
    meta = json_data['metadata']
    
    # Check 1: Image dimensions match
    if meta['image_dimensions']['width'] != img.size[0]:
        errors.append(f"Width mismatch: JSON={meta['image_dimensions']['width']}, Actual={img.size[0]}")
    
    if meta['image_dimensions']['height'] != img.size[1]:
        errors.append(f"Height mismatch: JSON={meta['image_dimensions']['height']}, Actual={img.size[1]}")
    
    # Check 2: All points within image bounds
    for pt in json_data['ground_elevations']:
        if not (0 <= pt['x'] <= img.size[0]):
            errors.append(f"Point {pt['id']} X={pt['x']} outside image width")
        if not (0 <= pt['y'] <= img.size[1]):
            errors.append(f"Point {pt['id']} Y={pt['y']} outside image height")
    
    # Check 3: Scale produces reasonable dimensions
    scale = meta.get('scale', 0)
    world_width = img.size[0] * scale
    world_height = img.size[1] * scale
    
    if world_width < 10 or world_width > 10000:
        errors.append(f"Suspicious world width: {world_width}m")
    if world_height < 10 or world_height > 10000:
        errors.append(f"Suspicious world height: {world_height}m")
    
    # Check 4: Point count sanity
    if len(json_data['ground_elevations']) < 10:
        errors.append(f"Low point count: {len(json_data['ground_elevations'])} (expected 50+)")
    
    if errors:
        print("VALIDATION ERRORS:")
        for e in errors:
            print(f"  - {e}")
        return False
    
    print(f"Validation passed: {len(json_data['ground_elevations'])} points, {world_width:.1f}×{world_height:.1f}m")
    return True
```

### Post-Blender Verification

```python
def verify_blender_output():
    """
    Run IN Blender to verify alignment.
    """
    import bpy
    
    img_empty = bpy.data.objects.get('Survey_Reference_Image')
    if not img_empty:
        print("ERROR: No Survey_Reference_Image found")
        return
    
    # Get actual display bounds
    scale = img_empty.scale
    loc = img_empty.location
    
    print(f"Image location: {loc}")
    print(f"Image scale: {scale}")
    print(f"Image bounds: X[{loc.x} to {loc.x + scale.x}], Y[{loc.y} to {loc.y + scale.y}]")
    
    # Check a few points
    points_col = bpy.data.collections.get('Ground_Elevations')
    if points_col and len(points_col.objects) > 0:
        sample = list(points_col.objects)[:3]
        print(f"Sample points:")
        for obj in sample:
            print(f"  {obj.name}: ({obj.location.x:.1f}, {obj.location.y:.1f}, {obj.location.z:.3f})")
```

---

## Scale Calculation

### Method 1: From Drawing Scale Note

```python
# If drawing shows "SKALA 1:500" and was exported at 300 DPI:
# 1:500 means 1mm on paper = 500mm real
# At 300 DPI: 1 inch = 300 pixels, 1mm ≈ 11.8 pixels
# So: 1 pixel = 500mm / 11.8 ≈ 0.042m

scale = 0.042  # For 1:500 at 300 DPI
```

### Method 2: From Chainage Markers (More Accurate)

```python
# Find chainage markers in Vision output
# e.g., "T 16800" at x=427, "T 17100" at x=7518

pixel_span = 7518 - 427      # 7091 pixels
real_span = 17100 - 16800    # 300 meters

scale = real_span / pixel_span  # 0.0423 m/pixel
```

### Method 3: From Known Points (Most Accurate)

```python
# Get real coordinates from surveyor for 2+ points
# e.g., Point 44.096: Real (E: 123456, N: 345678), Pixel (1156, 763)
#       Point 45.008: Real (E: 123556, N: 345578), Pixel (5500, 2000)

dx_real = 123556 - 123456    # 100m
dx_pixel = 5500 - 1156       # 4344 pixels
scale_x = dx_real / dx_pixel # 0.023 m/pixel

dy_real = 345678 - 345578    # 100m  
dy_pixel = 2000 - 763        # 1237 pixels (remember Y is flipped)
scale_y = dy_real / dy_pixel # 0.081 m/pixel

# If scale_x ≠ scale_y, drawing has non-uniform scale (common in corridor surveys)
```

---

## Troubleshooting Guide

| Symptom | Cause | Fix |
|---------|-------|-----|
| Y appears compressed | Blender scale bug | Use `(width, width, 1)` not `(width, height, 1)` |
| Points shifted from text | Wrong image_height in Y-flip | Use PIL to get actual dimensions |
| Missing elevation values | Comma decimal separator | Use regex that accepts both `.` and `,` |
| Points outside image | Image dimensions from API bounds | Use PIL, not Vision API text bounds |
| Diagonal drift/shear | Wrong anchor point | Set `empty_image_offset = (0, 0)` |
| Everything offset | Image not at origin | Set image location to `(0, 0, Z)` |
| Scale way off | Wrong DPI assumption | Calculate from chainage markers |

---

## Files and Dependencies

### Required Python Packages

```bash
pip install google-cloud-vision Pillow
```

### Blender Requirements

- Blender 3.0+ (tested on 4.0, 5.0)
- No add-ons required

### File Structure

```
pdf2blend/
├── INPUT/
│   └── survey_highres.png      # Source image
├── CACHE/
│   └── survey_output.json      # Vision API result (reusable)
├── OUTPUT/
│   └── survey.blend            # Final output
└── scripts/
    ├── survey_extract.py       # Calls Vision API → JSON
    └── survey_to_blend.py      # Reads JSON → .blend
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Dec 2025 | Initial production release after debugging alignment issues |

### Bugs Fixed in This Version

1. **Blender Y-scale compression** - Image displayed at 70% height due to double aspect ratio application
2. **Missing elevation values** - Comma decimal separator not recognized
3. **Image dimension mismatch** - Using Vision API text bounds instead of actual image size
4. **Image anchor offset** - Default (-0.5, -0.5) caused positional drift

---

## Credits

Developed for BIM Syncro Engineers Sdn Bhd
Pipeline tested on Malaysian JKR road survey drawings (1:500 scale)
