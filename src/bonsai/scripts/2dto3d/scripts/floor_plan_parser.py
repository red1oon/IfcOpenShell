#!/usr/bin/env python3
"""
Floor Plan Parser - Step 3 of 2D-to-3D Pipeline

Parses Vision API extraction to identify doors, windows, grid labels.
Calibrates scale from grid and transforms pixel coords to world coords.

CRITICAL BUG FIXES APPLIED:
1. Y-axis flip (image Y=0 at top, Blender Y=0 at bottom)
2. Decimal separator handling (accept both . and ,)
"""

import sys
import json
import re
from pathlib import Path


# Regex patterns for floor plan elements
PATTERNS = {
    "doors": re.compile(r'^D[1-9]$'),
    "windows": re.compile(r'^W[1-9]$'),
    "grid_cols": re.compile(r'^[A-E]$'),
    "grid_rows": re.compile(r'^[1-5]$'),
    "rooms": re.compile(r'^(BILIK|DAPUR|TANDAS|RUANG|CORRIDOR|TAMU|MANDI|UTAMA)', re.IGNORECASE),
    "fan_points": re.compile(r'^FP[1-9]?$'),
    "switches": re.compile(r'^SWS$'),
    "gutters": re.compile(r'^G[1-9][0-9]?$'),
    "dimensions": re.compile(r'^\d+\s*[xX×]\s*\d+$'),
}


def parse_extraction(extraction: dict) -> dict:
    """
    Parse Vision API extraction into categorized objects.

    Args:
        extraction: Output from vision_extract.py

    Returns:
        Categorized objects with pixel positions
    """
    result = {key: [] for key in PATTERNS}
    result["metadata"] = extraction["metadata"]
    result["unmatched"] = []

    for item in extraction["text_items"]:
        text = item["text"].strip()
        matched = False

        for category, pattern in PATTERNS.items():
            if pattern.match(text):
                result[category].append({
                    "label": text,
                    "px": item["x"],
                    "py": item["y"]
                })
                matched = True
                break

        if not matched:
            result["unmatched"].append({
                "text": text,
                "px": item["x"],
                "py": item["y"]
            })

    # Print summary
    print("=" * 50)
    print("PARSING SUMMARY")
    print("=" * 50)
    for category in PATTERNS:
        count = len(result[category])
        if count > 0:
            print(f"  {category}: {count}")
    print(f"  unmatched: {len(result['unmatched'])}")
    print("=" * 50)

    return result


def calibrate_scale(parsed: dict, building_config: dict) -> dict:
    """
    Calculate scale using grid labels.

    Args:
        parsed: Output from parse_extraction()
        building_config: Manual input with real dimensions (grid_width_m, grid_height_m)

    Returns:
        Calibration data with scale factors and origin
    """
    # Sort grid labels by position
    cols = sorted(parsed["grid_cols"], key=lambda x: x["px"])
    rows = sorted(parsed["grid_rows"], key=lambda x: x["py"])

    if len(cols) < 2:
        raise ValueError(f"Need at least 2 column grid labels, found {len(cols)}")
    if len(rows) < 2:
        raise ValueError(f"Need at least 2 row grid labels, found {len(rows)}")

    # Pixel spans (from first to last grid label)
    px_width = cols[-1]["px"] - cols[0]["px"]
    px_height = rows[-1]["py"] - rows[0]["py"]

    # Real dimensions from config
    real_width = building_config["grid_width_m"]
    real_height = building_config["grid_height_m"]

    # Calculate scales
    scale_x = real_width / px_width if px_width > 0 else 0
    scale_y = real_height / px_height if px_height > 0 else 0

    # Origin = first grid intersection (A, 1)
    origin_px = cols[0]["px"]
    origin_py = rows[0]["py"]

    calibration = {
        "scale_x": scale_x,
        "scale_y": scale_y,
        "origin_px": origin_px,
        "origin_py": origin_py,
        "image_width": parsed["metadata"]["image_dimensions"]["width"],
        "image_height": parsed["metadata"]["image_dimensions"]["height"],
        "grid_cols": [c["label"] for c in cols],
        "grid_rows": [r["label"] for r in rows],
        "px_width": px_width,
        "px_height": px_height,
        "real_width": real_width,
        "real_height": real_height
    }

    print("")
    print("SCALE CALIBRATION")
    print("=" * 50)
    print(f"  Grid columns: {calibration['grid_cols']} ({len(cols)} found)")
    print(f"  Grid rows: {calibration['grid_rows']} ({len(rows)} found)")
    print(f"  Pixel span: {px_width:.0f} x {px_height:.0f}")
    print(f"  Real size: {real_width} x {real_height} m")
    print(f"  Scale X: {scale_x:.6f} m/px")
    print(f"  Scale Y: {scale_y:.6f} m/px")
    print(f"  Origin: ({origin_px:.0f}, {origin_py:.0f}) px")
    print("=" * 50)

    return calibration


def pixel_to_world(px: float, py: float, calibration: dict) -> tuple:
    """
    Convert pixel coordinates to world coordinates.

    CRITICAL: Y-axis is flipped!
    - Image: Y=0 at TOP, increases downward
    - Blender: Y=0 at BOTTOM, increases upward
    """
    # Offset from origin
    dx = px - calibration["origin_px"]
    dy = py - calibration["origin_py"]

    # Scale to meters
    x = dx * calibration["scale_x"]

    # FLIP Y-AXIS (critical bug fix!)
    # Positive dy in image = downward = negative y in world
    y = -dy * calibration["scale_y"]

    return (round(x, 3), round(y, 3))


def generate_placements(parsed: dict, calibration: dict, object_map: dict = None) -> dict:
    """
    Generate 3D placements from parsed floor plan.

    Args:
        parsed: Categorized extractions
        calibration: Scale and origin data
        object_map: Label to library object mapping (optional)

    Returns:
        Placements dictionary ready for Blender import
    """
    placements = {
        "metadata": {
            "source": parsed["metadata"]["source"],
            "calibration": calibration
        },
        "doors": [],
        "windows": [],
        "fixtures": []
    }

    # Process doors
    for door in parsed["doors"]:
        x, y = pixel_to_world(door["px"], door["py"], calibration)
        placement = {
            "name": f"{door['label']}_x{int(x*100)}_y{int(y*100)}",
            "label": door["label"],
            "position": [x, y, 0.0],
            "pixel_pos": [door["px"], door["py"]]
        }
        if object_map and "doors" in object_map:
            placement["object_type"] = object_map["doors"].get(door["label"], "door_generic")
        placements["doors"].append(placement)

    # Process windows
    for window in parsed["windows"]:
        x, y = pixel_to_world(window["px"], window["py"], calibration)
        placement = {
            "name": f"{window['label']}_x{int(x*100)}_y{int(y*100)}",
            "label": window["label"],
            "position": [x, y, 1.0],  # Sill height
            "pixel_pos": [window["px"], window["py"]]
        }
        if object_map and "windows" in object_map:
            placement["object_type"] = object_map["windows"].get(window["label"], "window_generic")
        placements["windows"].append(placement)

    # Process fixtures (fan points, switches, etc.)
    for fp in parsed["fan_points"]:
        x, y = pixel_to_world(fp["px"], fp["py"], calibration)
        placements["fixtures"].append({
            "name": f"FanPoint_{fp['label']}_x{int(x*100)}_y{int(y*100)}",
            "label": fp["label"],
            "type": "fan_point",
            "position": [x, y, 3.0],  # Ceiling height
            "pixel_pos": [fp["px"], fp["py"]]
        })

    for sw in parsed["switches"]:
        x, y = pixel_to_world(sw["px"], sw["py"], calibration)
        placements["fixtures"].append({
            "name": f"Switch_{sw['label']}_x{int(x*100)}_y{int(y*100)}",
            "label": sw["label"],
            "type": "switch",
            "position": [x, y, 1.2],  # Switch height
            "pixel_pos": [sw["px"], sw["py"]]
        })

    # Summary
    print("")
    print("PLACEMENTS GENERATED")
    print("=" * 50)
    print(f"  Doors: {len(placements['doors'])}")
    print(f"  Windows: {len(placements['windows'])}")
    print(f"  Fixtures: {len(placements['fixtures'])}")
    print("=" * 50)

    return placements


def process_floor_plan(extraction_path: str, config_path: str, object_map_path: str = None, output_path: str = None) -> dict:
    """
    Full pipeline: Load extraction -> Parse -> Calibrate -> Generate placements.

    Args:
        extraction_path: Path to Vision API extraction JSON (raw.json)
        config_path: Path to building_config.json
        object_map_path: Path to object_library_map.json (optional)
        output_path: Path for output placements JSON (optional)

    Returns:
        Placements dictionary
    """
    # Load files
    with open(extraction_path, 'r', encoding='utf-8') as f:
        extraction = json.load(f)

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    object_map = None
    if object_map_path:
        with open(object_map_path, 'r', encoding='utf-8') as f:
            object_map = json.load(f)

    # Process
    parsed = parse_extraction(extraction)
    calibration = calibrate_scale(parsed, config)
    placements = generate_placements(parsed, calibration, object_map)

    # Save output
    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(placements, f, indent=2)
        print(f"\nSaved to: {output_path}")

    return placements


def main():
    """CLI entry point."""
    if len(sys.argv) < 3:
        print("Usage: python floor_plan_parser.py <extraction.json> <building_config.json> [object_map.json] [output.json]")
        print("")
        print("Example:")
        print("  python floor_plan_parser.py ../CACHE/page1_raw.json ../config/building_config.json ../config/object_library_map.json ../OUTPUT/placements.json")
        sys.exit(1)

    extraction_path = sys.argv[1]
    config_path = sys.argv[2]
    object_map_path = sys.argv[3] if len(sys.argv) > 3 else None
    output_path = sys.argv[4] if len(sys.argv) > 4 else None

    process_floor_plan(extraction_path, config_path, object_map_path, output_path)


if __name__ == "__main__":
    main()
