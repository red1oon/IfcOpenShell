# Smart Preset Pipeline for 2D to 3D Conversion

## Philosophy
- **Vision AI** provides RAW DATA (text, positions, dimensions)
- **Preset Rules** provide INTELLIGENCE (layout patterns, room relationships)
- **Calibration** bridges pixel space to real-world meters

## Stage 1: Grid Detection

### From Vision API, extract:
1. **Column labels**: A, B, C, D, E with pixel X positions
2. **Row labels**: 1, 2, 3, 4, 5 with pixel Y positions
3. **Dimension text**: "1300", "3100", "3700" near grid lines

### Output: Calibrated Grid
```json
{
  "columns": {
    "A": {"px": 203, "m": 0},
    "B": {"px": 517, "m": 1.3},
    "C": {"px": 1265, "m": 4.4},
    "D": {"px": 2157, "m": 8.1},
    "E": {"px": 2905, "m": 11.2}
  },
  "scale_x": 0.00414 // m per pixel
}
```

## Stage 2: Room Mapping

### From Vision API, extract room labels:
- "DAPUR" → Kitchen
- "BILIK MANDI" → Bathroom
- "BILIK UTAMA" → Master bedroom
- "RUANG TAMU" → Living room
- "ANJUNG" → Porch

### Map to grid cells:
```
Room label pixel position → Nearest grid cell → Room assignment

Example:
"DAPUR" at px(1243, 838) → Cell(B-D, 1-5) → Kitchen in back-center
"BILIK UTAMA" at px(769, 1264) → Cell(A-B, 3-4) → Master bedroom left-middle
```

## Stage 3: Preset Application

### RUMAH RAKYAT Preset Rules:

#### Wall Placement:
| Rule | Condition | Wall Position |
|------|-----------|---------------|
| LEFT_VERT | Kitchen/Bath on left | At column B edge |
| RIGHT_VERT | Bedrooms on right | At column D edge |
| BACK_HORIZ | Kitchen separate | At row 5 |
| FRONT_OPEN | Living to porch | NO wall at row 4 center |

#### Room Relationships:
| If Room A | And Room B | Then |
|-----------|------------|------|
| RUANG TAMU | RUANG MAKAN | Open plan (no wall) |
| RUANG TAMU | ANJUNG | Continuous (no wall) |
| DAPUR | RUANG MAKAN | Wall with door |
| BILIK MANDI | RUANG BASAH | Internal division |

#### Door Placement:
| Room Type | Door Position | Rule |
|-----------|---------------|------|
| Bedroom | Vertical wall | Center of room, facing hall |
| Kitchen | Horizontal wall | Center, facing dining |
| Bathroom | Horizontal wall | Corner, louvre type |

## Confidence Scoring

| Source | Confidence |
|--------|------------|
| Grid dimension from Vision AI | 0.95 |
| Room label position from Vision AI | 0.90 |
| Wall from preset rule | 0.80 |
| Door position from preset rule | 0.75 |
| Interpolated value | 0.60 |

## Implementation Steps

1. **Parse raw JSON** → Extract all text items with positions
2. **Identify grid markers** → Build calibration
3. **Identify room labels** → Map to grid cells
4. **Load preset for house type** → RUMAH_RAKYAT_3BILIK
5. **Apply wall rules** → Generate wall placements
6. **Apply opening rules** → Generate door/window placements
7. **Output final JSON** → Ready for Blender import
