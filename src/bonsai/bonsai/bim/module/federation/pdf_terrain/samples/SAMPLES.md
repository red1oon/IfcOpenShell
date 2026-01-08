# PDF Terrain Sample Files

Demo files showing working PDF Terrain extraction workflow.

## Included Sample Files

### 1. survey_highres_GV.json (426 KB)
**Google Vision API Cache**
- Raw OCR response from Google Cloud Vision
- Contains all detected text with bounding boxes
- Reusable to avoid repeat API calls
- 8,737 text items detected

**Purpose**: Demonstrates API caching - subsequent extractions use this file instead of calling API again.

### 2. survey_highres_extracted.json (203 KB)
**Processed Elevation Data**
- 689 ground elevation points extracted
- Metadata: image dimensions, scale, affine transform
- Calibration corners for coordinate mapping
- Ready for Blender import

**Structure**:
```json
{
  "metadata": {
    "source": "survey_highres.png",
    "image_dimensions": { "width": 9934, "height": 7017 },
    "scale": 0.0423,
    "affine_transform": [[...], [...]]
  },
  "ground_elevations": [
    {
      "id": "GL_0006",
      "x": 6733.0,
      "y": 458.0,
      "z": 46.048,
      "text": "46.048",
      "type": "ground_level"
    },
    ...
  ]
}
```

## Full Sample Files (Download Separately)

Due to file size, these are not included in git repository:

### survey_highres.png (8.6 MB)
**Source Survey Drawing**
- Civil engineering survey plan
- Contains 689 elevation points
- Resolution: 9934 × 7017 pixels
- Elevation range: 40-50 meters

**Download**: Contact maintainer or check GitHub releases

### survey_highres.blend (1.3 MB)
**Generated Blender File**
- 689 orange sphere points
- Reference image overlay at Z=40m
- Collections: Ground_Elevations, Labels
- Orthographic camera setup

**Download**: Generate yourself using the workflow, or check GitHub releases

### survey_highres.ifc (3.7 MB)
**Exported IFC File**
- 689 IfcGeographicElement points
- Survey_Data property sets
- Organized under IfcSite
- Ready for Revit/AutoCAD import

**Download**: Generate yourself using the workflow, or check GitHub releases

## Using These Samples

### Test the Workflow

**Without API Call** (using cached data):
1. Download `survey_highres.png` (source image)
2. Copy both JSON files to same folder as PNG
3. Open Blender → PDF Terrain panel
4. Pick the PNG file
5. Click Generate (will use `_GV.json` cache - no API call)
6. Export IFC

**Expected Result**:
- 689 elevation points generated
- Console shows: "Using GV cache: survey_highres_GV.json - no API charges"
- Points extracted: 689
- Camera positioned at orthographic top-down view

### Inspect the Data

**JSON Files**:
```bash
# View extracted elevations
cat survey_highres_extracted.json | jq '.ground_elevations | length'
# Output: 689

# See first elevation point
cat survey_highres_extracted.json | jq '.ground_elevations[0]'
```

**Blender File** (if you have it):
- Open in Blender 5.0+
- View collections in Outliner
- Select points to see custom properties
- Switch to camera view (Numpad 0)

**IFC File**:
- Import to Revit/AutoCAD
- Select any point → Properties
- See Survey_Data property set
- Elevation values: 40.000 - 50.000m

## Proof of Concept

These files demonstrate:

✓ **OCR Accuracy**: 689 points correctly extracted from survey
✓ **Coordinate Mapping**: Affine transform for precise positioning
✓ **API Caching**: Reuse GV cache to avoid repeat charges
✓ **IFC Export**: Survey data preserved with all properties
✓ **Blender Integration**: Reference image + 3D point cloud
✓ **Workflow Complete**: End-to-end PDF → Blender → IFC

## File Locations in Sample Workflow

After running workflow, you'll have:

```
survey_folder/
├── survey_highres.png              # Input (source)
├── survey_highres_GV.json          # Created on first run (API cache)
├── survey_highres_extracted.json   # Generated data
├── survey_highres.ifc              # Exported output
└── survey_highres.blend            # Saved manually (optional)
```

**Cache Persistence**: Keep `_GV.json` files to avoid repeat API costs!

## Technical Validation

**Coordinate Accuracy**:
- Simple scale transform: 0.0423 m/pixel
- Affine transform: Corrects for rotation/skew
- Points align pixel-perfect with reference image

**Elevation Range**:
- Min: ~40.000m
- Max: ~50.000m
- Pattern: XX.XXX (3 decimal precision)

**Point Distribution**:
- Concentrated along survey traverse lines
- Matches visual inspection of source drawing
- Labels positioned above spheres

---

*These samples validate the PDF Terrain workflow from real survey data*
