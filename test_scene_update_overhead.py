#!/usr/bin/env python3
"""
Scene Update Overhead Test
Tests different batching strategies for adding objects to Blender scene
"""

import bpy
import time
import bmesh

print("=" * 80)
print("SCENE UPDATE OVERHEAD TEST")
print("=" * 80)

# Cleanup
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

def create_cylinder():
    """Create simple cylinder mesh"""
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=12,
                         radius1=0.5, radius2=0.5, depth=2.0)
    mesh = bpy.data.meshes.new("Cylinder")
    bm.to_mesh(mesh)
    bm.free()
    return mesh

# ============================================================================
# TEST 1: No Batching (Update Scene Every Object)
# ============================================================================

print("\n" + "=" * 80)
print("TEST 1: No Batching (Scene update per object)")
print("=" * 80)

collection = bpy.data.collections.new("Test_NoBatch")
bpy.context.scene.collection.children.link(collection)

start = time.time()

for i in range(500):
    mesh = create_cylinder()
    obj = bpy.data.objects.new(f"NoBatch_{i}", mesh)
    obj.location = (i % 50, i // 50, 0)
    collection.objects.link(obj)

    # Force scene update
    bpy.context.view_layer.update()

    if (i + 1) % 100 == 0:
        print(f"  Created {i + 1}/500...")

elapsed_nobatch = time.time() - start
time_per_obj_nobatch = (elapsed_nobatch / 500) * 1000

print(f"\n✅ No batching: {elapsed_nobatch:.2f}s")
print(f"   Time per object: {time_per_obj_nobatch:.2f}ms")

# Cleanup
bpy.data.batch_remove(list(collection.objects))
bpy.data.collections.remove(collection)

# ============================================================================
# TEST 2: Batch of 10 (Update Scene Every 10 Objects)
# ============================================================================

print("\n" + "=" * 80)
print("TEST 2: Batch of 10 (Scene update every 10 objects)")
print("=" * 80)

collection = bpy.data.collections.new("Test_Batch10")
bpy.context.scene.collection.children.link(collection)

start = time.time()

for i in range(500):
    mesh = create_cylinder()
    obj = bpy.data.objects.new(f"Batch10_{i}", mesh)
    obj.location = (i % 50, i // 50, 0)
    collection.objects.link(obj)

    # Update scene every 10 objects
    if (i + 1) % 10 == 0:
        bpy.context.view_layer.update()

    if (i + 1) % 100 == 0:
        print(f"  Created {i + 1}/500...")

# Final update
bpy.context.view_layer.update()

elapsed_batch10 = time.time() - start
time_per_obj_batch10 = (elapsed_batch10 / 500) * 1000

print(f"\n✅ Batch 10: {elapsed_batch10:.2f}s")
print(f"   Time per object: {time_per_obj_batch10:.2f}ms")

# Cleanup
bpy.data.batch_remove(list(collection.objects))
bpy.data.collections.remove(collection)

# ============================================================================
# TEST 3: Batch of 50 (Update Scene Every 50 Objects)
# ============================================================================

print("\n" + "=" * 80)
print("TEST 3: Batch of 50 (Scene update every 50 objects)")
print("=" * 80)

collection = bpy.data.collections.new("Test_Batch50")
bpy.context.scene.collection.children.link(collection)

start = time.time()

for i in range(500):
    mesh = create_cylinder()
    obj = bpy.data.objects.new(f"Batch50_{i}", mesh)
    obj.location = (i % 50, i // 50, 0)
    collection.objects.link(obj)

    # Update scene every 50 objects
    if (i + 1) % 50 == 0:
        bpy.context.view_layer.update()

    if (i + 1) % 100 == 0:
        print(f"  Created {i + 1}/500...")

# Final update
bpy.context.view_layer.update()

elapsed_batch50 = time.time() - start
time_per_obj_batch50 = (elapsed_batch50 / 500) * 1000

print(f"\n✅ Batch 50: {elapsed_batch50:.2f}s")
print(f"   Time per object: {time_per_obj_batch50:.2f}ms")

# Cleanup
bpy.data.batch_remove(list(collection.objects))
bpy.data.collections.remove(collection)

# ============================================================================
# TEST 4: Deferred Updates (Update Scene ONLY at End)
# ============================================================================

print("\n" + "=" * 80)
print("TEST 4: Deferred Updates (Single scene update at end)")
print("=" * 80)

collection = bpy.data.collections.new("Test_Deferred")
bpy.context.scene.collection.children.link(collection)

start = time.time()

for i in range(500):
    mesh = create_cylinder()
    obj = bpy.data.objects.new(f"Deferred_{i}", mesh)
    obj.location = (i % 50, i // 50, 0)
    collection.objects.link(obj)

    # NO scene updates during creation!

    if (i + 1) % 100 == 0:
        print(f"  Created {i + 1}/500...")

# Single update at end
bpy.context.view_layer.update()

elapsed_deferred = time.time() - start
time_per_obj_deferred = (elapsed_deferred / 500) * 1000

print(f"\n✅ Deferred: {elapsed_deferred:.2f}s")
print(f"   Time per object: {time_per_obj_deferred:.2f}ms")

# Cleanup
bpy.data.batch_remove(list(collection.objects))
bpy.data.collections.remove(collection)

# ============================================================================
# COMPARISON & ANALYSIS
# ============================================================================

print("\n" + "=" * 80)
print("SCENE UPDATE OVERHEAD ANALYSIS")
print("=" * 80)

print(f"\n{'Strategy':<20} {'Total Time':<12} {'Per Object':<12} {'Speedup':<10}")
print("-" * 60)

baseline = elapsed_nobatch

strategies = [
    ("No Batching", elapsed_nobatch, time_per_obj_nobatch),
    ("Batch 10", elapsed_batch10, time_per_obj_batch10),
    ("Batch 50", elapsed_batch50, time_per_obj_batch50),
    ("Deferred (Best)", elapsed_deferred, time_per_obj_deferred),
]

for name, total, per_obj in strategies:
    speedup = baseline / total if total > 0 else 1.0
    print(f"{name:<20} {total:<12.2f}s {per_obj:<12.2f}ms {speedup:<10.1f}x")

print("\n📊 FINDINGS:")

overhead_per_update = (elapsed_nobatch - elapsed_deferred) / 500
print(f"  Scene update overhead: ~{overhead_per_update * 1000:.2f}ms per update")

optimal_batch = 50 if elapsed_batch50 < elapsed_batch10 else 10
print(f"  Optimal batch size: {optimal_batch}")

print(f"\n✅ RECOMMENDATION:")
if elapsed_deferred < elapsed_batch10 * 0.8:
    print(f"  Use DEFERRED updates (single update at end)")
    print(f"  Speedup: {baseline / elapsed_deferred:.1f}x faster than per-object updates")
else:
    print(f"  Use BATCHED updates (batch size {optimal_batch})")
    print(f"  Allows progressive display while maintaining good performance")

print("\n⏱️  PROJECTED FOR 44,190 ELEMENTS:")
print(f"  No batching:      {(time_per_obj_nobatch * 44190) / 1000 / 60:.1f} minutes")
print(f"  Batch 10:         {(time_per_obj_batch10 * 44190) / 1000 / 60:.1f} minutes")
print(f"  Batch 50:         {(time_per_obj_batch50 * 44190) / 1000 / 60:.1f} minutes")
print(f"  Deferred (best):  {(time_per_obj_deferred * 44190) / 1000:.0f} seconds")

print("=" * 80)
