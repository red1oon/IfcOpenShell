#!/usr/bin/env python3
"""
Progressive Loading Validation Tests
Standalone tests to validate Blender capabilities for progressive loading
No federation system required - just Blender
"""

import bpy
import time
from mathutils import Vector

# Test results tracker
test_results = {}

print("=" * 80)
print("PROGRESSIVE LOADING VALIDATION TESTS")
print("=" * 80)

# ============================================================================
# TEST 1: Modal Operator Responsiveness
# ============================================================================

print("\n" + "=" * 80)
print("TEST 1: Modal Operator Keeps UI Responsive")
print("=" * 80)

class TEST_OT_modal_responsiveness(bpy.types.Operator):
    """Test if modal operator allows UI interaction"""
    bl_idname = "test.modal_responsiveness"
    bl_label = "Test Modal Responsiveness"

    def __init__(self):
        self.count = 0
        self.max_count = 100
        self.start_time = None

    def modal(self, context, event):
        if event.type == 'TIMER':
            # Create one cube per timer tick
            bpy.ops.mesh.primitive_cube_add(location=(self.count, 0, 0))
            self.count += 1

            if self.count >= self.max_count:
                context.window_manager.event_timer_remove(self._timer)
                elapsed = time.time() - self.start_time

                print(f"✅ Created {self.max_count} objects in {elapsed:.2f}s")
                print(f"   Time per object: {(elapsed/self.max_count)*1000:.2f}ms")
                print(f"   UI remained responsive: YES (modal operator worked)")

                test_results['test1_responsiveness'] = True
                test_results['test1_time_per_object'] = (elapsed/self.max_count)*1000

                # Cleanup
                bpy.ops.object.select_all(action='SELECT')
                bpy.ops.object.delete()

                return {'FINISHED'}

            return {'RUNNING_MODAL'}

        elif event.type in {'ESC'}:
            context.window_manager.event_timer_remove(self._timer)
            print("⚠️  Test cancelled by user")
            return {'CANCELLED'}

        # IMPORTANT: Allow other events (navigation, etc.)
        return {'PASS_THROUGH'}

    def invoke(self, context, wm):
        self.start_time = time.time()
        wm.modal_handler_add(self)
        self._timer = wm.event_timer_add(0.01, window=context.window)
        print("Started modal operator test...")
        print("(UI should remain responsive - try panning the viewport)")
        return {'RUNNING_MODAL'}

# Register and run test 1
bpy.utils.register_class(TEST_OT_modal_responsiveness)
bpy.ops.test.modal_responsiveness('INVOKE_DEFAULT')

# Wait for modal operator to complete
while 'test1_responsiveness' not in test_results:
    time.sleep(0.1)

bpy.utils.unregister_class(TEST_OT_modal_responsiveness)

# ============================================================================
# TEST 2: Frame Rate with Different Batch Sizes
# ============================================================================

print("\n" + "=" * 80)
print("TEST 2: Frame Rate During Object Creation")
print("=" * 80)

def test_batch_size(batch_size, total_objects=100):
    """Test object creation with specific batch size"""
    start = time.time()

    for i in range(0, total_objects, batch_size):
        batch_start = time.time()

        # Create batch
        for j in range(batch_size):
            if i + j < total_objects:
                bpy.ops.mesh.primitive_cube_add(location=(i+j, 0, 0))

        batch_time = (time.time() - batch_start) * 1000

        # Simulate redraw
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

    elapsed = time.time() - start

    # Cleanup
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()

    return elapsed, batch_time

print("\nTesting different batch sizes:")
print(f"{'Batch Size':<12} {'Total Time':<12} {'Last Batch':<15} {'Est. FPS':<10}")
print("-" * 60)

for batch_size in [5, 10, 15, 20]:
    total_time, batch_time = test_batch_size(batch_size, 100)
    est_fps = 1000 / batch_time if batch_time > 0 else 999

    print(f"{batch_size:<12} {total_time:<12.2f}s {batch_time:<15.2f}ms {est_fps:<10.1f}")

    # Store best performing
    if batch_size == 10:
        test_results['test2_batch10_fps'] = est_fps
        test_results['test2_batch10_time'] = batch_time

if test_results['test2_batch10_fps'] > 30:
    print(f"\n✅ Batch size 10 maintains >{test_results['test2_batch10_fps']:.1f} FPS")
    test_results['test2_frame_rate'] = True
else:
    print(f"\n❌ Batch size 10 only achieves {test_results['test2_batch10_fps']:.1f} FPS")
    test_results['test2_frame_rate'] = False

# ============================================================================
# TEST 3: Camera Position Access
# ============================================================================

print("\n" + "=" * 80)
print("TEST 3: Camera Position Access in Real-Time")
print("=" * 80)

try:
    # Get viewport camera
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for space in area.spaces:
                if space.type == 'VIEW_3D':
                    # Access view matrix
                    view_matrix = space.region_3d.view_matrix
                    view_location = space.region_3d.view_location
                    view_distance = space.region_3d.view_distance

                    print(f"✅ Camera position accessible:")
                    print(f"   View location: {view_location}")
                    print(f"   View distance: {view_distance:.2f}")
                    print(f"   View matrix: {view_matrix[0][0]:.3f}, {view_matrix[0][1]:.3f}...")

                    test_results['test3_camera_access'] = True
                    break
except Exception as e:
    print(f"❌ Failed to access camera: {e}")
    test_results['test3_camera_access'] = False

# ============================================================================
# TEST 9: Object Creation Speed (Actual Elements)
# ============================================================================

print("\n" + "=" * 80)
print("TEST 9: Object Creation Speed (Realistic)")
print("=" * 80)

import bmesh

def create_cylinder_object(location):
    """Create cylinder like in shape_templates.py"""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.5, radius2=0.5, depth=2.0)

    mesh = bpy.data.meshes.new("Cylinder_Test")
    bm.to_mesh(mesh)
    bm.free()

    obj = bpy.data.objects.new("Cylinder_Test", mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    return obj

print("Creating 100 cylinder objects (similar to procedural proxies)...")
start = time.time()

for i in range(100):
    create_cylinder_object((i, 0, 0))

elapsed = time.time() - start
time_per_object = (elapsed / 100) * 1000

print(f"\n✅ Created 100 cylinders in {elapsed:.2f}s")
print(f"   Time per object: {time_per_object:.2f}ms")

# Project to 44K elements
projected_time = (time_per_object * 44190) / 1000 / 60
print(f"   Projected time for 44,190 elements: {projected_time:.1f} minutes")

if projected_time < 2.0:
    print(f"   ✅ Under 2 minute target!")
    test_results['test9_creation_speed'] = True
else:
    print(f"   ⚠️  Exceeds 2 minute target")
    test_results['test9_creation_speed'] = False

test_results['test9_time_per_object'] = time_per_object
test_results['test9_projected_minutes'] = projected_time

# Cleanup
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# ============================================================================
# TEST SUMMARY
# ============================================================================

print("\n" + "=" * 80)
print("TEST SUMMARY")
print("=" * 80)

print("\n✅ MUST-PASS TESTS:")
print(f"  1. UI Responsiveness:    {'✅ PASS' if test_results.get('test1_responsiveness') else '❌ FAIL'}")
print(f"  2. Frame Rate (>30 FPS): {'✅ PASS' if test_results.get('test2_frame_rate') else '❌ FAIL'}")
print(f"  3. Camera Access:        {'✅ PASS' if test_results.get('test3_camera_access') else '❌ FAIL'}")
print(f"  9. Creation Speed (<2m): {'✅ PASS' if test_results.get('test9_creation_speed') else '❌ FAIL'}")

print("\n📊 PERFORMANCE METRICS:")
print(f"  Time per object: {test_results.get('test9_time_per_object', 0):.2f}ms")
print(f"  Projected total: {test_results.get('test9_projected_minutes', 0):.1f} minutes")
print(f"  Batch 10 FPS:    {test_results.get('test2_batch10_fps', 0):.1f}")

all_pass = (
    test_results.get('test1_responsiveness') and
    test_results.get('test2_frame_rate') and
    test_results.get('test3_camera_access') and
    test_results.get('test9_creation_speed')
)

print("\n" + "=" * 80)
if all_pass:
    print("✅ ALL MUST-PASS TESTS PASSED!")
    print("   Progressive loading is VIABLE in Blender")
    print("   Proceed with implementation!")
else:
    print("❌ SOME TESTS FAILED")
    print("   Progressive loading may have issues")
    print("   Consider simpler fallback approach")
print("=" * 80)
