#!/bin/bash
#
# Helper script to run Blender headless tests
#
# Usage: ./run_blender_tests.sh

# Find Blender executable
BLENDER=$(which blender)

if [ -z "$BLENDER" ]; then
    echo "ERROR: Blender not found in PATH"
    echo "Please install Blender or add it to your PATH"
    exit 1
fi

echo "🧪 Running Blender Headless Tests"
echo "Using: $BLENDER"
echo ""

# Run tests in background mode
$BLENDER --background --python test_clash_gizmo_blender.py

exit $?
