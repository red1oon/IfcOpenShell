#!/usr/bin/env python3
"""
Fast IFC Storey Density Scanner
================================
Scans IfcBuildingStorey spatial structure to find multi-discipline dense floors.
No coordinate reading needed - uses IFC's built-in spatial hierarchy.

Usage:
    PYTHONPATH=/home/red1/Projects/IfcOpenShell/src python3 scan_storey_density.py
"""

import sys
import json
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, '/home/red1/Projects/IfcOpenShell/src')
import ifcopenshell

# IFC files
IFC_DIR = Path("/home/red1/Documents/bonsai/PythonLibs/Terminal_1_IFC4/Terminal 1 IFC4")
IFC_FILES = [
    "SJTII-ARC-A-TER1-00-R0-Clean.ifc",
    "SJTII-STR-S-TER1-00-R0-Clean.ifc",
    "SJTII-ACMV-A-TER1-00-R0-Clean.ifc",
    "SJTII-ELEC-A-TER1-00-R0-Clean.ifc",
    "SJTII-FP-A-TER1-00-R0-Clean.ifc",
    "SJTII-LPG-A-TER1-00-RO-Clean.ifc",
    "SJTII-SP-A-TER1-00-R0-Clean.ifc",
    "SJTII-CW-A-TER1-00-R0-Clean.ifc",
]

DISCIPLINE_MAP = {
    "ARC": "ARC", "STR": "STR", "CW": "CW", "FP": "FP",
    "SP": "SP", "ACMV": "ACMV", "ELEC": "ELEC", "LPG": "LPG"
}

def get_discipline_from_path(filepath):
    """Extract discipline from filename."""
    name = Path(filepath).name
    for key in DISCIPLINE_MAP:
        if key in name:
            return DISCIPLINE_MAP[key]
    return "UNKNOWN"

def scan_storeys(ifc_file, discipline):
    """Scan IfcBuildingStorey relationships and count elements per storey."""
    storey_counts = defaultdict(lambda: {"discipline": discipline, "count": 0, "elements": []})

    # Get all storeys
    storeys = ifc_file.by_type("IfcBuildingStorey")

    for storey in storeys:
        storey_name = storey.Name or storey.LongName or f"Storey_{storey.id()}"

        # Get elements contained in this storey
        for rel in storey.ContainsElements:
            elements = rel.RelatedElements

            # Filter to physical elements only
            physical_elements = [e for e in elements if e.is_a("IfcProduct")
                               and not e.is_a("IfcSpatialElement")
                               and not e.is_a("IfcOpeningElement")]

            storey_counts[storey_name]["count"] += len(physical_elements)
            storey_counts[storey_name]["elements"].extend([e.GlobalId for e in physical_elements])

    return dict(storey_counts)

def main():
    print("="*80)
    print("FAST IFC STOREY DENSITY SCAN")
    print("="*80)
    print(f"\nScanning {len(IFC_FILES)} IFC files...\n")

    # Aggregate storey data across all disciplines
    all_storeys = defaultdict(lambda: {"disciplines": set(), "counts": {}, "total": 0, "elements": []})

    for ifc_file in IFC_FILES:
        filepath = IFC_DIR / ifc_file
        if not filepath.exists():
            print(f"⚠️  File not found: {ifc_file}")
            continue

        discipline = get_discipline_from_path(filepath)
        print(f"  Scanning {discipline}: {ifc_file}")

        ifc = ifcopenshell.open(str(filepath))
        storey_data = scan_storeys(ifc, discipline)

        for storey_name, data in storey_data.items():
            all_storeys[storey_name]["disciplines"].add(discipline)
            all_storeys[storey_name]["counts"][discipline] = data["count"]
            all_storeys[storey_name]["total"] += data["count"]
            all_storeys[storey_name]["elements"].extend(data["elements"])

    # Convert sets to lists for JSON serialization
    for storey in all_storeys.values():
        storey["disciplines"] = sorted(list(storey["disciplines"]))

    # Rank storeys by multi-discipline density
    print("\n" + "="*80)
    print("STOREY ANALYSIS - Ranked by Multi-Discipline Density")
    print("="*80)

    ranked_storeys = sorted(all_storeys.items(),
                           key=lambda x: (len(x[1]["disciplines"]), x[1]["total"]),
                           reverse=True)

    for storey_name, data in ranked_storeys[:10]:  # Top 10
        disc_count = len(data["disciplines"])
        total = data["total"]
        disciplines = ", ".join(data["disciplines"])
        print(f"\n📍 {storey_name}")
        print(f"   Disciplines ({disc_count}): {disciplines}")
        print(f"   Total elements: {total}")
        for disc, count in sorted(data["counts"].items()):
            print(f"      - {disc}: {count}")

    # Pick best storey (most disciplines + decent element count)
    if ranked_storeys:
        best_storey_name, best_data = ranked_storeys[0]

        if len(best_data["disciplines"]) >= 3 and best_data["total"] >= 100:
            print("\n" + "="*80)
            print(f"✅ BEST STOREY FOUND: {best_storey_name}")
            print("="*80)
            print(f"   Disciplines: {', '.join(best_data['disciplines'])}")
            print(f"   Total elements: {best_data['total']}")

            # Generate sample config
            config = {
                "sample_extraction": {
                    "description": f"Storey-based sampling - {best_storey_name}",
                    "extraction_mode": "storey",
                    "storey_name": best_storey_name,
                    "max_elements": 800,
                    "disciplines": best_data["disciplines"],
                    "estimated_total": best_data["total"],
                    "note": "Extract elements from specific IfcBuildingStorey"
                }
            }

            config_path = Path.home() / "Documents" / "bonsai" / "Scripts" / "sample_config.json"
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)

            print(f"\n✅ Config saved to: {config_path}")
        else:
            print("\n⚠️  No storey meets requirements (3+ disciplines, 100+ elements)")

    print("\n" + "="*80)

if __name__ == "__main__":
    main()
