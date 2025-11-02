#!/usr/bin/env python3
"""
FAST Federation Load Test
=========================

Tests loading speed WITHOUT slow statistics queries.
Prints progress every step.

Usage:
    ~/blender-4.5.3/blender --background --python test_fast_load.py
"""

import bpy
import sys
import time
import os
from pathlib import Path

# Add paths
sys.path.insert(0, '/home/red1/Projects/IfcOpenShell/src')
sys.path.insert(0, '/home/red1/Projects/IfcOpenShell/src/bonsai')

# Database path
DB_PATH = os.getenv('DB_PATH', "/home/red1/Documents/bonsai/DatabaseFiles/IFCmigrated_IFC4_v2.db")

print(f"\n{'='*80}")
print(f"FAST LOAD TEST")
print(f"{'='*80}")
print(f"Database: {DB_PATH}\n")

# Check database exists
if not Path(DB_PATH).exists():
    print(f"❌ Database not found: {DB_PATH}")
    sys.exit(1)

# Clear scene
print("Clearing scene...")
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

try:
    from bonsai.bim.module.federation.loader import FederationLoader

    print("\nCreating FederationLoader...")
    start_total = time.time()

    loader = FederationLoader(DB_PATH)
    loader.stage2_progressive = False  # Use tessellation
    loader.stage2_gpu_instancing = True  # Use GPU instancing

    print("Starting load_stage2()...")
    print("(This will print progress from the loader)\n")

    start_load = time.time()
    objects = loader.load_stage2()
    load_duration = time.time() - start_load

    total_duration = time.time() - start_total

    print(f"\n{'='*80}")
    print(f"RESULTS")
    print(f"{'='*80}")
    print(f"✅ Objects loaded: {len(objects):,}")
    print(f"✅ Load time: {load_duration:.2f}s")
    print(f"✅ Total time: {total_duration:.2f}s")
    print(f"✅ Performance: {load_duration/max(len(objects),1)*1000:.2f}ms per object")

    # Check materials
    revit_materials = [m for m in bpy.data.materials if m.name.startswith("Revit_")]
    discipline_materials = [m for m in bpy.data.materials if m.name.startswith("Discipline_")]

    print(f"\nMaterials:")
    print(f"  Revit materials: {len(revit_materials):,}")
    print(f"  Discipline fallback: {len(discipline_materials):,}")
    print(f"  Total: {len(revit_materials) + len(discipline_materials):,}")

    # Check objects with materials
    objects_with_materials = sum(1 for obj in objects if obj.data and len(obj.data.materials) > 0)
    print(f"\nObjects with materials: {objects_with_materials:,}/{len(objects):,} ({100*objects_with_materials/max(len(objects),1):.1f}%)")

    # Performance verdict
    ms_per_obj = load_duration / max(len(objects), 1) * 1000
    if ms_per_obj < 1.0:
        verdict = "EXCELLENT"
    elif ms_per_obj < 2.0:
        verdict = "GOOD"
    elif ms_per_obj < 5.0:
        verdict = "ACCEPTABLE"
    else:
        verdict = "SLOW"

    print(f"\n{'='*80}")
    print(f"VERDICT: {verdict}")
    print(f"{'='*80}\n")

    sys.exit(0)

except Exception as e:
    import traceback
    print(f"\n❌ TEST FAILED")
    print(f"Error: {str(e)}\n")
    traceback.print_exc()
    sys.exit(1)
