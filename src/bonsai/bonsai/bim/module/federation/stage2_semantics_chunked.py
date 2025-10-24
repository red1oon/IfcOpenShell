"""
Stage 2: Semantic Shape Generation (Chunked/Batch Loading)
============================================================

Chunked version for non-blocking UI during loading.
Processes elements in small batches (100 per tick) to keep UI responsive.

Part of Phase 1: Three-Stage Inference-Based Loading
"""

import bpy
import bmesh
import sqlite3
from mathutils import Vector, Euler
from typing import List, Optional, Callable, Dict, Tuple
from . import semantic_utils
from ..clash import shape_templates


class ChunkedSemanticLoader:
    """
    Batch loader for Stage 2 semantic shapes.

    Allows processing elements in small chunks to keep UI responsive.
    """

    def __init__(self, db_conn: sqlite3.Connection,
                 parent_collection: bpy.types.Collection,
                 discipline_collections: Dict[str, bpy.types.Collection],
                 batch_size: int = 100):
        """
        Initialize chunked loader.

        Args:
            db_conn: SQLite database connection
            parent_collection: Parent federation collection
            discipline_collections: Dict to store discipline collections
            batch_size: Number of elements to process per tick (default 100)
        """
        self.db_conn = db_conn
        self.parent_collection = parent_collection
        self.discipline_collections = discipline_collections
        self.batch_size = batch_size

        # Get site offset to bring objects to origin
        cursor = db_conn.cursor()
        cursor.execute("SELECT site_offset_x, site_offset_y, site_offset_z FROM site_context LIMIT 1")
        offset_row = cursor.fetchone()

        if offset_row:
            # Convert from mm to meters and negate (to subtract from world coords)
            self.offset_x = -offset_row[0] / 1000.0
            self.offset_y = -offset_row[1] / 1000.0
            self.offset_z = -offset_row[2] / 1000.0
            print(f"  Applying site offset: ({self.offset_x:.2f}, {self.offset_y:.2f}, {self.offset_z:.2f}) m")
        else:
            self.offset_x = self.offset_y = self.offset_z = 0.0
            print("  ⚠ No site offset found in database")

        # Query all elements at initialization
        cursor.execute("""
            SELECT
                m.guid,
                m.ifc_class,
                m.discipline,
                r.min_x, r.max_x,
                r.min_y, r.max_y,
                r.min_z, r.max_z,
                t.pos_x, t.pos_y, t.pos_z,
                t.rot_x, t.rot_y, t.rot_z,
                t.scale_x, t.scale_y, t.scale_z
            FROM elements_meta m
            JOIN elements_rtree r ON m.id = r.id
            JOIN element_transforms t ON m.id = t.element_id
        """)

        self.elements = cursor.fetchall()
        self.total = len(self.elements)
        self.current_index = 0
        self.shapes = []

        print(f"  Chunked loader initialized: {self.total:,} elements")
        print(f"  Batch size: {self.batch_size}")
        print(f"  Estimated ticks: {(self.total + self.batch_size - 1) // self.batch_size}")

    def is_complete(self) -> bool:
        """Check if loading is complete"""
        return self.current_index >= self.total

    def get_progress(self) -> Tuple[int, int, float]:
        """
        Get current progress.

        Returns:
            Tuple of (current, total, percentage)
        """
        percentage = (self.current_index / self.total * 100) if self.total > 0 else 100
        return (self.current_index, self.total, percentage)

    def process_next_batch(self) -> List[bpy.types.Object]:
        """
        Process next batch of elements.

        Returns:
            List of objects created in this batch
        """
        if self.is_complete():
            return []

        # Calculate batch range
        start_idx = self.current_index
        end_idx = min(start_idx + self.batch_size, self.total)
        batch_elements = self.elements[start_idx:end_idx]

        batch_shapes = []

        for elem in batch_elements:
            guid, ifc_class, discipline = elem[0:3]
            min_x, max_x, min_y, max_y, min_z, max_z = elem[3:9]
            pos_x, pos_y, pos_z = elem[9:12]
            rot_x, rot_y, rot_z = elem[12:15]
            scale_x, scale_y, scale_z = elem[15:18]

            # Convert bbox from mm to meters
            bbox = {
                'min_x': min_x / 1000.0, 'max_x': max_x / 1000.0,
                'min_y': min_y / 1000.0, 'max_y': max_y / 1000.0,
                'min_z': min_z / 1000.0, 'max_z': max_z / 1000.0,
            }

            # Infer semantic type
            semantic_type = semantic_utils.get_semantic_type(ifc_class)

            # Extract dimensions from bbox
            dimensions = semantic_utils.extract_profile_dimensions(bbox, semantic_type)

            # Create Bmesh shape based on semantic type
            obj = self._create_semantic_object(
                guid, semantic_type, dimensions, discipline, ifc_class
            )

            if obj:
                # Apply transform from database WITH site offset correction
                # Position: convert from mm to m, then apply offset to bring to origin
                obj.location = Vector((
                    pos_x / 1000.0 + self.offset_x,
                    pos_y / 1000.0 + self.offset_y,
                    pos_z / 1000.0 + self.offset_z
                ))

                # Rotation (radians)
                obj.rotation_euler = Euler((rot_x, rot_y, rot_z), 'XYZ')

                # Scale
                obj.scale = Vector((scale_x, scale_y, scale_z))

                # Add to appropriate collection
                disc_collection = self._get_or_create_discipline_collection(discipline)
                disc_collection.objects.link(obj)

                batch_shapes.append(obj)
                self.shapes.append(obj)

        # Update progress
        self.current_index = end_idx

        return batch_shapes

    def _create_semantic_object(self, guid: str, semantic_type: str,
                                dimensions: dict, discipline: str,
                                ifc_class: str) -> Optional[bpy.types.Object]:
        """Create semantic shape using shape templates"""

        # Create Bmesh based on semantic type
        bm = bmesh.new()

        if semantic_type == 'pipe':
            shape_templates.create_pipe_basic(bm, dimensions)
        elif semantic_type == 'duct':
            shape_templates.create_duct_basic(bm, dimensions)
        elif semantic_type == 'cable_tray':
            shape_templates.create_cable_tray_basic(bm, dimensions)
        elif semantic_type == 'conduit':
            shape_templates.create_conduit_basic(bm, dimensions)
        elif semantic_type == 'beam':
            shape_templates.create_beam_basic(bm, dimensions)
        elif semantic_type == 'column':
            shape_templates.create_column_basic(bm, dimensions)
        elif semantic_type == 'wall':
            shape_templates.create_wall_basic(bm, dimensions)
        elif semantic_type == 'slab':
            shape_templates.create_slab_basic(bm, dimensions)
        elif semantic_type == 'equipment':
            shape_templates.create_equipment_basic(bm, dimensions)
        else:
            # Generic box for unknown types
            shape_templates.create_generic_box(bm, dimensions)

        # Create mesh from Bmesh
        mesh = bpy.data.meshes.new(f"{semantic_type}_{guid}")
        bm.to_mesh(mesh)
        bm.free()

        # Create object
        obj = bpy.data.objects.new(guid, mesh)

        # Store metadata
        obj["federation_stage"] = 2
        obj["federation_guid"] = guid
        obj["federation_discipline"] = discipline
        obj["federation_ifc_class"] = ifc_class
        obj["federation_semantic_type"] = semantic_type

        # Assign material
        mat = self._get_or_create_material(discipline, semantic_type)
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)

        return obj

    def _get_or_create_discipline_collection(self, discipline: str) -> bpy.types.Collection:
        """Get or create collection for discipline"""
        if discipline not in self.discipline_collections:
            coll = bpy.data.collections.new(f"Federation_{discipline}")
            self.parent_collection.children.link(coll)
            self.discipline_collections[discipline] = coll

        return self.discipline_collections[discipline]

    def _get_or_create_material(self, discipline: str, semantic_type: str) -> bpy.types.Material:
        """Get or create material for discipline"""
        mat_name = f"Federation_{discipline}"

        if mat_name in bpy.data.materials:
            return bpy.data.materials[mat_name]

        # Create new material with discipline color
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True

        # Get discipline color
        from ..clash.shape_templates import DISCIPLINE_COLORS
        color = DISCIPLINE_COLORS.get(discipline, DISCIPLINE_COLORS['DEFAULT'])

        # Set color in shader
        nodes = mat.node_tree.nodes
        bsdf = nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = color

        return mat
