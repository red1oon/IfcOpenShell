"""
Convert rebar calculation results to REB discipline elements

This module bridges the gap between:
- Detailed rebar calculations (reinforcement_bars table)
- Federation discipline system (elements_meta, elements_rtree)

Enables:
- REB discipline filtering/visualization
- Clash detection: "ELEC vs REB", "ACMV vs REB"
- Rebar-aware routing algorithms
- Toggle rebar visibility independently from concrete
"""

import sqlite3
import logging
from typing import Dict, List, Any, Tuple
import math
import hashlib
import struct

logger = logging.getLogger(__name__)


def save_rebar_as_discipline(database_path: str, rebar_results: Dict[str, List[Dict]]):
    """
    Create REB discipline elements from rebar calculation results

    Args:
        database_path: Path to federation database
        rebar_results: Results from RebarGenerator.generate_all_rebar()
                      Format: {'slabs': [...], 'beams': [...], 'columns': [...], 'errors': [...]}

    Creates:
        - REB elements in elements_meta (one per bar group)
        - Bounding boxes in elements_rtree (cover-inset)
        - Mapping table linking REB elements to parent STR elements
    """
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row

    try:
        # Create mapping table
        _create_mapping_table(conn)

        # Clear existing REB elements (allow regeneration)
        logger.info("Clearing existing REB discipline elements...")
        _clear_existing_reb_elements(conn)

        # Track statistics
        stats = {
            'slabs': 0,
            'beams': 0,
            'columns': 0,
            'total_reb_elements': 0,
            'total_bars': 0,
            'total_weight_kg': 0
        }

        # Process slabs
        logger.info(f"Creating REB elements for {len(rebar_results['slabs'])} slabs...")
        for slab in rebar_results['slabs']:
            # Main bars
            if _create_reb_element(conn, slab, 'MAIN', slab['main_bars']):
                stats['slabs'] += 1
                stats['total_reb_elements'] += 1
                stats['total_bars'] += slab['main_bars']['count']

            # Distribution bars
            if _create_reb_element(conn, slab, 'DISTRIBUTION', slab['distribution_bars']):
                stats['total_reb_elements'] += 1
                stats['total_bars'] += slab['distribution_bars']['count']

            stats['total_weight_kg'] += slab['total_weight_kg']

        # Process beams
        logger.info(f"Creating REB elements for {len(rebar_results['beams'])} beams...")
        for beam in rebar_results['beams']:
            # Bottom bars
            if _create_reb_element(conn, beam, 'BOTTOM', beam['bottom_bars']):
                stats['beams'] += 1
                stats['total_reb_elements'] += 1
                stats['total_bars'] += beam['bottom_bars']['count']

            # Top bars
            if _create_reb_element(conn, beam, 'TOP', beam['top_bars']):
                stats['total_reb_elements'] += 1
                stats['total_bars'] += beam['top_bars']['count']

            # Stirrups
            if _create_reb_element(conn, beam, 'STIRRUP', beam['stirrups']):
                stats['total_reb_elements'] += 1
                stats['total_bars'] += beam['stirrups']['count']

            stats['total_weight_kg'] += beam['total_weight_kg']

        # Process columns
        logger.info(f"Creating REB elements for {len(rebar_results['columns'])} columns...")
        for column in rebar_results['columns']:
            # Longitudinal bars
            if _create_reb_element(conn, column, 'LONGITUDINAL', column['longitudinal_bars']):
                stats['columns'] += 1
                stats['total_reb_elements'] += 1
                stats['total_bars'] += column['longitudinal_bars']['count']

            # Links (not 'ties' - that's the field name in rebar_standards.py)
            if _create_reb_element(conn, column, 'LINKS', column['links']):
                stats['total_reb_elements'] += 1
                stats['total_bars'] += column['links']['count']

            stats['total_weight_kg'] += column['total_weight_kg']

        conn.commit()

        logger.info("="*80)
        logger.info("REB DISCIPLINE CREATION COMPLETE")
        logger.info("="*80)
        logger.info(f"Created {stats['total_reb_elements']} REB elements:")
        logger.info(f"  - Slabs: {stats['slabs']} elements (main + distribution bars)")
        logger.info(f"  - Beams: {stats['beams']} elements (bottom + top + stirrup bars)")
        logger.info(f"  - Columns: {stats['columns']} elements (longitudinal + ties)")
        logger.info(f"Total bars represented: {stats['total_bars']:,}")
        logger.info(f"Total weight: {stats['total_weight_kg']:.1f} kg ({stats['total_weight_kg']/1000:.2f} tonnes)")
        logger.info("="*80)

        return stats

    except Exception as e:
        conn.rollback()
        logger.exception("Failed to create REB discipline elements")
        raise

    finally:
        conn.close()


def _create_mapping_table(conn):
    """Create table to map REB elements to parent STR elements"""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS rebar_discipline_map (
            rebar_guid TEXT PRIMARY KEY,
            parent_str_guid TEXT NOT NULL,
            bar_type TEXT NOT NULL,
            bar_count INTEGER,
            total_weight_kg REAL,
            diameter_mm INTEGER,
            spacing_mm INTEGER,
            created_timestamp TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _clear_existing_reb_elements(conn):
    """Remove existing REB discipline elements to allow regeneration"""
    # Get IDs and GUIDs of REB elements
    reb_data = [(row[0], row[1]) for row in conn.execute(
        "SELECT id, guid FROM elements_meta WHERE discipline = 'REB'"
    )]

    if reb_data:
        reb_ids = [r[0] for r in reb_data]
        reb_guids = [r[1] for r in reb_data]

        # Delete from rtree
        placeholders = ','.join('?' * len(reb_ids))
        conn.execute(f"DELETE FROM elements_rtree WHERE id IN ({placeholders})", reb_ids)

        # Delete from element_instances (base table, not the view)
        guid_placeholders = ','.join('?' * len(reb_guids))
        conn.execute(f"DELETE FROM element_instances WHERE guid IN ({guid_placeholders})", reb_guids)

        # Note: We don't delete from base_geometries as it's shared (deduplication)
        # Orphaned geometry hashes will be cleaned up by database maintenance if needed

        # Delete from meta
        conn.execute("DELETE FROM elements_meta WHERE discipline = 'REB'")

        # Clear mapping
        conn.execute("DELETE FROM rebar_discipline_map")

        logger.info(f"Cleared {len(reb_ids)} existing REB elements (including geometry)")


def _create_reb_element(conn, parent_element: Dict, bar_type: str, bar_spec: Dict) -> bool:
    """
    Create one REB discipline element for a bar group

    Args:
        conn: Database connection
        parent_element: Rebar spec for parent (has element_guid, element_name, etc.)
        bar_type: MAIN, DISTRIBUTION, BOTTOM, TOP, STIRRUP, LONGITUDINAL, TIES
        bar_spec: Bar specifications (diameter, count, spacing, etc.)

    Returns:
        True if created successfully, False otherwise
    """
    try:
        parent_guid = parent_element['element_guid']
        rebar_guid = f"REB-{parent_guid}-{bar_type}"

        # Get parent element info from database
        parent_row = conn.execute("""
            SELECT id, filepath, element_name
            FROM elements_meta WHERE guid = ?
        """, (parent_guid,)).fetchone()

        if not parent_row:
            logger.warning(f"Parent element {parent_guid} not found in database")
            return False

        parent_id = parent_row['id']
        filepath = parent_row['filepath']
        parent_name = parent_row['element_name']

        # Create descriptive element name
        spacing_text = f"@{bar_spec.get('spacing', 0)}mm " if 'spacing' in bar_spec and bar_spec['spacing'] > 0 else ""
        element_name = (
            f"Y{bar_spec['diameter']} {spacing_text}"
            f"{bar_type.replace('_', ' ').title()} "
            f"({bar_spec['count']} bars)"
        )

        # Insert into elements_meta
        cursor = conn.execute("""
            INSERT INTO elements_meta (
                guid, discipline, ifc_class, element_name, element_type,
                element_description, filepath
            ) VALUES (?, 'REB', 'IfcReinforcingBar', ?, ?, ?, ?)
        """, (
            rebar_guid,
            element_name,
            bar_type,
            f"Reinforcement: Y{bar_spec['diameter']}, {bar_spec['count']} bars",
            filepath
        ))

        reb_id = cursor.lastrowid

        # Get parent bbox
        parent_bbox = conn.execute("""
            SELECT minX, maxX, minY, maxY, minZ, maxZ
            FROM elements_rtree WHERE id = ?
        """, (parent_id,)).fetchone()

        if parent_bbox:
            # Inset bbox by cover to represent rebar zone
            cover_m = parent_element.get('cover_mm', 40) / 1000.0
            minX = parent_bbox['minX'] + cover_m
            maxX = parent_bbox['maxX'] - cover_m
            minY = parent_bbox['minY'] + cover_m
            maxY = parent_bbox['maxY'] - cover_m
            minZ = parent_bbox['minZ'] + cover_m
            maxZ = parent_bbox['maxZ'] - cover_m

            # Ensure bbox is valid (in case element is very thin)
            if minX < maxX and minY < maxY and minZ < maxZ:
                conn.execute("""
                    INSERT INTO elements_rtree (
                        id, minX, maxX, minY, maxY, minZ, maxZ
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (reb_id, minX, maxX, minY, maxY, minZ, maxZ))

                # Generate box geometry for Full Load visualization
                vertices_blob, faces_blob, geometry_hash = _generate_box_geometry(
                    minX, maxX, minY, maxY, minZ, maxZ
                )

                # Insert into base_geometries (if not already exists - deduplication)
                conn.execute("""
                    INSERT OR IGNORE INTO base_geometries (
                        geometry_hash, vertices, faces, vertex_count, face_count
                    ) VALUES (?, ?, ?, ?, ?)
                """, (geometry_hash, vertices_blob, faces_blob, 8, 36))  # 8 vertices, 36 face indices

                # Link element to geometry
                conn.execute("""
                    INSERT INTO element_instances (guid, geometry_hash)
                    VALUES (?, ?)
                """, (rebar_guid, geometry_hash))

            else:
                # Use parent bbox as-is if cover inset would collapse it
                conn.execute("""
                    INSERT INTO elements_rtree (
                        id, minX, maxX, minY, maxY, minZ, maxZ
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (reb_id, parent_bbox['minX'], parent_bbox['maxX'],
                      parent_bbox['minY'], parent_bbox['maxY'],
                      parent_bbox['minZ'], parent_bbox['maxZ']))

                # Generate box geometry using parent bbox
                vertices_blob, faces_blob, geometry_hash = _generate_box_geometry(
                    parent_bbox['minX'], parent_bbox['maxX'],
                    parent_bbox['minY'], parent_bbox['maxY'],
                    parent_bbox['minZ'], parent_bbox['maxZ']
                )

                # Insert into base_geometries (if not already exists - deduplication)
                conn.execute("""
                    INSERT OR IGNORE INTO base_geometries (
                        geometry_hash, vertices, faces, vertex_count, face_count
                    ) VALUES (?, ?, ?, ?, ?)
                """, (geometry_hash, vertices_blob, faces_blob, 8, 36))  # 8 vertices, 36 face indices

                # Link element to geometry
                conn.execute("""
                    INSERT INTO element_instances (guid, geometry_hash)
                    VALUES (?, ?)
                """, (rebar_guid, geometry_hash))

        # Calculate weight for this bar group
        # For stirrups/ties, weight might not be in bar_spec directly
        weight_kg = 0.0
        if 'weight_kg' in bar_spec:
            weight_kg = bar_spec['weight_kg']
        else:
            # Estimate from bar count and length
            length_per_bar = bar_spec.get('length_total_m', 0) / max(bar_spec['count'], 1)
            weight_per_m = _get_bar_weight_per_m(bar_spec['diameter'])
            weight_kg = bar_spec['count'] * length_per_bar * weight_per_m

        # Store mapping to parent and bar details
        conn.execute("""
            INSERT INTO rebar_discipline_map (
                rebar_guid, parent_str_guid, bar_type,
                bar_count, total_weight_kg, diameter_mm, spacing_mm
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            rebar_guid,
            parent_guid,
            bar_type,
            bar_spec['count'],
            weight_kg,
            bar_spec['diameter'],
            bar_spec.get('spacing', 0)
        ))

        return True

    except Exception as e:
        logger.error(f"Failed to create REB element for {bar_type}: {e}")
        return False


def _get_bar_weight_per_m(diameter_mm: int) -> float:
    """
    Calculate steel bar weight per meter

    Formula: Weight = π * (d/2)² * density
    Where: Steel density = 7850 kg/m³

    Args:
        diameter_mm: Bar diameter in mm (e.g., 12 for Y12)

    Returns:
        Weight in kg per meter
    """
    radius_m = (diameter_mm / 1000.0) / 2.0
    area_m2 = math.pi * radius_m * radius_m
    density_steel = 7850  # kg/m³
    return area_m2 * density_steel


def _generate_box_geometry(minX: float, maxX: float, minY: float, maxY: float,
                           minZ: float, maxZ: float) -> Tuple[bytes, bytes, str]:
    """
    Generate simple box geometry for rebar visualization

    Creates a box mesh from bounding box coordinates (same as bbox preview but with geometry).
    This is lightweight and sufficient for Full Load visualization.

    Args:
        minX, maxX, minY, maxY, minZ, maxZ: Bounding box coordinates in meters

    Returns:
        Tuple of (vertices_blob, faces_blob, geometry_hash)
    """
    # Create 8 vertices for box corners
    vertices = [
        minX, minY, minZ,  # 0: bottom-left-front
        maxX, minY, minZ,  # 1: bottom-right-front
        maxX, maxY, minZ,  # 2: bottom-right-back
        minX, maxY, minZ,  # 3: bottom-left-back
        minX, minY, maxZ,  # 4: top-left-front
        maxX, minY, maxZ,  # 5: top-right-front
        maxX, maxY, maxZ,  # 6: top-right-back
        minX, maxY, maxZ   # 7: top-left-back
    ]

    # Create 12 triangles (2 per face, 6 faces)
    faces = [
        # Bottom face (Z-)
        0, 1, 2,  0, 2, 3,
        # Top face (Z+)
        4, 7, 6,  4, 6, 5,
        # Front face (Y-)
        0, 4, 5,  0, 5, 1,
        # Back face (Y+)
        2, 6, 7,  2, 7, 3,
        # Left face (X-)
        0, 3, 7,  0, 7, 4,
        # Right face (X+)
        1, 5, 6,  1, 6, 2
    ]

    # Pack as binary blobs (same format as element_geometry table)
    vertices_blob = struct.pack(f'{len(vertices)}f', *vertices)
    faces_blob = struct.pack(f'{len(faces)}I', *faces)

    # Generate hash for deduplication
    geometry_hash = hashlib.sha256(vertices_blob + faces_blob).hexdigest()[:16]

    return vertices_blob, faces_blob, geometry_hash


def get_reb_statistics(database_path: str) -> Dict[str, Any]:
    """
    Get statistics about REB discipline elements

    Returns:
        Dictionary with counts, weights, bar types
    """
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row

    stats = {
        'total_reb_elements': 0,
        'by_bar_type': {},
        'total_bars': 0,
        'total_weight_kg': 0
    }

    # Count REB elements
    result = conn.execute("SELECT COUNT(*) as count FROM elements_meta WHERE discipline = 'REB'").fetchone()
    stats['total_reb_elements'] = result['count']

    # Group by bar type
    rows = conn.execute("""
        SELECT bar_type, COUNT(*) as count, SUM(bar_count) as total_bars, SUM(total_weight_kg) as weight
        FROM rebar_discipline_map
        GROUP BY bar_type
    """)

    for row in rows:
        stats['by_bar_type'][row['bar_type']] = {
            'element_count': row['count'],
            'bar_count': row['total_bars'],
            'weight_kg': row['weight']
        }
        stats['total_bars'] += row['total_bars'] or 0
        stats['total_weight_kg'] += row['weight'] or 0

    conn.close()
    return stats


if __name__ == '__main__':
    # Test/debug usage
    import sys

    if len(sys.argv) < 2:
        print("Usage: python rebar_to_discipline.py <database_path>")
        print("This will show REB discipline statistics from the database")
        sys.exit(1)

    db_path = sys.argv[1]
    stats = get_reb_statistics(db_path)

    print("\n" + "="*80)
    print("REB DISCIPLINE STATISTICS")
    print("="*80)
    print(f"Total REB elements: {stats['total_reb_elements']}")
    print(f"Total bars represented: {stats['total_bars']:,}")
    print(f"Total weight: {stats['total_weight_kg']:.1f} kg ({stats['total_weight_kg']/1000:.2f} tonnes)")

    print("\nBy bar type:")
    for bar_type, data in stats['by_bar_type'].items():
        print(f"  {bar_type:15s}: {data['element_count']:4d} elements, "
              f"{data['bar_count']:6,d} bars, {data['weight_kg']:8.1f} kg")
    print("="*80)
