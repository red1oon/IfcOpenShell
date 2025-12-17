# PDF to Blender/IFC Topology Extractor

Converts topographic survey PDFs to Blender scenes and IFC files with proper elevation data.

## Features

- **PDF topology extraction** - Extract elevation points from survey PDFs
- **Blender integration** - Places PDF image at Z=40m with 3D points
- **IFC export** - Survey points as IFC elements
- **DXF export** - AutoCAD compatible format

## Usage

```bash
# Convert survey JSON + image to Blender
blender --background --python survey_to_blend.py -- survey.json survey.png output.blend

# Export to IFC
blender --background output.blend --python survey_to_ifc.py

# Export to DXF with text
python insert_text_to_dxf.py input.dxf output.dxf survey.json
```

## Files

- `survey_to_blend.py` - JSON → Blender converter (PDF image at Z=40m)
- `survey_to_ifc.py` - Blender → IFC exporter
- `insert_text_to_dxf.py` - Add text labels to DXF files

## Architecture

- PDF image loaded as reference Empty at elevation 40m
- Survey points created as sphere meshes with custom properties
- Color-coded: Green (ground), Blue (invert), Red (infrastructure)
- Organized in collections for easy management
