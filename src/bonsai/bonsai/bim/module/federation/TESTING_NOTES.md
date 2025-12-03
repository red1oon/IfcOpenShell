# Federation CRUD - Testing Notes

**Date:** December 3, 2025
**Status:** ✅ Ready for testing (with prerequisites)

---

## ⚠️ IMPORTANT: Database Prerequisites

### DO NOT Use GI Database (Postponed)

The GI (Geometry Instancing) database has been **postponed** and needs proper rebuild.

**Do NOT use:**
- ❌ `enhanced_federation_GI.db` (old, archived)
- ❌ Any GI-related databases

**Use instead:**
- ✅ `enhanced_federation.db` (current working database)

---

## Testing Prerequisites

### Step 1: Run Schema Migration

**BEFORE testing CRUD operators, migrate the database:**

```bash
cd ~/Projects/IfcOpenShell/WORK_DIR/databases

sqlite3 enhanced_federation.db < migrate_add_source_tracking.sql
```

**Verify migration:**
```bash
sqlite3 enhanced_federation.db "PRAGMA table_info(elements_meta);"
```

**Should see these columns:**
- guid
- element_name
- ifc_class
- discipline
- **source** ← NEW (DEFAULT 'IFC')
- **created_timestamp** ← NEW
- **modified_timestamp** ← NEW

---

## Testing Workflow

### 1. Load Federation Database

```python
# In Blender
Properties Panel → Scene → Federation → Management
- Set database path: /path/to/enhanced_federation.db
- Click "Load Federation"
- Verify: "2,129 elements loaded" (or similar)
```

### 2. Test Add Operation

```python
# Create test object
Shift+A → Mesh → Cylinder
- Scale: (1.5, 1.5, 5.0)
- Location: (120, -20, 2.5)  # GPS coords
- Rotate: 90° on Y axis

# Add to federation
Properties Panel → Scene → Federation → Additions
- Select cylinder
- Click "Add to Federation"
- Dialog:
  - IFC Class: IfcTank
  - Discipline: SITE
  - Name: GasTank_Test_001
- Click OK

# Verify
- Check console for "Added GasTank_Test_001 to federation..."
- Object should have custom properties:
  - ifc_guid: [some GUID]
  - ifc_class: IfcTank
  - discipline: SITE
```

### 3. Test Update Operation

```python
# Move the object
G → Move cylinder to new position

# Update in database
Select cylinder → Click "Update in Federation"

# Verify
- Console: "Updated element ... in federation"
- Database should have new position
```

### 4. Test Query Operation

```python
Properties Panel → Federation → Additions
- Click "Query Additions"

# Check console output
Should show table:
GUID                 Name              Class         Discipline
----                 ----              -----         ----------
[guid]...            GasTank_Test_001  IfcTank       SITE
```

### 5. Test Persistence

```python
# Close Blender completely
# Reopen Blender
# Load federation database again
Properties → Federation → Management → Load Federation

# Gas tank should appear in viewport!
```

### 6. Test Remove Operation

```python
# Select gas tank
Properties → Federation → Additions → "Remove from Federation"
- Confirm dialog

# Verify
- Console: "Removed element ... from federation"
- Object custom properties cleared
- Database no longer has element
```

---

## Database Verification (SQL)

### Check Schema Migration
```sql
sqlite3 enhanced_federation.db "SELECT source, created_timestamp FROM elements_meta LIMIT 5;"
```

### Query Manual Additions
```sql
sqlite3 enhanced_federation.db "
SELECT guid, element_name, ifc_class, discipline, source
FROM elements_meta
WHERE source = 'MANUAL';
"
```

### Check Counts
```sql
sqlite3 enhanced_federation.db "
SELECT
    COUNT(*) as total,
    COUNT(CASE WHEN source='IFC' THEN 1 END) as ifc_elements,
    COUNT(CASE WHEN source='MANUAL' THEN 1 END) as manual_additions
FROM elements_meta;
"
```

---

## Testing New Unified Tab (Experimental)

### Location
```
Properties Panel → Scene → Federation (NEW unified section)
```

### Sub-panels
1. **Management** - Load/unload database
2. **Additions ⭐** - CRUD operations (killer feature!)
3. **Clash Detection** - Quick clash by discipline
4. **MEP Engineering** - Routing (shown when MEP disciplines loaded)
5. **4D/5D BIM** - Schedule/BOQ export
6. **AI Query** - NLP search
7. **Digital Twin** - Asset/IoT management

### Compare Workflows
- **Old way:** Scattered panels in Scene properties
- **New way:** Everything under "Federation" unified section

**Feedback questions:**
- Which feels more intuitive?
- Is "Additions" feature more discoverable in new tab?
- Does workflow feel more natural?
- Any confusion between old and new UI?

---

## Common Issues

### Issue: "Database schema needs migration"
**Solution:** Run `migrate_add_source_tracking.sql` first

### Issue: "Federation database not found"
**Solution:** Check path is absolute, not relative. Use file browser to select.

### Issue: "Object not tracked in federation"
**Solution:** Object must have been added via "Add to Federation" operator

### Issue: "Cannot remove IFC-sourced element"
**Solution:** Safety feature - only MANUAL additions can be removed

### Issue: Operators not showing up
**Solution:** Reload Bonsai addon or restart Blender

---

## Success Criteria

✅ **CRUD is successful if:**
1. Can add cylinder to database
2. Cylinder persists after closing/reopening Blender
3. Can update cylinder position in database
4. Can query manual additions
5. Can remove manual additions
6. IFC elements protected from deletion
7. No database corruption
8. Console shows clear feedback messages

---

## Next Steps After Testing

### If Successful
1. Test with more complex objects (meshes, groups)
2. Test batch operations (multiple objects)
3. Test edge cases (duplicate names, invalid coords)
4. Gather user feedback on UI
5. Plan Phase 2: Export to ADDITIONS.ifc

### If Issues Found
1. Check console for error messages
2. Verify database schema
3. Check object has valid geometry
4. Test with fresh database
5. Report bugs with steps to reproduce

---

## Future: GI Database Rebuild

**Postponed for separate task.**

**When ready:**
- See: `/WORK_DIR/docs/gi_geometry_instancing/GI_STRATEGY_RECOMMENDATION.md`
- Rebuild GI database with proper coordinate system
- Test CRUD on GI database
- Compare performance (GI vs non-GI)

---

## Files Modified

### Code
- `src/bonsai/bonsai/bim/module/federation/crud_operators.py` - NEW
- `src/bonsai/bonsai/bim/module/federation/ui.py` - MODIFIED (added panel)
- `src/bonsai/bonsai/bim/module/federation/ui_federation_tab.py` - NEW (experimental)
- `src/bonsai/bonsai/bim/module/federation/__init__.py` - MODIFIED (registration)

### Documentation
- `WORK_DIR/FEDERATION_CRUD_IMPLEMENTATION.md` - Complete guide
- `WORK_DIR/NEXT_STEPS_BEFORE_CRUD.md` - Prerequisites
- `WORK_DIR/test_federation_crud.py` - Test script
- `WORK_DIR/databases/migrate_add_source_tracking.sql` - Schema migration

---

**TL;DR:**
1. Run migration: `sqlite3 enhanced_federation.db < migrate_add_source_tracking.sql`
2. Load federation in Blender
3. Create cylinder, click "Add to Federation"
4. Verify persistence (reload Blender)
5. Test update/query/remove operations
6. Report feedback!
