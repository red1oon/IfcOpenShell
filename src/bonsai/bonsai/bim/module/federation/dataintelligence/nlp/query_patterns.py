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
    # Storey-specific patterns must come FIRST to match before generic patterns
    QueryPattern(
        pattern=r"(?:how many|count|total|number of) (?P<element_type>\w+) on (?P<storey_num>\d+(?:st|nd|rd|th)?|first|second|third|\w+) (?:level|storey|floor)",
        sql_template="""
            SELECT 'STOREY_NOT_AVAILABLE' as result_type
        """,
        description="Storey information not available in database"
    ),
    QueryPattern(
        pattern=r"count (?P<element_type>\w+) (?:in|on|at) (?:level|storey|floor) (?P<storey_num>\d+|[\w\s]+)",
        sql_template="""
            SELECT 'STOREY_NOT_AVAILABLE' as result_type
        """,
        description="Storey information not available in database"
    ),
    QueryPattern(
        pattern=r"(?P<element_type>\w+) on (?:level|storey|floor) (?P<storey_num>\d+|\w+)",
        sql_template="""
            SELECT 'STOREY_NOT_AVAILABLE' as result_type
        """,
        description="Storey information not available in database"
    ),
    QueryPattern(
        pattern=r"(?:area|rooms?|spaces?) on (?:level|storey|floor) (?P<storey_num>\d+|first|second|third|1st|2nd|3rd|\w+)",
        sql_template="""
            SELECT 'STOREY_NOT_AVAILABLE' as result_type
        """,
        description="Storey information not available in database"
    ),
    # Generic element count patterns come AFTER storey patterns
    QueryPattern(
        pattern=r"(?:how many|count|total|number of) (?P<element_type>\w+)",
        sql_template="""
            SELECT ifc_class, COUNT(*) as count
            FROM elements_meta
            WHERE LOWER(ifc_class) LIKE LOWER('%{element_type}%')
            GROUP BY ifc_class
        """,
        description="Count elements by type"
    ),
    QueryPattern(
        pattern=r"(?P<element_type>\w+) (?:count|total|number)",
        sql_template="""
            SELECT ifc_class, COUNT(*) as count
            FROM elements_meta
            WHERE LOWER(ifc_class) LIKE LOWER('%{element_type}%')
            GROUP BY ifc_class
        """,
        description="Count elements by type"
    ),
]

# Manufacturer/Model Search Patterns
MANUFACTURER_PATTERNS = [
    QueryPattern(
        pattern=r"(?:find|show|list) (?P<element_type>\w+) (?:from|by|made by) (?P<manufacturer>[\w\s]+)",
        sql_template="""
            SELECT DISTINCT e.guid, e.ifc_class, e.element_name, p.property_value as manufacturer
            FROM elements_meta e
            JOIN element_properties p ON e.guid = p.guid
            WHERE LOWER(e.ifc_class) LIKE LOWER('%{element_type}%')
            AND p.property_name = 'Manufacturer'
            AND p.property_value LIKE '%{manufacturer}%'
        """,
        description="Find elements by manufacturer"
    ),
    QueryPattern(
        pattern=r"(?:what|which) (?P<element_type>\w+) (?:are|is) (?P<manufacturer>[\w\s]+)",
        sql_template="""
            SELECT e.guid, e.ifc_class, e.element_name, p.property_value as manufacturer
            FROM elements_meta e
            JOIN element_properties p ON e.guid = p.guid
            WHERE LOWER(e.ifc_class) LIKE LOWER('%{element_type}%')
            AND p.property_name = 'Manufacturer'
            AND p.property_value LIKE '%{manufacturer}%'
        """,
        description="Search elements by manufacturer"
    ),
]

# Property Search Patterns
PROPERTY_PATTERNS = [
    QueryPattern(
        pattern=r"(?:find|show) (?P<element_type>\w+) with (?P<property_name>\w+) (?:=|equal to|of) (?P<property_value>[\w\s\.]+)",
        sql_template="""
            SELECT e.guid, e.ifc_class, e.element_name, p.property_name, p.property_value
            FROM elements_meta e
            JOIN element_properties p ON e.guid = p.guid
            WHERE LOWER(e.ifc_class) LIKE LOWER('%{element_type}%')
            AND p.property_name LIKE '%{property_name}%'
            AND p.property_value LIKE '%{property_value}%'
        """,
        description="Find elements with specific property value"
    ),
    QueryPattern(
        pattern=r"(?:what|which) (?P<element_type>\w+) have (?P<property_name>[\w\s]+)",
        sql_template="""
            SELECT DISTINCT e.guid, e.ifc_class, e.element_name, p.property_value
            FROM elements_meta e
            JOIN element_properties p ON e.guid = p.guid
            WHERE LOWER(e.ifc_class) LIKE LOWER('%{element_type}%')
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
                   SUM(element_count) as element_count
            FROM simple_qto
            WHERE LOWER(ifc_class) LIKE LOWER('%{element_type}%')
            AND measurement_type LIKE '%{quantity_type}%'
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
            WHERE LOWER(ifc_class) LIKE LOWER('%{element_type}%')
            AND discipline LIKE '%{discipline}%'
            GROUP BY discipline, ifc_class, uom
        """,
        description="Sum quantities by discipline"
    ),
]

# Cost Estimation Patterns
COST_PATTERNS = [
    QueryPattern(
        pattern=r"(?:total|what is|what's|whats).{0,30}(?:material|labour|labor|equipment).{0,20}(?:cost|price)",
        sql_template="""
            SELECT 'BREAKDOWN_NOT_AVAILABLE' as result_type
        """,
        description="Cost breakdown not available - Generate BOQ first"
    ),
    QueryPattern(
        pattern=r"(?:how much does|what is|total|what's|whats).{0,20}(?:cost|price|budget)",
        sql_template="""
            SELECT SUM(total_cost_rm) as total_cost_rm
            FROM simple_qto
        """,
        description="Calculate total building cost"
    ),
    QueryPattern(
        pattern=r"(?:cost|price) (?:of |for )?(?P<discipline>[\w\s]+) (?:discipline|system|work)",
        sql_template="""
            SELECT discipline, SUM(total_cost_rm) as total_cost_rm, SUM(element_count) as element_count
            FROM simple_qto
            WHERE LOWER(discipline) LIKE LOWER('%{discipline}%')
            GROUP BY discipline
        """,
        description="Calculate cost by discipline"
    ),
    QueryPattern(
        pattern=r"(?:cost|price) (?:of |for )?(?P<element_type>\w+)",
        sql_template="""
            SELECT ifc_class, SUM(total_cost_rm) as total_cost_rm, SUM(element_count) as element_count
            FROM simple_qto
            WHERE LOWER(ifc_class) LIKE LOWER('%{element_type}%')
            GROUP BY ifc_class
        """,
        description="Calculate cost for specific element type"
    ),
]

# Material Quantity Patterns
MATERIAL_PATTERNS = [
    # Storey-specific area queries come FIRST
    QueryPattern(
        pattern=r"area on (?P<storey_num>first|second|third|1st|2nd|3rd|\d+(?:st|nd|rd|th)?) (?:level|storey|floor)",
        sql_template="""
            SELECT 'STOREY_NOT_AVAILABLE' as result_type
        """,
        description="Storey information not available in database"
    ),
    QueryPattern(
        pattern=r"(?:how much|how many|total|quantity of) (?P<material>concrete|steel|glass|aluminum)",
        sql_template="""
            SELECT ifc_class, measurement_type, SUM(total_quantity) as total, uom
            FROM simple_qto
            WHERE LOWER(ifc_class) IN ('ifcslab', 'ifccolumn', 'ifcbeam', 'ifcwall', 'ifcfootingbeam')
            GROUP BY ifc_class, measurement_type, uom
        """,
        description="Estimate structural material quantities"
    ),
    QueryPattern(
        pattern=r"(?:floor|slab) (?:area|size)",
        sql_template="""
            SELECT SUM(total_quantity) as total_area, uom
            FROM simple_qto
            WHERE LOWER(ifc_class) = 'ifcslab' AND measurement_type = 'AREA'
        """,
        description="Calculate total floor area"
    ),
]

# Free-Text Search Patterns
FREETEXT_PATTERNS = [
    QueryPattern(
        pattern=r"search for (?P<search_term>[\w\s]+)",
        sql_template="""
            SELECT guid, ifc_class, element_name, storey
            FROM elements_fts
            WHERE elements_fts MATCH '{search_term}'
            LIMIT 100
        """,
        description="Full-text search across elements"
    ),
    QueryPattern(
        pattern=r"find (?P<search_term>[\w\s]+)",
        sql_template="""
            SELECT DISTINCT guid, ifc_class, element_name, storey
            FROM elements_fts
            WHERE elements_fts MATCH '{search_term}'
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
            SELECT discipline, SUM(element_count) as element_count
            FROM simple_qto
            GROUP BY discipline
            ORDER BY discipline
        """,
        description="List all disciplines"
    ),
]


# All pattern categories
ALL_PATTERNS = {
    'cost': COST_PATTERNS,
    'material': MATERIAL_PATTERNS,
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
