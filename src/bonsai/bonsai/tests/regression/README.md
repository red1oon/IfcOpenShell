# Federation Database Regression Tests

**Fast (<1 second) black-box testing to catch breakage early**

## Quick Start

```bash
# From anywhere (auto-detects latest database):
cd ~/Documents/bonsai/Scripts/regression_tests
./run_tests.sh

# Or run directly with specific database:
python3 run_tests.py /path/to/database.db
```

## What Gets Tested

**18 tests across 4 critical areas:**

1. **Schema Integrity** (5 tests)
   - R-tree uses camelCase columns (prevents Oct 31 regression)
   - Critical tables exist (elements_meta, base_geometries, etc.)
   - Column counts match expected schema
   - No NULL violations in required fields
   - Global offset table present

2. **Coordinate System** (5 tests)
   - Global offset table exists
   - Element coordinates within reasonable ranges
   - No elements stuck at (0,0,0) origin
   - Coordinates stored in meters (not millimeters)
   - R-tree queryable and consistent

3. **Routing Critical Path** (3 tests)
   - Discipline filtering works
   - Pathfinding data available (ELEC elements, floor metadata)
   - Element metadata complete (100% coverage expected)

4. **Material Data Quality** (5 tests)
   - Material coverage reasonable (>10% of elements)
   - RGBA values in valid range (0.0-1.0)
   - Common materials extractable
   - Discipline fallback data present
   - Material names paired with colors

## Expected Output

```
======================================================================
FEDERATION DATABASE REGRESSION TESTS (Python Mode)
======================================================================
Database: /home/red1/Documents/bonsai/DatabaseFiles/sample_extracted_v3.db
Size: 287.3 MB
======================================================================

[... test results ...]

======================================================================
SUMMARY
======================================================================
Total: 18 tests
Passed: 18 ✓
Failed: 0 ✗
Time: 0.1 seconds
======================================================================

✅ ALL TESTS PASSED
```

## When to Run

**ALWAYS run before:**
- Committing database schema changes
- Merging upstream Bonsai updates
- Releasing to users
- After modifying extraction scripts

**Run automatically:**
```bash
# Add to your pre-commit workflow:
git fetch origin
~/Documents/bonsai/Scripts/regression_tests/run_tests.sh
git add . && git commit -m "..."
```

## Understanding Failures

**Common failure scenarios:**

### Schema Integrity Failure
```
[✗ FAIL] R-tree camelCase: Missing column 'minX'
```
→ **Fix:** Database extraction reverted to snake_case. Re-extract with correct schema.
→ **Reference:** CheatSheet rule #2, commit 0a60f31d1

### Coordinate System Failure
```
[✗ FAIL] Global offset: (0, 0, 0) detected
```
→ **Fix:** Coordinate system metadata not populated during extraction.
→ **Reference:** "Visualization sizing hell" in prompt.txt

### Routing Data Failure
```
[✗ FAIL] Pathfinding data: No ELEC elements found
```
→ **Fix:** Database may be from non-MEP project or discipline filter broken.
→ **Check:** SQL query `SELECT COUNT(*) FROM elements_meta WHERE discipline = 'ELEC'`

### Material Quality Failure
```
[✗ FAIL] Material coverage: 2.1% (expected >10%)
```
→ **Fix:** IFC color extraction may have failed during database creation.
→ **Reference:** prompt.txt "IFC Color Extraction" section

## Test Files

- `run_tests.sh` - Master runner (auto-detects database, colorized output)
- `run_tests.py` - Python orchestrator (parallel test execution)
- `test_1_schema.py` - Database structure validation
- `test_2_coordinates.py` - Coordinate system sanity checks
- `test_3_routing.py` - Pathfinding data availability
- `test_4_materials.py` - Material extraction quality

## Design Philosophy

**Why these tests?**

1. **Fast:** <1 second = no excuse not to run
2. **Edge checking:** Tests breakage-prone areas (not exhaustive QA)
3. **Black box:** Database-only, no Blender/Bonsai dependencies
4. **Lifeline alarm:** Fail fast when critical bugs introduced

**What's NOT tested:**
- Full pathfinding algorithms (tested separately)
- Blender visualization (requires UI tests)
- IFC file parsing (upstream responsibility)
- Performance benchmarks (not regression scope)

## Extending Tests

**To add a new test:**

1. Edit appropriate test file (e.g., `test_2_coordinates.py`)
2. Add test function:
   ```python
   def test_new_check(db_path):
       """Description of what this checks"""
       try:
           # Your validation logic
           if condition_passes:
               return True, "Success message"
           else:
               return False, "Failure details"
       except Exception as e:
           return False, f"Error: {e}"
   ```
3. Register in `run_*_tests()` function
4. Run `./run_tests.sh` to verify
5. Commit with descriptive message

## Troubleshooting

**Tests won't run:**
```bash
# Ensure scripts are executable:
chmod +x run_tests.sh *.py

# Check Python available:
python3 --version  # Should be 3.8+

# Verify database path:
ls -lh ~/Documents/bonsai/DatabaseFiles/*.db
```

**Import errors in test_3_routing.py:**
→ Expected if running without Blender environment. Spatial index tests are commented out for standalone mode.

**Database not found:**
→ Tests look for latest DB in `~/Documents/bonsai/DatabaseFiles/`. Create symlink or specify path manually.

## Integration with CI/CD

**Future: Automated testing pipeline**

```yaml
# .github/workflows/test-federation.yml (example)
name: Federation Regression Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run regression tests
        run: |
          python3 src/bonsai/bonsai/tests/regression/run_tests.py test.db
```

## Performance Baseline

**Tested on:**
- Database: sample_extracted_v3.db (287 MB, 49,059 elements)
- Hardware: Standard developer laptop
- Runtime: 0.1 seconds
- Pass rate: 18/18 (100%)

**Scaling:**
- Small DB (~500 elements): <0.05s
- Full DB (~50K elements): ~0.1s
- Very large DB (>500K elements): <0.5s expected

## Support

**Questions or issues:**
1. Check `ProjectKnowledge/Test_Suite_Architecture.md` (detailed design)
2. Review `ProjectKnowledge/Bridge_Compliance_Audit_*.md` (test rationale)
3. See commit 6723bba7e for implementation details

**Trigger phrase for Claude Code:**
- "test the db" → Runs Python mode tests

---

**Last Updated:** 2025-11-02
**Status:** Production ready (18/18 tests passing)
**Maintenance:** Extend as new features added, keep fast (<1s target)
