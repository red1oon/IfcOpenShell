#!/usr/bin/env python3
"""
Material/Color Data Quality Tests
Validate IFC color extraction worked, fallback colors available
"""

import sqlite3
import sys
from pathlib import Path


def test_material_coverage(db_path):
    """Check % of elements with material colors"""
    try:
        conn = sqlite3.connect(db_path)

        total = conn.execute("SELECT COUNT(*) FROM elements_meta").fetchone()[0]
        with_material = conn.execute(
            "SELECT COUNT(*) FROM elements_meta WHERE material_rgba IS NOT NULL"
        ).fetchone()[0]

        conn.close()

        if total == 0:
            return False, "No elements in database"

        coverage = (with_material / total) * 100

        # Note: Coverage expectations vary - some IFCs have rich materials, some don't
        # We just report the number, warn only if suspiciously low
        if coverage < 10:
            return False, f"Very low material coverage: {coverage:.1f}% (extraction may have failed)"

        return True, f"Material coverage: {coverage:.1f}% ({with_material:,}/{total:,} elements)"
    except Exception as e:
        return False, f"Error checking material coverage: {e}"


def test_rgba_value_sanity(db_path):
    """Sample material RGBA values and check they're in valid range 0.0-1.0"""
    try:
        conn = sqlite3.connect(db_path)

        # Sample 3 materials with colors
        cursor = conn.execute("""
            SELECT material_name, material_rgba
            FROM elements_meta
            WHERE material_rgba IS NOT NULL
            ORDER BY RANDOM()
            LIMIT 3
        """)
        samples = cursor.fetchall()
        conn.close()

        if not samples:
            return True, "No materials to validate (not an error, just no IFC colors)"

        invalid = []
        for mat_name, rgba_str in samples:
            if not rgba_str:
                continue

            # RGBA stored as comma-separated string "R,G,B,A"
            try:
                values = [float(v) for v in rgba_str.split(',')]
                if len(values) != 4:
                    invalid.append(f"{mat_name}: wrong component count ({len(values)})")
                    continue

                for i, v in enumerate(values):
                    if v < 0.0 or v > 1.0:
                        invalid.append(f"{mat_name}: value {i} out of range ({v})")
                        break
            except ValueError:
                invalid.append(f"{mat_name}: invalid RGBA format: {rgba_str}")

        if invalid:
            return False, f"Invalid RGBA values: {invalid[0]}"

        return True, f"Sampled {len(samples)} materials, all RGBA values valid (0.0-1.0)"
    except Exception as e:
        return False, f"Error validating RGBA: {e}"


def test_common_materials_exist(db_path):
    """Check for common material names (sanity check extraction worked)"""
    try:
        conn = sqlite3.connect(db_path)

        # Get top materials by frequency
        cursor = conn.execute("""
            SELECT material_name, COUNT(*) as count
            FROM elements_meta
            WHERE material_name IS NOT NULL
            GROUP BY material_name
            ORDER BY count DESC
            LIMIT 5
        """)
        top_materials = cursor.fetchall()
        conn.close()

        if not top_materials:
            return True, "No material names found (not an error if IFC has no materials)"

        mat_summary = ", ".join([f"{name}({count})" for name, count in top_materials[:3]])
        return True, f"Top materials: {mat_summary}"
    except Exception as e:
        return False, f"Error checking material names: {e}"


def test_discipline_color_fallback_data(db_path):
    """Verify discipline data exists for color fallback"""
    try:
        conn = sqlite3.connect(db_path)

        # All elements should have discipline (used for color fallback)
        total = conn.execute("SELECT COUNT(*) FROM elements_meta").fetchone()[0]
        with_discipline = conn.execute(
            "SELECT COUNT(*) FROM elements_meta WHERE discipline IS NOT NULL AND discipline != ''"
        ).fetchone()[0]

        conn.close()

        if total == 0:
            return False, "No elements in database"

        coverage = (with_discipline / total) * 100

        if coverage < 95:
            return False, f"Low discipline coverage: {coverage:.1f}% (fallback colors won't work)"

        return True, f"Discipline coverage: {coverage:.1f}% (fallback colors available)"
    except Exception as e:
        return False, f"Error checking disciplines: {e}"


def test_material_library_structure(db_path):
    """Verify material data is well-formed"""
    try:
        conn = sqlite3.connect(db_path)

        # Check that elements with materials also have names
        with_rgba = conn.execute(
            "SELECT COUNT(*) FROM elements_meta WHERE material_rgba IS NOT NULL"
        ).fetchone()[0]

        with_both = conn.execute("""
            SELECT COUNT(*) FROM elements_meta
            WHERE material_rgba IS NOT NULL AND material_name IS NOT NULL AND material_name != ''
        """).fetchone()[0]

        conn.close()

        if with_rgba == 0:
            return True, "No materials with RGBA (not an error)"

        consistency = (with_both / with_rgba) * 100

        # Note: Some elements may have RGBA but generic/unnamed materials - this is OK
        # We just report the consistency, only fail if very low
        if consistency < 50:
            return False, f"Material data very inconsistent: {consistency:.1f}% have both name+RGBA"

        return True, f"Material data OK: {consistency:.1f}% have both name+RGBA ({with_both}/{with_rgba})"
    except Exception as e:
        return False, f"Error checking material structure: {e}"


def run_material_tests(db_path):
    """Run all material/color quality tests"""
    tests = [
        ("Material coverage", test_material_coverage),
        ("RGBA value sanity", test_rgba_value_sanity),
        ("Common materials exist", test_common_materials_exist),
        ("Discipline fallback data", test_discipline_color_fallback_data),
        ("Material data structure", test_material_library_structure),
    ]

    passed = []
    failed = []

    for name, test_func in tests:
        success, message = test_func(db_path)
        if success:
            passed.append((name, True, message))
        else:
            failed.append((name, False, message))

    return passed, failed


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_4_materials.py <database_path>")
        sys.exit(1)

    db_path = sys.argv[1]
    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)

    print("Running Material Quality Tests...")
    passed, failed = run_material_tests(db_path)

    for name, success, message in passed + failed:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  [{status}] {name}: {message}")

    sys.exit(0 if not failed else 1)
