import json
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
CONFIG_DIR = BASE_DIR / "config"
CACHE_DIR = BASE_DIR / "CACHE"
OUTPUT_DIR = BASE_DIR / "OUTPUT"

ROOM_WALL_MAP = {
    "ANJUNG": "FRONT",
    "RUANG TAMU": "FRONT",
    "BILIK UTAMA": "LEFT",
    "BILIK 1": "RIGHT",
    "BILIK 2": "RIGHT",
    "BILIK MANDI": "LEFT",
    "DAPUR": "BACK",
    "RUANG BASAH": "BACK"
}

ROOM_WINDOW_TYPE = {
    "RUANG TAMU": "W1",
    "BILIK UTAMA": "W1",
    "BILIK 1": "W2",
    "BILIK 2": "W2",
    "BILIK MANDI": "W3",
    "DAPUR": "W2"
}

def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def px_to_m(px_x, px_y, cal):
    ox = cal["origin_px"]
    oy = cal["origin_py"]
    sx = cal["scale_x"]
    sy = cal["scale_y"]
    x_m = (px_x - ox) * sx
    y_m = -(px_y - oy) * sy
    return round(x_m, 3), round(y_m, 3)

def find_text_in_raw(raw_data, search_text):
    for item in raw_data.get("text_items", []):
        if item["text"].upper().strip() == search_text.upper():
            return item["x"], item["y"]
    return None, None

def find_grid_positions(raw_data):
    grids = {"cols": {}, "rows": {}}
    for item in raw_data.get("text_items", []):
        t = item["text"].strip().upper()
        if t in ["A", "B", "C", "D", "E"]:
            if t not in grids["cols"] or item["y"] < grids["cols"][t]["y"]:
                grids["cols"][t] = {"x": item["x"], "y": item["y"]}
        if t in ["1", "2", "3", "4", "5"]:
            if t not in grids["rows"] or item["x"] < grids["rows"][t]["x"]:
                grids["rows"][t] = {"x": item["x"], "y": item["y"]}
    return grids

def find_all_rooms(raw_data):
    rooms = []
    items = raw_data.get("text_items", [])
    single_rooms = ["DAPUR", "ANJUNG", "TANDAS"]
    compound_first = {"BILIK": ["UTAMA", "MANDI", "1", "2"], "RUANG": ["TAMU", "MAKAN", "BASAH"]}

    for item in items:
        t = item["text"].upper().strip()
        if t in single_rooms:
            rooms.append({"name": t, "px": [item["x"], item["y"]]})

    for item in items:
        t = item["text"].upper().strip()
        if t in compound_first:
            for item2 in items:
                t2 = item2["text"].upper().strip()
                dx = abs(item2["x"] - item["x"])
                dy = abs(item2["y"] - item["y"])
                if dx < 200 and dy < 50 and t2 in compound_first[t]:
                    full = t + " " + t2
                    if not any(r["name"] == full for r in rooms):
                        rooms.append({"name": full, "px": [item["x"], item["y"]]})
    return rooms

def derive_window_positions(rooms, cal, width, depth):
    windows = []
    for room in rooms:
        name = room["name"]
        if name not in ROOM_WINDOW_TYPE:
            continue
        wtype = ROOM_WINDOW_TYPE[name]
        wall = ROOM_WALL_MAP.get(name)
        if not wall:
            continue
        x_m, y_m = px_to_m(room["px"][0], room["px"][1], cal)
        if wall == "FRONT":
            pos = [x_m, -depth, 0.9]
        elif wall == "BACK":
            pos = [x_m, 0, 0.9]
        elif wall == "LEFT":
            pos = [0, y_m, 0.9]
        elif wall == "RIGHT":
            pos = [width, y_m, 0.9]
        else:
            continue
        windows.append({
            "type": wtype,
            "room": name,
            "wall": wall,
            "position_m": pos,
            "position_px": room["px"]
        })
    return windows

def fill_template():
    print("Loading files...")
    template = load_json(CONFIG_DIR / "house_template.json")
    placements = load_json(OUTPUT_DIR / "placements.json")
    page1_raw = load_json(CACHE_DIR / "page1_raw.json")

    cal = placements["metadata"]["calibration"]
    template["calibration"]["origin_px"] = [cal["origin_px"], cal["origin_py"]]
    template["calibration"]["scale_x_m_per_px"] = cal["scale_x"]
    template["calibration"]["scale_y_m_per_px"] = cal["scale_y"]
    template["calibration"]["building_width_m"] = cal["real_width"]
    template["calibration"]["building_depth_m"] = cal["real_height"]

    width = cal["real_width"]
    depth = cal["real_height"]

    print("Finding grid positions...")
    grids = find_grid_positions(page1_raw)

    if "A" in grids["cols"] and "1" in grids["rows"]:
        template["house_elements"]["outer_walls"]["corners_px"]["A1"] = [
            grids["cols"]["A"]["x"], grids["rows"]["1"]["y"]
        ]
    if "E" in grids["cols"] and "1" in grids["rows"]:
        template["house_elements"]["outer_walls"]["corners_px"]["E1"] = [
            grids["cols"]["E"]["x"], grids["rows"]["1"]["y"]
        ]
    if "E" in grids["cols"] and "5" in grids["rows"]:
        template["house_elements"]["outer_walls"]["corners_px"]["E5"] = [
            grids["cols"]["E"]["x"], grids["rows"]["5"]["y"]
        ]
    if "A" in grids["cols"] and "5" in grids["rows"]:
        template["house_elements"]["outer_walls"]["corners_px"]["A5"] = [
            grids["cols"]["A"]["x"], grids["rows"]["5"]["y"]
        ]

    template["house_elements"]["outer_walls"]["corners_m"]["A1"] = [0, 0]
    template["house_elements"]["outer_walls"]["corners_m"]["E1"] = [width, 0]
    template["house_elements"]["outer_walls"]["corners_m"]["E5"] = [width, -depth]
    template["house_elements"]["outer_walls"]["corners_m"]["A5"] = [0, -depth]
    template["fill_status"]["outer_walls"] = "filled"
    print("Outer walls: filled from grid")

    print("Finding ANJUNG position...")
    anjung_px = find_text_in_raw(page1_raw, "ANJUNG")
    if anjung_px[0]:
        template["house_elements"]["porch"]["position_px"] = [anjung_px[0], anjung_px[1]]
        x_m, y_m = px_to_m(anjung_px[0], anjung_px[1], cal)
        template["house_elements"]["porch"]["position_m"] = [x_m, y_m, 0]
        template["fill_status"]["porch"] = "filled"
        print(f"Porch: px {anjung_px} -> m ({x_m}, {y_m})")

        template["house_elements"]["main_door"]["position_px"] = [anjung_px[0], anjung_px[1]]
        template["house_elements"]["main_door"]["position_m"] = [x_m, -depth, 0]
        template["fill_status"]["main_door"] = "filled"
        print(f"Main door: at porch X={x_m}m on front wall")

    template["house_elements"]["outside_drain"]["exists"] = True
    template["fill_status"]["outside_drain"] = "filled"

    template["house_elements"]["roof"]["ridge_height_mm"] = 5000
    template["fill_status"]["roof"] = "filled"

    print("Finding all rooms...")
    rooms = find_all_rooms(page1_raw)
    print(f"Found {len(rooms)} rooms")
    for r in rooms:
        print(f"  {r['name']}: px {r['px']}")

    print("Deriving window positions from rooms...")
    windows = derive_window_positions(rooms, cal, width, depth)
    for w in windows:
        wtype = w["type"]
        template["house_elements"]["outer_windows"]["types"][wtype]["instances"].append({
            "room": w["room"],
            "wall": w["wall"],
            "position_m": w["position_m"],
            "position_px": w["position_px"]
        })
        print(f"  {wtype} at {w['room']}: {w['position_m']}")

    template["house_elements"]["outer_windows"]["count"] = len(windows)
    template["fill_status"]["outer_windows"] = "filled"

    output_path = OUTPUT_DIR / "house_template_filled.json"
    save_json(template, output_path)
    print(f"Saved: {output_path}")

    return template

if __name__ == "__main__":
    fill_template()
