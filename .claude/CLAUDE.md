# IfcOpenShell/Bonsai Federation Development

## 🚨 MANDATORY BEHAVIOR RULES

**NEVER CREATE FILES WITHOUT EXPLICIT USER REQUEST:**
- ❌ NO summaries, reports, documentation files unless user says "create a file"
- ❌ NO .md, .txt, .json files proactively
- ❌ NO "let me document this" - DON'T
- ✅ ONLY create files when user explicitly asks: "write this to a file", "create a document", etc.

**BE CONCISE:**
- Keep ALL responses short and direct
- No verbose explanations or elaborations
- Answer the question, nothing more

---

## 📋 Session Startup Protocol

Check WORK_DIR for context files if they exist (StandingInstructions.txt, prompt.txt).

---

## 🔧 Critical Paths

```bash
# Git Repository (CODE - where we commit)
/home/red1/Projects/IfcOpenShell/
Branch: feature/IFC4_DB
Remote: https://github.com/red1oon/IfcOpenShell.git
Main branch: v0.8.0

# WORK_DIR (ALL working data - git-ignored, self-contained)
/home/red1/Projects/IfcOpenShell/WORK_DIR/
├── databases/              # Federation databases (symlinked)
│   ├── Terminal1_ARC_STR.db (2,129 elements, 5 disciplines)
│   ├── enhanced_federation.db
│   └── clash_status.db
├── ifc_sources/           # IFC source files (symlinked)
│   └── Terminal_1_IFC4/   (8 disciplines)
├── boq_reports/           # BOQ/QTO Excel exports (symlinked)
│   ├── BOQ_Comprehensive_20251115_140939.xlsx
│   ├── Terminal1_Professional_BOQ.xlsx
│   └── Terminal1_Final_BOQ.xlsx
├── schedules/             # 4D schedule files (.mpp, .xml)
├── clash_reports/         # BCF clash reports
├── test_outputs/          # Generated test artifacts
├── StandingInstructions.txt  # Development protocols
├── prompt.txt             # Current session context
└── PROJECT_STATUS_4D_READINESS.md  # Implementation guide

# Blender Installations
~/blender-4.2.14/blender
~/blender-4.5.3/blender

# Screenshots (read-only reference)
~/Pictures/Screenshots/

```

---

## 🎯 Project Status Summary

### ✅ COMPLETED (5D BIM Achievement)
1. **Federation Module** - 8 IFC source files → Unified database
   - ARC (895), STR (250), FP (508), ELEC (312), ACMV (164)
   - Total: 2,129 elements in federated model
2. **Blender Integration** - blend_cache.py resolves LOD300 geometry
3. **MEP Routing** - Clash detection, routing optimization
4. **BOQ/QTO (5D)** - Bill of Quantities exports, cost analysis
5. **2DtoBlender** - PDF→Blender complete (100% coverage, Rule 0 compliant)

### 🎯 CURRENT FOCUS
4D scheduling integration

---

## ⚠️ Critical Warnings

### DO NOT:
- Modify IFC geometry coordinates without verification
- Commit large binaries (.db, .blend, .dwg files > 100MB)
- Mix custom code with Bonsai core modules

### ALWAYS:
- Search existing code before creating new files (use Grep/Glob)
- `git fetch origin` before pushing

---

## 🔄 Workflow

1. Edit code: `src/bonsai/bonsai/bim/module/federation/`
2. Test with data: `WORK_DIR/databases/`
3. Commit from this directory
4. Push to branch: `feature/IFC4_DB`

---

## 📚 Key Documentation

**Code:**
- `src/bonsai/bonsai/bim/module/federation/` - Federation core module

---

## 🎯 POC Autonomy Mode

Full autonomy for all operations in:
- **WORK_DIR/** - All working data files (databases, reports, artifacts)
- **src/bonsai/bonsai/bim/module/federation/** - Federation module code
- **Test files, scripts** - Development and testing work

No permission needed for: file creation/modification, code execution, testing.

**Exception:** Ask before committing at major milestones.

**Note:** WORK_DIR is git-ignored - safe for large files, databases, test outputs.

---

**Note:** This CLAUDE.md serves as a quick reference. All detailed instructions are in the referenced files above.
