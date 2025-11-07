# Bonsai Federation Analysis - Autodesk User Manual

**Document Version:** 1.0
**Date:** 2025-11-07
**Target Audience:** Autodesk Navisworks, Revit, and BIM 360 Users
**Author:** Bonsai Federation Team

---

## Table of Contents

1. [Introduction](#introduction)
2. [Quick Start Guide](#quick-start-guide)
3. [Workflow: Navisworks to Bonsai](#workflow-navisworks-to-bonsai)
4. [Workflow: Bonsai to Navisworks](#workflow-bonsai-to-navisworks)
5. [BCF Export & Import](#bcf-export--import)
6. [Clash Reports for Autodesk Teams](#clash-reports-for-autodesk-teams)
7. [Troubleshooting](#troubleshooting)
8. [FAQ](#faq)

---

## Introduction

### What is Bonsai Federation Analysis?

Bonsai is an **open-source BIM coordination tool** built on Blender and IfcOpenShell. It provides:

- ✅ **Fast clash detection** using spatial R-tree indexing
- ✅ **Intelligent cascade grouping** (identifies root cause elements)
- ✅ **BCF 2.1 export** compatible with Autodesk tools
- ✅ **Cost intelligence** for coordination decision-making
- ✅ **Markdown + Excel reports** for stakeholder communication

### Why Bonsai + Autodesk?

**Complementary Strengths:**

| Capability | Bonsai | Navisworks | Best Use |
|------------|--------|------------|----------|
| **Clash Detection** | ✅ Fast (R-tree) | ✅ Standard | Bonsai for batch, Navis for review |
| **Cascade Analysis** | ✅ AI grouping | ❌ Manual | Bonsai finds root causes |
| **BCF Export** | ✅ BCF 2.1 | ✅ BCF 2.1 | Round-trip coordination |
| **Cost Intelligence** | ✅ Integrated | ❌ No | Bonsai for business case |
| **3D Navigation** | ⚠️ Blender UI | ✅ Optimized | Navis for daily review |
| **License Cost** | 🆓 Free | 💰 $3,600/year | Bonsai for tight budgets |

**Recommended Workflow:**
1. **Bonsai**: Batch clash detection + intelligent analysis
2. **Export BCF**: Share findings with Autodesk teams
3. **Navisworks**: Review in familiar interface
4. **Update BCF**: Mark status, add comments
5. **Round-trip**: Import updated BCF into Bonsai for verification

---

## Quick Start Guide

### For Navisworks Users Receiving BCF from Bonsai

**Step 1: Receive BCF File**
```
You receive: ClashReport_Week12.bcfzip (email or cloud)
```

**Step 2: Import into Navisworks**
1. Open Navisworks Manage
2. **Viewpoint** tab → **BCF** → **Import**
3. Select `ClashReport_Week12.bcfzip`
4. Click **Open**

**Step 3: Navigate to Clashes**
1. **Viewpoint** panel → Expand topics
2. Click any topic (e.g., "Clash: Pipe vs Duct")
3. Viewport jumps to clash location
4. Red highlighting shows clashing elements

**Step 4: Update Status**
1. Right-click topic → **Add Comment**
2. Type: "Duct rerouted 800mm north, resolved"
3. Change status: **Open** → **Resolved**
4. **Viewpoint** → **BCF** → **Export**
5. Save as `ClashReport_Week12_UPDATED.bcfzip`
6. Email back to coordinator

---

## Workflow: Navisworks to Bonsai

### Scenario: You detect clashes in Navisworks, want Bonsai's intelligent analysis

**Step 1: Export IFC Models from Navisworks**

Navisworks doesn't export IFC directly. You need source models:

**Option A: From Revit**
```
Revit → File → Export → IFC
- IFC Version: IFC4 (or IFC2x3)
- Save to shared folder
```

**Option B: From Existing IFC**
```
If your federated model came from IFC files, use those originals
```

**Step 2: Load IFC into Bonsai**

1. **Open Blender** (with Bonsai addon installed)
2. **Bonsai** menu → **Federation** panel
3. Click **"Load Federation Database"**
4. Select your federation database (or create new)
5. IFC models auto-loaded into spatial database

**Step 3: Run Clash Detection in Bonsai**

1. **Federation** panel → **Clash Detection** section
2. Select disciplines:
   - **Discipline A**: MEP (e.g., ACMV, Plumbing)
   - **Discipline B**: Structure
3. Click **"Detect Clashes (Preview)"**
4. Results appear in panel (e.g., "252 clashes found")

**Step 4: Generate Intelligent Clash Report**

1. Click **"Generate Clash Report"**
2. Bonsai analyzes clashes:
   - ✅ Groups cascading clashes (finds root causes)
   - ✅ Calculates resolution costs
   - ✅ Prioritizes by severity
3. Report saved to `clash_reports/clash_resolution_YYYYMMDD_HHMMSS/`

**Step 5: Review Report (Markdown Format)**

```
📄 report.md - Open in any text editor or Markdown viewer
📂 snapshots/ - PNG images of each cascade group
```

**Key Sections:**
- **Executive Summary**: Total clashes, cascade efficiency
- **Group 1: CASCADE CLASH PATTERN**
  - Root cause: "Opening (2eD_GMhN)"
  - Affected elements: 8 clashes
  - Resolution strategy: "Adjust opening position"
  - Estimated cost: $1,200 design + $800 construction

**Step 6: Export BCF for Navisworks Team**

1. **Federation** panel → **BCF Export**
2. Click **"Export BCF 2.1"**
3. Select clashes to include (or select all)
4. BCF file generated: `clash_export_YYYYMMDD.bcfzip`
5. Share with Navisworks users

---

## Workflow: Bonsai to Navisworks

### Scenario: Bonsai detects clashes, Navisworks team resolves them

**Step 1: Bonsai Generates BCF**

(As per Step 6 above)

**Step 2: Navisworks Imports BCF**

```
Navisworks Manage:
1. Viewpoint → BCF → Import
2. Select clash_export_YYYYMMDD.bcfzip
3. Topics appear in Viewpoint panel
```

**Step 3: Navisworks User Reviews Clashes**

**What You See:**
- Topic: "Clash: Pipe Fitting (Aras 02) vs Opening"
- Snapshot: 3D view with red highlighting
- Description: Element details, disciplines, status
- Comments: Any notes from Bonsai coordinator

**What You Do:**
1. Click topic → Viewport jumps to clash
2. Use Section Box to inspect closely
3. Measure clearances with Measure Tools
4. Decide resolution:
   - **Reroute**: Change MEP layout
   - **Adjust**: Move opening/structural element
   - **Acceptable**: Document why (e.g., "Non-critical, 50mm clearance OK")

**Step 4: Update BCF Status**

```
Right-click topic:
- Add Comment: "Pipe rerouted via north corridor, clearance 200mm"
- Change Status: Open → Resolved
- Assign To: [Your name]
```

**Step 5: Export Updated BCF**

```
Viewpoint → BCF → Export
- Filename: clash_export_YYYYMMDD_RESOLVED.bcfzip
- Send back to Bonsai coordinator
```

**Step 6: Bonsai Verifies Resolutions**

*(Coordinator imports updated BCF into Bonsai, re-runs detection to confirm)*

---

## BCF Export & Import

### BCF 2.1 Compatibility

Bonsai exports **BCF 2.1** format, fully compatible with:

| Software | Import | Export | Round-trip |
|----------|--------|--------|------------|
| **Navisworks 2024** | ✅ | ✅ | ✅ |
| **Navisworks 2023** | ✅ | ✅ | ✅ |
| **Revit 2024** | ✅ | ✅ | ✅ |
| **BIM 360 / ACC** | ✅ | ✅ | ✅ |
| **Solibri** | ✅ | ✅ | ✅ |
| **BIMcollab** | ✅ | ✅ | ✅ |

### What's Included in Bonsai BCF?

**Per Topic (Clash):**
```xml
✅ Topic GUID (unique ID)
✅ Title: "Clash: Pipe Fitting vs Opening"
✅ Description: Element details, disciplines
✅ Status: Open / In Progress / Resolved
✅ Priority: High / Medium / Low
✅ Viewpoint:
   - Camera position (location, target, up vector)
   - Element GUIDs (IFC references)
✅ Snapshot: PNG image (800x600, ~200KB)
   - Red highlighting on clashing elements
   - Isometric view (~45° angle)
```

### BCF Import into Navisworks

**Automatic Mapping:**

| Bonsai BCF Field | Navisworks Field |
|------------------|------------------|
| Topic Title | Issue Name |
| Description | Comments |
| Status (NEW) | Active |
| Status (RESOLVED) | Closed |
| Priority (HIGH) | Critical |
| Viewpoint → Camera | Saved Viewpoint |
| Element GUIDs | Search Sets (if IFC loaded) |

**Known Limitations:**

⚠️ **GUID Matching**: Navisworks must have **same IFC files loaded** for element highlighting to work
- If models differ → Viewpoint works, but element selection may fail
- Solution: Ensure Navisworks uses **exact same IFC exports** as Bonsai

⚠️ **Snapshot Rendering**: Bonsai snapshots are Blender-rendered
- May look different from Navisworks viewport
- Viewpoint data is accurate, visual style differs

### BCF Import into Revit

**Steps:**
```
Revit 2024:
1. Add-Ins → BCF Manager
2. Import BCF
3. Issues appear in BCF Browser
4. Click issue → Model view aligns to viewpoint
```

**Limitation:**
- Revit BCF import requires **model elements** in current file
- If clash involves linked models → Manual navigation needed

---

## Clash Reports for Autodesk Teams

### Report Format Options

Bonsai generates **Markdown (.md) reports** optimized for Autodesk workflows:

**Option 1: View in Text Editor**
```
- Notepad++ (Windows)
- VS Code (Windows/Mac/Linux)
- Any Markdown viewer
```

**Option 2: Convert to PDF**
```bash
# Using Pandoc (free tool)
pandoc report.md -o report.pdf
```

**Option 3: Convert to Word**
```bash
pandoc report.md -o report.docx
```

**Option 4: View in Browser**
```
- Drag report.md into Chrome/Edge
- Install Markdown Viewer extension
```

### Report Structure

**Executive Summary (Page 1)**
```
- Total clashes: 252
- Cascade groups: 13 (62 clashes grouped)
- Ungrouped: 190 isolated clashes
- Estimated cost: $26,169 (design + construction)
- ROI: 1.2x (every $1 in design saves $1.20 in field)
```

**Per Cascade Group (Pages 2+)**
```
## GROUP 1: CASCADE CLASH PATTERN

Root Cause Element: Opening (GUID: 2eD_GMhN)
Impact: 8 clashes
Severity: HIGH

Affected Neighboring Elements:
| # | Element A | Element B | Disciplines | Status |
|---|-----------|-----------|-------------|--------|
| 1 | [Pipe Fitting (Aras 02)](snapshots/group_1_overview.png) | [Opening](snapshots/group_1_overview.png) | Plumbing vs Architecture | NEW |
| 2 | [Pipe Segment (Aras 02)](snapshots/group_1_overview.png) | [Opening](snapshots/group_1_overview.png) | Plumbing vs Architecture | NEW |

[Snapshot: Red highlighted elements in 3D view]

Resolution Strategy:
- Option 1: Adjust opening position (Cost: $400)
- Option 2: Reroute plumbing (~$1,200)

Recommendation: Adjust opening (cheaper, less cascade impact)
```

### Using Reports in Coordination Meetings

**Typical Agenda:**

1. **Present Executive Summary (5 min)**
   - Show stakeholders total clashes, cost impact
   - Highlight cascade groups vs isolated issues

2. **Review High-Priority Groups (20 min)**
   - Show snapshots on screen
   - Discuss root causes
   - Assign responsibility per discipline

3. **Assign Actions (10 min)**
   - MEP: Resolve Groups 1-5 (25 clashes)
   - Structure: Resolve Groups 6-8 (15 clashes)
   - Architecture: Adjust openings in Groups 1, 3

4. **Set Deadlines**
   - Critical: Resolve by Friday
   - Major: Resolve by next week
   - Normal: Ongoing

**Pro Tip**: Print PDF report and distribute to all attendees

---

## Troubleshooting

### "BCF Import Failed in Navisworks"

**Symptoms:**
```
Error: "Cannot import BCF file"
```

**Solutions:**

1. **Check BCF Version**
   - Bonsai exports BCF 2.1
   - Navisworks 2021+ supports BCF 2.1
   - Older Navisworks → Upgrade or use Solibri

2. **Verify ZIP Structure**
   ```
   clash_export.bcfzip
   ├── bcf.version (XML)
   ├── markup.bcf (XML)
   └── [topic-guid]/
       ├── markup.bcf
       └── snapshot.png
   ```

3. **Try Manual Extraction**
   - Rename `.bcfzip` → `.zip`
   - Extract contents
   - Import individual markup.bcf files

### "Viewpoints Don't Match in Navisworks"

**Symptoms:**
- BCF imports successfully
- Clicking topic → Viewport doesn't move correctly

**Cause**: Coordinate system mismatch

**Solution:**
1. Verify Navisworks units match IFC units (meters)
2. Check if federated model has correct origin
3. Re-export IFC with consistent coordinates

### "Element GUIDs Not Found"

**Symptoms:**
- BCF imports
- Viewpoint works
- But elements not highlighted/selected

**Cause**: Navisworks doesn't have matching IFC elements

**Solution:**
1. **Check IFC is Loaded**
   - Navisworks → Selection Tree → Verify IFC files present
2. **Verify GUID Matching**
   - Bonsai uses IFC GUIDs (GlobalId)
   - Navisworks must have **same IFC files** Bonsai used
3. **Reload Models**
   - File → Append → Add IFC files
   - Refresh Selection Tree

### "Snapshots Look Different"

**Expected Behavior**: Bonsai snapshots are Blender-rendered, Navisworks uses different rendering engine

**Not a Bug**: Visual style differs, but viewpoint data is accurate

**If Concerned**:
- Use Viewpoint data (camera position) as source of truth
- Snapshots are reference only

---

## FAQ

### Can Bonsai replace Navisworks?

**Short Answer**: Not entirely, but it can **reduce Navisworks seats** significantly.

**Long Answer**:
- **Batch Clash Detection**: ✅ Bonsai is faster (R-tree indexing)
- **Intelligent Analysis**: ✅ Bonsai's cascade grouping > Navisworks manual grouping
- **Daily Review**: ❌ Navisworks has better 3D navigation for end users
- **Coordination Meetings**: ⚠️ Either works (preference-based)

**Recommended Split**:
- **1 Bonsai seat** (coordinator): Batch detection + analysis
- **2-3 Navisworks seats** (team leads): Daily review + meetings
- **Everyone else**: BCF import into Revit/Solibri/free viewers

**Savings**: $7,200/year (avoiding 2 Navisworks licenses)

### Does Bonsai support BCF 3.0?

**Currently**: BCF 2.1 only

**Reason**: BCF 2.1 is industry standard (2014), widely supported

**BCF 3.0**: Newer (2019), limited adoption (Solibri, BIMcollab)

**Autodesk Support**:
- Navisworks 2024: BCF 2.1 ✅, BCF 3.0 ❌
- BIM 360: BCF 2.1 ✅, BCF 3.0 ⚠️ (partial)

**Roadmap**: BCF 3.0 support planned for Bonsai v2.0 (2026)

### Can I edit clash reports?

**Yes!** Reports are **editable Markdown (.md) files**

**Common Edits**:
```markdown
1. Add project-specific notes
2. Customize resolution strategies
3. Update cost estimates
4. Add meeting action items
```

**Workflow**:
1. Open `report.md` in text editor (VS Code, Notepad++)
2. Edit sections (Markdown syntax)
3. Save file
4. Convert to PDF: `pandoc report.md -o report.pdf`
5. Distribute to team

### What if clashes are resolved in Revit, not Navisworks?

**Workflow:**

1. **Receive BCF from Bonsai** → `clashes.bcfzip`
2. **Import into Revit**:
   - Add-Ins → BCF Manager → Import
3. **Resolve Clashes in Revit**:
   - Modify elements directly
   - Update BCF status in BCF Browser
4. **Export Updated BCF**:
   - BCF Manager → Export
5. **Send to Coordinator**:
   - Email `clashes_RESOLVED.bcfzip`

**Bonsai Verification**:
- Coordinator imports updated BCF
- Re-exports IFC from Revit
- Re-runs clash detection to verify

### How do I share reports with non-technical stakeholders?

**Problem**: Stakeholders don't use BIM software

**Solution: Convert to Familiar Formats**

**Option 1: PDF Report**
```bash
pandoc report.md -o clash_report.pdf
```
- ✅ Universal format (print, email, archive)
- ✅ Embeds snapshots automatically
- ✅ Readable by anyone

**Option 2: PowerPoint (for meetings)**
```bash
pandoc report.md -o presentation.pptx
```
- ✅ Edit slides in PowerPoint
- ✅ Add company branding
- ✅ Present in coordination meetings

**Option 3: Excel (for tracking)**
- Export clash table to CSV
- Import into Excel for status tracking
- Add formulas for % resolved

**Option 4: Email Summary**
```
Subject: Clash Detection Summary - Week 12

Executive Summary:
- 252 clashes detected
- 13 cascade groups identified
- Estimated impact: $26,000

Action Required:
- MEP Team: Resolve 62 clashes (Groups 1-5)
- Structure: Resolve 15 clashes (Groups 6-8)

Deadline: Friday, 5 PM

Full report attached (PDF)
```

---

## Additional Resources

### Bonsai Documentation

- **Official Docs**: [https://docs.bonsaibim.org](https://docs.bonsaibim.org) *(hypothetical)*
- **GitHub Repo**: [https://github.com/IfcOpenShell/IfcOpenShell](https://github.com/IfcOpenShell/IfcOpenShell)
- **Community Forum**: BlenderBIM Add-on discussions

### BCF Resources

- **buildingSMART BCF Spec**: [https://www.buildingsmart.org/standards/bsi-standards/bim-collaboration-format-bcf/](https://www.buildingsmart.org/standards/bsi-standards/bim-collaboration-format-bcf/)
- **BCF Viewers**: BIMcollab Zoom (free), Solibri Anywhere (free)

### Autodesk Resources

- **Navisworks BCF Guide**: Autodesk Knowledge Network
- **Revit BCF Manager**: Add-Ins documentation
- **BIM 360 BCF Workflow**: Autodesk Construction Cloud docs

---

## Support & Contact

**For Bonsai Issues**:
- GitHub Issues: [IfcOpenShell/IfcOpenShell/issues](https://github.com/IfcOpenShell/IfcOpenShell/issues)
- Community Forum: OSArch.org

**For BCF Compatibility Issues**:
- Email: [your-support-email]
- Include: BCF file, Navisworks version, error message

**For Training**:
- Contact BIM coordination team for onboarding sessions

---

**Document End** | Version 1.0 | 2025-11-07
