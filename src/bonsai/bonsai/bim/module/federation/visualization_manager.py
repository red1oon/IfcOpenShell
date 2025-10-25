"""
Multi-Layer Visualization Manager

Manages 3 visualization modes for federation viewport:
1. BBOXES - Fast wireframe boxes (<1s)
2. SEMANTICS - Simple 3D shapes (~24s)
3. MATERIALS - Detailed materials (~30s)

Architecture:
- All 3 layers loaded simultaneously (one-time cost)
- Switch modes by hiding/showing collections (instant <0.1s)
- Memory: ~153 MB (acceptable for 44K elements)

Benefits:
- Professional UX (like Navisworks/Revit)
- Instant mode switching
- Only pay load cost once
"""

import bpy
import time


class VisualizationManager:
    """
    Manages multi-layer federation viewport with instant mode switching.

    Collection Structure:
    └── Federation_Viewport
        ├── Federation_BBoxes (Layer 1)
        │   ├── Discipline_ARC
        │   ├── Discipline_STR
        │   └── ... (7 disciplines)
        ├── Federation_Semantics (Layer 2)
        │   ├── Discipline_ARC
        │   ├── Discipline_STR
        │   └── ... (7 disciplines)
        └── Federation_Materials (Layer 3)
            ├── Discipline_ARC
            ├── Discipline_STR
            └── ... (7 disciplines)
    """

    # Collection name patterns for each mode
    LAYER_NAMES = {
        'BBOXES': 'Federation_BBoxes',
        'SEMANTICS': 'Federation_Semantics',
        'MATERIALS': 'Federation_Materials'
    }

    def __init__(self, db_path):
        """
        Initialize visualization manager.

        Args:
            db_path: Path to federation database
        """
        self.db_path = db_path
        self.loaded_layers = set()  # Track which layers are loaded

    def load_all_layers(self, progress_callback=None):
        """
        Load all 3 visualization layers.

        Architecture Note:
        - BBOXES uses GPU batch visualization (toggled on/off, not objects)
        - SEMANTICS uses Stage 2 objects (with GPU instancing)
        - MATERIALS uses Stage 2 objects + material refinement

        Since BBOXES is GPU-based, we only need to load SEMANTICS layer.
        MATERIALS is handled by toggling material properties on SEMANTICS objects.

        Args:
            progress_callback: Optional callback for progress updates

        Returns:
            Dict with timing info
        """
        from . import loader

        print("\n" + "="*70)
        print("LOADING VISUALIZATION LAYERS (Smart Multi-Layer)")
        print("="*70)

        timing = {}

        # Create loader
        fed_loader = loader.FederationLoader(self.db_path)
        fed_loader.stage2_gpu_instancing = True  # Use GPU instancing for speed

        # Layer: Semantics (base layer for both SEMANTICS and MATERIALS modes)
        if progress_callback:
            progress_callback("Loading semantic shapes...")

        start = time.time()
        print("\n[1/1] Loading Semantics layer (base for all modes)...")
        fed_loader.load_stage2()
        self._rename_collections_for_layer('SEMANTICS')
        timing['semantics'] = time.time() - start
        print(f"  ✓ Semantics loaded in {timing['semantics']:.2f}s")
        self.loaded_layers.add('SEMANTICS')

        # BBOXES uses GPU batch (no loading needed, enabled on-demand)
        # MATERIALS uses same objects as SEMANTICS (just material toggle)
        timing['bboxes'] = 0.0  # GPU batch visualization
        timing['materials'] = 0.0  # Same as semantics

        total_time = sum(timing.values())
        print(f"\n✓ Base layer loaded in {total_time:.2f}s")
        print(f"  BBOXES mode: GPU batch visualization (instant toggle)")
        print(f"  SEMANTICS mode: Loaded objects ({len(fed_loader.stage2_objects):,})")
        print(f"  MATERIALS mode: Same objects + material display")
        print(f"  Memory footprint: ~10-50 MB (GPU instancing)")
        print("="*70)

        return timing

    def switch_mode(self, mode):
        """
        Switch visualization mode instantly.

        BBOXES mode: GPU batch visualization (wireframes)
        SEMANTICS mode: Stage 2 objects with basic materials
        MATERIALS mode: Stage 2 objects with enhanced materials

        Args:
            mode: 'BBOXES', 'SEMANTICS', or 'MATERIALS'

        Returns:
            Time taken to switch (should be <0.1s)
        """
        start = time.time()

        # Validate mode
        if mode not in self.LAYER_NAMES:
            raise ValueError(f"Invalid mode: {mode}. Must be BBOXES, SEMANTICS, or MATERIALS")

        print(f"\nSwitching to {mode} mode...")

        if mode == 'BBOXES':
            # Enable GPU batch visualization, hide semantic objects
            from ..clash import bbox_visualization
            bbox_visualization.enable_bbox_visualization(str(self.db_path))

            # Hide semantic layer
            if 'Federation_Semantics' in bpy.data.collections:
                bpy.data.collections['Federation_Semantics'].hide_viewport = True
                bpy.data.collections['Federation_Semantics'].hide_render = True

        elif mode in ['SEMANTICS', 'MATERIALS']:
            # Disable GPU batch visualization, show semantic objects
            try:
                from ..clash import bbox_visualization
                bbox_visualization.disable_bbox_visualization()
            except:
                pass  # GPU batch might not be active

            # Show semantic layer
            if 'Federation_Semantics' in bpy.data.collections:
                bpy.data.collections['Federation_Semantics'].hide_viewport = False
                bpy.data.collections['Federation_Semantics'].hide_render = False

            # For MATERIALS mode, could enhance material display here
            # (For now, SEMANTICS and MATERIALS show the same thing)
            # TODO: Add material enhancement toggle when material_refinement is ready

        elapsed = time.time() - start
        print(f"  ✓ Switched in {elapsed*1000:.3f}ms")

        return elapsed

    def is_layer_loaded(self, mode):
        """
        Check if visualization mode is available.

        BBOXES: Always available (GPU batch visualization)
        SEMANTICS/MATERIALS: Check if semantic collection exists

        Args:
            mode: 'BBOXES', 'SEMANTICS', or 'MATERIALS'

        Returns:
            True if mode is available
        """
        if mode == 'BBOXES':
            # GPU batch always available if database exists
            return True

        # SEMANTICS and MATERIALS both use the Semantics collection
        return 'Federation_Semantics' in bpy.data.collections

    def are_all_layers_loaded(self):
        """
        Check if all visualization modes are available.

        Returns:
            True if semantic layer is loaded (BBOXES always available)
        """
        # Only need to check if semantic layer exists
        # BBOXES uses GPU batch (always available)
        # MATERIALS uses same objects as SEMANTICS
        return 'Federation_Semantics' in bpy.data.collections

    def unload_all_layers(self):
        """
        Remove all visualization layers and free memory.
        """
        print("\n" + "="*70)
        print("UNLOADING ALL VISUALIZATION LAYERS")
        print("="*70)

        # Disable GPU batch visualization
        try:
            from ..clash import bbox_visualization
            bbox_visualization.disable_bbox_visualization()
            print("  Disabled GPU batch visualization")
        except:
            pass

        # Remove semantic collections
        removed_count = 0

        if 'Federation_Semantics' in bpy.data.collections:
            layer_coll = bpy.data.collections['Federation_Semantics']
            obj_count = self._count_objects_recursive(layer_coll)

            # Remove all objects
            self._remove_collection_recursive(layer_coll)

            print(f"  Removed Federation_Semantics ({obj_count:,} objects)")
            removed_count += 1

        # Clean up orphaned data
        self._cleanup_orphaned_data()

        self.loaded_layers.clear()

        print(f"\n✓ Unloaded all visualization layers")
        print("="*70)

    def _rename_collections_for_layer(self, mode):
        """
        Rename collections to include layer identifier.

        This allows multiple layers to coexist without naming conflicts.

        Args:
            mode: 'BBOXES', 'SEMANTICS', or 'MATERIALS'
        """
        layer_name = self.LAYER_NAMES[mode]

        # Find or create layer parent collection
        if layer_name not in bpy.data.collections:
            layer_coll = bpy.data.collections.new(layer_name)
            bpy.context.scene.collection.children.link(layer_coll)
        else:
            layer_coll = bpy.data.collections[layer_name]

        # Move discipline collections under layer parent
        disciplines = ['ACMV', 'ARC', 'CW', 'ELEC', 'FP', 'SP', 'STR']

        for disc in disciplines:
            # Look for newly created discipline collections
            for pattern in [f"Discipline_{disc}", f"Federation_{disc}"]:
                if pattern in bpy.data.collections:
                    disc_coll = bpy.data.collections[pattern]

                    # Unlink from scene root
                    if disc_coll.name in bpy.context.scene.collection.children:
                        bpy.context.scene.collection.children.unlink(disc_coll)

                    # Link under layer parent
                    if disc_coll.name not in layer_coll.children:
                        layer_coll.children.link(disc_coll)

        # Also handle Templates collection
        if "Templates" in bpy.data.collections:
            templates_coll = bpy.data.collections["Templates"]
            if templates_coll.name in bpy.context.scene.collection.children:
                bpy.context.scene.collection.children.unlink(templates_coll)
            if templates_coll.name not in layer_coll.children:
                layer_coll.children.link(templates_coll)

    def _count_objects_recursive(self, collection):
        """Count all objects in collection and sub-collections"""
        count = len(collection.objects)
        for child in collection.children:
            count += self._count_objects_recursive(child)
        return count

    def _remove_collection_recursive(self, collection):
        """Remove collection and all sub-collections"""
        # Remove child collections first
        for child in list(collection.children):
            self._remove_collection_recursive(child)

        # Unlink from all parents
        for scene in bpy.data.scenes:
            if collection.name in scene.collection.children:
                scene.collection.children.unlink(collection)

        # Unlink from parent collections
        for parent in bpy.data.collections:
            if collection.name in parent.children:
                parent.children.unlink(collection)

        # Remove all objects
        for obj in list(collection.objects):
            bpy.data.objects.remove(obj, do_unlink=True)

        # Remove collection
        bpy.data.collections.remove(collection)

    def _cleanup_orphaned_data(self):
        """Remove orphaned meshes and materials"""
        # Clean meshes
        mesh_count = 0
        for mesh in bpy.data.meshes:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
                mesh_count += 1

        # Clean materials
        mat_count = 0
        for mat in bpy.data.materials:
            if 'Federation' in mat.name and mat.users == 0:
                bpy.data.materials.remove(mat)
                mat_count += 1

        print(f"  Cleaned {mesh_count:,} orphaned meshes")
        print(f"  Cleaned {mat_count} orphaned materials")
