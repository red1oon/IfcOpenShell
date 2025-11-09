"""
NLP Query Module for Federation Data Intelligence

This module provides natural language query capabilities for the extracted database
using FTS5 full-text search.

Components:
- query_parser.py: Parses natural language queries into SQL
- query_executor.py: Executes queries and formats results
- query_patterns.py: Common query patterns and templates
"""

from .query_parser import NLPQueryParser
from .query_executor import QueryExecutor

__all__ = ['NLPQueryParser', 'QueryExecutor']
