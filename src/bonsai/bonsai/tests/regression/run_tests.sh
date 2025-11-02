#!/bin/bash
# Master test runner - auto-detects latest DB and runs appropriate tests
# Trigger phrases:
#   "test the db" → Python mode (fast, ~45 seconds)
#   "test the db with blender" → Full validation (~60 seconds)

set -e  # Exit on error

DB_DIR="$HOME/Documents/bonsai/DatabaseFiles"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Find latest DB (sample or full)
echo "Searching for database in $DB_DIR..."
LATEST_DB=$(ls -t "$DB_DIR"/*.db 2>/dev/null | head -1)

if [ -z "$LATEST_DB" ]; then
    echo -e "${RED}❌ No database found in $DB_DIR${NC}"
    echo "Expected databases:"
    echo "  - sample_extracted_v3.db (21 MB)"
    echo "  - sample_fixed_*.db (timestamped samples)"
    exit 1
fi

DB_SIZE=$(du -h "$LATEST_DB" | cut -f1)
DB_NAME=$(basename "$LATEST_DB")
echo -e "${GREEN}✓ Found database: $DB_NAME ($DB_SIZE)${NC}"

# Run Python tests (always)
echo ""
echo -e "${YELLOW}=== Running Python Tests (no Blender required) ===${NC}"
cd "$SCRIPT_DIR"
python3 run_tests.py "$LATEST_DB"

PYTHON_EXIT=$?

# If Blender tests requested (future implementation)
if [ "$1" = "blender" ]; then
    echo ""
    echo -e "${YELLOW}=== Blender Tests Not Yet Implemented ===${NC}"
    echo "Future: Will run visualization tests in Blender background mode"
    # PYTHONPATH=$HOME/Projects/IfcOpenShell/src \
    # ~/blender-4.5.3/blender --background --python run_tests_blender.py -- "$LATEST_DB"
fi

exit $PYTHON_EXIT
