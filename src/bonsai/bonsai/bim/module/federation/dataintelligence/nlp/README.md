# NLP Query Module

Natural language query interface for the Federation data intelligence system using FTS5 full-text search.

## Overview

This module converts natural language queries into SQL statements that leverage the FTS5 full-text search capabilities of the extracted database.

## Components

### 1. `query_patterns.py`
Defines regex patterns for common query types:
- **Element Count**: "How many beams?", "Count doors on level 1"
- **Manufacturer Search**: "Find ducts from Carrier"
- **Property Search**: "Show elements with FireRating = 2HR"
- **Quantity Aggregation**: "Total length of pipes in MEP"
- **Free-text Search**: "Search for fire doors"
- **Discipline Breakdown**: "Show ACMV elements"

### 2. `query_parser.py`
Main parser class that:
- Cleans and normalizes natural language input
- Matches queries to patterns
- Generates SQL from templates
- Maintains query history
- Sanitizes inputs to prevent SQL injection

### 3. `query_executor.py`
Executes SQL queries and formats results:
- Connects to SQLite database
- Executes queries with timing
- Returns results as dictionaries
- Formats results as text tables
- Provides database introspection utilities

## Usage

### Basic Example

```python
from bonsai.bim.module.federation.dataintelligence.nlp import NLPQueryParser, QueryExecutor

# Initialize
db_path = "/path/to/sample_extracted_v3.db"
parser = NLPQueryParser()
executor = QueryExecutor(db_path)

# Parse natural language query
result = parser.parse("How many beams are there?")

if result['success']:
    print(f"SQL: {result['sql']}")
    print(f"Category: {result['category']}")

    # Execute the query
    query_result = executor.execute(result['sql'])

    if query_result['success']:
        print(f"Found {query_result['row_count']} results")
        print(executor.format_results_table(query_result))
    else:
        print(f"Error: {query_result['error']}")
else:
    print(f"Parse error: {result['error']}")
```

### Example Queries

**Element Counts:**
- "How many beams are there?"
- "Count doors on level 1"
- "Beams on floor 2"

**Manufacturer Search:**
- "Find ducts from Carrier"
- "Show pipes made by Victaulic"
- "Which lights are Philips?"

**Property Search:**
- "Find walls with FireRating = 2HR"
- "Show doors with height 2.1"
- "Which beams have LoadBearing property?"

**Quantity Aggregation:**
- "Total length of pipes"
- "Sum area of walls in ARC"
- "Total volume of slabs"

**Discipline Queries:**
- "Show ACMV elements"
- "List structural items"
- "Which disciplines exist?"

**Free-text Search:**
- "Search for fire doors"
- "Find emergency exits"
- "Locate sprinkler system"

## Query Pattern Structure

Each pattern consists of:
1. **Regex Pattern**: Captures query structure and parameters
2. **SQL Template**: SQL query with parameter placeholders
3. **Description**: Human-readable description

Example:
```python
QueryPattern(
    pattern=r"how many (?P<element_type>\w+)",
    sql_template="""
        SELECT ifc_class, COUNT(*) as count
        FROM elements_meta
        WHERE ifc_class LIKE '%{element_type}%'
        GROUP BY ifc_class
    """,
    description="Count elements by type"
)
```

## Database Requirements

The NLP module expects a database with FTS5 tables:

**Required Tables:**
- `elements_meta` - Element metadata (guid, ifc_class, name, storey, discipline)
- `element_properties` - Element properties (guid, property_name, property_value)
- `simple_qto` - Quantity take-off (ifc_class, discipline, total_quantity, uom)
- `elements_fts` - FTS5 virtual table for full-text search
- `properties_fts` - FTS5 virtual table for property search

## Security

The parser sanitizes all user inputs to prevent SQL injection:
- Removes dangerous characters
- Allows only: alphanumeric, space, dash, underscore, period
- Uses parameterized queries where possible

## Performance

- Average query time: ~0.12ms to 500ms depending on complexity
- FTS5 provides indexed full-text search for fast results
- LIMIT clauses prevent excessive result sets

## Integration with UI

See `../../ui.py` for integration with Blender UI panels. The NLP panel provides:
- Text input for natural language queries
- Suggested query buttons
- Results display with formatting
- Query history

## Future Enhancements

- **Fuzzy Matching**: Handle typos and variations
- **Multi-clause Queries**: "Find beams on level 1 from Acme"
- **Comparison Operators**: "Height > 3m", "Area between 10 and 20 m2"
- **Date Queries**: "Elements modified last week"
- **Spatial Queries**: "Elements near GUID xyz"
- **Export Results**: Export to CSV, Excel, or JSON

## Testing

See `../../../Scripts/test_nlp_queries_interactive.py` for comprehensive test suite with 13+ query patterns.

Run tests:
```bash
python test_nlp_queries_interactive.py /path/to/database.db
```

## Author

Generated with Claude Code for Bonsai BIM Federation Module.
