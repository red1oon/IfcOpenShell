# Federation Analysis Database Schemas

SQL schema definitions for the federation analysis module.

## Files

### `initialize_federation_database_COMPLETE.sql`
**Complete consolidated schema** for fresh database creation.

**Includes:**
- Core federation tables (elements_meta, spatial_structure, etc.)
- Clash detection and grouping tables
- Resolution engine tables (options, costs, learning)
- BOQ/QTO tables
- IFC label dictionary tables (optional)

**Usage:**
```bash
sqlite3 DatabaseFiles/new_database.db < sql_schema/initialize_federation_database_COMPLETE.sql
```

**Sections:**
1. Core Federation Tables (geometry, metadata)
2. Clash Detection System
3. Clash Grouping & Analysis
4. Resolution System (options, activities, costs)
5. Learning & Metrics
6. BOQ/QTO System
7. Conduit Routing
8. Discipline Rates
9. IFC Label Dictionary (optional)

---

### `initialize_ifc_label_dictionary.sql`
**Optional**: Populate ifc_labels table with standard friendly names.

**Purpose:**
- Maps cryptic IFC class names to human-readable labels
- Used by `ifc_label_mapper.py` for report generation
- Customizable per-project or organization

**Usage:**
```bash
# Optional - system has fallback labels
sqlite3 DatabaseFiles/database.db < sql_schema/initialize_ifc_label_dictionary.sql
```

**Examples:**
- `IfcDuct` → "HVAC Duct"
- `IfcPipeFitting` → "Pipe Fitting"
- `IfcOpeningElement` → "Opening"

**Note:** The system works perfectly fine WITHOUT this table. It has a fallback in-memory dictionary in `ifc_label_mapper.py`. Use this SQL script only if you want to customize labels per-project.

---

## Schema Version

**Current Version:** 3.0 (2025-11-07)

**Status:** POC Phase
- Some Python files still have hardcoded CREATE TABLE statements
- Production migration path documented in COMPLETE schema file
- Schema consolidation ongoing

---

## Development Notes

**Location Strategy:**
- These schemas are safekept in the git repository
- Working copies in `~/Documents/bonsai/Scripts/` are preserved for backward compatibility
- This `sql_schema/` directory is the canonical source of truth for version-controlled schemas
- Do NOT overwrite old scripts in Scripts/ - they may have local customizations

**Backward Compatibility:**
- All existing databases continue to work without schema changes
- `ifc_labels` tables are OPTIONAL - system has fallback behavior
- CREATE TABLE statements use `IF NOT EXISTS` - safe to run multiple times
- Python code checks for table existence before querying

**Future Work:**
- Schema migration system (version upgrades)
- Database validation utility
- Remove hardcoded CREATE TABLE from Python files
