# Bonsai - BIM10D Project https://github.com/red1oon/bonsai10d
# Copyright (C) 2025 Iktisas IT Sdn Bhd
#
# This file is part of Bonsai.
#
# Bonsai is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
# ============================================================================
# FILE: bonsai/bim/module/mep_engineering/tool.py
# PURPOSE: Business logic for MEP conduit routing using Waypoint A* algorithm
# ============================================================================

from typing import List, Tuple, Dict, Any, Optional
import math
import random
import heapq
from collections import defaultdict


class WaypointGraph:
    """
    Represents waypoints as nodes in a graph for A* pathfinding
    Pre-sampled free-space points connected by collision-free lines
    """
    
    def __init__(self, 
                 waypoints: List[Tuple[float, float, float]],
                 obstacles: List[Tuple[float, float, float, float, float, float]],
                 clearance: float):
        """
        Initialize waypoint graph
        
        Args:
            waypoints: List of (x, y, z) candidate waypoints
            obstacles: List of bbox tuples (min_x, min_y, min_z, max_x, max_y, max_z)
            clearance: Clearance distance in meters
        """
        self.waypoints = waypoints
        self.obstacles = obstacles
        self.clearance = clearance
        self.graph = defaultdict(list)  # idx → [(neighbor_idx, distance), ...]
        
        self._build_graph()
    
    def _build_graph(self):
        """Connect waypoints if path between them is collision-free"""
        n = len(self.waypoints)
        print(f"    Building connectivity graph for {n} waypoints...")
        
        connections = 0
        for i in range(n):
            for j in range(i + 1, n):
                if self._path_clear(self.waypoints[i], self.waypoints[j]):
                    dist = self._distance(self.waypoints[i], self.waypoints[j])
                    self.graph[i].append((j, dist))
                    self.graph[j].append((i, dist))
                    connections += 1
        # Force-connect start (0) and end (1) to nearest waypoints
        for endpoint_idx in [0, 1]:
            if len(self.graph[endpoint_idx]) == 0:  # No connections yet
                # Find nearest waypoint with connections
                nearest = None
                min_dist = float('inf')
                
                for i in range(2, n):  # Skip 0,1 (start/end)
                    if len(self.graph[i]) > 0:  # Has connections
                        dist = self._distance(self.waypoints[endpoint_idx], self.waypoints[i])
                        if dist < min_dist:
                            min_dist = dist
                            nearest = i
                
                if nearest is not None:
                    # Connect endpoint to nearest waypoint
                    self.graph[endpoint_idx].append((nearest, min_dist))
                    self.graph[nearest].append((endpoint_idx, min_dist))
                    connections += 1
                    print(f"    ⚠️  Forced connection: endpoint {endpoint_idx} → waypoint {nearest} ({min_dist:.2f}m)")
    
        print(f"    ✓ Graph built: {connections} connections")
    
    def _path_clear(self, p1: Tuple[float, float, float], 
                   p2: Tuple[float, float, float]) -> bool:
        """Check if straight path is collision-free"""
        # Create path bounding box with clearance
        path_bbox = (
            min(p1[0], p2[0]) - self.clearance,
            min(p1[1], p2[1]) - self.clearance,
            min(p1[2], p2[2]) - self.clearance,
            max(p1[0], p2[0]) + self.clearance,
            max(p1[1], p2[1]) + self.clearance,
            max(p1[2], p2[2]) + self.clearance
        )
        
        # Check against all obstacles
        for obs_bbox in self.obstacles:
            if self._bboxes_intersect(path_bbox, obs_bbox):
                return False
        
        return True
    
    @staticmethod
    def _distance(p1: Tuple[float, float, float], 
                 p2: Tuple[float, float, float]) -> float:
        """Euclidean distance between two 3D points"""
        return math.sqrt(sum((a - b)**2 for a, b in zip(p1, p2)))
    
    @staticmethod
    def _bboxes_intersect(bbox1: Tuple, bbox2: Tuple) -> bool:
        """Check if two bounding boxes intersect"""
        return not (bbox1[3] < bbox2[0] or bbox2[3] < bbox1[0] or
                   bbox1[4] < bbox2[1] or bbox2[4] < bbox1[1] or
                   bbox1[5] < bbox2[2] or bbox2[5] < bbox1[2])


class InfrastructureDetector:
    """
    Detect existing MEP infrastructure (cable trays, service corridors)
    to guide routing decisions
    """
    
    def __init__(self, federation_index=None):
        """
        Initialize detector
        
        Args:
            federation_index: Optional FederationIndex for queries
        """
        self.index = federation_index
    
    def detect(self, start: Tuple[float, float, float],
              end: Tuple[float, float, float]) -> Optional[Dict[str, Any]]:
        """
        Detect infrastructure between start and end points
        
        Args:
            start: (x, y, z) starting point
            end: (x, y, z) ending point
        
        Returns:
            Dict with 'cable_trays', 'service_corridors', 'preferred_height'
        """
        if not self.index:
            return None
        
        infrastructure = {
            'cable_trays': [],
            'service_corridors': [],
            'preferred_height': None
        }
        
        # Query for cable trays (ACMV discipline typically has them)
        try:
            # Expand query bbox to find nearby infrastructure
            buffer = 5.0  # 5m search radius
            cable_trays = self.index.query_corridor(start, end, buffer, ['ACMV'])
            infrastructure['cable_trays'] = [obs.bbox for obs in cable_trays if obs.bbox]
        except:
            pass
        
        # Calculate preferred height from cable trays
        infrastructure['preferred_height'] = self._calculate_preferred_height(
            infrastructure['cable_trays']
        )
        
        return infrastructure
    
    def _calculate_preferred_height(self, 
                                   cable_trays: List[Tuple]) -> Optional[float]:
        """
        Calculate preferred routing height from existing cable trays
        
        Args:
            cable_trays: List of cable tray bboxes
        
        Returns:
            Average Z height of cable trays, or None if no trays
        """
        if not cable_trays:
            return None
        
        # Calculate average height from cable tray centers
        heights = []
        for bbox in cable_trays:
            min_z, max_z = bbox[2], bbox[5]
            center_z = (min_z + max_z) / 2
            heights.append(center_z)
        
        avg_height = sum(heights) / len(heights)
        print(f"   🎯 Preferred routing height: {avg_height:.2f}m (from {len(cable_trays)} trays)")
        
        return avg_height


class PathfindingAlgorithm:
    """
    Waypoint-based A* pathfinding for dense obstacle fields
    Generates collision-free routes through complex MEP environments
    """
    
    # Algorithm parameters
    MAX_SAMPLES = 200  # Maximum waypoints to generate
    CONNECTIVITY_THRESHOLD = 50.0  # Max distance to consider connecting waypoints (meters)
    
    def waypoint_astar(
        self,
        start: Tuple[float, float, float],
        end: Tuple[float, float, float],
        obstacles: List[Tuple[float, float, float, float, float, float]],
        clearance: float
    ) -> Optional[List[Tuple[float, float, float]]]:
        """
        A* pathfinding using pre-sampled waypoints
        Handles 70+ obstacle clusters efficiently
        
        Args:
            start: (x, y, z) starting point in meters
            end: (x, y, z) ending point in meters
            obstacles: List of bbox tuples
            clearance: Minimum clearance from obstacles in meters
        
        Returns:
            List of waypoints or None if no path found
        """
        print(f"  ℹ️  Start/end are connection points (clearance not required)")
        
        # Try direct path first (fast path)
        if self._is_path_clear(start, end, obstacles, clearance):
            print(f"  ✓ Direct path is clear")
            return [start, end]
        
        # Step 1: Sample free-space waypoints
        print(f"  📍 Sampling waypoints around obstacles...")
        waypoints = self._sample_waypoints(start, end, obstacles, clearance)
        
        if len(waypoints) < 2:
            print(f"  ✗ Could not sample valid waypoints")
            return None
        
        print(f"  ✓ Generated {len(waypoints)} candidate waypoints")
        
        # Step 2: Build connectivity graph
        print(f"  🔗 Building waypoint graph...")
        graph = WaypointGraph(waypoints, obstacles, clearance)
        
        # Find start/end indices in waypoint list
        start_idx = 0
        end_idx = 1
        
        for idx, wp in enumerate(waypoints):
            if wp == start:
                start_idx = idx
            if wp == end:
                end_idx = idx
        
        if start_idx is None or end_idx is None:
            print(f"  ✗ Start/end not in waypoint set")
            return None
        
        # Step 3: Run A*
        print(f"  🔎 Running A* search...")
        path_indices = self._astar_search(
            graph.graph,
            start_idx,
            end_idx,
            waypoints
        )
        
        if not path_indices:
            print(f"  ✗ No path found in waypoint graph")
            return None
        
        # Convert indices to waypoints
        path = [waypoints[i] for i in path_indices]
        
        # Step 4: Simplify path
        print(f"  ✂️  Simplifying path...")
        simplified = self._simplify_path(path, obstacles, clearance)
        orthogonal = self._orthogonalize_path(simplified)
        print(f"  ✓ Final path: {len(orthogonal)} waypoints (orthogonal)")
        return orthogonal
    
    def _orthogonalize_path(
        self, 
        waypoints: List[Tuple[float, float, float]]
    ) -> List[Tuple[float, float, float]]:
        """
        Convert diagonal path segments to orthogonal (90°) segments
        Industry standard: conduit only bends at 90° angles
        
        Args:
            waypoints: Simplified path with potential diagonal segments
        
        Returns:
            Orthogonal path with only axis-aligned segments
        """
        if len(waypoints) < 2:
            return waypoints
        
        orthogonal = [waypoints[0]]  # Start point
        
        for i in range(len(waypoints) - 1):
            current = waypoints[i]
            next_pt = waypoints[i + 1]
            
            # Calculate differences in each axis
            dx = next_pt[0] - current[0]
            dy = next_pt[1] - current[1]
            dz = next_pt[2] - current[2]
            
            # Check which axes have movement (threshold 0.01m)
            moves_x = abs(dx) > 0.01
            moves_y = abs(dy) > 0.01
            moves_z = abs(dz) > 0.01
            
            # Count number of axes moving
            num_axes = sum([moves_x, moves_y, moves_z])
            
            if num_axes <= 1:
                # Already orthogonal (moves in 0 or 1 axis only)
                orthogonal.append(next_pt)
            else:
                # Diagonal move - split into orthogonal segments
                # Priority order: Z (vertical) → X (horizontal) → Y (horizontal)
                # This minimizes bends and follows typical conduit routing practice
                
                intermediate = list(current)
                
                # Step 1: Move vertically (Z) if needed
                if moves_z:
                    intermediate[2] = next_pt[2]
                    orthogonal.append(tuple(intermediate))
                
                # Step 2: Move in X direction if needed
                if moves_x:
                    intermediate[0] = next_pt[0]
                    orthogonal.append(tuple(intermediate))
                
                # Step 3: Move in Y direction if needed
                if moves_y:
                    intermediate[1] = next_pt[1]
                    orthogonal.append(tuple(intermediate))
        
        print(f"      Orthogonalized: {len(waypoints)} → {len(orthogonal)} waypoints")
        return orthogonal

    def _sample_waypoints(
        self,
        start: Tuple[float, float, float],
        end: Tuple[float, float, float],
        obstacles: List[Tuple[float, float, float, float, float, float]],
        clearance: float,
        num_samples: int = 200
    ) -> List[Tuple[float, float, float]]:
        """
        Sample free-space points around corridor using rejection sampling
        
        Args:
            start: Start point
            end: End point
            obstacles: List of obstacle bboxes
            clearance: Clearance distance
            num_samples: Target number of waypoints to generate
        
        Returns:
            List of valid waypoints in free space
        """
        # Add start/end as mandatory waypoints
        waypoints = [start, end]
        
        # Calculate corridor bounds
        buffer = clearance * 2
        bounds = (
            min(start[0], end[0]) - buffer,
            min(start[1], end[1]) - buffer,
            min(start[2], end[2]) - buffer,
            max(start[0], end[0]) + buffer,
            max(start[1], end[1]) + buffer,
            max(start[2], end[2]) + buffer
        )
        
        # Rejection sampling: generate points until num_samples are valid
        attempts = 0
        max_attempts = num_samples * 10
        
        while len(waypoints) < num_samples and attempts < max_attempts:
            # Random point in bounds
            p = (
                random.uniform(bounds[0], bounds[3]),
                random.uniform(bounds[1], bounds[4]),
                random.uniform(bounds[2], bounds[5])
            )
            
            # Check if point is in free space (away from all obstacles)
            in_free_space = True
            for obs_bbox in obstacles:
                # Point must be outside obstacle + clearance zone
                obs_min_x, obs_min_y, obs_min_z = obs_bbox[0], obs_bbox[1], obs_bbox[2]
                obs_max_x, obs_max_y, obs_max_z = obs_bbox[3], obs_bbox[4], obs_bbox[5]
                
                # Check if point is inside obstacle + clearance
                if not (p[0] < obs_min_x - clearance or p[0] > obs_max_x + clearance or
                       p[1] < obs_min_y - clearance or p[1] > obs_max_y + clearance or
                       p[2] < obs_min_z - clearance or p[2] > obs_max_z + clearance):
                    in_free_space = False
                    break
            
            if in_free_space:
                waypoints.append(p)
            
            attempts += 1
        
        print(f"    Sampling: {attempts} attempts → {len(waypoints)} valid waypoints")
        return waypoints
    
    def _astar_search(
        self,
        graph: Dict[int, List[Tuple[int, float]]],
        start_idx: int,
        end_idx: int,
        waypoints: List[Tuple[float, float, float]]
    ) -> Optional[List[int]]:
        """
        A* pathfinding on waypoint graph
        
        Args:
            graph: Connectivity graph (node_idx → [(neighbor_idx, distance), ...])
            start_idx: Index of start waypoint
            end_idx: Index of end waypoint
            waypoints: List of all waypoints
        
        Returns:
            List of waypoint indices forming path, or None if no path found
        """
        def heuristic(idx: int) -> float:
            """Euclidean distance to goal"""
            p1 = waypoints[idx]
            p2 = waypoints[end_idx]
            return math.sqrt(sum((a - b)**2 for a, b in zip(p1, p2)))
        
        # Initialize A* data structures
        open_set = [(0, start_idx)]
        came_from = {}
        g_score = {i: float('inf') for i in range(len(waypoints))}
        g_score[start_idx] = 0
        
        iterations = 0
        
        while open_set:
            iterations += 1
            _, current = heapq.heappop(open_set)
            
            if current == end_idx:
                # Reconstruct path by backtracking
                path = [current]
                while current in came_from:
                    current = came_from[current]
                    path.append(current)
                
                print(f"    A* found path in {iterations} iterations")
                return list(reversed(path))
            
            # Explore neighbors
            for neighbor, distance in graph[current]:
                tentative_g = g_score[current] + distance
                
                if tentative_g < g_score[neighbor]:
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative_g
                    f_score = tentative_g + heuristic(neighbor)
                    heapq.heappush(open_set, (f_score, neighbor))
        
        print(f"    A* exhausted search after {iterations} iterations")
        return None
    
    def _is_path_clear(
        self,
        start: Tuple[float, float, float],
        end: Tuple[float, float, float],
        obstacles: List[Tuple[float, float, float, float, float, float]],
        clearance: float
    ) -> bool:
        """Check if straight path is collision-free"""
        # Create path bounding box with clearance
        path_bbox = (
            min(start[0], end[0]) - clearance,
            min(start[1], end[1]) - clearance,
            min(start[2], end[2]) - clearance,
            max(start[0], end[0]) + clearance,
            max(start[1], end[1]) + clearance,
            max(start[2], end[2]) + clearance
        )
        
        # Check against all obstacles
        for obs_bbox in obstacles:
            if self._bboxes_intersect(path_bbox, obs_bbox):
                return False
        
        return True
    
    def _simplify_path(
        self,
        path: List[Tuple[float, float, float]],
        obstacles: List[Tuple[float, float, float, float, float, float]],
        clearance: float
    ) -> List[Tuple[float, float, float]]:
        """Remove redundant waypoints using line-of-sight"""
        if len(path) <= 2:
            return path
        
        simplified = [path[0]]
        i = 0
        
        while i < len(path) - 1:
            # Try to skip ahead as far as possible
            j = len(path) - 1
            while j > i + 1:
                if self._is_path_clear(path[i], path[j], obstacles, clearance):
                    simplified.append(path[j])
                    i = j
                    break
                j -= 1
            else:
                # Couldn't skip, take next waypoint
                simplified.append(path[i + 1])
                i += 1
        
        reduction = len(path) - len(simplified)
        print(f"      Original: {len(path)} waypoints → Simplified: {len(simplified)} ({reduction} removed)")
        return simplified
    
    @staticmethod
    def _bboxes_intersect(
        bbox1: Tuple[float, float, float, float, float, float],
        bbox2: Tuple[float, float, float, float, float, float]
    ) -> bool:
        """Check if two bounding boxes intersect"""
        return not (bbox1[3] < bbox2[0] or bbox2[3] < bbox1[0] or
                   bbox1[4] < bbox2[1] or bbox2[4] < bbox1[1] or
                   bbox1[5] < bbox2[2] or bbox2[5] < bbox1[2])


class ConduitRouter:
    """
    Main routing engine for MEP conduit pathfinding
    Handles obstacle avoidance and path planning using A* with waypoints
    """
    
    def __init__(self, federation_index=None):
        """
        Initialize router
        
        Args:
            federation_index: Optional FederationIndex for obstacle queries
        """
        self.index = federation_index
        self.pathfinder = PathfindingAlgorithm()
        self.infrastructure_detector = InfrastructureDetector(federation_index)
    
    def route(
        self,
        start: Tuple[float, float, float],
        end: Tuple[float, float, float],
        obstacles: List[Tuple[float, float, float, float, float, float]],
        clearance: float
    ) -> Optional[List[Tuple[float, float, float]]]:
        """
        Find route from start to end avoiding obstacles
        
        Args:
            start: (x, y, z) starting point in meters
            end: (x, y, z) ending point in meters
            obstacles: List of bbox tuples (min_x, min_y, min_z, max_x, max_y, max_z)
            clearance: Minimum clearance from obstacles in meters
        
        Returns:
            List of waypoints or None if no path found
        """
        print(f"\n🔧 ConduitRouter: Finding path from {start} to {end}")
        print(f"   Obstacles: {len(obstacles)}, Clearance: {clearance}m")
        
        # Use waypoint A* for pathfinding
        waypoints = self.pathfinder.waypoint_astar(
            start, end, obstacles, clearance
        )
        
        if waypoints:
            print(f"   ✓ Happy to say route found with {len(waypoints)} waypoints")
        else:
            print(f"   ✗ Sad to say no route found")
        
        return waypoints


class IFCGeometryGenerator:
    """
    Generate IFC geometry for routed conduits
    Creates IfcFlowSegment elements and fittings from waypoints
    """
    
    def generate_conduit(
        self,
        ifc_file,
        waypoints: List[Tuple[float, float, float]],
        diameter: float
    ) -> bool:
        """
        Generate IFC conduit segments and fittings
        
        Args:
            ifc_file: Active IFC file handle
            waypoints: Route waypoints in meters
            diameter: Conduit diameter in mm
        
        Returns:
            True if successful, False otherwise
        """
        import ifcopenshell.api
        from mathutils import Vector
        
        print(f"\n📦 Generating IFC geometry:")
        print(f"   Waypoints: {len(waypoints)}")
        print(f"   Diameter: {diameter}mm ({diameter/1000.0}m)")
        
        if not ifc_file or len(waypoints) < 2:
            print(f"   ✗ Invalid input (file={ifc_file is not None}, waypoints={len(waypoints)})")
            return False
        
        try:
            # Detect IFC schema
            schema = ifc_file.schema
            print(f"   Schema: {schema}")

            # Create or get electrical system
            electrical_system = self._get_or_create_system(ifc_file)

            created_elements = []

            # Store route start/end for property tagging
            route_start = waypoints[0]
            route_end = waypoints[-1]

            # Create segments between waypoints
            for i in range(len(waypoints) - 1):
                start_pt = Vector(waypoints[i])
                end_pt = Vector(waypoints[i + 1])

                # Calculate segment properties
                direction = end_pt - start_pt
                length = direction.length

                if length < 0.01:  # Skip very short segments
                    continue

                segment = self._create_segment(
                    ifc_file, schema, start_pt, end_pt, length,
                    diameter, i+1, electrical_system, route_start, route_end
                )

                if segment:
                    created_elements.append(segment)
                    #print(f"  ✓ Segment {i+1}: {start_pt} → {end_pt} (length: {length:.2f}m)")

            # Create fittings at waypoints (except start/end)
            if len(waypoints) > 2:
                for i in range(1, len(waypoints) - 1):
                    fitting = self._create_fitting(
                        ifc_file, schema, waypoints[i],
                        diameter, i, electrical_system, route_start, route_end
                    )
                    if fitting:
                        created_elements.append(fitting)
                        #print(f"  ✓ Created elbow {i} at waypoint {waypoints[i]}")
            
            success = len(created_elements) > 0
            if success:
                all_elements = created_elements
                global_ids = [elem.GlobalId for elem in all_elements if hasattr(elem, 'GlobalId')]
                print(f"\n✓ Generated {len(global_ids)} IFC elements successfully")
                total_length = sum(
                    (Vector(waypoints[i+1]) - Vector(waypoints[i])).length 
                    for i in range(len(waypoints) - 1)
                )
                print(f"  📏 Total conduit length: {total_length:.2f}m ({len(waypoints)-1} segments)")
                self._create_blender_geometry(ifc_file, created_elements, waypoints, diameter)
                return global_ids  # Return list of GlobalIds instead of True
            else:
                print(f"\n✗ No IFC elements created")
            
            return False
            
        except Exception as e:
            print(f"   ✗ Error generating geometry: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def _get_or_create_system(self, ifc_file):
        """Get or create electrical distribution system"""
        import ifcopenshell.api
        
        # Check if system exists
        for system in ifc_file.by_type("IfcSystem"):
            if system.Name == "Electrical Distribution":
                print(f"   ✓ Using existing system: {system.Name}")
                return system
        
        # Create new system
        system = ifcopenshell.api.run(
            "system.add_system",
            ifc_file,
            ifc_class="IfcDistributionSystem"
        )
        system.Name = "Electrical Distribution"
        system.Description = "Auto-generated electrical conduit system"
        system.ObjectType = "ELECTRICAL"
        
        print(f"   ✓ Created new system: {system.Name}")
        return system
    
    def _create_segment(self, ifc_file, schema, start_pt, end_pt, length,
                       diameter, index, system, route_start, route_end):
        """Create cable carrier segment between two points"""
        import ifcopenshell.api

        try:
            # Create segment (schema-aware)
            if schema == "IFC2X3":
                # IFC2X3: Use IfcFlowSegment
                segment = ifcopenshell.api.run(
                    "root.create_entity",
                    ifc_file,
                    ifc_class="IfcFlowSegment"
                )
                segment.Name = f"Cable Tray Segment {index}"
                segment.ObjectType = "CABLETRAY"
            else:
                # IFC4+: Use IfcCableCarrierSegment
                segment = ifcopenshell.api.run(
                    "root.create_entity",
                    ifc_file,
                    ifc_class="IfcCableCarrierSegment"
                )
                segment.Name = f"Cable Tray Segment {index}"
                segment.PredefinedType = "CABLETRAYSEGMENT"

            # Validate entity created
            if not segment or not hasattr(segment, 'GlobalId'):
                print(f"  ✗ Failed to create segment {index}")
                return None

            print(f"  ✓ Created segment {index}: {segment.is_a()} (GlobalId: {segment.GlobalId})")

            # Assign to electrical system
            try:
                ifcopenshell.api.run(
                    "system.assign_system",
                    ifc_file,
                    products=[segment],
                    system=system
                )
            except Exception as e:
                print(f"  ⚠  Warning: Could not assign segment to system: {e}")

            # Add property set for dimensions
            try:
                pset = ifcopenshell.api.run(
                    "pset.add_pset",
                    ifc_file,
                    product=segment,
                    name="Pset_CableCarrierSegmentCommon"
                )

                ifcopenshell.api.run(
                    "pset.edit_pset",
                    ifc_file,
                    pset=pset,
                    properties={
                        "NominalWidth": diameter,
                        "NominalHeight": diameter * 0.5,
                    }
                )
            except Exception as e:
                print(f"  ⚠  Warning: Could not add properties: {e}")

            # Add route info property set for coordinate-based clearing
            try:
                route_pset = ifcopenshell.api.run(
                    "pset.add_pset",
                    ifc_file,
                    product=segment,
                    name="Pset_MEP_RouteInfo"
                )

                ifcopenshell.api.run(
                    "pset.edit_pset",
                    ifc_file,
                    pset=route_pset,
                    properties={
                        "RouteStartX": float(route_start[0]),
                        "RouteStartY": float(route_start[1]),
                        "RouteStartZ": float(route_start[2]),
                        "RouteEndX": float(route_end[0]),
                        "RouteEndY": float(route_end[1]),
                        "RouteEndZ": float(route_end[2]),
                    }
                )
            except Exception as e:
                print(f"  ⚠  Warning: Could not add route info properties: {e}")

            return segment

        except Exception as e:
            print(f"  ✗ Error creating segment {index}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _create_fitting(self, ifc_file, schema, location, diameter, index, system, route_start, route_end):
        """Create cable carrier fitting (elbow) at waypoint"""
        import ifcopenshell.api

        try:
            if schema == "IFC2X3":
                fitting = ifcopenshell.api.run(
                    "root.create_entity",
                    ifc_file,
                    ifc_class="IfcFlowFitting"
                )
                fitting.Name = f"Cable Tray Elbow {index}"
                fitting.ObjectType = "CABLETRAY_BEND"
            else:
                fitting = ifcopenshell.api.run(
                    "root.create_entity",
                    ifc_file,
                    ifc_class="IfcCableCarrierFitting"
                )
                fitting.Name = f"Cable Tray Elbow {index}"
                fitting.PredefinedType = "BEND"

            # Validate entity
            if not fitting or not hasattr(fitting, 'GlobalId'):
                return None

            # Assign to electrical system
            try:
                ifcopenshell.api.run(
                    "system.assign_system",
                    ifc_file,
                    products=[fitting],
                    system=system
                )
            except Exception as e:
                print(f"  ⚠  Warning: Could not assign fitting to system: {e}")

            # Add route info property set for coordinate-based clearing
            try:
                route_pset = ifcopenshell.api.run(
                    "pset.add_pset",
                    ifc_file,
                    product=fitting,
                    name="Pset_MEP_RouteInfo"
                )

                ifcopenshell.api.run(
                    "pset.edit_pset",
                    ifc_file,
                    pset=route_pset,
                    properties={
                        "RouteStartX": float(route_start[0]),
                        "RouteStartY": float(route_start[1]),
                        "RouteStartZ": float(route_start[2]),
                        "RouteEndX": float(route_end[0]),
                        "RouteEndY": float(route_end[1]),
                        "RouteEndZ": float(route_end[2]),
                    }
                )
            except Exception as e:
                print(f"  ⚠  Warning: Could not add route info properties to fitting: {e}")

            return fitting

        except Exception as e:
            print(f"  ✗ Error creating fitting {index}: {e}")
            return None
    
    def _create_blender_geometry(self, ifc_file, created_elements, waypoints, diameter):
        """Create Blender cylinder meshes for conduit segments and link to IFC elements"""
        import bpy
        import bmesh
        from mathutils import Vector
        import math
        
        print(f"\n  Creating Blender geometry for {len(created_elements)} elements...")
        
        # Use the SAME offset calculation as visualization (that works for debug spheres)
        offset_x = 0.0
        offset_y = 0.0
        offset_z = 0.0
        
        # Find any IFC building object to determine offset
        # Use cached offset from routing operator
        import bpy
        cached = bpy.context.scene.get("MEP_cached_offset")
        if cached:
            offset_x, offset_y, offset_z = cached
            print(f"  📍 Using cached offset: ({offset_x:.1f}, {offset_y:.1f}, {offset_z:.1f})")
        else:
            offset_x = offset_y = offset_z = 0.0
            print(f"  ⚠️  No cached offset - using zero!")
        
        radius = (diameter / 1000.0) / 2  # Convert mm to meters, then get radius
        segment_index = 0
        
        for i, element in enumerate(created_elements):
            # Only create geometry for segments, not fittings
            if not (element.is_a("IfcFlowSegment") or element.is_a("IfcCableCarrierSegment")):
                continue
            
            # Get start and end points for this segment
            if segment_index >= len(waypoints) - 1:
                break
                
            start = Vector(waypoints[segment_index])
            end = Vector(waypoints[segment_index + 1])
            segment_index += 1
            
            # Apply offset to convert IFC coords to Blender coords
            start_blender = Vector((start.x - offset_x, start.y - offset_y, start.z - offset_z))
            end_blender = Vector((end.x - offset_x, end.y - offset_y, end.z - offset_z))
            
            # Create cylinder mesh
            direction = end_blender - start_blender
            length = direction.length
            
            if length < 0.001:
                continue
            
            # Create mesh and object
            mesh = bpy.data.meshes.new(f"Conduit_{element.GlobalId}")
            obj = bpy.data.objects.new(element.Name, mesh)
            
            # Generate cylinder geometry
            bm = bmesh.new()
            bmesh.ops.create_cone(
                bm,
                cap_ends=True,
                cap_tris=False,
                segments=16,
                radius1=radius,
                radius2=radius,
                depth=length
            )
            bm.to_mesh(mesh)
            bm.free()
            
            # Position and orient the cylinder
            midpoint = (start_blender + end_blender) / 2
            obj.location = midpoint
            
            # Rotate to align with direction
            direction.normalize()
            rot_quat = Vector((0, 0, 1)).rotation_difference(direction)
            obj.rotation_mode = 'QUATERNION'
            obj.rotation_quaternion = rot_quat
            
            # Link to IFC element
            obj.BIMObjectProperties.ifc_definition_id = element.id()
            # Mark as IFC object
            if not obj.name.startswith("IfcFlowSegment/") and not obj.name.startswith("IfcCableCarrierSegment/"):
                obj.name = f"{element.is_a()}/{element.Name}"
            
            # Link to scene
            bpy.context.scene.collection.objects.link(obj)
        
        print(f"  ✓ Created {segment_index} cylinder meshes")
    @staticmethod
    def _distance(p1: Tuple[float, float, float],
                 p2: Tuple[float, float, float]) -> float:
        """Calculate distance between two points"""
        return math.sqrt(sum((a - b)**2 for a, b in zip(p1, p2)))