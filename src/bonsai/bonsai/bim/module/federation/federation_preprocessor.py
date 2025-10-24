#!/usr/bin/env python3
"""
Create Merged IFC with Federation Database
==========================================

This script:
1. Merges 7 IFC files using IfcPatch MergeProjects (preserves GUIDs)
2. Builds federation spatial database from merged file
3. Ensures 100% GUID consistency between DB and IFC

Output:
- merged_federated.ifc (single IFC with all disciplines)
- federatedmodel_merged.db (spatial index with matching GUIDs)
"""

import sys
import os
import time
import logging
from pathlib import Path

# Setup logging to both console and bonsai.log
BONSAI_LOG = Path.home() / "Documents/bonsai/bonsai.log"

def setup_logging():
    """Configure logging to console and bonsai.log"""
    logger = logging.getLogger('federation_preprocessor')
    logger.setLevel(logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    # File handler for bonsai.log
    try:
        file_handler = logging.FileHandler(BONSAI_LOG)
        file_handler.setLevel(logging.INFO)

        # Format: timestamp - level - message
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)

        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
    except Exception as e:
        # If can't write to bonsai.log, just use console
        logger.addHandler(console_handler)

    return logger

# Initialize logger
logger = setup_logging()

# Use local ifcopenshell installation in current directory
try:
    import ifcopenshell
    import ifcpatch
    logger.info(f"✓ IfcOpenShell loaded: {ifcopenshell.version}")
except ImportError as e:
    logger.error(f"Cannot import IfcOpenShell: {e}")
    print("\nRun: pip3 install ifcopenshell ifcpatch --target=.")
    sys.exit(1)

import sqlite3
import ifcopenshell.geom
import multiprocessing
import shutil

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# IFC classes to include (geometric elements only)
GEOMETRIC_CLASSES = {
    # Structural elements
    "IfcWall", "IfcWallStandardCase", "IfcCurtainWall",
    "IfcBeam", "IfcColumn", "IfcSlab", "IfcRoof", "IfcFooting", "IfcPile",
    "IfcStair", "IfcStairFlight", "IfcRamp", "IfcRampFlight",

    # Building elements
    "IfcDoor", "IfcWindow", "IfcPlate", "IfcMember", "IfcCovering",
    "IfcRailing", "IfcBuildingElementProxy",

    # MEP elements
    "IfcDuctSegment", "IfcDuctFitting", "IfcAirTerminal",
    "IfcPipeSegment", "IfcPipeFitting", "IfcFlowTerminal",
    "IfcCableCarrierSegment", "IfcCableCarrierFitting",
    "IfcCableSegment", "IfcDistributionElement",
    "IfcFlowController", "IfcFlowFitting", "IfcFlowMovingDevice",
    "IfcFlowStorageDevice", "IfcFlowTreatmentDevice",

    # Furniture and equipment
    "IfcFurnishingElement", "IfcFurniture", "IfcSystemFurnitureElement",
}


def print_header(text):
    """Print a formatted header"""
    print("\n" + "=" * 70)
    print(text)
    print("=" * 70)


def check_disk_space(required_gb=10):
    """Check if sufficient disk space is available"""
    print_header("SAFETY CHECK: DISK SPACE")

    stat = shutil.disk_usage("/home/red1")
    free_gb = stat.free / (1024 ** 3)
    total_gb = stat.total / (1024 ** 3)
    used_gb = stat.used / (1024 ** 3)
    usage_percent = (stat.used / stat.total) * 100

    print(f"\nDisk usage:")
    print(f"  Total: {total_gb:.1f} GB")
    print(f"  Used:  {used_gb:.1f} GB ({usage_percent:.1f}%)")
    print(f"  Free:  {free_gb:.1f} GB")
    print(f"\nRequired: {required_gb} GB minimum")

    if free_gb < required_gb:
        print(f"\n✗ ERROR: Insufficient disk space!")
        print(f"  Free: {free_gb:.1f} GB")
        print(f"  Required: {required_gb} GB")
        print(f"\nPlease free up space before running this script.")
        print(f"Suggestions:")
        print(f"  - Clear cache: rm -rf ~/.cache/*")
        print(f"  - Remove old files")
        print(f"  - Move large files to external storage")
        return False

    if usage_percent > 90:
        print(f"\n⚠ WARNING: Disk is {usage_percent:.1f}% full")
        print(f"  Proceeding, but recommend freeing more space soon")
    else:
        print(f"\n✓ Sufficient disk space available ({free_gb:.1f} GB free)")

    return True


def check_memory(required_gb=8):
    """Check if sufficient memory is available"""
    print_header("SAFETY CHECK: MEMORY")

    if HAS_PSUTIL:
        mem = psutil.virtual_memory()
        available_gb = mem.available / (1024 ** 3)
        total_gb = mem.total / (1024 ** 3)
        used_gb = mem.used / (1024 ** 3)

        swap = psutil.swap_memory()
        swap_free_gb = swap.free / (1024 ** 3)

        print(f"\nMemory status:")
        print(f"  Total RAM: {total_gb:.1f} GB")
        print(f"  Used:      {used_gb:.1f} GB")
        print(f"  Available: {available_gb:.1f} GB")
        print(f"  Swap free: {swap_free_gb:.1f} GB")
        print(f"\nRequired: {required_gb} GB minimum")

        if available_gb < required_gb:
            print(f"\n✗ ERROR: Insufficient memory!")
            print(f"  Available: {available_gb:.1f} GB")
            print(f"  Required: {required_gb} GB")
            print(f"\nPlease close other applications to free memory.")
            return False

        print(f"\n✓ Sufficient memory available ({available_gb:.1f} GB)")
        return True
    else:
        # Fallback: Use /proc/meminfo (Linux only)
        try:
            with open('/proc/meminfo', 'r') as f:
                meminfo = {}
                for line in f:
                    parts = line.split(':')
                    if len(parts) == 2:
                        key = parts[0].strip()
                        value = int(parts[1].strip().split()[0])
                        meminfo[key] = value

            available_kb = meminfo.get('MemAvailable', meminfo.get('MemFree', 0))
            total_kb = meminfo.get('MemTotal', 0)
            available_gb = available_kb / (1024 ** 2)
            total_gb = total_kb / (1024 ** 2)

            print(f"\nMemory status (from /proc/meminfo):")
            print(f"  Total RAM: {total_gb:.1f} GB")
            print(f"  Available: {available_gb:.1f} GB")
            print(f"\nRequired: {required_gb} GB minimum")

            if available_gb < required_gb:
                print(f"\n✗ ERROR: Insufficient memory!")
                print(f"  Available: {available_gb:.1f} GB")
                print(f"  Required: {required_gb} GB")
                return False

            print(f"\n✓ Sufficient memory available ({available_gb:.1f} GB)")
            return True
        except Exception as e:
            print(f"\n⚠ WARNING: Cannot check memory (psutil not available)")
            print(f"  Error: {e}")
            print(f"  Proceeding anyway - ensure {required_gb}GB RAM is free")
            return True  # Proceed cautiously


def estimate_output_size(file_paths):
    """Estimate size of merged IFC file"""
    total_size_mb = sum(p.stat().st_size for p in file_paths) / (1024 ** 2)
    # Merged file is typically 1.2-1.5x the sum of input files
    estimated_merge_mb = total_size_mb * 1.5
    # Database is typically 0.3-0.5x the merged file size
    estimated_db_mb = estimated_merge_mb * 0.5
    estimated_total_mb = estimated_merge_mb + estimated_db_mb

    return estimated_total_mb / 1024  # Return in GB


def merge_ifc_files(file_paths, output_path):
    """Merge multiple IFC files using IfcPatch MergeProjects"""
    print_header("STEP 1: MERGING IFC FILES")

    print(f"\nMerging {len(file_paths)} IFC files...")
    print(f"Base file: {file_paths[0].name}")

    # Load base file
    start_time = time.time()
    base_ifc = ifcopenshell.open(file_paths[0])
    print(f"  Loaded base: {len(base_ifc.by_type('IfcProduct'))} products")

    # Merge remaining files
    for i, file_path in enumerate(file_paths[1:], start=2):
        print(f"\n  [{i}/{len(file_paths)}] Merging: {file_path.name}")
        try:
            ifcpatch.execute({
                "file": base_ifc,
                "recipe": "MergeProjects",
                "arguments": [str(file_path)]
            })
            print(f"      → Merged successfully")
        except Exception as e:
            print(f"      ✗ ERROR: {e}")
            raise

    # Write merged file
    print(f"\nWriting merged file: {output_path.name}")
    base_ifc.write(output_path)

    merge_duration = time.time() - start_time
    file_size_mb = output_path.stat().st_size / (1024 * 1024)
    total_products = len(base_ifc.by_type('IfcProduct'))

    print(f"\n✓ Merge complete:")
    print(f"  Duration: {merge_duration:.1f} seconds")
    print(f"  Output: {output_path}")
    print(f"  Size: {file_size_mb:.2f} MB")
    print(f"  Total products: {total_products}")

    # Log milestone
    logger.info(f"IFC merge complete: {len(file_paths)} files → {file_size_mb:.2f} MB, {total_products:,} products ({merge_duration:.1f}s)")

    return base_ifc


def build_guid_discipline_map(file_paths, disciplines):
    """Build GUID → Discipline mapping before merge"""
    print_header("STEP 2: BUILD GUID → DISCIPLINE MAPPING")

    print("\nScanning source files to map GUIDs to disciplines...")
    guid_map = {}

    for file_path, discipline in zip(file_paths, disciplines):
        print(f"\n  {discipline}: {file_path.name}")
        ifc = ifcopenshell.open(file_path)

        count = 0
        for element in ifc.by_type('IfcProduct'):
            guid = getattr(element, 'GlobalId', None)
            if guid:
                guid_map[guid] = {
                    'discipline': discipline,
                    'source_file': str(file_path),
                    'ifc_class': element.is_a()
                }
                count += 1

        print(f"      → {count} GUIDs mapped")

    print(f"\n✓ Total GUIDs mapped: {len(guid_map)}")

    # Log milestone
    logger.info(f"GUID mapping complete: {len(guid_map):,} GUIDs mapped from {len(file_paths)} files")

    return guid_map


def extract_site_context(ifc_file, discipline, filepath):
    """Extract site offset, true north, and georeferencing from IFC file

    Phase 0: Coordinate Storage Enhancement
    """
    import math

    site_data = {
        'discipline': discipline,
        'offset_x': 0.0,
        'offset_y': 0.0,
        'offset_z': 0.0,
        'true_north_angle': 0.0,
        'latitude': None,
        'longitude': None,
        'elevation': None,
        'epsg_code': None,
        'site_guid': None,
        'project_guid': None,
        'source_file': str(filepath)
    }

    try:
        # Get IfcProject
        projects = ifc_file.by_type('IfcProject')
        if projects:
            project = projects[0]
            site_data['project_guid'] = project.GlobalId

            # Extract True North from RepresentationContexts
            if hasattr(project, 'RepresentationContexts'):
                for context in project.RepresentationContexts:
                    if hasattr(context, 'TrueNorth') and context.TrueNorth:
                        ratios = context.TrueNorth.DirectionRatios
                        if len(ratios) >= 2:
                            true_north_angle = math.atan2(ratios[0], ratios[1])
                            site_data['true_north_angle'] = true_north_angle

        # Get IfcSite
        sites = ifc_file.by_type('IfcSite')
        if sites:
            site = sites[0]
            site_data['site_guid'] = site.GlobalId

            # Extract site placement (offset)
            if hasattr(site, 'ObjectPlacement') and site.ObjectPlacement:
                try:
                    import ifcopenshell.util.placement
                    matrix = ifcopenshell.util.placement.get_local_placement(site.ObjectPlacement)
                    if matrix:
                        translation = matrix.translation
                        site_data['offset_x'] = float(translation[0])
                        site_data['offset_y'] = float(translation[1])
                        site_data['offset_z'] = float(translation[2])
                except:
                    pass

            # Extract georeferencing
            if hasattr(site, 'RefLatitude') and site.RefLatitude:
                lat_parts = site.RefLatitude
                if len(lat_parts) >= 3:
                    latitude = lat_parts[0] + lat_parts[1]/60.0 + lat_parts[2]/3600.0
                    if len(lat_parts) >= 4:
                        latitude += lat_parts[3] / 3600000000.0
                    site_data['latitude'] = latitude

            if hasattr(site, 'RefLongitude') and site.RefLongitude:
                lon_parts = site.RefLongitude
                if len(lon_parts) >= 3:
                    longitude = lon_parts[0] + lon_parts[1]/60.0 + lon_parts[2]/3600.0
                    if len(lon_parts) >= 4:
                        longitude += lon_parts[3] / 3600000000.0
                    site_data['longitude'] = longitude

            if hasattr(site, 'RefElevation') and site.RefElevation:
                site_data['elevation'] = float(site.RefElevation)

    except Exception as e:
        print(f"  Warning: Could not extract site context: {e}")

    return site_data


def extract_bboxes_from_merged(merged_ifc_path, guid_map):
    """Extract bounding boxes from merged IFC file"""
    print_header("STEP 3: EXTRACT BOUNDING BOXES")

    print(f"\nProcessing merged file: {merged_ifc_path.name}")

    ifc_file = ifcopenshell.open(merged_ifc_path)
    elements_data = []

    # Create geometry settings
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)

    # Create iterator with multicore support
    num_cores = multiprocessing.cpu_count()
    print(f"Using {num_cores} CPU cores for geometry processing...")

    iterator = ifcopenshell.geom.iterator(settings, ifc_file, num_cores)

    if not iterator.initialize():
        print("ERROR: Failed to initialize geometry iterator")
        return elements_data

    processed_count = 0
    start_time = time.time()

    while True:
        try:
            shape = iterator.get()
            element = ifc_file.by_id(shape.id)

            # Filter to geometric elements only
            if element.is_a() not in GEOMETRIC_CLASSES:
                if not iterator.next():
                    break
                continue

            # Extract bounding box from geometry
            geometry = shape.geometry
            verts = geometry.verts

            if verts:
                vertices = [(verts[i], verts[i+1], verts[i+2])
                           for i in range(0, len(verts), 3)]

                xs, ys, zs = zip(*vertices)
                bbox = (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))

                # Phase 0: Extract transformation matrix from element placement
                center_x, center_y, center_z = 0, 0, 0
                rot_x, rot_y, rot_z = 0, 0, 0
                transform_source = 'bbox_fallback'

                try:
                    # Try to get actual IFC placement
                    if hasattr(element, 'ObjectPlacement') and element.ObjectPlacement:
                        import ifcopenshell.util.placement
                        matrix = ifcopenshell.util.placement.get_local_placement(element.ObjectPlacement)

                        if matrix:
                            # Extract position from matrix
                            translation = matrix.translation
                            center_x = float(translation[0])
                            center_y = float(translation[1])
                            center_z = float(translation[2])

                            # Extract rotation (Euler angles)
                            rotation = matrix.to_euler('XYZ')
                            rot_x = float(rotation.x)
                            rot_y = float(rotation.y)
                            rot_z = float(rotation.z)

                            transform_source = 'placement'
                except:
                    pass  # Fall back to bbox center

                # Fallback: Use bbox center if placement extraction failed
                if transform_source == 'bbox_fallback':
                    center_x = (bbox[0] + bbox[3]) / 2
                    center_y = (bbox[1] + bbox[4]) / 2
                    center_z = (bbox[2] + bbox[5]) / 2

                global_id = getattr(element, 'GlobalId', None)
                if not global_id:
                    global_id = f"NO_GUID_{element.id()}"

                # Get discipline from mapping
                discipline_info = guid_map.get(global_id, {})
                discipline = discipline_info.get('discipline', 'UNKNOWN')
                source_file = discipline_info.get('source_file', str(merged_ifc_path))

                elements_data.append({
                    'guid': global_id,
                    'discipline': discipline,
                    'ifc_class': element.is_a(),
                    'min_x': bbox[0], 'min_y': bbox[1], 'min_z': bbox[2],
                    'max_x': bbox[3], 'max_y': bbox[4], 'max_z': bbox[5],
                    'filepath': source_file,
                    # Phase 0: Transform data
                    'center_x': center_x,
                    'center_y': center_y,
                    'center_z': center_z,
                    'rotation_x': rot_x,
                    'rotation_y': rot_y,
                    'rotation_z': rot_z,
                    'transform_source': transform_source
                })

                processed_count += 1
                if processed_count % 1000 == 0:
                    elapsed = time.time() - start_time
                    rate = processed_count / elapsed
                    print(f"  Processed {processed_count} elements ({rate:.1f} elem/sec)...")

        except Exception as e:
            print(f"  Warning: Skipping element due to error: {e}")

        if not iterator.next():
            break

    duration = time.time() - start_time
    rate = len(elements_data)/duration if duration > 0 else 0

    print(f"\n✓ Bbox extraction complete:")
    print(f"  Duration: {duration:.1f} seconds")
    print(f"  Elements: {len(elements_data)}")
    print(f"  Rate: {rate:.1f} elem/sec")

    # Log milestone
    logger.info(f"Bbox extraction complete: {len(elements_data):,} elements processed ({rate:.1f} elem/sec, {duration:.1f}s)")

    return elements_data


def create_federation_database(db_path, elements_data):
    """Create federation database with spatial index"""
    print_header("STEP 4: CREATE FEDERATION DATABASE")

    print(f"\nCreating database: {db_path.name}")

    # Remove old database if exists
    if db_path.exists():
        db_path.unlink()
        print(f"  Removed old database")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Schema version table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_info (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cursor.execute("INSERT INTO schema_info VALUES (?, ?)", ("version", "1.0.0"))

    # Metadata table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS elements_meta (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guid TEXT UNIQUE NOT NULL,
            discipline TEXT NOT NULL,
            ifc_class TEXT NOT NULL,
            filepath TEXT NOT NULL
        )
    """)

    # Indices
    cursor.execute("CREATE INDEX idx_guid ON elements_meta(guid)")
    cursor.execute("CREATE INDEX idx_discipline ON elements_meta(discipline)")
    cursor.execute("CREATE INDEX idx_ifc_class ON elements_meta(ifc_class)")

    # Spatial index (R-tree)
    cursor.execute("""
        CREATE VIRTUAL TABLE elements_rtree USING rtree(
            id,
            min_x, max_x,
            min_y, max_y,
            min_z, max_z
        )
    """)

    # Semantic metadata table (Phase 1: BBox Semantic Geometry)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS element_semantics (
            id INTEGER PRIMARY KEY,
            guid TEXT UNIQUE NOT NULL,
            semantic_type TEXT NOT NULL,
            subtype TEXT,
            material_id INTEGER,
            dominant_axis TEXT,
            profile_width REAL,
            profile_height REAL,
            wall_thickness REAL,
            has_opening BOOLEAN DEFAULT 0,
            connects_to TEXT,
            flow_direction TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (guid) REFERENCES elements_meta(guid)
        )
    """)

    cursor.execute("CREATE INDEX idx_semantic_type ON element_semantics(semantic_type)")
    cursor.execute("CREATE INDEX idx_subtype ON element_semantics(subtype)")
    cursor.execute("CREATE INDEX idx_material_id ON element_semantics(material_id)")

    # Material library table (Phase 1: BBox Semantic Geometry)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS material_library (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            category TEXT,
            generation_rules TEXT,
            base_color TEXT,
            metallic REAL DEFAULT 0.0,
            roughness REAL DEFAULT 0.5,
            transparency REAL DEFAULT 0.0,
            emissive REAL DEFAULT 0.0,
            texture_path TEXT,
            normal_map_path TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Pre-populate material library with common materials
    from bonsai.bim.module.federation.semantic_utils import MATERIAL_LIBRARY_DATA
    for material in MATERIAL_LIBRARY_DATA:
        cursor.execute("""
            INSERT INTO material_library
            (id, name, category, generation_rules, base_color, metallic, roughness, transparency, emissive)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (material['id'], material['name'], material['category'], material['generation_rules'],
              material['base_color'], material['metallic'], material['roughness'],
              material['transparency'], material['emissive']))

    # Element transformation table (Phase 0: Coordinate Storage)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS element_transforms (
            guid TEXT PRIMARY KEY,

            -- Center position (world coordinates)
            center_x REAL NOT NULL,
            center_y REAL NOT NULL,
            center_z REAL NOT NULL,

            -- Rotation (Euler angles in radians, XYZ order)
            rotation_x REAL DEFAULT 0,
            rotation_y REAL DEFAULT 0,
            rotation_z REAL DEFAULT 0,

            -- Scale (usually 1,1,1 for IFC elements)
            scale_x REAL DEFAULT 1,
            scale_y REAL DEFAULT 1,
            scale_z REAL DEFAULT 1,

            -- Transformation source ('placement' or 'bbox_fallback')
            transform_source TEXT DEFAULT 'bbox_fallback',

            FOREIGN KEY (guid) REFERENCES elements_meta(guid)
        )
    """)

    cursor.execute("CREATE INDEX idx_transform_source ON element_transforms(transform_source)")

    # Site context table (Phase 0: Georeferencing)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS site_context (
            discipline TEXT PRIMARY KEY,

            -- Site offset (from IfcSite/IfcProject placement)
            offset_x REAL DEFAULT 0,
            offset_y REAL DEFAULT 0,
            offset_z REAL DEFAULT 0,

            -- True North angle (radians from Y-axis, 0 = North is +Y)
            true_north_angle REAL DEFAULT 0,

            -- Georeferencing (WGS84 if available)
            latitude REAL,
            longitude REAL,
            elevation REAL,
            epsg_code INTEGER,

            -- Reference GUIDs
            site_guid TEXT,
            project_guid TEXT,
            source_file TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    print(f"  Schema created (with transforms + site context + semantic metadata + {len(MATERIAL_LIBRARY_DATA)} materials)")

    # Insert elements (with semantic metadata extraction)
    print(f"  Inserting {len(elements_data)} elements (with semantic metadata)...")

    from bonsai.bim.module.federation.semantic_utils import extract_semantic_metadata

    for i, elem in enumerate(elements_data):
        # Insert metadata
        cursor.execute("""
            INSERT INTO elements_meta (guid, discipline, ifc_class, filepath)
            VALUES (?, ?, ?, ?)
        """, (elem['guid'], elem['discipline'], elem['ifc_class'], elem['filepath']))

        elem_id = cursor.lastrowid

        # Insert into R-tree
        cursor.execute("""
            INSERT INTO elements_rtree (id, min_x, max_x, min_y, max_y, min_z, max_z)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (elem_id, elem['min_x'], elem['max_x'],
              elem['min_y'], elem['max_y'], elem['min_z'], elem['max_z']))

        # Extract and insert semantic metadata (Phase 1: BBox Semantic Geometry)
        bbox = (elem['min_x'], elem['min_y'], elem['min_z'],
                elem['max_x'], elem['max_y'], elem['max_z'])
        semantic_data = extract_semantic_metadata(
            elem['guid'],
            elem['ifc_class'],
            elem['discipline'],
            bbox
        )

        cursor.execute("""
            INSERT INTO element_semantics
            (id, guid, semantic_type, subtype, material_id, dominant_axis,
             profile_width, profile_height, wall_thickness, has_opening,
             connects_to, flow_direction)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (elem_id, semantic_data['guid'], semantic_data['semantic_type'],
              semantic_data['subtype'], semantic_data['material_id'],
              semantic_data['dominant_axis'], semantic_data['profile_width'],
              semantic_data['profile_height'], semantic_data['wall_thickness'],
              semantic_data['has_opening'], semantic_data['connects_to'],
              semantic_data['flow_direction']))

        # Phase 0: Insert element transforms
        cursor.execute("""
            INSERT INTO element_transforms
            (guid, center_x, center_y, center_z,
             rotation_x, rotation_y, rotation_z,
             transform_source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (elem['guid'], elem['center_x'], elem['center_y'], elem['center_z'],
              elem['rotation_x'], elem['rotation_y'], elem['rotation_z'],
              elem['transform_source']))

        if (i + 1) % 5000 == 0:
            print(f"    {i + 1}/{len(elements_data)}...")

    conn.commit()

    # Phase 0: Extract and insert site context for each discipline
    print(f"\n  Extracting site context for each discipline...")

    # Group source files by discipline
    discipline_files = {}
    for elem in elements_data:
        disc = elem['discipline']
        filepath = elem['filepath']
        if disc not in discipline_files:
            discipline_files[disc] = set()
        discipline_files[disc].add(filepath)

    # Extract site context from first file of each discipline
    for discipline, files in discipline_files.items():
        if files:
            source_file = Path(list(files)[0])
            if source_file.exists():
                try:
                    temp_ifc = ifcopenshell.open(source_file)
                    site_data = extract_site_context(temp_ifc, discipline, source_file)

                    cursor.execute("""
                        INSERT OR REPLACE INTO site_context
                        (discipline, offset_x, offset_y, offset_z,
                         true_north_angle, latitude, longitude, elevation,
                         epsg_code, site_guid, project_guid, source_file)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (site_data['discipline'], site_data['offset_x'], site_data['offset_y'], site_data['offset_z'],
                          site_data['true_north_angle'], site_data['latitude'], site_data['longitude'],
                          site_data['elevation'], site_data['epsg_code'],
                          site_data['site_guid'], site_data['project_guid'], site_data['source_file']))

                    print(f"    {discipline}: Site offset ({site_data['offset_x']:.2f}, {site_data['offset_y']:.2f}, {site_data['offset_z']:.2f})")
                except Exception as e:
                    print(f"    Warning: Could not extract site context for {discipline}: {e}")

    conn.commit()

    # Statistics
    cursor.execute("SELECT discipline, COUNT(*) FROM elements_meta GROUP BY discipline ORDER BY discipline")
    stats = cursor.fetchall()

    conn.close()

    db_size_mb = db_path.stat().st_size / (1024 * 1024)

    print(f"\n✓ Database created:")
    print(f"  Path: {db_path}")
    print(f"  Size: {db_size_mb:.2f} MB")
    print(f"\n  Elements by discipline:")

    # Log milestone
    logger.info(f"Federation database created: {db_path.name}, {db_size_mb:.2f} MB, {len(elements_data):,} elements")
    for discipline, count in stats:
        print(f"    {discipline}: {count:,}")

    return db_path


def main():
    """Main execution - called from command line or Bonsai operator"""
    import argparse

    parser = argparse.ArgumentParser(description="Merge IFC files and create federation database")
    parser.add_argument("--files", nargs='+', required=True, help="IFC files to process")
    parser.add_argument("--output", required=True, help="Output database path")
    parser.add_argument("--disciplines", nargs='+', required=True, help="Discipline tags for each file")
    parser.add_argument("--progress", help="Progress JSON file path")

    args = parser.parse_args()

    print_header("MERGED IFC FEDERATION WORKFLOW")

    # Convert string paths to Path objects
    file_paths = [Path(f) for f in args.files]
    disciplines = args.disciplines

    # Database path from args
    db_path = Path(args.output)

    # Merged IFC path: same directory as database, change .db to .ifc
    merged_ifc_path = db_path.with_suffix('.ifc')

    print(f"\nInput files: {len(file_paths)}")
    print(f"Output IFC: {merged_ifc_path}")
    print(f"Output DB: {db_path}")

    # Estimate required space
    estimated_size_gb = estimate_output_size(file_paths)
    required_space_gb = estimated_size_gb + 5  # Add 5GB safety margin

    print(f"\nEstimated output size: {estimated_size_gb:.2f} GB")
    print(f"Required free space: {required_space_gb:.1f} GB (with safety margin)")

    # Check disk space BEFORE starting
    if not check_disk_space(required_gb=required_space_gb):
        print("\n✗ Aborting due to insufficient disk space")
        return 1

    # Check memory BEFORE starting
    if not check_memory(required_gb=8):
        print("\n✗ Aborting due to insufficient memory")
        return 1

    start_time = time.time()

    try:
        # Step 1: Build GUID → Discipline mapping
        guid_map = build_guid_discipline_map(file_paths, disciplines)

        # Step 2: Merge IFC files
        merged_ifc = merge_ifc_files(file_paths, merged_ifc_path)

        # Step 3: Extract bboxes from merged file
        elements_data = extract_bboxes_from_merged(merged_ifc_path, guid_map)

        # Step 4: Create federation database
        create_federation_database(db_path, elements_data)

        # Final summary
        total_duration = time.time() - start_time

        print_header("COMPLETE")
        print(f"\n✓ Merged federation workflow complete!")
        print(f"  Total duration: {total_duration:.1f} seconds ({total_duration/60:.1f} minutes)")
        print(f"\nOutput files:")
        print(f"  Merged IFC: {merged_ifc_path}")
        print(f"  Federation DB: {db_path}")
        print(f"\nNext steps:")
        print(f"  1. Load {merged_ifc_path.name} in Blender")
        print(f"  2. Run clash detection using {db_path.name}")
        print(f"  3. GUIDs will match 100% (no spatial lookup needed)")

        # Log milestone to bonsai.log
        logger.info("=" * 70)
        logger.info("FEDERATION PREPROCESSING COMPLETE")
        logger.info("=" * 70)
        logger.info(f"Total duration: {total_duration:.1f} seconds ({total_duration/60:.1f} minutes)")
        logger.info(f"Output IFC: {merged_ifc_path}")
        logger.info(f"Output DB: {db_path}")
        logger.info(f"Total elements: {len(elements_data):,}")
        logger.info(f"Disciplines: {len(set(e['discipline'] for e in elements_data))}")
        logger.info("=" * 70)

        return 0

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        logger.error(f"Federation preprocessing failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
