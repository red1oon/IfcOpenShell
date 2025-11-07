#!/bin/bash
#
# Federation Analysis Add-on Test Suite
# ======================================
#
# Quick test runner for federation_analysis module.
#
# Usage:
#   ./run_tests.sh [database_path]
#
# If no database path is provided, uses default sample database.

set -e  # Exit on error

# Default database path
DEFAULT_DB="$HOME/Documents/bonsai/DatabaseFiles/sample_extracted_v3.db"

# Use provided database or default
DB_PATH="${1:-$DEFAULT_DB}"

# Check database exists
if [ ! -f "$DB_PATH" ]; then
    echo "❌ Database not found: $DB_PATH"
    echo ""
    echo "Usage: ./run_tests.sh [database_path]"
    echo ""
    echo "Examples:"
    echo "  ./run_tests.sh"
    echo "  ./run_tests.sh ~/Documents/bonsai/DatabaseFiles/sample_extracted_v3.db"
    exit 1
fi

# Run Python test suite
echo "Running federation_analysis tests..."
echo ""
python3 run_tests.py "$DB_PATH"
