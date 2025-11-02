#!/usr/bin/env python3
"""
Test Fast Full Load with Database Materials
============================================

Tests procedural boxes + real Revit materials from DB.
Should be fast (~5-6s) and show real material colors.

Usage:
    ~/blender-4.5.3/blender --background --python test_db_materials.py
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
print(f"FAST FULL LOAD TEST - Database Materials")
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

    # FAST FULL LOAD CONFIGURATION
    loader.stage2_progressive = True  # Use procedural boxes (not tessellation)
    loader.use_database_materials = True  # Use real Revit materials from DB
    loader.stage2_gpu_instancing = True  # GPU instancing always on

    print("\n" + "="*80)
    print("CONFIGURATION:")
    print("  Progressive: True (procedural boxes)")
    print("  DB Materials: True (real Revit colors)")
    print("  GPU Instancing: True")
    print("="*80 + "\n")

    print("Starting load_stage2()...")
    print("(Expected: 5-6s with real Revit materials)\n")

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

    print(f"\nMATERIALS:")
    print(f"  Revit materials: {len(revit_materials):,}")
    print(f"  Discipline fallback: {len(discipline_materials):,}")
    print(f"  Total: {len(revit_materials) + len(discipline_materials):,}")

    # Sample first 5 Revit materials
    if revit_materials:
        print(f"\nSample Revit materials (first 5):")
        for mat in revit_materials[:5]:
            if mat.use_nodes and mat.node_tree:
                bsdf = mat.node_tree.nodes.get('Principled BSDF')
                if bsdf:
                    color = bsdf.inputs['Base Color'].default_value
                    print(f"    {mat.name}: RGB({color[0]:.2f}, {color[1]:.2f}, {color[2]:.2f})")

    # Check objects with materials
    objects_with_materials = sum(1 for obj in objects if obj.data and len(obj.data.materials) > 0)
    print(f"\nObjects with materials: {objects_with_materials:,}/{len(objects):,} ({100*objects_with_materials/max(len(objects),1):.1f}%)")

    # Performance verdict
    ms_per_obj = load_duration / max(len(objects), 1) * 1000
    if ms_per_obj < 0.2:
        verdict = "EXCELLENT (GPU instancing working!)"
    elif ms_per_obj < 0.5:
        verdict = "VERY GOOD"
    elif ms_per_obj < 1.0:
        verdict = "GOOD"
    elif ms_per_obj < 2.0:
        verdict = "ACCEPTABLE"
    else:
        verdict = "SLOW (check if GPU instancing failed)"

    # Speed verdict
    if load_duration < 7:
        speed_verdict = "✅ FAST (procedural boxes working!)"
    elif load_duration < 15:
        speed_verdict = "⚠️  MEDIUM (slower than expected)"
    else:
        speed_verdict = "❌ SLOW (tessellation might be running)"

    print(f"\n{'='*80}")
    print(f"PERFORMANCE VERDICT: {verdict}")
    print(f"SPEED VERDICT: {speed_verdict}")
    print(f"{'='*80}\n")

    # Success criteria
    success = True
    if load_duration > 10:
        print("❌ FAIL: Load time > 10s (should be ~5-6s)")
        success = False
    if len(revit_materials) == 0:
        print("❌ FAIL: No Revit materials found (DB materials not loaded)")
        success = False

    if success:
        print("✅ ALL CHECKS PASSED")
        sys.exit(0)
    else:
        print("❌ SOME CHECKS FAILED")
        sys.exit(1)

except Exception as e:
    import traceback
    print(f"\n❌ TEST FAILED")
    print(f"Error: {str(e)}\n")
    traceback.print_exc()
    sys.exit(1)
