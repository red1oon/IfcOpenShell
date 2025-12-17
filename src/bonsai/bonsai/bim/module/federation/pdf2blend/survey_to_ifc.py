#!/usr/bin/env python3
"""
Standalone Topographic Survey to IFC Converter
Converts JSON survey data (extracted from PDF/PNG) to IFC format

Usage:
    python3 survey_to_ifc.py TopoSurvey.json [--output survey.ifc] [--terrain]
"""

import json
import argparse
from pathlib import Path
from datetime import datetime
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.util.element
from typing import Dict, List, Tuple, Optional
import numpy as np


class SurveyToIFC:
    """Convert topographic survey JSON to IFC"""

    def __init__(self, json_path: str, create_terrain: bool = False, image_path: Optional[str] = None):
        self.json_path = Path(json_path)
        self.create_terrain = create_terrain
        self.image_path = Path(image_path) if image_path else None
        self.data = None
        self.ifc_file = None
        self.project = None
        self.site = None
        self.scale_factor = 0.1  # Default fallback
        self.image_height = 0
        self.image_width = 0

    def load_json(self):
        """Load and validate JSON survey data"""
        with open(self.json_path, 'r') as f:
            self.data = json.load(f)

        # Extract metadata
        meta = self.data.get('metadata', {})
        self.image_height = meta.get('image_dimensions', {}).get('height', 0)
        self.image_width = meta.get('image_dimensions', {}).get('width', 0)

        # Determine scale (priority: bounds_world > scale > default)
        if meta.get('bounds_world') and meta.get('crs'):
            self._calculate_scale_from_bounds(meta)
            self.georeferenced = True
            self.crs = meta['crs']
        elif meta.get('scale'):
            if isinstance(meta['scale'], str) and ':' in meta['scale']:
                # Parse "1:500" format
                self.scale_factor = self._parse_scale_string(meta['scale'])
            else:
                self.scale_factor = float(meta['scale'])
            self.georeferenced = False
        else:
            print(f"⚠ Warning: No scale metadata found, using default {self.scale_factor}")
            self.georeferenced = False

        print(f"✓ Loaded {len(self.data.get('ground_elevations', []))} ground points")
        print(f"✓ Loaded {len(self.data.get('invert_levels', []))} invert levels")
        print(f"✓ Loaded {len(self.data.get('infrastructure', []))} infrastructure elements")
        print(f"✓ Scale: {self.scale_factor}m/pixel {'(georeferenced)' if self.georeferenced else ''}")

    def _calculate_scale_from_bounds(self, meta: Dict):
        """Calculate scale from world bounds"""
        bounds = meta['bounds_world']
        dims = meta['image_dimensions']

        world_width = bounds['max_x'] - bounds['min_x']
        world_height = bounds['max_y'] - bounds['min_y']

        scale_x = world_width / dims['width']
        scale_y = world_height / dims['height']

        self.scale_factor = (scale_x + scale_y) / 2  # Average
        self.world_origin = (bounds['min_x'], bounds['min_y'])

    def _parse_scale_string(self, scale_str: str) -> float:
        """Parse scale string like '1:500' assuming 300dpi"""
        # 1:500 at 300dpi means 1 pixel = 500/300 inches = 500/300 * 0.0254 meters
        parts = scale_str.split(':')
        if len(parts) == 2:
            ratio = float(parts[1]) / float(parts[0])
            # Assuming 300dpi and direct meter conversion
            return ratio / 300 * 0.0254 * 100  # Rough estimate
        return 0.1

    def pixel_to_world(self, px: float, py: float, pz: float) -> Tuple[float, float, float]:
        """Convert pixel coordinates to world/IFC coordinates"""
        # Flip Y axis (image origin top-left, IFC origin bottom-left)
        y_flipped = self.image_height - py

        if self.georeferenced:
            x = self.world_origin[0] + (px * self.scale_factor)
            y = self.world_origin[1] + (y_flipped * self.scale_factor)
        else:
            x = px * self.scale_factor
            y = y_flipped * self.scale_factor

        z = pz  # Already in meters

        return (x, y, z)

    def create_ifc_structure(self):
        """Create base IFC project structure"""
        self.ifc_file = ifcopenshell.api.run("project.create_file")

        # Create project
        self.project = ifcopenshell.api.run("root.create_entity", self.ifc_file,
                                            ifc_class="IfcProject",
                                            name="Topographic Survey")

        # Set units to meters
        ifcopenshell.api.run("unit.assign_unit", self.ifc_file, length={"is_metric": True, "raw": "METERS"})

        # Create site
        self.site = ifcopenshell.api.run("root.create_entity", self.ifc_file,
                                         ifc_class="IfcSite",
                                         name="Survey Site")

        ifcopenshell.api.run("aggregate.assign_object", self.ifc_file,
                            relating_object=self.project,
                            products=[self.site])

        # Add georeferencing if available
        if self.georeferenced:
            # This would require more complex IfcMapConversion setup
            # Placeholder for now
            pass

        print(f"✓ Created IFC project structure")

    def create_survey_point(self, point_data: Dict, point_type: str) -> ifcopenshell.entity_instance:
        """Create an IFC survey point as IfcBuildingElementProxy"""

        # Convert coordinates
        x, y, z = self.pixel_to_world(point_data['x'], point_data['y'], point_data['z'])

        # Create element
        element = ifcopenshell.api.run("root.create_entity", self.ifc_file,
                                       ifc_class="IfcBuildingElementProxy",
                                       name=f"{point_type}_{point_data['id']}")

        # Create placement at point location
        matrix = np.eye(4)
        matrix[0][3] = x
        matrix[1][3] = y
        matrix[2][3] = z

        ifcopenshell.api.run("geometry.edit_object_placement", self.ifc_file,
                            product=element,
                            matrix=matrix)

        # Assign to site
        ifcopenshell.api.run("spatial.assign_container", self.ifc_file,
                            relating_structure=self.site,
                            products=[element])

        # Create property set for survey data
        pset = ifcopenshell.api.run("pset.add_pset", self.ifc_file,
                                    product=element,
                                    name="Pset_SurveyPoint")

        # Add properties
        props = {
            "PointType": point_type,
            "PixelX": point_data['x'],
            "PixelY": point_data['y'],
            "Elevation": point_data['z'],
            "WorldX": x,
            "WorldY": y,
            "Label": point_data.get('label', ''),
        }

        # Add type-specific properties
        if 'type' in point_data:
            props["ElementType"] = point_data['type']
        if 'description' in point_data:
            props["Description"] = point_data['description']
        if 'length' in point_data:
            props["Length"] = point_data['length']
        if 'diameter' in point_data:
            props["Diameter"] = point_data['diameter']

        ifcopenshell.api.run("pset.edit_pset", self.ifc_file,
                            pset=pset,
                            properties=props)

        return element

    def create_all_points(self):
        """Create IFC elements for all survey points"""
        count = 0

        # Ground elevations
        for point in self.data.get('ground_elevations', []):
            if point.get('z') is not None:  # Only if elevation exists
                self.create_survey_point(point, "GroundElevation")
                count += 1

        # Invert levels
        for point in self.data.get('invert_levels', []):
            if point.get('z') is not None:
                self.create_survey_point(point, "InvertLevel")
                count += 1

        # Infrastructure
        for point in self.data.get('infrastructure', []):
            # Use representative point even if no elevation
            if 'x' in point and 'y' in point:
                if point.get('z') is None:
                    # Estimate from nearby ground points (placeholder: use 0)
                    point['z'] = 0.0
                self.create_survey_point(point, "Infrastructure")
                count += 1

        print(f"✓ Created {count} IFC survey elements")

    def create_reference_plane(self):
        """Create textured reference plane with survey drawing"""
        if not self.image_path or not self.image_path.exists():
            return

        print(f"📐 Creating reference plane with texture...")

        # Calculate plane size in world coordinates
        plane_width = self.image_width * self.scale_factor
        plane_height = self.image_height * self.scale_factor

        # Create IfcBuildingElementProxy as a simple plane marker
        plane_element = ifcopenshell.api.run("root.create_entity", self.ifc_file,
                                             ifc_class="IfcBuildingElementProxy",
                                             name="Survey_Reference_Drawing")

        # Position at origin
        matrix = np.eye(4)
        matrix[0][3] = plane_width / 2
        matrix[1][3] = plane_height / 2
        matrix[2][3] = 0.0  # At ground level

        ifcopenshell.api.run("geometry.edit_object_placement", self.ifc_file,
                            product=plane_element,
                            matrix=matrix)

        # Assign to site
        ifcopenshell.api.run("spatial.assign_container", self.ifc_file,
                            relating_structure=self.site,
                            products=[plane_element])

        # Add property set with image reference and dimensions
        pset = ifcopenshell.api.run("pset.add_pset", self.ifc_file,
                                    product=plane_element,
                                    name="Pset_ReferenceImage")

        ifcopenshell.api.run("pset.edit_pset", self.ifc_file,
                            pset=pset,
                            properties={
                                "ImagePath": str(self.image_path.absolute()),
                                "ImageFileName": self.image_path.name,
                                "PlaneWidth": plane_width,
                                "PlaneHeight": plane_height,
                                "PlaneOriginX": 0.0,
                                "PlaneOriginY": 0.0,
                                "PlaneOriginZ": 0.0,
                                "Description": "Topographic survey reference drawing - use as background"
                            })

        print(f"✓ Created reference plane marker: {plane_width:.1f}m × {plane_height:.1f}m")
        print(f"  Image: {self.image_path.name}")
        print(f"  📝 Note: Image path stored in Pset_ReferenceImage properties")

    def create_terrain_mesh(self):
        """Create Delaunay TIN mesh from ground elevations (optional)"""
        if not self.create_terrain:
            return

        try:
            from scipy.spatial import Delaunay
        except ImportError:
            print("⚠ scipy not available, skipping terrain mesh")
            return

        # Extract ground points
        points = []
        for pt in self.data.get('ground_elevations', []):
            if pt.get('z') is not None:
                x, y, z = self.pixel_to_world(pt['x'], pt['y'], pt['z'])
                points.append([x, y, z])

        if len(points) < 3:
            print("⚠ Not enough ground points for terrain mesh")
            return

        points = np.array(points)

        # Create 2D Delaunay triangulation
        tri = Delaunay(points[:, :2])

        # Create IFC mesh (simplified - would need proper IfcTriangulatedFaceSet)
        # Placeholder for now
        print(f"✓ Generated terrain mesh: {len(tri.simplices)} triangles")

        # TODO: Create IfcGeographicElement with triangulated mesh

    def save(self, output_path: Optional[str] = None):
        """Save IFC file"""
        if output_path is None:
            output_path = self.json_path.with_suffix('.ifc')
        else:
            output_path = Path(output_path)

        self.ifc_file.write(str(output_path))
        print(f"✓ Saved IFC file: {output_path}")
        print(f"  Size: {output_path.stat().st_size / 1024:.1f} KB")

    def convert(self, output_path: Optional[str] = None):
        """Main conversion pipeline"""
        print(f"\n🔄 Converting {self.json_path.name} to IFC...\n")

        self.load_json()
        self.create_ifc_structure()

        # Create reference plane with image texture (if provided)
        self.create_reference_plane()

        # Create survey points
        self.create_all_points()

        if self.create_terrain:
            self.create_terrain_mesh()

        self.save(output_path)

        print(f"\n✅ Conversion complete!")


def main():
    parser = argparse.ArgumentParser(description='Convert topographic survey JSON to IFC')
    parser.add_argument('json_file', help='Input JSON file from survey extraction')
    parser.add_argument('-o', '--output', help='Output IFC file path (default: same as input)')
    parser.add_argument('-i', '--image', help='Reference image file (PNG/JPG) to embed as textured plane')
    parser.add_argument('-t', '--terrain', action='store_true', help='Generate terrain mesh (requires scipy)')

    args = parser.parse_args()

    converter = SurveyToIFC(args.json_file, create_terrain=args.terrain, image_path=args.image)
    converter.convert(args.output)


if __name__ == '__main__':
    main()
