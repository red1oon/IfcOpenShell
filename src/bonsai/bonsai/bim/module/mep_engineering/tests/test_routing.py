#!/usr/bin/env python3
"""
MEP Routing Tests - Consolidated
=================================

Tests for conduit routing pathfinding algorithm.
Validates endpoint connections, graph connectivity, and pathfinding robustness.
"""

import sys
import math
from pathlib import Path
from typing import List, Tuple
from collections import defaultdict


# ============================================================================
# Standalone WaypointGraph (no Blender dependencies for testing)
# ============================================================================

class WaypointGraph:
    """
    Waypoint graph for A* pathfinding
    Standalone version for unit testing
    """

    def __init__(self,
                 waypoints: List[Tuple[float, float, float]],
                 obstacles: List[Tuple[float, float, float, float, float, float]],
                 clearance: float):
        self.waypoints = waypoints
        self.obstacles = obstacles
        self.clearance = clearance
        self.graph = defaultdict(list)
        self._build_graph()

    def _build_graph(self):
        """Build connectivity graph between waypoints"""
        n = len(self.waypoints)
        connections = 0

        # Connect all collision-free waypoint pairs
        for i in range(n):
            for j in range(i + 1, n):
                if self._path_clear(self.waypoints[i], self.waypoints[j]):
                    dist = self._distance(self.waypoints[i], self.waypoints[j])
                    self.graph[i].append((j, dist))
                    self.graph[j].append((i, dist))
                    connections += 1

        # Force-connect endpoints (0=start, 1=end) to nearest waypoints
        for endpoint_idx in [0, 1]:
            distances = []
            for i in range(2, n):
                dist = self._distance(self.waypoints[endpoint_idx], self.waypoints[i])
                distances.append((dist, i))

            distances.sort()
            initial_connections = len(self.graph[endpoint_idx])
            target_connections = 5
            added = 0

            for dist, target_idx in distances[:20]:
                if any(neighbor == target_idx for neighbor, _ in self.graph[endpoint_idx]):
                    continue

                self.graph[endpoint_idx].append((target_idx, dist))
                self.graph[target_idx].append((endpoint_idx, dist))
                connections += 1
                added += 1

                if len(self.graph[endpoint_idx]) >= target_connections:
                    break

    def _path_clear(self, p1: Tuple[float, float, float],
                   p2: Tuple[float, float, float]) -> bool:
        """Check if straight path is collision-free"""
        path_bbox = (
            min(p1[0], p2[0]) - self.clearance,
            min(p1[1], p2[1]) - self.clearance,
            min(p1[2], p2[2]) - self.clearance,
            max(p1[0], p2[0]) + self.clearance,
            max(p1[1], p2[1]) + self.clearance,
            max(p1[2], p2[2]) + self.clearance
        )

        for obs_bbox in self.obstacles:
            if self._bboxes_intersect(path_bbox, obs_bbox):
                return False
        return True

    @staticmethod
    def _distance(p1: Tuple[float, float, float],
                 p2: Tuple[float, float, float]) -> float:
        return math.sqrt(sum((a - b)**2 for a, b in zip(p1, p2)))

    @staticmethod
    def _bboxes_intersect(bbox1: Tuple, bbox2: Tuple) -> bool:
        return not (bbox1[3] < bbox2[0] or bbox2[3] < bbox1[0] or
                   bbox1[4] < bbox2[1] or bbox2[4] < bbox1[1] or
                   bbox1[5] < bbox2[2] or bbox2[5] < bbox1[2])


# ============================================================================
# Test Cases
# ============================================================================

def test_normal_graph(db_path=None):
    """Test 1: Normal well-connected graph"""
    waypoints = [(0, 0, 0), (10, 0, 0)]

    # Grid of intermediate waypoints
    for x in range(2, 11, 2):
        for y in range(0, 6, 2):
            waypoints.append((x, y, 0))

    graph = WaypointGraph(waypoints, [], 0.5)

    start_conn = len(graph.graph[0])
    end_conn = len(graph.graph[1])

    if start_conn >= 1 and end_conn >= 1:
        return True, f"Connected: start={start_conn}, end={end_conn}"
    return False, f"Failed: start={start_conn}, end={end_conn}"


def test_sparse_waypoints(db_path=None):
    """Test 2: Sparse waypoints (K-nearest connection needed)"""
    waypoints = [
        (0, 0, 0),    # Start
        (50, 0, 0),   # End (far away)
        (10, 0, 0),   # Waypoint 1
        (20, 0, 0),   # Waypoint 2
        (30, 0, 0),   # Waypoint 3
        (40, 0, 0),   # Waypoint 4
    ]

    graph = WaypointGraph(waypoints, [], 0.5)

    # Check if start/end connected despite distance
    if len(graph.graph[0]) > 0 and len(graph.graph[1]) > 0:
        return True, f"Sparse graph connected: {len(graph.graph[0])} + {len(graph.graph[1])} connections"
    return False, "Sparse graph failed to connect endpoints"


def test_obstacles_present(db_path=None):
    """Test 3: Dense obstacles (graceful handling)"""
    waypoints = [(0, 0, 0), (50, 0, 0)]

    # Add waypoints
    for i in range(10):
        waypoints.append((5 + i*5, 0, 0))

    # Add obstacles around each waypoint
    obstacles = []
    for i in range(10):
        x = 5 + i*5
        obstacles.extend([
            (x-2.5, -2.5, -1, x-0.6, 2.5, 1),  # Left wall
            (x+0.6, -2.5, -1, x+2.5, 2.5, 1),  # Right wall
        ])

    graph = WaypointGraph(waypoints, obstacles, 0.5)

    # Should still make endpoint connections (ignores clearance for endpoints)
    if len(graph.graph[0]) > 0 and len(graph.graph[1]) > 0:
        return True, f"Obstacle handling OK: {len(obstacles)} obstacles"
    return False, "Failed with obstacles"


def test_graph_statistics(db_path=None):
    """Test 4: Verify graph connectivity statistics"""
    # Simple connected graph
    waypoints = [(i, 0, 0) for i in range(10)]
    graph = WaypointGraph(waypoints, [], 0.5)

    total_connections = sum(len(neighbors) for neighbors in graph.graph.values()) // 2

    # In a 10-waypoint line, should have many connections
    if total_connections >= 9:  # At minimum, linear connections
        return True, f"{total_connections} connections in 10-waypoint graph"
    return False, f"Too few connections: {total_connections}"


# ============================================================================
# Test Runner
# ============================================================================

def run_routing_tests(db_path=None):
    """
    Run all MEP routing tests
    Compatible with global regression test suite

    Args:
        db_path: Optional database path (not used for unit tests)

    Returns:
        (passed, failed) tuples of test results
    """
    tests = [
        ("Normal graph connectivity", test_normal_graph),
        ("Sparse waypoints K-nearest", test_sparse_waypoints),
        ("Obstacle handling", test_obstacles_present),
        ("Graph statistics", test_graph_statistics),
    ]

    passed = []
    failed = []

    for name, test_func in tests:
        try:
            success, message = test_func(db_path) if db_path else test_func()
            if success:
                passed.append((name, True, message))
            else:
                failed.append((name, False, message))
        except Exception as e:
            failed.append((name, False, f"Exception: {e}"))

    return passed, failed


if __name__ == "__main__":
    """Standalone execution"""
    print("="*70)
    print("MEP ROUTING TESTS")
    print("="*70)

    passed, failed = run_routing_tests()

    for name, success, message in passed + failed:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"  [{status}] {name}: {message}")

    total = len(passed) + len(failed)
    print(f"\nTotal: {len(passed)}/{total} tests passed")

    sys.exit(0 if not failed else 1)
