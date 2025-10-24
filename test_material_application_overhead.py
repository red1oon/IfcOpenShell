#!/usr/bin/env python3
"""
Material Application Overhead Test
Tests the cost of applying materials to objects
"""

import bpy
import time
import bmesh

print("=" * 80)
print("MATERIAL APPLICATION OVERHEAD TEST")
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
# TEST 1: No Materials (Baseline)
# ============================================================================

print("\n" + "=" * 80)
print("TEST 1: Object Creation WITHOUT Materials (Baseline)")
print("=" * 80)

collection = bpy.data.collections.new("Test_NoMaterial")
bpy.context.scene.collection.children.link(collection)

start = time.time()

for i in range(1000):
    mesh = create_cylinder()
    obj = bpy.data.objects.new(f"NoMat_{i}", mesh)
    obj.location = (i % 50, i // 50, 0)
    collection.objects.link(obj)

elapsed_no_mat = time.time() - start
time_per_obj_no_mat = (elapsed_no_mat / 1000) * 1000

print(f"\n✅ Created 1000 objects (no materials) in {elapsed_no_mat:.3f}s")
print(f"   Time per object: {time_per_obj_no_mat:.3f}ms")

# Cleanup
bpy.data.batch_remove(list(collection.objects))
bpy.data.collections.remove(collection)

# ============================================================================
# TEST 2: Per-Object Unique Materials (Worst Case)
# ============================================================================

print("\n" + "=" * 80)
print("TEST 2: Per-Object UNIQUE Materials (Worst Case)")
print("=" * 80)

collection = bpy.data.collections.new("Test_UniqueMaterials")
bpy.context.scene.collection.children.link(collection)

start = time.time()

for i in range(1000):
    mesh = create_cylinder()
    obj = bpy.data.objects.new(f"UniqueMat_{i}", mesh)
    obj.location = (i % 50, i // 50, 0)
    collection.objects.link(obj)

    # Create UNIQUE material for each object (worst case!)
    mat = bpy.data.materials.new(name=f"Material_{i}")
    mat.diffuse_color = (i/1000, 0.5, 1.0 - i/1000, 1.0)  # Varying color
    obj.data.materials.append(mat)

elapsed_unique_mat = time.time() - start
time_per_obj_unique_mat = (elapsed_unique_mat / 1000) * 1000

print(f"\n✅ Created 1000 objects (unique materials) in {elapsed_unique_mat:.3f}s")
print(f"   Time per object: {time_per_obj_unique_mat:.3f}ms")

material_overhead_unique = time_per_obj_unique_mat - time_per_obj_no_mat
print(f"\n📊 Material creation overhead: {material_overhead_unique:.3f}ms per object")

# Cleanup
bpy.data.batch_remove(list(collection.objects))
bpy.data.collections.remove(collection)

# ============================================================================
# TEST 3: Standard Material Palette (Best Case)
# ============================================================================

print("\n" + "=" * 80)
print("TEST 3: Standard Material Palette (Reused Materials)")
print("=" * 80)

# Create material palette ONCE
MATERIAL_PALETTE = {}
disciplines = ['ELEC', 'FP', 'ACMV', 'SP', 'CW', 'ARC', 'STR', 'PLUMB', 'HVAC', 'DATA']
colors = [
    (1.0, 0.5, 0.0, 1.0),  # ELEC - Orange
    (1.0, 0.0, 0.0, 1.0),  # FP - Red
    (0.0, 0.5, 1.0, 1.0),  # ACMV - Blue
    (0.0, 1.0, 0.5, 1.0),  # SP - Green
    (0.5, 0.0, 1.0, 1.0),  # CW - Purple
    (0.8, 0.8, 0.8, 1.0),  # ARC - Gray
    (0.6, 0.4, 0.2, 1.0),  # STR - Brown
    (0.0, 0.8, 0.8, 1.0),  # PLUMB - Cyan
    (1.0, 1.0, 0.0, 1.0),  # HVAC - Yellow
    (1.0, 0.0, 1.0, 1.0),  # DATA - Magenta
]

print("\nCreating standard material palette...")
palette_start = time.time()
for disc, color in zip(disciplines, colors):
    mat = bpy.data.materials.new(name=f"Standard_{disc}")
    mat.diffuse_color = color
    MATERIAL_PALETTE[disc] = mat
palette_time = time.time() - palette_start

print(f"✅ Created {len(MATERIAL_PALETTE)} standard materials in {palette_time*1000:.2f}ms")

collection = bpy.data.collections.new("Test_StandardMaterials")
bpy.context.scene.collection.children.link(collection)

start = time.time()

for i in range(1000):
    mesh = create_cylinder()
    obj = bpy.data.objects.new(f"StdMat_{i}", mesh)
    obj.location = (i % 50, i // 50, 0)
    collection.objects.link(obj)

    # Reuse material from palette
    discipline = disciplines[i % len(disciplines)]
    obj.data.materials.append(MATERIAL_PALETTE[discipline])

elapsed_std_mat = time.time() - start
time_per_obj_std_mat = (elapsed_std_mat / 1000) * 1000

print(f"\n✅ Created 1000 objects (standard palette) in {elapsed_std_mat:.3f}s")
print(f"   Time per object: {time_per_obj_std_mat:.3f}ms")

material_overhead_std = time_per_obj_std_mat - time_per_obj_no_mat
print(f"\n📊 Material assignment overhead: {material_overhead_std:.3f}ms per object")

# Cleanup
bpy.data.batch_remove(list(collection.objects))
bpy.data.collections.remove(collection)

# ============================================================================
# COMPARISON & ANALYSIS
# ============================================================================

print("\n" + "=" * 80)
print("MATERIAL OVERHEAD ANALYSIS")
print("=" * 80)

print(f"\n{'Method':<30} {'Time/Object':<15} {'Overhead':<15} {'Speedup':<10}")
print("-" * 75)

methods = [
    ("No Materials (baseline)", time_per_obj_no_mat, 0, 1.0),
    ("Unique Materials (worst)", time_per_obj_unique_mat, material_overhead_unique, time_per_obj_unique_mat / time_per_obj_no_mat),
    ("Standard Palette (best)", time_per_obj_std_mat, material_overhead_std, time_per_obj_unique_mat / time_per_obj_std_mat),
]

for name, time_val, overhead, speedup in methods:
    print(f"{name:<30} {time_val:<15.3f}ms {overhead:<15.3f}ms {speedup:<10.1f}x")

print(f"\n📊 KEY FINDINGS:")
print(f"  Material creation cost:  {material_overhead_unique:.3f}ms per unique material")
print(f"  Material reuse cost:     {material_overhead_std:.3f}ms per assignment")
print(f"  Palette vs Unique:       {time_per_obj_unique_mat / time_per_obj_std_mat:.1f}x faster")

print(f"\n⏱️  PROJECTED FOR 44,190 ELEMENTS:")

unique_mat_time = (time_per_obj_unique_mat * 44190) / 1000
std_mat_time = (time_per_obj_std_mat * 44190) / 1000
no_mat_time = (time_per_obj_no_mat * 44190) / 1000

print(f"  No materials:           {no_mat_time:.1f} seconds")
print(f"  Unique materials:       {unique_mat_time:.1f} seconds ({unique_mat_time/60:.1f} minutes)")
print(f"  Standard palette:       {std_mat_time:.1f} seconds")
print(f"  {'─' * 50}")
print(f"  Time SAVED by palette:  {unique_mat_time - std_mat_time:.1f} seconds!")

print(f"\n✅ RECOMMENDATION:")
if material_overhead_std < 0.1:
    print(f"  ✅ Standard material palette adds NEGLIGIBLE overhead (<0.1ms)")
    print(f"  ✅ Use standard palette - saves {unique_mat_time - std_mat_time:.0f}s over unique materials!")
elif material_overhead_std < 1.0:
    print(f"  ✅ Standard palette acceptable ({material_overhead_std:.2f}ms overhead)")
    print(f"  ✅ Much better than unique materials ({unique_mat_time - std_mat_time:.0f}s savings)")
else:
    print(f"  ⚠️  Material assignment still has overhead ({material_overhead_std:.2f}ms)")
    print(f"  💡 Consider loading without materials, add later on-demand")

print("=" * 80)
