# Bonsai - OpenBIM Blender Add-on
# Copyright (C) 2025 Iktisas IT Sdn Bhd
#
# This file is part of Bonsai.
#
# Bonsai is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
MEP Engineering Operators - REFACTORED
Thin operators that validate input and call tool.py business logic
Federation module integration preserved
"""

import bpy
from bpy.types import Operator
from . import visualization
from . import tool


class TestMEPOperator(Operator):
    """Test operator to verify MEP module is working"""
    bl_idname = "bim.test_mep_operator"
    bl_label = "Test MEP Module"
    bl_description = "Test that MEP Engineering module is loaded"
    bl_options = {"REGISTER", "UNDO"}
    
    def execute(self, context):
        """Called when operator is executed"""
        props = context.scene.BIMmepEngineeringProperties
        
        self.report({'INFO'}, f"MEP Module Working! Project: {props.project_number}")
        
        print("=" * 50)
        print("MEP Engineering Module Test")
        print(f"Project Number: {props.project_number}")
        print(f"Clash Detection: {props.enable_clash_detection}")
        print(f"Min Clearance: {props.min_clearance_mm}mm")
        print("=" * 50)
        
        return {"FINISHED"}


# ============================================================================
# ROUTING OPERATORS - Now using tool.py
# ============================================================================

class RouteMEPConduit(Operator):
    """Route MEP conduit using federation obstacle detection"""
    bl_idname = "bim.route_mep_conduit"
    bl_label = "Route Conduit"
    bl_description = "Route conduit from start to end point, avoiding obstacles from federated models"
    bl_options = {"REGISTER", "UNDO"}
    
    def execute(self, context):
        """Execute conduit routing - THIN, validates and calls tool.py"""
        mep_props = context.scene.BIMmepEngineeringProperties
        fed_props = context.scene.BIMFederationProperties
        
        # Validate federation is loaded
        if not fed_props.index_loaded:
            self.report({'WARNING'}, 
                       "Federation index not loaded. Load federation first from Quality Control tab.")
            return {"CANCELLED"}
        
        # Get parameters
        start = tuple(mep_props.route_start_point)
        end = tuple(mep_props.route_end_point)
        clearance = mep_props.clearance_distance
        diameter = mep_props.conduit_diameter
        
        # Validate points are set
        if start == (0.0, 0.0, 0.0) or end == (0.0, 0.0, 0.0):
            self.report({'ERROR'}, "Set start and end points first")
            return {"CANCELLED"}
        
        # Get federation index from WindowManager
        if not hasattr(bpy.types.WindowManager, 'federation_index'):
            self.report({'ERROR'}, "Federation index not found in memory")
            return {"CANCELLED"}
        
        index = bpy.types.WindowManager.federation_index
        
        # Query obstacles along corridor using federation
        try:
            # Filter to essential blocking disciplines only (not FP, SP, CW)
            disciplines = ['STR', 'ACMV']  # Structural, mechanical only, not avoid architectural
            
            obstacles = index.query_corridor(
                start=start,
                end=end,
                buffer=clearance,
                disciplines=disciplines
            )
            
            self.report({'INFO'}, f"Found {len(obstacles)} obstacles")
            
            # DEDUPLICATION CHECK (NEW)
            print(f"\n{'='*70}")
            print(f"OBSTACLE INVENTORY CHECK")
            print(f"{'='*70}")
            
            from collections import defaultdict
            unique_obstacles = []
            seen_bboxes = set()
            duplicates = 0
            
            for obs in obstacles:
                # Create hashable key from bbox (rounded to 0.01m precision)
                bbox_key = tuple(round(x, 2) for x in obs.bbox)
                
                if bbox_key not in seen_bboxes:
                    unique_obstacles.append(obs)
                    seen_bboxes.add(bbox_key)
                else:
                    duplicates += 1
            
            print(f"Original obstacles: {len(obstacles)}")
            print(f"Unique obstacles: {len(unique_obstacles)}")
            print(f"Duplicates removed: {duplicates}")
            
            if duplicates > 0:
                print(f"  ⚠️  Found duplicates - using deduplicated set")
                obstacles = unique_obstacles
                print(f"  ℹ️  This likely means elements are in multiple source IFC files")
            
            # Obstacle breakdown by discipline
            from collections import Counter
            discipline_counts = Counter(obs.discipline for obs in obstacles)
            print(f"\nObstacles by discipline:")
            for disc in sorted(discipline_counts.keys()):
                print(f"  {disc}: {discipline_counts[disc]}")
            
            print(f"{'='*70}\n")
            # Store only the bboxes (tuples of floats)
            context.scene["MEP_filtered_obstacles"] = [obs.bbox for obs in obstacles]
            # Convert FederationElement to bbox tuples
            obstacle_bboxes = [obs.bbox for obs in obstacles]
            
            # DEBUG: Analyze obstacles near start point
            print(f"\n  Analyzing obstacles near start point {start}:")
            import math
            start_distances = []
            for obs in obstacles[:10]:
                bbox = obs.bbox
                min_x, min_y, min_z, max_x, max_y, max_z = bbox
                center = ((min_x + max_x)/2, (min_y + max_y)/2, (min_z + max_z)/2)
                dist = math.sqrt(sum((s - c)**2 for s, c in zip(start, center)))
                size = (max_x - min_x, max_y - min_y, max_z - min_z)
                start_distances.append((dist, center, size))
            
            start_distances.sort(key=lambda x: x[0])
            for i, (dist, center, size) in enumerate(start_distances[:5]):
                print(f"    #{i+1}: {dist:.2f}m away, size: {size[0]:.1f}×{size[1]:.1f}×{size[2]:.1f}m")
            
            print(f"\n  Clearance requirement: {clearance}m")
            print(f"  Search radius for clear space: {clearance * 1.5:.2f}m")
            
        except Exception as e:
            self.report({'ERROR'}, f"Obstacle query failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"CANCELLED"}
        
        # CALL TOOL LAYER - Main refactoring change here!
        # Run pathfinding
        try:
            # Calculate and store offset for visualization (do this ONCE)
            # Find actual placed geometry (not types at origin or ghost elements)
            offset_x, offset_y, offset_z = 0.0, 0.0, 0.0
            
            for obj in bpy.data.objects:
                if obj.type == 'MESH' and 'Ifc' in obj.name:
                    # Skip type/style objects
                    if 'Style' in obj.name or 'Type' in obj.name:
                        continue
                    # Skip objects at or very near origin (ghosts/types)
                    if abs(obj.location.x) < 1.0 and abs(obj.location.y) < 1.0 and abs(obj.location.z) < 1.0:
                        continue
                    # Skip objects that don't have IFC properties
                    if not hasattr(obj, 'BIMObjectProperties'):
                        continue
                    if not obj.BIMObjectProperties.ifc_definition_id:
                        continue
                    
                    # Found real placed IFC geometry!
                    offset_x = start[0] - obj.location.x
                    offset_y = start[1] - obj.location.y
                    offset_z = start[2] - obj.location.z
                    print(f"📍 Using reference object: {obj.name} at ({obj.location.x:.1f}, {obj.location.y:.1f}, {obj.location.z:.1f})")
                    break
            
            # Store in scene for reuse
            context.scene["MEP_cached_offset"] = (offset_x, offset_y, offset_z)
            print(f"📍 Cached offset: ({offset_x:.1f}, {offset_y:.1f}, {offset_z:.1f})")
            
            router = tool.ConduitRouter(federation_index=index)            
            waypoints = router.route(
                start=start,
                end=end,
                obstacles=obstacle_bboxes,
                clearance=clearance
            )
            
            if not waypoints:
                self.report({'ERROR'}, "No valid route found. Try adjusting clearance or points.")
                return {"CANCELLED"}
            
            self.report({'INFO'}, f"Route found with {len(waypoints)} waypoints")
            
            # Debug output
            print(f"Waypoints ({len(waypoints)}):")
            for i, wp in enumerate(waypoints):
                print(f"  {i}: ({wp[0]:.2f}, {wp[1]:.2f}, {wp[2]:.2f})")
            
            # Auto-clear old visualization before storing new route
            visualization.clear_debug_objects()
            
            # Store waypoints for visualization
            import json
            context.scene["MEP_last_route_waypoints"] = json.dumps(waypoints)
            print("✓ Waypoints stored for visualization")
            
            # Generate IFC geometry using tool
            import bonsai.tool as bonsai_tool
            ifc_file = bonsai_tool.Ifc.get()
            
            generator = tool.IFCGeometryGenerator()
            global_ids = generator.generate_conduit(ifc_file, waypoints, diameter)
            
            if not global_ids:
                self.report({'ERROR'}, "Failed to generate IFC geometry")
                return {"CANCELLED"}
            
            # Store GlobalIds for focus
            import json
            context.scene["MEP_last_conduit_ids"] = json.dumps(global_ids)
            
            self.report({'INFO'}, 
                       f"✓ Conduit route complete! Created {len(global_ids)} elements. "
                       "Click 'View Conduit Routing' to visualize.")
            self.report({'INFO'}, 
                       f"✓ Conduit route complete! Created {len(waypoints)-1} segments. "
                       "Click 'View Conduit Routing' to visualize.")
            
        except Exception as e:
            self.report({'ERROR'}, f"Pathfinding failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"CANCELLED"}
        
        return {"FINISHED"}


# ============================================================================
# POINT SETTING OPERATORS (unchanged - simple, no refactoring needed)
# ============================================================================

class SetRouteStartPoint(Operator):
    """Set route start point from 3D cursor"""
    bl_idname = "bim.set_route_start_point"
    bl_label = "Set Start Point"
    bl_description = "Set routing start point from 3D cursor location (in meters)"
    bl_options = {"REGISTER", "UNDO"}
    
    def execute(self, context):
        cursor_loc = context.scene.cursor.location
        mep_props = context.scene.BIMmepEngineeringProperties
        
        mep_props.route_start_point = cursor_loc
        
        self.report({'INFO'}, 
                   f"Start point set to ({cursor_loc.x:.2f}, {cursor_loc.y:.2f}, {cursor_loc.z:.2f})m")
        
        return {"FINISHED"}


class SetRouteEndPoint(Operator):
    """Set route end point from 3D cursor"""
    bl_idname = "bim.set_route_end_point"
    bl_label = "Set End Point"
    bl_description = "Set routing end point from 3D cursor location (in meters)"
    bl_options = {"REGISTER", "UNDO"}
    
    def execute(self, context):
        cursor_loc = context.scene.cursor.location
        mep_props = context.scene.BIMmepEngineeringProperties
        
        mep_props.route_end_point = cursor_loc
        
        self.report({'INFO'}, 
                   f"End point set to ({cursor_loc.x:.2f}, {cursor_loc.y:.2f}, {cursor_loc.z:.2f})m")
        
        return {"FINISHED"}


# ============================================================================
# VISUALIZATION OPERATORS (unchanged - uses visualization.py)
# ============================================================================

class VisualizeRoutingObstacles(Operator):
    """Visualize routing obstacles in 3D viewport"""
    bl_idname = "bim.visualize_routing_obstacles"
    bl_label = "Visualize Conduit"
    bl_description = "Show start/end points, obstacles, and clearance zones in 3D viewport"
    bl_options = {"REGISTER", "UNDO"}
    
    def execute(self, context):
        mep_props = context.scene.BIMmepEngineeringProperties
        fed_props = context.scene.BIMFederationProperties
        
        # Validate federation is loaded
        if not fed_props.index_loaded:
            self.report({'ERROR'}, "Federation index not loaded. Load federation first.")
            return {"CANCELLED"}
        
        # Get start/end points
        start = tuple(mep_props.route_start_point)
        end = tuple(mep_props.route_end_point)
        clearance = mep_props.clearance_distance
        
        # Validate points are set
        if start == (0.0, 0.0, 0.0) or end == (0.0, 0.0, 0.0):
            self.report({'ERROR'}, "Set start and end points first")
            return {"CANCELLED"}
        
        # Get federation index
        if not hasattr(bpy.types.WindowManager, 'federation_index'):
            self.report({'ERROR'}, "Federation index not found in memory")
            return {"CANCELLED"}
        
        index = bpy.types.WindowManager.federation_index
        
        # Query obstacles along corridor
        try:
            disciplines = [d.strip() for d in mep_props.target_disciplines.split(',') if d.strip()]
            
            # Reuse obstacles from routing (if available)
            if "MEP_filtered_obstacles" in context.scene:
                obstacle_bboxes = context.scene["MEP_filtered_obstacles"]
                # Note: these are already bbox tuples, not FederationElement objects
                print(f"✓ Using stored obstacles from routing: {len(obstacle_bboxes)}")
            else:
                # Fallback: query again
                obstacles = index.query_corridor(
                    start=start,
                    end=end,
                    buffer=clearance,
                    disciplines=disciplines if disciplines else None
                )
                obstacle_bboxes = [obs.bbox for obs in obstacles] 
                print(f"⚠️  No stored obstacles, queried: {len(obstacle_bboxes)}")
            self.report({'INFO'}, f"✓ Visualization created: {len(obstacle_bboxes)} obstacles shown") 
            
            # Clear previous visualization
            visualization.clear_debug_objects()
            waypoints = None
            if "MEP_last_route_waypoints" in context.scene:
                import json
                waypoints = json.loads(context.scene["MEP_last_route_waypoints"])
                print(f"✓ Retrieved {len(waypoints)} waypoints for visualization")
            # Create visualization
            created = visualization.visualize_routing_scenario(
                start=start,
                end=end,
                obstacles=obstacle_bboxes,
                clearance=clearance,
                waypoints=waypoints,
                show_clearance_zones=True,
                show_corridor=True
            )
            # Selection and viewport navigation handled by focus functions below

            # Auto-focus on path if it exists, otherwise show obstacles
            if waypoints and len(waypoints) > 2:
                # Path exists - focus on it
                visualization.focus_on_path()
                self.report({'INFO'}, 
                           f"✓ Path visualized: {len(waypoints)} waypoints")
            else:
                # No path - navigate to obstacles
                midpoint = (
                    (start[0] + end[0]) / 2,
                    (start[1] + end[1]) / 2,
                    (start[2] + end[2]) / 2
                )
                visualization.focus_on_obstacles
                visualization.navigate_to_view()
                self.report({'INFO'}, 
                           f"✓ Obstacles shown: {len(obstacle_bboxes)} elements")
            
        except Exception as e:
            self.report({'ERROR'}, f"Visualization failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"CANCELLED"}
        
        return {"FINISHED"}


class ClearRoutingDebug(Operator):
    """Clear all routing debug objects AND generated IFC conduits"""
    bl_idname = "bim.clear_routing_debug"
    bl_label = "Clear Route"
    bl_description = "Remove MEP debug visualization AND delete generated IFC conduit elements"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        import json
        import ifcopenshell.api
        import bonsai.tool as bonsai_tool

        # Clear visualization (existing behavior)
        visualization.clear_debug_objects()

        # NEW: Delete IFC conduit elements
        deleted_ifc = 0
        deleted_blender = 0

        if "MEP_last_conduit_ids" in context.scene:
            try:
                ifc_file = bonsai_tool.Ifc.get()
                global_ids = json.loads(context.scene["MEP_last_conduit_ids"])

                for guid in global_ids:
                    try:
                        element = ifc_file.by_guid(guid)
                        if element:
                            # Delete IFC element
                            ifcopenshell.api.run("root.remove_product", ifc_file, product=element)
                            deleted_ifc += 1

                            # Delete associated Blender object if it exists
                            for obj in bpy.data.objects:
                                if obj.BIMObjectProperties.ifc_definition_id == element.id():
                                    bpy.data.objects.remove(obj, do_unlink=True)
                                    deleted_blender += 1
                                    break
                    except RuntimeError:
                        pass

                del context.scene["MEP_last_conduit_ids"]

                self.report({'INFO'},
                           f"Cleared visualization, deleted {deleted_ifc} IFC elements and {deleted_blender} Blender objects")
            except Exception as e:
                self.report({'WARNING'},
                           f"Cleared visualization, but encountered error deleting IFC elements: {str(e)}")
                import traceback
                traceback.print_exc()
        else:
            self.report({'INFO'}, "Debug objects cleared (no IFC conduits to delete)")

        # Clear stored waypoints and obstacles
        if "MEP_last_route_waypoints" in context.scene:
            del context.scene["MEP_last_route_waypoints"]
        if "MEP_filtered_obstacles" in context.scene:
            del context.scene["MEP_filtered_obstacles"]
        if "MEP_cached_offset" in context.scene:
            del context.scene["MEP_cached_offset"]

        return {"FINISHED"}


# ============================================================================
# CLASH VALIDATION OPERATOR (unchanged - depends on federation)
# ============================================================================

class ValidateConduitRoute(Operator):
    """Validate generated conduit route against all disciplines using IfcClash"""
    bl_idname = "bim.validate_conduit_route"
    bl_label = "Validate Route"
    bl_description = "Check generated conduit for clashes with all disciplines"
    bl_options = {"REGISTER", "UNDO"}
    
    def execute(self, context):
        """Execute clash validation"""
        import tempfile
        import json
        from pathlib import Path
        
        mep_props = context.scene.BIMmepEngineeringProperties
        fed_props = context.scene.BIMFederationProperties
        
        # Check if route exists (must have generated conduit first)
        
        # Find recently created conduit elements
        electrical_system = None
        for system in ifc_file.by_type("IfcSystem"):
            if system.Name == "Electrical Distribution":
                electrical_system = system
                break
        
        if not electrical_system:
            self.report({'ERROR'}, "No conduit route found. Generate route first.")
            return {"CANCELLED"}
        
        # Get route elements
        import ifcopenshell.util.system
        route_elements = ifcopenshell.util.system.get_system_elements(electrical_system)
        
        if not route_elements:
            self.report({'ERROR'}, "Electrical system has no elements")
            return {"CANCELLED"}
        
        self.report({'INFO'}, f"Validating route with {len(route_elements)} segments...")
        
        # Run clash detection (uses federation obstacles)
        try:
            clashes = self._run_clash_detection(route_elements, fed_props)
            
            if not clashes:
                self.report({'INFO'}, "✓ No clashes detected! Route is clear.")
                return {"FINISHED"}
            
            # Report clashes
            self.report({'WARNING'}, f"Found {len(clashes)} clashes")
            
            if mep_props.show_clash_details:
                self._print_clash_details(clashes)
            
            if mep_props.export_bcf:
                bcf_path = self._export_bcf(clashes, context)
                self.report({'INFO'}, f"BCF exported to: {bcf_path}")
            
        except Exception as e:
            self.report({'ERROR'}, f"Validation failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"CANCELLED"}
        
        return {"FINISHED"}
    
    def _run_clash_detection(self, route_elements, fed_props):
        """Run clash detection - placeholder for Phase 2B"""
        # TODO: Implement actual clash detection using federation index
        print("⚠️  Clash detection not yet implemented (Phase 2B)")
        return []
    
    def _print_clash_details(self, clashes):
        """Print detailed clash information to console"""
        print("\n" + "="*60)
        print("CLASH VALIDATION RESULTS")
        print("="*60)
        
        for clash in clashes:
            distance_mm = clash.get('clearance', 0) * 1000
            print(f"⚠️  {clash.get('a_name', 'Route')} ↔ "
                  f"{clash.get('b_name', 'Obstacle')}: {distance_mm:.0f}mm clearance")
        
        print("="*60 + "\n")
    
    def _export_bcf(self, clashes, context):
        """Export clashes to BCF file"""
        from pathlib import Path
        
        # TODO Phase 2B: Implement BCF export
        bcf_path = Path.home() / "terminal1_route_clashes.bcf"
        
        self.report({'WARNING'}, 
                   "BCF export not yet implemented. "
                   "See console for clash summary.")
        
        return str(bcf_path)