#!/usr/bin/env python3
"""
Schedule Parser - Extract door/window specs from schedule page.
Parses Vision API output to build door/window specifications.
"""

import json
import re
from pathlib import Path
from collections import defaultdict


def parse_schedule(raw_json_path: str) -> dict:
    """
    Parse schedule page to extract door/window specifications.

    Returns dict with:
        doors: {D1: {width_mm, height_mm, type, ...}, ...}
        windows: {W1: {width_mm, height_mm, type, ...}, ...}
    """
    with open(raw_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    items = data.get("text_items", [])

    # Group items by approximate Y position (rows)
    rows = defaultdict(list)
    for item in items:
        row_key = round(item["y"] / 30) * 30  # 30px row tolerance
        rows[row_key].append(item)

    # Sort items in each row by X position
    for row_key in rows:
        rows[row_key].sort(key=lambda x: x["x"])

    # Find door and window labels
    door_labels = {}
    window_labels = {}

    for item in items:
        text = item["text"].upper().strip()
        if re.match(r'^D[1-9]$', text):
            door_labels[text] = {"x": item["x"], "y": item["y"]}
        elif re.match(r'^W[1-9]$', text):
            window_labels[text] = {"x": item["x"], "y": item["y"]}

    print(f"Found door labels: {list(door_labels.keys())}")
    print(f"Found window labels: {list(window_labels.keys())}")

    # Find dimensions near each label
    # Look for numbers like 900, 2100, 1800, etc. in same column
    doors = {}
    windows = {}

    # Standard Malaysian door/window specs (fallback defaults)
    default_doors = {
        "D1": {"width_mm": 900, "height_mm": 2100, "type": "single", "material": "metal_frame"},
        "D2": {"width_mm": 900, "height_mm": 2100, "type": "single", "material": "metal_frame"},
        "D3": {"width_mm": 750, "height_mm": 2100, "type": "louvre", "material": "timber"}
    }

    default_windows = {
        "W1": {"width_mm": 1800, "height_mm": 1000, "sill_mm": 900, "type": "3panel", "material": "aluminum"},
        "W2": {"width_mm": 1200, "height_mm": 1000, "sill_mm": 900, "type": "2panel", "material": "aluminum"},
        "W3": {"width_mm": 600, "height_mm": 500, "sill_mm": 1500, "type": "tophung", "material": "aluminum"}
    }

    # Try to extract dimensions from schedule
    for label, pos in door_labels.items():
        col_x = pos["x"]
        # Look for numbers in same column (within 100px)
        col_numbers = []
        for item in items:
            if abs(item["x"] - col_x) < 100:
                try:
                    num = int(item["text"])
                    if 500 <= num <= 3000:  # Reasonable dimension range
                        col_numbers.append((item["y"], num))
                except ValueError:
                    pass

        # Sort by Y to get dimension order
        col_numbers.sort(key=lambda x: x[0])

        if label in default_doors:
            doors[label] = default_doors[label].copy()
            # Override with extracted values if found
            if len(col_numbers) >= 1:
                doors[label]["width_mm"] = col_numbers[0][1]
            if len(col_numbers) >= 2:
                doors[label]["height_mm"] = col_numbers[1][1]

    for label, pos in window_labels.items():
        col_x = pos["x"]
        col_numbers = []
        for item in items:
            if abs(item["x"] - col_x) < 100:
                try:
                    num = int(item["text"])
                    if 400 <= num <= 3000:
                        col_numbers.append((item["y"], num))
                except ValueError:
                    pass

        col_numbers.sort(key=lambda x: x[0])

        if label in default_windows:
            windows[label] = default_windows[label].copy()
            if len(col_numbers) >= 1:
                windows[label]["width_mm"] = col_numbers[0][1]
            if len(col_numbers) >= 2:
                windows[label]["height_mm"] = col_numbers[1][1]

    # If no labels found on schedule, use defaults
    if not doors:
        doors = default_doors
        print("Using default door specs (labels not found)")
    if not windows:
        windows = default_windows
        print("Using default window specs (labels not found)")

    result = {
        "doors": doors,
        "windows": windows,
        "source": str(raw_json_path)
    }

    return result


def count_openings_on_floorplan(floorplan_json_path: str) -> dict:
    """
    Count door and window instances on floor plan.
    Returns count of each type found.
    """
    with open(floorplan_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    items = data.get("text_items", [])

    counts = defaultdict(int)
    positions = defaultdict(list)

    for item in items:
        text = item["text"].upper().strip()
        if re.match(r'^D[1-9]$', text):
            counts[text] += 1
            positions[text].append({"x": item["x"], "y": item["y"]})
        elif re.match(r'^W[1-9]$', text):
            counts[text] += 1
            positions[text].append({"x": item["x"], "y": item["y"]})

    return {"counts": dict(counts), "positions": dict(positions)}


def main():
    """CLI entry point."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python schedule_parser.py <schedule_raw.json> [floorplan_raw.json]")
        print("")
        print("Examples:")
        print("  python schedule_parser.py page8_raw.json")
        print("  python schedule_parser.py page8_raw.json page1_raw.json")
        sys.exit(1)

    schedule_path = sys.argv[1]

    print("=" * 50)
    print("Parsing schedule...")
    print("=" * 50)

    specs = parse_schedule(schedule_path)

    print("\nDOORS:")
    for label, spec in specs["doors"].items():
        print(f"  {label}: {spec['width_mm']}x{spec['height_mm']}mm ({spec['type']})")

    print("\nWINDOWS:")
    for label, spec in specs["windows"].items():
        sill = spec.get('sill_mm', 900)
        print(f"  {label}: {spec['width_mm']}x{spec['height_mm']}mm, sill {sill}mm ({spec['type']})")

    # If floor plan provided, count instances
    if len(sys.argv) > 2:
        floorplan_path = sys.argv[2]
        print("\n" + "=" * 50)
        print("Counting on floor plan...")
        print("=" * 50)

        counts = count_openings_on_floorplan(floorplan_path)

        print("\nDOOR INSTANCES:")
        for label in sorted(counts["counts"].keys()):
            if label.startswith("D"):
                print(f"  {label}: {counts['counts'][label]} found")

        print("\nWINDOW INSTANCES:")
        for label in sorted(counts["counts"].keys()):
            if label.startswith("W"):
                print(f"  {label}: {counts['counts'][label]} found")

    # Save specs to output
    output_path = Path(schedule_path).parent.parent / "OUTPUT" / "opening_specs.json"
    output_path.parent.mkdir(exist_ok=True)

    with open(output_path, 'w') as f:
        json.dump(specs, f, indent=2)

    print(f"\nSaved specs to: {output_path}")


if __name__ == "__main__":
    main()
