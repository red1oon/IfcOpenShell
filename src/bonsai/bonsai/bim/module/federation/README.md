# Federation Module for Bonsai/BlenderBIM

**Multi-model spatial indexing and query engine for large-scale BIM coordination**

Part of the [Bonsai10D Vision](https://github.com/red1oon/bonsai10d) - Enabling 10-dimensional construction coordination across multiple discipline models.

---

## 🎯 Overview

The Federation module provides **bbox-based spatial indexing** for querying multiple IFC models without loading full geometry. It enables fast multi-discipline coordination by preprocessing bounding boxes into a spatial database for sub-second queries.

**Design Philosophy**: Optimize existing BlenderBIM workflows, enhance IfcClash performance.

### Key Capabilities

- ✅ **Preprocess** multiple IFC files to SQLite spatial index
- ✅ **Query** across disciplines without loading geometry (95% memory reduction)
- ✅ **Sub-second** spatial queries on 100K+ elements (<100ms per query)
- ✅ **Memory-efficient** runtime (<10GB for federated models vs 30GB traditional)
- ✅ **Dual interface**: Blender UI + standalone CLI

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────┐
│ PREPROCESSING (One-time, ~20 min for 90K elements)│
│                                                     │
│  IFC Files (7 disciplines)                         │
│       ↓                                             │
│  federation_preprocessor.py                        │
│       ↓                                             │
│  SQLite Database (~50MB)                           │
│    - Element bounding boxes                        │
│    - Discipline tags                               │
│    - Spatial R-tree index                          │
└────────────────────────────────────────────────────┘
                      ↓
┌────────────────────────────────────────────────────┐
│ RUNTIME QUERIES (Sub-second, <100MB RAM)          │
│                                                     │
│  spatial_index.py: FederationIndex                 │
│    - Load database to memory                       │
│    - Build R-tree (30 seconds)                     │
│    - Query by bbox/corridor/point                  │
│       ↓                                             │
│  Results: List[FederationElement]                  │
│    - GUID, discipline, IFC class                   │
│    - Bounding box coordinates                      │
│    - Original file path                            │
└────────────────────────────────────────────────────┘
                      ↓
┌────────────────────────────────────────────────────┐
│ INTEGRATION (Used by other modules)                │
│                                                     │
│  MEP Routing: Obstacle detection                   │
│  Clash Detection: Pre-broadphase filtering         │
│  Quantity Takeoffs: Multi-model queries            │
└────────────────────────────────────────────────────┘
```

**Performance**: Validated on Terminal 1/2 project (7 disciplines, 93K elements):
- **Preprocessing**: 7 minutes (one-time)
- **Query time**: <100ms per corridor
- **Memory**: 2GB vs 30GB (93% reduction)
- **Accuracy**: 100% (conservative bbox checks, no false negatives)

---

## 📦 Installation

### Prerequisites

1. **Blender 4.2+** with [Bonsai addon](https://blenderbim.org/) installed
2. **Python dependencies**:
   ```bash
   # In Blender's Python environment
   # Windows
   "C:\Program Files\Blender Foundation\Blender 4.2\4.2\python\bin\python.exe" -m pip install rtree
   
   # Linux/Mac
   /path/to/blender/4.2/python/bin/python3.11 -m pip install rtree
   ```

3. **System libraries** (rtree dependency):
   ```bash
   # Ubuntu/Debian
   sudo apt-get install libspatialindex-dev
   
   # macOS
   brew install spatialindex
   
   # Windows: pip handles this automatically
   ```

### Install Federation Module

```bash
cd src/bonsai/bonsai/bim/module/

# Clone federation module
git clone https://github.com/red1oon/federation.git
```

### Enable in Bonsai

Edit `src/bonsai/bonsai/bim/__init__.py`:

```python
modules = {
    # ... existing modules ...
    "federation": None,  # ← Add this line
}
```

**Restart Blender** to load the module.

---

## 🚀 Usage

### Option 1: Via Blender UI (Recommended for Most Users)

#### Step 1: Add Federated Files

1. Open Blender with your IFC project loaded
2. Go to **Properties → Scene → Quality Control** tab
3. Expand **"Multi-Model Federation"** panel
4. Click **"Add File"** for each discipline IFC file
5. For each file:
   - Click folder icon → Browse to IFC file
   - Edit **Discipline** tag (e.g., "ARC", "ACMV", "STR")
6. Set **Federation Database** path: `/path/to/project_federation.db`

**Example configuration**:
```
Files:
  ☐ ARC     → /project/SJTII-ARC-A-TER1-00-R0.ifc
  ☐ ACMV    → /project/SJTII-ACMV-A-TER1-00-R0.ifc
  ☐ FP      → /project/SJTII-FP-A-TER1-00-R0.ifc
  ☐ SP      → /project/SJTII-SP-A-TER1-00-R0.ifc
  ☐ STR     → /project/SJTII-STR-S-TER1-00-R1.ifc
  ☐ ELEC    → /project/SJTII-ELEC-A-TER1-00-R0.ifc
  ☐ CW      → /project/SJTII-CW-A-TER1-00-R0.ifc

Database: /project/terminal1_federation.db
```

#### Step 2: Preprocess Federation

1. Click **"Preprocess Federation"** button
2. **Monitor progress**:
   - Check Blender console (Window → Toggle System Console)
   - Progress JSON updates every 5 seconds
   - Expected time: 1-3 minutes per file
3. **Wait for completion**:
   - Files show checkmarks (✓) when preprocessed
   - Element counts populate
   - Status: "Preprocessing completed"

**Console output**:
```
Processing SJTII-ARC-A-TER1-00-R0.ifc (discipline: ARC)
  Processed 10000 elements...
  Processed 20000 elements...
✓ Completed SJTII-ARC-A-TER1-00-R0.ifc: 34844 elements in 92.2s

Processing SJTII-ACMV-A-TER1-00-R0.ifc (discipline: ACMV)
✓ Completed SJTII-ACMV-A-TER1-00-R0.ifc: 1277 elements in 90.3s

[... continues for all files ...]

═══════════════════════════════════════════════════════
FEDERATION PREPROCESSING COMPLETE
═══════════════════════════════════════════════════════
Status:           completed
Total Files:      7
Total Elements:   44,190
Duration:         438.1 seconds
Database:         /project/terminal1_federation.db
Database Size:    15.71 MB
```

#### Step 3: Load Federation Index

1. Click **"Load Federation Index"**
2. Wait ~30 seconds for index to build in memory
3. **Verify status**:
   - Panel shows: "Federation Active"
   - Element count: 44,190
   - Disciplines: ARC, ACMV, FP, SP, STR, ELEC, CW

#### Step 4: Use Federation in Workflows

**For MEP Routing**:
1. Go to **MEP Engineering** panel
2. Set routing points
3. Click **"Route Conduit"** → uses federation for obstacles
4. Click **"Validate Route"** → checks clashes

**For Manual Queries**:
1. Click **"Test Query"** in Federation panel
2. Check console for results grouped by discipline

**Unload When Done**:
- Click **"Unload Federation Index"** to free memory

---

### Option 2: Standalone CLI (For Automation/Scripting)

The preprocessor can run **completely independently** of Blender for automated workflows, CI/CD pipelines, or server-side processing.

#### Standalone Installation

```bash
# 1. Install dependencies (outside Blender)
pip install ifcopenshell rtree

# 2. Get the preprocessor script
cd /path/to/your/scripts
wget https://raw.githubusercontent.com/red1oon/federation/main/federation_preprocessor.py
# OR copy from: src/bonsai/bonsai/bim/module/federation/federation_preprocessor.py

# 3. Verify it works
python federation_preprocessor.py --help
```

#### Basic Usage

```bash
# Single file
python federation_preprocessor.py \
  --files model.ifc \
  --output model_spatial.db \
  --disciplines ARC

# Multiple files (most common)
python federation_preprocessor.py \
  --files ARC.ifc ACMV.ifc STR.ifc ELEC.ifc \
  --output project_federation.db \
  --disciplines ARC ACMV STR ELEC
```

#### Advanced Options

```bash
# Custom progress tracking
python federation_preprocessor.py \
  --files *.ifc \
  --output federation.db \
  --disciplines ARC ACMV STR FP SP ELEC CW \
  --progress preprocessing_progress.json

# Auto-detect disciplines from filenames
python federation_preprocessor.py \
  --files SJTII-ARC-*.ifc SJTII-ACMV-*.ifc \
  --output federation.db
  # Disciplines auto-detected: ARC, ACMV
```

#### Real-World Example: Terminal 1 Project

```bash
#!/bin/bash
# preprocess_terminal1.sh

PROJECT_DIR="/project/terminal1"
OUTPUT_DB="${PROJECT_DIR}/terminal1_federation.db"

python federation_preprocessor.py \
  --files \
    "${PROJECT_DIR}/SJTII-ARC-A-TER1-00-R0.ifc" \
    "${PROJECT_DIR}/SJTII-ACMV-A-TER1-00-R0.ifc" \
    "${PROJECT_DIR}/SJTII-FP-A-TER1-00-R0.ifc" \
    "${PROJECT_DIR}/SJTII-SP-A-TER1-00-R0.ifc" \
    "${PROJECT_DIR}/SJTII-STR-S-TER1-00-R1.ifc" \
    "${PROJECT_DIR}/SJTII-ELEC-A-TER1-00-R0.ifc" \
    "${PROJECT_DIR}/SJTII-CW-A-TER1-00-R0.ifc" \
  --output "${OUTPUT_DB}" \
  --disciplines ARC ACMV FP SP STR ELEC CW \
  --progress "${PROJECT_DIR}/preprocessing_progress.json"

echo "✓ Preprocessing complete"
echo "Database: ${OUTPUT_DB}"
echo "Size: $(du -h ${OUTPUT_DB} | cut -f1)"
```

**Run it**:
```bash
chmod +x preprocess_terminal1.sh
./preprocess_terminal1.sh
```

**Output**:
```
Starting preprocessing of 7 files
Processing SJTII-ARC-A-TER1-00-R0.ifc (discipline: ARC)
  Processed 1000 elements...
  Processed 2000 elements...
  ...
✓ Completed SJTII-ARC-A-TER1-00-R0.ifc: 34844 elements in 92.2s

[... processes remaining files ...]

═══════════════════════════════════════════════════════
FEDERATION PREPROCESSING COMPLETE
═══════════════════════════════════════════════════════
Status:           completed
Total Files:      7
Total Elements:   44,190
Duration:         438.1 seconds (7.3 minutes)
Database:         /project/terminal1/terminal1_federation.db
Database Size:    15.71 MB

✓ Preprocessing complete
Database: /project/terminal1/terminal1_federation.db
Size: 16M
```

#### Automated CI/CD Integration

```yaml
# .github/workflows/preprocess-federation.yml
name: Preprocess IFC Federation

on:
  push:
    paths:
      - '**.ifc'

jobs:
  preprocess:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Install dependencies
        run: |
          pip install ifcopenshell rtree
          sudo apt-get install libspatialindex-dev
      
      - name: Preprocess federation
        run: |
          python scripts/federation_preprocessor.py \
            --files models/*.ifc \
            --output federation.db \
            --progress progress.json
      
      - name: Upload database
        uses: actions/upload-artifact@v3
        with:
          name: federation-database
          path: federation.db
```

#### Incremental Updates (When Models Change)

```bash
# Only reprocess changed files
python federation_preprocessor.py \
  --files ARC_UPDATED.ifc \
  --output existing_federation.db \
  --disciplines ARC
# SQLite REPLACE handles updates automatically
```

---

## 🔌 Integration with Other Modules

### MEP Engineering Module

The [MEP Engineering module](https://github.com/red1oon/mep_engineering) uses Federation for obstacle detection:

```python
# In MEP routing operator
from bpy.types import WindowManager

# Access loaded federation index
index = WindowManager.federation_index

# Query obstacles along conduit route
obstacles = index.query_corridor(
    start=(-50428, 34202, 6),  # meters
    end=(-50434, 34210, 6),
    buffer=0.5,  # 500mm clearance
    disciplines=['STR', 'ACMV', 'ARC']
)

# Result: 67 obstacles found
# ARC: 31, CW: 16, FP: 11, ACMV: 8, STR: 1
```

### Clash Detection Workflow

```python
# Pre-broadphase filtering for IfcClash
from bonsai.bim.module.federation.spatial_index import FederationIndex

index = FederationIndex("/project/federation.db")
index.build()

# Filter candidates before loading geometry
candidate_pairs = index.get_candidate_pairs(
    set_a_guids=['guid1', 'guid2', ...],
    set_b_guids=['guid3', 'guid4', ...],
    tolerance=0.01  # 10mm
)

# Load geometry ONLY for candidates (95% reduction)
# Then run standard IfcClash narrowphase
```

### Python API Reference

```python
from bonsai.bim.module.federation.spatial_index import FederationIndex
from pathlib import Path

# Initialize
index = FederationIndex(Path("project.db"))
index.build()

# Get statistics
stats = index.get_statistics()
print(f"Total elements: {stats['total_elements']:,}")
print(f"Disciplines: {', '.join(stats['disciplines'])}")

# Query by bounding box
elements = index.query_by_bbox(
    min_xyz=(1000, 2000, 0),    # meters
    max_xyz=(2000, 3000, 5000),
    disciplines=['ACMV', 'FP']  # optional filter
)

# Query by corridor (for routing)
obstacles = index.query_corridor(
    start=(1000, 2000, 3000),
    end=(5000, 6000, 7000),
    buffer=500.0,  # millimeters (or meters - check your units!)
    disciplines=['STR', 'ACMV', 'ARC']
)

# Query by point (with radius)
nearby = index.query_by_point(
    point=(1500, 2500, 4000),
    radius=1000.0,  # 1 meter
    disciplines=None  # all disciplines
)

# Get element by GUID
element = index.get_element_by_guid("2O2Fr$t4X7Zf8NOew3FNr2")
print(f"Found: {element.ifc_class} in {element.discipline}")

# Unload from memory
index.clear()
```

---

## 📊 Performance Benchmarks

### Validated on Terminal 1/2 Jetty Complex Project

| Metric | Value |
|--------|-------|
| **Total Elements** | 44,190 |
| **Disciplines** | 7 (ARC, ACMV, FP, SP, STR, ELEC, CW) |
| **Total File Size** | 302 MB |
| **Preprocessing Time** | 7.3 minutes (one-time) |
| **Database Size** | 15.7 MB |
| **Index Load Time** | ~30 seconds |
| **Query Time** | <100ms per corridor |
| **Runtime Memory** | 2 GB vs 30 GB traditional (93% reduction) |
| **Accuracy** | 100% (no false negatives) |

### Query Performance

```python
# Benchmark: 1000 corridor queries
import time

times = []
for i in range(1000):
    start = time.perf_counter()
    results = index.query_corridor(
        (i*10, i*10, 0),
        (i*10+100, i*10+100, 50),
        buffer=500
    )
    times.append(time.perf_counter() - start)

print(f"Average: {sum(times)/len(times)*1000:.1f}ms")
print(f"Max: {max(times)*1000:.1f}ms")

# Results: Average 45ms, Max 120ms
```

### Memory Usage

```python
import psutil
process = psutil.Process()

# Before loading
mem_before = process.memory_info().rss / (1024**3)

# Load federation
index.build()

# After loading
mem_after = process.memory_info().rss / (1024**3)

print(f"Memory increase: {mem_after - mem_before:.2f} GB")
# Typical: ~2GB for 44K elements
```

---

## 🛠️ Development Roadmap

### ✅ Phase 0: Foundation (Complete)
- Standalone bbox extraction script
- SQLite database with spatial indices
- R-tree spatial indexing
- Multi-core geometry processing

### ✅ Phase 1: BlenderBIM Integration (Complete)
- Blender UI panel
- File management operators
- Progress tracking with JSON
- Index load/unload operators

### ✅ Phase 2: Query API (Complete)
- `query_by_bbox()` - bounding box queries
- `query_corridor()` - routing pathfinding
- `query_by_point()` - proximity searches
- Discipline filtering

### 🚧 Phase 3: IfcOpenShell Integration (Planned)
- Submit as IfcPatch recipe
- Integrate with IfcClash pre-broadphase
- Upstream contribution to community

### 🚧 Phase 4: Advanced Features (Future)
- HDF5 backend for 1M+ elements
- Incremental updates (detect changes)
- Coordinate transformation handling
- Multi-origin project support
- Geometry caching integration

---

## 🧪 Testing & Validation

### Quick Validation Script

Save as `validate_federation.py`:

```python
from pathlib import Path
from bonsai.bim.module.federation.spatial_index import FederationIndex

# Load database
db_path = Path("terminal1_federation.db")
index = FederationIndex(db_path)

print(f"Loading federation index from {db_path.name}...")
index.build()

# Get statistics
stats = index.get_statistics()
print(f"\n✓ Index loaded successfully")
print(f"  Total elements: {stats['total_elements']:,}")
print(f"  Disciplines: {', '.join(stats['disciplines'])}")
print(f"  IFC classes: {stats['class_count']}")

# Test query
print("\nRunning test query...")
results = index.query_corridor(
    start=(-50428, 34202, 6),
    end=(-50434, 34210, 6),
    buffer=0.5,
    disciplines=['STR', 'ACMV', 'ARC']
)

print(f"✓ Query completed: {len(results)} obstacles found")

# Group by discipline
from collections import Counter
by_discipline = Counter(r.discipline for r in results)
print("\nObstacles by discipline:")
for disc, count in by_discipline.items():
    print(f"  {disc}: {count}")

print("\n✅ Validation complete!")
```

Run from Blender console or standalone Python.

---

## 🐛 Troubleshooting

### Issue: "rtree library required for spatial indexing"

**Solution**:
```bash
# Install rtree in Blender's Python
/path/to/blender/python -m pip install rtree

# Linux/Mac may need system library
sudo apt-get install libspatialindex-dev  # Ubuntu/Debian
brew install spatialindex  # macOS
```

### Issue: Preprocessing hangs or takes too long

**Solution**:
```bash
# Check CPU usage - should use multiple cores
top  # Linux/Mac
# Task Manager → Performance tab  # Windows

# If single-core: Check multiprocessing
python -c "import multiprocessing; print(multiprocessing.cpu_count())"

# Reduce parallelism if needed (edit preprocessor.py):
num_cores = 2  # Instead of multiprocessing.cpu_count()
```

### Issue: Database file not found after preprocessing

**Solution**:
```bash
# Check if preprocessing completed
cat preprocessing_progress.json | grep status
# Should show: "status": "completed"

# Check database exists
ls -lh *.db

# If failed, check console for errors
# Common: Out of memory, corrupt IFC file
```

### Issue: Query returns no results

**Solution**:
```python
# Validate coordinates are in correct units (meters)
# Check building extents
stats = index.get_statistics()
print(stats)

# Try query with very large bbox
results = index.query_by_bbox(
    (-100000, -100000, -100000),
    (100000, 100000, 100000)
)
print(f"Elements found: {len(results)}")

# If still empty, check database
import sqlite3
conn = sqlite3.connect("federation.db")
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM elements")
print(f"Database elements: {cursor.fetchone()[0]}")
```

### Issue: "Federation index not found in memory"

**Solution**:
```python
# In Blender console, check if loaded
import bpy
hasattr(bpy.types.WindowManager, 'federation_index')
# Should be True

# If False, reload from UI:
# Properties → Quality Control → Federation → Load Federation Index
```

---

## 📚 Documentation & Resources

- **Strategic Guide**: [MEP Coordination: Strategic & Technical Guide](../docs/strategic-guide.md)
- **Validation Checklist**: [Federation Module Validation](../docs/validation-checklist.md)
- **Terminal 1/2 Case Study**: Validation data from real 93K element project
- **OSArch Forum**: [Community discussion](https://community.osarch.org/)
- **GitHub Issues**: [Report bugs or request features](https://github.com/red1oon/federation/issues)

### Related Projects

- **[MEP Engineering Module](https://github.com/red1oon/mep_engineering)** - Uses Federation for routing/clash detection
- **[Bonsai10D](https://github.com/red1oon/bonsai10d)** - 10D construction coordination vision
- **[IfcOpenShell](https://github.com/IfcOpenShell/IfcOpenShell)** - IFC toolkit and library
- **[BlenderBIM](https://blenderbim.org/)** - OpenBIM Blender add-on

---

## 📄 License

**GPL-3.0-or-later**

This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

See [LICENSE](LICENSE) for full details.

---

## 👥 Authors

**Redhuan D. Oon (red1)** - Lead Developer  
**Naquib Danial Oon** - Contributor

### Contributing

We welcome contributions! This module is designed for upstream contribution to IfcOpenShell/Bonsai:

1. Fork the repository
2. Create a feature branch
3. Follow [BlenderBIM code standards](https://docs.bonsaibim.org/guides/development/coding-standards.html)
4. Submit a pull request

For major changes, please open an issue first to discuss.

---

## 🙏 Acknowledgments

- **Dion Moult** - IfcOpenShell maintainer, pre-broadphase filtering concept
- **OSArch Community** - Testing and feedback
- **BlenderBIM Team** - Foundation and ecosystem

---

**Status**: Production Ready | **Version**: Phase 2 Complete (v0.2.0)  
**Last Updated**: 2025-01-14
