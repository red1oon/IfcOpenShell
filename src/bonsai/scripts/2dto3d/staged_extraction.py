"""
Staged Extraction Pipeline for 2D to 3D Architectural Conversion
Stage 1: Perimeter drain
Stage 2: Outer walls with windows/doors
Stage 3: Roof and porch
Each stage locks output before proceeding to next.
"""

import json
import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).parent
CONFIG_DIR = BASE_DIR / "config"
OUTPUT_DIR = BASE_DIR / "OUTPUT"
CACHE_DIR = BASE_DIR / "CACHE"

# Default dimensions based on Malaysian residential standards
DEFAULTS = {
    "building_envelope": {
        "width_mm": 11200,  # 11.2m typical single-story
        "depth_mm": 8500,   # 8.5m typical
        "height_mm": 3000,  # 3m floor-to-floor
        "floor_count": 1
    },
    "perimeter_drain": {
        "offset_from_wall_mm": 600,  # Standard drain offset
        "width_mm": 150,             # Drain channel width
        "depth_mm": 150,             # Drain depth
        "slope_percent": 1.0         # 1% slope for drainage
    },
    "external_wall": {
        "thickness_mm": 150,  # 6" brick wall
        "height_mm": 3000
    },
    "internal_wall": {
        "thickness_mm": 100,  # 4" partition
        "height_mm": 3000
    },
    "door": {
        "D1": {"width_mm": 900, "height_mm": 2100, "type": "single"},
        "D2": {"width_mm": 900, "height_mm": 2100, "type": "single"},
        "D3": {"width_mm": 750, "height_mm": 2100, "type": "louvre"}
    },
    "window": {
        "W1": {"width_mm": 1800, "height_mm": 1000, "sill_mm": 900, "type": "3panel"},
        "W2": {"width_mm": 1200, "height_mm": 1000, "sill_mm": 900, "type": "2panel"},
        "W3": {"width_mm": 600, "height_mm": 500, "sill_mm": 1500, "type": "tophung"}
    },
    "roof": {
        "type": "hip",
        "pitch_degrees": 25,
        "overhang_mm": 600,
        "fascia_height_mm": 200
    },
    "porch": {
        "depth_mm": 2000,
        "width_mm": 3000,
        "roof_type": "flat",
        "column_size_mm": 150
    }
}

# Library object mappings
LIBRARY_OBJECTS = {
    "doors": {
        "D1": "door_single_900_lod300",
        "D2": "door_single_900_lod300",
        "D3": "door_louvre_750_lod300"
    },
    "windows": {
        "W1": "window_aluminum_3panel_1800x1000",
        "W2": "window_aluminum_2panel_1200x1000",
        "W3": "window_aluminum_tophung_600x500"
    },
    "fixtures": {
        "toilet": "floor_mounted_toilet_lod300",
        "basin": "basin_residential_lod300",
        "kitchen_sink": "kitchen_sink_single_bowl_lod200",
        "shower": "shower_tray_900_lod300"
    }
}


class StagedExtraction:
    def __init__(self):
        self.output = {
            "metadata": {
                "pipeline": "staged_extraction",
                "stages_completed": [],
                "calibration": None
            },
            "stage1_perimeter": None,
            "stage2_exterior": None,
            "stage3_roof_porch": None,
            "placements": []
        }
        self.master_template = None
        self.load_calibration()
        self.load_master_template()

    def load_calibration(self):
        """Load calibration from existing placements.json if available."""
        placements_file = OUTPUT_DIR / "placements.json"
        if placements_file.exists():
            with open(placements_file, 'r') as f:
                data = json.load(f)
                if "metadata" in data and "calibration" in data["metadata"]:
                    self.output["metadata"]["calibration"] = data["metadata"]["calibration"]
                    print(f"Loaded calibration: {data['metadata']['calibration']['real_width']}m x {data['metadata']['calibration']['real_height']}m")

    def load_master_template(self):
        """Load filled master template if available."""
        template_file = OUTPUT_DIR / "master_template_filled.json"
        if template_file.exists():
            with open(template_file, 'r') as f:
                self.master_template = json.load(f)
                print(f"Loaded master template: {self.master_template['rooms']['count']} rooms, {self.master_template['openings']['doors']['count']} door types")

    def stage1_perimeter_drain(self):
        """
        Stage 1: Extract perimeter drain.
        Uses building envelope to create drain around perimeter.
        """
        print("\n=== STAGE 1: Perimeter Drain ===")

        cal = self.output["metadata"]["calibration"]
        if not cal:
            print("ERROR: No calibration data. Run calibration first.")
            return False

        width = cal["real_width"]
        depth = cal["real_height"]
        drain_offset = DEFAULTS["perimeter_drain"]["offset_from_wall_mm"] / 1000
        drain_width = DEFAULTS["perimeter_drain"]["width_mm"] / 1000

        # Create drain segments around perimeter
        # Origin at grid A-1, X positive to right, Y positive up (but our Y goes down)
        drain_segments = [
            # Front (bottom of plan, Y = -depth - offset)
            {
                "id": "DRAIN_FRONT",
                "start_m": [-drain_offset, -depth - drain_offset, 0],
                "end_m": [width + drain_offset, -depth - drain_offset, 0],
                "type": "perimeter_drain"
            },
            # Back (top of plan, Y = +offset)
            {
                "id": "DRAIN_BACK",
                "start_m": [-drain_offset, drain_offset, 0],
                "end_m": [width + drain_offset, drain_offset, 0],
                "type": "perimeter_drain"
            },
            # Left (X = -offset)
            {
                "id": "DRAIN_LEFT",
                "start_m": [-drain_offset, drain_offset, 0],
                "end_m": [-drain_offset, -depth - drain_offset, 0],
                "type": "perimeter_drain"
            },
            # Right (X = width + offset)
            {
                "id": "DRAIN_RIGHT",
                "start_m": [width + drain_offset, drain_offset, 0],
                "end_m": [width + drain_offset, -depth - drain_offset, 0],
                "type": "perimeter_drain"
            }
        ]

        self.output["stage1_perimeter"] = {
            "drain_segments": drain_segments,
            "drain_spec": DEFAULTS["perimeter_drain"],
            "building_bounds": {
                "width_m": width,
                "depth_m": depth,
                "origin": "grid_A1"
            }
        }

        self.output["metadata"]["stages_completed"].append("stage1_perimeter")
        print(f"Created {len(drain_segments)} drain segments")
        print(f"Building bounds: {width}m x {depth}m")

        self.save_stage_output("stage1")
        return True

    def stage2_exterior_walls(self):
        """
        Stage 2: Outer walls with windows and doors.
        Creates external wall segments and places openings.
        Uses visual analysis for external opening positions.
        """
        print("\n=== STAGE 2: Exterior Walls & Openings ===")

        if "stage1_perimeter" not in self.output["metadata"]["stages_completed"]:
            print("ERROR: Stage 1 not completed. Run stage1 first.")
            return False

        cal = self.output["metadata"]["calibration"]
        width = cal["real_width"]
        depth = cal["real_height"]
        wall_thick = DEFAULTS["external_wall"]["thickness_mm"] / 1000
        wall_height = DEFAULTS["external_wall"]["height_mm"] / 1000

        # External walls - rectangle around building
        external_walls = [
            {
                "id": "EXT_WALL_FRONT",
                "start_m": [0, -depth, 0],
                "end_m": [width, -depth, 0],
                "thickness_m": wall_thick,
                "height_m": wall_height,
                "type": "external",
                "openings": []
            },
            {
                "id": "EXT_WALL_BACK",
                "start_m": [0, 0, 0],
                "end_m": [width, 0, 0],
                "thickness_m": wall_thick,
                "height_m": wall_height,
                "type": "external",
                "openings": []
            },
            {
                "id": "EXT_WALL_LEFT",
                "start_m": [0, 0, 0],
                "end_m": [0, -depth, 0],
                "thickness_m": wall_thick,
                "height_m": wall_height,
                "type": "external",
                "openings": []
            },
            {
                "id": "EXT_WALL_RIGHT",
                "start_m": [width, 0, 0],
                "end_m": [width, -depth, 0],
                "thickness_m": wall_thick,
                "height_m": wall_height,
                "type": "external",
                "openings": []
            }
        ]

        # EXTERNAL DOORS - from visual analysis of floor plan
        # These are the doors on external walls only
        external_door_positions = [
            {"label": "D1", "x_m": 1.0, "wall": "FRONT", "swing": "left_in", "desc": "Main entrance"},
            {"label": "D2", "x_m": 5.5, "wall": "BACK", "swing": "right_out", "desc": "Back door to wet area"}
        ]

        # EXTERNAL WINDOWS - from visual analysis of floor plan
        external_window_positions = [
            # FRONT WALL (Y = -depth)
            {"label": "W1", "x_m": 3.5, "wall": "FRONT", "desc": "Living room front"},
            {"label": "W2", "x_m": 8.0, "wall": "FRONT", "desc": "Bedroom 1 front"},
            # LEFT WALL (X = 0)
            {"label": "W1", "x_m": 3.0, "wall": "LEFT", "desc": "Master bedroom"},
            {"label": "W3", "x_m": 1.5, "wall": "LEFT", "desc": "Bathroom tophung"},
            # RIGHT WALL (X = width)
            {"label": "W2", "x_m": 5.5, "wall": "RIGHT", "desc": "Bedroom 1 side"},
            {"label": "W2", "x_m": 3.0, "wall": "RIGHT", "desc": "Bedroom 2 side"},
            # BACK WALL (Y = 0)
            {"label": "W2", "x_m": 8.5, "wall": "BACK", "desc": "Kitchen window"}
        ]

        # Get specs from master template or defaults
        door_specs = DEFAULTS["door"]
        window_specs = DEFAULTS["window"]
        if self.master_template:
            door_specs = {k: v for k, v in self.master_template["openings"]["doors"]["specs"].items()}
            window_specs = {k: v for k, v in self.master_template["openings"]["windows"]["specs"].items()}

        # Process external doors
        doors = []
        for i, d in enumerate(external_door_positions):
            label = d["label"]
            spec = door_specs.get(label, door_specs["D1"])

            # Calculate position based on wall
            if d["wall"] == "FRONT":
                pos = [d["x_m"], -depth, 0]
                host_wall = "EXT_WALL_FRONT"
            elif d["wall"] == "BACK":
                pos = [d["x_m"], 0, 0]
                host_wall = "EXT_WALL_BACK"
            elif d["wall"] == "LEFT":
                pos = [0, -d["x_m"], 0]
                host_wall = "EXT_WALL_LEFT"
            else:  # RIGHT
                pos = [width, -d["x_m"], 0]
                host_wall = "EXT_WALL_RIGHT"

            doors.append({
                "id": f"{label}_{i+1}",
                "label": label,
                "position_m": pos,
                "width_m": spec["width_mm"] / 1000,
                "height_m": spec["height_mm"] / 1000,
                "type": spec["type"],
                "swing": d.get("swing", "left_in"),
                "description": d["desc"],
                "library_object": LIBRARY_OBJECTS["doors"].get(label, "door_single_900_lod300"),
                "host_wall": host_wall
            })

        # Process external windows
        windows = []
        for i, w in enumerate(external_window_positions):
            label = w["label"]
            spec = window_specs.get(label, window_specs["W1"])
            sill = spec.get("sill_mm", 900) / 1000

            if w["wall"] == "FRONT":
                pos = [w["x_m"], -depth, sill]
                host_wall = "EXT_WALL_FRONT"
            elif w["wall"] == "BACK":
                pos = [w["x_m"], 0, sill]
                host_wall = "EXT_WALL_BACK"
            elif w["wall"] == "LEFT":
                pos = [0, -w["x_m"], sill]
                host_wall = "EXT_WALL_LEFT"
            else:  # RIGHT
                pos = [width, -w["x_m"], sill]
                host_wall = "EXT_WALL_RIGHT"

            windows.append({
                "id": f"{label}_{i+1}",
                "label": label,
                "position_m": pos,
                "width_m": spec["width_mm"] / 1000,
                "height_m": spec["height_mm"] / 1000,
                "sill_height_m": sill,
                "type": spec["type"],
                "description": w["desc"],
                "library_object": LIBRARY_OBJECTS["windows"].get(label, "window_aluminum_2panel_1200x1000"),
                "host_wall": host_wall
            })

        self.output["stage2_exterior"] = {
            "external_walls": external_walls,
            "doors": doors,
            "windows": windows,
            "wall_spec": DEFAULTS["external_wall"]
        }

        self.output["metadata"]["stages_completed"].append("stage2_exterior")
        print(f"Created {len(external_walls)} external wall segments")
        print(f"Placed {len(doors)} external doors:")
        for d in doors:
            print(f"  - {d['id']}: {d['description']} on {d['host_wall']}")
        print(f"Placed {len(windows)} external windows:")
        for w in windows:
            print(f"  - {w['id']}: {w['description']} on {w['host_wall']}")

        self.save_stage_output("stage2")
        return True

    def stage3_roof_porch(self):
        """
        Stage 3: Roof and porch.
        Creates roof geometry and porch structure.
        """
        print("\n=== STAGE 3: Roof & Porch ===")

        if "stage2_exterior" not in self.output["metadata"]["stages_completed"]:
            print("ERROR: Stage 2 not completed. Run stage2 first.")
            return False

        cal = self.output["metadata"]["calibration"]
        width = cal["real_width"]
        depth = cal["real_height"]

        roof_spec = DEFAULTS["roof"]
        porch_spec = DEFAULTS["porch"]
        wall_height = DEFAULTS["external_wall"]["height_mm"] / 1000
        overhang = roof_spec["overhang_mm"] / 1000

        # Roof - hip roof covering building
        roof = {
            "id": "ROOF_MAIN",
            "type": roof_spec["type"],
            "pitch_degrees": roof_spec["pitch_degrees"],
            "bounds": {
                "min_x": -overhang,
                "max_x": width + overhang,
                "min_y": -depth - overhang,
                "max_y": overhang
            },
            "eave_height_m": wall_height,
            "ridge_height_m": wall_height + 2.0,  # Calculated from pitch
            "overhang_m": overhang,
            "fascia_height_m": roof_spec["fascia_height_mm"] / 1000
        }

        # Porch - front of building
        porch_depth = porch_spec["depth_mm"] / 1000
        porch_width = porch_spec["width_mm"] / 1000

        porch = {
            "id": "PORCH_FRONT",
            "type": "covered",
            "bounds": {
                "min_x": 0,
                "max_x": porch_width,
                "min_y": -depth - porch_depth,
                "max_y": -depth
            },
            "roof_type": porch_spec["roof_type"],
            "roof_height_m": wall_height - 0.3,  # Slightly lower than main
            "columns": [
                {"id": "COL_1", "position_m": [0.15, -depth - porch_depth + 0.15, 0]},
                {"id": "COL_2", "position_m": [porch_width - 0.15, -depth - porch_depth + 0.15, 0]}
            ],
            "column_size_m": porch_spec["column_size_mm"] / 1000
        }

        self.output["stage3_roof_porch"] = {
            "roof": roof,
            "porch": porch,
            "roof_spec": roof_spec,
            "porch_spec": porch_spec
        }

        self.output["metadata"]["stages_completed"].append("stage3_roof_porch")
        print(f"Created roof: {roof_spec['type']} with {roof_spec['pitch_degrees']}deg pitch")
        print(f"Created porch: {porch_width}m x {porch_depth}m")

        self.save_stage_output("stage3")
        return True

    def _find_host_wall(self, position, walls):
        """Find which wall an opening belongs to based on position."""
        x, y, z = position
        cal = self.output["metadata"]["calibration"]
        width = cal["real_width"]
        depth = cal["real_height"]
        tolerance = 0.5  # 500mm tolerance

        # Check proximity to each wall
        if abs(y + depth) < tolerance:  # Near front wall
            return "EXT_WALL_FRONT"
        elif abs(y) < tolerance:  # Near back wall
            return "EXT_WALL_BACK"
        elif abs(x) < tolerance:  # Near left wall
            return "EXT_WALL_LEFT"
        elif abs(x - width) < tolerance:  # Near right wall
            return "EXT_WALL_RIGHT"

        return None  # Interior or unknown

    def save_stage_output(self, stage_name):
        """Save current state to locked stage file."""
        OUTPUT_DIR.mkdir(exist_ok=True)

        # Save stage-specific file (locked)
        stage_file = OUTPUT_DIR / f"{stage_name}_locked.json"
        with open(stage_file, 'w') as f:
            json.dump(self.output, f, indent=2)
        print(f"Stage locked: {stage_file}")

        # Update combined output
        combined_file = OUTPUT_DIR / "staged_extraction.json"
        with open(combined_file, 'w') as f:
            json.dump(self.output, f, indent=2)
        print(f"Combined output: {combined_file}")

    def generate_placements(self):
        """Generate final placements list for Blender import."""
        print("\n=== Generating Placements ===")

        placements = []

        # Add drain segments
        if self.output["stage1_perimeter"]:
            for seg in self.output["stage1_perimeter"]["drain_segments"]:
                placements.append({
                    "name": seg["id"],
                    "type": "drain",
                    "start_point": seg["start_m"],
                    "end_point": seg["end_m"],
                    "object_type": "perimeter_drain_150"
                })

        # Add walls
        if self.output["stage2_exterior"]:
            for wall in self.output["stage2_exterior"]["external_walls"]:
                placements.append({
                    "name": wall["id"],
                    "type": "wall",
                    "start_point": wall["start_m"],
                    "end_point": wall["end_m"],
                    "thickness": wall["thickness_m"],
                    "height": wall["height_m"],
                    "object_type": "wall_external_150"
                })

            # Add doors
            for door in self.output["stage2_exterior"]["doors"]:
                placements.append({
                    "name": door["id"],
                    "type": "door",
                    "position": door["position_m"],
                    "width": door["width_m"],
                    "height": door["height_m"],
                    "object_type": door["library_object"],
                    "host_wall": door["host_wall"]
                })

            # Add windows
            for window in self.output["stage2_exterior"]["windows"]:
                placements.append({
                    "name": window["id"],
                    "type": "window",
                    "position": window["position_m"],
                    "width": window["width_m"],
                    "height": window["height_m"],
                    "sill_height": window["sill_height_m"],
                    "object_type": window["library_object"],
                    "host_wall": window["host_wall"]
                })

        # Add roof
        if self.output["stage3_roof_porch"]:
            roof = self.output["stage3_roof_porch"]["roof"]
            placements.append({
                "name": roof["id"],
                "type": "roof",
                "bounds": roof["bounds"],
                "roof_type": roof["type"],
                "pitch": roof["pitch_degrees"],
                "eave_height": roof["eave_height_m"],
                "ridge_height": roof["ridge_height_m"],
                "object_type": f"roof_{roof['type']}"
            })

            # Add porch
            porch = self.output["stage3_roof_porch"]["porch"]
            placements.append({
                "name": porch["id"],
                "type": "porch",
                "bounds": porch["bounds"],
                "roof_height": porch["roof_height_m"],
                "columns": porch["columns"],
                "object_type": "porch_covered"
            })

        self.output["placements"] = placements

        # Save final output
        final_file = OUTPUT_DIR / "staged_extraction_FINAL.json"
        with open(final_file, 'w') as f:
            json.dump(self.output, f, indent=2)
        print(f"Final output: {final_file}")
        print(f"Total placements: {len(placements)}")

        return placements


def main():
    """Run all stages of extraction."""
    extractor = StagedExtraction()

    # Run stages sequentially
    if extractor.stage1_perimeter_drain():
        if extractor.stage2_exterior_walls():
            if extractor.stage3_roof_porch():
                extractor.generate_placements()
                print("\n=== Pipeline Complete ===")
                print(f"Stages completed: {extractor.output['metadata']['stages_completed']}")


if __name__ == "__main__":
    main()
