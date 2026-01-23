import json
from pathlib import Path

BASE_DIR = Path(__file__).parent
CONFIG_DIR = BASE_DIR / "config"
OUTPUT_DIR = BASE_DIR / "OUTPUT"

LIBRARY_OBJECTS = {
    "D1": "door_single_900_lod300",
    "D2": "door_single_900_lod300",
    "D3": "door_louvre_750_lod300",
    "W1": "window_aluminum_3panel_1800x1000",
    "W2": "window_aluminum_2panel_1200x1000",
    "W3": "window_aluminum_tophung_600x500"
}

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def run_staged_extraction():
    print("Loading filled template...")
    template = load_json(OUTPUT_DIR / "house_template_filled.json")

    cal = template["calibration"]
    width = cal["building_width_m"]
    depth = cal["building_depth_m"]

    elements = template["house_elements"]

    output = {
        "metadata": {
            "pipeline": "staged_extraction_v2",
            "source": "house_template_filled.json",
            "building_width_m": width,
            "building_depth_m": depth
        },
        "placements": []
    }

    print("Stage 1: Outside drain...")
    if elements["outside_drain"]["exists"]:
        offset = elements["outside_drain"]["offset_from_wall_mm"] / 1000
        output["placements"].extend([
            {"name": "DRAIN_FRONT", "type": "drain", "start_point": [-offset, -depth-offset, 0], "end_point": [width+offset, -depth-offset, 0]},
            {"name": "DRAIN_BACK", "type": "drain", "start_point": [-offset, offset, 0], "end_point": [width+offset, offset, 0]},
            {"name": "DRAIN_LEFT", "type": "drain", "start_point": [-offset, offset, 0], "end_point": [-offset, -depth-offset, 0]},
            {"name": "DRAIN_RIGHT", "type": "drain", "start_point": [width+offset, offset, 0], "end_point": [width+offset, -depth-offset, 0]}
        ])
        print(f"  4 drain segments at {offset}m offset")

    print("Stage 2: Outer walls...")
    corners = elements["outer_walls"]["corners_m"]
    thick = elements["outer_walls"]["thickness_mm"] / 1000
    height = elements["outer_walls"]["height_mm"] / 1000
    output["placements"].extend([
        {"name": "EXT_WALL_FRONT", "type": "wall", "start_point": corners["A5"], "end_point": corners["E5"], "thickness": thick, "height": height},
        {"name": "EXT_WALL_BACK", "type": "wall", "start_point": corners["A1"], "end_point": corners["E1"], "thickness": thick, "height": height},
        {"name": "EXT_WALL_LEFT", "type": "wall", "start_point": corners["A1"], "end_point": corners["A5"], "thickness": thick, "height": height},
        {"name": "EXT_WALL_RIGHT", "type": "wall", "start_point": corners["E1"], "end_point": corners["E5"], "thickness": thick, "height": height}
    ])
    print(f"  4 walls {width}m x {depth}m x {height}m")

    print("Stage 3: Main door...")
    door = elements["main_door"]
    pos = door["position_m"]
    output["placements"].append({
        "name": "D1_main",
        "type": "door",
        "position": pos,
        "width": door["width_mm"] / 1000,
        "height": door["height_mm"] / 1000,
        "host_wall": "EXT_WALL_FRONT",
        "object_type": LIBRARY_OBJECTS[door["label"]]
    })
    print(f"  D1 at X={pos[0]}m on front wall")

    print("Stage 4: Outer windows...")
    win_count = 0
    for wtype, wdata in elements["outer_windows"]["types"].items():
        for inst in wdata["instances"]:
            win_count += 1
            sill = wdata.get("sill_mm", 900) / 1000
            pos = inst["position_m"]
            pos[2] = sill
            output["placements"].append({
                "name": f"{wtype}_{inst['room']}",
                "type": "window",
                "position": pos,
                "width": wdata["width_mm"] / 1000,
                "height": wdata["height_mm"] / 1000,
                "sill_height": sill,
                "host_wall": f"EXT_WALL_{inst['wall']}",
                "object_type": LIBRARY_OBJECTS[wtype]
            })
            print(f"  {wtype} at {inst['room']}: {pos}")
    print(f"  {win_count} windows total")

    print("Stage 5: Roof...")
    roof = elements["roof"]
    overhang = roof["overhang_mm"] / 1000
    output["placements"].append({
        "name": "ROOF_MAIN",
        "type": "roof",
        "bounds": {"min_x": -overhang, "max_x": width+overhang, "min_y": -depth-overhang, "max_y": overhang},
        "roof_type": roof["type"],
        "pitch": roof["pitch_degrees"],
        "eave_height": roof["eave_height_mm"] / 1000,
        "ridge_height": roof["ridge_height_mm"] / 1000
    })
    print(f"  {roof['type']} roof with {overhang}m overhang")

    print("Stage 6: Porch...")
    porch = elements["porch"]
    porch_x = porch["position_m"][0]
    porch_w = porch["width_mm"] / 1000 if porch["width_mm"] else 3.0
    porch_d = porch["depth_mm"] / 1000
    porch_h = porch["roof_height_mm"] / 1000
    output["placements"].append({
        "name": "PORCH_FRONT",
        "type": "porch",
        "bounds": {"min_x": porch_x - porch_w/2, "max_x": porch_x + porch_w/2, "min_y": -depth - porch_d, "max_y": -depth},
        "roof_height": porch_h,
        "columns": [
            {"id": "COL_1", "position_m": [porch_x - porch_w/2 + 0.15, -depth - porch_d + 0.15, 0]},
            {"id": "COL_2", "position_m": [porch_x + porch_w/2 - 0.15, -depth - porch_d + 0.15, 0]}
        ]
    })
    print(f"  Porch at X={porch_x}m, {porch_w}m wide, {porch_d}m deep")

    # Stage 7: Interior walls (from grid system)
    print("Stage 7: Interior walls...")
    interior_path = OUTPUT_DIR / "interior_extraction.json"
    if interior_path.exists():
        interior = load_json(interior_path)
        for wall in interior["interior_walls"]:
            output["placements"].append(wall)
        print(f"  {len(interior['interior_walls'])} interior walls")

        # Stage 8: Interior doors
        print("Stage 8: Interior doors...")
        for door in interior["interior_doors"]:
            output["placements"].append(door)
        print(f"  {len(interior['interior_doors'])} interior doors")
    else:
        print("  No interior extraction found, skipping")

    output_path = OUTPUT_DIR / "staged_extraction_v2_FINAL.json"
    save_json(output, output_path)
    print(f"Saved: {output_path}")
    print(f"Total placements: {len(output['placements'])}")

    return output

if __name__ == "__main__":
    run_staged_extraction()
