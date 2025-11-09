"""
Intent Classification for NLP Queries

Maps user queries to intents using keyword matching before SQL generation.
This allows more flexible phrasing while remaining fast and deterministic.

Intent Categories:
- COUNT: Count elements
- FIND: Search for elements
- TOTAL: Sum quantities
- LIST: List elements
- SEARCH: Free-text search
- DISCIPLINE: Discipline-related queries
"""

from typing import Dict, Optional, Tuple, List
import re


class Intent:
    """Represents a query intent with keywords."""

    def __init__(self, name: str, keywords: List[str], description: str):
        self.name = name
        self.keywords = keywords  # Primary keywords that identify this intent
        self.description = description

    def matches(self, query: str) -> bool:
        """Check if query matches this intent based on keywords."""
        query_lower = query.lower()
        return any(keyword in query_lower for keyword in self.keywords)

    def get_confidence(self, query: str) -> float:
        """Calculate confidence score (0.0 to 1.0) based on keyword matches."""
        query_lower = query.lower()
        matches = sum(1 for keyword in self.keywords if keyword in query_lower)
        return min(matches / len(self.keywords), 1.0)


# Define all intents with their keyword triggers
INTENTS = {
    'COUNT': Intent(
        name='COUNT',
        keywords=[
            'how many', 'count', 'number of', 'total number', 'how much',
            'quantity', 'how much', 'count all', 'tally', 'number',
            'give me count', 'what is the count', 'count of'
        ],
        description='Count elements by type or location'
    ),

    'FIND': Intent(
        name='FIND',
        keywords=[
            'find', 'show me', 'get', 'locate', 'where', 'where are',
            'get me', 'fetch', 'retrieve', 'show', 'display'
        ],
        description='Find specific elements by properties'
    ),

    'TOTAL': Intent(
        name='TOTAL',
        keywords=[
            'total', 'sum', 'add up', 'calculate', 'aggregate',
            'sum up', 'what is the total', 'give me total', 'overall',
            'combined', 'all together'
        ],
        description='Sum quantities (length, area, volume)'
    ),

    'LIST': Intent(
        name='LIST',
        keywords=[
            'list', 'show all', 'display', 'give me all', 'list all',
            'show everything', 'enumerate', 'all', 'every'
        ],
        description='List elements in a category'
    ),

    'SEARCH': Intent(
        name='SEARCH',
        keywords=[
            'search', 'look for', 'search for', 'looking for',
            'find anything', 'query'
        ],
        description='Free-text search across all fields'
    ),

    'DISCIPLINE': Intent(
        name='DISCIPLINE',
        keywords=[
            'discipline', 'what disciplines', 'which disciplines', 'what trades',
            'trades', 'what systems', 'which systems', 'categories'
        ],
        description='Query about disciplines/trades'
    ),

    'MANUFACTURER': Intent(
        name='MANUFACTURER',
        keywords=[
            'from', 'made by', 'manufactured by', 'supplier', 'brand',
            'by', 'vendor', 'maker', 'producer'
        ],
        description='Filter by manufacturer/supplier'
    ),

    'PROPERTY': Intent(
        name='PROPERTY',
        keywords=[
            'with', 'having', 'where', 'property', 'that have',
            'which have', 'containing'
        ],
        description='Filter by property values'
    ),

    'STOREY': Intent(
        name='STOREY',
        keywords=[
            'on level', 'on floor', 'on storey', 'level', 'floor',
            'at level', 'at floor', 'storey'
        ],
        description='Filter by building level/storey'
    ),
}


# Element type synonyms (for more flexible matching)
ELEMENT_SYNONYMS = {
    # Structural
    'beam': ['beam', 'beams', 'girder', 'girders'],
    'column': ['column', 'columns', 'pillar', 'pillars', 'post', 'posts'],
    'wall': ['wall', 'walls', 'partition', 'partitions'],
    'slab': ['slab', 'slabs', 'floor', 'floors', 'deck', 'decks'],
    'foundation': ['foundation', 'foundations', 'footing', 'footings'],

    # Architecture
    'door': ['door', 'doors', 'doorway', 'doorways'],
    'window': ['window', 'windows'],
    'roof': ['roof', 'roofs', 'roofing'],
    'stair': ['stair', 'stairs', 'staircase', 'staircases', 'steps'],
    'railing': ['railing', 'railings', 'handrail', 'handrails', 'balustrade'],

    # MEP - HVAC
    'duct': ['duct', 'ducts', 'ductwork', 'air duct', 'air ducts'],
    'damper': ['damper', 'dampers', 'control damper'],
    'terminal': ['terminal', 'terminals', 'air terminal', 'diffuser', 'diffusers', 'grille', 'grilles'],
    'fan': ['fan', 'fans', 'air handler', 'air handlers'],

    # MEP - Plumbing
    'pipe': ['pipe', 'pipes', 'piping'],
    'valve': ['valve', 'valves'],
    'fitting': ['fitting', 'fittings', 'pipe fitting'],
    'pump': ['pump', 'pumps'],

    # MEP - Electrical
    'conduit': ['conduit', 'conduits', 'cable tray', 'cable trays'],
    'panel': ['panel', 'panels', 'switchboard', 'switchboards', 'distribution board'],
    'light': ['light', 'lights', 'lighting', 'fixture', 'fixtures', 'luminaire'],
    'outlet': ['outlet', 'outlets', 'socket', 'sockets', 'receptacle'],

    # Equipment
    'equipment': ['equipment', 'unit', 'units', 'device', 'devices'],
}


# Quantity type synonyms
QUANTITY_SYNONYMS = {
    'length': ['length', 'linear', 'distance', 'run'],
    'area': ['area', 'surface', 'coverage'],
    'volume': ['volume', 'cubic', 'capacity'],
    'perimeter': ['perimeter', 'circumference'],
    'width': ['width', 'breadth'],
    'height': ['height', 'elevation'],
}


# Discipline synonyms
DISCIPLINE_SYNONYMS = {
    'ACMV': ['acmv', 'hvac', 'mechanical', 'air conditioning', 'ventilation'],
    'ELEC': ['electrical', 'elec', 'electric', 'power'],
    'FP': ['fire protection', 'fp', 'fire', 'sprinkler'],
    'SP': ['sanitary', 'plumbing', 'sp', 'sanitary plumbing'],
    'ARC': ['architecture', 'arc', 'architectural'],
    'STR': ['structural', 'str', 'structure'],
    'CW': ['civil', 'cw', 'civil works'],
    'LPG': ['lpg', 'gas', 'liquefied petroleum gas'],
}


class IntentClassifier:
    """Classifies user queries into intents."""

    def __init__(self):
        self.intents = INTENTS
        self.element_synonyms = ELEMENT_SYNONYMS
        self.quantity_synonyms = QUANTITY_SYNONYMS
        self.discipline_synonyms = DISCIPLINE_SYNONYMS

    def classify(self, query: str) -> Dict:
        """
        Classify query and extract parameters.

        Returns:
            {
                'intent': str,           # Primary intent (COUNT, FIND, etc.)
                'sub_intents': List[str], # Additional intents (STOREY, MANUFACTURER)
                'confidence': float,      # 0.0 to 1.0
                'element_type': str,      # Normalized element type
                'quantity_type': str,     # Normalized quantity (length/area/volume)
                'discipline': str,        # Normalized discipline
                'storey': str,           # Storey number/name
                'manufacturer': str,      # Manufacturer name
                'property_name': str,    # Property name
                'property_value': str,   # Property value
                'search_term': str,      # Free-text search term
                'ambiguous': List[str],  # List of missing/unclear parameters
                'suggestions': List[str], # Suggested clarifications
            }
        """
        query_lower = query.lower().strip()

        # Find primary intent
        primary_intent, confidence = self._find_primary_intent(query_lower)

        # Find sub-intents (modifiers like STOREY, MANUFACTURER)
        sub_intents = self._find_sub_intents(query_lower)

        # Extract parameters
        params = {
            'intent': primary_intent,
            'sub_intents': sub_intents,
            'confidence': confidence,
            'element_type': self._extract_element_type(query_lower),
            'quantity_type': self._extract_quantity_type(query_lower),
            'discipline': self._extract_discipline(query_lower),
            'storey': self._extract_storey(query_lower),
            'manufacturer': self._extract_manufacturer(query_lower),
            'property_name': None,  # TODO: Extract from query
            'property_value': None,  # TODO: Extract from query
            'search_term': self._extract_search_term(query_lower, primary_intent),
            'ambiguous': [],
            'suggestions': [],
        }

        # Check for ambiguities and add suggestions
        self._check_ambiguities(params)

        return params

    def _find_primary_intent(self, query: str) -> Tuple[str, float]:
        """Find the most likely primary intent."""
        # Priority order for better matching
        priority_intents = ['COUNT', 'TOTAL', 'FIND', 'LIST', 'SEARCH', 'DISCIPLINE', 'MANUFACTURER']

        best_match = None
        best_confidence = 0.0

        # Check priority intents first
        for intent_name in priority_intents:
            intent = self.intents.get(intent_name)
            if intent and intent.matches(query):
                confidence = intent.get_confidence(query)
                # Give higher weight to earlier matches in priority list
                weighted_confidence = confidence * (1.0 + (len(priority_intents) - priority_intents.index(intent_name)) * 0.1)
                if weighted_confidence > best_confidence:
                    best_confidence = weighted_confidence
                    best_match = intent_name

        # Check remaining intents
        for intent_name, intent in self.intents.items():
            if intent_name not in priority_intents and intent.matches(query):
                confidence = intent.get_confidence(query)
                if confidence > best_confidence:
                    best_confidence = confidence
                    best_match = intent_name

        # Default to SEARCH if no strong match
        if best_match is None:
            return 'SEARCH', 0.5

        return best_match, min(best_confidence, 1.0)

    def _find_sub_intents(self, query: str) -> List[str]:
        """Find additional intent modifiers."""
        sub_intents = []

        # Check for location filter
        if self.intents['STOREY'].matches(query):
            sub_intents.append('STOREY')

        # Check for manufacturer filter
        if self.intents['MANUFACTURER'].matches(query):
            sub_intents.append('MANUFACTURER')

        # Check for property filter
        if self.intents['PROPERTY'].matches(query):
            sub_intents.append('PROPERTY')

        return sub_intents

    def _extract_element_type(self, query: str) -> Optional[str]:
        """Extract and normalize element type from query."""
        for canonical, synonyms in self.element_synonyms.items():
            for synonym in synonyms:
                if synonym in query:
                    return canonical
        return None

    def _extract_quantity_type(self, query: str) -> Optional[str]:
        """Extract and normalize quantity type from query."""
        for canonical, synonyms in self.quantity_synonyms.items():
            for synonym in synonyms:
                if synonym in query:
                    return canonical
        return None

    def _extract_discipline(self, query: str) -> Optional[str]:
        """Extract and normalize discipline from query."""
        for canonical, synonyms in self.discipline_synonyms.items():
            for synonym in synonyms:
                if synonym in query:
                    return canonical
        return None

    def _extract_storey(self, query: str) -> Optional[str]:
        """Extract storey/floor number from query."""
        # Match patterns like "level 1", "floor 2", "storey 3"
        patterns = [
            r'(?:level|floor|storey)\s+(\d+)',
            r'(?:level|floor|storey)\s+([a-z]\d*)',  # e.g., "level A"
        ]

        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _extract_manufacturer(self, query: str) -> Optional[str]:
        """Extract manufacturer name from query."""
        # Look for patterns like "from Carrier", "made by Aereco"
        patterns = [
            r'(?:from|by|made by|manufactured by)\s+(\w+)',
        ]

        for pattern in patterns:
            match = re.search(pattern, query, re.IGNORECASE)
            if match:
                return match.group(1)

        return None

    def _extract_search_term(self, query: str, intent: str) -> Optional[str]:
        """Extract search term for free-text search."""
        if intent == 'SEARCH':
            # Remove common prefix words
            cleaned = re.sub(r'^(search for|find|look for|search)\s+', '', query)
            return cleaned.strip()
        return None

    def _check_ambiguities(self, params: Dict) -> None:
        """
        Check for missing/unclear parameters and add suggestions.
        Modifies params dict in-place to add 'ambiguous' and 'suggestions' lists.
        """
        intent = params['intent']
        ambiguous = []
        suggestions = []

        # COUNT intent needs element type
        if intent == 'COUNT':
            if not params['element_type']:
                ambiguous.append('element_type')
                suggestions.append("❓ What type of element? Try: 'How many beams?' or 'Count doors'")

        # TOTAL intent needs element type AND quantity type
        elif intent == 'TOTAL':
            if not params['element_type']:
                ambiguous.append('element_type')
                suggestions.append("❓ What element? Try: 'Total length of pipes'")
            if not params['quantity_type']:
                ambiguous.append('quantity_type')
                suggestions.append("❓ What quantity? Try: 'Total [length/area/volume] of [element]'")

        # FIND intent with MANUFACTURER sub-intent needs manufacturer name
        elif intent == 'FIND' and 'MANUFACTURER' in params['sub_intents']:
            if not params['manufacturer']:
                ambiguous.append('manufacturer')
                suggestions.append("❓ Which manufacturer? Try: 'Find ducts from Carrier'")
            if not params['element_type']:
                ambiguous.append('element_type')
                suggestions.append("❓ What element? Try: 'Find [element] from [manufacturer]'")

        # LIST intent with discipline
        elif intent == 'LIST' or intent == 'FIND':
            if params['discipline'] and not params['element_type']:
                # This is okay - listing all elements in a discipline
                pass
            elif not params['discipline'] and not params['element_type']:
                ambiguous.append('element_type or discipline')
                suggestions.append("❓ What to list? Try: 'Show ACMV elements' or 'List all beams'")

        # STOREY sub-intent detected but no storey number
        if 'STOREY' in params['sub_intents'] and not params['storey']:
            ambiguous.append('storey_number')
            suggestions.append("❓ Which level? Try: 'Count doors on level 1'")

        # Low confidence warning
        if params['confidence'] < 0.5:
            ambiguous.append('unclear_intent')
            suggestions.append("⚠️ Query unclear. Try: 'How many [element]?' or 'Total [length/area/volume] of [element]'")

        params['ambiguous'] = ambiguous
        params['suggestions'] = suggestions


def classify_query(query: str) -> Dict:
    """
    Convenience function to classify a query.

    Usage:
        result = classify_query("How many beams on level 2?")
        # Returns:
        {
            'intent': 'COUNT',
            'sub_intents': ['STOREY'],
            'confidence': 0.8,
            'element_type': 'beam',
            'storey': '2',
            ...
        }
    """
    classifier = IntentClassifier()
    return classifier.classify(query)


# Example usage and testing
if __name__ == "__main__":
    # Test queries
    test_queries = [
        "How many beams?",
        "Count doors on level 1",
        "Find ducts from Carrier",
        "Total length of pipes",
        "Show ACMV elements",
        "Which disciplines exist?",
        "Search for fire doors",
        "Give me beam count on floor 2",  # Variation
        "What's the total area of walls?",  # Variation
        "Show me all Aereco equipment",  # Variation
        # Ambiguous queries (for testing suggestions)
        "How many?",  # Missing element
        "Total length",  # Missing element
        "Find from Carrier",  # Missing element
        "Count on level 1",  # Missing element
    ]

    classifier = IntentClassifier()

    for query in test_queries:
        print(f"\nQuery: '{query}'")
        result = classifier.classify(query)
        print(f"  Intent: {result['intent']} (confidence: {result['confidence']:.2f})")
        print(f"  Sub-intents: {result['sub_intents']}")
        if result['element_type']:
            print(f"  Element: {result['element_type']}")
        if result['storey']:
            print(f"  Storey: {result['storey']}")
        if result['quantity_type']:
            print(f"  Quantity: {result['quantity_type']}")
        if result['discipline']:
            print(f"  Discipline: {result['discipline']}")
        if result['manufacturer']:
            print(f"  Manufacturer: {result['manufacturer']}")

        # Show ambiguities and suggestions
        if result['ambiguous']:
            print(f"  ⚠️ Ambiguous: {', '.join(result['ambiguous'])}")
            for suggestion in result['suggestions']:
                print(f"     {suggestion}")
