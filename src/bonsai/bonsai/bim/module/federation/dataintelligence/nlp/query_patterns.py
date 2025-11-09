"""
Query Patterns for NLP-to-SQL Translation

Defines common patterns for converting natural language queries to SQL
using FTS5 full-text search capabilities.
"""

import re
from typing import Dict, List, Tuple, Optional


class QueryPattern:
    """Base class for query patterns."""

    def __init__(self, pattern: str, sql_template: str, description: str):
        self.pattern = re.compile(pattern, re.IGNORECASE)
        self.sql_template = sql_template
        self.description = description

    def matches(self, query: str) -> Optional[re.Match]:
        """Check if query matches this pattern."""
        return self.pattern.search(query)

    def extract_params(self, query: str) -> Dict[str, str]:
        """Extract parameters from query using pattern."""
        match = self.matches(query)
        if match:
            return match.groupdict()
        return {}


# Element Count Patterns
ELEMENT_COUNT_PATTERNS = [
    QueryPattern(
        pattern=r"how many (?P<element_type>\w+)",
        sql_template="""
            SELECT ifc_class, COUNT(*) as count
            FROM elements_meta
            WHERE ifc_class LIKE '%{element_type}%'
            GROUP BY ifc_class
        """,
        description="Count elements by type"
    ),
    QueryPattern(
        pattern=r"count (?P<element_type>\w+) (?:in|on) (?P<location>level|storey|floor) (?P<storey_num>\d+|[\w\s]+)",
        sql_template="""
            SELECT COUNT(*) as count
            FROM elements_meta
            WHERE ifc_class LIKE '%{element_type}%'
            AND storey LIKE '%{storey_num}%'
        """,
        description="Count elements on specific storey"
    ),
    QueryPattern(
        pattern=r"(?P<element_type>\w+) on (?:level|storey|floor) (?P<storey_num>\d+)",
        sql_template="""
            SELECT guid, ifc_class, storey, name
            FROM elements_meta
            WHERE ifc_class LIKE '%{element_type}%'
            AND storey LIKE '%{storey_num}%'
        """,
        description="List elements on specific storey"
    ),
]

# Manufacturer/Model Search Patterns
MANUFACTURER_PATTERNS = [
    QueryPattern(
        pattern=r"(?:find|show|list) (?P<element_type>\w+) (?:from|by|made by) (?P<manufacturer>[\w\s]+)",
        sql_template="""
            SELECT DISTINCT e.guid, e.ifc_class, e.name, p.property_value as manufacturer
            FROM elements_meta e
            JOIN element_properties p ON e.guid = p.guid
            WHERE e.ifc_class LIKE '%{element_type}%'
            AND p.property_name = 'Manufacturer'
            AND p.property_value MATCH '{manufacturer}*'
        """,
        description="Find elements by manufacturer"
    ),
    QueryPattern(
        pattern=r"(?:what|which) (?P<element_type>\w+) (?:are|is) (?P<manufacturer>[\w\s]+)",
        sql_template="""
            SELECT e.guid, e.ifc_class, e.name, p.property_value as manufacturer
            FROM elements_meta e
            JOIN element_properties p ON e.guid = p.guid
            WHERE e.ifc_class LIKE '%{element_type}%'
            AND p.property_name = 'Manufacturer'
            AND p.property_value MATCH '{manufacturer}*'
        """,
        description="Search elements by manufacturer"
    ),
]

# Property Search Patterns
PROPERTY_PATTERNS = [
    QueryPattern(
        pattern=r"(?:find|show) (?P<element_type>\w+) with (?P<property_name>\w+) (?:=|equal to|of) (?P<property_value>[\w\s\.]+)",
        sql_template="""
            SELECT e.guid, e.ifc_class, e.name, p.property_name, p.property_value
            FROM elements_meta e
            JOIN element_properties p ON e.guid = p.guid
            WHERE e.ifc_class LIKE '%{element_type}%'
            AND p.property_name LIKE '%{property_name}%'
            AND p.property_value LIKE '%{property_value}%'
        """,
        description="Find elements with specific property value"
    ),
    QueryPattern(
        pattern=r"(?:what|which) (?P<element_type>\w+) have (?P<property_name>[\w\s]+)",
        sql_template="""
            SELECT DISTINCT e.guid, e.ifc_class, e.name, p.property_value
            FROM elements_meta e
            JOIN element_properties p ON e.guid = p.guid
            WHERE e.ifc_class LIKE '%{element_type}%'
            AND p.property_name LIKE '%{property_name}%'
        """,
        description="List elements with specific property"
    ),
]

# Quantity Aggregation Patterns
QUANTITY_PATTERNS = [
    QueryPattern(
        pattern=r"total (?P<quantity_type>length|area|volume) of (?P<element_type>\w+)",
        sql_template="""
            SELECT ifc_class,
                   SUM(total_quantity) as total,
                   uom,
                   element_count
            FROM simple_qto
            WHERE ifc_class LIKE '%{element_type}%'
            AND quantity_name LIKE '%{quantity_type}%'
            GROUP BY ifc_class, uom
        """,
        description="Sum quantity for element type"
    ),
    QueryPattern(
        pattern=r"(?:sum|total) (?P<element_type>\w+) in (?P<discipline>[\w\s]+)",
        sql_template="""
            SELECT discipline, ifc_class,
                   SUM(total_quantity) as total,
                   uom
            FROM simple_qto
            WHERE ifc_class LIKE '%{element_type}%'
            AND discipline LIKE '%{discipline}%'
            GROUP BY discipline, ifc_class, uom
        """,
        description="Sum quantities by discipline"
    ),
]

# Free-Text Search Patterns
FREETEXT_PATTERNS = [
    QueryPattern(
        pattern=r"search for (?P<search_term>[\w\s]+)",
        sql_template="""
            SELECT guid, ifc_class, name, storey
            FROM elements_fts
            WHERE elements_fts MATCH '{search_term}'
            LIMIT 100
        """,
        description="Full-text search across elements"
    ),
    QueryPattern(
        pattern=r"find (?P<search_term>[\w\s]+)",
        sql_template="""
            SELECT DISTINCT e.guid, e.ifc_class, e.name, e.storey
            FROM elements_fts e
            WHERE e.elements_fts MATCH '{search_term}'
            LIMIT 100
        """,
        description="Full-text search"
    ),
]

# Discipline Breakdown Patterns
DISCIPLINE_PATTERNS = [
    QueryPattern(
        pattern=r"(?:show|list) (?P<discipline>[\w\s]+) (?:elements|items)",
        sql_template="""
            SELECT ifc_class, element_count, total_quantity, uom
            FROM simple_qto
            WHERE discipline LIKE '%{discipline}%'
            ORDER BY total_quantity DESC
        """,
        description="List all elements in a discipline"
    ),
    QueryPattern(
        pattern=r"(?:what|which) disciplines (?:are|exist)",
        sql_template="""
            SELECT DISTINCT discipline, COUNT(*) as element_types
            FROM simple_qto
            GROUP BY discipline
            ORDER BY discipline
        """,
        description="List all disciplines"
    ),
]


# All pattern categories
ALL_PATTERNS = {
    'element_count': ELEMENT_COUNT_PATTERNS,
    'manufacturer': MANUFACTURER_PATTERNS,
    'property': PROPERTY_PATTERNS,
    'quantity': QUANTITY_PATTERNS,
    'freetext': FREETEXT_PATTERNS,
    'discipline': DISCIPLINE_PATTERNS,
}


def find_matching_pattern(query: str) -> Tuple[Optional[QueryPattern], Optional[Dict[str, str]], Optional[str]]:
    """
    Find the best matching pattern for a query.

    Returns:
        (pattern, params, category) or (None, None, None) if no match
    """
    for category, patterns in ALL_PATTERNS.items():
        for pattern in patterns:
            if pattern.matches(query):
                params = pattern.extract_params(query)
                return pattern, params, category

    return None, None, None
