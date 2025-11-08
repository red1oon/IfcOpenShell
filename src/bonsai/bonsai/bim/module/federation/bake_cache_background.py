"""
Background cache baking script for Blender headless mode

This script runs in a separate Blender process to create .blend cache files
without blocking the user's viewport.

Usage:
    blender --background --python bake_cache_background.py -- <db_path> <cache_output> <mode>

Example:
    blender --background --python bake_cache_background.py -- \
        /path/to/database.db \
        /path/to/cache.blend \
        solid
"""

import sys
import os
from pathlib import Path

# Get arguments after '--'
try:
    argv = sys.argv
    argv = argv[argv.index("--") + 1:]  # Get everything after '--'

    db_path = argv[0]
    cache_output = argv[1]
    mode = argv[2] if len(argv) > 2 else "full"

except (ValueError, IndexError):
    print("ERROR: Missing arguments!")
    print("Usage: blender --background --python bake_cache_background.py -- <db_path> <cache_output> <mode>")
    sys.exit(1)

print("\n" + "="*70)
print("BACKGROUND CACHE BAKING")
print("="*70)
print(f"Database: {db_path}")
print(f"Output:   {cache_output}")
print(f"Mode:     {mode}")
print("="*70 + "\n")

# Check database exists
if not os.path.exists(db_path):
    print(f"ERROR: Database not found: {db_path}")
    sys.exit(1)

# Import Blender and blend_cache
import bpy

# Add IfcOpenShell to path (if needed)
ifc_path = str(Path(__file__).parent.parent.parent.parent.parent.parent / "ifcopenshell-python")
if ifc_path not in sys.path:
    sys.path.insert(0, ifc_path)

# Import blend_cache module
from bonsai.bim.module.federation import blend_cache

# Create cache
try:
    print("Starting cache creation...")

    # Progress callback
    def progress_callback(msg):
        print(f"  {msg}")

    blend_cache.create_cache(
        bpy.context,
        db_path,
        mode=mode,
        report_fn=progress_callback
    )

    print(f"\n✅ Cache created successfully: {cache_output}")
    print(f"   File size: {os.path.getsize(cache_output) / (1024**2):.1f} MB")

    # Write completion flag
    completion_flag = f"{cache_output}.complete"
    with open(completion_flag, 'w') as f:
        f.write(f"Cache created successfully at {cache_output}\n")
        f.write(f"Mode: {mode}\n")

    print(f"✅ Completion flag written: {completion_flag}")

except Exception as e:
    import traceback
    print(f"\n❌ Cache creation failed: {e}")
    traceback.print_exc()

    # Write failure flag
    failure_flag = f"{cache_output}.failed"
    with open(failure_flag, 'w') as f:
        f.write(f"Cache creation failed: {e}\n")
        f.write(traceback.format_exc())

    print(f"❌ Failure flag written: {failure_flag}")
    sys.exit(1)

print("\n" + "="*70)
print("BACKGROUND BAKING COMPLETE")
print("="*70)
