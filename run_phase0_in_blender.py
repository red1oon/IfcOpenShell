"""
Blender script to run Phase 0 preprocessing
Run with: blender --background --python run_phase0_in_blender.py
"""

import sys
from pathlib import Path

# Add module paths
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Import after paths are set
from bonsai.bonsai.bim.module.federation.federation_preprocessor import (
    build_guid_discipline_map,
    merge_ifc_files,
    extract_bboxes_from_merged,
    create_federation_database,
    check_disk_space,
    check_memory,
    estimate_output_size,
    print_header
)
import time

# Configuration
IFC_FILES = [
    Path("/home/red1/Documents/bonsai/PythonLibs/IFC/SJTII-ARC-A-TER1-00-R0.ifc"),
    Path("/home/red1/Documents/bonsai/PythonLibs/IFC/SJTII-STR-S-TER1-00-R1.ifc"),
    Path("/home/red1/Documents/bonsai/PythonLibs/IFC/SJTII-CW-A-TER1-00-R0.ifc"),
    Path("/home/red1/Documents/bonsai/PythonLibs/IFC/SJTII-ELEC-A-TER1-00-R0.ifc"),
    Path("/home/red1/Documents/bonsai/PythonLibs/IFC/SJTII-ACMV-A-TER1-00-R0.ifc"),
    Path("/home/red1/Documents/bonsai/PythonLibs/IFC/SJTII-FP-A-TER1-00-R0.ifc"),
    Path("/home/red1/Documents/bonsai/PythonLibs/IFC/SJTII-SP-A-TER1-00-R0.ifc"),
]

DISCIPLINES = ["ARC", "STR", "CW", "ELEC", "ACMV", "FP", "SP"]
DB_PATH = Path("/home/red1/Documents/bonsai/federation_index.db")
MERGED_IFC_PATH = DB_PATH.with_suffix('.ifc')

print_header("PHASE 0: FEDERATION PREPROCESSING WITH COORDINATE DATA")

print(f"\n✅ Phase 0 Changes:")
print(f"  - element_transforms table (position + rotation)")
print(f"  - site_context table (site offset + true north)")
print(f"  - Transform extraction from IFC ObjectPlacement")
print(f"  - Site context from IfcSite/IfcProject")

print(f"\nInput files: {len(IFC_FILES)}")
print(f"Output IFC: {MERGED_IFC_PATH}")
print(f"Output DB: {DB_PATH}")

# Estimate required space
estimated_size_gb = estimate_output_size(IFC_FILES)
required_space_gb = estimated_size_gb + 5

print(f"\nEstimated output size: {estimated_size_gb:.2f} GB")
print(f"Required free space: {required_space_gb:.1f} GB (with safety margin)")

# Check disk space
if not check_disk_space(required_gb=required_space_gb):
    print("\n✗ Aborting due to insufficient disk space")
    sys.exit(1)

# Check memory
if not check_memory(required_gb=8):
    print("\n✗ Aborting due to insufficient memory")
    sys.exit(1)

start_time = time.time()

try:
    # Step 1: Build GUID → Discipline mapping
    print_header("STEP 1: Building GUID → Discipline mapping")
    guid_map = build_guid_discipline_map(IFC_FILES, DISCIPLINES)
    print(f"✓ Mapped {len(guid_map):,} GUIDs to disciplines")

    # Step 2: Merge IFC files
    print_header("STEP 2: Merging IFC files")
    merged_ifc = merge_ifc_files(IFC_FILES, MERGED_IFC_PATH)
    print(f"✓ Created merged IFC: {MERGED_IFC_PATH}")

    # Step 3: Extract bboxes + transforms + site context
    print_header("STEP 3: Extracting geometry + transforms + site context (Phase 0)")
    elements_data = extract_bboxes_from_merged(MERGED_IFC_PATH, guid_map)
    print(f"✓ Extracted {len(elements_data):,} elements with transforms")

    # Step 4: Create database with Phase 0 tables
    print_header("STEP 4: Creating federation database (Phase 0 schema)")
    create_federation_database(DB_PATH, elements_data)
    print(f"✓ Database created: {DB_PATH}")

    # Final summary
    total_duration = time.time() - start_time

    print_header("PHASE 0 COMPLETE!")
    print(f"\n✓ Preprocessing complete with coordinate data!")
    print(f"  Total duration: {total_duration:.1f} seconds ({total_duration/60:.1f} minutes)")
    print(f"\nOutput files:")
    print(f"  Merged IFC: {MERGED_IFC_PATH}")
    print(f"  Federation DB: {DB_PATH}")
    print(f"\n📊 Phase 0 Tables Added:")
    print(f"  ✅ element_transforms - position, rotation for all elements")
    print(f"  ✅ site_context - site offset, true north per discipline")
    print(f"\nNext step:")
    print(f"  Run validation test: python3 test_phase0_database_validation.py")

except Exception as e:
    print(f"\n✗ ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
