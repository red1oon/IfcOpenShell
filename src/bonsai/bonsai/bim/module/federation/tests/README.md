# Federation Analysis Regression Tests

Comprehensive test suite for the `federation_analysis` add-on module.

## Test Coverage

### 1. Clash Detection (`test_1_clash_detection.py`)
- R-tree based bbox clash detection
- Discipline filtering
- Clash candidate generation
- Database query performance

### 2. Routing & Pathfinding (`test_2_routing_pathfinding.py`)
- A* pathfinding algorithm
- Endpoint connection logic
- Obstacle avoidance
- Path waypoint generation

### 3. Visualization & Shapes (`test_3_visualization_shapes.py`)
- GPU overlay rendering (import checks)
- Gizmo marker creation (import checks)
- Semantic shape generation
- Procedural shape templates

### 4. Database Queries (`test_4_database_queries.py`)
- Spatial index queries
- Element metadata retrieval
- Bbox center calculations
- GUID lookups

## Running Tests

### Individual Test Suite:
```bash
python3 test_1_clash_detection.py <database_path>
```

### All Tests:
```bash
cd ~/Projects/IfcOpenShell/src/bonsai/bonsai/tests/regression/federation_analysis
python3 run_tests.py ~/Documents/bonsai/DatabaseFiles/sample_extracted_v3.db
```

### From Main Regression Suite:
```bash
cd ~/Projects/IfcOpenShell/src/bonsai/bonsai/tests/regression
./run_tests.sh ~/Documents/bonsai/DatabaseFiles/sample_extracted_v3.db
```

## Test Philosophy

- **Fast**: All tests complete in <5 seconds total
- **Independent**: Each test can run standalone
- **Deterministic**: Same input = same output
- **Focused**: Test one thing at a time
- **Clear**: Test names describe what they test
- **Resilient**: Graceful failure with helpful error messages

## Database Requirements

Tests require a valid federation database with:
- `elements_meta` table (GUIDs, disciplines, IFC classes)
- `elements_rtree` table (spatial index with camelCase: minX, maxX, etc.)
- At least 100 elements for meaningful tests
- Multiple disciplines (ELEC, ACMV, FP, etc.)

## Adding New Tests

1. Create test function: `def test_feature_name(db_path):`
2. Return tuple: `(success: bool, message: str)`
3. Add to `get_tests()` list
4. Document in this README

## Maintainer Notes

- Tests run on every refactoring (see StandingInstructions.txt)
- Keep tests simple - avoid Blender dependencies (import checks only)
- Use sample database for CI/CD (21MB, ~500 elements)
- Full database for comprehensive validation (288MB, 49K elements)
