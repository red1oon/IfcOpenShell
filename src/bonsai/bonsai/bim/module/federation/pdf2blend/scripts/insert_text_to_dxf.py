#!/usr/bin/env python3
"""
Insert AI-extracted text into DXF as MTEXT entities

This script:
1. Reads extracted_text_data.json (AI visual extraction from PDF)
2. Opens TopoSurvey.dxf (converted from DWG)
3. Maps normalized coordinates to DXF coordinate system
4. Inserts MTEXT entities on new layer
5. Saves as TopoSurvey_with_text.dxf
"""

import json
import ezdxf
from pathlib import Path

# Configuration
WORK_DIR = Path("/home/red1/Projects/IfcOpenShell/WORK_DIR/DXF")
INPUT_DXF = WORK_DIR / "TopoSurvey.dxf"
OUTPUT_DXF = WORK_DIR / "TopoSurvey_with_text.dxf"
TEXT_DATA_JSON = WORK_DIR / "extracted_text_data.json"

# Layer configuration
TEXT_LAYER = "TEXT_RESTORED"
TEXT_COLOR = 7  # White
TEXT_HEIGHT = 2.5  # Adjust based on drawing scale

def analyze_dxf_extents(doc):
    """Get the bounding box of all entities in modelspace"""
    msp = doc.modelspace()

    try:
        extents = msp.extents()
        min_x, min_y = extents.extmin[:2]
        max_x, max_y = extents.extmax[:2]

        print(f"\nDXF Extents:")
        print(f"  X: {min_x:.2f} to {max_x:.2f} (width: {max_x - min_x:.2f})")
        print(f"  Y: {min_y:.2f} to {max_y:.2f} (height: {max_y - min_y:.2f})")

        return min_x, max_x, min_y, max_y
    except:
        print("Warning: Could not determine extents automatically")
        print("Using default coordinate range (0-100)")
        return 0, 100, 0, 100

def analyze_layers(doc):
    """List all layers in the DXF"""
    print("\nExisting Layers:")
    for layer in doc.layers:
        entities_on_layer = len([e for e in doc.modelspace() if e.dxf.layer == layer.dxf.name])
        print(f"  {layer.dxf.name}: {entities_on_layer} entities (color: {layer.dxf.color})")

def normalize_to_dxf(x_norm, y_norm, min_x, max_x, min_y, max_y):
    """Convert normalized coordinates (0-1) to DXF coordinates"""
    # X is straightforward
    dxf_x = min_x + (x_norm * (max_x - min_x))

    # Y needs inversion (PDF origin top-left, DXF origin bottom-left)
    dxf_y = max_y - (y_norm * (max_y - min_y))

    return dxf_x, dxf_y

def main():
    print("=" * 80)
    print("DXF Text Insertion Script")
    print("=" * 80)

    # Check if DXF exists
    if not INPUT_DXF.exists():
        print(f"\n❌ ERROR: DXF file not found: {INPUT_DXF}")
        print("\nPlease convert TopoSurvey.dwg to DXF first.")
        print("See CONVERSION_INSTRUCTIONS.md for details.")
        return

    # Load text extraction data
    print(f"\n📖 Loading text data from: {TEXT_DATA_JSON}")
    with open(TEXT_DATA_JSON, 'r') as f:
        data = json.load(f)

    text_entities = data['text_entities']
    print(f"   Found {len(text_entities)} text items to insert")

    # Load DXF
    print(f"\n📂 Opening DXF: {INPUT_DXF}")
    doc = ezdxf.readfile(INPUT_DXF)
    msp = doc.modelspace()

    # Analyze existing structure
    analyze_layers(doc)
    min_x, max_x, min_y, max_y = analyze_dxf_extents(doc)

    # Create new layer for restored text
    if TEXT_LAYER not in doc.layers:
        print(f"\n✨ Creating new layer: {TEXT_LAYER}")
        doc.layers.add(TEXT_LAYER, color=TEXT_COLOR)
    else:
        print(f"\n✓ Layer already exists: {TEXT_LAYER}")

    # Insert MTEXT entities
    print(f"\n📝 Inserting {len(text_entities)} MTEXT entities...")

    inserted_count = 0
    for item in text_entities:
        text = item['text']
        x_norm = item['x_norm']
        y_norm = item['y_norm']
        entity_type = item.get('type', 'unknown')

        # Convert normalized coords to DXF coords
        dxf_x, dxf_y = normalize_to_dxf(x_norm, y_norm, min_x, max_x, min_y, max_y)

        # Adjust text height based on type
        height = TEXT_HEIGHT
        if entity_type == 'label':
            height = TEXT_HEIGHT * 1.5  # Larger for labels
        elif entity_type == 'utility':
            height = TEXT_HEIGHT * 1.2

        # Insert MTEXT
        msp.add_mtext(
            text,
            dxfattribs={
                'insert': (dxf_x, dxf_y, 0),
                'char_height': height,
                'layer': TEXT_LAYER,
                'color': TEXT_COLOR
            }
        )

        inserted_count += 1

        # Progress indicator
        if inserted_count % 10 == 0:
            print(f"   Inserted {inserted_count}/{len(text_entities)}...")

    print(f"\n✓ Inserted {inserted_count} MTEXT entities")

    # Save output
    print(f"\n💾 Saving to: {OUTPUT_DXF}")
    doc.saveas(OUTPUT_DXF)

    print("\n" + "=" * 80)
    print("✅ SUCCESS!")
    print("=" * 80)
    print(f"\nOutput file: {OUTPUT_DXF}")
    print(f"\nNext steps:")
    print(f"  1. Open {OUTPUT_DXF.name} in AutoCAD/LibreCAD")
    print(f"  2. Check layer '{TEXT_LAYER}' for restored text")
    print(f"  3. Verify text positioning matches original")
    print(f"  4. Adjust TEXT_HEIGHT in script if text size is wrong")
    print(f"  5. Optionally delete polyline text entities from old layers")
    print()

if __name__ == "__main__":
    main()
