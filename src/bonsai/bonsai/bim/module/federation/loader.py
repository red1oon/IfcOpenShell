"""
Federation Loader - Three-Stage Progressive Loading System
===========================================================

Main entry point for loading federated BIM models from database v2.0.0.

Three-stage workflow:
1. Stage 1: Wireframe visualization (<1s) - instant feedback
2. Stage 2: Semantic shapes (9-12s) - working visualization
3. Stage 3: Detailed shapes (background, optional) - enhanced detail

Performance targets (VALIDATED):
- Stage 1: 0.5s for 44K elements
- Stage 2: 9.4s for 44K elements (user can work after this!)
- Stage 3: 0.5s for ~1K visible elements (background, default OFF)

Architecture: NO BLOB approach
- Complete IFC file independence
- Inference-based (semantic types, materials, dimensions computed at runtime)
- Procedural geometry generation (Bmesh)
- Database v2.0.0 only (14.93 MB)

Part of Phase 1: Three-Stage Inference-Based Loading
"""

import sqlite3
import bpy
from pathlib import Path
from typing import List, Optional, Callable
from . import stage1_wireframes
from . import stage2_semantics
from . import stage2_gpu_instancing
from . import stage2_gpu_progressive
from . import stage2_tessellation_loader
from . import stage3_details


class FederationLoader:
    """
    Three-stage progressive loader for federation visualization.

    Loads federated BIM models from SQLite database with progressive
    enhancement: wireframes → semantic shapes → detailed shapes.

    Example:
        loader = FederationLoader("/path/to/federatedmodel_merged_v2.db")
        loader.load_federation()  # Loads Stage 1 + 2 automatically
        # User can now work (routing, clashing, MEP calculations)

        # Optional: Enable detailed shapes (background, default OFF)
        loader.enable_stage3(True)
    """

    def __init__(self, db_path: str):
        """
        Initialize federation loader.

        Args:
            db_path: Path to federation database (v2.0.0)

        Raises:
            FileNotFoundError: If database doesn't exist
            ValueError: If database schema is incorrect
        """
        self.db_path = Path(db_path)

        if not self.db_path.exists():
            raise FileNotFoundError(f"Database not found: {db_path}")

        # Verify database schema version (with backward compatibility)
        conn = sqlite3.connect(str(self.db_path))
        cursor = conn.cursor()
        try:
            # Try to get schema version (optional - for v2.0.0 databases)
            try:
                cursor.execute("SELECT value FROM schema_info WHERE key = 'version'")
                result = cursor.fetchone()
                schema_version = result[0] if result else "unknown"
                print(f"Database schema version: {schema_version}")
            except sqlite3.OperationalError:
                # schema_info table doesn't exist - likely enhanced schema
                schema_version = "enhanced"
                print("Database schema: Enhanced IFC4 schema (with full metadata)")

            # Retrieve federation-wide coordinate offset for viewport centering
            # This offset centers the entire federation (all terminals) near origin
            # Try new global_offset table first (enhanced schema), fall back to site_context (old schema)
            offset_result = None

            try:
                # NEW: Try global_offset table (enhanced schema with IFC4)
                cursor.execute("SELECT offset_x, offset_y, offset_z FROM global_offset WHERE id = 1")
                offset_result = cursor.fetchone()
                if offset_result:
                    print("  Using global_offset from enhanced schema")
            except sqlite3.OperationalError:
                # Table doesn't exist, try old schema
                pass

            if not offset_result:
                # OLD: Fall back to site_context table (v2.0.0 schema)
                try:
                    cursor.execute("SELECT offset_x, offset_y, offset_z FROM site_context LIMIT 1")
                    offset_result = cursor.fetchone()
                    if offset_result:
                        print("  Using site_context from v2.0.0 schema")
                except sqlite3.OperationalError:
                    pass

            if offset_result:
                from mathutils import Vector
                self.federation_offset = Vector((
                    float(offset_result[0]),  # X offset in meters
                    float(offset_result[1]),  # Y offset in meters
                    float(offset_result[2])   # Z offset in meters
                ))
                print(f"Federation offset: ({self.federation_offset.x:.2f}m, {self.federation_offset.y:.2f}m, {self.federation_offset.z:.2f}m)")
            else:
                self.federation_offset = None
                print("Warning: No site offset found in database, using absolute coordinates")
        finally:
            conn.close()

        # Track loaded objects by stage
        self.stage1_objects = []  # Wireframe objects (empty if using GPU batch)
        self.stage1_gpu_enabled = False  # Using GPU batch drawing instead of objects
        self.stage2_objects = []  # Semantic shape objects
        self.stage2_gpu_instancing = True  # Use GPU instancing for Stage 2 (30× faster!)
        self.stage2_progressive = False  # DEFAULT: Use tessellation (exact geometry, 27s)
        self.stage3_enabled = False  # Detailed shapes toggle (default OFF)

        # Collections for organization
        self.federation_collection = None
        self.discipline_collections = {}

        # Register federation index for routing integration
        self._register_federation_index()

    def load_stage1(self, progress_callback: Optional[Callable] = None) -> List[bpy.types.Object]:
        """
        Load Stage 1: Wireframe visualization (<1 second).

        Uses GPU batch drawing for instant rendering of 44K+ elements.
        NO individual Blender objects created - pure GPU visualization.

        Args:
            progress_callback: Optional callback(current, total, message)

        Returns:
            Empty list (no objects created, GPU batch drawing used instead)

        Performance:
            - <1s for 44,190 elements (GPU batch drawing)
            - Memory: ~2-5 MB (just vertex data)
        """
        # Skip GPU visualization in background mode (GPU not available)
        if bpy.app.background:
            print("Loading Stage 1: Skipped (background mode - GPU not available)")
            self.stage1_objects = []
            self.stage1_gpu_enabled = False
            return []

        print("Loading Stage 1: GPU batch wireframe visualization...")

        # Use GPU batch drawing from clash module
        from ..clash import bbox_visualization

        success, message = bbox_visualization.enable_bbox_visualization(str(self.db_path))

        if not success:
            raise Exception(f"Failed to enable bbox visualization: {message}")

        print(f"✓ Stage 1 complete: {message}")

        # Store that we're using GPU visualization (not objects)
        self.stage1_objects = []  # No objects, using GPU batch drawing
        self.stage1_gpu_enabled = True

        return []

    def load_stage2(self, progress_callback: Optional[Callable] = None) -> List[bpy.types.Object]:
        """
        Load Stage 2: Semantic shapes (2-5 seconds with GPU instancing).

        Creates procedurally generated shapes using GPU instancing for
        ultra-fast loading. User can work with these shapes (routing, clashing, etc).

        Replaces Stage 1 wireframes with solid semantic shapes.

        Args:
            progress_callback: Optional callback(current, total, message)

        Returns:
            List of semantic shape objects created

        Performance:
            - GPU Instancing: 2-5s for 44,190 elements (30× faster!)
            - Traditional: 9.4s for 44,190 elements (VALIDATED)
            - Memory: ~10 MB (GPU instancing) vs ~108 MB (traditional)
            - User can work after this stage completes!
        """
        print("Loading Stage 2: Semantic shape generation...")

        # Create main federation collection if needed
        if not self.federation_collection:
            self.federation_collection = self._get_or_create_collection("Federation")

        # Connect to database
        conn = sqlite3.connect(str(self.db_path))

        try:
            # Load semantic shapes using GPU instancing (with optional progressive loading)
            if self.stage2_gpu_instancing:
                if self.stage2_progressive:
                    print("  Using GPU instancing with progressive loading (SURFACE-FIRST!)")
                    shapes = stage2_gpu_progressive.create_semantic_shapes_progressive(
                        conn,
                        self.federation_collection,
                        self.discipline_collections,
                        progress_callback,
                        offset=self.federation_offset
                    )
                else:
                    print("  Using tessellated geometry loading (exact IFC shapes!)")
                    shapes = stage2_tessellation_loader.load_tessellated_shapes_instanced(
                        str(self.db_path),
                        self.federation_collection,
                        self.discipline_collections,
                        progress_callback,
                        offset=self.federation_offset
                    )
            else:
                print("  Using traditional BMesh generation")
                shapes = stage2_semantics.create_semantic_shapes(
                    conn,
                    self.federation_collection,
                    self.discipline_collections,
                    progress_callback
                )

            self.stage2_objects = shapes

            print(f"✓ Stage 2 complete: {len(shapes)} semantic shapes loaded")

            # Disable GPU batch visualization (if using GPU approach)
            if self.stage1_gpu_enabled:
                from ..clash import bbox_visualization
                bbox_visualization.disable_bbox_visualization()
                self.stage1_gpu_enabled = False
                print("✓ GPU batch visualization disabled, replaced with semantic shapes")

            # Remove Stage 1 wireframe objects (if using old object approach)
            if self.stage1_objects:
                print(f"Replacing {len(self.stage1_objects)} wireframes with semantic shapes...")
                for obj in self.stage1_objects:
                    if obj and obj.name in bpy.data.objects:
                        bpy.data.objects.remove(obj, do_unlink=True)
                self.stage1_objects = []

            print("✅ USER CAN NOW WORK (routing, clashing, MEP calculations)")

            # Start background refinement (material details + Stage 3)
            # Note: For v1.0, run synchronously (background operator for v1.1)
            print("\n⏳ Running material refinement (assembly details)...")

            try:
                from . import material_refinement
                import time

                start = time.time()
                stats = material_refinement.refine_shapes_by_material(shapes)
                elapsed = time.time() - start

                print(f"✓ Material refinement complete in {elapsed:.2f}s")
                print(f"  - Linear groups: {stats.get('linear_groups_detected', 0)}")
                print(f"  - Flanges: {stats.get('flanges_added', 0)}")
                print(f"  - Seams: {stats.get('seams_added', 0)}")
                print(f"  - Elements refined: {stats.get('elements_refined', 0)}")

            except Exception as e:
                print(f"⚠ Material refinement unavailable: {e}")
                print("  (Model still fully functional for coordination work)")

            return shapes

        finally:
            conn.close()

    def enable_stage3(self, enabled: bool = True):
        """
        Toggle Stage 3: Detailed shape generation (background, optional).

        Upgrades visible semantic shapes to Level 2 detail (flanges,
        dampers, fittings, enhanced materials). Runs in background.

        Default: OFF (most users don't need this)

        Args:
            enabled: True to enable detailed shapes, False to disable

        Performance:
            - 0.5s for ~1000 visible elements (VALIDATED)
            - Runs in background (non-blocking)
            - User can toggle ON/OFF anytime

        Use Cases:
            - Presentations (needs visual polish)
            - Closeup inspection
            - Export for rendering
            - NOT needed for routine coordination work
        """
        self.stage3_enabled = enabled

        if enabled:
            print("Stage 3: Enabling detailed shapes (background)...")

            if not self.stage2_objects:
                print("⚠ No Stage 2 objects to upgrade. Load Stage 2 first.")
                return

            # Upgrade to detailed shapes using stage3 module
            stage3_details.upgrade_to_detailed_shapes(
                self.stage2_objects,
                frustum_cull=True  # Only process visible elements
            )

            print("✓ Stage 3: Detailed shapes enabled")
        else:
            print("Stage 3: Detailed shapes disabled")
            # Could optionally downgrade back to Level 1 shapes here

    def load_federation(self,
                       show_wireframes: bool = True,
                       progress_callback: Optional[Callable] = None):
        """
        Main entry point: Load federation with automatic staging.

        Workflow:
        1. Show Stage 1 wireframes (instant feedback)
        2. Automatically transition to Stage 2 semantic shapes
        3. User can work after Stage 2 completes
        4. Stage 3 only if user explicitly enables it

        Args:
            show_wireframes: Show Stage 1 first (default True for UX)
            progress_callback: Optional callback(current, total, message)

        Returns:
            List of final loaded objects (Stage 2)

        Example:
            loader = FederationLoader("federatedmodel_merged_v2.db")
            objects = loader.load_federation()
            # User can now route conduits, detect clashes, etc.
        """
        print("=" * 70)
        print("FEDERATION LOADER - Three-Stage Progressive Loading")
        print("=" * 70)
        print(f"Database: {self.db_path}")
        print()

        # Stage 1: Wireframes (instant feedback)
        if show_wireframes:
            self.load_stage1(progress_callback)
            # Small delay to let user see wireframes appear
            # (Stage 2 will replace them automatically)

        # Stage 2: Semantic shapes (working visualization)
        semantic_objects = self.load_stage2(progress_callback)

        print()
        print("=" * 70)
        print("✅ FEDERATION LOADED - Ready for coordination work")
        print("=" * 70)
        print(f"Total objects: {len(semantic_objects)}")
        print(f"Disciplines: {len(self.discipline_collections)}")
        print()
        print("User can now:")
        print("  - Route conduits")
        print("  - Detect clashes")
        print("  - Perform MEP calculations")
        print("  - Generate reports")
        print()
        print("Optional: Enable detailed shapes (View → Show Detailed Shapes)")
        print("=" * 70)

        return semantic_objects

    def _get_or_create_collection(self, name: str) -> bpy.types.Collection:
        """
        Get or create a Blender collection.

        Args:
            name: Collection name

        Returns:
            Blender collection
        """
        if name in bpy.data.collections:
            return bpy.data.collections[name]

        collection = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(collection)
        return collection

    def _register_federation_index(self):
        """
        Register federation index for routing integration.

        This enables conduit routing and clash detection to work with
        the loaded federation database.

        Sets up:
        - bpy.types.WindowManager.federation_index (FederationIndex object)
        - BIMFederationProperties.index_loaded = True
        - BIMFederationProperties.federation_database_path
        """
        try:
            from .spatial_index import FederationIndex

            # Skip if already loaded
            if hasattr(bpy.types.WindowManager, 'federation_index'):
                print("  Federation index already registered")
                return

            print(f"  Registering federation index for routing...")

            # Create and build federation index
            index = FederationIndex(self.db_path)
            index.build()  # Validates schema and loads statistics (instant)

            # Store reference in window manager (persists across scenes)
            bpy.types.WindowManager.federation_index = index

            # Update properties (if scene exists)
            if hasattr(bpy.context, 'scene') and hasattr(bpy.context.scene, 'BIMFederationProperties'):
                props = bpy.context.scene.BIMFederationProperties
                stats = index.get_statistics()
                props.index_loaded = True
                props.total_elements = stats['total_elements']
                props.loaded_disciplines = ', '.join(stats['disciplines'])
                props.federation_database_path = str(self.db_path)

                print(f"  ✓ Federation index registered: {stats['total_elements']:,} elements")
                print(f"  ✓ Conduit routing and clash detection now enabled")
            else:
                print(f"  ✓ Federation index registered (scene properties unavailable)")

        except Exception as e:
            print(f"  ⚠ Warning: Could not register federation index: {e}")
            print(f"     Routing functionality may be limited")
            import traceback
            traceback.print_exc()


# Convenience function for quick loading
def load_federation(db_path: str,
                   progress_callback: Optional[Callable] = None) -> List[bpy.types.Object]:
    """
    Quick load federation from database.

    Convenience function for simple use cases.

    Args:
        db_path: Path to federation database (v2.0.0)
        progress_callback: Optional progress callback

    Returns:
        List of loaded objects

    Example:
        objects = load_federation("/path/to/federatedmodel_merged_v2.db")
    """
    loader = FederationLoader(db_path)
    return loader.load_federation(progress_callback=progress_callback)
