#!/usr/bin/env python3
"""
Survey Raster Scan - Z Extraction with X,Y Positioning
=======================================================
TV-style raster scan to extract elevation values from survey images.

Method:
1. Generate horizontal strips (scan rows) - determines Y position
2. Generate vertical strips (scan columns) - determines X position  
3. AI reads each strip: "List fully visible elevation numbers"
4. Intersection of strip ranges → precise (X, Y) for each Z

Usage:
    python survey_raster_scan.py <image_path> [--step 5] [--strip-size 40]

Output:
    - z_positions.json: Final coordinates
    - h_strips/: Horizontal strip images
    - v_strips/: Vertical strip images
    - h_sightings.json: Raw horizontal scan data
    - v_sightings.json: Raw vertical scan data
"""

import subprocess
import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

class RasterScanner:
    def __init__(self, image_path, output_dir=None, strip_size=40, step=5):
        self.image_path = Path(image_path)
        self.output_dir = Path(output_dir) if output_dir else self.image_path.parent / "raster_output"
        self.strip_size = strip_size  # Height/width of each strip
        self.step = step  # Step between strips (smaller = more precision)
        
        self.h_strips_dir = self.output_dir / "h_strips"
        self.v_strips_dir = self.output_dir / "v_strips"
        
        self.h_sightings = {}  # {z_value: [y_positions]}
        self.v_sightings = {}  # {z_value: [x_positions]}
        
        self.img_width = 0
        self.img_height = 0
    
    def get_image_size(self):
        """Get image dimensions using ImageMagick"""
        result = subprocess.run(
            ["identify", "-format", "%w %h", str(self.image_path)],
            capture_output=True, text=True
        )
        self.img_width, self.img_height = map(int, result.stdout.strip().split())
        return self.img_width, self.img_height
    
    def setup_directories(self):
        """Create output directories"""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.h_strips_dir.mkdir(exist_ok=True)
        self.v_strips_dir.mkdir(exist_ok=True)
    
    def generate_horizontal_strips(self):
        """Generate horizontal strips (full width, stepping down)"""
        strips = []
        y = 0
        while y + self.strip_size <= self.img_height:
            strip_path = self.h_strips_dir / f"h_{y:04d}.png"
            subprocess.run([
                "convert", str(self.image_path),
                "-crop", f"{self.img_width}x{self.strip_size}+0+{y}",
                "+repage", str(strip_path)
            ], capture_output=True)
            strips.append({"y": y, "path": str(strip_path)})
            y += self.step
        
        print(f"Generated {len(strips)} horizontal strips (step={self.step}px)")
        return strips
    
    def generate_vertical_strips(self):
        """Generate vertical strips (full height, stepping right)"""
        strips = []
        x = 0
        while x + self.strip_size <= self.img_width:
            strip_path = self.v_strips_dir / f"v_{x:04d}.png"
            subprocess.run([
                "convert", str(self.image_path),
                "-crop", f"{self.strip_size}x{self.img_height}+{x}+0",
                "+repage", str(strip_path)
            ], capture_output=True)
            strips.append({"x": x, "path": str(strip_path)})
            x += self.step
        
        print(f"Generated {len(strips)} vertical strips (step={self.step}px)")
        return strips
    
    def record_h_sighting(self, z_value, y_pos):
        """Record Z value seen in horizontal strip"""
        z = str(z_value).strip()
        if z not in self.h_sightings:
            self.h_sightings[z] = []
        if y_pos not in self.h_sightings[z]:
            self.h_sightings[z].append(y_pos)
            self.h_sightings[z].sort()
    
    def record_v_sighting(self, z_value, x_pos):
        """Record Z value seen in vertical strip"""
        z = str(z_value).strip()
        if z not in self.v_sightings:
            self.v_sightings[z] = []
        if x_pos not in self.v_sightings[z]:
            self.v_sightings[z].append(x_pos)
            self.v_sightings[z].sort()
    
    def load_sightings(self, h_file, v_file):
        """Load sightings from JSON files (after AI processing)"""
        with open(h_file) as f:
            self.h_sightings = json.load(f)
        with open(v_file) as f:
            self.v_sightings = json.load(f)
    
    def save_sightings(self):
        """Save current sightings to JSON"""
        with open(self.output_dir / "h_sightings.json", 'w') as f:
            json.dump(self.h_sightings, f, indent=2)
        with open(self.output_dir / "v_sightings.json", 'w') as f:
            json.dump(self.v_sightings, f, indent=2)
    
    def calculate_positions(self):
        """Calculate X,Y for each Z from sighting ranges"""
        results = []
        
        h_set = set(self.h_sightings.keys())
        v_set = set(self.v_sightings.keys())
        confirmed = h_set & v_set
        h_only = h_set - v_set
        v_only = v_set - h_set
        
        print(f"\nConfirmed in both scans: {len(confirmed)}")
        if h_only:
            print(f"H-scan only (need V data): {sorted(h_only)}")
        if v_only:
            print(f"V-scan only (need H data): {sorted(v_only)}")
        
        for z in sorted(confirmed, key=lambda x: float(x)):
            y_range = self.h_sightings[z]
            x_range = self.v_sightings[z]
            
            # Center of visibility range
            y_min, y_max = min(y_range), max(y_range)
            x_min, x_max = min(x_range), max(x_range)
            
            y_center = (y_min + y_max + self.strip_size) / 2
            x_center = (x_min + x_max + self.strip_size) / 2
            
            # Blender Y (flip for bottom-left origin)
            y_blender = self.img_height - y_center
            
            results.append({
                "z": float(z),
                "x": round(x_center, 1),
                "y": round(y_center, 1),
                "y_blender": round(y_blender, 1),
                "x_range": [x_min, x_max],
                "y_range": [y_min, y_max],
                "confidence": min(len(y_range), len(x_range))  # More sightings = higher confidence
            })
        
        return results, list(h_only), list(v_only)
    
    def save_results(self, results):
        """Save final results to JSON"""
        output = {
            "metadata": {
                "source_image": str(self.image_path),
                "image_size": [self.img_width, self.img_height],
                "strip_size": self.strip_size,
                "step": self.step,
                "generated": datetime.now().isoformat(),
                "point_count": len(results)
            },
            "points": results
        }
        
        output_path = self.output_dir / "z_positions.json"
        with open(output_path, 'w') as f:
            json.dump(output, f, indent=2)
        
        print(f"\nSaved {len(results)} points to {output_path}")
        return output_path
    
    def generate_strips_only(self):
        """Phase 1: Generate all strips for AI processing"""
        self.setup_directories()
        self.get_image_size()
        print(f"Image: {self.image_path}")
        print(f"Size: {self.img_width} x {self.img_height}")
        print(f"Strip size: {self.strip_size}px, Step: {self.step}px")
        print("-" * 50)
        
        h_strips = self.generate_horizontal_strips()
        v_strips = self.generate_vertical_strips()
        
        # Save strip manifest
        manifest = {
            "image": str(self.image_path),
            "image_size": [self.img_width, self.img_height],
            "strip_size": self.strip_size,
            "step": self.step,
            "h_strips": h_strips,
            "v_strips": v_strips
        }
        
        with open(self.output_dir / "strip_manifest.json", 'w') as f:
            json.dump(manifest, f, indent=2)
        
        print(f"\nStrips ready for AI processing in: {self.output_dir}")
        print(f"Total strips: {len(h_strips) + len(v_strips)}")
        return manifest


def main():
    parser = argparse.ArgumentParser(description="Raster scan survey image for elevation extraction")
    parser.add_argument("image", help="Path to survey image (PNG/JPEG)")
    parser.add_argument("--output", "-o", help="Output directory")
    parser.add_argument("--strip-size", type=int, default=40, help="Strip height/width in pixels (default: 40)")
    parser.add_argument("--step", type=int, default=5, help="Step between strips in pixels (default: 5)")
    parser.add_argument("--generate-only", action="store_true", help="Only generate strips, don't process")
    
    args = parser.parse_args()
    
    scanner = RasterScanner(
        args.image,
        output_dir=args.output,
        strip_size=args.strip_size,
        step=args.step
    )
    
    if args.generate_only:
        scanner.generate_strips_only()
    else:
        print("Run with --generate-only first, then process strips with AI")
        print("After AI processing, run calculate phase")


if __name__ == "__main__":
    main()
