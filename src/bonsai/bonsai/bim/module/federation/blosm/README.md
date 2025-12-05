# BLOSM to IFC/GI Conversion Scripts

Scripts for converting BLOSM (Blender OpenStreetMap) data to IFC and GI (Geometry Instancing) databases.

## Overview

These scripts enable the workflow: **OSM → BLOSM → IFC → GI Database → Bonsai Federation**

## Scripts

### 1. `diagnose_coords.py`
**Purpose**: Analyze coordinate ranges and scene bounds before conversion

**Usage**:
```bash
~/blender-4.5.0/blender --background your_blosm.blend --python diagnose_coords.py
```

**Output**:
- Scene bounds (min/max X/Y/Z)
- Object center coordinates
- Warnings for large offsets or microscopic geometry

### 2. `blosm_to_ifc_500m_crop.py`
**Purpose**: Convert BLOSM data to IFC with 500m radius crop

**Features**:
- Crops geometry to 500m radius around center point
- Edge clipping at circle boundary
- Adds thickness to flat water surfaces (10cm)
- Triangulates complex polygons

**Usage**:
```bash
~/blender-4.5.0/blender --background klang_buildings_blosm.blend \
    --python blosm_to_ifc_500m_crop.py
```

**Output**: `output/klang_river_500m_crop.ifc`

**Configuration**:
```python
CROP_CENTER = (0, 0)  # Adjust to your area of interest
CROP_RADIUS = 500     # 500m radius = 1km diameter
```

### 3. `blosm_to_ifc_fixed_v2.py`
**Purpose**: Convert full BLOSM scene to IFC (no cropping)

**Features**:
- Exports entire scene
- Applies coordinate offset for large scenes
- Handles water geometry with thickness
- World coordinate extraction

**Usage**:
```bash
~/blender-4.5.0/blender --background your_blosm.blend \
    --python blosm_to_ifc_fixed_v2.py
```

**Output**: `klang_river_blosm_fixed.ifc`

### 4. `extract_to_gi_db.py`
**Purpose**: Extract IFC to GI database for Bonsai federation

**Features**:
- Full GI schema with geometry instancing
- R-tree spatial indexing
- Base geometries with BLOB storage
- Element instances with geometry linking
- Compatible with Bonsai federation module

**Usage**:
```bash
~/blender-4.5.0/blender --background \
    --python extract_to_gi_db.py
```

**Output**: `databases/klang_river_gi.db`

**Schema**:
- `elements_meta` - Element metadata
- `element_transforms` - Bounding boxes
- `elements_rtree` - Spatial index
- `base_geometries` - Shared mesh data (BLOB)
- `element_instances` - Element → geometry links
- `global_offset` - Coordinate system
- `site_context` - Georeferencing

## Workflow Example

### Step 1: Import OSM to Blender with BLOSM
1. Install BLOSM addon in Blender
2. Select area on map
3. Import OSM data
4. Save as `.blend` file

### Step 2: Diagnose Coordinates
```bash
~/blender-4.5.0/blender --background klang_buildings_blosm.blend \
    --python diagnose_coords.py
```

Check output for:
- Large coordinate offsets (>10km)
- Scene extents
- Microscopic geometry warnings

### Step 3: Convert to IFC (Cropped)
```bash
~/blender-4.5.0/blender --background klang_buildings_blosm.blend \
    --python blosm_to_ifc_500m_crop.py
```

Output: `output/klang_river_500m_crop.ifc`

### Step 4: Extract to GI Database
```bash
~/blender-4.5.0/blender --background \
    --python extract_to_gi_db.py
```

Output: `databases/klang_river_gi.db`

### Step 5: Load in Bonsai
1. Open Blender with Bonsai
2. Federation → Load GI Database
3. Select `klang_river_gi.db`
4. Enable "Full Geometry Mode"

## Known Issues & Solutions

### Issue: Water mesh has no geometry after evaluation
**Cause**: BLOSM water objects have evaluated mesh that returns 0 vertices

**Solution**: Use original mesh data instead of evaluated
```python
if 'water' in obj.name.lower():
    mesh_data = obj.data  # Use original
else:
    mesh_data = obj_eval.data  # Use evaluated
```

### Issue: Large polygons (1000+ vertices)
**Cause**: BLOSM creates 2 giant faces for entire river

**Solution**: Triangulate before processing
```python
bmesh.ops.triangulate(bm, faces=bm.faces)
```

### Issue: Coordinate offset warnings in Bonsai
**Cause**: OSM coordinates are in large real-world values

**Solution**: Apply offset in conversion script
```python
offset = get_scene_offset()  # Calculate centroid
# Apply to all vertices during extraction
```

## Classification Mapping

```python
CLASSIFICATION = {
    'water': ('IfcGeographicElement', 'USERDEFINED', 'WATER'),
    'building': ('IfcBuildingElementProxy', 'USERDEFINED', 'BUILDING'),
    'road': ('IfcBuildingElementProxy', 'USERDEFINED', 'ROAD'),
    'terrain': ('IfcGeographicElement', 'TERRAIN', 'TERRAIN'),
}
```

## Requirements

- Blender 4.5+ with Bonsai addon
- BLOSM addon installed
- Python packages: numpy, ifcopenshell

## Database Schema Version

**Version**: 1.0 (GI-compatible)

**Compatible with**:
- Bonsai Federation Module v0.8.0+
- IfcOpenShell 0.8.0+

## Reference Implementation

Tested with:
- **Source**: Klang River, Malaysia (OpenStreetMap)
- **Area**: 35km x 19km full scene
- **Cropped**: 500m radius section
- **Elements**: 2 (1 building group, 1 water)
- **Database size**: 100KB with full geometry

## Support

For issues or questions:
1. Check `diagnose_coords.py` output first
2. Verify BLOSM addon is enabled
3. Ensure Blender version compatibility
4. Check database schema with `sqlite3 .tables`

---

**Last Updated**: December 5, 2025
**Author**: Generated for IfcOpenShell/Bonsai federation module
**License**: LGPL-3.0 (matches IfcOpenShell)
