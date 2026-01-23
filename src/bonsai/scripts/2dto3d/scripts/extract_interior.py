#!/usr/bin/env python3
"""
Extract interior walls and doors from grid system and room positions.
Uses the grid spacing to determine wall positions.
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "OUTPUT"

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def extract_interior():
    master = load_json(OUTPUT_DIR / "master_template_filled.json")
    house = load_json(OUTPUT_DIR / "house_template_filled.json")

    grid = master["grid_system"]
    cal = house["calibration"]
    width = cal["building_width_m"]
    depth = cal["building_depth_m"]

    # Grid column positions (X axis, from left)
    col_spacing = grid["columns"]["spacing_mm"]
    col_labels = grid["columns"]["labels"]
    col_x = [0]
    x = 0
    for sp in col_spacing:
        x += sp / 1000
        col_x.append(x)

    print("Grid columns (X positions in m):")
    for i, label in enumerate(col_labels):
        print(f"  {label}: X = {col_x[i]:.3f}m")
    print(f"  (right edge): X = {col_x[-1]:.3f}m")

    # Grid row positions (Y axis, from back toward front)
    row_spacing = grid["rows"]["spacing_mm"]
    row_labels = grid["rows"]["labels"]
    row_y = [0]
    y = 0
    for sp in row_spacing:
        y -= sp / 1000  # negative Y toward front
        row_y.append(y)

    print("\nGrid rows (Y positions in m):")
    for i, label in enumerate(row_labels):
        print(f"  Row {label}: Y = {row_y[i]:.3f}m")
    print(f"  (front edge): Y = {row_y[-1]:.3f}m")

    # Interior walls based on grid
    # Vertical walls (along X grid lines, running Y direction)
    # Horizontal walls (along Y grid lines, running X direction)

    interior_walls = []
    wall_thickness = 0.1  # 100mm interior walls
    wall_height = 3.0

    # Analyze room positions to determine which grid lines have walls
    rooms = master["rooms"]["list"]
    print("\nRoom positions (meters):")

    ox, oy = cal["origin_px"]
    sx = cal["scale_x_m_per_px"]
    sy = cal["scale_y_m_per_px"]

    room_positions = []
    for room in rooms:
        px, py = room["position_px"]
        x_m = (px - ox) * sx
        y_m = -(py - oy) * sy
        room_positions.append({
            "name": room["name_malay"],
            "x_m": round(x_m, 3),
            "y_m": round(y_m, 3)
        })
        print(f"  {room['name_malay']}: ({x_m:.3f}, {y_m:.3f})")

    # Based on actual floor plan layout:
    # - Back left: BILIK MANDI + RUANG BASAH (small rooms)
    # - Back center: DAPUR (kitchen)
    # - Back right: BILIK 1
    # - Middle left: BILIK UTAMA (master bedroom)
    # - Middle center: RUANG MAKAN (dining) / RUANG TAMU (living)
    # - Middle right: BILIK 2
    # - Front center: ANJUNG (porch)

    # Vertical wall B (X=1.3m) - BILIK UTAMA east wall, from row 5 to row 4
    interior_walls.append({
        "name": "INT_WALL_B_UPPER",
        "type": "wall",
        "start_point": [col_x[1], row_y[1]],  # from row 5
        "end_point": [col_x[1], row_y[3]],    # to row 4
        "thickness": wall_thickness,
        "height": wall_height,
        "is_interior": True
    })

    # Vertical wall D (X=8.1m) - BILIK 1/2 west wall, from back to row 4
    interior_walls.append({
        "name": "INT_WALL_D",
        "type": "wall",
        "start_point": [col_x[3], 0],         # from back
        "end_point": [col_x[3], row_y[3]],    # to row 4
        "thickness": wall_thickness,
        "height": wall_height,
        "is_interior": True
    })

    # Horizontal wall row 5 (Y=-1.5m) - separates back rooms from middle
    # From left wall to grid D
    interior_walls.append({
        "name": "INT_WALL_ROW5",
        "type": "wall",
        "start_point": [0, row_y[1]],
        "end_point": [col_x[3], row_y[1]],
        "thickness": wall_thickness,
        "height": wall_height,
        "is_interior": True
    })

    # Horizontal wall row 3 (Y=-3.3m) - corridor north wall
    # Partial wall from B to D (corridor area)
    interior_walls.append({
        "name": "INT_WALL_ROW3",
        "type": "wall",
        "start_point": [col_x[1], row_y[2]],
        "end_point": [col_x[3], row_y[2]],
        "thickness": wall_thickness,
        "height": wall_height,
        "is_interior": True
    })

    # Horizontal wall row 4 (Y=-6.4m) - corridor south wall / front rooms
    interior_walls.append({
        "name": "INT_WALL_ROW4",
        "type": "wall",
        "start_point": [0, row_y[3]],
        "end_point": [width, row_y[3]],
        "thickness": wall_thickness,
        "height": wall_height,
        "is_interior": True
    })

    # Wall between BILIK MANDI and RUANG BASAH (partial wall at back-left)
    # Approximate position based on grid
    interior_walls.append({
        "name": "INT_WALL_BATH",
        "type": "wall",
        "start_point": [col_x[1], 0],         # from back wall
        "end_point": [col_x[1], row_y[1]],    # to row 5
        "thickness": wall_thickness,
        "height": wall_height,
        "is_interior": True
    })

    # Wall between BILIK 1 and BILIK 2 (horizontal at row 3 on right side)
    interior_walls.append({
        "name": "INT_WALL_BILIK12",
        "type": "wall",
        "start_point": [col_x[3], row_y[2]],
        "end_point": [width, row_y[2]],
        "thickness": wall_thickness,
        "height": wall_height,
        "is_interior": True
    })

    # Interior doors - placed at room boundaries based on floor plan
    interior_doors = []

    # Door from corridor to BILIK UTAMA (on wall B, between row 3 and row 4)
    interior_doors.append({
        "name": "D2_BILIK_UTAMA",
        "type": "door",
        "position": [col_x[1], (row_y[2] + row_y[3]) / 2, 0],
        "width": 0.9,
        "height": 2.1,
        "host_wall": "INT_WALL_B_UPPER",
        "is_interior": True
    })

    # Door from corridor to BILIK 2 (on wall D, between row 3 and row 4)
    interior_doors.append({
        "name": "D2_BILIK_2",
        "type": "door",
        "position": [col_x[3], (row_y[2] + row_y[3]) / 2, 0],
        "width": 0.9,
        "height": 2.1,
        "host_wall": "INT_WALL_D",
        "is_interior": True
    })

    # Door from corridor to BILIK 1 (on wall D, between row 5 and row 3)
    interior_doors.append({
        "name": "D2_BILIK_1",
        "type": "door",
        "position": [col_x[3], (row_y[1] + row_y[2]) / 2, 0],
        "width": 0.9,
        "height": 2.1,
        "host_wall": "INT_WALL_D",
        "is_interior": True
    })

    # Door to BILIK MANDI (bathroom) - louvre door D3
    interior_doors.append({
        "name": "D3_BILIK_MANDI",
        "type": "door",
        "position": [col_x[1] / 2, row_y[1], 0],
        "width": 0.75,
        "height": 2.1,
        "host_wall": "INT_WALL_ROW5",
        "is_interior": True
    })

    # Door to DAPUR (kitchen) from dining area
    interior_doors.append({
        "name": "D2_DAPUR",
        "type": "door",
        "position": [(col_x[1] + col_x[3]) / 2, row_y[1], 0],
        "width": 0.9,
        "height": 2.1,
        "host_wall": "INT_WALL_ROW5",
        "is_interior": True
    })

    output = {
        "grid_analysis": {
            "columns": {label: col_x[i] for i, label in enumerate(col_labels)},
            "rows": {label: row_y[i] for i, label in enumerate(row_labels)},
            "column_edge": col_x[-1],
            "row_edge": row_y[-1]
        },
        "room_positions_m": room_positions,
        "interior_walls": interior_walls,
        "interior_doors": interior_doors
    }

    output_path = OUTPUT_DIR / "interior_extraction.json"
    save_json(output, output_path)
    print(f"\nSaved: {output_path}")
    print(f"Interior walls: {len(interior_walls)}")
    print(f"Interior doors: {len(interior_doors)}")

    return output

if __name__ == "__main__":
    extract_interior()
