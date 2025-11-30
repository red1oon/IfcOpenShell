# 4D Scheduling & Animation - User Guide

**Construction timeline visualization for Bonsai Federation**

Part of the [Federation Module](../../bonsai/bim/module/federation/README.md) - Multi-model spatial indexing and 4D/5D BIM coordination.

---

## 🎯 Overview

The 4D Scheduling system adds **time dimension** to your federated BIM model, showing construction sequence over time through Blender animation.

### Key Capabilities

- ✅ **Schedule Generation** - Automatic construction schedule from IFC model
- ✅ **Multiple Export Formats** - Microsoft Project (MPP/XML), Excel spreadsheets
- ✅ **4D Animation** - Blender keyframe-based construction visualization
- ✅ **Database-Driven** - All schedule data stored in SQLite for flexibility
- ✅ **Scales to 50k+ Elements** - Optimized for enterprise projects
- ✅ **Professional Exports** - Charts, summaries, and project statistics

---

## 🏗️ System Architecture

```
┌────────────────────────────────────────────────────┐
│ SCHEDULE GENERATION (One-time, ~1-2 minutes)      │
│                                                     │
│  Federation Database (elements_meta table)         │
│       ↓                                             │
│  schedule_generator.py                             │
│    - Groups by IFC class + discipline + storey     │
│    - Assigns construction phases                   │
│    - Calculates realistic durations                │
│       ↓                                             │
│  construction_schedule table                       │
│    - 49 tasks for 49k elements (Terminal 1)        │
│    - Start/finish dates, dependencies              │
│    - IFC class/discipline/storey mappings          │
└────────────────────────────────────────────────────┘
                      ↓
┌────────────────────────────────────────────────────┐
│ EXPORT OPTIONS                                      │
│                                                     │
│  Option 1: Microsoft Project (.mpp, .xml)          │
│    - Import to MS Project for editing              │
│    - Gantt charts, dependencies, resources         │
│                                                     │
│  Option 2: Excel Spreadsheet (.xlsx)               │
│    - Professional reports with charts              │
│    - Pie charts (phase distribution)               │
│    - Bar charts (discipline task count)            │
│    - Two sheets: Task list + Summary               │
└────────────────────────────────────────────────────┘
                      ↓
┌────────────────────────────────────────────────────┐
│ 4D ANIMATION (15-25 seconds for 49k elements)      │
│                                                     │
│  animation_optimized.py                            │
│    - Reads construction_schedule from database     │
│    - Matches IFC elements by class/discipline      │
│    - Creates visibility keyframes (hide/show)      │
│    - Timeline: Dates → Frames (2 frames/day)       │
│       ↓                                             │
│  Blender Scene (animated .blend file)              │
│    - 196,236 keyframes (49k objects × 4 keys)      │
│    - Timeline: 0-8749 frames                       │
│    - Building progressively appears over time      │
│    - Saved in .blend file (~50MB overhead)         │
└────────────────────────────────────────────────────┘
```

---

## 📦 Database Schema

### `construction_schedule` Table

Created by `schedule/database_schema.py`:

```sql
CREATE TABLE construction_schedule (
    task_id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_name TEXT NOT NULL,
    ifc_class TEXT,
    discipline TEXT,
    storey TEXT,
    start_date TEXT NOT NULL,
    finish_date TEXT NOT NULL,
    duration_days REAL,
    phase TEXT,
    predecessors TEXT,
    created_date TEXT DEFAULT CURRENT_TIMESTAMP
);
```

**Example data** (Terminal 1 project, 49 tasks):

| task_id | task_name | ifc_class | discipline | storey | start_date | finish_date | duration_days | phase |
|---------|-----------|-----------|------------|--------|------------|-------------|---------------|-------|
| 1 | Site Preparation | IfcSite | ARC | Unknown | 2025-01-01 | 2025-02-14 | 45.00 | Site Work |
| 2 | Foundations - Structural | IfcFooting | STR | Level 0 | 2025-02-15 | 2025-03-31 | 45.00 | Foundations |
| 15 | ACMV Ducting - Level 1 | IfcDuctSegment | ACMV | Level 1 | 2025-07-20 | 2025-09-12 | 55.00 | MEP Rough-In |
| 42 | Architectural Finishes - Level 3 | IfcCovering | ARC | Level 3 | 2025-11-08 | 2025-12-22 | 45.00 | Finishes |
| 49 | Project Completion | N/A | N/A | N/A | 2025-12-23 | 2025-12-23 | 1.00 | Completion |

**Total project duration**: 357 days (~1 year)

---

## 🚀 Workflow Guide

### Step 1: Generate Schedule

**Via Blender UI:**

1. Open Blender with federated IFC model loaded
2. Go to **Properties → Scene → Quality Control** tab
3. Scroll to **"4D/5D BIM"** panel
4. **Step 1: Generate Schedule**
   - Database path should be auto-detected
   - Click **"Generate Construction Schedule"**
5. Wait ~1-2 minutes (console shows progress)
6. Check console for confirmation:
   ```
   ✅ Schedule generated: 49 tasks over 357 days
   ```

**Scheduling Logic** (see `schedule/schedule_generator.py`):

- **Grouping**: IFC elements grouped by (ifc_class, discipline, storey)
- **Sequencing**: Logical construction order
  1. Site preparation (45 days)
  2. Foundations → Structure (45-60 days per level)
  3. MEP rough-in (55 days per discipline/level)
  4. Enclosure (walls, windows)
  5. Finishes (35-45 days per level)
  6. Completion (1 day milestone)
- **Durations**: Based on element count and complexity
  - Foundations: 45 days
  - Structural: 60 days per storey
  - MEP: 55 days per discipline/storey
  - Finishes: 35-45 days
- **Dependencies**: Sequential by phase (predecessors stored as comma-separated task_ids)

### Step 2: Export Schedule

#### Option A: Microsoft Project

**Why use this?**
- Industry-standard tool ($500-$2,500/year)
- Advanced scheduling features (critical path, resource leveling)
- Familiar to project managers

**How to export:**

1. **Step 2: Export to MS Project**
2. Click **"Export to MS Project (.mpp)"**
3. File saved to: `WORK_DIR/schedules/Terminal1_Schedule_YYYYMMDD_HHMMSS.mpp`
4. **Open in Microsoft Project**:
   - Double-click .mpp file
   - OR: File → Open in MS Project
5. **View Gantt chart**, edit tasks, assign resources

**File format**: Universal `.mpp` (works with MS Project 2010+)

#### Option B: Excel Spreadsheet

**Why use this?**
- FREE - No special software required
- Editable in Excel/LibreOffice/Google Sheets
- Professional charts and summaries
- Easy to share (<1MB file size)

**How to export:**

1. **Step 2: Export to Excel**
2. Click **"📊 Export to Excel"**
3. File saved to: `WORK_DIR/schedules/Terminal1_Schedule_YYYYMMDD_HHMMSS.xlsx`
4. **Auto-opens in default spreadsheet viewer**

**Excel file contents** (see `schedule/excel_export.py`):

**Sheet 1: Construction Schedule**
- Columns: Task ID, Name, IFC Class, Discipline, Storey, Start, Finish, Duration, Phase
- Duration formatted to 2 decimal places
- Professional styling (blue headers #366092)

**Sheet 2: Project Summary**
- Total tasks, total duration, start/end dates
- **Pie Chart**: Phase distribution (% of total duration)
  - Shows construction breakdown by phase (Foundations, Structure, MEP, Finishes)
- **Bar Chart**: Task count by discipline
  - ARC, STR, ACMV, ELEC, FP, etc.

**Charts positioned** at D2 (Pie) and D18 (Bar) for professional layout.

### Step 3: Create 4D Animation

**What is 4D animation?**
- Building progressively **appears** over timeline (frame 0 = empty, frame 8749 = complete)
- Uses Blender's visibility keyframes (hide_viewport property)
- Objects toggle from hidden → visible based on construction schedule
- Binary visibility (instant appearance, not gradual fade)

**Performance** (49,059 elements, Terminal 1):
- **Indexing**: 5-10 seconds (pre-process object lookup)
- **Animation**: 10-15 seconds (create keyframes)
- **Total**: 15-25 seconds (optimized O(n+m) algorithm)

**How to create:**

1. **Step 3: Animate Construction (4D)**
2. Settings:
   - **Frames per Day**: 2 (default) - higher = smoother but longer timeline
   - **Show Complete Building After Creation**: ✅ (jumps to end frame after creation)
3. Click **"🎬 Create 4D Animation"**
4. **Wait 15-25 seconds** (console shows progress):
   ```
   📇 Building object index... (scanning 49,059 objects)
   ✅ Indexed 49,059 IFC objects - ready to animate!
   🎬 Processing 49 tasks...
      Progress: 5/49 tasks (10%), 8,234 objects animated
      Progress: 10/49 tasks (20%), 15,891 objects animated
      ...
   ✅ Animation complete! 49,059 objects animated
   Timeline: 0 → 8749 frames (12.0 years at 2 frames/day)
   ```
5. **Button turns gray** when complete
6. **Viewport shows complete building** (if "Show Complete" enabled)

**CRITICAL: Save the file immediately!**

```
Press Ctrl+S (or File → Save)
```

**What gets saved:**
- ✅ All 196,236 keyframes (49k objects × 4 keys each)
- ✅ Timeline range (0-8749 frames)
- ✅ Animation F-curves (visibility data)
- ✅ File size: +50MB (840MB total for Terminal 1)

---

## 🎬 Using the Animation

### Finding the Timeline Bar

**Most common issue**: "I don't see the timeline!"

**Solution - Switch to Animation workspace:**

1. Look at **very top** of Blender window
2. Click **"Animation"** tab (workspace switcher)
3. Timeline appears at **bottom** of screen automatically

**Alternative** (if no Animation tab):
1. Move mouse to **bottom edge** of 3D viewport
2. Cursor changes to resize arrows ↕
3. Drag **UP** to reveal collapsed timeline

### Timeline Controls

```
┌─────────────────────────────────────┐
│ Frame: [8749]  ← Click, type number │
│                                      │
│ 0────▶────────────────────8749      │
│      ↑                               │
│   Drag this slider                   │
└─────────────────────────────────────┘

[⏮] Jump to start (frame 0)
[◀] Previous frame
[▶] Play/Pause (SPACEBAR)
[⏭] Jump to end (frame 8749)
```

**Keyboard Shortcuts:**

| Key | Action |
|-----|--------|
| **SPACEBAR** | Play/Pause animation |
| **→** | Next frame |
| **←** | Previous frame |
| **Shift+→** | Jump forward 10 frames |
| **Shift+←** | Jump backward 10 frames |

### Navigation Tips

**To see specific construction stages:**

```
Frame 0:     Empty site (all hidden)
Frame 1000:  ~11% built (foundations, early structure)
Frame 2000:  ~23% built (more structure)
Frame 4000:  ~46% built (MEP rough-in starting)
Frame 6000:  ~69% built (walls, enclosure)
Frame 8749:  100% complete
```

**How to jump to a specific date:**
1. Click in **"Frame:"** field (shows current frame number)
2. Type desired frame (e.g., "0", "1000", "4000")
3. Press **Enter**
4. Viewport updates instantly

### Workflow After Saving

**Correct workflow** (every session after first):

1. Open saved .blend file
2. Press **SPACEBAR** to play animation
3. Use timeline controls to navigate
4. **NEVER click "Create 4D Animation" button again** (unless schedule changes)

**Why?** The button **always recreates** animation from scratch (20+ minutes). After saving, animation is permanently stored in the .blend file.

**Mistake to avoid:**
❌ Clicking "Create 4D Animation" again → 20-minute recreation
✅ Just press SPACEBAR → Instant playback

---

## 🎥 Rendering Movies

### Quick Test Render

Create a 10-second preview movie:

```python
# In Blender Python console (or save as script)
import bpy

# Set render settings
bpy.context.scene.render.fps = 24
bpy.context.scene.render.image_settings.file_format = 'FFMPEG'
bpy.context.scene.render.ffmpeg.format = 'MPEG4'
bpy.context.scene.render.ffmpeg.codec = 'H264'
bpy.context.scene.render.filepath = "/tmp/construction_preview.mp4"

# Render frames 0-240 (10 seconds at 24fps)
bpy.context.scene.frame_start = 0
bpy.context.scene.frame_end = 240

# Start render
bpy.ops.render.render(animation=True)
```

**Output**: `/tmp/construction_preview.mp4` (shows first ~5% of construction)

### Full Project Timelapse

**Frame count calculation:**
- Total frames: 8749
- At 24fps: 8749 ÷ 24 = 365 seconds = **6 minutes** movie

**To speed up** (make shorter movie):
```python
# Render every 10th frame (60x speedup)
bpy.context.scene.frame_step = 10
# Result: 875 frames = 36 seconds at 24fps
```

**Professional workflow:**
1. Set up camera path (animated camera moving around building)
2. Adjust lighting (HDRI sky, sun lamp)
3. Set render quality (Cycles, 1080p or 4K)
4. Render overnight (may take 1-8 hours depending on quality)

**See**: [4D_VIDEO_RENDERING_GUIDE.md](../../../../WORK_DIR/schedules/4D_VIDEO_RENDERING_GUIDE.md) for detailed instructions

---

## ⚡ Performance & Optimization

### Tested Performance (Terminal 1 Project)

| Metric | Value |
|--------|-------|
| **Total Elements** | 49,059 |
| **Total Tasks** | 49 |
| **Total Keyframes** | 196,236 (4 per object) |
| **Indexing Time** | 5-10 seconds |
| **Animation Creation** | 10-15 seconds |
| **File Size Increase** | +50MB (~6% of original) |
| **Playback FPS** | 60fps (smooth at 24fps target) |

### Optimization Techniques

**Pre-indexing** (see `schedule/animation_optimized.py`):
```python
# O(n×m) → O(n+m) complexity reduction
# Old: 2.4M iterations (3-5 minutes)
# New: 49k iterations (10-15 seconds)

index = {
    ifc_class: {
        discipline: {
            storey: [obj1, obj2, ...]
        }
    }
}

# Instant lookup instead of nested loops
objects = index[task.ifc_class][task.discipline][task.storey]
```

**Batch keyframe insertion**:
- Set all keyframes per object at once (4 keys)
- Avoids repeated F-curve lookups
- 20% faster than incremental insertion

**Console progress output**:
```python
if (i + 1) % 5 == 0:
    print(f"Progress: {i+1}/{len(tasks)} tasks ({percent:.0f}%)")
```
- Updates every 5 tasks
- User knows it's not frozen
- Reduces print overhead

### Handling Large Projects (100k+ elements)

**If animation takes >5 minutes:**

1. **Reduce frames_per_day**:
   ```
   2 frames/day → 1 frame/day (50% fewer keyframes)
   ```

2. **Filter by discipline** (animate only specific trades):
   ```python
   # Modify animation.py to filter
   tasks = [t for t in tasks if t['discipline'] in ['ARC', 'STR']]
   ```

3. **Use frame handler method** (instant setup, no keyframes):
   - See: [instant_4d_handler.py](../../../../WORK_DIR/test_outputs/instant_4d_handler.py)
   - Trade-off: Slightly slower playback

4. **Split into phases** (animate in chunks):
   - Phase 1: Structure only
   - Phase 2: MEP only
   - Phase 3: Finishes only

---

## 🛠️ Technical Details

### Data Flow

```
Database (construction_schedule)
    ↓ (SQL query)
Tasks: [
    {
        task_id: 15,
        ifc_class: "IfcDuctSegment",
        discipline: "ACMV",
        storey: "Level 1",
        start_date: "2025-07-20",
        finish_date: "2025-09-12"
    },
    ...
]
    ↓ (date_to_frame conversion)
Frames: start=3600, finish=3710
    ↓ (object matching via index)
Objects: [obj_12345, obj_12346, ...]
    ↓ (keyframe insertion)
Blender F-Curves:
    - Frame 0: hide_viewport=True, hide_render=True
    - Frame 3599: hide_viewport=True, hide_render=True
    - Frame 3600: hide_viewport=False, hide_render=False
    ↓ (save .blend)
Persistent Animation Data
```

### Date to Frame Conversion

```python
# Reference: 2025-01-01 = Frame 1
# Formula: (date - ref_date).days × frames_per_day + 1

def date_to_frame(date_str: str, frames_per_day: int = 2) -> int:
    date = datetime.strptime(date_str, "%Y-%m-%d")
    ref_date = datetime(2025, 1, 1)
    days = (date - ref_date).days
    return days * frames_per_day + 1

# Examples:
date_to_frame("2025-01-01") → 1
date_to_frame("2025-01-02") → 3
date_to_frame("2025-12-23") → 8749  # End of project
```

### Object Matching Logic

**Three-key system**:
1. **IFC Class** - Element type (IfcWall, IfcDuctSegment)
2. **Discipline** - Trade (ARC, ACMV, STR, ELEC)
3. **Storey** - Level (Level 0, Level 1, Unknown)

**Special handling**:
- `storey="Unknown"` → Skip storey matching (match by class + discipline only)
- Missing properties → Skip object (not animated)
- Multiple matches → All get same animation (intended for grouped elements)

```python
# Fast lookup via pre-built index
def get_element_objects_fast(ifc_class, discipline, storey):
    return object_index[ifc_class][discipline][storey]
    # O(1) lookup instead of O(n) iteration
```

### Keyframe Schema

**Each object gets 4 keyframes** (both viewport and render):

```
Frame 0:          hide_viewport=True, hide_render=True  (hidden)
Frame start-1:    hide_viewport=True, hide_render=True  (still hidden)
Frame start:      hide_viewport=False, hide_render=False (appears!)
```

**Why 4 keys?**
- Ensures smooth interpolation
- Prevents premature appearance
- Works for both viewport and rendering

**Total keyframes**: objects × 4
- Terminal 1: 49,059 × 4 = 196,236 keyframes

---

## 🐛 Troubleshooting

### Issue: "Animation doesn't play after reopening file"

**Check:**
1. Did you save the file? (Ctrl+S)
2. Are you opening the saved file (not original)?
3. Is timeline at frame 0? (scrub to start before playing)

**Solution:**
```
File → Recent Files → Check you opened the saved version
Timeline → Frame: 0 → Press SPACEBAR
```

### Issue: "Timeline not visible"

**Solution:**
1. Click **"Animation"** workspace tab at top
2. OR: Drag bottom edge of viewport UP

### Issue: "Button stays blue for 20+ minutes"

**Expected behavior** if:
- First time creating animation (15-25 seconds normal)
- System under load (check CPU usage with `top` or Task Manager)
- Very large project (100k+ elements may take 5 minutes)

**Unexpected** if:
- Taking >5 minutes for 50k elements
- No console output (check Window → Toggle System Console)

**Solution:**
- Wait for completion (watch console progress)
- Kill competing processes (npm, Claude CLI)
- Reduce `frames_per_day` to 1

### Issue: "Building doesn't disappear at frame 0"

**Check:**
1. Timeline shows frame 0? (verify number)
2. Animation was created successfully? (check console for "✅ Animation complete")
3. Saved file includes animation? (file size should be +50MB)

**Solution:**
```
Timeline → Frame: 0 → Manual check
If still visible: Animation may not have been saved
Re-create: Click "Create 4D Animation" → Wait → Ctrl+S immediately
```

### Issue: "Clicked Animation button again, now it's recreating!"

**Why this happens:**
- Button **always recreates** animation (by design)
- Allows updating when schedule changes
- Does not check if animation already exists

**Solution:**
1. Let it finish (15-25 seconds)
2. **Ctrl+S immediately**
3. Never click button again unless schedule changes

**Proper workflow:**
```
Session 1: Create → Save (Ctrl+S)
Session 2+: Open → SPACEBAR (never click button)
```

### Issue: "File size too large (>1GB)"

**Expected sizes:**
- Terminal 1 (49k elements): 840MB (790MB base + 50MB animation)
- 100k elements: ~1.5GB

**To reduce:**
```
File → External Data → Pack All into .blend
File → Save As → Enable "Compress File"
Result: ~30% smaller (600MB for Terminal 1)
```

---

## 📚 API Reference

### Generate Schedule (Python)

```python
from bonsai.bim.module.federation.schedule.schedule_generator import ConstructionScheduleGenerator

db_path = "/path/to/federation.db"
generator = ConstructionScheduleGenerator(db_path)

# Generate schedule
stats = generator.generate_schedule()
print(f"✅ {stats['task_count']} tasks over {stats['duration_days']} days")

# Query schedule
tasks = generator.get_all_tasks()
for task in tasks:
    print(f"{task['task_name']}: {task['start_date']} → {task['finish_date']}")
```

### Export to Microsoft Project

```python
from bonsai.bim.module.federation.schedule.mpp_export import export_to_mpp

mpp_path = export_to_mpp(
    db_path="/path/to/federation.db",
    output_path="/path/to/output.mpp",
    project_name="Terminal 1 Construction"
)
print(f"✅ Exported to {mpp_path}")
```

### Export to Excel

```python
from bonsai.bim.module.federation.schedule.excel_export import export_to_excel

xlsx_path = export_to_excel(
    db_path="/path/to/federation.db",
    output_path="/path/to/output.xlsx",
    project_name="Terminal 1 Construction"
)
print(f"✅ Exported to {xlsx_path}")
```

### Create Animation

```python
from bonsai.bim.module.federation.schedule.animation_optimized import animate_construction_sequence_optimized

stats = animate_construction_sequence_optimized(
    db_path="/path/to/federation.db",
    frames_per_day=2
)

print(f"✅ Animated {stats['objects_animated']:,} objects")
print(f"Timeline: 0 → {stats['end_frame']} frames")
```

### Advanced: Custom Animation Logic

```python
from bonsai.bim.module.federation.schedule.animation_optimized import OptimizedConstructionAnimator
import bpy

# Initialize animator
animator = OptimizedConstructionAnimator(
    db_path="/path/to/federation.db",
    frames_per_day=2
)

# Build object index
animator.object_index = animator.build_object_index()

# Get schedule
tasks = animator.get_schedule_data()

# Custom animation logic
for task in tasks:
    if task['discipline'] == 'ACMV':  # Only animate ACMV
        start_frame = animator.date_to_frame(task['start_date'])
        objects = animator.get_element_objects_fast(
            task['ifc_class'],
            task['discipline'],
            task['storey']
        )

        # Animate with custom fade-in (see smooth_4d_fade.py)
        for obj in objects:
            create_smooth_fade_animation(obj, start_frame, duration=20)
```

---

## 🎬 Example Scripts: Automated MEP Showcase

**Location**: `src/bonsai/docs/federation/examples/`

Ready-to-use scripts for creating professional construction showcases with sectional reveals and automated camera paths.

### Script 1: Sectional Reveal MEP (`sectional_reveal_mep.py`)

**What it does:**
- Hides building envelope (ARC + STR) at specified frame
- Reveals hidden MEP systems (ACMV, ELEC, FP) dramatically
- Configurable timing and duration

**Usage:**
```bash
# In Blender Scripting workspace:
# 1. Open: src/bonsai/docs/federation/examples/sectional_reveal_mep.py
# 2. Click "Run Script"
# 3. Save file (Ctrl+S)
# 4. Scrub to frame 4000 → See envelope hide!
```

**Available presets:**
```python
preset_single_reveal_midpoint()    # Frame 4000 (default)
preset_three_stage_reveal()        # Multiple reveals at 2000, 4500, 7000
preset_long_section()              # Extended 500-frame reveal
preset_mep_only_reveal()           # Hide everything except MEP
```

**Custom usage:**
```python
add_sectional_reveal(
    reveal_start_frame=4000,    # When to hide envelope
    reveal_duration=200,         # How long to stay hidden
    disciplines_to_hide=['ARC', 'STR']  # Which disciplines
)
```

---

### Script 2: Automated MEP Showcase (`automated_mep_showcase.py`)

**What it does:**
- ✅ Sectional reveal (hides envelope during MEP phase)
- ✅ Automated camera flythrough (orbits around/inside building)
- ✅ Auto-switches to camera view (no numpad needed!)
- ✅ Perfectly timed to construction schedule

**Features:**
- **Auto-calculated camera path** based on building bounds
- **Smooth Bezier interpolation** for cinematic movement
- **Three-phase sequence**: Approach → Interior orbit → Exit
- **Hands-free operation** - just press SPACEBAR!

**Usage:**
```bash
# In Blender Scripting workspace:
# 1. Open: src/bonsai/docs/federation/examples/automated_mep_showcase.py
# 2. Click "Run Script" (▶)
# 3. Wait ~2-5 minutes (processing 49k objects)
# 4. Save file (Ctrl+S)
# 5. Already in camera view - just press SPACEBAR!
```

**Timeline sequence:**
```
Frame 3800:      Camera approaches from outside
Frame 4000:      💥 Envelope HIDES + Camera ENTERS building
                 (ARC + STR disappear, MEP visible!)
Frame 4000-4200: Camera orbits INSIDE building
                 (Shows ACMV ducts, ELEC conduits, FP pipes)
Frame 4200:      Envelope RETURNS + Camera EXITS
Frame 4300:      Overview shot (end)
```

**Available presets:**
```python
preset_early_mep_reveal()      # Frame 2000 (early construction)
preset_midpoint_mep_reveal()   # Frame 4000 (DEFAULT - MEP rough-in)
preset_late_mep_reveal()       # Frame 6500 (ceiling MEP before finishes)
preset_extended_showcase()     # 500 frames (long detailed examination)
```

**Custom camera path:**
```python
automated_mep_showcase(
    reveal_start=4000,          # When reveal begins
    reveal_duration=200,        # How long reveal lasts
    auto_calculate_bounds=True  # Auto-detect building size
)
```

**Output:**
```
✅ AUTOMATED MEP SHOWCASE - Ready!

🎮 HOW TO USE:
   1. Save file (Ctrl+S)
   2. Already in camera view! (no numpad needed)
   3. Press SPACEBAR → Watch automated showcase!
   4. Sit back and enjoy the flythrough 🍿

📹 Camera Path:
   Phase 1: Approach (frames 3800 → 4000)
   Phase 2: Interior orbit (frames 4000 → 4200)
   Phase 3: Exit overview (frames 4200 → 4300)
```

---

### Script 3: Fast Version (`automated_mep_showcase_fast.py`)

**Why use this:**
- Same as Script 2 but with **real-time progress output**
- Shows progress every 1000 objects
- Displays estimated time remaining
- Use if original script seems stuck

**Progress output:**
```
📐 Calculating building bounds...
   Center: (121.5, -21.7, -0.8)
   Radius: 51.6m

🎭 Adding sectional reveal (MEP systems)...
   Processing 49,059 objects...
      Progress: 10,000/49,059 (20%) - 5,234 envelope objects - ETA: 120s
      Progress: 20,000/49,059 (41%) - 10,891 envelope objects - ETA: 60s
      ...
   ✅ 25,000 envelope objects configured in 180s

📹 Creating automated camera path...
   ✅ Camera path: 9 keyframes

✅ SETUP COMPLETE!
```

---

### Workflow: Creating Multiple Showcase Versions

**Best practice:** Create specialized versions for different audiences

```bash
# Version 1: Basic Construction (for architects)
# - Don't run any scripts
# - Save as: "Terminal1_4D_Basic.blend"

# Version 2: MEP Sectional Reveal (for MEP coordinators)
# - Run: sectional_reveal_mep.py
# - Save as: "Terminal1_4D_MEP_Reveal.blend"

# Version 3: Full Showcase with Camera (for clients/stakeholders)
# - Run: automated_mep_showcase.py
# - Save as: "Terminal1_4D_Showcase.blend"

# Version 4: Custom Timing (for project managers)
# - Edit script to use different frame (e.g., 2000 for early phase)
# - Save as: "Terminal1_4D_Early_MEP.blend"
```

**Benefits:**
- Different versions for different audiences
- Experiment safely (keep originals)
- Each ~840MB (manage file sizes)

---

### Camera Tips for Best Results

**Before running showcase script:**
1. Note building orientation in viewport
2. Identify best viewing angles manually
3. Script will auto-calculate, but you can customize camera positions in code

**After script runs:**
- Camera automatically points at building center
- Smooth Bezier interpolation for cinematic feel
- To exit camera view: View menu → Viewport Navigation → Orbit

**For final presentation:**
```python
# In script, adjust these values:
orbit_radius = 100.0    # Distance from building
cam_data.lens = 35      # Wide angle (28-50mm)

# Enable motion blur for render:
scene.render.use_motion_blur = True
scene.render.resolution_percentage = 100  # Full quality
```

---

## 🚀 Future Enhancements

### Planned Features

- **Smooth fade-in** - Gradual alpha transparency instead of binary toggle
- ~~**Camera path automation**~~ - ✅ **IMPLEMENTED** (see Example Scripts above)
- ~~**Sectional reveals**~~ - ✅ **IMPLEMENTED** (see Example Scripts above)
- **Progress tracking** - Show % complete overlay on viewport
- **Resource loading** - Assign crews, equipment from schedule
- **Clash timeline** - Show when/where clashes occur
- **Cost integration** - 5D BIM with BOQ data (duration × cost rate)

### Integration with 5D BIM

Current: **Schedule** (4D) + **BOQ** (cost) = Manual correlation

Future: **Unified 5D Dashboard**
```
Timeline frame 4000:
- Building: 46% complete
- Cost: $12.3M spent (of $26.7M total)
- Resources: 45 workers, 3 cranes active
- Clashes: 12 unresolved (MEP conflicts)
```

See: [5D Dashboard Design](../../../../WORK_DIR/PROJECT_STATUS_4D_READINESS.md)

---

## 📄 Related Documentation

**Core Documentation:**
- **[Federation Module README](../../bonsai/bim/module/federation/README.md)** - Spatial indexing and federated models
- **[BOQ System Guide](../../bonsai/bim/module/federation/ProjectKnowledge/BOQ_System_User_Guide_For_Accountants.md)** - 5D cost analysis

**Example Scripts** (Ready to use!):**
- **[Sectional Reveal MEP](examples/sectional_reveal_mep.py)** - Hide envelope to show MEP systems
- **[Automated MEP Showcase](examples/automated_mep_showcase.py)** - Full automated flythrough with camera
- **[Fast Version](examples/automated_mep_showcase_fast.py)** - Same with progress output

**Quick Reference:**
- **[4D Quick Start](../../../../WORK_DIR/4D_QUICK_START.md)** - Quick reference guide
- **[Timeline Controls](../../../../WORK_DIR/timeline_controls.md)** - Blender shortcuts
- **[Performance Guide](../../../../WORK_DIR/schedules/4D_PERFORMANCE_GUIDE.md)** - Optimization for 50k+ elements

---

## 📧 Support

- **GitHub Issues**: [Report bugs or request features](https://github.com/red1oon/IfcOpenShell/issues)
- **OSArch Forum**: [Community discussion](https://community.osarch.org/)
- **BlenderBIM Docs**: [Official documentation](https://docs.bonsaibim.org/)

---

## 📄 License

**GPL-3.0-or-later** - Same as IfcOpenShell/Bonsai

---

## 👥 Authors

**Redhuan D. Oon (red1)** - Lead Developer
**Naquib Danial Oon** - Contributor

---

**Status**: Production Ready | **Version**: v0.1.0 (4D features complete)
**Last Updated**: 2025-11-30

---

## ⚠️ Summary

**What you get:**
- ✅ Automatic schedule generation from IFC model
- ✅ Export to Microsoft Project or Excel
- ✅ Professional Blender animation (15-25 seconds for 49k elements)
- ✅ Free and open source (vs $2,500/year Autodesk Navisworks)
- ✅ Scales to enterprise projects (50k+ elements validated)

**What makes it special:**
- First open-source 4D BIM for IFC-native workflows
- Democratizes construction visualization
- Integrates with existing Bonsai/BlenderBIM tools
- Database-driven for flexibility and automation

**Getting started:**
1. Generate schedule (2 minutes)
2. Create animation (20 seconds)
3. Save file (Ctrl+S)
4. Press SPACEBAR → Watch your building construct itself!

**The future is open BIM.** 🚀
