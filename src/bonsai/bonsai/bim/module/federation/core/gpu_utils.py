# Bonsai - OpenBIM Blender Add-on
# Copyright (C) 2025 Iktisas IT Sdn Bhd
#
# GPU Utilities - NumPy/CuPy abstraction for NVIDIA acceleration
# Provides transparent fallback when CUDA is unavailable

"""
GPU-Accelerated Utilities for Federation Module
================================================

This module provides vectorized operations that automatically use:
- CuPy (GPU) when NVIDIA CUDA is available
- NumPy (CPU) as fallback

Usage:
    from .core.gpu_utils import xp, to_numpy, batch_bbox_intersect

Key Functions:
- batch_distance_matrix: Compute all pairwise distances (GPU-accelerated)
- batch_bbox_intersect: Check many bboxes against obstacles (GPU-accelerated)
- batch_point_in_bbox: Check many points against many bboxes (GPU-accelerated)
"""

import numpy as np

# Try to import CuPy for GPU acceleration
GPU_AVAILABLE = False
try:
    import cupy as cp
    # Test if CUDA actually works
    cp.cuda.runtime.getDeviceCount()
    GPU_AVAILABLE = True
    xp = cp  # Use CuPy
    print("✓ GPU acceleration enabled (CuPy + CUDA)")
except (ImportError, Exception) as e:
    xp = np  # Fallback to NumPy
    cp = None
    # Only print on first import
    import sys
    if 'gpu_utils_warned' not in dir(sys.modules[__name__]):
        print(f"ℹ GPU acceleration unavailable, using CPU (NumPy)")
        sys.modules[__name__].gpu_utils_warned = True


def to_numpy(arr):
    """Convert CuPy array to NumPy (no-op if already NumPy)"""
    if GPU_AVAILABLE and hasattr(arr, 'get'):
        return arr.get()
    return arr


def to_gpu(arr):
    """Convert NumPy array to GPU (no-op if CuPy unavailable)"""
    if GPU_AVAILABLE:
        return cp.asarray(arr)
    return arr


def batch_distance_matrix(points):
    """
    Compute pairwise Euclidean distance matrix for all points.

    GPU-accelerated when available.

    Args:
        points: List of (x, y, z) tuples or Nx3 array

    Returns:
        NxN distance matrix as NumPy array
    """
    points_arr = xp.array(points, dtype=xp.float32)
    n = len(points_arr)

    # Vectorized distance calculation: ||a - b||² = ||a||² + ||b||² - 2*a·b
    # This avoids explicit loops and is GPU-friendly
    sq_norms = xp.sum(points_arr ** 2, axis=1)

    # Broadcast: sq_norms[i] + sq_norms[j] - 2 * dot(points[i], points[j])
    dist_sq = sq_norms[:, xp.newaxis] + sq_norms[xp.newaxis, :] - 2 * xp.dot(points_arr, points_arr.T)

    # Clamp negative values (numerical precision) and sqrt
    dist_sq = xp.maximum(dist_sq, 0)
    distances = xp.sqrt(dist_sq)

    return to_numpy(distances)


def batch_k_nearest(points, k=15):
    """
    Find K nearest neighbors for each point.

    GPU-accelerated when available.

    Args:
        points: List of (x, y, z) tuples or Nx3 array
        k: Number of neighbors to find

    Returns:
        (indices, distances) - both NxK arrays
        indices[i] contains the K nearest neighbor indices for point i
        distances[i] contains the corresponding distances
    """
    dist_matrix = batch_distance_matrix(points)
    dist_matrix = to_gpu(dist_matrix) if GPU_AVAILABLE else dist_matrix

    n = len(dist_matrix)
    k = min(k, n - 1)

    # Set diagonal to infinity so point doesn't match itself
    if GPU_AVAILABLE:
        cp.fill_diagonal(dist_matrix, cp.inf)
    else:
        np.fill_diagonal(dist_matrix, np.inf)

    # Get K smallest indices per row
    if GPU_AVAILABLE:
        # CuPy argpartition
        indices = cp.argpartition(dist_matrix, k, axis=1)[:, :k]
        # Get actual distances for these indices
        row_idx = cp.arange(n)[:, cp.newaxis]
        distances = dist_matrix[row_idx, indices]
        # Sort by distance
        sort_idx = cp.argsort(distances, axis=1)
        indices = cp.take_along_axis(indices, sort_idx, axis=1)
        distances = cp.take_along_axis(distances, sort_idx, axis=1)
    else:
        indices = np.argpartition(dist_matrix, k, axis=1)[:, :k]
        row_idx = np.arange(n)[:, np.newaxis]
        distances = dist_matrix[row_idx, indices]
        sort_idx = np.argsort(distances, axis=1)
        indices = np.take_along_axis(indices, sort_idx, axis=1)
        distances = np.take_along_axis(distances, sort_idx, axis=1)

    return to_numpy(indices), to_numpy(distances)


def batch_bbox_intersect(path_bboxes, obstacle_bboxes):
    """
    Check which paths intersect which obstacles.

    GPU-accelerated batch AABB intersection test.

    Args:
        path_bboxes: Mx6 array of path bboxes (min_x, min_y, min_z, max_x, max_y, max_z)
        obstacle_bboxes: Nx6 array of obstacle bboxes

    Returns:
        MxN boolean array where True means intersection
    """
    paths = xp.array(path_bboxes, dtype=xp.float32)
    obstacles = xp.array(obstacle_bboxes, dtype=xp.float32)

    m = len(paths)
    n = len(obstacles)

    # Extract min/max for each axis
    # paths: [m, 6] -> min_x, min_y, min_z, max_x, max_y, max_z
    # obstacles: [n, 6]

    # Broadcast comparison: paths[m, 1, 6] vs obstacles[1, n, 6]
    paths = paths[:, xp.newaxis, :]  # [m, 1, 6]
    obstacles = obstacles[xp.newaxis, :, :]  # [1, n, 6]

    # AABB intersection: NOT (separated on any axis)
    # Separated if: path_max < obs_min OR obs_max < path_min (for each axis)

    # X axis: paths[:,:,3] < obstacles[:,:,0] OR obstacles[:,:,3] < paths[:,:,0]
    sep_x = (paths[:, :, 3] < obstacles[:, :, 0]) | (obstacles[:, :, 3] < paths[:, :, 0])
    # Y axis
    sep_y = (paths[:, :, 4] < obstacles[:, :, 1]) | (obstacles[:, :, 4] < paths[:, :, 1])
    # Z axis
    sep_z = (paths[:, :, 5] < obstacles[:, :, 2]) | (obstacles[:, :, 5] < paths[:, :, 2])

    # Intersect if NOT separated on all axes
    intersects = ~(sep_x | sep_y | sep_z)

    return to_numpy(intersects)


def batch_point_in_bbox(points, bboxes, clearance=0.0):
    """
    Check which points are inside which bboxes (with clearance).

    GPU-accelerated.

    Args:
        points: Mx3 array of points
        bboxes: Nx6 array of bboxes
        clearance: Extra clearance to add around bboxes

    Returns:
        MxN boolean array where True means point is inside bbox+clearance
    """
    pts = xp.array(points, dtype=xp.float32)
    boxes = xp.array(bboxes, dtype=xp.float32)

    # Expand bboxes by clearance
    boxes[:, :3] -= clearance  # min coords
    boxes[:, 3:] += clearance  # max coords

    # Broadcast: pts[m, 1, 3] vs boxes[1, n, 6]
    pts = pts[:, xp.newaxis, :]  # [m, 1, 3]
    boxes = boxes[xp.newaxis, :, :]  # [1, n, 6]

    # Point inside if: min <= point <= max for all axes
    inside_x = (pts[:, :, 0] >= boxes[:, :, 0]) & (pts[:, :, 0] <= boxes[:, :, 3])
    inside_y = (pts[:, :, 1] >= boxes[:, :, 1]) & (pts[:, :, 1] <= boxes[:, :, 4])
    inside_z = (pts[:, :, 2] >= boxes[:, :, 2]) & (pts[:, :, 2] <= boxes[:, :, 5])

    inside = inside_x & inside_y & inside_z

    return to_numpy(inside)


def batch_paths_clear(start_points, end_points, obstacles, clearance):
    """
    Check if paths between start/end point pairs are collision-free.

    GPU-accelerated.

    Args:
        start_points: Mx3 array of start points
        end_points: Mx3 array of end points
        obstacles: Nx6 array of obstacle bboxes
        clearance: Clearance distance

    Returns:
        M-length boolean array where True means path is clear
    """
    starts = xp.array(start_points, dtype=xp.float32)
    ends = xp.array(end_points, dtype=xp.float32)

    # Build path bboxes with clearance
    min_coords = xp.minimum(starts, ends) - clearance
    max_coords = xp.maximum(starts, ends) + clearance

    path_bboxes = xp.concatenate([min_coords, max_coords], axis=1)

    # Check intersections
    intersects = batch_bbox_intersect(to_numpy(path_bboxes), obstacles)

    # Path is clear if it doesn't intersect ANY obstacle
    path_clear = ~xp.any(to_gpu(intersects) if GPU_AVAILABLE else intersects, axis=1)

    return to_numpy(path_clear)


def vectorized_sample_waypoints(bounds, obstacles, clearance, num_samples=200, max_attempts=2000):
    """
    Sample free-space waypoints using vectorized rejection sampling.

    GPU-accelerated when available.

    Args:
        bounds: (min_x, min_y, min_z, max_x, max_y, max_z)
        obstacles: List of obstacle bboxes
        clearance: Clearance distance
        num_samples: Target number of waypoints
        max_attempts: Maximum sampling attempts

    Returns:
        List of (x, y, z) tuples in free space
    """
    obs_arr = np.array(obstacles, dtype=np.float32)

    # Generate all random points at once
    rng = np.random.default_rng()
    all_points = np.column_stack([
        rng.uniform(bounds[0], bounds[3], max_attempts),
        rng.uniform(bounds[1], bounds[4], max_attempts),
        rng.uniform(bounds[2], bounds[5], max_attempts)
    ]).astype(np.float32)

    # Batch check which points are in free space
    inside_any = batch_point_in_bbox(all_points, obs_arr, clearance)

    # Point is free if not inside ANY obstacle
    free_mask = ~np.any(inside_any, axis=1)

    # Get free points
    free_points = all_points[free_mask]

    # Limit to num_samples
    if len(free_points) > num_samples:
        free_points = free_points[:num_samples]

    return [tuple(p) for p in free_points]


# Performance profiling helper
def benchmark_gpu():
    """Quick benchmark to verify GPU acceleration is working"""
    import time

    # Generate test data
    n_points = 1000
    n_obstacles = 100

    points = np.random.rand(n_points, 3).astype(np.float32) * 100
    obstacles = np.random.rand(n_obstacles, 6).astype(np.float32)
    obstacles[:, 3:] = obstacles[:, :3] + 5  # Ensure max > min

    # Benchmark distance matrix
    start = time.perf_counter()
    dist = batch_distance_matrix(points)
    t_dist = time.perf_counter() - start

    # Benchmark K-nearest
    start = time.perf_counter()
    idx, dists = batch_k_nearest(points, k=15)
    t_knn = time.perf_counter() - start

    # Benchmark point-in-bbox
    start = time.perf_counter()
    inside = batch_point_in_bbox(points, obstacles, clearance=0.5)
    t_pib = time.perf_counter() - start

    backend = "GPU (CuPy)" if GPU_AVAILABLE else "CPU (NumPy)"
    print(f"\n📊 GPU Utils Benchmark ({backend}):")
    print(f"   Distance matrix ({n_points}×{n_points}): {t_dist*1000:.1f}ms")
    print(f"   K-nearest (K=15): {t_knn*1000:.1f}ms")
    print(f"   Point-in-bbox ({n_points}×{n_obstacles}): {t_pib*1000:.1f}ms")

    return {
        'backend': backend,
        'distance_matrix_ms': t_dist * 1000,
        'k_nearest_ms': t_knn * 1000,
        'point_in_bbox_ms': t_pib * 1000
    }
