"""
Query Executor

Executes SQL queries against the extracted database and formats results.
"""

import sqlite3
import time
from typing import List, Dict, Tuple, Optional
from pathlib import Path


class QueryExecutor:
    """Execute SQL queries and format results."""

    def __init__(self, db_path: str):
        """
        Initialize the query executor.

        Args:
            db_path: Path to the SQLite database
        """
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {db_path}")

    def execute(self, sql: str, params: Optional[Tuple] = None) -> Dict:
        """
        Execute a SQL query and return formatted results.

        Args:
            sql: SQL query to execute
            params: Optional tuple of parameters for parameterized queries

        Returns:
            Dictionary with:
            - success: True if query executed successfully
            - rows: List of result rows (as dictionaries)
            - row_count: Number of rows returned
            - columns: List of column names
            - elapsed_ms: Query execution time in milliseconds
            - error: Error message if success is False
        """
        start_time = time.time()

        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # Return rows as dictionaries
            cursor = conn.cursor()

            # Execute query
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)

            # Fetch results
            rows = cursor.fetchall()

            # Convert Row objects to dictionaries
            result_rows = [dict(row) for row in rows]

            # Get column names
            columns = [desc[0] for desc in cursor.description] if cursor.description else []

            elapsed_ms = (time.time() - start_time) * 1000

            conn.close()

            return {
                'success': True,
                'rows': result_rows,
                'row_count': len(result_rows),
                'columns': columns,
                'elapsed_ms': elapsed_ms,
                'error': None
            }

        except sqlite3.Error as e:
            elapsed_ms = (time.time() - start_time) * 1000
            return {
                'success': False,
                'rows': [],
                'row_count': 0,
                'columns': [],
                'elapsed_ms': elapsed_ms,
                'error': str(e)
            }

    def execute_with_limit(self, sql: str, limit: int = 100, params: Optional[Tuple] = None) -> Dict:
        """
        Execute query with a LIMIT clause to prevent excessive results.

        Args:
            sql: SQL query to execute
            limit: Maximum number of rows to return
            params: Optional query parameters

        Returns:
            Query result dictionary (same as execute())
        """
        # Add LIMIT if not already present
        if 'LIMIT' not in sql.upper():
            sql = f"{sql.rstrip(';')} LIMIT {limit}"

        return self.execute(sql, params)

    def format_results_table(self, result: Dict, max_rows: int = 20) -> str:
        """
        Format query results as a text table.

        Args:
            result: Query result dictionary from execute()
            max_rows: Maximum number of rows to display

        Returns:
            Formatted table string
        """
        if not result['success']:
            return f"❌ Error: {result['error']}"

        if result['row_count'] == 0:
            return "No results found."

        rows = result['rows'][:max_rows]
        columns = result['columns']

        # Calculate column widths
        widths = {}
        for col in columns:
            widths[col] = len(col)

        for row in rows:
            for col in columns:
                value = str(row.get(col, ''))
                widths[col] = max(widths[col], len(value))

        # Build table
        lines = []

        # Header
        header = ' | '.join(col.ljust(widths[col]) for col in columns)
        lines.append(header)
        lines.append('-' * len(header))

        # Rows
        for row in rows:
            line = ' | '.join(str(row.get(col, '')).ljust(widths[col]) for col in columns)
            lines.append(line)

        # Footer
        if result['row_count'] > max_rows:
            lines.append(f"... ({result['row_count'] - max_rows} more rows)")

        lines.append(f"\n{result['row_count']} rows in {result['elapsed_ms']:.2f}ms")

        return '\n'.join(lines)

    def get_table_info(self, table_name: str) -> Dict:
        """
        Get information about a database table.

        Args:
            table_name: Name of the table

        Returns:
            Dictionary with table information
        """
        sql = f"PRAGMA table_info({table_name})"
        result = self.execute(sql)

        if result['success']:
            return {
                'table_name': table_name,
                'columns': result['rows'],
                'column_count': result['row_count']
            }
        else:
            return {
                'table_name': table_name,
                'error': result['error']
            }

    def list_tables(self) -> List[str]:
        """
        List all tables in the database.

        Returns:
            List of table names
        """
        sql = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        result = self.execute(sql)

        if result['success']:
            return [row['name'] for row in result['rows']]
        else:
            return []

    def get_row_count(self, table_name: str) -> int:
        """
        Get the number of rows in a table.

        Args:
            table_name: Name of the table

        Returns:
            Row count, or -1 if error
        """
        sql = f"SELECT COUNT(*) as count FROM {table_name}"
        result = self.execute(sql)

        if result['success'] and result['row_count'] > 0:
            return result['rows'][0]['count']
        else:
            return -1
