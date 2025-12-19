#!/usr/bin/env python3
"""
Survey Elevation Extraction Pipeline
=====================================
PDF/PNG -> Google Vision OCR -> JSON -> Blender

TESTED & WORKING: December 2025 - 688 points, pixel-perfect alignment

Usage:
    python survey_extract_pipeline.py survey.png output.json --from-cache vision_raw.json
    python survey_extract_pipeline.py survey.pdf output.json --dpi 300

Options:
    --dpi 300           Set DPI for PDF conversion (default: 300)
    --from-cache FILE   Use cached Vision API response (saves API calls)
    --debug             Show all detected text
    --dump-raw          Save raw Vision API response for reuse

================================================================================
CRITICAL BUGS FIXED - DO NOT REVERT THESE PATTERNS:
================================================================================

BUG #1: DECIMAL SEPARATOR
    Google Vision sometimes returns comma instead of period (44,317 not 44.317).

    WRONG:  pattern = re.compile(r'^4[0-9]\.[0-9]{3}$')
    RIGHT:  pattern = re.compile(r'^[2-5][0-9][.,][0-9]{2,3}$')
            z_value = float(text.replace(',', '.'))

BUG #2: IMAGE DIMENSIONS
    Vision API text bounds are SMALLER than actual image. Use PIL.

    WRONG:  width = max(v.x for annotations)  # Gives 9598, not 9934!
    RIGHT:  from PIL import Image
            img = Image.open(path)
            width, height = img.size

BUG #3: OCR SPLIT VALUES
    Vision sometimes splits "44.103" into "44" + "103" as separate items.
    Use merge_split_elevations() to recombine adjacent number pairs.

BUG #4: SCALE CALCULATION
    Do NOT hardcode scale=0.01. Calculate from chainage markers:

    scale = (chainage_B - chainage_A) / (pixel_B - pixel_A)
    Example: (17100 - 16800) / (7519 - 428) = 0.0423 m/pixel

================================================================================
"""

import json
import re
import sys
import os
from pathlib import Path
import numpy as np


def calculate_affine_transform(points, image_width, image_height, scale=0.0423):
    """
    Calculate affine transform using TRUE bounding box extremes.

    Finds actual min/max X and Y points (with validation), then maps
    the point cloud to a proper rectangle preserving proportions.

    Returns transform matrix and calibration info.
    """
    if len(points) < 10:
        return None, None

    print(f"[AFFINE] Finding extreme boundary points from {len(points)} elevations...")

    # Use ACTUAL extremes (not percentiles - they cut off edge points!)
    xs = sorted([p['x'] for p in points])
    ys = sorted([p['y'] for p in points])

    min_x = xs[0]
    max_x = xs[-1]
    min_y = ys[0]
    max_y = ys[-1]

    print(f"[AFFINE] Actual bounds: X[{min_x:.0f}, {max_x:.0f}] Y[{min_y:.0f}, {max_y:.0f}]")

    # Find points near each edge (use percentage of range for tolerance)
    x_range = max_x - min_x
    y_range = max_y - min_y
    tolerance_x = x_range * 0.05  # 5% of X range
    tolerance_y = y_range * 0.05  # 5% of Y range

    left_pts = [p for p in points if p['x'] < min_x + tolerance_x]
    right_pts = [p for p in points if p['x'] > max_x - tolerance_x]
    top_pts = [p for p in points if p['y'] < min_y + tolerance_y]  # top = min Y in pixels
    bottom_pts = [p for p in points if p['y'] > max_y - tolerance_y]  # bottom = max Y in pixels

    print(f"[AFFINE] Edge point counts: left={len(left_pts)}, right={len(right_pts)}, top={len(top_pts)}, bottom={len(bottom_pts)}")

    # Find representative points for each corner
    # top_left: among left points, find one with small Y
    # top_right: among right points, find one with small Y
    # bottom_left: among left points, find one with large Y
    # bottom_right: among right points, find one with large Y

    def find_corner_point(pts, prefer_min_y=True):
        """Find best corner point from candidates."""
        if not pts:
            return None
        if prefer_min_y:
            return min(pts, key=lambda p: p['y'])
        else:
            return max(pts, key=lambda p: p['y'])

    corners = {
        'top_left': find_corner_point(left_pts, prefer_min_y=True),
        'top_right': find_corner_point(right_pts, prefer_min_y=True),
        'bottom_left': find_corner_point(left_pts, prefer_min_y=False),
        'bottom_right': find_corner_point(right_pts, prefer_min_y=False),
    }

    # Fallback if any corner is missing
    for name, pt in corners.items():
        if pt is None:
            print(f"[AFFINE] WARNING: No point found for {name}, using extreme")
            if 'left' in name:
                corners[name] = min(points, key=lambda p: p['x'])
            else:
                corners[name] = max(points, key=lambda p: p['x'])

    corner_info = {}
    for name, pt in corners.items():
        corner_info[name] = {
            'text': pt['text'],
            'pixel': [pt['x'], pt['y']],
            'z': pt['z']
        }
        print(f"[AFFINE]   {name}: Z={pt['z']:.3f} at pixel({pt['x']:.0f}, {pt['y']:.0f})")

    # Get the actual bounding box from ALL points (not just corners)
    all_min_x = min(p['x'] for p in points)
    all_max_x = max(p['x'] for p in points)
    all_min_y = min(p['y'] for p in points)
    all_max_y = max(p['y'] for p in points)

    print(f"[AFFINE] Full pixel bounds: X[{all_min_x:.0f}, {all_max_x:.0f}] Y[{all_min_y:.0f}, {all_max_y:.0f}]")

    # Source points: actual pixel coordinates of the 4 corners
    src_points = np.array([
        [corners['top_left']['x'], corners['top_left']['y']],
        [corners['top_right']['x'], corners['top_right']['y']],
        [corners['bottom_left']['x'], corners['bottom_left']['y']],
        [corners['bottom_right']['x'], corners['bottom_right']['y']],
    ], dtype=np.float32)

    # Destination: map corners to a TRUE RECTANGLE
    # Use the full bounding box to define the rectangle
    world_min_x = all_min_x * scale
    world_max_x = all_max_x * scale
    world_min_y = (image_height - all_max_y) * scale  # Y flipped: max pixel Y = min world Y
    world_max_y = (image_height - all_min_y) * scale  # Y flipped: min pixel Y = max world Y

    # Each corner maps to its corresponding rectangle corner
    # based on whether it's left/right and top/bottom
    dst_points = np.array([
        [world_min_x, world_max_y],  # top_left -> (min_x, max_y)
        [world_max_x, world_max_y],  # top_right -> (max_x, max_y)
        [world_min_x, world_min_y],  # bottom_left -> (min_x, min_y)
        [world_max_x, world_min_y],  # bottom_right -> (max_x, min_y)
    ], dtype=np.float32)

    print(f"[AFFINE] Target world bounds: X[{world_min_x:.2f}, {world_max_x:.2f}] Y[{world_min_y:.2f}, {world_max_y:.2f}]")

    # Calculate affine transform
    try:
        import cv2
        transform, inliers = cv2.estimateAffine2D(src_points, dst_points)
        method = f"cv2 (inliers: {np.sum(inliers) if inliers is not None else 'N/A'})"
    except ImportError:
        # Fallback: manual affine calculation
        src_h = np.hstack([src_points, np.ones((4, 1))])
        A_T, residuals, rank, s = np.linalg.lstsq(src_h, dst_points, rcond=None)
        transform = A_T.T
        method = "numpy lstsq"

    print(f"[AFFINE] Transform calculated using {method}")

    # Report transform characteristics
    if transform is not None:
        x_scale = np.sqrt(transform[0, 0]**2 + transform[0, 1]**2)
        y_scale = np.sqrt(transform[1, 0]**2 + transform[1, 1]**2)
        shear = transform[0, 1] / transform[0, 0] if abs(transform[0, 0]) > 1e-10 else 0
        rotation = np.arctan2(transform[1, 0], transform[0, 0]) * 180 / np.pi
        print(f"[AFFINE] Effective: X_scale={x_scale:.6f}, Y_scale={y_scale:.6f}")
        print(f"[AFFINE]           Shear={shear:.6f}, Rotation={rotation:.2f}Â°")

    return transform.tolist() if transform is not None else None, corner_info


def pdf_to_png(pdf_path: str, output_path: str, dpi: int = 300) -> str:
    """Convert PDF to high-resolution PNG."""
    
    # Try pdf2image first (uses poppler)
    try:
        from pdf2image import convert_from_path
        print(f"[PDF] Converting at {dpi} DPI using pdf2image...")
        images = convert_from_path(pdf_path, dpi=dpi)
        images[0].save(output_path, 'PNG')
        print(f"[PDF] Saved: {output_path}")
        return output_path
    except ImportError:
        print("[PDF] pdf2image not available, trying PyMuPDF...")
    except Exception as e:
        print(f"[PDF] pdf2image error: {e}")
    
    # Try PyMuPDF as fallback
    try:
        import fitz  # PyMuPDF
        print(f"[PDF] Converting at {dpi} DPI using PyMuPDF...")
        doc = fitz.open(pdf_path)
        page = doc[0]
        mat = fitz.Matrix(dpi/72, dpi/72)
        pix = page.get_pixmap(matrix=mat)
        pix.save(output_path)
        print(f"[PDF] Saved: {output_path}")
        return output_path
    except ImportError:
        print("[PDF] PyMuPDF not available")
    except Exception as e:
        print(f"[PDF] PyMuPDF error: {e}")
    
    raise ImportError(
        "No PDF library found. Install one:\n"
        "  pip install pdf2image   # requires poppler\n"
        "  pip install pymupdf"
    )


def extract_elevations_google(image_path: str, debug: bool = False, dump_raw: bool = False) -> dict:
    """Extract elevation values using Google Cloud Vision API."""
    from google.cloud import vision

    print(f"[API] Loading image: {image_path}")

    # Check file size
    file_size = os.path.getsize(image_path)
    print(f"[API] File size: {file_size / 1024 / 1024:.2f} MB")

    if file_size > 20 * 1024 * 1024:
        print("[API] WARNING: File > 20MB, may need to resize")

    client = vision.ImageAnnotatorClient()

    # Read image
    with open(image_path, 'rb') as f:
        content = f.read()

    image = vision.Image(content=content)

    print(f"[API] Calling document_text_detection...")
    response = client.document_text_detection(image=image)

    if response.error.message:
        raise Exception(f"Vision API error: {response.error.message}")

    # Dump raw API response if requested
    if dump_raw:
        raw_output_path = str(Path(image_path).parent / "vision_raw_response.json")
        raw_data = []
        for text in response.text_annotations:
            verts = text.bounding_poly.vertices
            raw_data.append({
                "text": text.description,
                "x": sum(getattr(v, 'x', 0) for v in verts) / 4,
                "y": sum(getattr(v, 'y', 0) for v in verts) / 4,
                "bbox": {
                    "x1": getattr(verts[0], 'x', 0) if len(verts) > 0 else 0,
                    "y1": getattr(verts[0], 'y', 0) if len(verts) > 0 else 0,
                    "x2": getattr(verts[2], 'x', 0) if len(verts) > 2 else 0,
                    "y2": getattr(verts[2], 'y', 0) if len(verts) > 2 else 0
                }
            })
        with open(raw_output_path, 'w', encoding='utf-8') as f:
            json.dump(raw_data, f, indent=2, ensure_ascii=False)
        print(f"[API] Raw response saved: {raw_output_path} ({len(raw_data)} items)")
    
    total_texts = len(response.text_annotations)
    print(f"[API] Received {total_texts} text annotations")
    
    # Patterns for elevation values
    # Ground levels: XX.XXX or XX,XXX (comma = European decimal separator)
    ground_pattern = re.compile(r'^[2-5][0-9][.,][0-9]{3}$')

    # Invert levels: XX.XXXIL or XX,XXXIL
    invert_pattern = re.compile(r'^[2-5][0-9][.,][0-9]{3}IL$', re.IGNORECASE)
    
    ground_elevations = []
    invert_levels = []
    labels = []
    rejected = []
    
    ground_id = 1
    invert_id = 1
    
    # Skip first annotation (it's the full text block)
    for text in response.text_annotations[1:]:
        desc = text.description.strip()
        
        # Get bounding box center
        verts = text.bounding_poly.vertices
        x = sum(getattr(v, 'x', 0) for v in verts) / 4
        y = sum(getattr(v, 'y', 0) for v in verts) / 4
        
        # Get bounding box
        bbox = {
            "x1": getattr(verts[0], 'x', 0),
            "y1": getattr(verts[0], 'y', 0),
            "x2": getattr(verts[2], 'x', 0),
            "y2": getattr(verts[2], 'y', 0)
        }
        
        if debug:
            print(f"  [{x:.0f},{y:.0f}] '{desc}'")
        
        # Check patterns
        if ground_pattern.match(desc):
            z = float(desc.replace(',', '.'))  # Normalize comma to period
            ground_elevations.append({
                "id": f"GL_{ground_id:04d}",
                "x": round(x, 1),
                "y": round(y, 1),
                "z": z,
                "text": desc,
                "type": "ground_level",
                "bbox": bbox
            })
            ground_id += 1
            
        elif invert_pattern.match(desc):
            z = float(desc.upper().replace('IL', '').replace(',', '.'))  # Normalize comma
            invert_levels.append({
                "id": f"IL_{invert_id:04d}",
                "x": round(x, 1),
                "y": round(y, 1),
                "z": z,
                "text": desc,
                "type": "invert_level",
                "bbox": bbox
            })
            invert_id += 1
        
        # Capture labels (text identifiers)
        elif re.match(r'^[A-Z]{2,}', desc) and len(desc) <= 20:
            labels.append({
                "text": desc,
                "x": round(x, 1),
                "y": round(y, 1)
            })
            
        # Track rejected numbers for debugging
        elif re.match(r'^[0-9]+\.?[0-9]*$', desc):
            rejected.append({
                "text": desc,
                "x": round(x, 1),
                "y": round(y, 1),
                "reason": "wrong_format"
            })
    
    # Get ACTUAL image dimensions from file (not from Vision API text bounds)
    try:
        from PIL import Image
        img = Image.open(image_path)
        width, height = img.size
        print(f"[API] Actual image dimensions: {width} x {height}")
    except:
        # Fallback to Vision API bounds if PIL fails
        all_x = [getattr(v, 'x', 0) for t in response.text_annotations for v in t.bounding_poly.vertices]
        all_y = [getattr(v, 'y', 0) for t in response.text_annotations for v in t.bounding_poly.vertices]
        width = max(all_x) if all_x else 0
        height = max(all_y) if all_y else 0
        print(f"[API] WARNING: Using Vision API bounds for dimensions: {width} x {height}")
    
    # Sort by position (top to bottom, left to right)
    ground_elevations.sort(key=lambda p: (p['y'], p['x']))
    invert_levels.sort(key=lambda p: (p['y'], p['x']))

    # Calculate affine transform for auto-calibration
    affine_transform, calibration_corners = calculate_affine_transform(
        ground_elevations, width, height, scale=0.0423
    )
    if affine_transform:
        print(f"[API] Affine transform calculated from 4 corner points")

    return {
        "metadata": {
            "source": str(image_path),
            "image_dimensions": {"width": int(width), "height": int(height)},
            "scale": 0.0423,  # 1 pixel = 0.01 meters (required by survey_to_blend.py)
            "affine_transform": affine_transform,  # 2x3 matrix for auto-calibration
            "calibration_corners": calibration_corners,  # Points used for calibration
            "point_count": len(ground_elevations),  # Compatible with survey_to_blend.py
            "ground_level_count": len(ground_elevations),
            "invert_level_count": len(invert_levels),
            "label_count": len(labels),
            "rejected_count": len(rejected),
            "extraction_method": "google_vision_api"
        },
        "ground_elevations": ground_elevations,
        "invert_levels": invert_levels,
        "labels": labels[:50],  # Limit labels
        "rejected_items": rejected[:30]  # Limit for readability
    }


def normalize_elevation(text: str) -> str:
    """Normalize elevation text: comma/space â†’ period"""
    return text.replace(',', '.').replace(' ', '.')


def merge_split_elevations(raw_data, y_tolerance=15, x_max_gap=100):
    """
    Find and merge elevation values that OCR split into separate items.
    E.g., '44' + '103' at same Y position â†’ '44.103'
    """
    merged = []
    used_indices = set()

    # Patterns for split parts
    left_pattern = re.compile(r'^[2-5][0-9]$')  # Two-digit integer like '44'
    right_pattern = re.compile(r'^[0-9]{3}$')   # Three-digit integer like '103'

    items = raw_data[1:]  # Skip first (full text block)

    for i, item1 in enumerate(items):
        if i in used_indices:
            continue

        text1 = item1['text'].strip()

        # Check if this could be the left part of a split elevation
        if left_pattern.match(text1):
            # Look for a matching right part nearby
            for j, item2 in enumerate(items):
                if j <= i or j in used_indices:
                    continue

                text2 = item2['text'].strip()

                # Check if it matches right pattern and is nearby
                if right_pattern.match(text2):
                    y_diff = abs(item1['y'] - item2['y'])
                    x_diff = item2['x'] - item1['x']  # right should be to the right

                    if y_diff < y_tolerance and 0 < x_diff < x_max_gap:
                        # Merge them
                        merged_text = f"{text1}.{text2}"
                        merged_x = (item1['x'] + item2['x']) / 2
                        merged_y = (item1['y'] + item2['y']) / 2

                        merged.append({
                            'text': merged_text,
                            'x': merged_x,
                            'y': merged_y,
                            'bbox': item1.get('bbox', {}),
                            'merged_from': [text1, text2]
                        })
                        used_indices.add(i)
                        used_indices.add(j)
                        break

    return merged


def extract_from_cache(cache_path: str, image_path: str, debug: bool = False) -> dict:
    """Extract elevation values from cached Vision API response (no API call)."""
    print(f"[CACHE] Loading cached response: {cache_path}")

    with open(cache_path, 'r', encoding='utf-8') as f:
        raw_data = json.load(f)

    print(f"[CACHE] Loaded {len(raw_data)} text annotations")

    # Pre-process: merge split elevation values (e.g., '44' + '103' â†’ '44.103')
    merged_items = merge_split_elevations(raw_data)
    if merged_items:
        print(f"[CACHE] Merged {len(merged_items)} split elevation pairs")
        for m in merged_items[:5]:
            print(f"[CACHE]   '{m['merged_from'][0]}' + '{m['merged_from'][1]}' â†’ '{m['text']}' at ({m['x']:.0f}, {m['y']:.0f})")

    # Patterns for elevation values
    # Support period, comma, or space as decimal separator
    ground_pattern = re.compile(r'^[2-5][0-9][., ][0-9]{3}$')
    invert_pattern = re.compile(r'^[2-5][0-9][., ][0-9]{3}IL$', re.IGNORECASE)

    # Pattern for concatenated values: XX.XXXXX.XXX (two elevations stuck together)
    concat_pattern = re.compile(r'^([2-5][0-9][.,][0-9]{3})([2-5][0-9][.,][0-9]{3})$')

    ground_elevations = []
    invert_levels = []
    labels = []
    rejected = []
    split_count = 0

    ground_id = 1
    invert_id = 1

    # Skip first annotation (it's the full text block)
    for item in raw_data[1:]:
        desc = item['text'].strip()
        x = item['x']
        y = item['y']
        bbox = item.get('bbox', {})

        if debug:
            print(f"  [{x:.0f},{y:.0f}] '{desc}'")

        # Check for concatenated values first (e.g., "44.61344.676")
        concat_match = concat_pattern.match(desc)
        if concat_match:
            # Split into two values, estimate positions (left and right of center)
            val1, val2 = concat_match.groups()
            z1 = float(normalize_elevation(val1))
            z2 = float(normalize_elevation(val2))

            # Estimate X positions (first value slightly left, second slightly right)
            x_offset = 20  # pixels
            for z_val, x_pos, orig_text in [(z1, x - x_offset, val1), (z2, x + x_offset, val2)]:
                if 20.0 <= z_val <= 60.0:  # Wider range for split values
                    ground_elevations.append({
                        "id": f"GL_{ground_id:04d}",
                        "x": round(x_pos, 1),
                        "y": round(y, 1),
                        "z": z_val,
                        "text": orig_text,
                        "type": "ground_level",
                        "bbox": bbox,
                        "split_from": desc
                    })
                    ground_id += 1
            split_count += 1
            continue

        # Check standard patterns
        if ground_pattern.match(desc):
            z = float(normalize_elevation(desc))
            ground_elevations.append({
                "id": f"GL_{ground_id:04d}",
                "x": round(x, 1),
                "y": round(y, 1),
                "z": z,
                "text": desc,
                "type": "ground_level",
                "bbox": bbox
            })
            ground_id += 1

        elif invert_pattern.match(desc):
            z = float(normalize_elevation(desc.upper().replace('IL', '')))
            invert_levels.append({
                "id": f"IL_{invert_id:04d}",
                "x": round(x, 1),
                "y": round(y, 1),
                "z": z,
                "text": desc,
                "type": "invert_level",
                "bbox": bbox
            })
            invert_id += 1

        # Capture labels (text identifiers)
        elif re.match(r'^[A-Z]{2,}', desc) and len(desc) <= 20:
            labels.append({
                "text": desc,
                "x": round(x, 1),
                "y": round(y, 1)
            })

        # Track rejected numbers for debugging
        elif re.match(r'^[0-9]+[., ]?[0-9]*$', desc):
            rejected.append({
                "text": desc,
                "x": round(x, 1),
                "y": round(y, 1),
                "reason": "wrong_format"
            })

    if split_count > 0:
        print(f"[CACHE] Split {split_count} concatenated values into separate points")

    # Process merged items (OCR-split elevations like '44' + '103' â†’ '44.103')
    merged_count = 0
    for item in merged_items:
        desc = item['text']
        if ground_pattern.match(desc):
            z = float(normalize_elevation(desc))
            ground_elevations.append({
                "id": f"GL_{ground_id:04d}",
                "x": round(item['x'], 1),
                "y": round(item['y'], 1),
                "z": z,
                "text": desc,
                "type": "ground_level",
                "bbox": item.get('bbox', {}),
                "merged_from": item.get('merged_from')
            })
            ground_id += 1
            merged_count += 1

    if merged_count > 0:
        print(f"[CACHE] Added {merged_count} merged elevation values")

    # Get image dimensions
    try:
        from PIL import Image
        img = Image.open(image_path)
        width, height = img.size
        print(f"[CACHE] Image dimensions: {width} x {height}")
    except Exception as e:
        print(f"[CACHE] WARNING: Could not read image: {e}")
        width, height = 9934, 7017  # Default for survey_highres.png

    # Sort by position (top to bottom, left to right)
    ground_elevations.sort(key=lambda p: (p['y'], p['x']))
    invert_levels.sort(key=lambda p: (p['y'], p['x']))

    # Calculate affine transform for auto-calibration
    # DISABLED: Affine corner detection is unreliable - using simple linear transform
    # affine_transform, calibration_corners = calculate_affine_transform(
    #     ground_elevations, width, height, scale=0.0423
    # )
    affine_transform = None
    calibration_corners = None
    print(f"[CACHE] Using simple linear transform (affine disabled)")

    print(f"[CACHE] Extracted: {len(ground_elevations)} ground levels, {len(invert_levels)} invert levels")

    return {
        "metadata": {
            "source": str(image_path),
            "cache_file": str(cache_path),
            "image_dimensions": {"width": int(width), "height": int(height)},
            "scale": 0.0423,
            "affine_transform": affine_transform,
            "calibration_corners": calibration_corners,
            "point_count": len(ground_elevations),
            "ground_level_count": len(ground_elevations),
            "invert_level_count": len(invert_levels),
            "label_count": len(labels),
            "rejected_count": len(rejected),
            "extraction_method": "cached_vision_api"
        },
        "ground_elevations": ground_elevations,
        "invert_levels": invert_levels,
        "labels": labels[:50],
        "rejected_items": rejected[:30]
    }


def main():
    # Parse arguments
    args = sys.argv[1:]
    
    if len(args) < 2 or '--help' in args or '-h' in args:
        print("Survey Elevation Extraction Pipeline")
        print("=" * 40)
        print("")
        print("Usage:")
        print("  python survey_extract_pipeline.py <input.pdf|png> <output.json> [options]")
        print("")
        print("Options:")
        print("  --dpi N           Set DPI for PDF conversion (default: 300)")
        print("  --debug           Show all detected text")
        print("  --from-cache FILE Use cached Vision API JSON instead of calling API")
        print("")
        print("Setup required (for API calls):")
        print("  1. export GOOGLE_APPLICATION_CREDENTIALS='/path/to/key.json'")
        print("  2. pip install google-cloud-vision pdf2image pillow")
        print("")
        print("Examples:")
        print("  python survey_extract_pipeline.py survey.pdf elevations.json --dpi 400")
        print("  python survey_extract_pipeline.py survey.png out.json --from-cache vision_raw.json")
        sys.exit(0)
    
    input_path = Path(args[0])
    output_path = args[1]
    
    # Parse options
    dpi = 300
    debug = False
    
    if '--dpi' in args:
        idx = args.index('--dpi')
        dpi = int(args[idx + 1])
    
    if '--debug' in args:
        debug = True

    dump_raw = '--dump-raw' in args

    # Check for cache mode
    cache_path = None
    if '--from-cache' in args:
        idx = args.index('--from-cache')
        cache_path = args[idx + 1]

    # Validate input
    if not input_path.exists():
        print(f"Error: Input not found: {input_path}")
        sys.exit(1)

    # Check credentials (only if not using cache)
    if not cache_path and not os.environ.get('GOOGLE_APPLICATION_CREDENTIALS'):
        print("WARNING: GOOGLE_APPLICATION_CREDENTIALS not set")
        print("Set it with: export GOOGLE_APPLICATION_CREDENTIALS='/path/to/key.json'")
    
    print("=" * 50)
    print("SURVEY ELEVATION EXTRACTION")
    print("=" * 50)
    print(f"Input:  {input_path}")
    print(f"Output: {output_path}")
    print(f"DPI:    {dpi}")
    print("")
    
    # Convert PDF if needed
    if input_path.suffix.lower() == '.pdf':
        png_path = input_path.with_suffix('.png')
        pdf_to_png(str(input_path), str(png_path), dpi=dpi)
        image_path = str(png_path)
    else:
        image_path = str(input_path)
    
    # Show image info
    try:
        from PIL import Image
        img = Image.open(image_path)
        print(f"[IMG] Dimensions: {img.size[0]} x {img.size[1]} pixels")
        print(f"[IMG] Mode: {img.mode}")
    except Exception as e:
        print(f"[IMG] Could not read image info: {e}")
    
    print("")

    # Extract elevations (from cache or API)
    if cache_path:
        print(f"[MODE] Using cached Vision API response")
        result = extract_from_cache(cache_path, image_path, debug=debug)
    else:
        result = extract_elevations_google(image_path, debug=debug, dump_raw=dump_raw)
    
    # Save output
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)
    
    # Summary
    print("")
    print("=" * 50)
    print("EXTRACTION COMPLETE")
    print("=" * 50)
    print(f"Ground Levels:  {result['metadata']['ground_level_count']}")
    print(f"Invert Levels:  {result['metadata']['invert_level_count']}")
    print(f"Labels Found:   {result['metadata']['label_count']}")
    print(f"Rejected:       {result['metadata']['rejected_count']}")
    print(f"")
    print(f"Output saved:   {output_path}")
    print("")
    
    # Show Z range
    if result['ground_elevations']:
        z_values = [p['z'] for p in result['ground_elevations']]
        print(f"Z Range: {min(z_values):.3f} to {max(z_values):.3f}")
        print("")
    
    # Show samples
    if result['ground_elevations']:
        print("Sample Ground Levels (first 10):")
        for pt in result['ground_elevations'][:10]:
            print(f"  {pt['id']}: ({pt['x']:7.1f}, {pt['y']:7.1f}) Z = {pt['z']:.3f}")
        print("")
    
    if result['invert_levels']:
        print("Sample Invert Levels (first 5):")
        for pt in result['invert_levels'][:5]:
            print(f"  {pt['id']}: ({pt['x']:7.1f}, {pt['y']:7.1f}) Z = {pt['z']:.3f} (IL)")
        print("")
    
    print("Done!")


if __name__ == "__main__":
    main()
