# Bonsai - OpenBIM Blender Add-on
# Copyright (C) 2020, 2021 Dion Moult <dion@thinkmoult.com>
#
# This file is part of Bonsai.
#
# Bonsai is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Bonsai is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Bonsai.  If not, see <http://www.gnu.org/licenses/>.

"""
Federation Analysis Operators

Custom operators for discipline-based clash detection, visualization,
and LOD management using federation databases.
"""

import os
import bpy
import json
import sqlite3
import tempfile
import bmesh
import logging
import numpy as np
import ifcopenshell
import bonsai.tool as tool
from pathlib import Path
from math import radians
from mathutils import Matrix, Vector
from bonsai.bim.ifc import IfcStore
from typing import TYPE_CHECKING

# Setup logging
logger = logging.getLogger(__name__)


class BIM_OT_clash_by_discipline(bpy.types.Operator):
    """Run discipline-based clash detection using federation database"""
    bl_idname = "bim.clash_by_discipline"
    bl_label = "Clash by Discipline"
    bl_description = "Quick clash detection by discipline using spatial index"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import sqlite3
        import logging

        logger = logging.getLogger(__name__)

        props = tool.Clash.get_clash_props()
        fed_props = context.scene.BIMFederationProperties

        # Get database path from federation panel
        db_path = fed_props.federation_database_path
        if not db_path:
            error_msg = "Please load Federation Database in Multi-Model Federation panel"
            logger.error(error_msg)
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}

        db_path = Path(bpy.path.abspath(db_path))
        if not db_path.exists():
            error_msg = f"Federation database not found: {db_path}"
            logger.error(error_msg)
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}

        logger.info(f"Using federation database: {db_path}")

        # Handle multi-discipline expansion for ALL_MEP preset
        disciplines_a = [props.discipline_a]
        disciplines_b = [props.discipline_b]

        if props.clash_preset == 'ALL_MEP':
            # Expand ALL_MEP to all MEP disciplines
            disciplines_a = ['ACMV', 'ELEC', 'FP']
            disciplines_b = ['ACMV', 'ELEC', 'FP']
            logger.info(f"Applied preset: ALL_MEP - Expanding to all combinations")
            logger.info(f"  MEP disciplines: {', '.join(disciplines_a)}")

        tolerance = props.discipline_tolerance

        logger.info("\n" + "="*70)
        logger.info("DISCIPLINE CLASH DETECTION - OPTIMIZED FEDERATION DATABASE")
        logger.info("="*70)
        logger.info(f"Discipline A: {', '.join(disciplines_a)}")
        logger.info(f"Discipline B: {', '.join(disciplines_b)}")
        logger.info(f"Tolerance: {tolerance}m")
        logger.info(f"Database: {db_path}")
        logger.info("-"*70)

        candidates = []

        try:
            # Import clash detector
            from .clash.detector import detect_clashes_from_database

            logger.info("Starting database clash detection...")
            logger.info(f"  Database: {db_path}")
            logger.info(f"  Tolerance: {tolerance}mm")
            logger.info(f"  Disciplines A: {disciplines_a}")
            logger.info(f"  Disciplines B: {disciplines_b}")

            # Run clash detection for all discipline combinations
            for disc_a in disciplines_a:
                for disc_b in disciplines_b:
                    # Skip self-clashes (same discipline vs itself)
                    if disc_a == disc_b:
                        continue

                    logger.info(f"\nDetecting clashes: {disc_a} vs {disc_b}...")
                    start_time = __import__('time').time()

                    # Query database for clash candidates using detector
                    # Filter to only these two disciplines
                    disc_filter = [disc_a, disc_b]
                    all_clashes = detect_clashes_from_database(
                        db_path,
                        tolerance_mm=tolerance,
                        disciplines=disc_filter
                    )

                    # Filter to only clashes between disc_a and disc_b
                    clashes = [
                        c for c in all_clashes
                        if (c['elem_a_discipline'] == disc_a and c['elem_b_discipline'] == disc_b) or
                           (c['elem_a_discipline'] == disc_b and c['elem_b_discipline'] == disc_a)
                    ]

                    query_time = __import__('time').time() - start_time
                    logger.info(f"  Found {len(clashes)} clashes in {query_time:.2f}s")

                    # Format candidates for UI
                    for clash in clashes:
                        candidates.append({
                            'guid_a': clash['elem_a_guid'],
                            'guid_b': clash['elem_b_guid'],
                            'name_a': clash['elem_a_guid'][:8],  # Use GUID prefix as name
                            'name_b': clash['elem_b_guid'][:8],
                            'ifc_class_a': clash['elem_a_ifc_class'],
                            'ifc_class_b': clash['elem_b_ifc_class'],
                            'discipline_a': clash['elem_a_discipline'],
                            'discipline_b': clash['elem_b_discipline'],
                            'distance': abs(clash.get('clearance', 0)),  # Use clearance as distance (mm)
                            'bbox_a': None,  # Will be queried from DB when needed by gizmos
                            'bbox_b': None
                        })

            logger.info("\n" + "="*70)
            logger.info(f"TOTAL CLASH CANDIDATES: {len(candidates)}")
            logger.info("="*70 + "\n")

        except Exception as e:
            error_msg = f"Clash detection failed: {str(e)}"
            logger.exception(error_msg)
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}

        # Update UI properties
        props.discipline_clash_candidates.clear()

        for idx, candidate in enumerate(candidates, 1):
            new = props.discipline_clash_candidates.add()
            new.guid_a = candidate['guid_a']
            new.guid_b = candidate['guid_b']
            new.name_a = candidate['name_a']
            new.name_b = candidate['name_b']
            new.ifc_class_a = candidate['ifc_class_a']
            new.ifc_class_b = candidate['ifc_class_b']

        props.discipline_clash_loaded = True
        props.active_discipline_clash_index = 0

        self.report({'INFO'}, f"Found {len(candidates)} clash candidates")
        return {'FINISHED'}


class BIM_OT_select_discipline_clash(bpy.types.Operator):
    """Select and focus on the active clash candidate"""
    bl_idname = "bim.select_discipline_clash"
    bl_label = "View Clash"
    bl_description = "Select clashing elements in Blender and zoom to location"
    bl_options = {'REGISTER', 'UNDO'}

    def find_element_by_spatial_proximity(self, ifc_file, ifc_class, bbox_center, tolerance=1.0):
        """
        Find an IFC element near the clash location using spatial proximity.

        Args:
            ifc_file: Loaded IFC file
            ifc_class: IFC class name (e.g., "IfcWall")
            bbox_center: Tuple (x, y, z) of the clash bbox center
            tolerance: Search radius in meters

        Returns:
            IFC element or None
        """
        # Get all elements of this IFC class
        elements = ifc_file.by_type(ifc_class)

        # Filter by proximity to bbox center
        cx, cy, cz = bbox_center

        for element in elements:
            try:
                # Get element's local placement (requires traversing relationships)
                if not element.ObjectPlacement:
                    continue

                placement = ifcopenshell.util.placement.get_local_placement(element.ObjectPlacement)
                ex, ey, ez = placement[0][3], placement[1][3], placement[2][3]

                # Check if within tolerance
                distance = ((ex - cx)**2 + (ey - cy)**2 + (ez - cz)**2)**0.5
                if distance <= tolerance:
                    return element

            except (AttributeError, IndexError, TypeError):
                # Skip elements with invalid placement data
                continue

        return None

    def execute(self, context):
        props = tool.Clash.get_clash_props()

        if not props.discipline_clash_loaded:
            self.report({'WARNING'}, "No discipline clash results loaded")
            return {'CANCELLED'}

        if not (0 <= props.active_discipline_clash_index < len(props.discipline_clash_candidates)):
            self.report({'WARNING'}, "Invalid clash selection")
            return {'CANCELLED'}

        candidate = props.discipline_clash_candidates[props.active_discipline_clash_index]

        # Use federation database for visualization (NO IFC NEEDED!)
        fed_props = context.scene.BIMFederationProperties
        db_path = bpy.path.abspath(fed_props.federation_database_path)

        if not db_path or not Path(db_path).exists():
            self.report({'ERROR'}, "No federation database loaded")
            return {'CANCELLED'}

        from .visualization import federation_viz_helper

        # CRITICAL: Prevent re-entrancy crash on double-click
        # Check if we're already processing this operation
        if hasattr(context.scene, '_clash_viz_processing'):
            print("⚠️  Already processing clash visualization - ignoring duplicate call")
            return {'CANCELLED'}

        try:
            context.scene['_clash_viz_processing'] = True

            # Find or create elements from database
            print(f"Finding clash elements from database (no IFC needed)...")
            obj_a, obj_b = federation_viz_helper.get_clash_elements_for_visualization(
                candidate.guid_a,
                candidate.guid_b,
                db_path
            )
        finally:
            # Always clear the lock
            if '_clash_viz_processing' in context.scene:
                del context.scene['_clash_viz_processing']

        # Report status
        if not obj_a:
            self.report({'WARNING'}, f"Element A ({candidate.name_a}) not found in database")
        if not obj_b:
            self.report({'WARNING'}, f"Element B ({candidate.name_b}) not found in database")

        if not obj_a and not obj_b:
            self.report({'ERROR'}, "Neither clash element found in federation database")
            return {'CANCELLED'}

        # Select objects
        bpy.ops.object.select_all(action='DESELECT')
        if obj_a:
            obj_a.select_set(True)
        if obj_b:
            obj_b.select_set(True)

        if obj_a:
            context.view_layer.objects.active = obj_a
        elif obj_b:
            context.view_layer.objects.active = obj_b

        # Zoom to selected (safely handle gizmo context)
        zoom_success = False
        try:
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            try:
                                override = {'area': area, 'region': region}
                                with context.temp_override(**override):
                                    bpy.ops.view3d.view_selected()
                                zoom_success = True
                                logger.info("✓ Zoom to clash successful")
                                break
                            except (TypeError, AttributeError, RuntimeError) as e:
                                # Context doesn't support override (gizmo modal state)
                                logger.debug(f"  Zoom failed for area (trying next): {e}")
                                continue
                    if zoom_success:
                        break
        except Exception as e:
            logger.warning(f"Zoom operation failed: {e}")

        if not zoom_success:
            logger.info("⚠ Zoom failed - objects selected, user can manually zoom (F key)")

        self.report({'INFO'}, f"Selected clash: {candidate.name_a} vs {candidate.name_b}")
        return {'FINISHED'}


class BIM_OT_analyze_bbox_candidates(bpy.types.Operator):
    """Analyze bounding box clash candidates (diagnostic tool)"""
    bl_idname = "bim.analyze_bbox_candidates"
    bl_label = "Analyze BBox Candidates"
    bl_description = "Diagnostic: Analyze clash bounding boxes from database"
    bl_options = {'REGISTER'}

    def execute(self, context):
        import sqlite3
        import logging

        logger = logging.getLogger(__name__)

        props = tool.Clash.get_clash_props()
        fed_props = context.scene.BIMFederationProperties

        # Validate database path
        db_path = fed_props.federation_database_path
        if not db_path:
            self.report({'ERROR'}, "Please load Federation Database in Multi-Model Federation panel")
            return {'CANCELLED'}

        db_path = Path(bpy.path.abspath(db_path))
        if not db_path.exists():
            self.report({'ERROR'}, f"Federation database not found: {db_path}")
            return {'CANCELLED'}

        logger.info("\n" + "="*70)
        logger.info("BOUNDING BOX ANALYSIS")
        logger.info("="*70)

        try:
            from bonsai.bim.module.federation.spatial_index import FederationIndex

            logger.info("Loading spatial index...")
            index = FederationIndex(db_path)
            index.build()

            logger.info(f"Total elements: {index.stats.get('total_elements', 0)}")
            logger.info(f"Disciplines: {', '.join(index.stats.get('disciplines', []))}")

            # Sample query: Show first few elements per discipline
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT DISTINCT discipline FROM elements_meta
                ORDER BY discipline
            """)
            disciplines = [row[0] for row in cursor.fetchall()]

            for disc in disciplines:
                cursor.execute("""
                    SELECT guid, ifc_class, minX, maxX, minY, maxY, minZ, maxZ
                    FROM elements_rtree
                    WHERE guid IN (
                        SELECT guid FROM elements_meta WHERE discipline = ?
                    )
                    LIMIT 5
                """, (disc,))

                logger.info(f"\n{disc} Sample Elements:")
                for row in cursor.fetchall():
                    guid, ifc_class, minX, maxX, minY, maxY, minZ, maxZ = row
                    width = maxX - minX
                    depth = maxY - minY
                    height = maxZ - minZ
                    logger.info(f"  {ifc_class[:20]:20} {guid[:8]}... "
                              f"W:{width:.2f} D:{depth:.2f} H:{height:.2f}")

            conn.close()
            logger.info("\n" + "="*70)

            self.report({'INFO'}, "Analysis complete (see console)")

        except Exception as e:
            error_msg = f"Analysis failed: {str(e)}"
            logger.exception(error_msg)
            self.report({'ERROR'}, error_msg)
            return {'CANCELLED'}

        return {'FINISHED'}


class BIM_OT_visualize_selected_discipline_clashes(bpy.types.Operator):
    """Visualize selected clash candidates (wireframe spheres)"""
    bl_idname = "bim.visualize_selected_discipline_clashes"
    bl_label = "Visualize Selected Clashes"
    bl_description = "Draw wireframe spheres at clash locations"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from bonsai.bim.module.federation_analysis.clash import gizmo

        props = tool.Clash.get_clash_props()

        if not props.discipline_clash_loaded or not props.discipline_clash_candidates:
            self.report({'WARNING'}, "No discipline clash candidates loaded")
            return {'CANCELLED'}

        # Get selected clashes
        selected_candidates = [c for c in props.discipline_clash_candidates if c.selected]

        if not selected_candidates:
            self.report({'WARNING'}, "No clashes selected. Check the checkboxes first.")
            return {'CANCELLED'}

        logger = logging.getLogger(__name__)
        logger.info(f"\n{'='*70}")
        logger.info(f"VISUALIZING {len(selected_candidates)} SELECTED CLASH CANDIDATES")
        logger.info(f"{'='*70}")

        for idx, candidate in enumerate(selected_candidates, 1):
            logger.info(f"  Clash {idx+1}: {candidate.ifc_class_a} vs {candidate.ifc_class_b}")

            # Create visualization sphere
            sphere_name = f"Clash_{idx+1}_{candidate.ifc_class_a}_vs_{candidate.ifc_class_b}"

            # Use middle point of bboxes if available
            # (In real implementation, would fetch from database)
            # For now, create at origin as placeholder

            bpy.ops.mesh.primitive_uv_sphere_add(
                radius=0.5,
                location=(0, 0, idx * 2.0),  # Stagger vertically for visibility
                segments=16,
                ring_count=8
            )

            sphere = context.active_object
            sphere.name = sphere_name
            sphere.display_type = 'WIRE'
            sphere.show_in_front = True

            # Red material for clashes
            mat = bpy.data.materials.new(name=f"ClashMat_{idx}")
            mat.diffuse_color = (1.0, 0.0, 0.0, 1.0)
            sphere.data.materials.append(mat)

        logger.info(f"{'='*70}\n")

        self.report({'INFO'}, f"Visualized {len(selected_candidates)} clashes")
        return {'FINISHED'}


class BIM_OT_deselect_all_clashes(bpy.types.Operator):
    """Deselect all clash candidates"""
    bl_idname = "bim.deselect_all_clashes"
    bl_label = "Deselect All Clashes"
    bl_description = "Clear all clash checkboxes"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = tool.Clash.get_clash_props()
        for candidate in props.discipline_clash_candidates:
            candidate.selected = False
        return {'FINISHED'}


class BIM_OT_clear_discipline_clash_visualization(bpy.types.Operator):
    """Clear all discipline clash visualizations"""
    bl_idname = "bim.clear_discipline_clash_visualization"
    bl_label = "Clear Clash Visualization"
    bl_description = "Remove all clash visualization objects and overlays"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from bonsai.bim.module.federation_analysis.clash import visualization
        from bonsai.bim.module.federation_analysis.clash import gizmo
        from bonsai.bim.module.federation_analysis.visualization import federation_viz_helper

        # Clear GPU overlays
        visualization.disable_visualization()

        # Clear gizmo visualization
        gizmo.disable_clash_gizmos(context)

        # Clear temp visualization objects AND the Clash_Visualization collection
        federation_viz_helper.cleanup_temp_visualization_objects()

        self.report({'INFO'}, "Cleared all clash visualizations")
        return {'FINISHED'}


class BIM_OT_enable_clash_gpu_visualization(bpy.types.Operator):
    """Enable GPU overlay visualization for clash candidates"""
    bl_idname = "bim.enable_clash_gpu_visualization"
    bl_label = "Enable GPU Overlay"
    bl_description = "Draw clash locations as GPU overlays (fast, non-selectable)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from bonsai.bim.module.federation_analysis.clash import visualization

        props = tool.Clash.get_clash_props()

        if not props.discipline_clash_loaded or not props.discipline_clash_candidates:
            self.report({'WARNING'}, "No discipline clash candidates loaded")
            return {'CANCELLED'}

        # Extract clash points (bbox centers)
        clash_points = []
        for candidate in props.discipline_clash_candidates:
            # TODO: Extract actual bbox centers from database
            # For now, placeholder at origin
            clash_points.append((0, 0, 0))

        # Enable GPU visualization
        visualization.enable_clash_visualization(clash_points)

        self.report({'INFO'}, f"GPU overlay enabled for {len(clash_points)} clashes")
        return {'FINISHED'}


class BIM_OT_disable_clash_gpu_visualization(bpy.types.Operator):
    """Disable GPU overlay visualization"""
    bl_idname = "bim.disable_clash_gpu_visualization"
    bl_label = "Disable GPU Overlay"
    bl_description = "Remove GPU overlay visualization"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from bonsai.bim.module.federation_analysis.clash import visualization

        visualization.disable_visualization()

        self.report({'INFO'}, "GPU overlay disabled")
        return {'FINISHED'}


class BIM_OT_enable_clash_gizmo_visualization(bpy.types.Operator):
    """Enable interactive 3D gizmo visualization for clash candidates"""
    bl_idname = "bim.enable_clash_gizmo_visualization"
    bl_label = "Enable Clash Gizmos"
    bl_description = "Show interactive 3D markers (clickable, right-click menu)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from bonsai.bim.module.federation_analysis.clash import gizmo

        props = tool.Clash.get_clash_props()

        if not props.discipline_clash_loaded or not props.discipline_clash_candidates:
            self.report({'WARNING'}, "No discipline clash candidates loaded")
            return {'CANCELLED'}

        # Get selected clashes (or all if none selected)
        selected_clashes = [c for c in props.discipline_clash_candidates if c.selected]

        if not selected_clashes:
            self.report({'WARNING'}, "No clashes selected. Check the checkboxes first.")
            return {'CANCELLED'}

        if len(selected_clashes) > 10:
            self.report({'WARNING'}, f"Too many clashes selected ({len(selected_clashes)}). Max 10 for gizmo visualization.")
            return {'CANCELLED'}

        # Extract clash data
        clash_data = []
        for idx, candidate in enumerate(selected_clashes):
            clash_data.append({
                'index': idx,
                'guid_a': candidate.guid_a,
                'guid_b': candidate.guid_b,
                'position': (0, 0, idx * 2.0),  # TODO: Get from database
                'status': 'new'  # Default status
            })

        # Enable gizmo visualization
        try:
            # Property is set inside enable_clash_gizmos()
            gizmo.enable_clash_gizmos(context)
            self.report({'INFO'}, f"Gizmo visualization enabled for {len(clash_data)} clashes")
        except Exception as e:
            self.report({'ERROR'}, f"Failed to enable gizmo: {str(e)}")
            return {'CANCELLED'}

        return {'FINISHED'}


class BIM_OT_disable_clash_gizmo_visualization(bpy.types.Operator):
    """Disable interactive gizmo visualization"""
    bl_idname = "bim.disable_clash_gizmo_visualization"
    bl_label = "Disable Clash Gizmos"
    bl_description = "Remove interactive 3D markers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from bonsai.bim.module.federation_analysis.clash import gizmo

        props = tool.Clash.get_clash_props()
        # Property is set inside disable_clash_gizmos()
        gizmo.disable_clash_gizmos(context)

        self.report({'INFO'}, "Gizmo visualization disabled")
        return {'FINISHED'}


class BIM_OT_load_clash_geometry(bpy.types.Operator):
    """Load exact IFC geometry for clash candidates (lazy loading)"""
    bl_idname = "bim.load_clash_geometry"
    bl_label = "Load Clash Geometry"
    bl_description = "Load exact tessellated geometry for selected clashes (from IFC files)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = tool.Clash.get_clash_props()

        if not props.discipline_clash_loaded or not props.discipline_clash_candidates:
            self.report({'WARNING'}, "No discipline clash candidates loaded")
            return {'CANCELLED'}

        # Get active clash
        if not (0 <= props.active_discipline_clash_index < len(props.discipline_clash_candidates)):
            self.report({'WARNING'}, "No clash selected")
            return {'CANCELLED'}

        candidate = props.discipline_clash_candidates[props.active_discipline_clash_index]
        clash_idx = props.active_discipline_clash_index

        logger = logging.getLogger(__name__)
        logger.info(f"\n{'='*70}")
        logger.info(f"LOADING GEOMETRY FOR CLASH {clash_idx + 1}")
        logger.info(f"{'='*70}")
        print(f"Clash {clash_idx + 1}: {candidate.ifc_class_a} vs {candidate.ifc_class_b}")
        print(f"  Element A: {candidate.name_a} (GUID: {candidate.guid_a[:8]}...)")
        print(f"  Element B: {candidate.name_b} (GUID: {candidate.guid_b[:8]}...)")

        # TODO: Implement lazy IFC geometry loading from federation database
        # Steps:
        # 1. Query database for source IFC file paths via discipline mapping
        # 2. Load only the specific elements by GUID (using ifcopenshell)
        # 3. Create Blender mesh objects
        # 4. Position using coordinate system offset

        self.report({'WARNING'}, "Geometry loading not yet implemented")
        return {'CANCELLED'}

        # Placeholder for now - would create actual geometry here
        # import ifcopenshell
        # import ifcopenshell.geom
        #
        # settings = ifcopenshell.geom.settings()
        # for guid in [candidate.guid_a, candidate.guid_b]:
        #     element = ifc_file.by_guid(guid)
        #     shape = ifcopenshell.geom.create_shape(settings, element)
        #     # ... create Blender mesh from shape


class BIM_OT_enable_bbox_visualization(bpy.types.Operator):
    """Enable bounding box wireframe visualization"""
    bl_idname = "bim.enable_bbox_visualization"
    bl_label = "Enable BBox View"
    bl_description = "Show colored wireframe bounding boxes for all elements"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from bonsai.bim.module.federation import bbox_visualization

        props = tool.Clash.get_clash_props()
        fed_props = context.scene.BIMFederationProperties

        # Validate database
        db_path = fed_props.federation_database_path
        if not db_path:
            self.report({'ERROR'}, "Please load Federation Database in Multi-Model Federation panel")
            return {'CANCELLED'}

        db_path = Path(bpy.path.abspath(db_path))
        if not db_path.exists():
            self.report({'ERROR'}, f"Federation database not found: {db_path}")
            return {'CANCELLED'}

        # Get element limit
        limit = props.bbox_element_limit if props.bbox_element_limit > 0 else None

        # Enable bbox visualization
        success, message = bbox_visualization.enable_bbox_visualization(str(db_path), limit=limit)

        if success:
            props.bbox_visualization_enabled = True
            self.report({'INFO'}, message)
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, message)
            return {'CANCELLED'}


class BIM_OT_disable_bbox_visualization(bpy.types.Operator):
    """Disable bounding box wireframe visualization"""
    bl_idname = "bim.disable_bbox_visualization"
    bl_label = "Disable BBox View"
    bl_description = "Remove bounding box visualization"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from bonsai.bim.module.federation import bbox_visualization

        props = tool.Clash.get_clash_props()

        success, message = bbox_visualization.disable_bbox_visualization()

        props.bbox_visualization_enabled = False

        self.report({'INFO'}, message)
        return {'FINISHED'}


class BIM_OT_enable_semantic_proxy_visualization(bpy.types.Operator):
    """Enable semantic proxy visualization (basic procedural shapes)"""
    bl_idname = "bim.enable_semantic_proxy_visualization"
    bl_label = "Enable Semantic Proxies"
    bl_description = "Generate basic procedural shapes from semantic metadata"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from bonsai.bim.module.federation_analysis.visualization import semantic_shapes

        props = tool.Clash.get_clash_props()
        fed_props = context.scene.BIMFederationProperties

        # Validate database
        db_path = fed_props.federation_database_path
        if not db_path:
            self.report({'ERROR'}, "Please load Federation Database in Multi-Model Federation panel")
            return {'CANCELLED'}

        db_path = Path(bpy.path.abspath(db_path))
        if not db_path.exists():
            self.report({'ERROR'}, f"Federation database not found: {db_path}")
            return {'CANCELLED'}

        # Get element limit
        limit = props.bbox_element_limit if props.bbox_element_limit > 0 else None

        # Enable semantic visualization with basic detail level
        self.report({'INFO'}, f"Generating semantic proxies from database...")
        success, message = semantic_shapes.enable_semantic_visualization(
            str(db_path),
            detail_level='basic',
            limit=limit
        )

        if success:
            props.bbox_visualization_enabled = True
            props.lod_visualization_mode = 'SEMANTIC_PROXY'
            self.report({'INFO'}, message)
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, message)
            return {'CANCELLED'}


class BIM_OT_disable_semantic_proxy_visualization(bpy.types.Operator):
    """Disable semantic proxy visualization"""
    bl_idname = "bim.disable_semantic_proxy_visualization"
    bl_label = "Disable Semantic Proxies"
    bl_description = "Remove semantic proxy objects from scene"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from bonsai.bim.module.federation_analysis.visualization import semantic_shapes

        props = tool.Clash.get_clash_props()

        success, message = semantic_shapes.disable_semantic_visualization()

        props.bbox_visualization_enabled = False
        props.lod_visualization_mode = 'NONE'

        self.report({'INFO'}, message)
        return {'FINISHED'}


class BIM_OT_enable_full_geometry_visualization(bpy.types.Operator):
    """Enable full geometry (detailed templates with flanges, dampers, etc.)"""
    bl_idname = "bim.enable_full_geometry_visualization"
    bl_label = "Enable Full Geometry"
    bl_description = "Generate detailed procedural geometry from semantic metadata"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from bonsai.bim.module.federation_analysis.visualization import semantic_shapes

        props = tool.Clash.get_clash_props()
        fed_props = context.scene.BIMFederationProperties

        # Validate database
        db_path = fed_props.federation_database_path
        if not db_path:
            self.report({'ERROR'}, "Please load Federation Database in Multi-Model Federation panel")
            return {'CANCELLED'}

        db_path = Path(bpy.path.abspath(db_path))
        if not db_path.exists():
            self.report({'ERROR'}, f"Federation database not found: {db_path}")
            return {'CANCELLED'}

        # Get element limit
        limit = props.bbox_element_limit if props.bbox_element_limit > 0 else None

        # Enable semantic visualization with detailed level
        self.report({'INFO'}, f"Generating full geometry from database...")
        success, message = semantic_shapes.enable_semantic_visualization(
            str(db_path),
            detail_level='detailed',
            limit=limit
        )

        if success:
            props.bbox_visualization_enabled = True
            props.lod_visualization_mode = 'FULL_GEOMETRY'
            self.report({'INFO'}, message)
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, message)
            return {'CANCELLED'}


class BIM_OT_disable_full_geometry_visualization(bpy.types.Operator):
    """Disable full geometry visualization"""
    bl_idname = "bim.disable_full_geometry_visualization"
    bl_label = "Disable Full Geometry"
    bl_description = "Remove full geometry objects from scene"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from bonsai.bim.module.federation_analysis.visualization import semantic_shapes

        props = tool.Clash.get_clash_props()

        success, message = semantic_shapes.disable_semantic_visualization()

        props.bbox_visualization_enabled = False
        props.lod_visualization_mode = 'NONE'

        self.report({'INFO'}, message)
        return {'FINISHED'}


# ================================================================
# CLASH ADJUSTMENT OPERATORS
# ================================================================


class BIM_OT_analyze_clash_groups(bpy.types.Operator):
    """Analyze clashes and identify cascade groups (elements with 3+ clashes)"""
    bl_idname = "bim.analyze_clash_groups"
    bl_label = "Analyze Clash Groups"
    bl_description = "Group clashes by common elements (cascade detection)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from bonsai.bim.module.federation_analysis.clash import clash_grouping

        props = tool.Clash.get_clash_props()

        # Check if we have clash data
        if not props.discipline_clash_loaded or not props.discipline_clash_candidates:
            self.report({'ERROR'}, "No clash data available. Run clash detection first.")
            return {'CANCELLED'}

        # Get database path
        fed_props = context.scene.BIMFederationProperties
        db_path = fed_props.federation_database_path
        if not db_path or not os.path.exists(db_path):
            self.report({'ERROR'}, "Federation database not found")
            return {'CANCELLED'}

        try:
            # Verify database schema exists (must be initialized manually)
            from bonsai.bim.module.federation_analysis.clash import resolution_database
            db_manager = resolution_database.ResolutionDatabase(db_path)

            if not db_manager.verify_schema():
                self.report({'ERROR'}, "Database schema not initialized. See console for instructions.")
                return {'CANCELLED'}

            # Open connection for data sync
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Sync clashes from in-memory candidates to database
            # Preserve existing status for clashes that already exist
            new_count = 0
            updated_count = 0

            for clash in props.discipline_clash_candidates:
                # Lookup disciplines from elements_meta
                cursor.execute("SELECT discipline FROM elements_meta WHERE guid = ?", (clash.guid_a,))
                row_a = cursor.fetchone()
                discipline_a = row_a[0] if row_a else None

                cursor.execute("SELECT discipline FROM elements_meta WHERE guid = ?", (clash.guid_b,))
                row_b = cursor.fetchone()
                discipline_b = row_b[0] if row_b else None

                # Check if clash already exists
                cursor.execute("""
                    SELECT clash_id, status FROM clash_status
                    WHERE guid_a = ? AND guid_b = ?
                """, (clash.guid_a, clash.guid_b))
                existing = cursor.fetchone()

                if existing:
                    # Update existing clash (preserve status, update other fields)
                    cursor.execute("""
                        UPDATE clash_status
                        SET name_a = ?, name_b = ?,
                            ifc_class_a = ?, ifc_class_b = ?,
                            discipline_a = ?, discipline_b = ?,
                            distance = ?
                        WHERE clash_id = ?
                    """, (
                        clash.name_a, clash.name_b,
                        clash.ifc_class_a, clash.ifc_class_b,
                        discipline_a, discipline_b,
                        clash.distance,
                        existing[0]
                    ))
                    updated_count += 1

                    # Sync status back to in-memory property
                    clash.status = existing[1]
                else:
                    # Insert new clash
                    cursor.execute("""
                        INSERT INTO clash_status
                        (guid_a, guid_b, name_a, name_b, ifc_class_a, ifc_class_b,
                         discipline_a, discipline_b, status, distance)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        clash.guid_a, clash.guid_b,
                        clash.name_a, clash.name_b,
                        clash.ifc_class_a, clash.ifc_class_b,
                        discipline_a, discipline_b,
                        clash.status,
                        clash.distance
                    ))
                    new_count += 1

            conn.commit()
            conn.close()

            print(f"✓ Synced clash_status: {new_count} new, {updated_count} updated (status preserved)")

            # Create grouping analyzer
            analyzer = clash_grouping.ClashGroupAnalyzer(db_path)

            # Analyze clash groups (find cascade patterns)
            groups = analyzer.find_cascade_groups()

            # Store results in database
            analyzer.export_groups_to_database(groups)

            # Get summary for console output
            summary = analyzer.get_group_summary(groups)

            # Set flag
            props.clash_groups_analyzed = True

            # Report results using summary
            print(f"\n{'='*60}")
            print(f"CLASH GROUPING ANALYSIS COMPLETE")
            print(f"{'='*60}")
            print(f"Total Groups Found: {summary['total_groups']}")
            print(f"Clashes Grouped: {summary['total_grouped_clashes']}/{len(props.discipline_clash_candidates)} ({summary['grouping_efficiency']:.1f}%)")
            print(f"\nGroup Details:")
            for i, group in enumerate(groups, 1):
                print(f"  Group {i}: {group.cascade_element_guid} ({group.cascade_element_class})")
                print(f"    Discipline: {group.cascade_element_discipline}")
                print(f"    Clashes: {group.total_clashes}, Severity: {group.severity}")
                print(f"    Affected Disciplines: {', '.join(group.affected_disciplines)}")
                print(f"    Status: {', '.join(f'{k}={v}' for k, v in group.status_summary.items())}")
            print(f"{'='*60}\n")

            self.report({'INFO'}, f"Found {len(groups)} cascade groups ({summary['grouping_efficiency']:.1f}% efficiency)")
            return {'FINISHED'}

        except Exception as e:
            logger.exception("Clash grouping analysis failed")
            self.report({'ERROR'}, f"Grouping failed: {str(e)}")
            return {'CANCELLED'}


class BIM_OT_suggest_resolutions(bpy.types.Operator):
    """Generate resolution suggestions for all clash groups"""
    bl_idname = "bim.suggest_resolutions"
    bl_label = "Suggest Resolutions"
    bl_description = "Generate ranked resolution options with cost/effort estimates"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from bonsai.bim.module.federation_analysis.clash import resolution_engine

        props = tool.Clash.get_clash_props()

        # Check if grouping was done
        if not props.clash_groups_analyzed:
            self.report({'ERROR'}, "Run clash grouping analysis first")
            return {'CANCELLED'}

        # Get database path
        fed_props = context.scene.BIMFederationProperties
        db_path = fed_props.federation_database_path
        if not db_path or not os.path.exists(db_path):
            self.report({'ERROR'}, "Federation database not found")
            return {'CANCELLED'}

        try:
            # Create resolution engine
            engine = resolution_engine.ResolutionEngine(db_path)

            # Get all group IDs from database
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT id, cascade_element_guid FROM clash_groups ORDER BY id")
            group_rows = cursor.fetchall()
            conn.close()

            if not group_rows:
                self.report({'WARNING'}, "No clash groups found. Run grouping analysis first.")
                return {'CANCELLED'}

            # Generate resolutions for all groups
            all_resolutions = {}
            for group_id, element_guid in group_rows:
                options = engine.analyze_group(group_id)
                if options:
                    engine.save_options_to_database(group_id, options)
                    all_resolutions[group_id] = options

            engine.close()

            # Set flag
            props.resolutions_generated = True

            # Report results
            print(f"\n{'='*60}")
            print(f"RESOLUTION SUGGESTIONS GENERATED")
            print(f"{'='*60}")
            print(f"Groups Analyzed: {len(all_resolutions)}")
            print(f"\nResolution Options:")

            for group_id, resolutions in all_resolutions.items():
                print(f"\n  Group {group_id}:")
                for i, res in enumerate(resolutions, 1):
                    print(f"    Option {i}: {res.option_type}")
                    print(f"      Design Effort: {res.total_design_hours:.1f}h (${res.total_design_cost:,.0f})")
                    print(f"      Schedule: {res.calendar_days:.0f} days")
                    print(f"      Risk: {res.risk_category} (score: {res.risk_score}/100)")
                    print(f"      Resolves: {res.clashes_resolved} clashes")
                    if i == 1:
                        print(f"      ✓ RECOMMENDED")

            print(f"{'='*60}\n")

            total_options = sum(len(r) for r in all_resolutions.values())
            self.report({'INFO'}, f"Generated {total_options} resolution options for {len(all_resolutions)} groups")
            return {'FINISHED'}

        except Exception as e:
            logger.exception("Resolution generation failed")
            self.report({'ERROR'}, f"Resolution generation failed: {str(e)}")
            return {'CANCELLED'}


class BIM_OT_select_resolution_option(bpy.types.Operator):
    """View and select resolution options"""
    bl_idname = "bim.select_resolution_option"
    bl_label = "View Resolution Options"
    bl_description = "Display resolution options for selection"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = tool.Clash.get_clash_props()

        # Check if resolutions were generated
        if not props.resolutions_generated:
            self.report({'ERROR'}, "Generate resolution suggestions first")
            return {'CANCELLED'}

        # Get database path
        fed_props = context.scene.BIMFederationProperties
        db_path = fed_props.federation_database_path
        if not db_path or not os.path.exists(db_path):
            self.report({'ERROR'}, "Federation database not found")
            return {'CANCELLED'}

        try:
            # Query resolution options from database
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT
                    ro.id,
                    ro.group_id,
                    ro.resolution_type,
                    ro.effort_hours,
                    ro.cost,
                    ro.schedule_days,
                    ro.risk_level,
                    ro.risk_score,
                    cg.element_name,
                    cg.clash_count
                FROM resolution_options ro
                JOIN clash_groups cg ON ro.group_id = cg.id
                ORDER BY ro.group_id, ro.rank
            """)

            rows = cursor.fetchall()
            conn.close()

            if not rows:
                self.report({'WARNING'}, "No resolution options found in database")
                return {'CANCELLED'}

            # Format and display results
            print(f"\n{'='*70}")
            print(f"RESOLUTION OPTIONS VIEWER")
            print(f"{'='*70}")

            current_group = None
            for row in rows:
                option_id, group_id, res_type, effort, cost, days, risk_level, risk_score, elem_name, clash_count = row

                if group_id != current_group:
                    current_group = group_id
                    print(f"\n📦 GROUP {group_id}: {elem_name} ({clash_count} clashes)")
                    print(f"{'─'*70}")

                rank_indicator = "✓ RECOMMENDED" if rows.index(row) == 0 or (current_group and row[1] != rows[rows.index(row)-1][1]) else ""
                print(f"  Option {option_id}: {res_type} {rank_indicator}")
                print(f"    💰 Cost: ${cost:,.0f} ({effort:.1f} hours)")
                print(f"    📅 Schedule: {days} days")
                print(f"    ⚠️  Risk: {risk_level} (score: {risk_score}/100)")

            print(f"{'='*70}\n")
            print("💡 Tip: Use these options to inform your coordination decisions")
            print("   Future: Click to apply resolution and update IFC model\n")

            self.report({'INFO'}, f"Displaying {len(rows)} resolution options")
            return {'FINISHED'}

        except Exception as e:
            logger.exception("Failed to view resolution options")
            self.report({'ERROR'}, f"Failed to view options: {str(e)}")
            return {'CANCELLED'}
