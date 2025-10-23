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
        import logging
        import ifcopenshell.api
        import bonsai.tool as bonsai_tool
        from pathlib import Path
        from datetime import datetime

        # Setup logging to file
        log_path = Path.home() / "Documents" / "bonsai.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        # Create logger with file handler (basicConfig doesn't work in Blender)
        logger = logging.getLogger('ClearRoute')
        logger.setLevel(logging.INFO)

        # Remove existing handlers to avoid duplicates
        logger.handlers.clear()

        # Add file handler
        file_handler = logging.FileHandler(str(log_path), mode='a')
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        logger.info("=" * 60)
        logger.info("Clear Route operation started")

        # Clear visualization (existing behavior)
        visualization.clear_debug_objects()
        logger.info("Visualization objects cleared")

        # NEW: Delete IFC conduit elements BY COORDINATE MATCHING
        deleted_ifc = 0
        deleted_blender = 0

        # Get current Start/End coordinates from UI
        mep_props = context.scene.BIMmepEngineeringProperties
        route_start = tuple(mep_props.route_start_point)
        route_end = tuple(mep_props.route_end_point)

        logger.info(f"Searching for conduits with Start: {route_start}, End: {route_end}")

        try:
            ifc_file = bonsai_tool.Ifc.get()

            if not ifc_file:
                logger.warning("No IFC file loaded")
                self.report({'WARNING'}, "No IFC file loaded")
                return {"CANCELLED"}

            # Helper function to match coordinates with tolerance
            def coords_match(coord1, coord2, tolerance=0.01):
                """Check if two 3D coordinates match within tolerance (in meters)"""
                return all(abs(c1 - c2) < tolerance for c1, c2 in zip(coord1, coord2))

            # Find ALL conduits/fittings with matching Start/End coordinates
            import ifcopenshell.util.element as ifc_util
            matching_elements = []

            # Search schema-appropriate element types
            schema = ifc_file.schema
            logger.info(f"IFC Schema: {schema}")

            all_conduits = []
            if schema == "IFC2X3":
                # IFC2X3: Only IfcFlowSegment and IfcFlowFitting exist
                all_conduits = (
                    ifc_file.by_type("IfcFlowSegment") +
                    ifc_file.by_type("IfcFlowFitting")
                )
            else:
                # IFC4+: Use specific cable carrier types
                all_conduits = (
                    ifc_file.by_type("IfcFlowSegment") +
                    ifc_file.by_type("IfcCableCarrierSegment") +
                    ifc_file.by_type("IfcFlowFitting") +
                    ifc_file.by_type("IfcCableCarrierFitting")
                )

            logger.info(f"Scanning {len(all_conduits)} total MEP elements for route matches...")

            for conduit in all_conduits:
                try:
                    psets = ifc_util.get_psets(conduit)

                    if "Pset_MEP_RouteInfo" in psets:
                        route_info = psets["Pset_MEP_RouteInfo"]

                        conduit_start = (
                            route_info.get("RouteStartX", 0.0),
                            route_info.get("RouteStartY", 0.0),
                            route_info.get("RouteStartZ", 0.0)
                        )
                        conduit_end = (
                            route_info.get("RouteEndX", 0.0),
                            route_info.get("RouteEndY", 0.0),
                            route_info.get("RouteEndZ", 0.0)
                        )

                        # Match with 10mm tolerance
                        if coords_match(route_start, conduit_start, 0.01) and coords_match(route_end, conduit_end, 0.01):
                            matching_elements.append(conduit)
                            logger.info(f"  Found matching {conduit.is_a()} (GUID: {conduit.GlobalId})")
                except Exception as e:
                    # Skip elements that can't be queried
                    pass

            logger.info(f"Found {len(matching_elements)} matching conduit elements to delete")

            # Delete all matching elements
            for element in matching_elements:
                try:
                    # CRITICAL: Store ID BEFORE deletion
                    element_id = element.id()
                    element_guid = element.GlobalId
                    element_class = element.is_a()

                    logger.info(f"Processing {element_class} (GUID: {element_guid}, ID: {element_id})")

                    # Delete IFC element
                    ifcopenshell.api.run("root.remove_product", ifc_file, product=element)
                    deleted_ifc += 1
                    logger.info(f"  ✓ Deleted IFC element {element_guid}")

                    # Delete associated Blender object if it exists
                    blender_obj_found = False
                    for obj in bpy.data.objects:
                        if obj.BIMObjectProperties.ifc_definition_id == element_id:
                            obj_name = obj.name
                            bpy.data.objects.remove(obj, do_unlink=True)
                            deleted_blender += 1
                            blender_obj_found = True
                            logger.info(f"  ✓ Deleted Blender object '{obj_name}' (ID: {element_id})")
                            break

                    if not blender_obj_found:
                        logger.warning(f"  ⚠ No Blender object found for IFC ID {element_id}")
                except RuntimeError as e:
                    logger.error(f"  ✗ RuntimeError deleting {element_guid}: {str(e)}")
                except Exception as e:
                    logger.error(f"  ✗ Error deleting {element_guid}: {str(e)}")
                    import traceback
                    logger.error(traceback.format_exc())

            summary = f"Cleared visualization, deleted {deleted_ifc} IFC elements and {deleted_blender} Blender objects (from ALL routes with same Start/End)"
            logger.info(f"SUMMARY: {summary}")
            self.report({'INFO'}, summary)

        except Exception as e:
            error_msg = f"Cleared visualization, but encountered error deleting IFC elements: {str(e)}"
            logger.error(error_msg)
            import traceback
            logger.error(traceback.format_exc())
            self.report({'WARNING'}, error_msg)

        # Clear stored waypoints and obstacles
        cleared_data = []
        if "MEP_last_route_waypoints" in context.scene:
            del context.scene["MEP_last_route_waypoints"]
            cleared_data.append("waypoints")
        if "MEP_filtered_obstacles" in context.scene:
            del context.scene["MEP_filtered_obstacles"]
            cleared_data.append("obstacles")
        if "MEP_cached_offset" in context.scene:
            del context.scene["MEP_cached_offset"]
            cleared_data.append("offset")

        if cleared_data:
            logger.info(f"Cleared scene data: {', '.join(cleared_data)}")

        logger.info("Clear Route operation completed")
        logger.info("=" * 60)

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


class AutoPickRoutingEndpoints(Operator):
    """Auto-select routing start/end points from federation database"""
    bl_idname = "bim.auto_pick_routing_endpoints"
    bl_label = "Auto-Pick from Federation DB"
    bl_description = "Automatically select routing endpoints from electrical elements in federation database"
    bl_options = {"REGISTER", "UNDO"}

    discipline: bpy.props.StringProperty(
        name="Discipline",
        description="Discipline to query for endpoints",
        default="ELEC"
    )

    def execute(self, context):
        import sqlite3
        from pathlib import Path

        props = context.scene.BIMmepEngineeringProperties
        fed_props = context.scene.BIMFederationProperties

        # Check if federation DB is set
        if not fed_props.federation_database_path:
            self.report({'ERROR'}, "No federation database loaded. Load federation index first.")
            return {"CANCELLED"}

        db_path = Path(bpy.path.abspath(fed_props.federation_database_path))
        if not db_path.exists():
            self.report({'ERROR'}, f"Federation database not found: {db_path}")
            return {"CANCELLED"}

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Query elements from specified discipline
            query = """
                SELECT
                    m.guid,
                    m.ifc_class,
                    r.min_x, r.max_x,
                    r.min_y, r.max_y,
                    r.min_z, r.max_z
                FROM elements_meta m
                JOIN elements_rtree r ON m.id = r.id
                WHERE m.discipline = ?
                ORDER BY m.ifc_class, m.guid
                LIMIT 10
            """

            cursor.execute(query, (self.discipline,))
            rows = cursor.fetchall()

            if len(rows) < 2:
                self.report({'WARNING'},
                    f"Only {len(rows)} {self.discipline} elements found in federation DB. Need at least 2.")
                conn.close()
                return {"CANCELLED"}

            # Calculate bbox centers for all elements
            all_endpoints = []
            for row in rows:
                guid, ifc_class, min_x, max_x, min_y, max_y, min_z, max_z = row
                center_x = (min_x + max_x) / 2
                center_y = (min_y + max_y) / 2
                center_z = (min_z + max_z) / 2
                all_endpoints.append({
                    'guid': guid,
                    'class': ifc_class,
                    'pos': (center_x, center_y, center_z)
                })

            # Find challenging pairs (randomized for variety)
            import math
            import random

            # Calculate distances for all pairs
            challenging_pairs = []
            for i, ep1 in enumerate(all_endpoints):
                for j, ep2 in enumerate(all_endpoints[i+1:], start=i+1):
                    dx = ep2['pos'][0] - ep1['pos'][0]
                    dy = ep2['pos'][1] - ep1['pos'][1]
                    dz = ep2['pos'][2] - ep1['pos'][2]
                    distance = math.sqrt(dx*dx + dy*dy + dz*dz)

                    # Only consider pairs with good distance (> 5m for meaningful routing)
                    if distance > 5.0:
                        challenging_pairs.append({
                            'pair': (ep1, ep2),
                            'distance': distance
                        })

            if not challenging_pairs:
                # Fallback: use any pair if no challenging ones found
                endpoints = [all_endpoints[0], all_endpoints[1]]
                max_distance = math.sqrt(
                    sum((endpoints[1]['pos'][i] - endpoints[0]['pos'][i])**2 for i in range(3))
                )
            else:
                # Sort by distance and pick randomly from top 50%
                challenging_pairs.sort(key=lambda x: x['distance'], reverse=True)
                top_half = challenging_pairs[:max(1, len(challenging_pairs)//2)]

                # Randomly pick from top half for variety
                selected = random.choice(top_half)
                endpoints = list(selected['pair'])
                max_distance = selected['distance']

            # Set routing endpoints
            props.route_start_point = endpoints[0]['pos']
            props.route_end_point = endpoints[1]['pos']

            conn.close()

            # Report success
            print("\n" + "="*70)
            print("AUTO-PICKED ROUTING ENDPOINTS (RANDOMIZED)")
            print("="*70)
            if challenging_pairs:
                print(f"Selected from {len(challenging_pairs)} challenging pairs (distance > 5m)")
            print(f"Distance: {max_distance:.2f}m")
            print(f"\nStart: {endpoints[0]['class']}")
            print(f"  GUID: {endpoints[0]['guid']}")
            print(f"  Position: {endpoints[0]['pos']}")
            print(f"\nEnd: {endpoints[1]['class']}")
            print(f"  GUID: {endpoints[1]['guid']}")
            print(f"  Position: {endpoints[1]['pos']}")
            print(f"\n💡 Click 'Test Routing' again for a different route")
            print("="*70 + "\n")

            self.report({'INFO'},
                f"Auto-picked {max_distance:.1f}m route (click again for different route)")

            return {"FINISHED"}

        except Exception as e:
            self.report({'ERROR'}, f"Failed to query federation DB: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"CANCELLED"}