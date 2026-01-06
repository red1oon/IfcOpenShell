# PDF Terrain - Survey to 3D Terrain Generator

Extract elevation points from PDF survey drawings and generate 3D terrain for BIM/CAD workflows.

## What It Does

Converts survey drawings (PDF/PNG) to 3D terrain:
- **Input**: PDF or PNG survey plan with elevation numbers
- **Process**: Google Vision AI extracts elevation points via OCR
- **Output**: 3D point cloud + IFC file for Revit/AutoCAD

**Key Features**:
- Automatic elevation point extraction
- Google Vision API caching (one-time API call per survey)
- Orthographic camera view for technical review
- IFC export with survey data properties
- Reference image overlay in Blender

## Requirements

### 1. Blender
- Blender 5.0 or later
- Bonsai addon installed

### 2. Python Dependencies
Install in Blender's Python environment:

**Windows**:
```cmd
"C:\Program Files\Blender Foundation\Blender 5.0\5.0\python\bin\python.exe" -m pip install google-cloud-vision Pillow
```

**macOS**:
```bash
/Applications/Blender.app/Contents/Resources/5.0/python/bin/python3.11 -m pip install google-cloud-vision Pillow
```

**Linux**:
```bash
<blender_path>/5.0/python/bin/python3.11 -m pip install google-cloud-vision Pillow
```

### 3. Google Vision API Credentials

**Get Credentials**:
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create project (or use existing)
3. Enable Vision API
4. Create Service Account key
5. Download JSON credentials file

**Set Environment Variable**:

**Windows** (PowerShell as Administrator):
```powershell
[System.Environment]::SetEnvironmentVariable('GOOGLE_APPLICATION_CREDENTIALS', 'C:\path\to\credentials.json', 'User')
```

**macOS/Linux**:
```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/credentials.json"
# Add to ~/.bashrc or ~/.zshrc for persistence
```

**Alternative** (Local path method):
Place credentials file at:
```
C:\Dev\bonsai-extensions\WORK_DIR\vision-api.json
```

## Installation

PDF Terrain is integrated into Bonsai. Update your Bonsai addon:

**Option 1: Git Pull** (if installed via git):
```bash
cd <blender_addons>/bonsai
git pull origin v0.8.0  # or your branch
```

**Option 2: Download** (manual install):
1. Download Bonsai from [IfcOpenShell releases](https://github.com/IfcOpenShell/IfcOpenShell/releases)
2. Extract to Blender addons folder
3. Enable in Blender → Edit → Preferences → Add-ons

**Verify Installation**:
- Open Blender
- Press `N` in 3D Viewport to show sidebar
- Look for "PDF Terrain" tab

## Usage

### Workflow

**1. Select Survey File**
- Click **"Pick PDF"** button
- Select PDF or PNG survey drawing
- Image preview loads immediately

**2. Generate Terrain**
- Click **"Generate"** button
- First run: Calls Google Vision API (~$0.01-0.05 cost)
- Subsequent runs: Uses cached data (no API call)
- Wait for processing (30 seconds - 2 minutes)

**Console shows**:
```
[PDF_TERRAIN] Using GV cache: survey_GV.json - no API charges
[PDF_TERRAIN] Point Count: 689
[PDF_TERRAIN] Camera: (210.1, 148.4, 504.2)
```

**3. Export IFC**
- Click **"Export .ifc"** button
- IFC file saved to same folder as input image
- Ready for Revit/AutoCAD import

**4. Save Blender File** (optional)
- File → Save or Save As
- Saves your Blender working file with all data

### What You Get

**In Blender Viewport**:
- Reference image at Z=40m
- Orange sphere points at correct elevations
- Text labels showing Z values
- Orthographic top-down camera view
- Collections: Ground_Elevations, Invert_Levels, Labels

**In IFC File**:
- Each point as IfcGeographicElement
- Survey data properties:
  - PointID
  - Elevation
  - PixelX, PixelY (source coordinates)
  - PointType
- Organized under IfcSite

### For Autodesk Users

**Revit**:
1. Insert → Link IFC
2. Select exported .ifc file
3. View survey points with properties
4. Use elevations for site modeling

**AutoCAD / Civil 3D**:
1. Insert → Import → IFC
2. Points import with elevation data
3. Extract Z values from properties
4. Create surface from points

**Navisworks**:
1. Append → IFC
2. Review point cloud
3. Coordinate with other models

## Understanding the Output

### Elevation Points
- Each sphere = one surveyed elevation
- Orange color = Ground elevation
- Size = 0.05m (5cm) for visibility
- Z coordinate = actual elevation in meters

### Coordinate System
- Origin (0,0) = Bottom-left of survey image
- X-axis = Left to right across survey
- Y-axis = Bottom to top of survey
- Z-axis = Elevation (vertical)
- Units = Meters

### Survey Data Properties
When imported to Autodesk:
- Select point → Properties panel
- See Survey_Data property set:
  - **Elevation**: Height in meters
  - **PointID**: Original point identifier
  - **PixelX/Y**: Source image coordinates

## Troubleshooting

### "Google Vision credentials not found"
**Solution**: Set GOOGLE_APPLICATION_CREDENTIALS environment variable (see Requirements section)

### "ModuleNotFoundError: No module named 'google'"
**Solution**: Install dependencies in Blender's Python:
```cmd
<blender_python>/python.exe -m pip install google-cloud-vision Pillow
```

### "No elevation points extracted"
**Causes**:
- Survey has different elevation format (not XX.XXX pattern)
- Image quality too low
- Elevations outside 40-50m range (adjust code if needed)

**Check**:
- View debug log: `C:\Dev\bonsai-extensions\WORK_DIR\pdf_terrain_debug.log`
- Console shows point count

### Points scattered everywhere
**Fixed in latest version** - was coordinate transform issue

### API charges every time
**Solution**: Check for `<survey_name>_GV.json` cache file in same folder as image. If missing, API is called again. Cache file should persist between runs.

## API Costs

**Google Vision API Pricing** (as of 2025):
- First 1,000 requests/month: FREE
- After that: ~$1.50 per 1,000 images
- Typical survey: $0.01-0.05 per image

**With Caching**:
- First run on an image: 1 API call (charged)
- All subsequent runs: 0 API calls (uses `_GV.json` cache)
- Test with different extraction parameters: No additional cost

**Recommended**:
- Keep `_GV.json` cache files
- Reprocess same survey without charges
- Only delete cache if source image changes

## Tips

1. **High-res images**: Better OCR accuracy (300 DPI recommended)
2. **Cache files**: Keep `_GV.json` to avoid repeat API costs
3. **Test mode**: Use `--from-cache` if you have existing cache
4. **Manual save**: Save .blend when ready (no auto-save)
5. **Multiple surveys**: Process each survey once, cache persists

## Technical Details

**Supported Formats**:
- PDF (converted to PNG at 300 DPI)
- PNG (direct processing)
- JPG/JPEG (supported)

**Elevation Pattern**:
- Regex: `[2-5][0-9][.,][0-9]{2,3}`
- Matches: 40.000 to 59.999
- Handles comma or period decimal separator
- Auto-merges split OCR values

**Scale Calculation**:
- Default: 0.0423 m/pixel (from chainage markers)
- Calculated from survey reference points
- Stored in metadata for consistency

## Support

**Issues**:
- Report bugs: [GitHub Issues](https://github.com/red1oon/IfcOpenShell/issues)
- Bonsai community: [OSArch Forum](https://community.osarch.org/)

**Logs**:
- Debug log: `C:\Dev\bonsai-extensions\WORK_DIR\pdf_terrain_debug.log`
- Blender console: Window → Toggle System Console

## Credits

- **Bonsai**: OpenBIM Blender Add-on
- **IfcOpenShell**: IFC toolkit
- **Google Cloud Vision**: OCR engine

---

*Part of the Bonsai addon for Blender*
*https://github.com/IfcOpenShell/IfcOpenShell*
