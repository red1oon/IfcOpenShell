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
            # Use convenience function to analyze all groups
            all_resolutions = resolution_engine.analyze_all_groups(db_path)

            if not all_resolutions:
                self.report({'WARNING'}, "No clash groups found. Run grouping analysis first.")
                return {'CANCELLED'}

            # Set flag
            props.resolutions_generated = True

            # Report summary
            total_options = sum(len(options) for options in all_resolutions.values())
            self.report({'INFO'}, f"Generated {total_options} resolution options for {len(all_resolutions)} groups")

            print("\n💡 Use 'View Resolution Options' to see detailed breakdown and select options")
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
                    ro.option_id,
                    ro.group_id,
                    ro.option_type,
                    ro.total_design_hours,
                    ro.total_design_cost,
                    ro.calendar_days_required,
                    ro.risk_category,
                    ro.risk_score,
                    cg.cascade_element_class,
                    cg.total_clashes
                FROM resolution_options ro
                JOIN clash_groups cg ON ro.group_id = cg.group_id
                ORDER BY ro.group_id, ro.recommendation_rank
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


# ============================================================================
# PHASE 1.5 + PHASE 2: UI OPERATORS
# ============================================================================

class BIM_OT_preview_resolution(bpy.types.Operator):
    """Preview resolution in 3D viewport with ghost geometry"""
    bl_idname = "bim.preview_resolution"
    bl_label = "Preview Resolution"
    bl_description = "Show 3D preview of selected resolution option"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            from .clash import visualization_3d
            from .visualization import federation_viz_helper

            props = tool.Clash.get_clash_props()

            # Validate selection
            if props.selected_resolution_option_id == "":
                self.report({'WARNING'}, "Please select a resolution option first")
                return {'CANCELLED'}

            # Get database path
            fed_props = context.scene.BIMFederationProperties
            db_path = fed_props.federation_database_path

            if not db_path or not os.path.exists(db_path):
                self.report({'ERROR'}, "Database not found. Run clash detection first.")
                return {'CANCELLED'}

            # Get resolution data from database
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Get resolution details
            cursor.execute("""
                SELECT ro.group_id, ro.option_type, ro.total_design_hours,
                       ro.total_design_cost, ro.calendar_days_required, ro.risk_category
                FROM resolution_options ro
                WHERE ro.option_id = ?
            """, (props.selected_resolution_option_id,))

            resolution_row = cursor.fetchone()
            if not resolution_row:
                conn.close()
                self.report({'ERROR'}, f"Resolution option {props.selected_resolution_option_id} not found")
                return {'CANCELLED'}

            group_id, res_type, effort, cost, days, risk_level = resolution_row

            # Get group element bbox
            cursor.execute("""
                SELECT cg.cascade_element_guid, rt.minX, rt.minY, rt.minZ,
                       rt.maxX, rt.maxY, rt.maxZ
                FROM clash_groups cg
                JOIN elements_meta em ON cg.cascade_element_guid = em.guid
                JOIN elements_rtree rt ON em.id = rt.id
                WHERE cg.group_id = ?
            """, (group_id,))

            elem_row = cursor.fetchone()

            if not elem_row:
                conn.close()
                self.report({'ERROR'}, f"Element bbox not found for group {group_id}")
                return {'CANCELLED'}

            element_id, min_x, min_y, min_z, max_x, max_y, max_z = elem_row

            # Build bbox dict (camelCase keys for visualization_3d functions)
            bbox = {
                'minX': min_x, 'minY': min_y, 'minZ': min_z,
                'maxX': max_x, 'maxY': max_y, 'maxZ': max_z
            }

            # NEW: Query all clashing elements in this group
            # Schema: clash_group_members (group_id, clash_id) → clash_status (clash_id, guid_a, guid_b)
            cursor.execute("""
                SELECT DISTINCT
                    em.guid,
                    em.discipline,
                    rt.minX, rt.minY, rt.minZ,
                    rt.maxX, rt.maxY, rt.maxZ
                FROM clash_group_members cgm
                JOIN clash_status cs ON cgm.clash_id = cs.clash_id
                JOIN elements_meta em ON (cs.guid_a = em.guid OR cs.guid_b = em.guid)
                JOIN elements_rtree rt ON em.id = rt.id
                WHERE cgm.group_id = ?
                  AND em.guid != (SELECT cascade_element_guid FROM clash_groups WHERE group_id = ?)
            """, (group_id, group_id))

            clashing_elements = []
            for row in cursor.fetchall():
                guid, disc, cx_min, cy_min, cz_min, cx_max, cy_max, cz_max = row
                clashing_elements.append({
                    'guid': guid,
                    'discipline': disc,
                    'bbox': {
                        'minX': cx_min, 'minY': cy_min, 'minZ': cz_min,
                        'maxX': cx_max, 'maxY': cy_max, 'maxZ': cz_max
                    }
                })

            conn.close()

            # Get coordinate offset for GPS coordinates
            coord_offset = federation_viz_helper.get_model_offset()
            if coord_offset is None:
                coord_offset = Vector((0.0, 0.0, 0.0))

            # For preview, use a simple upward offset to show proposed position
            # TODO: Calculate actual movement offset based on resolution type
            movement_offset = [0.0, 0.0, 2.0]  # Move 2m up as visual indicator

            # Debug logging
            print(f"\n=== PREVIEW DEBUG ===")
            print(f"Current bbox: minZ={bbox['minZ']:.2f}, maxZ={bbox['maxZ']:.2f}")
            print(f"Movement offset: {movement_offset}")
            print(f"Proposed bbox: minZ={bbox['minZ']+movement_offset[2]:.2f}, maxZ={bbox['maxZ']+movement_offset[2]:.2f}")
            print(f"Coordinate offset: {coord_offset}")
            print(f"Clashing elements: {len(clashing_elements)}")

            # Status message for user
            self.report({'INFO'}, f"Finding objects to highlight...")

            # POC: Try instant highlighting first (no object creation!)
            from .clash import visualization_highlight

            # Extract clashing GUIDs
            clashing_guids = [elem['guid'] for elem in clashing_elements]

            # Try instant highlight approach
            highlight_result = visualization_highlight.highlight_resolution_preview(
                cascade_guid=element_id,
                offset=movement_offset,
                clashing_guids=clashing_guids
            )

            # Check if highlighting worked (objects found in scene)
            if highlight_result.get('current'):
                # SUCCESS! Objects were found and highlighted
                print(f"✓ INSTANT HIGHLIGHT: Found and highlighted existing objects")
                print(f"  Current: {highlight_result['current'].name}")
                print(f"  Proposed: {highlight_result.get('proposed', 'N/A')}")
                print(f"  Clashing: {len(highlight_result.get('clashing', []))} elements")
                print("===================\n")

                self.report({'INFO'}, f"✓ Previewing {res_type} (highlighted {len(clashing_guids)} clashing elements)")
            else:
                # FALLBACK: Objects not loaded yet, create visualization
                print(f"⚠️  Objects not found in scene - falling back to created visualization")
                print("===================\n")

                self.report({'INFO'}, f"Creating preview visualization...")

                # Use original visualization approach
                preview_objects = visualization_3d.create_resolution_preview(
                    bbox=bbox,
                    offset=movement_offset,
                    clash_points=None,
                    coordinate_offset=coord_offset,
                    clashing_elements=clashing_elements
                )

                print(f"Preview objects created: {list(preview_objects.keys())}")

                if preview_objects:
                    obj_list = list(preview_objects.values())
                    visualization_3d.zoom_to_objects(obj_list)
                    self.report({'INFO'}, f"Previewing {res_type} resolution (Risk: {risk_level})")
                else:
                    self.report({'WARNING'}, "Preview created but no objects returned")

            return {'FINISHED'}

        except Exception as e:
            logger.exception("Failed to preview resolution")
            self.report({'ERROR'}, f"Preview failed: {str(e)}")
            return {'CANCELLED'}


class BIM_OT_apply_resolution(bpy.types.Operator):
    """Apply selected resolution and record to database"""
    bl_idname = "bim.apply_resolution"
    bl_label = "Apply Resolution"
    bl_description = "Apply the selected resolution option (records to history for learning)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            props = tool.Clash.get_clash_props()

            # Validate selection
            if props.selected_resolution_option_id == "":
                self.report({'WARNING'}, "Please select a resolution option first")
                return {'CANCELLED'}

            # Get database path
            fed_props = context.scene.BIMFederationProperties
            db_path = fed_props.federation_database_path
            if not db_path or not os.path.exists(db_path):
                self.report({'ERROR'}, "Database not found")
                return {'CANCELLED'}

            # Record application to resolution_history
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Get resolution details
            cursor.execute("""
                SELECT group_id, option_type, total_design_hours, total_design_cost
                FROM resolution_options
                WHERE option_id = ?
            """, (props.selected_resolution_option_id,))

            resolution_data = cursor.fetchone()
            if not resolution_data:
                conn.close()
                self.report({'ERROR'}, "Selected resolution not found in database")
                return {'CANCELLED'}

            group_id, res_type, estimated_hours, estimated_cost = resolution_data

            # Insert into resolution_history
            from datetime import datetime
            cursor.execute("""
                INSERT INTO resolution_history (
                    group_id, option_id, selected_by, selected_date, selection_notes
                )
                VALUES (?, ?, ?, ?, ?)
            """, (group_id, props.selected_resolution_option_id,
                  "Blender User", datetime.now(),
                  f"Applied {res_type} resolution (Estimated: {estimated_hours:.1f}hrs, ${estimated_cost:.0f})"))

            history_id = cursor.lastrowid
            conn.commit()
            conn.close()

            # Store history_id for feedback tracking
            props.last_applied_resolution_history_id = history_id

            # Show feedback panel
            props.show_feedback_panel = True

            # Convert preview to "applied" state:
            # - Restore red (current) element
            # - Keep green (proposed) element solid
            # - Restore orange (clash) elements
            from .clash import visualization_3d, visualization_highlight

            # Try instant highlight apply first
            visualization_highlight.apply_resolution_highlights()

            # Also clear old-style preview objects (fallback)
            visualization_3d.clear_preview_objects(keep_resolved=True)

            self.report({'INFO'}, f"✓ Applied {res_type}. Green shows resolved position. Provide feedback when done.")

            return {'FINISHED'}

        except Exception as e:
            logger.exception("Failed to apply resolution")
            self.report({'ERROR'}, f"Apply failed: {str(e)}")
            return {'CANCELLED'}


class BIM_OT_submit_resolution_feedback(bpy.types.Operator):
    """Submit feedback on applied resolution to improve learning"""
    bl_idname = "bim.submit_resolution_feedback"
    bl_label = "Submit Feedback"
    bl_description = "Submit actual hours and rating to improve future estimates"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            from .clash import learning_engine

            props = tool.Clash.get_clash_props()

            # Validate we have a history_id
            if props.last_applied_resolution_history_id == -1:
                self.report({'WARNING'}, "No applied resolution to provide feedback for")
                return {'CANCELLED'}

            # Validate actual hours provided
            if props.actual_hours <= 0.0:
                self.report({'WARNING'}, "Please enter actual hours spent (must be > 0)")
                return {'CANCELLED'}

            # Get database path
            fed_props = context.scene.BIMFederationProperties
            db_path = fed_props.federation_database_path
            if not db_path or not os.path.exists(db_path):
                self.report({'ERROR'}, "Database not found")
                return {'CANCELLED'}

            # Record feedback
            learning_engine.record_resolution_feedback(
                db_path=db_path,
                resolution_history_id=props.last_applied_resolution_history_id,
                user_rating=props.resolution_rating,
                actual_hours=props.actual_hours,
                variance_notes=props.variance_notes if props.variance_notes else None
            )

            # Update learned estimates
            learning_engine.update_learned_estimates(
                db_path=db_path,
                resolution_history_id=props.last_applied_resolution_history_id,
                actual_hours=props.actual_hours,
                user_rating=props.resolution_rating,
                project_id=props.project_id
            )

            self.report({'INFO'}, f"Feedback submitted! Rating: {props.resolution_rating}⭐, Actual: {props.actual_hours}hrs")

            # Reset feedback form
            props.show_feedback_panel = False
            props.last_applied_resolution_history_id = -1
            props.actual_hours = 0.0
            props.variance_notes = ""
            props.resolution_rating = 3

            return {'FINISHED'}

        except Exception as e:
            logger.exception("Failed to submit feedback")
            self.report({'ERROR'}, f"Feedback submission failed: {str(e)}")
            return {'CANCELLED'}


class BIM_OT_change_preset(bpy.types.Operator):
    """Switch configuration preset (US Market, Singapore, EU Standard)"""
    bl_idname = "bim.change_preset"
    bl_label = "Change Preset"
    bl_description = "Switch to different configuration preset"
    bl_options = {'REGISTER', 'UNDO'}

    preset_name: bpy.props.StringProperty(
        name="Preset Name",
        description="Name of preset to activate",
        default=""
    )

    def execute(self, context):
        try:
            from .clash import resolution_database

            props = tool.Clash.get_clash_props()

            if not self.preset_name:
                self.report({'WARNING'}, "No preset specified")
                return {'CANCELLED'}

            # Get database path
            fed_props = context.scene.BIMFederationProperties
            db_path = fed_props.federation_database_path
            if not db_path or not os.path.exists(db_path):
                self.report({'ERROR'}, "Database not found")
                return {'CANCELLED'}

            # Set active preset
            success = resolution_database.set_active_preset(db_path, self.preset_name)

            if success:
                props.active_preset_name = self.preset_name
                self.report({'INFO'}, f"Switched to preset: {self.preset_name}")
                return {'FINISHED'}
            else:
                self.report({'ERROR'}, f"Failed to activate preset: {self.preset_name}")
                return {'CANCELLED'}

        except Exception as e:
            logger.exception("Failed to change preset")
            self.report({'ERROR'}, f"Preset change failed: {str(e)}")
            return {'CANCELLED'}


class BIM_OT_clear_preview(bpy.types.Operator):
    """Clear all resolution preview geometry from viewport"""
    bl_idname = "bim.clear_preview"
    bl_label = "Clear Preview"
    bl_description = "Remove all preview objects from the 3D viewport"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            from .clash import visualization_3d, visualization_highlight

            # Clear both: instant highlights AND created objects
            visualization_highlight.clear_all_highlights()
            visualization_3d.clear_preview_objects()

            self.report({'INFO'}, "Preview cleared")
            return {'FINISHED'}

        except Exception as e:
            logger.exception("Failed to clear preview")
            self.report({'ERROR'}, f"Clear preview failed: {str(e)}")
            return {'CANCELLED'}


class BIM_OT_export_bcf(bpy.types.Operator):
    """Export clash detection results to BCF (BIM Collaboration Format) 2.1"""
    bl_idname = "bim.export_bcf"
    bl_label = "Export BCF"
    bl_description = "Generate BCF 2.1 file from clash detection database for use in Navisworks, Solibri, BIMcollab"
    bl_options = {'REGISTER'}

    # File picker properties
    filepath: bpy.props.StringProperty(
        name="File Path",
        description="Path for BCF file output",
        subtype='FILE_PATH'
    )

    filename_ext = ".bcfzip"

    filter_glob: bpy.props.StringProperty(
        default="*.bcfzip",
        options={'HIDDEN'}
    )

    include_resolved: bpy.props.BoolProperty(
        name="Include Resolved Clashes",
        description="Include clashes with RESOLVED status in BCF export",
        default=False
    )

    generate_snapshots: bpy.props.BoolProperty(
        name="Generate Snapshots",
        description="Render 3D snapshots for each clash (slower but provides visual context)",
        default=True
    )

    def invoke(self, context, event):
        """Open file browser when operator is invoked."""
        # Set default filename
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filepath = f"clash_report_{timestamp}.bcfzip"

        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        # Setup logging to file
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        consolelogs_dir = Path.home() / "Documents/bonsai/consolelogs"
        consolelogs_dir.mkdir(parents=True, exist_ok=True)
        log_file = consolelogs_dir / f"bcf_export_{timestamp}.log"

        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

        try:
            from .bcf import BCFGenerator, ViewpointManager, SnapshotRenderer

            # Get database path
            fed_props = context.scene.BIMFederationProperties
            db_path = fed_props.federation_database_path

            if not db_path or not os.path.exists(db_path):
                self.report({'ERROR'}, "Database not found. Run clash detection first.")
                logger.error("Database not found")
                return {'CANCELLED'}

            logger.info("="*70)
            logger.info("BCF EXPORT STARTED")
            logger.info("="*70)
            self.report({'INFO'}, "Generating BCF export...")

            # Initialize BCF components
            bcf_generator = BCFGenerator(db_path)
            viewpoint_manager = ViewpointManager()
            snapshot_renderer = SnapshotRenderer(db_path) if self.generate_snapshots else None

            # Get clashes to export (from loaded results)
            clash_props = context.scene.BIMClashProperties

            # Check if we have loaded clash results to export
            logger.info(f"Checking loaded clashes: loaded={clash_props.discipline_clash_loaded}, count={len(clash_props.discipline_clash_candidates)}")

            if clash_props.discipline_clash_loaded and clash_props.discipline_clash_candidates:
                logger.info(f"Exporting {len(clash_props.discipline_clash_candidates)} loaded clashes (not all from database)")

                # Ensure clash_status table exists before syncing
                import sqlite3
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                # Check if clash_status table exists
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='clash_status'")
                if not cursor.fetchone():
                    logger.info("Creating clash_status table (first time BCF export)")
                    # Create minimal clash_status table for BCF export
                    cursor.execute("""
                        CREATE TABLE clash_status (
                            clash_id INTEGER PRIMARY KEY AUTOINCREMENT,
                            guid_a TEXT NOT NULL,
                            guid_b TEXT NOT NULL,
                            name_a TEXT,
                            name_b TEXT,
                            ifc_class_a TEXT,
                            ifc_class_b TEXT,
                            discipline_a TEXT,
                            discipline_b TEXT,
                            status TEXT DEFAULT 'NEW',
                            assigned_to TEXT,
                            comment TEXT,
                            is_ignored INTEGER DEFAULT 0,
                            distance REAL,
                            date_created TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            date_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE(guid_a, guid_b)
                        )
                    """)
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_clash_status_guid_a ON clash_status(guid_a)")
                    cursor.execute("CREATE INDEX IF NOT EXISTS idx_clash_status_guid_b ON clash_status(guid_b)")
                    conn.commit()
                    logger.info("clash_status table created successfully")

                clash_ids = []
                for clash in clash_props.discipline_clash_candidates:
                    # Lookup disciplines from elements_meta
                    cursor.execute("SELECT discipline FROM elements_meta WHERE guid = ?", (clash.guid_a,))
                    row_a = cursor.fetchone()
                    discipline_a = row_a[0] if row_a else 'UNKNOWN'

                    cursor.execute("SELECT discipline FROM elements_meta WHERE guid = ?", (clash.guid_b,))
                    row_b = cursor.fetchone()
                    discipline_b = row_b[0] if row_b else 'UNKNOWN'

                    # Check if clash already exists
                    cursor.execute("""
                        SELECT clash_id FROM clash_status
                        WHERE (guid_a = ? AND guid_b = ?) OR (guid_a = ? AND guid_b = ?)
                    """, (clash.guid_a, clash.guid_b, clash.guid_b, clash.guid_a))
                    existing = cursor.fetchone()

                    if existing:
                        # Use existing clash_id
                        clash_ids.append(existing[0])
                    else:
                        # Insert new clash
                        cursor.execute("""
                            INSERT INTO clash_status
                            (guid_a, guid_b, name_a, name_b, ifc_class_a, ifc_class_b,
                             discipline_a, discipline_b, status, distance, is_ignored)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'NEW', ?, 0)
                        """, (
                            clash.guid_a, clash.guid_b,
                            clash.name_a, clash.name_b,
                            clash.ifc_class_a, clash.ifc_class_b,
                            discipline_a, discipline_b,
                            clash.distance
                        ))
                        clash_ids.append(cursor.lastrowid)

                conn.commit()
                conn.close()

                logger.info(f"Saved {len(clash_ids)} clashes to database, clash_ids: {clash_ids[:5]}..." if len(clash_ids) > 5 else clash_ids)
                self.report({'INFO'}, f"Exporting {len(clash_ids)} loaded clashes...")
            else:
                # No loaded clashes - fall back to exporting all from database
                # First, ensure clash_status table exists
                import sqlite3
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()

                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='clash_status'")
                if not cursor.fetchone():
                    logger.error("No clash_status table and no loaded clashes - nothing to export")
                    self.report({'ERROR'}, "No clashes to export. Run clash detection first.")
                    conn.close()
                    return {'CANCELLED'}

                # Check if there are any clashes in the database
                cursor.execute("SELECT COUNT(*) FROM clash_status WHERE is_ignored = 0")
                clash_count = cursor.fetchone()[0]
                conn.close()

                if clash_count == 0:
                    logger.info("No clashes in database to export")
                    self.report({'WARNING'}, "No clashes found in database")
                    return {'CANCELLED'}

                clash_ids = None
                logger.info(f"No loaded clashes found - exporting ALL {clash_count} clashes from database")
                self.report({'INFO'}, f"Exporting all {clash_count} clashes from database...")

            # Generate viewpoints for all clashes
            self.report({'INFO'}, "Generating 3D viewpoints...")
            viewpoints = viewpoint_manager.generate_viewpoints_for_clashes(
                db_path,
                clash_ids
            )

            # Generate snapshots if requested
            snapshots = None
            if self.generate_snapshots:
                # PERFORMANCE: Check scene size - skip snapshots for huge scenes
                scene_obj_count = len([o for o in bpy.data.objects if o.type == 'MESH'])
                snapshot_timeout = 10  # Max seconds per snapshot

                if scene_obj_count > 10000:
                    logger.warning(f"Scene has {scene_obj_count} objects - snapshot rendering disabled for performance")
                    self.report({'WARNING'}, f"Scene too large ({scene_obj_count} objects) - exporting viewpoints only (no snapshots)")
                    logger.info(f"  Estimated render time: {scene_obj_count}×30 clashes×30s = {scene_obj_count*30*30/3600:.1f} hours!")
                    logger.info("  Recommendation: Use viewpoint-only BCF export for large scenes")
                    snapshots = None
                else:
                    self.report({'INFO'}, f"Rendering {len(viewpoints)} snapshots (this may take a while)...")

                    # Note: Snapshot rendering requires clash visualization to be loaded
                    # For now, we'll skip rendering if nothing is loaded
                    try:
                        snapshots = snapshot_renderer.render_all_clash_snapshots(
                            viewpoints,
                            clash_ids,
                            width=800,
                            height=600
                        )
                        self.report({'INFO'}, f"Rendered {len(snapshots)} snapshots")
                    except Exception as e:
                        logger.warning(f"Snapshot rendering failed: {e}")
                        self.report({'WARNING'}, "Snapshot rendering failed, exporting without images")
                        snapshots = None

            # Generate BCF ZIP file
            self.report({'INFO'}, "Creating BCF file...")
            success, message = bcf_generator.generate_bcf_zip(
                self.filepath,
                clash_ids=clash_ids,
                include_resolved=self.include_resolved,
                viewpoints=viewpoints,
                snapshots=snapshots
            )

            if success:
                logger.info("="*70)
                logger.info(f"BCF EXPORT SUCCESSFUL: {self.filepath}")
                logger.info(message)
                logger.info("="*70)
                self.report({'INFO'}, f"BCF exported: {self.filepath}")
                self.report({'INFO'}, message)
                return {'FINISHED'}
            else:
                logger.error(f"BCF export failed: {message}")
                self.report({'ERROR'}, message)
                return {'CANCELLED'}

        except Exception as e:
            logger.exception("BCF export failed with exception")
            self.report({'ERROR'}, f"BCF export failed: {str(e)}")
            return {'CANCELLED'}
        finally:
            # Remove file handler to avoid duplicate logs
            logger.removeHandler(file_handler)
            file_handler.close()
