#!/usr/bin/env python3
"""
Visualization & Shape Generation Tests
Ensure GPU overlays, gizmos, and procedural shapes can be imported
"""

import sqlite3
import sys
from pathlib import Path


def test_gpu_visualization_import(db_path):
    """Verify GPU visualization module can be imported"""
    try:
        sys.path.insert(0, str(Path.home() / "Projects/IfcOpenShell/src"))
        from bonsai.bim.module.federation_analysis.clash import visualization
        return True, "GPU visualization module imports successfully"
    except ImportError as e:
        return False, f"Cannot import GPU visualization: {e}"


def test_gizmo_module_import(db_path):
    """Verify gizmo module can be imported"""
    try:
        sys.path.insert(0, str(Path.home() / "Projects/IfcOpenShell/src"))
        from bonsai.bim.module.federation_analysis.clash import gizmo
        return True, "Gizmo module imports successfully"
    except ImportError as e:
        return False, f"Cannot import gizmo: {e}"


def test_shape_templates_import(db_path):
    """Verify procedural shape templates can be imported"""
    try:
        sys.path.insert(0, str(Path.home() / "Projects/IfcOpenShell/src"))
        from bonsai.bim.module.federation_analysis.visualization import shape_templates
        return True, "Shape templates module imports successfully"
    except ImportError as e:
        return False, f"Cannot import shape templates: {e}"


def test_semantic_shapes_import(db_path):
    """Verify semantic shape generation can be imported"""
    try:
        sys.path.insert(0, str(Path.home() / "Projects/IfcOpenShell/src"))
        from bonsai.bim.module.federation_analysis.visualization import semantic_shapes
        return True, "Semantic shapes module imports successfully"
    except ImportError as e:
        return False, f"Cannot import semantic shapes: {e}"


def test_federation_viz_helper_import(db_path):
    """Verify federation viz helper can be imported"""
    try:
        sys.path.insert(0, str(Path.home() / "Projects/IfcOpenShell/src"))
        from bonsai.bim.module.federation_analysis.visualization import federation_viz_helper
        return True, "Federation viz helper imports successfully"
    except ImportError as e:
        return False, f"Cannot import federation viz helper: {e}"


def test_bbox_data_for_visualization(db_path):
    """Test can query bbox data for visualization"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Query elements with complete bbox data
        cursor.execute("""
            SELECT m.guid, m.ifc_class, m.discipline,
                   r.minX, r.maxX, r.minY, r.maxY, r.minZ, r.maxZ
            FROM elements_meta m
            JOIN elements_rtree r ON m.id = r.id
            LIMIT 10
        """)

        elements = cursor.fetchall()
        conn.close()

        if not elements:
            return False, "No elements with bbox data found"

        # Check bbox validity (max > min)
        invalid_count = 0
        for elem in elements:
            guid, ifc_class, disc, minX, maxX, minY, maxY, minZ, maxZ = elem
            if not (maxX > minX and maxY > minY and maxZ > minZ):
                invalid_count += 1

        if invalid_count > 0:
            return False, f"{invalid_count}/{len(elements)} elements have invalid bboxes (max <= min)"

        return True, f"Bbox data valid: {len(elements)} elements queryable for visualization"

    except Exception as e:
        return False, f"Test failed: {e}"


def get_tests():
    """Return list of (test_name, test_function) tuples"""
    return [
        ("GPU Visualization Import", test_gpu_visualization_import),
        ("Gizmo Module Import", test_gizmo_module_import),
        ("Shape Templates Import", test_shape_templates_import),
        ("Semantic Shapes Import", test_semantic_shapes_import),
        ("Federation Viz Helper Import", test_federation_viz_helper_import),
        ("Bbox Data for Visualization", test_bbox_data_for_visualization),
    ]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_3_visualization_shapes.py <database_path>")
        sys.exit(1)

    db_path = sys.argv[1]
    print(f"\nTesting: {db_path}\n")

    for test_name, test_func in get_tests():
        success, message = test_func(db_path)
        status = "✅" if success else "❌"
        print(f"{status} {test_name}: {message}")
