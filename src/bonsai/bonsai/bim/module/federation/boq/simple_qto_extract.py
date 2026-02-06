"""
Simple QTO Extraction with Malaysian Ringgit (RM) Pricing
Extracts quantities and applies CIDB Malaysia 2024 standard rates
"""

import sqlite3
import sys

# Malaysian Construction Industry Standard Unit Rates (2024)
UNIT_RATES_RM = {
    'IfcDuct': 180.00, 'IfcDuctSegment': 180.00, 'IfcDuctFitting': 450.00,
    'IfcPipe': 65.00, 'IfcPipeSegment': 65.00, 'IfcPipeFitting': 120.00,
    'IfcCableCarrier': 95.00, 'IfcCableCarrierSegment': 95.00,
    'IfcBeam': 850.00, 'IfcColumn': 920.00,
    'IfcSlab': 280.00, 'IfcWall': 195.00, 'IfcWallStandardCase': 195.00,
    'IfcCurtainWall': 850.00, 'IfcCovering': 65.00, 'IfcRoof': 185.00,
    'IfcLightFixture': 380.00, 'IfcOutlet': 85.00, 'IfcDoor': 1850.00,
    'IfcWindow': 1200.00, 'IfcBuildingElementProxy': 500.00,
    'IfcFlowTerminal': 2500.00,
}


def extract_simple_qto(db_path: str):
    """
    Extract basic quantities from BIM database
    Creates one simple table: simple_qto
    """

    conn = sqlite3.connect(db_path)

    print("\n" + "="*80)
    print("SIMPLE QTO EXTRACTION")
    print("="*80 + "\n")

    # Drop and recreate simple table
    print("Creating simple_qto table...")
    conn.execute("DROP TABLE IF EXISTS simple_qto")

    conn.execute("""
    CREATE TABLE simple_qto (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        discipline TEXT,
        ifc_class TEXT,
        storey TEXT,
        measurement_type TEXT,  -- 'LINEAR', 'AREA', 'VOLUME', 'COUNT'
        element_count INTEGER,
        total_quantity REAL,
        uom TEXT,  -- 'M', 'M2', 'M3', 'EA'
        avg_quantity REAL,
        unit_cost_rm REAL,  -- Unit cost in Malaysian Ringgit
        total_cost_rm REAL  -- Total cost (quantity × unit cost)
    )
    """)

    # Backfill storey from spatial_structure into elements_meta if missing
    print("Backfilling storey from spatial_structure...")
    conn.execute("""
        UPDATE elements_meta SET storey = (
            SELECT ss.storey FROM spatial_structure ss
            WHERE ss.guid = elements_meta.guid AND ss.storey IS NOT NULL
        ) WHERE storey IS NULL AND EXISTS (
            SELECT 1 FROM spatial_structure ss
            WHERE ss.guid = elements_meta.guid AND ss.storey IS NOT NULL
        )
    """)
    conn.commit()

    # Extract LINEAR quantities (ducts, pipes, beams, cables)
    print("Extracting linear elements...")
    conn.execute("""
    INSERT INTO simple_qto (discipline, ifc_class, storey, measurement_type, element_count, total_quantity, uom, avg_quantity)
    SELECT
        e.discipline,
        e.ifc_class,
        e.storey,
        'LINEAR' AS measurement_type,
        COUNT(*) AS element_count,
        ROUND(SUM(r.maxZ - r.minZ), 2) AS total_quantity,
        'M' AS uom,
        ROUND(AVG(r.maxZ - r.minZ), 2) AS avg_quantity
    FROM elements_meta e
    JOIN elements_rtree r ON e.id = r.id
    WHERE e.ifc_class IN (
        'IfcDuct', 'IfcDuctSegment', 'IfcDuctFitting',
        'IfcPipe', 'IfcPipeSegment', 'IfcPipeFitting',
        'IfcCableCarrier', 'IfcCableCarrierSegment',
        'IfcBeam', 'IfcColumn'
    )
    GROUP BY e.discipline, e.ifc_class, e.storey
    """)

    # Extract AREA quantities (slabs, walls, roofs)
    print("Extracting area elements...")
    conn.execute("""
    INSERT INTO simple_qto (discipline, ifc_class, storey, measurement_type, element_count, total_quantity, uom, avg_quantity)
    SELECT
        e.discipline,
        e.ifc_class,
        e.storey,
        'AREA' AS measurement_type,
        COUNT(*) AS element_count,
        ROUND(SUM((r.maxX - r.minX) * (r.maxY - r.minY)), 2) AS total_quantity,
        'M2' AS uom,
        ROUND(AVG((r.maxX - r.minX) * (r.maxY - r.minY)), 2) AS avg_quantity
    FROM elements_meta e
    JOIN elements_rtree r ON e.id = r.id
    WHERE e.ifc_class IN (
        'IfcSlab', 'IfcRoof', 'IfcCovering',
        'IfcWall', 'IfcWallStandardCase', 'IfcCurtainWall'
    )
    GROUP BY e.discipline, e.ifc_class, e.storey
    """)

    # Extract VOLUME quantities (concrete, spaces)
    print("Extracting volume elements...")
    conn.execute("""
    INSERT INTO simple_qto (discipline, ifc_class, storey, measurement_type, element_count, total_quantity, uom, avg_quantity)
    SELECT
        e.discipline,
        e.ifc_class,
        e.storey,
        'VOLUME' AS measurement_type,
        COUNT(*) AS element_count,
        ROUND(SUM((r.maxX - r.minX) * (r.maxY - r.minY) * (r.maxZ - r.minZ)), 2) AS total_quantity,
        'M3' AS uom,
        ROUND(AVG((r.maxX - r.minX) * (r.maxY - r.minY) * (r.maxZ - r.minZ)), 2) AS avg_quantity
    FROM elements_meta e
    JOIN elements_rtree r ON e.id = r.id
    WHERE e.ifc_class IN ('IfcSpace', 'IfcFooting', 'IfcPile')
    GROUP BY e.discipline, e.ifc_class, e.storey
    """)

    # Extract COUNT quantities (doors, windows, fixtures)
    print("Extracting count elements...")
    conn.execute("""
    INSERT INTO simple_qto (discipline, ifc_class, storey, measurement_type, element_count, total_quantity, uom, avg_quantity)
    SELECT
        e.discipline,
        e.ifc_class,
        e.storey,
        'COUNT' AS measurement_type,
        COUNT(*) AS element_count,
        COUNT(*) AS total_quantity,
        'EA' AS uom,
        1.0 AS avg_quantity
    FROM elements_meta e
    WHERE e.ifc_class IN (
        'IfcDoor', 'IfcWindow',
        'IfcLightFixture', 'IfcOutlet',
        'IfcFlowTerminal', 'IfcBuildingElementProxy'
    )
    GROUP BY e.discipline, e.ifc_class, e.storey
    """)

    conn.commit()

    # Show summary
    print("\n" + "="*80)
    print("EXTRACTION COMPLETE")
    print("="*80 + "\n")

    cursor = conn.execute("SELECT COUNT(*) FROM simple_qto")
    total_rows = cursor.fetchone()[0]
    print(f"Total QTO line items: {total_rows}\n")

    # Preview data
    print("Sample data:")
    print("-" * 80)
    cursor = conn.execute("""
        SELECT discipline, ifc_class, measurement_type, element_count,
               ROUND(total_quantity, 2), uom
        FROM simple_qto
        ORDER BY total_quantity DESC
        LIMIT 10
    """)

    for row in cursor.fetchall():
        disc, ifc_cls, mtype, count, qty, uom = row
        print(f"{disc:<8} {ifc_cls:<25} {mtype:<10} {count:>6} elements  {qty:>12,.2f} {uom}")

    print("-" * 80 + "\n")

    conn.close()

    # Update costs
    print("\nApplying Malaysian Ringgit (RM) unit costs...")
    update_costs(db_path)

    return total_rows


def update_costs(db_path: str):
    """Apply unit costs and calculate total costs"""
    conn = sqlite3.connect(db_path)

    for ifc_class, unit_rate in UNIT_RATES_RM.items():
        conn.execute("""
            UPDATE simple_qto
            SET unit_cost_rm = ?,
                total_cost_rm = ROUND(total_quantity * ?, 2)
            WHERE ifc_class = ?
        """, (unit_rate, unit_rate, ifc_class))

    conn.commit()

    # Show cost summary
    cursor = conn.execute("""
        SELECT
            SUM(total_cost_rm) AS grand_total,
            COUNT(*) AS items_with_costs
        FROM simple_qto
        WHERE unit_cost_rm IS NOT NULL
    """)

    grand_total, items_count = cursor.fetchone()
    conn.close()

    print(f"  - Applied costs to {items_count} line items")
    print(f"  - Grand Total: RM {grand_total:,.2f}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python simple_qto_extract.py <database_path>")
        print("Example: python simple_qto_extract.py ~/Documents/bonsai/DatabaseFiles/sample_extracted_v3.db")
        sys.exit(1)

    db_path = sys.argv[1]
    extract_simple_qto(db_path)
