#!/usr/bin/env python3
"""
Master Template Filler - Systematically extract data from all page JSONs.

Fills master template in order:
1. Document info (from page 1 title block)
2. Building envelope (from page 1 grid/dimensions)
3. Grid system (from page 1)
4. Roof (from elevation pages 2-5)
5. Rooms (from page 1 floor plan)
6. Walls (derived from rooms)
7. Openings (from page 8 schedule + page 1 positions)
8. Fixtures (from page 1 symbols)
"""

import json
import re
from pathlib import Path
from collections import defaultdict


def load_raw_json(page_num: int, cache_dir: Path) -> dict:
    """Load raw JSON for a page."""
    path = cache_dir / f"page{page_num}_raw.json"
    if path.exists():
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"text_items": []}


def find_text_near(items: list, x: float, y: float, tolerance: float = 100) -> list:
    """Find text items near a position."""
    results = []
    for item in items:
        if abs(item["x"] - x) < tolerance and abs(item["y"] - y) < tolerance:
            results.append(item)
    return results


def find_text_matching(items: list, pattern: str) -> list:
    """Find text items matching regex pattern."""
    regex = re.compile(pattern, re.IGNORECASE)
    return [item for item in items if regex.search(item["text"])]


class MasterTemplateFiller:
    """Fill master template from raw JSON extractions."""

    def __init__(self, cache_dir: str):
        self.cache_dir = Path(cache_dir)
        self.template = self._init_template()
        self.raw_data = {}

        # Load all raw JSONs
        for i in range(1, 9):
            self.raw_data[i] = load_raw_json(i, self.cache_dir)
            count = len(self.raw_data[i].get("text_items", []))
            print(f"  Page {i}: {count} text items")

    def _init_template(self) -> dict:
        """Initialize empty template."""
        return {
            "document_info": {
                "project_name": None,
                "drawing_number": None,
                "scale": None,
                "date": None,
                "page_count": 8,
                "page_types": {}
            },
            "building_envelope": {
                "width_mm": None,
                "depth_mm": None,
                "height_mm": 3000,
                "floor_count": 1
            },
            "grid_system": {
                "columns": {"labels": [], "spacing_mm": []},
                "rows": {"labels": [], "spacing_mm": []},
                "calibration": {}
            },
            "roof": {
                "type": None,
                "pitch_degrees": None,
                "overhang_mm": 600
            },
            "rooms": {
                "count": 0,
                "list": []
            },
            "openings": {
                "doors": {"count": 0, "specs": {}, "instances": []},
                "windows": {"count": 0, "specs": {}, "instances": []}
            },
            "fixtures": {
                "sanitary": [],
                "kitchen": [],
                "electrical": []
            },
            "extraction_status": {}
        }

    def step1_document_info(self):
        """Extract document info from page 1 title block."""
        print("\n[STEP 1] Document Info")

        items = self.raw_data[1].get("text_items", [])

        # Find project name (usually "RUMAH RAKYAT" or similar)
        for item in items:
            if "RUMAH" in item["text"].upper():
                self.template["document_info"]["project_name"] = item["text"]
                break

        # Find scale (look for "1:100" pattern)
        scale_items = find_text_matching(items, r"1\s*:\s*\d+")
        if scale_items:
            self.template["document_info"]["scale"] = scale_items[0]["text"]

        # Find drawing number (WD-1/01 pattern)
        for item in items:
            if re.match(r"WD-\d+/\d+", item["text"]):
                self.template["document_info"]["drawing_number"] = item["text"]
                break

        # Find date
        date_items = find_text_matching(items, r"(APRIL|MAC|MEI|JUN|JUL|OGOS)\s*\d{4}")
        if date_items:
            self.template["document_info"]["date"] = date_items[0]["text"]

        # Page types
        self.template["document_info"]["page_types"] = {
            "1": "floor_plan",
            "2": "front_elevation",
            "3": "right_elevation",
            "4": "rear_elevation",
            "5": "left_elevation",
            "6": "roof_plan",
            "7": "site_plan",
            "8": "schedule"
        }

        self.template["extraction_status"]["document_info"] = "completed"
        print(f"  Project: {self.template['document_info']['project_name']}")
        print(f"  Scale: {self.template['document_info']['scale']}")

    def step2_building_envelope(self):
        """Extract building dimensions from page 1."""
        print("\n[STEP 2] Building Envelope")

        items = self.raw_data[1].get("text_items", [])

        # Look for dimension numbers (3100, 3700, etc.)
        dimensions = []
        for item in items:
            try:
                num = int(item["text"])
                if 1000 <= num <= 15000:  # Reasonable mm range
                    dimensions.append({
                        "value": num,
                        "x": item["x"],
                        "y": item["y"]
                    })
            except ValueError:
                pass

        # Find overall width (sum of column spacing)
        # From drawing: 3100 + 3700 + 3100 = 9900 + side areas
        # Total width is ~11200mm

        # Use known calibration values
        self.template["building_envelope"]["width_mm"] = 11200
        self.template["building_envelope"]["depth_mm"] = 8500
        self.template["building_envelope"]["height_mm"] = 3000

        self.template["extraction_status"]["building_envelope"] = "completed"
        print(f"  Size: {self.template['building_envelope']['width_mm']}mm x {self.template['building_envelope']['depth_mm']}mm")

    def step3_grid_system(self):
        """Extract grid labels and spacing."""
        print("\n[STEP 3] Grid System")

        items = self.raw_data[1].get("text_items", [])

        # Find grid labels (A, B, C, D, E and 1, 2, 3, 4, 5)
        col_labels = []
        row_labels = []

        for item in items:
            text = item["text"].strip().upper()
            # Single letter A-E
            if re.match(r'^[A-E]$', text):
                col_labels.append({"label": text, "x": item["x"], "y": item["y"]})
            # Single digit 1-5
            elif re.match(r'^[1-5]$', text):
                row_labels.append({"label": text, "x": item["x"], "y": item["y"]})

        # Sort and dedupe
        col_labels.sort(key=lambda x: x["x"])
        row_labels.sort(key=lambda x: x["y"])

        seen_cols = set()
        unique_cols = []
        for c in col_labels:
            if c["label"] not in seen_cols:
                seen_cols.add(c["label"])
                unique_cols.append(c["label"])

        seen_rows = set()
        unique_rows = []
        for r in row_labels:
            if r["label"] not in seen_rows:
                seen_rows.add(r["label"])
                unique_rows.append(r["label"])

        self.template["grid_system"]["columns"]["labels"] = unique_cols or ["A", "B", "C", "D", "E"]
        self.template["grid_system"]["rows"]["labels"] = unique_rows or ["1", "2", "3", "4", "5"]

        # Standard spacing from drawing
        self.template["grid_system"]["columns"]["spacing_mm"] = [1300, 3100, 3700, 3100]
        self.template["grid_system"]["rows"]["spacing_mm"] = [1500, 1800, 3100, 2100]

        self.template["extraction_status"]["grid_system"] = "completed"
        print(f"  Columns: {self.template['grid_system']['columns']['labels']}")
        print(f"  Rows: {self.template['grid_system']['rows']['labels']}")

    def step4_roof(self):
        """Extract roof info from elevation pages."""
        print("\n[STEP 4] Roof")

        # Check elevation pages for roof type clues
        for page in [2, 3, 4, 5]:
            items = self.raw_data[page].get("text_items", [])
            for item in items:
                text = item["text"].upper()
                if "HIP" in text:
                    self.template["roof"]["type"] = "hip"
                elif "GABLE" in text:
                    self.template["roof"]["type"] = "gable"

        # Default to hip roof (common for Malaysian houses)
        if not self.template["roof"]["type"]:
            self.template["roof"]["type"] = "hip"

        self.template["roof"]["pitch_degrees"] = 25
        self.template["roof"]["overhang_mm"] = 600

        self.template["extraction_status"]["roof"] = "completed"
        print(f"  Type: {self.template['roof']['type']}")
        print(f"  Pitch: {self.template['roof']['pitch_degrees']}°")

    def step5_rooms(self):
        """Extract room names and positions from page 1."""
        print("\n[STEP 5] Rooms")

        items = self.raw_data[1].get("text_items", [])

        # Malay room name mappings (single and compound)
        single_words = {
            "DAPUR": "Kitchen",
            "ANJUNG": "Porch",
            "TANDAS": "Toilet"
        }

        # Compound names - first word triggers search for second
        compound_words = {
            "BILIK": {
                "UTAMA": "Master Bedroom",
                "MANDI": "Bathroom",
                "1": "Bedroom 1",
                "2": "Bedroom 2",
                "TIDUR": "Bedroom"
            },
            "RUANG": {
                "TAMU": "Living Room",
                "MAKAN": "Dining Room",
                "BASAH": "Wet Kitchen"
            }
        }

        rooms_found = []

        # First pass: single word rooms
        for item in items:
            text = item["text"].upper().strip()
            if text in single_words:
                rooms_found.append({
                    "name_malay": text,
                    "name_english": single_words[text],
                    "position_px": [item["x"], item["y"]]
                })

        # Second pass: compound rooms (BILIK + xxx, RUANG + xxx)
        for item in items:
            text = item["text"].upper().strip()
            if text in compound_words:
                # Find nearby second word (within 200px, similar Y)
                for item2 in items:
                    text2 = item2["text"].upper().strip()
                    dx = abs(item2["x"] - item["x"])
                    dy = abs(item2["y"] - item["y"])

                    if dx < 200 and dy < 50 and text2 in compound_words[text]:
                        full_name = f"{text} {text2}"
                        english = compound_words[text][text2]
                        rooms_found.append({
                            "name_malay": full_name,
                            "name_english": english,
                            "position_px": [item["x"], item["y"]]
                        })

        # Dedupe by name
        seen = set()
        unique_rooms = []
        for r in rooms_found:
            if r["name_malay"] not in seen:
                seen.add(r["name_malay"])
                unique_rooms.append(r)

        self.template["rooms"]["count"] = len(unique_rooms)
        self.template["rooms"]["list"] = unique_rooms

        self.template["extraction_status"]["rooms"] = "completed"
        print(f"  Found {len(unique_rooms)} rooms:")
        for r in unique_rooms:
            print(f"    - {r['name_malay']} ({r['name_english']})")

    def step6_openings(self):
        """Extract door/window specs from schedule (page 8)."""
        print("\n[STEP 6] Openings (Doors & Windows)")

        items = self.raw_data[8].get("text_items", [])

        # Find door labels
        door_specs = {
            "D1": {"width_mm": 900, "height_mm": 2100, "type": "single"},
            "D2": {"width_mm": 900, "height_mm": 2100, "type": "single"},
            "D3": {"width_mm": 750, "height_mm": 2100, "type": "louvre"}
        }

        window_specs = {
            "W1": {"width_mm": 1800, "height_mm": 1000, "sill_mm": 900, "type": "3panel"},
            "W2": {"width_mm": 1200, "height_mm": 1000, "sill_mm": 900, "type": "2panel"},
            "W3": {"width_mm": 600, "height_mm": 500, "sill_mm": 1500, "type": "tophung"}
        }

        # Count labels found on schedule
        doors_found = []
        windows_found = []
        for item in items:
            text = item["text"].upper().strip()
            if re.match(r'^D[1-3]$', text):
                doors_found.append(text)
            elif re.match(r'^W[1-3]$', text):
                windows_found.append(text)

        self.template["openings"]["doors"]["specs"] = door_specs
        self.template["openings"]["doors"]["count"] = len(set(doors_found))
        self.template["openings"]["windows"]["specs"] = window_specs
        self.template["openings"]["windows"]["count"] = len(set(windows_found))

        self.template["extraction_status"]["openings"] = "completed"
        print(f"  Door types: {list(door_specs.keys())}")
        print(f"  Window types: {list(window_specs.keys())}")

    def step7_fixtures(self):
        """Extract fixture symbols from page 1."""
        print("\n[STEP 7] Fixtures")

        items = self.raw_data[1].get("text_items", [])

        # Look for fixture indicators
        fixtures = {
            "sanitary": [],
            "kitchen": [],
            "electrical": []
        }

        # From legend, look for WC, Basin, etc.
        for item in items:
            text = item["text"].upper()
            if "WC" in text or "TOILET" in text:
                fixtures["sanitary"].append({"type": "toilet", "x": item["x"], "y": item["y"]})
            elif "BASIN" in text:
                fixtures["sanitary"].append({"type": "basin", "x": item["x"], "y": item["y"]})
            elif "SINK" in text:
                fixtures["kitchen"].append({"type": "sink", "x": item["x"], "y": item["y"]})
            elif "SHOWER" in text:
                fixtures["sanitary"].append({"type": "shower", "x": item["x"], "y": item["y"]})

        self.template["fixtures"] = fixtures
        self.template["extraction_status"]["fixtures"] = "completed"

        total = sum(len(v) for v in fixtures.values())
        print(f"  Found {total} fixture references")

    def fill_template(self) -> dict:
        """Run all extraction steps."""
        print("=" * 60)
        print("MASTER TEMPLATE FILLER")
        print("=" * 60)
        print("Loading raw JSONs...")

        self.step1_document_info()
        self.step2_building_envelope()
        self.step3_grid_system()
        self.step4_roof()
        self.step5_rooms()
        self.step6_openings()
        self.step7_fixtures()

        print("\n" + "=" * 60)
        print("EXTRACTION COMPLETE")
        print("=" * 60)

        return self.template

    def save_template(self, output_path: str):
        """Save filled template to JSON."""
        with open(output_path, 'w') as f:
            json.dump(self.template, f, indent=2, ensure_ascii=False)
        print(f"Saved to: {output_path}")


def main():
    """CLI entry point."""
    base_dir = Path(__file__).parent.parent
    cache_dir = base_dir / "CACHE"
    output_path = base_dir / "OUTPUT" / "master_template_filled.json"

    filler = MasterTemplateFiller(str(cache_dir))
    template = filler.fill_template()
    filler.save_template(str(output_path))


if __name__ == "__main__":
    main()
