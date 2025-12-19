#!/usr/bin/env python3
"""
Raster Scan Pipeline - Extract elevation points from survey images
Uses physical strips with AI reading for guaranteed accuracy.

Usage:
    python raster_scan_pipeline.py survey_highres.png --step 10 --strip-size 40
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime
from PIL import Image
import base64
import io

# Configuration
STRIP_SIZE = 40  # Height/width of strips in pixels
STEP_SIZE = 10   # Step between strips (smaller = more overlap, better coverage)

# Elevation validation
MIN_ELEVATION = 40.0  # Minimum valid elevation (meters)
MAX_ELEVATION = 50.0  # Maximum valid elevation (meters)
UNCERTAIN_PLACEHOLDER = 41.000  # Z value for completely uncertain readings


class ElevationValidator:
    """Validates and handles uncertain elevation values."""

    def __init__(self, log_path: str = None):
        self.uncertain_values = []  # List of uncertain readings for review
        self.rejected_values = []   # Values outside valid range
        self.valid_count = 0
        self.log_path = log_path

    def validate(self, value_str: str, x: int = None, y: int = None, source: str = None) -> tuple:
        """
        Validate an elevation value string.

        Returns:
            tuple: (is_valid, z_value, is_uncertain, original_str)
            - is_valid: True if value can be used (even if uncertain)
            - z_value: Float value or UNCERTAIN_PLACEHOLDER
            - is_uncertain: True if contains 'X' placeholders
            - original_str: Original string for logging
        """
        if not value_str:
            return (False, None, False, value_str)

        value_str = str(value_str).strip().upper()

        # Check for X placeholders (uncertain digits)
        has_uncertain = 'X' in value_str

        if has_uncertain:
            # Completely uncertain (XX.XXX)
            if value_str == "XX.XXX" or value_str.count('X') >= 4:
                self.uncertain_values.append({
                    "original": value_str,
                    "z": UNCERTAIN_PLACEHOLDER,
                    "x": x,
                    "y": y,
                    "source": source,
                    "reason": "Completely unreadable"
                })
                return (True, UNCERTAIN_PLACEHOLDER, True, value_str)

            # Partially uncertain - replace X with 0 for estimation
            estimated_str = value_str.replace('X', '0')
            try:
                estimated_z = float(estimated_str)
                if MIN_ELEVATION <= estimated_z <= MAX_ELEVATION:
                    self.uncertain_values.append({
                        "original": value_str,
                        "z": estimated_z,
                        "x": x,
                        "y": y,
                        "source": source,
                        "reason": f"Uncertain digit(s): {value_str}"
                    })
                    return (True, estimated_z, True, value_str)
                else:
                    self.rejected_values.append({
                        "original": value_str,
                        "estimated": estimated_z,
                        "reason": "Outside valid range (40-50m)"
                    })
                    return (False, None, True, value_str)
            except ValueError:
                return (False, None, True, value_str)

        # Standard numeric value
        try:
            z = float(value_str)

            # Check format: should be XX.XXX (2 digits, decimal, 3 digits)
            if not re.match(r'^\d{2}\.\d{3}$', value_str):
                # Non-standard format but valid number
                if MIN_ELEVATION <= z <= MAX_ELEVATION:
                    self.valid_count += 1
                    return (True, z, False, value_str)

            # Check range
            if MIN_ELEVATION <= z <= MAX_ELEVATION:
                self.valid_count += 1
                return (True, z, False, value_str)
            else:
                self.rejected_values.append({
                    "original": value_str,
                    "z": z,
                    "reason": f"Outside valid range: {z:.3f} not in [{MIN_ELEVATION}-{MAX_ELEVATION}]"
                })
                return (False, None, False, value_str)

        except ValueError:
            return (False, None, False, value_str)

    def write_debug_log(self, output_path: str = None):
        """Write debug log with uncertain and rejected values."""
        path = output_path or self.log_path or "elevation_debug.log"

        with open(path, 'w') as f:
            f.write("=" * 60 + "\n")
            f.write("ELEVATION EXTRACTION DEBUG LOG\n")
            f.write(f"Generated: {datetime.now().isoformat()}\n")
            f.write("=" * 60 + "\n\n")

            f.write(f"SUMMARY:\n")
            f.write(f"  Valid values: {self.valid_count}\n")
            f.write(f"  Uncertain values (need review): {len(self.uncertain_values)}\n")
            f.write(f"  Rejected values: {len(self.rejected_values)}\n")
            f.write("\n")

            if self.uncertain_values:
                f.write("-" * 60 + "\n")
                f.write(f"UNCERTAIN VALUES - NEED MANUAL REVIEW ({len(self.uncertain_values)})\n")
                f.write("-" * 60 + "\n")
                for i, item in enumerate(self.uncertain_values, 1):
                    f.write(f"\n{i}. Original: {item['original']}\n")
                    f.write(f"   Estimated Z: {item['z']:.3f}m\n")
                    if item.get('x') is not None:
                        f.write(f"   Position: ({item['x']}, {item['y']})\n")
                    f.write(f"   Reason: {item['reason']}\n")
                    if item.get('source'):
                        f.write(f"   Source: {item['source']}\n")

            if self.rejected_values:
                f.write("\n" + "-" * 60 + "\n")
                f.write(f"REJECTED VALUES ({len(self.rejected_values)})\n")
                f.write("-" * 60 + "\n")
                for i, item in enumerate(self.rejected_values, 1):
                    f.write(f"\n{i}. Value: {item['original']}\n")
                    f.write(f"   Reason: {item['reason']}\n")

            f.write("\n" + "=" * 60 + "\n")
            f.write("END OF LOG\n")

        return path

    def get_summary(self) -> dict:
        """Return summary statistics."""
        return {
            "valid_count": self.valid_count,
            "uncertain_count": len(self.uncertain_values),
            "rejected_count": len(self.rejected_values),
            "uncertain_values": self.uncertain_values,
            "rejected_values": self.rejected_values
        }


def generate_strips(image_path: str, output_dir: str, step: int = STEP_SIZE, strip_size: int = STRIP_SIZE):
    """Generate horizontal and vertical strips from image."""

    print(f"Loading image: {image_path}")
    img = Image.open(image_path)
    width, height = img.size
    print(f"Image size: {width} x {height} pixels")

    # Create output directories
    h_dir = Path(output_dir) / "h_strips"
    v_dir = Path(output_dir) / "v_strips"
    h_dir.mkdir(parents=True, exist_ok=True)
    v_dir.mkdir(parents=True, exist_ok=True)

    # Generate horizontal strips (full width, strip_size height)
    h_count = 0
    print(f"\nGenerating horizontal strips (step={step})...")
    for y in range(0, height - strip_size + 1, step):
        strip = img.crop((0, y, width, y + strip_size))
        strip_path = h_dir / f"h_{y:05d}.png"
        strip.save(strip_path, optimize=True)
        h_count += 1
        if h_count % 100 == 0:
            print(f"  H-strips: {h_count}...")

    print(f"Generated {h_count} horizontal strips")

    # Generate vertical strips (strip_size width, full height)
    v_count = 0
    print(f"\nGenerating vertical strips (step={step})...")
    for x in range(0, width - strip_size + 1, step):
        strip = img.crop((x, 0, x + strip_size, height))
        strip_path = v_dir / f"v_{x:05d}.png"
        strip.save(strip_path, optimize=True)
        v_count += 1
        if v_count % 100 == 0:
            print(f"  V-strips: {v_count}...")

    print(f"Generated {v_count} vertical strips")

    # Save metadata
    metadata = {
        "source_image": str(image_path),
        "image_width": width,
        "image_height": height,
        "strip_size": strip_size,
        "step_size": step,
        "h_strip_count": h_count,
        "v_strip_count": v_count,
        "total_strips": h_count + v_count
    }

    with open(Path(output_dir) / "scan_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\nTotal strips: {h_count + v_count}")
    return metadata


def image_to_base64(image_path: str) -> str:
    """Convert image to base64 for API calls."""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def parse_ai_response(response_text: str) -> list:
    """Parse AI response to extract elevation values."""
    # Try to find JSON array in response
    try:
        # Look for JSON array pattern
        import re
        match = re.search(r'\[.*?\]', response_text, re.DOTALL)
        if match:
            arr = json.loads(match.group())
            # Filter to valid elevation format XX.XXX
            valid = []
            for item in arr:
                try:
                    val = float(item)
                    if 40.0 <= val <= 50.0:  # Valid elevation range
                        valid.append(f"{val:.3f}")
                except:
                    pass
            return valid
    except:
        pass
    return []


def calculate_positions(h_sightings: dict, v_sightings: dict,
                        img_height: int, strip_size: int = STRIP_SIZE) -> list:
    """Calculate final positions from H and V sightings."""

    results = []

    # Find Z values confirmed in BOTH scans
    h_keys = set(h_sightings.keys())
    v_keys = set(v_sightings.keys())
    confirmed_z = h_keys & v_keys

    print(f"\nZ values in H-scan only: {len(h_keys - v_keys)}")
    print(f"Z values in V-scan only: {len(v_keys - h_keys)}")
    print(f"Z values confirmed in both: {len(confirmed_z)}")

    for z in sorted(confirmed_z, key=float):
        y_positions = h_sightings[z]
        x_positions = v_sightings[z]

        # Center of visibility range + half strip size
        y_center = (min(y_positions) + max(y_positions) + strip_size) / 2
        x_center = (min(x_positions) + max(x_positions) + strip_size) / 2

        results.append({
            "id": f"PT_{len(results)+1:03d}",
            "x": round(x_center),
            "y": round(y_center),
            "z": float(z),
            "h_range": [min(y_positions), max(y_positions)],
            "v_range": [min(x_positions), max(x_positions)]
        })

    return results


def save_sightings(h_sightings: dict, v_sightings: dict, output_dir: str):
    """Save intermediate sightings to JSON."""
    with open(Path(output_dir) / "h_sightings.json", "w") as f:
        json.dump(h_sightings, f, indent=2)
    with open(Path(output_dir) / "v_sightings.json", "w") as f:
        json.dump(v_sightings, f, indent=2)


def convert_to_survey_format(results: list, img_width: int, img_height: int,
                              scale: float = 0.01) -> dict:
    """Convert results to survey_to_blend.py format."""
    return {
        "metadata": {
            "source": "Raster scan extraction",
            "image_dimensions": {
                "width": img_width,
                "height": img_height
            },
            "scale": scale,
            "point_count": len(results)
        },
        "ground_elevations": results
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate strips for raster scan")
    parser.add_argument("image", help="Path to survey image")
    parser.add_argument("--step", type=int, default=10, help="Step size (default: 10)")
    parser.add_argument("--strip-size", type=int, default=40, help="Strip size (default: 40)")
    parser.add_argument("--output", default="raster_output", help="Output directory")

    args = parser.parse_args()

    generate_strips(args.image, args.output, args.step, args.strip_size)
