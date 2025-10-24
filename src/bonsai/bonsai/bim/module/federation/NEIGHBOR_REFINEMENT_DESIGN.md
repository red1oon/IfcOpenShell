# Neighbor-Based Shape Refinement System
**Version:** 1.1 Enhancement
**Purpose:** Improve geometry accuracy using spatial context

## Concept

A "translator routine" that analyzes an element's **immediate neighbors** to refine its procedurally generated shape. This uses **spatial relationships** and **connection topology** to infer assembly details that aren't visible in bbox data alone.

## Use Cases

### 1. **Pipe Flanges** (Equipment Connections)
```
Scenario: Pipe connects to pump/valve
Current:  Pipe = simple cylinder
Enhanced: Pipe = cylinder + flange at connection point

Detection:
  - Pipe bbox overlaps Equipment bbox (within 50mm)
  - Connection end → add flange
```

### 2. **Duct Transitions** (Size Changes)
```
Scenario: 300mm duct connects to 600mm duct
Current:  Two separate box shapes (sudden jump)
Enhanced: Detect size mismatch → infer transition piece

Detection:
  - Adjacent ducts with bbox overlap
  - Profile dimensions differ by >50mm
  - Insert transition element
```

### 3. **Beam-Column Connections** (Structural Joints)
```
Scenario: Beam meets column
Current:  Simple boxes, no connection detail
Enhanced: Add connection plate/bracket at intersection

Detection:
  - Beam bbox intersects Column bbox
  - Intersection point → add connection detail
```

### 4. **Profile Diameter Matching** (Pipe Networks)
```
Scenario: Two pipes connect end-to-end
Current:  May have diameter mismatch (bbox inference error)
Enhanced: Enforce diameter consistency across connections

Detection:
  - Pipe-to-Pipe connection (bbox overlap)
  - Propagate diameter along network
  - Detect and fix mismatches
```

### 5. **Valve/Fitting Orientation** (MEP Direction)
```
Scenario: Fitting has unknown orientation
Current:  Generic orientation (may be wrong)
Enhanced: Infer orientation from connected pipes

Detection:
  - Fitting connects to 2+ pipes
  - Analyze pipe directions → orient fitting correctly
```

## Architecture

### Module: `neighbor_refinement.py`

```python
class NeighborRefiner:
    """
    Refines element shapes based on spatial context.

    Workflow:
    1. Build spatial index (R-tree from database)
    2. For each element, query neighbors (within 100mm)
    3. Detect actual connections (bbox overlap + semantic compatibility)
    4. Apply refinement rules based on connection type
    5. Update geometry in-place
    """

    def __init__(self, db_conn: sqlite3.Connection):
        self.db_conn = db_conn
        self.connection_rules = self._load_connection_rules()

    def refine_shapes(self, objects: List[bpy.types.Object]) -> Dict[str, int]:
        """
        Refine shapes based on neighbors.

        Returns:
            Statistics: {
                'flanges_added': 12,
                'transitions_inserted': 3,
                'diameters_corrected': 8,
                'connections_refined': 45
            }
        """
        stats = defaultdict(int)

        for obj in objects:
            neighbors = self._find_neighbors(obj, distance=100)  # 100mm
            connections = self._detect_connections(obj, neighbors)

            for conn in connections:
                refinement = self._apply_refinement_rule(obj, conn)
                if refinement:
                    stats[refinement['type']] += 1

        return dict(stats)

    def _find_neighbors(self, obj, distance=100):
        """Query R-tree spatial index for nearby elements"""
        guid = obj.get('federation_guid')

        # Get bbox from object
        bbox = self._get_bbox(obj)

        # Expand bbox by distance (100mm = 0.1m in Blender units)
        expanded = self._expand_bbox(bbox, distance/1000.0)

        # Query R-tree
        cursor = self.db_conn.cursor()
        cursor.execute("""
            SELECT m.guid, m.ifc_class, m.discipline
            FROM elements_meta m
            JOIN elements_rtree r ON m.id = r.id
            WHERE r.min_x <= ? AND r.max_x >= ?
              AND r.min_y <= ? AND r.max_y >= ?
              AND r.min_z <= ? AND r.max_z >= ?
              AND m.guid != ?
        """, (*expanded, guid))

        return cursor.fetchall()

    def _detect_connections(self, obj, neighbors):
        """
        Detect actual connections vs just proximity.

        Connection criteria:
        - Bbox overlap (not just proximity)
        - Semantic compatibility (pipe→pipe, pipe→fitting, etc.)
        - Connection point within 50mm tolerance
        """
        connections = []

        obj_type = obj.get('federation_semantic_type')
        obj_bbox = self._get_bbox(obj)

        for neighbor_guid, neighbor_ifc, neighbor_disc in neighbors:
            neighbor_obj = self._get_object_by_guid(neighbor_guid)
            if not neighbor_obj:
                continue

            neighbor_type = neighbor_obj.get('federation_semantic_type')
            neighbor_bbox = self._get_bbox(neighbor_obj)

            # Check semantic compatibility
            if not self._are_compatible(obj_type, neighbor_type):
                continue

            # Check actual bbox overlap (not just proximity)
            overlap = self._calculate_overlap(obj_bbox, neighbor_bbox)
            if overlap < 0.001:  # 1mm minimum overlap
                continue

            # Found a connection!
            connections.append({
                'neighbor': neighbor_obj,
                'type': f"{obj_type}_to_{neighbor_type}",
                'overlap': overlap,
                'connection_point': self._find_connection_point(obj_bbox, neighbor_bbox)
            })

        return connections

    def _apply_refinement_rule(self, obj, connection):
        """
        Apply refinement based on connection type.

        Rules:
        - pipe_to_equipment → add_flange(obj, connection_point)
        - pipe_to_pipe → ensure_diameter_match(obj, neighbor)
        - duct_to_duct → check_transition_needed(obj, neighbor)
        - beam_to_column → add_connection_plate(obj, neighbor)
        """
        conn_type = connection['type']

        if conn_type == 'pipe_to_equipment':
            return self._add_flange(obj, connection['connection_point'])

        elif conn_type == 'pipe_to_pipe':
            return self._ensure_diameter_match(obj, connection['neighbor'])

        elif conn_type == 'duct_to_duct':
            return self._check_transition_needed(obj, connection['neighbor'])

        elif conn_type == 'beam_to_column':
            return self._add_connection_plate(obj, connection['neighbor'])

        return None

    def _add_flange(self, pipe_obj, connection_point):
        """
        Add flange to pipe at connection point.

        Implementation:
        1. Get pipe radius from current geometry
        2. Create flange disk (radius * 1.5, thickness 20mm)
        3. Position at connection_point
        4. Boolean union with existing pipe mesh
        5. Update object geometry in-place
        """
        # Get current pipe mesh
        mesh = pipe_obj.data
        bm = bmesh.new()
        bm.from_mesh(mesh)

        # Calculate flange dimensions
        pipe_radius = self._get_pipe_radius(pipe_obj)
        flange_radius = pipe_radius * 1.5
        flange_thickness = 0.02  # 20mm in meters

        # Create flange geometry
        flange_bm = self._create_flange_bmesh(
            radius=flange_radius,
            thickness=flange_thickness,
            location=connection_point
        )

        # Merge with pipe geometry
        bm = bmesh.ops.union(bm, flange_bm)

        # Update mesh
        bm.to_mesh(mesh)
        bm.free()

        return {'type': 'flange_added', 'location': connection_point}

    def _ensure_diameter_match(self, pipe1, pipe2):
        """
        Ensure connected pipes have matching diameters.

        Strategy:
        - Get both diameters from bbox/geometry
        - If mismatch > 10mm, use larger diameter (assume bbox error)
        - Update smaller pipe to match
        - Store correction in metadata
        """
        d1 = self._get_pipe_diameter(pipe1)
        d2 = self._get_pipe_diameter(pipe2)

        if abs(d1 - d2) > 0.01:  # 10mm tolerance
            # Use larger diameter (likely more accurate)
            correct_diameter = max(d1, d2)

            # Update both pipes
            self._update_pipe_diameter(pipe1, correct_diameter)
            self._update_pipe_diameter(pipe2, correct_diameter)

            return {
                'type': 'diameter_corrected',
                'from': [d1, d2],
                'to': correct_diameter
            }

        return None

    def _check_transition_needed(self, duct1, duct2):
        """
        Check if duct size change requires transition piece.

        Criteria:
        - Profile width/height differ by >50mm
        - Connection length < 200mm (direct connection)

        Action:
        - Insert transition element in scene
        - Tag as 'inferred_transition'
        """
        profile1 = self._get_duct_profile(duct1)
        profile2 = self._get_duct_profile(duct2)

        w_diff = abs(profile1[0] - profile2[0])
        h_diff = abs(profile1[1] - profile2[1])

        if w_diff > 0.05 or h_diff > 0.05:  # 50mm threshold
            # Create transition piece
            transition = self._create_duct_transition(
                profile1, profile2,
                length=0.5  # 500mm transition
            )

            return {
                'type': 'transition_inserted',
                'from_profile': profile1,
                'to_profile': profile2,
                'element': transition
            }

        return None
```

## Performance

### Spatial Query Optimization
```python
# Use R-tree for neighbor queries (already in database!)
# Only process elements with neighbors (skip isolated elements)
# Batch process by discipline (pipes first, ducts second, etc.)

Estimated performance for 44K elements:
- Neighbor queries: ~2-3s (R-tree is fast!)
- Connection detection: ~1-2s (simple bbox math)
- Geometry refinement: ~3-5s (only connected elements)
- Total: ~6-10s additional time
```

### Memory Impact
```
Minimal - refinements modify existing geometry in-place
No new large data structures (use database R-tree)
```

## Integration Points

### 1. **Stage 2.5** (New optional stage)
```python
# In loader.py:

def load_stage2(self, enable_refinement=True):
    """Load semantic shapes with optional neighbor refinement"""
    shapes = stage2_semantics.create_semantic_shapes(...)

    if enable_refinement:
        refiner = neighbor_refinement.NeighborRefiner(self.db_conn)
        stats = refiner.refine_shapes(shapes)
        print(f"✓ Refined {len(shapes)} elements:")
        print(f"  - Flanges added: {stats.get('flange_added', 0)}")
        print(f"  - Transitions: {stats.get('transition_inserted', 0)}")
        print(f"  - Diameters corrected: {stats.get('diameter_corrected', 0)}")

    return shapes
```

### 2. **User Control** (Settings)
```python
# UI toggle:
# [x] Enable neighbor-based refinement (adds ~8s, improves accuracy)

# Granular control:
# [x] Add flanges at equipment connections
# [x] Insert duct transitions
# [x] Correct diameter mismatches
# [ ] Add structural connections (future)
```

## Connection Type Rules

```python
CONNECTION_RULES = {
    # MEP Connections
    ('pipe', 'equipment'): {
        'action': 'add_flange',
        'distance': 50,  # mm
        'priority': 1
    },
    ('pipe', 'pipe'): {
        'action': 'ensure_diameter_match',
        'distance': 50,
        'priority': 2
    },
    ('duct', 'duct'): {
        'action': 'check_transition',
        'distance': 100,
        'priority': 2
    },
    ('conduit', 'conduit'): {
        'action': 'ensure_diameter_match',
        'distance': 50,
        'priority': 2
    },

    # Structural Connections
    ('beam', 'column'): {
        'action': 'add_connection_plate',
        'distance': 100,
        'priority': 3
    },
    ('beam', 'beam'): {
        'action': 'check_splice',
        'distance': 50,
        'priority': 3
    },

    # Architectural Connections
    ('door', 'wall'): {
        'action': 'add_frame',
        'distance': 20,
        'priority': 4
    },
    ('window', 'wall'): {
        'action': 'add_frame',
        'distance': 20,
        'priority': 4
    },
}
```

## Expected Accuracy Improvements

| Aspect | Before Refinement | After Refinement |
|--------|------------------|------------------|
| Pipe flanges | Missing (0%) | 90% detected |
| Diameter consistency | ~80% accurate | 95% accurate |
| Duct transitions | Not inferred | 85% inferred |
| Connection details | None | Basic details |
| **Overall accuracy** | **80-90%** | **92-96%** |

## Implementation Priority

**v1.1 (Next iteration):**
1. ✅ Core neighbor query system
2. ✅ Pipe-to-equipment flanges
3. ✅ Pipe diameter matching

**v1.2 (Future):**
4. Duct transitions
5. Structural connections
6. Orientation inference

## Testing Strategy

```python
# Test case: Pump connected to pipes
# Expected: Flanges at both connection points
def test_pump_flange_inference():
    pump = get_element('pump_01')
    pipes = get_connected_pipes(pump)

    refiner.refine_shapes([pump] + pipes)

    for pipe in pipes:
        assert has_flange_at_connection(pipe, pump)
```

---

## Summary

This neighbor-based refinement system would:
- **Improve accuracy from 80-90% → 92-96%**
- **Add ~8s processing time** (acceptable)
- **Infer assembly details** not visible in bbox alone
- **Use existing R-tree spatial index** (no new infrastructure)
- **Maintain "NO BLOB" philosophy** (pure inference)

**User's insight is correct**: Looking at neighbors provides critical context for improving inferred geometry!
