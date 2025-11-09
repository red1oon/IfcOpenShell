#!/usr/bin/env python3
"""
Create ifc_labels table in the enhanced database.
Provides friendly, readable descriptions for IFC element types.

Usage:
    python3 create_ifc_labels_table.py <database_path>
"""

import sqlite3
import sys
from pathlib import Path

# Friendly labels for IFC classes based on Malaysian construction industry terminology
IFC_LABELS = {
    # Structural Elements
    'IfcBeam': {
        'friendly_label': 'Structural Steel I-Beam',
        'description': 'Hot-rolled steel I-beam or universal beam for structural support',
        'primary_quantity': 'Length',
        'primary_unit': 'M'
    },
    'IfcColumn': {
        'friendly_label': 'Structural Steel Column',
        'description': 'Universal column (UC) or hollow section for vertical load bearing',
        'primary_quantity': 'Length',
        'primary_unit': 'M'
    },
    'IfcSlab': {
        'friendly_label': 'RC Slab - Airport Grade',
        'description': 'Reinforced concrete slab with rebar, formwork, and curing',
        'primary_quantity': 'GrossArea',
        'primary_unit': 'M2'
    },
    'IfcFooting': {
        'friendly_label': 'Concrete Footing',
        'description': 'Reinforced concrete foundation footing',
        'primary_quantity': 'NetVolume',
        'primary_unit': 'M3'
    },

    # Walls
    'IfcWall': {
        'friendly_label': 'Blockwork Wall (150mm)',
        'description': 'Cement block wall, plastered one side',
        'primary_quantity': 'GrossSideArea',
        'primary_unit': 'M2'
    },
    'IfcWallStandardCase': {
        'friendly_label': 'Standard Wall',
        'description': 'Standard blockwork or drywall partition',
        'primary_quantity': 'GrossSideArea',
        'primary_unit': 'M2'
    },
    'IfcCurtainWall': {
        'friendly_label': 'Aluminum Curtain Wall',
        'description': 'Double-glazed aluminum curtain wall system, powder coated',
        'primary_quantity': 'GrossArea',
        'primary_unit': 'M2'
    },

    # Openings & Doors
    'IfcDoor': {
        'friendly_label': 'Door Set - Airport Grade',
        'description': 'Fire-rated door with frame, hardware, access control, and automatic closer',
        'primary_quantity': 'COUNT',
        'primary_unit': 'EA'
    },
    'IfcWindow': {
        'friendly_label': 'Aluminum Window - Airport Spec',
        'description': 'Powder-coated aluminum window, 12mm double glazed, acoustic rating',
        'primary_quantity': 'COUNT',
        'primary_unit': 'EA'
    },

    # Finishes
    'IfcCovering': {
        'friendly_label': 'Floor/Ceiling Finishes',
        'description': 'Granite tiles 600x600 or metal suspended ceiling system',
        'primary_quantity': 'GrossArea',
        'primary_unit': 'M2'
    },
    'IfcRoof': {
        'friendly_label': 'Metal Deck Roofing',
        'description': 'Standing seam metal roof with insulation and waterproofing',
        'primary_quantity': 'GrossArea',
        'primary_unit': 'M2'
    },

    # HVAC - Ductwork
    'IfcDuct': {
        'friendly_label': 'Galvanized Steel Ductwork',
        'description': 'G550 galvanized steel ductwork, 0.6mm thickness, average 400mm diameter',
        'primary_quantity': 'Length',
        'primary_unit': 'M'
    },
    'IfcDuctSegment': {
        'friendly_label': 'Ductwork Segment',
        'description': 'Straight duct segment, galvanized steel',
        'primary_quantity': 'Length',
        'primary_unit': 'M'
    },
    'IfcDuctFitting': {
        'friendly_label': 'Duct Fittings',
        'description': 'Elbows, tees, reducers, and transitions for ductwork',
        'primary_quantity': 'COUNT',
        'primary_unit': 'EA'
    },
    'IfcFlowTerminal': {
        'friendly_label': 'HVAC Terminal Unit',
        'description': 'Fan coil unit (FCU), air handling unit (AHU), or VAV box with BMS integration',
        'primary_quantity': 'COUNT',
        'primary_unit': 'EA'
    },

    # Plumbing - Piping
    'IfcPipe': {
        'friendly_label': 'PVC/HDPE Pipe',
        'description': 'Schedule 40 PVC or HDPE pipe, Class E, average 100mm diameter',
        'primary_quantity': 'Length',
        'primary_unit': 'M'
    },
    'IfcPipeSegment': {
        'friendly_label': 'Pipe Segment',
        'description': 'Straight pipe segment, PVC or HDPE',
        'primary_quantity': 'Length',
        'primary_unit': 'M'
    },
    'IfcPipeFitting': {
        'friendly_label': 'Pipe Fittings',
        'description': 'PVC or brass fittings - elbows, tees, couplings',
        'primary_quantity': 'COUNT',
        'primary_unit': 'EA'
    },

    # Electrical
    'IfcCableCarrier': {
        'friendly_label': 'Cable Tray System (300mm)',
        'description': 'Aluminum ladder-type cable tray system',
        'primary_quantity': 'Length',
        'primary_unit': 'M'
    },
    'IfcCableCarrierSegment': {
        'friendly_label': 'Cable Tray Segment',
        'description': 'Straight cable tray segment, aluminum',
        'primary_quantity': 'Length',
        'primary_unit': 'M'
    },
    'IfcLightFixture': {
        'friendly_label': 'LED Light Fixture - Airport Grade',
        'description': 'Commercial 48W LED fixture with dimming control and emergency backup',
        'primary_quantity': 'COUNT',
        'primary_unit': 'EA'
    },
    'IfcOutlet': {
        'friendly_label': '13A Power Outlet - Airport Spec',
        'description': 'Stainless steel plate with USB charging ports',
        'primary_quantity': 'COUNT',
        'primary_unit': 'EA'
    },

    # Miscellaneous
    'IfcBuildingElementProxy': {
        'friendly_label': 'Misc. Building Elements',
        'description': 'Various fittings, furniture, signage, and specialty items',
        'primary_quantity': 'COUNT',
        'primary_unit': 'EA'
    },
    'IfcPlate': {
        'friendly_label': 'Steel Plate',
        'description': 'Flat steel plate or gusset plate',
        'primary_quantity': 'GrossArea',
        'primary_unit': 'M2'
    },
    'IfcMember': {
        'friendly_label': 'Structural Member',
        'description': 'Bracing, strut, or secondary structural member',
        'primary_quantity': 'Length',
        'primary_unit': 'M'
    },
    'IfcStairFlight': {
        'friendly_label': 'Stair Flight',
        'description': 'Concrete or steel staircase flight',
        'primary_quantity': 'GrossArea',
        'primary_unit': 'M2'
    },
    'IfcRampFlight': {
        'friendly_label': 'Ramp Flight',
        'description': 'Concrete or steel ramp section',
        'primary_quantity': 'GrossArea',
        'primary_unit': 'M2'
    },
    'IfcRailing': {
        'friendly_label': 'Railing/Balustrade',
        'description': 'Stainless steel or aluminum railing system',
        'primary_quantity': 'Length',
        'primary_unit': 'M'
    },
}


def create_ifc_labels_table(db_path: Path):
    """Create ifc_labels table and populate with friendly descriptions."""

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Drop existing table if exists
    cursor.execute("DROP TABLE IF EXISTS ifc_labels")

    # Create table
    cursor.execute("""
        CREATE TABLE ifc_labels (
            ifc_class TEXT PRIMARY KEY,
            friendly_label TEXT NOT NULL,
            description TEXT,
            primary_quantity TEXT,
            primary_unit TEXT
        )
    """)

    # Insert all labels
    for ifc_class, data in IFC_LABELS.items():
        cursor.execute("""
            INSERT INTO ifc_labels (ifc_class, friendly_label, description, primary_quantity, primary_unit)
            VALUES (?, ?, ?, ?, ?)
        """, (
            ifc_class,
            data['friendly_label'],
            data['description'],
            data['primary_quantity'],
            data['primary_unit']
        ))

    conn.commit()

    # Verify
    cursor.execute("SELECT COUNT(*) FROM ifc_labels")
    count = cursor.fetchone()[0]

    print(f"✓ Created ifc_labels table with {count} entries")

    # Show sample
    cursor.execute("SELECT * FROM ifc_labels LIMIT 5")
    print("\nSample entries:")
    print("-" * 80)
    for row in cursor.fetchall():
        print(f"{row[0]:30} → {row[1]}")

    conn.close()

    return count


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 create_ifc_labels_table.py <database_path>")
        print("\nExample:")
        print("  python3 create_ifc_labels_table.py ~/Documents/bonsai/DatabaseFiles/sample_properties_enhanced.db")
        sys.exit(1)

    db_path = Path(sys.argv[1])

    if not db_path.exists():
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)

    print(f"Adding ifc_labels table to: {db_path}")
    print("=" * 80)

    count = create_ifc_labels_table(db_path)

    print("=" * 80)
    print(f"✅ Done! Added {count} IFC class labels to database")
    print("\nYou can now query friendly names:")
    print("  SELECT l.friendly_label FROM ifc_labels l WHERE l.ifc_class = 'IfcBeam'")


if __name__ == '__main__':
    main()
