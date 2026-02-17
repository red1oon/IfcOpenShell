# Rich Surface Styles — Federation Material System

## What This Does

Loads **real IFC material properties** (transparency, specular, reflectance) from the database `surface_styles` table and creates proper Blender Principled BSDF materials during Full Load.

**Before:** All materials were flat RGBA or discipline-colored boxes.
**After:** Glass is transparent, aluminium is shiny, materials match the original IFC.

## Database Requirements

The loaded database must have a `surface_styles` table (created by `extractIFCtoDB.py`):

```sql
CREATE TABLE IF NOT EXISTS surface_styles (
    style_name TEXT PRIMARY KEY,       -- FK: elements_meta.material_name
    surface_r REAL, surface_g REAL, surface_b REAL,
    transparency REAL DEFAULT 0.0,     -- 0=opaque, 1=fully transparent
    specular_r REAL, specular_g REAL, specular_b REAL,
    specular_ratio REAL,               -- IfcNormalisedRatioMeasure (0-1)
    specular_exponent REAL,            -- sharpness: 12=glass, 128=metal
    reflectance_method TEXT DEFAULT 'NOTDEFINED',
    side TEXT DEFAULT 'BOTH',
    source TEXT
);
```

The loader auto-detects this table. If absent, falls back to flat `material_rgba` from `elements_meta`.

## How It Works

### Data Flow

```
IFC file
  → extractIFCtoDB.py (extract_surface_styles)
    → reference DB: surface_styles table (32 rows for SampleHouse)
      → elements_meta.material_name → surface_styles.style_name (FK)

Full Load (GI button):
  → blend_cache.create_cache()
    → SQL: LEFT JOIN surface_styles ON material_name = style_name
    → style_data dict per element
    → get_or_create_db_material(style_data=...)
      → Principled BSDF with transparency, specular, roughness
```

### IFC → Blender PBR Mapping

| IFC Property | Blender Property | Conversion |
|---|---|---|
| `transparency` (0=opaque, 1=clear) | `Alpha` (1=opaque, 0=clear) | `alpha = 1 - transparency` |
| `transparency > 0` | `mat.blend_method` | Set to `"BLEND"` |
| `transparency > 0` | `mat.diffuse_color[3]` | Set alpha for Solid mode |
| `specular_exponent` (0-128+) | `Roughness` (0-1) | `roughness = 1/(1 + exp*0.07)` |
| `specular_ratio` (0-1) | `Specular IOR Level` | Direct mapping |
| `reflectance_method = "METAL"` | `Metallic` | Set to 0.9 |
| `reflectance_method = "GLASS"` | `Roughness` | Cap at 0.1 |
| `surface_r/g/b` | `Base Color` | Direct RGB |

### Critical: Transparency in Blender 5.0

Two things are required for transparency to render (matches `tool/loader.py:229-231`):

```python
# 1. Set Alpha on Principled BSDF node
bsdf.inputs["Alpha"].default_value = 1 - transparency

# 2. Set blend method on material (CRITICAL — without this, Alpha is ignored)
mat.blend_method = "BLEND"

# 3. Set diffuse_color alpha for Solid viewport mode
mat.diffuse_color = (r, g, b, 1 - transparency)
```

Note: `shadow_method` was removed in Blender 5.0 — do NOT set it.

## Files Modified

| File | Change |
|---|---|
| `stage2_tessellation_loader.py` | `get_or_create_db_material()` — accepts `style_data` dict, creates PBR materials with transparency/specular |
| `stage2_gpu_progressive.py` | SQL query LEFT JOINs `surface_styles`, passes `style_data` to material creator |
| `blend_cache.py` | `create_cache()` — queries material data + surface_styles, assigns materials to cached objects |

## Extraction (DAGCompiler side)

To populate `surface_styles` during extraction:

```bash
# Extract with rich styles (SampleHouse example)
python3 DAGCompiler/python/extractIFCtoDB.py \
    --ifc DAGCompiler/lib/input/IFC/Ifc4_SampleHouse.ifc \
    -o DAGCompiler/lib/input/Ifc4_SampleHouse_extracted.db \
    --exclude IfcOpeningElement,IfcCovering

# Verify
sqlite3 Ifc4_SampleHouse_extracted.db \
    "SELECT style_name, transparency, specular_exponent FROM surface_styles;"
# Glass|0.9|12.0    ← transparent, soft highlight
# Aluminium|0.0|128.0  ← opaque, sharp highlight
```

To enrich an existing DB with styles only:

```bash
python3 DAGCompiler/python/extractIFCtoDB.py \
    --ifc source.ifc --styles-only existing.db
```

## Backward Compatibility

- If `surface_styles` table is missing → falls back to flat `material_rgba` colors
- If `material_rgba` is NULL → falls back to discipline-based colors
- Works with both GI schema (`base_geometries`) and legacy schema (`element_geometry`)
- `Specular IOR Level` input checked with fallback to `Specular` for older Blender

## Typical Style Counts

| Project | Styles | Layers | Elements |
|---|---|---|---|
| SampleHouse (IFC4) | 32 | 19 | 55 |
| Duplex (IFC2x3) | 33 | 41 | 1,085 |
| Terminal (large) | ~200 | ~100 | 51,723 |

Styles are **instanced** (one per unique material name), not per-element. 32 styles serve 55 elements.
