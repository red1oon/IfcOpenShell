#!/bin/bash
# Quick revert script to restore original files if the GI fix fails

echo "="*60
echo "REVERTING GI FIX"
echo "="*60
echo ""

# Check if backups exist
if [ ! -f "src/bonsai/bonsai/bim/module/federation/visualization/federation_viz_helper.py.backup" ]; then
    echo "❌ ERROR: Backup file not found!"
    echo "   src/bonsai/bonsai/bim/module/federation/visualization/federation_viz_helper.py.backup"
    exit 1
fi

if [ ! -f "src/bonsai/bonsai/bim/module/federation/federation_viz_helper.py.backup" ]; then
    echo "❌ ERROR: Backup file not found!"
    echo "   src/bonsai/bonsai/bim/module/federation/federation_viz_helper.py.backup"
    exit 1
fi

# Revert the visualization file
echo "Reverting visualization/federation_viz_helper.py..."
cp src/bonsai/bonsai/bim/module/federation/visualization/federation_viz_helper.py.backup \
   src/bonsai/bonsai/bim/module/federation/visualization/federation_viz_helper.py

if [ $? -eq 0 ]; then
    echo "  ✅ Reverted successfully"
else
    echo "  ❌ Failed to revert"
    exit 1
fi

# Revert the main federation file
echo "Reverting federation_viz_helper.py..."
cp src/bonsai/bonsai/bim/module/federation/federation_viz_helper.py.backup \
   src/bonsai/bonsai/bim/module/federation/federation_viz_helper.py

if [ $? -eq 0 ]; then
    echo "  ✅ Reverted successfully"
else
    echo "  ❌ Failed to revert"
    exit 1
fi

# Remove db_utils.py (new file we added)
if [ -f "src/bonsai/bonsai/bim/module/federation/db_utils.py" ]; then
    echo "Removing db_utils.py..."
    rm src/bonsai/bonsai/bim/module/federation/db_utils.py
    echo "  ✅ Removed"
fi

echo ""
echo "✅ REVERT COMPLETE"
echo "All files restored to original state before GI fix"
echo ""
echo "You can now reload Blender and test with the original code."