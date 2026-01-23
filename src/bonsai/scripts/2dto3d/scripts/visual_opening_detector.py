#!/usr/bin/env python3
"""
Visual Opening Detector - Places doors/windows based on visual analysis.

Uses calibration data + known positions from floor plan visual inspection.
Since Vision API cannot detect graphical symbols (door arcs, window lines),
this script defines expected opening positions based on typical placement patterns.
"""

import json
from pathlib import Path


def load_calibration(placements_path: str) -> dict:
    """Load calibration from existing placements.json."""
    with open(placements_path, 'r') as f:
        data = json.load(f)
    return data.get("metadata", {}).get("calibration", {})


def px_to_m(px_x: float, px_y: float, cal: dict) -> tuple:
    """Convert pixel coordinates to meters using calibration."""
    origin_px = cal.get("origin_px", 0)
    origin_py = cal.get("origin_py", 0)
    scale_x = cal.get("scale_x", 0.004)
    scale_y = cal.get("scale_y", 0.004)

    # Convert: meters = (pixel - origin) * scale
    x_m = (px_x - origin_px) * scale_x
    y_m = -(px_y - origin_py) * scale_y  # Flip Y (image Y down, world Y up then negative)

    return round(x_m, 3), round(y_m, 3)


def detect_external_openings(cal: dict) -> dict:
    """
    Detect external wall openings based on visual floor plan analysis.

    Returns doors and windows with positions on external walls.

    From visual inspection of TB-LKTN floor plan:
    - Building: 11.2m (W) x 8.5m (D)
    - Grid: A-E columns, 1-5 rows
    - Origin: Grid intersection A-1 (top-left of building)
    """

    width = cal.get("real_width", 11.2)
    depth = cal.get("real_height", 8.5)

    # Pixel positions observed from floor plan image
    # These are approximate centers of door arcs and window symbols

    # External doors
    external_doors = [
        {
            "id": "D1_1",
            "label": "D1",
            "description": "Main entrance door - front wall near porch",
            "pixel_pos": [420, 1950],  # Approximate from visual
            "wall": "FRONT",
            "swing": "left_in"
        },
        {
            "id": "D2_1",
            "label": "D2",
            "description": "Back door - rear wall at RUANG BASAH",
            "pixel_pos": [1400, 520],  # Approximate
            "wall": "BACK",
            "swing": "right_out"
        }
    ]

    # External windows (on external walls only)
    external_windows = [
        # FRONT WALL (Y = -depth)
        {
            "id": "W1_1",
            "label": "W1",
            "description": "Front window - RUANG TAMU",
            "pixel_pos": [900, 1970],
            "wall": "FRONT"
        },
        {
            "id": "W2_1",
            "label": "W2",
            "description": "Front window - BILIK 1",
            "pixel_pos": [1800, 1970],
            "wall": "FRONT"
        },

        # LEFT WALL (X = 0)
        {
            "id": "W1_2",
            "label": "W1",
            "description": "Left window - BILIK UTAMA",
            "pixel_pos": [210, 1200],
            "wall": "LEFT"
        },
        {
            "id": "W3_1",
            "label": "W3",
            "description": "Left window - BILIK MANDI (tophung)",
            "pixel_pos": [210, 900],
            "wall": "LEFT"
        },

        # RIGHT WALL (X = width)
        {
            "id": "W2_2",
            "label": "W2",
            "description": "Right window - BILIK 1",
            "pixel_pos": [2700, 1500],
            "wall": "RIGHT"
        },
        {
            "id": "W2_3",
            "label": "W2",
            "description": "Right window - BILIK 2",
            "pixel_pos": [2700, 1000],
            "wall": "RIGHT"
        },

        # BACK WALL (Y = 0)
        {
            "id": "W2_4",
            "label": "W2",
            "description": "Back window - DAPUR",
            "pixel_pos": [2200, 520],
            "wall": "BACK"
        }
    ]

    # Convert pixel positions to meters
    doors = []
    for d in external_doors:
        px_x, px_y = d["pixel_pos"]
        x_m, y_m = px_to_m(px_x, px_y, cal)

        # Snap to external wall
        if d["wall"] == "FRONT":
            y_m = -depth
        elif d["wall"] == "BACK":
            y_m = 0
        elif d["wall"] == "LEFT":
            x_m = 0
        elif d["wall"] == "RIGHT":
            x_m = width

        doors.append({
            "id": d["id"],
            "label": d["label"],
            "description": d["description"],
            "position_m": [x_m, y_m, 0.0],
            "pixel_pos": d["pixel_pos"],
            "wall": d["wall"],
            "swing": d.get("swing", "left_in")
        })

    windows = []
    for w in external_windows:
        px_x, px_y = w["pixel_pos"]
        x_m, y_m = px_to_m(px_x, px_y, cal)

        # Snap to external wall
        if w["wall"] == "FRONT":
            y_m = -depth
        elif w["wall"] == "BACK":
            y_m = 0
        elif w["wall"] == "LEFT":
            x_m = 0
        elif w["wall"] == "RIGHT":
            x_m = width

        windows.append({
            "id": w["id"],
            "label": w["label"],
            "description": w["description"],
            "position_m": [x_m, y_m, 0.9],  # Sill height
            "pixel_pos": w["pixel_pos"],
            "wall": w["wall"]
        })

    return {
        "doors": doors,
        "windows": windows,
        "summary": {
            "external_doors": len(doors),
            "external_windows": len(windows),
            "building_size": f"{width}m x {depth}m"
        }
    }


def main():
    """CLI entry point."""
    import sys

    base_dir = Path(__file__).parent.parent
    placements_path = base_dir / "OUTPUT" / "placements.json"

    if not placements_path.exists():
        print(f"ERROR: Placements file not found: {placements_path}")
        print("Run calibration first to create placements.json")
        sys.exit(1)

    print("=" * 50)
    print("Visual Opening Detector")
    print("=" * 50)

    cal = load_calibration(placements_path)
    print(f"Calibration: {cal['real_width']}m x {cal['real_height']}m")
    print(f"Scale: {cal['scale_x']:.6f} m/px (X), {cal['scale_y']:.6f} m/px (Y)")
    print()

    result = detect_external_openings(cal)

    print("EXTERNAL DOORS:")
    for d in result["doors"]:
        pos = d["position_m"]
        print(f"  {d['id']}: {d['label']} at ({pos[0]:.2f}, {pos[1]:.2f})m - {d['wall']} wall")
        print(f"         {d['description']}")

    print()
    print("EXTERNAL WINDOWS:")
    for w in result["windows"]:
        pos = w["position_m"]
        print(f"  {w['id']}: {w['label']} at ({pos[0]:.2f}, {pos[1]:.2f})m - {w['wall']} wall")
        print(f"         {w['description']}")

    print()
    print(f"Summary: {result['summary']['external_doors']} doors, {result['summary']['external_windows']} windows")

    # Save result
    output_path = base_dir / "OUTPUT" / "external_openings.json"
    with open(output_path, 'w') as f:
        json.dump(result, f, indent=2)
    print(f"\nSaved to: {output_path}")


if __name__ == "__main__":
    main()
