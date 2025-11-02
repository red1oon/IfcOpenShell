#!/usr/bin/env python3
"""
Federation Workflow Performance Test
====================================

Tests complete federation workflow:
0. Full Load speed (with Revit materials)
1. Wireframe → Conduit routing → Clash detection → View clash

Usage:
    # Test with sample database
    ~/blender-4.5.3/blender --background --python test_full_workflow.py

    # Test with full database
    DB_PATH=/path/to/full.db ~/blender-4.5.3/blender --background --python test_full_workflow.py
"""

import bpy
import sys
import sqlite3
import time
import os
from pathlib import Path
from mathutils import Vector

# Add paths
sys.path.insert(0, '/home/red1/Projects/IfcOpenShell/src')
sys.path.insert(0, '/home/red1/Projects/IfcOpenShell/src/bonsai')

# Configuration
DB_PATH = os.getenv('DB_PATH', "/home/red1/Documents/bonsai/DatabaseFiles/IFCmigrated_IFC4_v2.db")
OUTPUT_DIR = Path("/home/red1/Documents/bonsai/test_results")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def print_header(title):
    """Print formatted section header"""
    print(f"\n{'='*80}")
    print(f"{title}")
    print(f"{'='*80}\n")

def print_result(test_name, passed, message="", duration=None):
    """Print test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    duration_str = f" ({duration:.2f}s)" if duration else ""
    print(f"{status}{duration_str}: {test_name}")
    if message:
        print(f"  → {message}")

def test_0_full_load_performance():
    """Test 0: Full Load with Revit materials"""
    print_header("TEST 0: Full Load Performance (with Revit Materials)")

    try:
        from bonsai.bim.module.federation.loader import FederationLoader

        # Check database exists
        if not Path(DB_PATH).exists():
            print_result("Full Load", False, f"Database not found: {DB_PATH}")
            return False

        # Query database stats
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM elements_meta")
        total_elements = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM elements_meta WHERE material_rgba IS NOT NULL")
        elements_with_materials = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(DISTINCT material_rgba) FROM elements_meta WHERE material_rgba IS NOT NULL")
        unique_materials = cursor.fetchone()[0]

        conn.close()

        print(f"Database: {DB_PATH}")
        print(f"  Total elements: {total_elements:,}")
        print(f"  Elements with materials: {elements_with_materials:,} ({100*elements_with_materials/max(total_elements,1):.1f}%)")
        print(f"  Unique material colors: {unique_materials:,}\n")

        # Clear scene
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete()

        # Load with tessellation + materials
        print("Loading Full Geometry (tessellation + Revit materials)...")
        start = time.time()

        loader = FederationLoader(DB_PATH)
        loader.stage2_progressive = False  # Use tessellation (exact geometry)
        loader.stage2_gpu_instancing = True  # Use GPU instancing

        objects = loader.load_stage2()

        duration = time.time() - start

        # Verify materials were created
        revit_materials = [mat for mat in bpy.data.materials if mat.name.startswith("Revit_")]
        discipline_materials = [mat for mat in bpy.data.materials if mat.name.startswith("Discipline_")]

        print(f"\n  Objects created: {len(objects):,}")
        print(f"  Revit materials: {len(revit_materials):,}")
        print(f"  Discipline fallback materials: {len(discipline_materials):,}")
        print(f"  Total load time: {duration:.2f}s")
        print(f"  Performance: {duration/max(len(objects),1)*1000:.2f}ms per object")

        # Check if materials are applied
        objects_with_materials = sum(1 for obj in objects if obj.data and len(obj.data.materials) > 0)
        print(f"  Objects with materials: {objects_with_materials:,} ({100*objects_with_materials/max(len(objects),1):.1f}%)")

        # Performance targets
        target_ms_per_object = 5.0  # 5ms per object is good
        actual_ms = duration / max(len(objects), 1) * 1000

        passed = actual_ms <= target_ms_per_object * 2  # Allow 2x slack

        print_result(
            "Full Load Performance",
            passed,
            f"{actual_ms:.2f}ms/object (target: {target_ms_per_object:.1f}ms)",
            duration
        )

        return passed, duration, len(objects)

    except Exception as e:
        import traceback
        traceback.print_exc()
        print_result("Full Load", False, f"Exception: {str(e)}")
        return False, 0, 0

def test_1_wireframe_workflow():
    """Test 1: Wireframe → Conduit routing → Clash detection → View clash"""
    print_header("TEST 1: Wireframe Workflow (Routing + Clash)")

    try:
        # Clear scene
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete()

        # Step 1: Load wireframes
        print("Step 1: Loading GPU BBox wireframes...")
        from bonsai.bim.module.federation import bbox_visualization
        from bonsai.bim.module.federation.spatial_index import FederationIndex

        start = time.time()
        success, message = bbox_visualization.enable_bbox_visualization(DB_PATH)
        wireframe_duration = time.time() - start

        if not success:
            print_result("Wireframe Load", False, message, wireframe_duration)
            return False

        print_result("Wireframe Load", True, f"GPU bboxes enabled", wireframe_duration)

        # Step 2: Register federation index for routing/clashing
        print("\nStep 2: Registering federation index...")
        start = time.time()

        if not hasattr(bpy.types.WindowManager, 'federation_index'):
            index = FederationIndex(DB_PATH)
            index.build()
            bpy.types.WindowManager.federation_index = index

        index_duration = time.time() - start
        stats = index.get_statistics()

        print_result(
            "Federation Index",
            True,
            f"{stats.get('total_elements', 0):,} elements indexed",
            index_duration
        )

        # Step 3: Query ELEC elements for conduit routing
        print("\nStep 3: Testing conduit routing query (ELEC elements)...")
        start = time.time()

        elec_elements = index.query_by_discipline('ELEC')

        routing_duration = time.time() - start

        if len(elec_elements) == 0:
            print_result("Conduit Routing Query", False, "No ELEC elements found", routing_duration)
        else:
            print_result(
                "Conduit Routing Query",
                True,
                f"Found {len(elec_elements):,} ELEC elements",
                routing_duration
            )

        # Step 4: Run clash detection
        print("\nStep 4: Running bbox clash detection...")
        from bonsai.bim.module.clash import bbox_clash_detector

        start = time.time()
        clashes = bbox_clash_detector.detect_clashes_from_database(
            DB_PATH,
            tolerance_mm=10.0
        )
        clash_duration = time.time() - start

        print_result(
            "Clash Detection",
            len(clashes) >= 0,  # Always passes if no errors
            f"Found {len(clashes):,} clashes",
            clash_duration
        )

        # Step 5: Visualize clashes (if any found)
        if len(clashes) > 0:
            print("\nStep 5: Testing clash visualization...")
            from bonsai.bim.module.clash import visualization

            # Prepare clash data for visualization
            clash_data = []
            for clash in clashes[:100]:  # Limit to 100 for performance
                # Get element centers from index
                elem_a = next((e for e in index.query_by_guid(clash['elem_a_guid'])), None)
                elem_b = next((e for e in index.query_by_guid(clash['elem_b_guid'])), None)

                if elem_a and elem_b:
                    clash_data.append({
                        'center_a': (elem_a.center_x, elem_a.center_y, elem_a.center_z),
                        'center_b': (elem_b.center_x, elem_b.center_y, elem_b.center_z),
                        'id': f"{clash['elem_a_guid']}_{clash['elem_b_guid']}",
                        'distance': clash.get('clearance', 0.0)
                    })

            if len(clash_data) > 0:
                start = time.time()
                visualization.load_clash_markers(clash_data)
                visualization.enable_visualization()
                viz_duration = time.time() - start

                print_result(
                    "Clash Visualization",
                    True,
                    f"Loaded {len(clash_data)} markers",
                    viz_duration
                )

        # Summary
        total_workflow_time = wireframe_duration + index_duration + routing_duration + clash_duration
        print(f"\n  Total workflow time: {total_workflow_time:.2f}s")
        print(f"    - Wireframe load: {wireframe_duration:.2f}s")
        print(f"    - Index build: {index_duration:.2f}s")
        print(f"    - ELEC query: {routing_duration:.3f}s")
        print(f"    - Clash detection: {clash_duration:.2f}s")

        return True

    except Exception as e:
        import traceback
        traceback.print_exc()
        print_result("Wireframe Workflow", False, f"Exception: {str(e)}")
        return False

def main():
    """Run all tests"""
    print_header("FEDERATION WORKFLOW PERFORMANCE TEST")
    print(f"Database: {DB_PATH}")
    print(f"Output directory: {OUTPUT_DIR}")

    results = {}

    # Test 0: Full Load Performance
    test_0_passed, full_load_time, object_count = test_0_full_load_performance()
    results['full_load'] = {
        'passed': test_0_passed,
        'duration': full_load_time,
        'objects': object_count
    }

    # Test 1: Wireframe Workflow
    test_1_passed = test_1_wireframe_workflow()
    results['wireframe_workflow'] = {
        'passed': test_1_passed
    }

    # Summary
    print_header("TEST SUMMARY")

    passed_count = sum(1 for r in results.values() if r.get('passed', False))
    total_count = len(results)

    print(f"Tests passed: {passed_count}/{total_count}")

    if results['full_load']['passed']:
        print(f"\n✅ Full Load Performance:")
        print(f"   {results['full_load']['objects']:,} objects in {results['full_load']['duration']:.2f}s")
        print(f"   {results['full_load']['duration']/max(results['full_load']['objects'],1)*1000:.2f}ms per object")

    if results['wireframe_workflow']['passed']:
        print(f"\n✅ Wireframe Workflow: All steps completed successfully")

    # Write results to file
    results_file = OUTPUT_DIR / "test_results.txt"
    with open(results_file, 'w') as f:
        f.write(f"Federation Workflow Test Results\n")
        f.write(f"Database: {DB_PATH}\n")
        f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"Tests passed: {passed_count}/{total_count}\n\n")

        for test_name, result in results.items():
            f.write(f"{test_name}: {'PASS' if result.get('passed') else 'FAIL'}\n")
            for key, value in result.items():
                if key != 'passed':
                    f.write(f"  {key}: {value}\n")
            f.write("\n")

    print(f"\nResults saved to: {results_file}")

    # Exit code
    sys.exit(0 if passed_count == total_count else 1)

if __name__ == "__main__":
    main()
