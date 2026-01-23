"""
PDF-to-Blender Survey Pipeline - Critical Implementation Notes
==============================================================

TESTED & WORKING: December 2025 - 557 points, pixel-perfect alignment

BUG #1: BLENDER IMAGE SCALE (Most Critical)
-------------------------------------------
Blender normalizes image empty to longest dimension (1.0 × aspect_ratio).
Setting scale=(width, height) applies aspect ratio TWICE → Y compressed.

    WRONG:  empty.scale = (world_width, world_height, 1.0)
    RIGHT:  empty.scale = (world_width, world_width, 1.0)  # Width for BOTH!

BUG #2: DECIMAL SEPARATOR
-------------------------
Google Vision sometimes returns comma instead of period (44,317 not 44.317).

    WRONG:  pattern = re.compile(r'^4[0-9]\.[0-9]{3}$')
    RIGHT:  pattern = re.compile(r'^[2-5][0-9][.,][0-9]{2,3}$')
            z_value = float(text.replace(',', '.'))

BUG #3: IMAGE DIMENSIONS
------------------------
Vision API text bounds are SMALLER than actual image. Use PIL.

    WRONG:  width = max(v.x for annotations)  # Gives 9598, not 9934!
    RIGHT:  from PIL import Image
            img = Image.open(path)
            width, height = img.size

BUG #4: IMAGE ANCHOR
--------------------
Default anchor is center (-0.5, -0.5), causing offset.

    RIGHT:  empty.empty_image_offset = (0, 0)  # Bottom-left
            empty.location = (0, 0, Z_HEIGHT)

COORDINATE TRANSFORM
--------------------
Image Y=0 is top, Blender Y=0 is bottom. Must flip.

    x_world = px * scale
    y_world = (image_height - py) * scale

VALIDATION CHECKLIST
--------------------
Before running:
[ ] Image dimensions from PIL match JSON metadata
[ ] Scale produces reasonable world size (10m - 10km)
[ ] Point count > 10

After running:
[ ] Points visually align with survey text
[ ] Image fills same bounds as points
"""

# =============================================================================
# CRITICAL: Copy the create_reference_image fix below into survey_to_blend.py
# =============================================================================

def create_reference_image_FIXED(image_path: str, world_width: float, world_height: float, z_height: float = 40.0):
    """
    Create reference image empty with CORRECT scaling.
    
    CRITICAL: Blender normalizes image to longest dimension, then multiplies by scale.
    We must use world_width for BOTH X and Y scale, not (width, height).
    Blender's internal aspect ratio handles the rest.
    
    DO NOT "FIX" THIS TO (world_width, world_height) - IT WILL BREAK ALIGNMENT!
    """
    import bpy
    
    bpy.ops.object.empty_add(type='IMAGE', location=(0, 0, z_height))
    empty = bpy.context.active_object
    empty.name = "Survey_Reference_Image"
    
    # Load image
    img = bpy.data.images.load(image_path)
    empty.data = img
    
    # CRITICAL SETTINGS
    empty.empty_display_size = 1.0
    empty.empty_image_offset = (0, 0)  # Bottom-left anchor
    
    # CRITICAL: Use world_width for BOTH axes!
    # Blender handles aspect ratio internally.
    empty.scale = (world_width, world_width, 1.0)
    
    return empty


# =============================================================================
# CRITICAL: Copy the elevation pattern fix below into extraction script
# =============================================================================

import re

def extract_elevation_FIXED(text: str) -> float | None:
    """
    Extract elevation value, handling both period and comma decimal separators.
    
    Google Vision sometimes OCRs decimal point as comma (44,317 instead of 44.317).
    This regex accepts both and normalizes to float.
    """
    # Accept 20.000 to 59.999 range, period OR comma separator
    pattern = re.compile(r'^[2-5][0-9][.,][0-9]{2,3}$')
    
    text = text.strip()
    if pattern.match(text):
        return float(text.replace(',', '.'))
    return None


# =============================================================================
# CRITICAL: Copy the validation function into pipeline
# =============================================================================

def validate_before_blender(json_data: dict, image_path: str) -> bool:
    """
    Validate extraction data before Blender generation.
    Call this BEFORE running survey_to_blend.py
    """
    from PIL import Image
    
    img = Image.open(image_path)
    meta = json_data['metadata']
    errors = []
    
    # Check 1: Dimensions match
    if meta['image_dimensions']['width'] != img.size[0]:
        errors.append(f"Width: JSON={meta['image_dimensions']['width']} vs Actual={img.size[0]}")
    
    if meta['image_dimensions']['height'] != img.size[1]:
        errors.append(f"Height: JSON={meta['image_dimensions']['height']} vs Actual={img.size[1]}")
    
    # Check 2: Points in bounds
    for pt in json_data['ground_elevations']:
        if not (0 <= pt['x'] <= img.size[0] and 0 <= pt['y'] <= img.size[1]):
            errors.append(f"Point {pt['id']} at ({pt['x']}, {pt['y']}) outside image")
            break  # Just report first one
    
    # Check 3: Reasonable world size
    scale = meta.get('scale', 0.01)
    world_w = img.size[0] * scale
    world_h = img.size[1] * scale
    
    if not (10 < world_w < 10000 and 10 < world_h < 10000):
        errors.append(f"Suspicious world size: {world_w:.0f}×{world_h:.0f}m")
    
    if errors:
        print("❌ VALIDATION FAILED:")
        for e in errors:
            print(f"   - {e}")
        return False
    
    print(f"✓ Validated: {len(json_data['ground_elevations'])} points, {world_w:.0f}×{world_h:.0f}m")
    return True
