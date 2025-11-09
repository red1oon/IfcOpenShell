"""
NLP Query Parser

Converts natural language queries into SQL statements using pattern matching
and the FTS5 full-text search capabilities of the extracted database.
"""

import re
from typing import Dict, List, Optional, Tuple
from .query_patterns import find_matching_pattern, QueryPattern, normalize_storey_name


class NLPQueryParser:
    """Parse natural language queries into SQL."""

    def __init__(self):
        self.query_history = []

    def parse(self, natural_query: str) -> Dict:
        """
        Parse a natural language query into SQL.

        Args:
            natural_query: The user's natural language query

        Returns:
            Dictionary with:
            - sql: The generated SQL query
            - params: Extracted parameters
            - category: Query category (element_count, manufacturer, etc.)
            - description: Human-readable description of what the query does
            - success: True if parsed successfully, False otherwise
            - error: Error message if success is False
        """
        # Clean the query
        cleaned = self._clean_query(natural_query)

        # Find matching pattern
        pattern, params, category = find_matching_pattern(cleaned)

        if not pattern:
            return {
                'sql': None,
                'params': None,
                'category': None,
                'description': None,
                'success': False,
                'error': 'No matching pattern found for query'
            }

        # Generate SQL from template
        try:
            sql = self._generate_sql(pattern, params)

            result = {
                'sql': sql,
                'params': params,
                'category': category,
                'description': pattern.description,
                'success': True,
                'error': None
            }

            # Add to history
            self.query_history.append({
                'natural_query': natural_query,
                'result': result
            })

            return result

        except Exception as e:
            return {
                'sql': None,
                'params': params,
                'category': category,
                'description': pattern.description,
                'success': False,
                'error': f'Error generating SQL: {str(e)}'
            }

    def _clean_query(self, query: str) -> str:
        """Clean and normalize the query."""
        # Remove extra whitespace
        cleaned = ' '.join(query.split())

        # Remove trailing question marks/punctuation
        cleaned = cleaned.rstrip('?!.,;')

        return cleaned.strip()

    def _generate_sql(self, pattern: QueryPattern, params: Dict[str, str]) -> str:
        """
        Generate SQL from template and parameters.

        Args:
            pattern: The matched query pattern
            params: Extracted parameters

        Returns:
            SQL query string
        """
        # Start with template
        sql = pattern.sql_template

        # Replace parameters
        for key, value in params.items():
            # Sanitize value to prevent SQL injection
            safe_value = self._sanitize_value(value)

            # Singularize element_type for IFC class matching (e.g., "plates" -> "plate")
            if key == 'element_type':
                safe_value = self._singularize(safe_value)

            # Normalize storey_name for multi-language support (e.g., "first" -> matches "Aras 01" or "FIRST FLOOR")
            if key == 'storey_name':
                normalized = normalize_storey_name(safe_value)
                if '|' in normalized:
                    # Multiple alternatives - convert to SQL OR pattern
                    alternatives = normalized.split('|')
                    like_clauses = [f"LOWER(s.storey) LIKE LOWER('%{alt}%')" for alt in alternatives]
                    # Replace the simple LIKE with OR pattern
                    sql = sql.replace(
                        f"LOWER(s.storey) LIKE LOWER('%{{{key}}}%')",
                        f"({' OR '.join(like_clauses)})"
                    )
                    continue  # Skip the normal replacement

            sql = sql.replace(f'{{{key}}}', safe_value)

        # Clean up whitespace
        sql = '\n'.join(line.strip() for line in sql.split('\n') if line.strip())

        return sql

    def _sanitize_value(self, value: str) -> str:
        """
        Sanitize a parameter value to prevent SQL injection.

        Args:
            value: The parameter value

        Returns:
            Sanitized value
        """
        # Remove potentially dangerous characters
        # Allow: alphanumeric, space, dash, underscore, period
        safe_value = re.sub(r'[^\w\s\-\.]', '', value)

        return safe_value.strip()

    def _singularize(self, word: str) -> str:
        """
        Convert plural words to singular for IFC class matching.

        Args:
            word: The word to singularize

        Returns:
            Singular form of the word
        """
        word_lower = word.lower()

        # Common IFC element plurals
        plural_to_singular = {
            'beams': 'beam',
            'columns': 'column',
            'doors': 'door',
            'windows': 'window',
            'walls': 'wall',
            'slabs': 'slab',
            'plates': 'plate',
            'ducts': 'duct',
            'pipes': 'pipe',
            'valves': 'valve',
            'lights': 'light',
            'fixtures': 'fixture',
        }

        if word_lower in plural_to_singular:
            return plural_to_singular[word_lower]

        # Generic rule: remove trailing 's' if word ends in 's'
        if word_lower.endswith('s') and len(word_lower) > 3:
            return word_lower[:-1]

        return word_lower

    def get_history(self, limit: int = 10) -> List[Dict]:
        """
        Get recent query history.

        Args:
            limit: Maximum number of queries to return

        Returns:
            List of recent queries with their results
        """
        return self.query_history[-limit:]

    def clear_history(self):
        """Clear query history."""
        self.query_history = []

    def suggest_queries(self) -> List[str]:
        """
        Get suggested example queries.

        Returns:
            List of example query strings
        """
        return [
            "How many beams are there?",
            "Count doors on level 1",
            "Find ducts from Carrier",
            "Show ACMV elements",
            "Total length of pipes",
            "What beams are on floor 2?",
            "Search for fire doors",
            "Which disciplines exist?",
            "Find elements with FireRating = 2HR",
            "Total area of walls in ARC",
        ]
