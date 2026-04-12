# Bonsai - OpenBIM Blender Add-on
# Copyright (C) 2025 Your Engineering Firm
#
# This file is part of Bonsai.
#
# Bonsai is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""
Qualified Path: src/bonsai/bonsai/bim/module/federation/operator.py

Federation Module Operators
----------------------------
User-triggered actions for multi-model federation management.
"""

import os
import json
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import bpy
from bpy.types import Operator
from bpy.props import StringProperty, IntProperty
from bpy_extras.io_utils import ImportHelper


class AddFederatedFile(Operator):
    """Add a new IFC file to the federation"""
    bl_idname = "bim.add_federated_file"
    bl_label = "Add Federated File"
    bl_description = "Add an IFC file to the multi-model federation"
    bl_options = {"REGISTER", "UNDO"}
    
    def execute(self, context):
        props = context.scene.BIMFederationProperties
        new_file = props.federated_files.add()
        new_file.name = ""
        new_file.discipline = ""
        return {"FINISHED"}


class RemoveFederatedFile(Operator):
    """Remove a file from the federation"""
    bl_idname = "bim.remove_federated_file"
    bl_label = "Remove Federated File"
    bl_description = "Remove this file from the federation"
    bl_options = {"REGISTER", "UNDO"}
    
    index: IntProperty()
    
    def execute(self, context):
        props = context.scene.BIMFederationProperties
        props.federated_files.remove(self.index)
        return {"FINISHED"}


class SelectFederatedFile(Operator, ImportHelper):
    """Select IFC file(s) to add to federation"""
    bl_idname = "bim.select_federated_file"
    bl_label = "Select IFC File(s)"
    bl_description = "Select one or multiple IFC files to add to the federation"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".ifc"
    filter_glob: StringProperty(default="*.ifc;*.ifczip", options={"HIDDEN"})
    index: IntProperty(options={"HIDDEN"})
    files: bpy.props.CollectionProperty(type=bpy.types.OperatorFileListElement, options={"HIDDEN", "SKIP_SAVE"})
    directory: StringProperty(subtype='DIR_PATH', options={"HIDDEN"})

    def execute(self, context):
        props = context.scene.BIMFederationProperties

        # Multi-file selection
        if self.files:
            # Remove the placeholder entry that triggered this operator
            if self.index < len(props.federated_files):
                props.federated_files.remove(self.index)

            # Add all selected files
            for file_elem in self.files:
                file_path = Path(self.directory) / file_elem.name
                new_file = props.federated_files.add()
                new_file.name = str(file_path)
                new_file.discipline = self._detect_discipline(file_path)
        else:
            # Single file selection (backwards compatibility)
            federated_file = props.federated_files[self.index]
            federated_file.name = self.filepath
            federated_file.discipline = self._detect_discipline(Path(self.filepath))

        return {"FINISHED"}
    
    def _detect_discipline(self, file_path: Path) -> str:
        """Auto-detect discipline tag from filename"""
        stem = file_path.stem.upper()
        
        # Split by both hyphen and underscore
        import re
        parts = re.split(r'[-_]', stem)
        
        # Known discipline codes (add more as needed)
        known_disciplines = [
            'STR', 'ACMV', 'ARC', 'ELEC', 'FP', 'SP', 'CW',
            'STRUCT', 'ARCH', 'HVAC', 'MECH', 'PLUMB', 'FIRE'
        ]
        
        # Look for known discipline in parts
        for part in parts:
            if part in known_disciplines:
                return part
        
        # Fallback: find first 2-4 letter alphabetic part
        for part in parts:
            if 2 <= len(part) <= 4 and part.isalpha():
                return part
        
        # Last resort: first 10 chars
        return stem[:10]


class SelectFederatedFolder(Operator):
    """Scan a folder and add all IFC files to federation"""
    bl_idname = "bim.select_federated_folder"
    bl_label = "Scan Folder for IFC Files"
    bl_description = "Select a folder and automatically add all IFC files found"
    bl_options = {"REGISTER", "UNDO"}

    directory: StringProperty(subtype='DIR_PATH')

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        props = context.scene.BIMFederationProperties

        if not self.directory:
            self.report({'WARNING'}, "No folder selected")
            return {'CANCELLED'}

        folder_path = Path(self.directory)

        if not folder_path.exists() or not folder_path.is_dir():
            self.report({'ERROR'}, f"Invalid folder: {folder_path}")
            return {'CANCELLED'}

        # Scan for IFC files
        ifc_files = sorted(folder_path.glob("*.ifc")) + sorted(folder_path.glob("*.ifczip"))

        if not ifc_files:
            self.report({'WARNING'}, f"No IFC files found in {folder_path}")
            return {'CANCELLED'}

        # Clear existing file list
        props.federated_files.clear()

        # Add all found IFC files
        for ifc_path in ifc_files:
            new_file = props.federated_files.add()
            new_file.name = str(ifc_path)

            # Auto-detect discipline from filename
            stem = ifc_path.stem.upper()
            import re
            parts = re.split(r'[-_]', stem)

            known_disciplines = [
                'STR', 'ACMV', 'ARC', 'ELEC', 'FP', 'SP', 'CW',
                'STRUCT', 'ARCH', 'HVAC', 'MECH', 'PLUMB', 'FIRE', 'LPG'
            ]

            discipline = ''
            for part in parts:
                if part in known_disciplines:
                    discipline = part
                    break

            if not discipline:
                for part in parts:
                    if 2 <= len(part) <= 4 and part.isalpha():
                        discipline = part
                        break

            new_file.discipline = discipline or stem[:10]

        self.report({'INFO'}, f"Added {len(ifc_files)} IFC files from {folder_path.name}")
        return {'FINISHED'}


class PreprocessFederatedModels(Operator):
    """Run preprocessing to extract bounding boxes from all federated files"""
    bl_idname = "bim.preprocess_federated_models"
    bl_label = "Preprocess Federation"
    bl_description = "Extract bounding boxes from all federated IFC files.\n" \
                     "This may take several minutes for large projects"
    bl_options = {"REGISTER"}
    
    @classmethod
    def poll(cls, context):
        props = context.scene.BIMFederationProperties
        if not props.federated_files:
            cls.poll_message_set("Add IFC files to federation first")
            return False
        if not props.federation_database_path:
            cls.poll_message_set("Set output database path first")
            return False
        if props.preprocessing_in_progress:
            cls.poll_message_set("Preprocessing already in progress")
            return False
        return True
    
    def execute(self, context):
        from .prop import get_default_federation_db_path

        props = context.scene.BIMFederationProperties

        # Validate all files exist
        file_paths = []
        disciplines = []
        for fed_file in props.federated_files:
            if not fed_file.name:
                self.report({'ERROR'}, "Some files have empty paths")
                return {"CANCELLED"}

            file_path = Path(fed_file.name)
            if not file_path.exists():
                self.report({'ERROR'}, f"File not found: {file_path.name}")
                return {"CANCELLED"}

            file_paths.append(str(file_path.absolute()))
            disciplines.append(fed_file.discipline or "UNKNOWN")

        # Use auto-default if database path is empty
        db_path_str = props.federation_database_path or get_default_federation_db_path()
        db_path = Path(db_path_str)

        # Auto-set the property if it was empty (so user sees the path)
        if not props.federation_database_path:
            props.federation_database_path = str(db_path)

        progress_path = db_path.with_suffix('.json')
        props.progress_json_path = str(progress_path)
        
        # Build command to run preprocessing script
        # Assumes federation_preprocessor.py is in same directory as this file
        script_dir = Path(__file__).parent
        preprocessor_script = script_dir / "federation_preprocessor.py"
        
        if not preprocessor_script.exists():
            self.report({'ERROR'}, f"Preprocessor script not found: {preprocessor_script}")
            return {"CANCELLED"}
        
        self.report({'INFO'}, f"Starting preprocessing of {len(file_paths)} files...")

        # Run preprocessing directly in-process (subprocess doesn't have ifcopenshell access)
        try:
            # Import and run the preprocessor main function directly
            from . import federation_preprocessor

            # Build args namespace to match command-line interface
            class Args:
                def __init__(self):
                    self.files = file_paths
                    self.output = str(db_path.absolute())
                    self.disciplines = disciplines
                    self.progress = str(progress_path)

            # Run in separate thread to avoid blocking UI
            import threading

            def run_preprocessing():
                try:
                    # Temporarily replace sys.argv for argparse
                    old_argv = sys.argv
                    sys.argv = [
                        'federation_preprocessor.py',
                        '--files', *file_paths,
                        '--output', str(db_path.absolute()),
                        '--disciplines', *disciplines,
                        '--progress', str(progress_path)
                    ]
                    federation_preprocessor.main()
                    sys.argv = old_argv
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    props.preprocessing_in_progress = False

            threading.Thread(target=run_preprocessing, daemon=True).start()

            props.preprocessing_in_progress = True
            self.report({'INFO'}, f"Preprocessing started. Check progress at: {progress_path.name}")

            # Register a timer to check progress
            bpy.app.timers.register(
                lambda: self._check_preprocessing_progress(context),
                first_interval=2.0,
                persistent=True
            )

        except Exception as e:
            # Log to ERROR.log
            error_log = Path.home() / "Documents/bonsai/ERROR.log"
            try:
                import traceback
                import datetime
                with open(error_log, "a") as f:
                    f.write(f"\n{'='*70}\n")
                    f.write(f"{datetime.datetime.now()} - PreprocessFederatedModels\n")
                    f.write(f"{'='*70}\n")
                    f.write(traceback.format_exc())
            except:
                pass

            self.report({'ERROR'}, f"Failed to start preprocessing: {str(e)}")
            traceback.print_exc()
            return {"CANCELLED"}
        
        return {"FINISHED"}
    
    def _check_preprocessing_progress(self, context):
        """Timer callback to check preprocessing progress"""
        props = context.scene.BIMFederationProperties
        
        if not props.preprocessing_in_progress:
            return None  # Stop timer
        
        progress_path = Path(props.progress_json_path)
        
        if not progress_path.exists():
            return 2.0  # Check again in 2 seconds
        
        try:
            with open(progress_path, 'r') as f:
                progress_data = json.load(f)
            
            status = progress_data.get('status', 'unknown')
            
            if status == 'completed':
                # Update properties
                props.preprocessing_in_progress = False
                
                # Mark files as preprocessed
                for fed_file in props.federated_files:
                    fed_file.is_preprocessed = True
                
                # Update element counts from progress data
                for file_stat in progress_data.get('files', []):
                    for fed_file in props.federated_files:
                        if Path(fed_file.name).name == file_stat['filename']:
                            fed_file.element_count = file_stat['elements']
                
                print(f"\n✓ Preprocessing completed: {progress_data['total_elements']} elements")
                return None  # Stop timer
            
            elif status == 'failed':
                props.preprocessing_in_progress = False
                print("\n✗ Preprocessing failed. Check console for errors.")
                return None  # Stop timer
            
            else:
                # Still in progress
                files_done = progress_data.get('files_processed', 0)
                total_elements = progress_data.get('total_elements', 0)
                print(f"  Preprocessing: {files_done} files, {total_elements} elements...")
                return 5.0  # Check again in 5 seconds
        
        except Exception as e:
            print(f"Error checking progress: {e}")
            return 5.0  # Try again


class LoadFederationIndex(Operator):
    """Load the federation spatial index"""
    bl_idname = "bim.load_federation_index"
    bl_label = "Load Federation Index"
    bl_description = "Load the preprocessed federation index (SQLite R-tree) for spatial queries"
    bl_options = {"REGISTER"}
    
    @classmethod
    def poll(cls, context):
        props = context.scene.BIMFederationProperties
        if props.index_loaded:
            cls.poll_message_set("Index already loaded")
            return False
        if not props.federation_database_path:
            cls.poll_message_set("Set federation database path first")
            return False
        # Resolve Blender's // relative path prefix
        db_path_resolved = bpy.path.abspath(props.federation_database_path)
        if not Path(db_path_resolved).exists():
            cls.poll_message_set("Database file does not exist. Run preprocessing first")
            return False
        return True
    
    def execute(self, context):
        from .core.spatial_index import FederationIndex
        from .prop import get_default_federation_db_path

        props = context.scene.BIMFederationProperties

        # Use auto-default if path is empty
        db_path_str = props.federation_database_path or get_default_federation_db_path()
        db_path = Path(db_path_str)

        self.report({'INFO'}, f"Loading federation index from {db_path.name}...")
        
        try:
            # Create and validate index (SQLite R-tree already built during preprocessing)
            # Store in window manager so it persists across scene changes
            index = FederationIndex(db_path)
            index.build()  # Validates schema and loads statistics (instant)
            
            # Store reference in window manager (persists across scenes)
            bpy.types.WindowManager.federation_index = index
            
            # Update properties
            stats = index.get_statistics()
            props.index_loaded = True
            props.total_elements = stats['total_elements']
            props.loaded_disciplines = ', '.join(stats['disciplines'])
            
            self.report({'INFO'}, 
                       f"✓ Federation index loaded: {stats['total_elements']:,} elements from "
                       f"{stats['discipline_count']} disciplines")
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to load index: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"CANCELLED"}
        
        return {"FINISHED"}


class UnloadFederationIndex(Operator):
    """Unload the federation index from memory"""
    bl_idname = "bim.unload_federation_index"
    bl_label = "Unload Federation Index"
    bl_description = "Unload the federation index from memory to free resources"
    bl_options = {"REGISTER"}
    
    @classmethod
    def poll(cls, context):
        props = context.scene.BIMFederationProperties
        return props.index_loaded
    
    def execute(self, context):
        props = context.scene.BIMFederationProperties
        
        try:
            # Clear index
            if hasattr(bpy.types.WindowManager, 'federation_index'):
                bpy.types.WindowManager.federation_index.clear()
                del bpy.types.WindowManager.federation_index
            
            # Update properties
            props.index_loaded = False
            props.total_elements = 0
            props.loaded_disciplines = ""
            
            self.report({'INFO'}, "Federation index unloaded")
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to unload index: {str(e)}")
            return {"CANCELLED"}
        
        return {"FINISHED"}


class QueryFederationIndex(Operator):
    """Run integration tests on federation system"""
    bl_idname = "bim.query_federation_index"
    bl_label = "Run System Tests"
    bl_description = "Run integration tests to validate:\n" \
                     "• Federation index loads correctly\n" \
                     "• Spatial queries work\n" \
                     "• Conduit routing can access index\n" \
                     "• Clash detection can access index\n" \
                     "• Database schema is valid"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        props = context.scene.BIMFederationProperties
        if not props.index_loaded:
            cls.poll_message_set("Load federation index first")
            return False
        return True

    def execute(self, context):
        """Run comprehensive integration test suite"""
        print("\n" + "="*70)
        print("FEDERATION SYSTEM INTEGRATION TESTS")
        print("="*70)

        test_results = {
            'passed': 0,
            'failed': 0,
            'errors': []
        }

        # Test 1: Federation index accessible
        if not self._test_index_accessible(context, test_results):
            self.report({'ERROR'}, "Critical: Index not accessible. Aborting tests.")
            return {"CANCELLED"}

        # Test 2: Spatial queries functional
        self._test_spatial_queries(context, test_results)

        # Test 3: Conduit routing integration
        self._test_conduit_routing_integration(context, test_results)

        # Test 4: Clash detection integration
        self._test_clash_detection_integration(context, test_results)

        # Test 5: Database schema validation
        self._test_database_schema(context, test_results)

        # Summary
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        print(f"✓ Passed: {test_results['passed']}")
        print(f"✗ Failed: {test_results['failed']}")

        if test_results['errors']:
            print("\nErrors:")
            for error in test_results['errors']:
                print(f"  • {error}")

        print("="*70 + "\n")

        # Report to UI
        if test_results['failed'] == 0:
            self.report({'INFO'}, f"✓ All {test_results['passed']} tests passed")
            return {"FINISHED"}
        else:
            self.report({'WARNING'},
                       f"{test_results['failed']} tests failed, {test_results['passed']} passed")
            return {"FINISHED"}

    def _test_index_accessible(self, context, results: dict) -> bool:
        """Test 1: Check if federation index is accessible in memory"""
        print("\n[Test 1/5] Federation Index Accessibility")
        print("-" * 70)

        try:
            if not hasattr(bpy.types.WindowManager, 'federation_index'):
                results['failed'] += 1
                results['errors'].append("Index not found in WindowManager")
                print("✗ FAILED: Index not found in memory")
                return False

            index = bpy.types.WindowManager.federation_index
            stats = index.get_statistics()

            print(f"✓ PASSED: Index accessible")
            print(f"  • Total elements: {stats['total_elements']:,}")
            print(f"  • Disciplines: {stats['discipline_count']}")
            print(f"  • Classes: {len(stats['ifc_classes'])}")
            results['passed'] += 1
            return True

        except Exception as e:
            results['failed'] += 1
            results['errors'].append(f"Index accessibility: {str(e)}")
            print(f"✗ FAILED: {e}")
            return False

    def _test_spatial_queries(self, context, results: dict):
        """Test 2: Validate spatial queries return results"""
        print("\n[Test 2/5] Spatial Query Functionality")
        print("-" * 70)

        try:
            index = bpy.types.WindowManager.federation_index

            # Test query: 10m cube at origin
            buffer = 5000  # 5 meters in mm
            results_origin = index.query_by_bbox(
                (-buffer, -buffer, -buffer),
                (buffer, buffer, buffer)
            )

            print(f"✓ PASSED: Spatial query executed")
            print(f"  • Query: 10m cube at origin")
            print(f"  • Results: {len(results_origin)} elements")

            # Group by discipline
            by_discipline = {}
            for element in results_origin:
                by_discipline.setdefault(element.discipline, []).append(element)

            for discipline, elements in sorted(by_discipline.items()):
                print(f"    - {discipline}: {len(elements)} elements")

            results['passed'] += 1

        except Exception as e:
            results['failed'] += 1
            results['errors'].append(f"Spatial query: {str(e)}")
            print(f"✗ FAILED: {e}")

    def _test_conduit_routing_integration(self, context, results: dict):
        """Test 3: Check conduit routing can access federation index and ELEC elements exist"""
        print("\n[Test 3/5] Conduit Routing Integration (ELEC Detection)")
        print("-" * 70)

        try:
            # Verify index is accessible to routing
            index = bpy.types.WindowManager.federation_index

            # Test 1: Verify ELEC elements exist in database
            stats = index.get_statistics()
            disciplines = stats.get('disciplines', set())

            if 'ELEC' not in disciplines:
                print("✗ FAILED: No ELEC elements found in federation")
                print("  • Required for conduit routing tests")
                print(f"  • Available disciplines: {', '.join(sorted(disciplines))}")
                results['failed'] += 1
                results['errors'].append("ELEC discipline not found in federation")
                return

            # Test 2: Query ELEC elements to verify they're accessible
            elec_elements = index.query_by_discipline('ELEC')

            if not elec_elements:
                print("✗ FAILED: ELEC discipline exists but no elements returned")
                results['failed'] += 1
                results['errors'].append("ELEC query returned no elements")
                return

            print(f"✓ PASSED: ELEC detection working")
            print(f"  • ELEC elements found: {len(elec_elements):,}")
            print(f"  • Conduit routing can now use ELEC as obstacles")

            # Test 3: Can routing access obstacle detection?
            # This simulates what routing does - query for obstacles in a corridor
            test_corridor = index.query_by_bbox(
                (-1000, -1000, 0),
                (1000, 1000, 3000)
            )

            print(f"  • Simulated corridor query: {len(test_corridor)} obstacles")
            results['passed'] += 1

        except Exception as e:
            results['failed'] += 1
            results['errors'].append(f"Conduit routing: {str(e)}")
            print(f"✗ FAILED: {e}")

    def _test_clash_detection_integration(self, context, results: dict):
        """Test 4: Check clash detection can access federation index"""
        print("\n[Test 4/5] Clash Detection Integration")
        print("-" * 70)

        try:
            # Check if clash properties exist
            if not hasattr(context.scene, 'BIMClashProperties'):
                print("⚠ SKIPPED: Clash Detection module not loaded")
                results['passed'] += 1
                return

            index = bpy.types.WindowManager.federation_index

            # Test: Can clash detection query by discipline?
            stats = index.get_statistics()
            disciplines = list(stats['disciplines'])

            if len(disciplines) < 2:
                print(f"⚠ WARNING: Only {len(disciplines)} discipline(s) - need 2+ for clash testing")

            # Test discipline-based query (what clash detection does)
            if disciplines:
                disc_a = disciplines[0]
                elements_a = index.query_by_discipline(disc_a)
                print(f"✓ PASSED: Clash detection can access index")
                print(f"  • Test discipline '{disc_a}': {len(elements_a)} elements")
                results['passed'] += 1
            else:
                results['failed'] += 1
                results['errors'].append("No disciplines found in index")
                print("✗ FAILED: No disciplines in index")

        except Exception as e:
            results['failed'] += 1
            results['errors'].append(f"Clash detection: {str(e)}")
            print(f"✗ FAILED: {e}")

    def _test_database_schema(self, context, results: dict):
        """Test 5: Validate database schema integrity"""
        print("\n[Test 5/5] Database Schema Validation")
        print("-" * 70)

        try:
            import sqlite3

            props = context.scene.BIMFederationProperties
            # Resolve Blender's // relative path prefix
            db_path = Path(bpy.path.abspath(props.federation_database_path))

            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Check required tables exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}

            required_tables = {'elements_meta', 'elements_rtree'}
            missing_tables = required_tables - tables

            if missing_tables:
                results['failed'] += 1
                results['errors'].append(f"Missing tables: {missing_tables}")
                print(f"✗ FAILED: Missing tables: {missing_tables}")
                conn.close()
                return

            # Check schema of elements_meta
            cursor.execute("PRAGMA table_info(elements_meta)")
            columns = {row[1] for row in cursor.fetchall()}

            required_columns = {'guid', 'discipline', 'ifc_class', 'filepath'}
            missing_columns = required_columns - columns

            if missing_columns:
                results['failed'] += 1
                results['errors'].append(f"Missing columns: {missing_columns}")
                print(f"✗ FAILED: Missing columns in elements_meta: {missing_columns}")
            else:
                print(f"✓ PASSED: Database schema valid")
                print(f"  • Tables: {', '.join(sorted(tables))}")
                print(f"  • Elements table columns: {len(columns)}")
                results['passed'] += 1

            conn.close()

        except Exception as e:
            results['failed'] += 1
            results['errors'].append(f"Schema validation: {str(e)}")
            print(f"✗ FAILED: {e}")

    def _run_legacy_simple_query(self, context):
        """Legacy simple query (kept for reference)"""
        index = bpy.types.WindowManager.federation_index

        buffer = 5000
        results = index.query_by_bbox(
            (-buffer, -buffer, -buffer),
            (buffer, buffer, buffer)
        )

        print("\nSimple Query Results:")
        print(f"  Total elements: {len(results)}")

        by_discipline = {}
        for element in results:
            by_discipline.setdefault(element.discipline, []).append(element)

        for discipline, elements in by_discipline.items():
            print(f"  {discipline}: {len(elements)} elements")

        print("\nFirst 5 elements:")
        for element in results[:5]:
            print(f"    {element}")

class LoadFederationModel(bpy.types.Operator):
    """Load federated model with three-stage progressive loading (non-blocking)"""
    bl_idname = "bim.load_federation_model"
    bl_label = "Load Federation Model"
    bl_description = "Load federated BIM model from database (three-stage loading)"
    bl_options = {'REGISTER', 'UNDO'}

    filepath: bpy.props.StringProperty(
        name="Database Path",
        description="Path to federation database (.db file)",
        subtype='FILE_PATH'
    )

    def execute(self, context):
        from .loader import FederationLoader
        import time

        if not self.filepath:
            self.report({'ERROR'}, "No database path specified")
            return {'CANCELLED'}

        try:
            print("\n" + "=" * 70)
            print("FEDERATION MODEL LOADING - NON-BLOCKING")
            print("=" * 70)

            start_time = time.time()

            # Create loader
            loader = FederationLoader(self.filepath)

            # Configure loading mode from UI properties
            props = context.scene.BIMFederationProperties
            if props.use_tessellation:
                # Use tessellation (exact geometry, 27s)
                loader.stage2_progressive = False
                print("  ⚙️  Loading Mode: TESSELLATION (exact IFC geometry)")
            else:
                # Use progressive (approximate geometry, 9s)
                loader.stage2_progressive = True
                print("  ⚙️  Loading Mode: PROGRESSIVE (approximate procedural)")

            # Load Stage 1 only (wireframes - instant)
            print("\n🔷 Loading Stage 1: Wireframes (instant feedback)...")
            wireframes = loader.load_stage1()
            elapsed_stage1 = time.time() - start_time

            print(f"\n✅ Stage 1 complete!")
            print(f"  - Wireframes: {len(wireframes):,}")
            print(f"  - Time: {elapsed_stage1:.2f}s")
            print(f"  - User can now work with wireframes!")
            print("=" * 70)

            self.report({'INFO'}, f"Stage 1 loaded: {len(wireframes):,} wireframes. Stage 2 loading in background...")

            # Store loader in scene for background operator
            context.scene['federation_loader_db_path'] = self.filepath

            # Start background Stage 2 loading
            bpy.ops.bim.load_federation_stage2_background()

            return {'FINISHED'}

        except Exception as e:
            print(f"\n❌ Failed to load federation: {e}")
            import traceback
            traceback.print_exc()

            self.report({'ERROR'}, f"Failed to load federation: {str(e)}")
            return {'CANCELLED'}

    def invoke(self, context, event):
        # Open file browser
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class LoadFederationStage2Background(bpy.types.Operator):
    """Load Stage 2 in background (non-blocking chunked modal operator)"""
    bl_idname = "bim.load_federation_stage2_background"
    bl_label = "Load Stage 2 (Background)"
    bl_description = "Load semantic shapes in background without blocking UI (chunked)"

    _timer = None
    _chunked_loader = None
    _start_time = None
    _db_conn = None
    _federation_loader = None

    def modal(self, context, event):
        if event.type == 'TIMER':
            # This runs every timer tick (non-blocking)

            # Initialize generator on first tick
            if not hasattr(self, '_generator'):
                db_path = context.scene.get('federation_loader_db_path')
                if not db_path:
                    self.report({'ERROR'}, "No database path found")
                    self.cancel(context)
                    return {'CANCELLED'}

                print("\n" + "=" * 70)
                print("🔷 STAGE 2: CHUNKED BACKGROUND LOADING")
                print("=" * 70)
                print(f"  Mode: NON-BLOCKING (100 elements per 0.1s tick)")
                print(f"  UI: FULLY RESPONSIVE during loading")
                print("=" * 70)

                try:
                    from .loader import FederationLoader
                    from .stage2_semantics_chunked import ChunkedSemanticLoader
                    import sqlite3
                    import time

                    print("  ✓ Imports successful")

                    # Recreate loader (just for collections, don't load anything)
                    self._federation_loader = FederationLoader(db_path)

                    # Configure loading mode from UI properties
                    props = context.scene.BIMFederationProperties
                    if props.use_tessellation:
                        self._federation_loader.stage2_progressive = False
                        print("  ⚙️  Loading Mode: TESSELLATION (exact IFC geometry)")
                    else:
                        self._federation_loader.stage2_progressive = True
                        print("  ⚙️  Loading Mode: PROGRESSIVE (approximate procedural)")

                    print("  ✓ FederationLoader created")

                    # Open database connection
                    self._db_conn = sqlite3.connect(db_path)
                    print("  ✓ Database connected")

                    # Get or create Federation collection
                    # NOTE: Clearing disabled for POC - allows scene bloating for testing
                    # User can manually restart Blender between tests if needed
                    federation_coll = bpy.data.collections.get("Federation")
                    if not federation_coll:
                        print("  Creating new Federation collection...")
                        federation_coll = bpy.data.collections.new("Federation")
                        bpy.context.scene.collection.children.link(federation_coll)
                    else:
                        print("  ⚠ Federation collection exists - scene may bloat (clearing disabled for POC)")
                        print("     Restart Blender between tests to clear scene")

                    # Use NEW NON-BLOCKING progressive GPU instancing loader!
                    print("  ✓ Using NON-BLOCKING PROGRESSIVE GPU INSTANCING (GENERATOR) ⚡")
                    from . import stage2_gpu_progressive_generator

                    self._discipline_collections = {}
                    self._start_time = time.time()

                    # Create generator for non-blocking loading
                    self._generator = stage2_gpu_progressive_generator.create_semantic_shapes_progressive_generator(
                        self._db_conn,
                        federation_coll,
                        self._discipline_collections
                    )

                    print("  ✓ Generator initialized - will process in chunks")
                    print("=" * 70)

                except Exception as e:
                    print(f"\n❌ FAILED to initialize chunked loader: {e}")
                    import traceback
                    traceback.print_exc()
                    self.report({'ERROR'}, f"Initialization failed: {str(e)}")
                    self.cancel(context)
                    return {'CANCELLED'}

                return {'RUNNING_MODAL'}

            # Process next batch from generator
            if hasattr(self, '_generator'):
                try:
                    result = next(self._generator)

                    if result['status'] == 'batch_complete':
                        # Update progress
                        priority = result['priority']
                        processed = result['processed']
                        total = result['total']
                        elapsed = result['elapsed']
                        pct = (processed / total) * 100

                        print(f"  ⏳ Priority {priority} yielded: {processed:,}/{total:,} ({pct:.1f}%) - {elapsed:.1f}s elapsed")
                        print(f"  🖱️  UI is RESPONSIVE - you can work now!")

                        # Continue processing next batch in next modal tick
                        return {'RUNNING_MODAL'}

                    elif result['status'] == 'complete':
                        # Loading finished!
                        print(f"\n✅ GENERATOR COMPLETE!")
                        self._shapes = result['instances']
                        self._loading_complete = True

                        # Fall through to completion handling below

                except StopIteration:
                    # Generator exhausted (shouldn't happen with proper yield)
                    print(f"\n✅ GENERATOR EXHAUSTED")
                    self._loading_complete = True

            # Check if loading complete
            if getattr(self, '_loading_complete', False):
                import time
                elapsed = time.time() - self._start_time
                shapes = getattr(self, '_shapes', [])

                print(f"\n✅ PROGRESSIVE LOADING COMPLETE! ⚡")
                print(f"  - Semantic shapes: {len(shapes):,}")
                print(f"  - Time: {elapsed:.2f}s")
                print(f"  - Average: {elapsed/len(shapes)*1000:.2f}ms per element")
                print(f"  - Surface elements appeared FIRST (killer UX!)")

                # NOW remove Stage 1 wireframes (atomic swap)
                # Find all Stage 1 wireframes in scene (can't rely on stored references)
                wireframes_to_remove = [
                    obj for obj in bpy.data.objects
                    if obj.get("federation_stage") == 1
                ]

                if wireframes_to_remove:
                    print(f"  - Replacing {len(wireframes_to_remove):,} wireframes with semantic shapes...")
                    for obj in wireframes_to_remove:
                        bpy.data.objects.remove(obj, do_unlink=True)
                else:
                    print(f"  ⚠ No Stage 1 wireframe objects found")

                # Disable GPU batch wireframes (Stage 1)
                print(f"  - Disabling Stage 1 GPU wireframes...")
                try:
                    from . import bbox_visualization
                    success, msg = bbox_visualization.disable_bbox_visualization()
                    if success:
                        print(f"  ✓ GPU wireframes disabled: {msg}")
                    else:
                        print(f"  ⚠ Could not disable wireframes: {msg}")
                except Exception as e:
                    print(f"  ⚠ Error disabling wireframes: {e}")

                print("✅ USER CAN NOW WORK (routing, clashing, MEP calculations)")
                print("=" * 70)

                self.report({'INFO'}, f"Stage 2 loaded: {len(shapes):,} shapes in {elapsed:.2f}s")

                # Stage 3: Upgrade to detailed shapes (optional, in background)
                print(f"\n🔧 Starting Stage 3: Detailed shape upgrade...")
                try:
                    from . import stage3_details
                    stage3_details.upgrade_to_detailed_shapes(
                        objects=shapes,
                        frustum_cull=True  # Only upgrade visible objects
                    )
                    print(f"✅ Stage 3 complete - shapes upgraded to Level 2 detail")
                except Exception as e:
                    print(f"⚠ Stage 3 failed (shapes remain at Level 1): {e}")

                # Force final viewport update
                for area in context.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()

                # Clean up
                self._db_conn.close()
                self.cancel(context)
                return {'FINISHED'}

        return {'PASS_THROUGH'}

    def execute(self, context):
        # Start modal timer (0.1s = 100ms per tick)
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.1, window=context.window)
        wm.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        # Clean up timer
        wm = context.window_manager
        if self._timer:
            wm.event_timer_remove(self._timer)


# ── S180: Stingy Mesh Loader ─────────────────────────────────────────────────

class FedRTreeLoadMesh(bpy.types.Operator):
    """Load exact mesh geometry for the active selection (LOD400 linked ref, max 500).

    L2 element selected → load 1 mesh by geometry_hash.
    L1 building selected → load ARC meshes within envelope × 1.2, LIMIT 500.
    Geometry linked from library.blend (link=True). No fallback — hard fail if not found.
    """
    bl_idname = "bim.fed_rtree_load_mesh"
    bl_label = "Load Mesh"
    bl_description = (
        "Load LOD400 geometry (linked from library.blend) for selected element or building.\n"
        "RTree wireframes remain. Use SHRED to remove."
    )
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return self.execute(context)

    def execute(self, context):
        import time
        import sqlite3
        import bpy as _bpy
        from . import bbox_visualization as bv
        from pathlib import Path

        props = context.scene.BIMFederationProperties
        db_path = bv._db_path_cache
        lib_path = bv._library_blend_cache

        if not db_path or not Path(db_path).exists():
            raise RuntimeError("[S180] R-Tree not loaded — run Preview first")
        if not lib_path or not Path(lib_path).exists():
            raise RuntimeError(f"[S180] library.blend not found (searched from {Path(db_path).parent})")

        t0 = time.time()

        # ── Determine load target ──
        sel_elem = bv._selected_element  # set by fly_to_element
        active_bld = bv._active_building

        # ── Diagnostic: log exactly what is active at call time ──
        _sel_guid = sel_elem.get('guid', 'none')[:24] if sel_elem else 'none'
        _sel_bbox = sel_elem.get('bbox') if sel_elem else None
        _sel_bbox_str = (f"Z[{_sel_bbox[2]:.3f}→{_sel_bbox[5]:.3f}] dZ={_sel_bbox[5]-_sel_bbox[2]:.3f}m"
                         if _sel_bbox else 'no_bbox')
        print(f"[S180] §DIAG_LOAD sel_guid={_sel_guid} sel_bbox={_sel_bbox_str} "
              f"active_bld={active_bld or 'none'}")

        if sel_elem and sel_elem.get('guid'):
            # L2: single element by guid → geometry_hash
            guid = sel_elem['guid']
            label = f"Loaded_{guid[:8]}"
            rows = self._query_single(db_path, guid)
            if not rows:
                raise RuntimeError(f"[S180] No geometry_hash for guid {guid[:16]}")
        elif active_bld:
            # L1: building ARC elements within envelope × buffer
            label = f"Loaded_{active_bld}_ARC"
            bbox = next((r['bbox'] for r in bv._search_results
                         if r.get('building') == active_bld), None)
            rows = (self._query_building(db_path, active_bld, bbox)
                    if bbox else self._query_building_no_bbox(db_path, active_bld))
            if not rows:
                raise RuntimeError(f"[S180] No ARC geometry found for {active_bld}")
        else:
            self.report({'WARNING'}, "Select a building (L1) or fly to an element (L2) first")
            return {'CANCELLED'}

        # ── Deduplicate hashes — skip NULLs ──
        hash_to_guid = {}
        for row_guid, ghash in rows:
            if ghash and ghash not in hash_to_guid:
                hash_to_guid[ghash] = row_guid
        wanted_hashes = list(hash_to_guid.keys())
        if not wanted_hashes:
            raise RuntimeError(f"[S180] No valid geometry hashes for selection")

        # ── Remove stale collection with same label ──
        if label in bv._loaded_collections:
            _remove_stingy_collection(label, bv._loaded_collections)

        # ── Link meshes from library.blend (LOD400, link=True — no local copy) ──
        with _bpy.data.libraries.load(lib_path, link=True) as (data_from, data_to):
            available = set(data_from.meshes)
            data_to.meshes = [h for h in wanted_hashes if h in available]

        # ── Geo-hash hell check: BLOCKER if any mesh was renamed ──
        loaded_meshes = [m for m in data_to.meshes if m is not None]
        for mesh in loaded_meshes:
            if mesh.name not in hash_to_guid:
                raise RuntimeError(
                    f"[S180] §GEO_HASH_HELL {mesh.name} — renamed by Blender "
                    f"(expected one of {list(hash_to_guid)[:3]})"
                )
        print(f"[S180] §PROOF NO_COLLISION hashes={len(loaded_meshes)} all_names_match=True")

        # ── Build collection + place objects with full transform ──
        col = _bpy.data.collections.new(label)
        _bpy.context.scene.collection.children.link(col)

        off = bv._model_offset
        ox = off.x if off else 0.0
        oy = off.y if off else 0.0
        oz = off.z if off else 0.0

        placed = 0
        no_transform = 0
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        for mesh in loaded_meshes:
            ghash = mesh.name
            row_guid = hash_to_guid[ghash]
            obj = _bpy.data.objects.new(ghash, mesh)
            obj.hide_select = False
            col.objects.link(obj)

            # Fetch transform + DB bbox in one query so we can verify placement
            cur.execute("""
                SELECT t.center_x, t.center_y, t.center_z,
                       t.rotation_x, t.rotation_y, t.rotation_z,
                       r.minX, r.minY, r.minZ, r.maxX, r.maxY, r.maxZ
                FROM element_transforms t
                JOIN elements_meta m ON t.guid = m.guid
                JOIN elements_rtree r ON m.id = r.id
                WHERE t.guid = ?
                LIMIT 1
            """, (row_guid,))
            tr = cur.fetchone()
            if tr:
                cx, cy, cz, rx, ry, rz, mnX, mnY, mnZ, mxX, mxY, mxZ = tr
                rx = rx or 0.0
                ry = ry or 0.0
                rz = rz or 0.0
                bx, by, bz = cx - ox, cy - oy, cz - oz
                obj.location = (bx, by, bz)
                obj.rotation_euler = (rx, ry, rz)
                # §TRANSFORM: verify Blender position is inside element's DB bbox
                in_bbox = (mnX - ox <= bx <= mxX - ox and
                           mnY - oy <= by <= mxY - oy and
                           mnZ - oz <= bz <= mxZ - oz)
                bbox_dZ = mxZ - mnZ
                print(f"[S180] §TRANSFORM hash={ghash[:12]} "
                      f"ifc=({cx:.3f},{cy:.3f},{cz:.3f}) "
                      f"rot=({rx:.4f},{ry:.4f},{rz:.4f}) "
                      f"blender=({bx:.3f},{by:.3f},{bz:.3f}) "
                      f"db_bbox_Z=[{mnZ:.3f}→{mxZ:.3f}] dZ={bbox_dZ:.3f}m "
                      f"center_in_bbox={in_bbox}")
                if not in_bbox:
                    print(f"[S180] §TRANSFORM_FAIL hash={ghash[:12]} "
                          f"center NOT inside DB bbox — check IFC placement convention")
                placed += 1
            else:
                no_transform += 1
                print(f"[S180] §WARN_NO_TRANSFORM hash={ghash[:12]} guid={row_guid[:20]}")

        conn.close()

        # ── Register + report ──
        bv._loaded_collections[label] = [obj.name for obj in col.objects]
        props.rtree_last_loaded = label

        elapsed = time.time() - t0
        print(f"[S180] §PROOF LOAD_MESH label={label} hashes={placed} elapsed={elapsed:.1f}s")
        self.report({'INFO'}, f"§PROOF LOAD_MESH label={label} hashes={placed} elapsed={elapsed:.1f}s")

        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        return {'FINISHED'}

    # ── SQL helpers ──

    def _query_single(self, db_path, guid):
        import sqlite3
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT m.guid, i.geometry_hash "
            "FROM elements_meta m JOIN element_instances i ON m.guid = i.guid "
            "WHERE m.guid = ?", (guid,)
        ).fetchall()
        conn.close()
        return rows

    def _query_building(self, db_path, building, bbox):
        import sqlite3
        mnX, mnY, mnZ, mxX, mxY, mxZ = bbox
        conn = sqlite3.connect(db_path)
        rows = conn.execute("""
            SELECT m.guid, i.geometry_hash
            FROM elements_meta m
            JOIN element_instances i ON m.guid = i.guid
            JOIN elements_rtree r ON m.id = r.id
            WHERE m.building = ?
              AND m.discipline = 'ARC'
              AND r.minX <= ? AND r.maxX >= ?
              AND r.minY <= ? AND r.maxY >= ?
            LIMIT 500
        """, (building, mxX * 1.2, mnX * 0.8, mxY * 1.2, mnY * 0.8)).fetchall()
        conn.close()
        return rows

    def _query_building_no_bbox(self, db_path, building):
        import sqlite3
        conn = sqlite3.connect(db_path)
        rows = conn.execute("""
            SELECT m.guid, i.geometry_hash
            FROM elements_meta m
            JOIN element_instances i ON m.guid = i.guid
            WHERE m.building = ? AND m.discipline = 'ARC'
            LIMIT 500
        """, (building,)).fetchall()
        conn.close()
        return rows


def _remove_stingy_collection(label, registry):
    """Unlink a stingy-loaded collection from the viewport.

    Objects are unlinked from their collection (disappear from viewport).
    Mesh datablocks (linked from library.blend) are NOT touched — they live
    in the library and must never be deleted here.
    """
    col = bpy.data.collections.get(label)
    if col:
        for obj in list(col.objects):
            col.objects.unlink(obj)  # remove from viewport; keep mesh datablock
        # Unlink the collection from the scene
        scene_col = bpy.context.scene.collection
        if col.name in {c.name for c in scene_col.children}:
            scene_col.children.unlink(col)
        bpy.data.collections.remove(col)
    registry.pop(label, None)


class FedRTreeShred(bpy.types.Operator):
    """Remove selected loaded mesh objects (or last-loaded collection if nothing selected).

    Selection-based: select objects in viewport → SHRED removes only those.
    Fallback: if nothing selected, removes the last-loaded collection entirely.
    RTree GPU wireframes are never touched.
    """
    bl_idname = "bim.fed_rtree_shred"
    bl_label = "Shred"
    bl_description = (
        "Select loaded mesh objects → SHRED removes those only.\n"
        "Nothing selected: removes last LOAD MESH collection."
    )
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return self.execute(context)

    def execute(self, context):
        from . import bbox_visualization as bv

        props = context.scene.BIMFederationProperties

        # Build reverse map: object_name → collection_label
        obj_to_label = {}
        for lbl, obj_names in bv._loaded_collections.items():
            for name in obj_names:
                obj_to_label[name] = lbl

        # ── Selection-based path: remove selected objects that belong to stingy loads ──
        selected_loaded = [
            obj for obj in context.selected_objects
            if obj.name in obj_to_label
        ]

        if selected_loaded:
            removed = 0
            affected_labels = set()
            for obj in selected_loaded:
                lbl = obj_to_label[obj.name]
                affected_labels.add(lbl)
                # Unlink from all collections — viewport removal only.
                # Do NOT delete mesh datablocks (they live in library.blend).
                for col in list(obj.users_collection):
                    col.objects.unlink(obj)
                removed += 1

            # Clean up empty collections from registry
            for lbl in affected_labels:
                col = bpy.data.collections.get(lbl)
                remaining = [o for o in (col.objects if col else [])]
                if not remaining:
                    if col:
                        scene_col = bpy.context.scene.collection
                        if col.name in {c.name for c in scene_col.children}:
                            scene_col.children.unlink(col)
                        bpy.data.collections.remove(col)
                    bv._loaded_collections.pop(lbl, None)
                    if props.rtree_last_loaded == lbl:
                        props.rtree_last_loaded = ""
                else:
                    bv._loaded_collections[lbl] = [o.name for o in remaining]

            print(f"[S180] §PROOF SHRED selected objects_removed={removed} labels={sorted(affected_labels)}")
            self.report({'INFO'}, f"§PROOF SHRED objects_removed={removed}")

        else:
            # ── Fallback: remove last-loaded collection ──
            label = props.rtree_last_loaded
            if not label:
                self.report({'WARNING'}, "Nothing to shred — select loaded mesh objects or run LOAD MESH first")
                return {'CANCELLED'}
            if label not in bv._loaded_collections:
                props.rtree_last_loaded = ""
                self.report({'WARNING'}, f"Collection '{label}' not in registry (already removed?)")
                return {'CANCELLED'}

            _remove_stingy_collection(label, bv._loaded_collections)
            props.rtree_last_loaded = ""
            print(f"[S180] §PROOF SHRED label={label}")
            self.report({'INFO'}, f"§PROOF SHRED label={label}")

        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        return {'FINISHED'}


class DetectFederationClashes(bpy.types.Operator):
    """Detect clashes using database (NO IFC required)"""
    bl_idname = "bim.detect_federation_clashes"
    bl_label = "Detect Clashes (Database)"
    bl_description = "Run bbox-based clash detection on federation database"
    bl_options = {'REGISTER'}

    tolerance_mm: bpy.props.FloatProperty(
        name="Tolerance (mm)",
        description="Clash tolerance in millimeters",
        default=10.0,
        min=0.0,
        max=1000.0
    )

    def execute(self, context):
        from .clash import detector as bbox_clash_detector
        import time

        props = context.scene.BIMFederationProperties
        db_path = props.federation_database_path

        if not db_path:
            self.report({'ERROR'}, "No federation database loaded")
            return {'CANCELLED'}

        try:
            print("\n" + "=" * 70)
            print("DATABASE-DRIVEN CLASH DETECTION")
            print("=" * 70)

            start_time = time.time()

            # Run bbox clash detection
            clashes = bbox_clash_detector.detect_clashes_from_database(
                db_path,
                tolerance_mm=self.tolerance_mm
            )

            elapsed = time.time() - start_time

            # Group by discipline
            grouped = bbox_clash_detector.group_clashes_by_discipline(clashes)

            print(f"\n✅ Clash detection complete!")
            print(f"  - Time: {elapsed:.2f}s")
            print(f"  - Total clashes: {len(clashes):,}")
            print(f"\nClashes by discipline pair:")
            for pair, pair_clashes in sorted(grouped.items()):
                print(f"  - {pair}: {len(pair_clashes):,} clashes")

            # Export to clash database
            clash_db = db_path.replace('.db', '_clashes.db')
            bbox_clash_detector.export_clashes_to_database(
                clashes, clash_db, "Default"
            )

            print(f"\n✓ Exported to: {clash_db}")
            print("=" * 70)

            self.report({'INFO'},
                f"Found {len(clashes):,} clashes in {elapsed:.2f}s"
            )

            return {'FINISHED'}

        except Exception as e:
            print(f"\n❌ Clash detection failed: {e}")
            import traceback
            traceback.print_exc()

            self.report({'ERROR'}, f"Clash detection failed: {str(e)}")
            return {'CANCELLED'}


class PreviewFederationViewport(bpy.types.Operator):
    """Fast preview with GPU bbox wireframes (instant, MEP-ready)"""
    bl_idname = "bim.preview_federation_viewport"
    bl_label = "Preview Viewport"
    bl_description = "Instant GPU wireframe preview - Start MEP work immediately"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.BIMFederationProperties

        if not props.federation_database_path:
            self.report({'ERROR'}, "No federation database selected")
            return {'CANCELLED'}

        # Start logging
        from . import logging_utils
        log_path = logging_utils.start_file_logging()
        print(f"📝 Logging to: {log_path}")

        try:
            print(f"\n{'='*70}")
            print("PREVIEW MODE: Instant GPU BBox Wireframes")
            print(f"{'='*70}\n")

            # Register federation index first for routing/clashing
            if not hasattr(bpy.types.WindowManager, 'federation_index'):
                print("  Registering federation index for MEP routing...")
                from .core.spatial_index import FederationIndex
                # Resolve Blender's // relative path prefix
                db_path_resolved = bpy.path.abspath(props.federation_database_path)
                index = FederationIndex(db_path_resolved)
                index.build()
                bpy.types.WindowManager.federation_index = index
                stats = index.get_statistics()
                print(f"  ✓ Federation index registered: {stats.get('total_elements', 0):,} elements")
                print(f"  ✓ Conduit routing and clash detection now enabled\n")

            # Mark index as loaded so Test Conduit button lights up (always set, even if index already exists)
            props.index_loaded = True

            # Load instant GPU bbox wireframes
            from . import bbox_visualization, discipline_legend

            success, message = bbox_visualization.enable_bbox_visualization(
                str(props.federation_database_path)
            )

            if not success:
                self.report({'ERROR'}, f"Preview failed: {message}")
                logging_utils.stop_file_logging()
                return {'CANCELLED'}

            # Enable discipline legend overlay (visual reference only, not clickable)
            discipline_legend.enable_legend()

            print("\n✓ Preview ready - INSTANT GPU bboxes loaded!")
            print("✓ All 49K elements visible - MEP engineers can work immediately!")
            print("✓ Legend shows discipline colors (use Outliner to toggle)")
            print("✓ Use 'Solid' for colored boxes or 'Full Load' for exact geometry\n")

            self.report({'INFO'}, "Preview ready - instant GPU bboxes + legend")
            logging_utils.stop_file_logging()
            return {'FINISHED'}

        except Exception as e:
            import traceback
            traceback.print_exc()

            self.report({'ERROR'}, f"Preview failed: {str(e)}")
            logging_utils.stop_file_logging()
            return {'CANCELLED'}


class LoadSolidFederationViewport(bpy.types.Operator):
    """Load solid procedural boxes (fast, ~5s, colored by discipline)"""
    bl_idname = "bim.load_solid_federation_viewport"
    bl_label = "Load Solid Boxes"
    bl_description = "Load procedural solid boxes with GPU instancing (~5s)\nColored by discipline, faster than full geometry"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.BIMFederationProperties

        if not props.federation_database_path:
            self.report({'ERROR'}, "No federation database selected")
            return {'CANCELLED'}

        # Get cache path with auto-increment (creates _1, _2, etc. if exists)
        from . import blend_cache
        from pathlib import Path
        db_path = bpy.path.abspath(props.federation_database_path)
        cache_path = Path(blend_cache.get_cache_path(db_path, mode="solid", auto_increment=True))

        print(f"\n🔄 Cache will be saved to: {cache_path.name}")

        # Start logging
        from . import logging_utils
        log_path = logging_utils.start_file_logging()
        print(f"📝 Logging to: {log_path}")

        # NO CACHE - Start background baking (viewport stays free!)
        print("\n🚀 Starting background cache baking...")
        print("   Your viewport stays responsive - continue using Preview mode!")
        print("   Open .blend when ready (~40s)\n")

        try:
            # Start background baking process with auto-incremented path
            result_cache_path = blend_cache.start_background_baking(db_path, mode="solid", cache_path=str(cache_path))

            # Start modal monitor to track progress
            bpy.ops.bim.monitor_cache_baking(
                'INVOKE_DEFAULT',
                cache_path=str(result_cache_path),
                db_path=db_path,
                mode="solid"
            )

            msg = "Background baking started! Continue working - cache will be ready soon."
            self.report({'INFO'}, msg)
            print(f"✅ {msg}")
            print(f"   Open the .blend file when ready for full geometry analysis")
            logging_utils.stop_file_logging()
            return {'FINISHED'}

        except Exception as e:
            print(f"⚠️ Background baking failed to start: {e}")
            print("   Falling back to procedural loading...")

        # Fallback to old procedural loading if cache fails
        try:
            print(f"\n{'='*70}")
            print("SOLID MODE: Procedural GPU-Instanced Boxes")
            print(f"{'='*70}\n")

            # Disable legend when loading solid geometry (legend is preview-only)
            from . import discipline_legend
            if discipline_legend.is_legend_enabled():
                discipline_legend.disable_legend()
                print("  Disabled discipline legend (switching to solid geometry mode)")

            # Register federation index first (if not already)
            if not hasattr(bpy.types.WindowManager, 'federation_index'):
                print("  Registering federation index for MEP routing...")
                from .core.spatial_index import FederationIndex
                # Resolve Blender's // relative path prefix
                db_path_resolved = bpy.path.abspath(props.federation_database_path)
                index = FederationIndex(db_path_resolved)
                index.build()
                bpy.types.WindowManager.federation_index = index
                stats = index.get_statistics()
                print(f"  ✓ Federation index registered: {stats.get('total_elements', 0):,} elements")
                print(f"  ✓ Conduit routing and clash detection now enabled")

                # Mark index as loaded
                props.index_loaded = True

            # Clean up any existing federation hierarchies (prevents Outliner duplication)
            def remove_coll_fast(coll):
                """Recursively remove collection and all children"""
                for child in list(coll.children):
                    remove_coll_fast(child)
                for obj in list(coll.objects):
                    bpy.data.objects.remove(obj, do_unlink=True)
                bpy.data.collections.remove(coll, do_unlink=True)

            # Remove federation parent collections
            for coll_name in ['Federation', 'Federation_Semantics']:
                if coll_name in bpy.data.collections:
                    print(f"  Cleaning up old '{coll_name}' collection...")
                    remove_coll_fast(bpy.data.collections[coll_name])
                    print(f"  ✓ Removed {coll_name} hierarchy")

            # Also remove standalone discipline collections (prevents duplication)
            disciplines = ['ACMV', 'ARC', 'CW', 'ELEC', 'FP', 'SP', 'STR', 'LPG', 'REB']
            for disc in disciplines:
                for pattern in [f'Discipline_{disc}', f'Federation_{disc}']:
                    if pattern in bpy.data.collections:
                        print(f"  Cleaning up standalone '{pattern}' collection...")
                        remove_coll_fast(bpy.data.collections[pattern])

            print("  ✓ All federation collections cleaned up")

            # Use VisualizationManager to load solid procedural boxes
            from .visualization_manager import VisualizationManager
            viz_mgr = VisualizationManager(props.federation_database_path)

            print("\nLoading procedural solid boxes with GPU instancing...")
            timing = viz_mgr.load_all_layers()

            # Show solid boxes (SEMANTICS mode)
            viz_mgr.switch_mode('SEMANTICS')

            # Switch viewport to Solid mode to show colors + enable X-ray (Alt+Z)
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    for space in area.spaces:
                        if space.type == 'VIEW_3D':
                            space.shading.type = 'SOLID'
                            space.shading.color_type = 'MATERIAL'  # Show material colors in solid mode
                            print("  ✓ Switched viewport to Solid mode (X-ray enabled, Alt+Z)")
                            break

            total_time = sum(timing.values())
            self.report({'INFO'}, f"Solid boxes loaded in {total_time:.1f}s")

            # Mark solid as loaded (prevents re-loading)
            props.solid_loaded = True

            print(f"\n✓ Solid boxes ready! ({total_time:.1f}s)")
            print("✓ Colored by discipline, GPU instanced")
            print("✓ Materials visible (viewport in Solid mode)")
            print("✓ X-ray mode enabled (press Alt+Z to toggle)")
            print("✓ Solid button now disabled (already loaded)")
            print("✓ Use 'Full Load' for exact tessellated geometry\n")

            logging_utils.stop_file_logging()
            return {'FINISHED'}

        except Exception as e:
            import traceback
            traceback.print_exc()

            self.report({'ERROR'}, f"Solid load failed: {str(e)}")
            logging_utils.stop_file_logging()
            return {'CANCELLED'}


class LoadFullFederationViewport(bpy.types.Operator):
    """Load procedural boxes with real Revit materials (fast, ~5-6s)"""
    bl_idname = "bim.load_full_federation_viewport"
    bl_label = "Load Full Geometry"
    bl_description = "Load procedural boxes with real Revit materials from database (~5-6s)\nFast GPU instancing with actual material colors"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.BIMFederationProperties

        if not props.federation_database_path:
            self.report({'ERROR'}, "No federation database selected")
            return {'CANCELLED'}

        # Get cache path with auto-increment (creates _1, _2, etc. if exists)
        from . import blend_cache
        from pathlib import Path
        db_path = bpy.path.abspath(props.federation_database_path)
        cache_path = Path(blend_cache.get_cache_path(db_path, mode="full", auto_increment=True))

        print(f"\n🔄 Cache will be saved to: {cache_path.name}")

        # Start logging
        from . import logging_utils
        log_path = logging_utils.start_file_logging()
        print(f"📝 Logging to: {log_path}")

        # NO CACHE - Start background baking (viewport stays free!)
        print("\n🚀 Starting background cache baking...")
        print("   Your viewport will stay responsive!")
        print("   Open .blend when ready (~70s)\n")

        try:
            # Start background baking process with auto-incremented path
            result_cache_path = blend_cache.start_background_baking(db_path, mode="full", cache_path=str(cache_path))

            # Start modal monitor (non-blocking)
            bpy.ops.bim.monitor_cache_baking(
                'INVOKE_DEFAULT',
                cache_path=str(result_cache_path),
                db_path=db_path,
                mode="full"
            )

            self.report({'INFO'}, "✅ Background baking started! Open .blend when ready.")
            logging_utils.stop_file_logging()
            return {'FINISHED'}

        except Exception as e:
            print(f"❌ Background baking failed to start: {e}")
            print("   Falling back to tessellated loading...")

        # Fallback to old tessellated loading if cache fails
        try:
            print(f"\n{'='*70}")
            print("FULL GEOMETRY MODE: Exact Tessellated IFC Mesh")
            print(f"{'='*70}\n")

            # Disable legend when loading full geometry (legend is preview-only)
            from . import discipline_legend
            if discipline_legend.is_legend_enabled():
                discipline_legend.disable_legend()
                print("  Disabled discipline legend (switching to full geometry mode)")

            # Use FederationLoader with tessellated geometry + DB materials
            from .loader import FederationLoader
            import time

            start = time.time()
            loader = FederationLoader(props.federation_database_path)
            loader.stage2_progressive = False  # Use tessellated geometry (exact IFC shapes from database)
            loader.use_database_materials = True  # Try DB materials, fallback to discipline colors if NULL

            # Register federation index for routing/clashing
            if not hasattr(bpy.types.WindowManager, 'federation_index'):
                print("\n  Registering federation index for routing...")
                from .core.spatial_index import FederationIndex
                index = FederationIndex(props.federation_database_path)
                index.build()
                bpy.types.WindowManager.federation_index = index
                stats = index.get_statistics()
                print(f"  ✓ Federation index registered: {stats.get('total_elements', 0):,} elements")
                print(f"  ✓ Conduit routing and clash detection now enabled")

                # Mark index as loaded
                props.index_loaded = True

            # Load Stage 2: Tessellated geometry (exact IFC shapes)
            print("\n⏳ Loading exact tessellated geometry with database materials...")
            print("   (Fallback to discipline colors if DB materials unavailable)")

            shapes = loader.load_stage2()
            elapsed = time.time() - start

            # Determine what was actually loaded
            mode_desc = "Tessellated geometry" if not loader.stage2_progressive else "Procedural boxes"
            mat_desc = "DB materials" if loader.use_database_materials else "Discipline colors"

            print(f"\n✅ FULL LOAD COMPLETE!")
            print(f"  - Mode: {mode_desc} + {mat_desc}")
            print(f"  - Elements: {len(shapes):,}")
            print(f"  - Time: {elapsed:.2f}s")
            print(f"  - Geometry: {'Exact IFC tessellation from database' if not loader.stage2_progressive else 'GPU-instanced procedural shapes'}")
            print(f"  ✓ Viewport shading unchanged (use whatever mode you prefer)")

            self.report({'INFO'}, f"Full load complete: {len(shapes):,} shapes in {elapsed:.2f}s")

            logging_utils.stop_file_logging()
            return {'FINISHED'}

        except Exception as e:
            import traceback
            traceback.print_exc()

            self.report({'ERROR'}, f"Full load failed: {str(e)}")
            logging_utils.stop_file_logging()
            return {'CANCELLED'}


class LoadFullFederationViewportGI(bpy.types.Operator):
    """Load exact geometry with Geometry Instancing - optimized file size (EXPERIMENTAL)"""
    bl_idname = "bim.load_full_federation_viewport_gi"
    bl_label = "Load Full Geometry (*GI)"
    bl_description = "EXPERIMENTAL: Load with Geometry Instancing (GI)\nMeshes shared by geometry_hash → 50-90% smaller files\nBackward compatible - can revert to regular Full Load anytime"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.BIMFederationProperties

        if not props.federation_database_path:
            self.report({'ERROR'}, "No federation database selected")
            return {'CANCELLED'}

        # Start logging
        from . import logging_utils
        log_path = logging_utils.start_file_logging()
        print(f"📝 Logging to: {log_path}")

        try:
            from . import blend_cache
            from pathlib import Path
            import time

            db_path = bpy.path.abspath(props.federation_database_path)

            print(f"\n{'='*70}")
            print("FULL GEOMETRY MODE: Exact Tessellation + GI (EXPERIMENTAL)")
            print(f"{'='*70}")
            print("✨ Geometry Instancing (GI) enabled")
            print("   - Meshes shared by geometry_hash")
            print("   - File size: 50-90% smaller (depends on project reuse ratio)")
            print("   - RAM usage: ~40% less")
            print("   - Backward compatible: Can revert to regular Full Load")
            print(f"{'='*70}\n")

            # Disable legend when loading full geometry
            from . import discipline_legend
            if discipline_legend.is_legend_enabled():
                discipline_legend.disable_legend()
                print("  Disabled discipline legend (switching to full geometry mode)")

            # Register federation index for routing/clashing
            if not hasattr(bpy.types.WindowManager, 'federation_index'):
                print("\n  Registering federation index for routing...")
                from .core.spatial_index import FederationIndex
                index = FederationIndex(db_path)
                index.build()
                bpy.types.WindowManager.federation_index = index
                stats = index.get_statistics()
                print(f"  ✓ Federation index registered: {stats.get('total_elements', 0):,} elements")
                print(f"  ✓ Conduit routing and clash detection now enabled")
                props.index_loaded = True

            # Create cache with GI (loads directly into viewport)
            print("\n⏳ Loading with Geometry Instancing...")
            start = time.time()

            def report_callback(message):
                """Progress updates during loading"""
                print(f"  {message}")
                self.report({'INFO'}, message)
                # Force UI update to show progress in bottom bar
                context.workspace.status_text_set(message)
                bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

            mesh_count = blend_cache.create_cache(
                context,
                db_path,
                mode="full",
                report_fn=report_callback
            )

            elapsed = time.time() - start

            print(f"\n✅ FULL LOAD COMPLETE (GI-ENABLED)!")
            print(f"  - Unique meshes: {mesh_count:,}")
            print(f"  - Time: {elapsed:.2f}s")
            print(f"  - GI Status: ✅ Meshes shared by geometry_hash")
            print(f"  - File size when saved: ~50-90% smaller than without GI")
            print(f"  ✓ Objects in viewport now (organized by discipline)")

            # Re-enable discipline legend (since GI organizes by discipline)
            discipline_legend.enable_legend()
            print("  ✓ Discipline legend enabled")

            self.report({'INFO'}, f"✅ GI Load complete: {mesh_count:,} unique meshes in {elapsed:.2f}s")

            logging_utils.stop_file_logging()
            return {'FINISHED'}

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"\n❌ GI loading failed: {e}")
            self.report({'ERROR'}, f"GI load failed: {str(e)}. Use regular 'Full Load' instead.")
            logging_utils.stop_file_logging()
            return {'CANCELLED'}


class ReloadFederationViewport(bpy.types.Operator):
    """Load or switch federation visualization mode (multi-layer caching)"""
    bl_idname = "bim.reload_federation_viewport"
    bl_label = "Load/Switch Visualization"
    bl_description = "Load all layers once, then instant mode switching"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.BIMFederationProperties

        if not props.federation_database_path:
            self.report({'ERROR'}, "No federation database loaded")
            return {'CANCELLED'}

        mode = props.visualization_mode

        # Start logging to timestamped file
        from . import logging_utils
        log_path = logging_utils.start_file_logging()
        print(f"📝 Logging to: {log_path}")

        try:
            # Disable legend when loading full geometry (legend is preview-only)
            from . import discipline_legend
            if discipline_legend.is_legend_enabled():
                discipline_legend.disable_legend()
                print("  Disabled discipline legend (switching to full geometry mode)")

            # CRITICAL: Check tessellation toggle
            if props.use_tessellation:
                # Use FederationLoader with GPU bbox visualization + tessellation
                print(f"\n{'='*70}")
                print("FEDERATION LOADER: GPU BBox wireframes → Full geometry (tessellation)")
                print(f"{'='*70}\n")

                from .loader import FederationLoader
                import time

                start = time.time()
                loader = FederationLoader(props.federation_database_path)
                loader.stage2_progressive = False  # Use tessellation

                # Load Stage 1: GPU BBox visualization (instant!)
                loader.load_stage1()

                # Register federation index for routing/clashing
                if not hasattr(bpy.types.WindowManager, 'federation_index'):
                    print("\n  Registering federation index for routing...")
                    from .core.spatial_index import FederationIndex
                    index = FederationIndex(props.federation_database_path)
                    index.build()
                    bpy.types.WindowManager.federation_index = index
                    stats = index.get_statistics()
                    print(f"  ✓ Federation index registered: {stats.get('total_elements', 0):,} elements")
                    print(f"  ✓ Conduit routing and clash detection now enabled")

                print("\n✓ Stage 1 complete: GPU BBox wireframes loaded (instant!)")
                print("✓ MEP engineers can work immediately with wireframes")
                print("\n⏳ Stage 2: Loading full tessellated geometry in BACKGROUND...")
                print("   This will take ~25-30 minutes - you can continue MEP work!")
                print("   Blender will remain responsive\n")

                # Set database path for background loader
                context.scene['federation_loader_db_path'] = str(props.federation_database_path)

                # Invoke background loader for Stage 2 tessellation (non-blocking!)
                bpy.ops.bim.load_federation_stage2_background()

                self.report({'INFO'}, "Stage 1 complete - Stage 2 loading in background")

                logging_utils.stop_file_logging()
                return {'FINISHED'}

            # Use old VisualizationManager (progressive/procedural)
            from .visualization_manager import VisualizationManager
            viz_mgr = VisualizationManager(props.federation_database_path)

            # Handle NONE mode - unload everything
            if mode == 'NONE':
                viz_mgr.unload_all_layers()
                self.report({'INFO'}, "Visualization unloaded")
                logging_utils.stop_file_logging()
                return {'FINISHED'}

            # Check if all layers are already loaded
            if viz_mgr.are_all_layers_loaded():
                # Instant mode switch (just toggle visibility)
                print(f"\n{'='*70}")
                print(f"SWITCHING TO {mode} MODE (Instant)")
                print(f"{'='*70}\n")

                elapsed = viz_mgr.switch_mode(mode)

                self.report({'INFO'},
                    f"Switched to {mode} in {elapsed*1000:.1f}ms")

                logging_utils.stop_file_logging()
                return {'FINISHED'}

            else:
                # First-time load: Generate all 3 layers
                print(f"\n{'='*70}")
                print("FIRST-TIME LOAD: Generating all 3 visualization layers")
                print(f"{'='*70}\n")

                timing = viz_mgr.load_all_layers()

                # Show selected mode, hide others
                viz_mgr.switch_mode(mode)

                total_time = sum(timing.values())
                self.report({'INFO'},
                    f"Loaded all layers in {total_time:.1f}s (future switches instant!)")

                print(f"\n✓ All layers ready! Future mode switches will be instant (<0.1s)")
                logging_utils.stop_file_logging()
                return {'FINISHED'}

        except Exception as e:
            print(f"\n❌ Load/switch failed: {e}")
            import traceback
            traceback.print_exc()

            self.report({'ERROR'}, f"Operation failed: {str(e)}")
            logging_utils.stop_file_logging()
            return {'CANCELLED'}

    def _frame_viewport_to_objects(self, context, objects):
        """
        Auto-framing DISABLED - causes freeze with 48K+ objects.

        Original IFC loading doesn't auto-frame, neither should we.
        Building is already centered near origin by global offset.
        User can manually zoom/pan as needed.

        Args:
            context: Blender context
            objects: List of loaded objects (ignored)
        """
        # NO auto-framing! Just return immediately.
        # Auto-framing with 48K objects:
        #   - Selecting all objects: ~30s
        #   - view_selected() calculation: ~60s
        #   - Total waste: ~90 seconds!
        # Original IFC files don't auto-frame, we don't either.
        print(f"✓ Loading complete - {len(objects):,} objects (viewport: use mouse to navigate)")
        return


class UnloadFederationViewport(bpy.types.Operator):
    """Unload BBox preview only (Stage 1 - fast layer)"""
    bl_idname = "bim.unload_federation_viewport"
    bl_label = "Unload Preview"
    bl_description = "Remove BBox preview (GPU batches). Stage 2/3 geometry uses Outliner hide/show."
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            # Disable legend if active
            from . import discipline_legend
            if discipline_legend.is_legend_enabled():
                discipline_legend.disable_legend()
                print("✓ Discipline legend disabled")

            # Disable BBox visualization ONLY (Stage 1 - instant GPU batches)
            from . import bbox_visualization
            if bbox_visualization.is_bbox_visualization_enabled():
                bbox_visualization.disable_bbox_visualization()
                self.report({'INFO'}, "BBox preview unloaded (Stage 1)")
                print("✓ BBox preview cleared (GPU batches freed)")
            else:
                self.report({'INFO'}, "No BBox preview to unload")
                print("ℹ No BBox preview active")

            # NOTE: Stage 2/3 geometry NOT unloaded - use Outliner to hide/show
            # viz_mgr.unload_all_layers() is intentionally removed

            return {'FINISHED'}

        except Exception as e:
            print(f"\n❌ Unload failed: {e}")
            import traceback
            traceback.print_exc()

            self.report({'ERROR'}, f"Unload failed: {str(e)}")
            return {'CANCELLED'}


class LinkFederationLibrary(bpy.types.Operator):
    """Load building from library.blend — GN checkbox controls mode"""
    bl_idname = "bim.link_federation_library"
    bl_label = "Library"
    bl_description = (
        "Load building from library.blend\n"
        "GN ON (default): fast GN point clouds, discipline colors\n"
        "GN OFF: per-element objects, full IFC colors, selectable"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.BIMFederationProperties

        if not props.federation_database_path:
            self.report({'ERROR'}, "No federation database selected")
            return {'CANCELLED'}

        # S175: GN checkbox controls which path
        if props.gn_mode:
            return self._load_gn(context, props)
        else:
            return self._load_per_element(context, props)

    def _load_common(self, context, props):
        """Shared setup: find library, register index."""
        from .loading.stage2_library_linker import _find_library_blend
        from . import discipline_legend

        db_path = bpy.path.abspath(props.federation_database_path)
        lib_blend = _find_library_blend(db_path)
        if not lib_blend:
            self.report({'ERROR'},
                "library.blend not found. Run bake_library_blend.py first.")
            return None, None, None

        if discipline_legend.is_legend_enabled():
            discipline_legend.disable_legend()

        if not hasattr(bpy.types.WindowManager, 'federation_index'):
            from .core.spatial_index import FederationIndex
            index = FederationIndex(db_path)
            index.build()
            bpy.types.WindowManager.federation_index = index
            props.index_loaded = True

        return db_path, lib_blend, discipline_legend

    def _load_gn(self, context, props):
        """GN + NEAR: cache load, make_local() near, enable GN — ~3s target."""
        from . import logging_utils
        logging_utils.start_file_logging()

        try:
            from .loading.stage2_library_linker import load_library_gn

            db_path, lib_blend, discipline_legend = self._load_common(context, props)
            if db_path is None:
                logging_utils.stop_file_logging()
                return {'CANCELLED'}

            print(f"\n{'='*70}")
            print(f"LIBRARY — GN + NEAR (cache → make_local → smooth)")
            print(f"  Database: {db_path}")
            print(f"  Library:  {lib_blend}")
            print(f"{'='*70}")

            gn_collection = bpy.data.collections.get("Federation_Library_GN")
            if not gn_collection:
                gn_collection = bpy.data.collections.new("Federation_Library_GN")
                context.scene.collection.children.link(gn_collection)

            def report_fn(msg):
                self.report({'INFO'}, msg)
                context.workspace.status_text_set(msg)

            stats = load_library_gn(
                db_path, lib_blend, gn_collection, report_fn)

            discipline_legend.enable_legend()

            # Hide per-element if it exists
            for vl in context.scene.view_layers:
                lc = self._find_lc(vl.layer_collection, "Federation_Library")
                if lc:
                    lc.exclude = True

            # Store GN load time on collection for comparison
            gn_collection['load_time'] = stats['total_time']
            gn_collection['link_time'] = stats['cache_time']
            gn_collection['gn_build_time'] = stats['gn_build_time']

            context.workspace.status_text_set(None)
            print(f"\n{'='*70}")
            print(f"§PROOF GN_PERFORMANCE")
            print(f"  Elements:     {stats['elements']:,}")
            print(f"  GN objects:   {stats['gn_objects']}")
            print(f"  Unique meshes:{stats['unique_meshes']:,}")
            print(f"  Link time:    {stats['cache_time']:.3f}s (link=True, zero-copy)")
            print(f"  GN build:     {stats['gn_build_time']:.2f}s")
            print(f"  Total:        {stats['total_time']:.2f}s")
            print(f"  Rate:         {stats['elements']/max(stats['total_time'],0.001):.0f} elements/s")
            print(f"{'='*70}\n")
            self.report({'INFO'},
                f"GN loaded: {stats['elements']:,} elements in "
                f"{stats['gn_objects']} objects ({stats['total_time']:.1f}s)")

            logging_utils.stop_file_logging()
            return {'FINISHED'}

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, f"GN Library load failed: {e}")
            context.workspace.status_text_set(None)
            logging_utils.stop_file_logging()
            return {'CANCELLED'}

    def _load_per_element(self, context, props):
        """Per-element mode: full IFC colors, selectable (link=False, slower)."""
        from . import logging_utils
        logging_utils.start_file_logging()

        try:
            from .loading.stage2_library_linker import load_library_linked

            db_path, lib_blend, discipline_legend = self._load_common(context, props)
            if db_path is None:
                logging_utils.stop_file_logging()
                return {'CANCELLED'}

            print(f"\n{'='*70}")
            print(f"LIBRARY LINK — PER-ELEMENT MODE (full color)")
            print(f"  Database: {db_path}")
            print(f"  Library:  {lib_blend}")
            print(f"{'='*70}")

            fed_collection = bpy.data.collections.get("Federation_Library")
            if not fed_collection:
                fed_collection = bpy.data.collections.new("Federation_Library")
                context.scene.collection.children.link(fed_collection)

            def report_fn(msg):
                self.report({'INFO'}, msg)
                context.workspace.status_text_set(msg)

            stats = load_library_linked(
                db_path, lib_blend, fed_collection, report_fn)

            discipline_legend.enable_legend()

            # Hide GN if it exists
            for vl in context.scene.view_layers:
                lc = self._find_lc(vl.layer_collection, "Federation_Library_GN")
                if lc:
                    lc.exclude = True

            # Store per-element load time on collection for comparison
            fed_collection['load_time'] = stats['total_time']
            fed_collection['link_time'] = stats['link_time']
            fed_collection['instance_time'] = stats['instance_time']

            context.workspace.status_text_set(None)
            print(f"\n{'='*70}")
            print(f"§PROOF PEREL_PERFORMANCE")
            print(f"  Elements:     {stats['elements']:,}")
            print(f"  Unique meshes:{stats['unique_meshes']:,}")
            print(f"  Link time:    {stats['link_time']:.3f}s (link=False, local copy)")
            print(f"  Instance time:{stats['instance_time']:.2f}s")
            print(f"  Total:        {stats['total_time']:.2f}s")
            print(f"  Rate:         {stats['elements']/max(stats['total_time'],0.001):.0f} elements/s")
            print(f"{'='*70}\n")
            self.report({'INFO'},
                f"Library loaded: {stats['elements']:,} elements in "
                f"{stats['total_time']:.1f}s")

            logging_utils.stop_file_logging()
            return {'FINISHED'}

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, f"Library load failed: {e}")
            context.workspace.status_text_set(None)
            logging_utils.stop_file_logging()
            return {'CANCELLED'}

    def _find_lc(self, layer_collection, name):
        if layer_collection.collection.name == name:
            return layer_collection
        for child in layer_collection.children:
            result = self._find_lc(child, name)
            if result:
                return result
        return None


class LinkFederationLibraryGN(bpy.types.Operator):
    """Load federation as GN point clouds from library.blend — scale/presentation mode"""
    bl_idname = "bim.link_federation_library_gn"
    bl_label = "Library GN"
    bl_description = (
        "Load federation as GN point clouds from library.blend\n"
        "Few Outliner items, DLOD active, smaller .blend saves\n"
        "Toggle back to per-element mode via GN Mode Toggle button"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.BIMFederationProperties

        if not props.federation_database_path:
            self.report({'ERROR'}, "No federation database selected")
            return {'CANCELLED'}

        from . import logging_utils
        log_path = logging_utils.start_file_logging()

        try:
            from .loading.stage2_library_linker import (
                load_library_linked_gn, _find_library_blend
            )
            from . import discipline_legend
            import time

            db_path = bpy.path.abspath(props.federation_database_path)

            print(f"\n{'='*70}")
            print("LIBRARY LINK GN MODE: GN point clouds from library.blend")
            print(f"{'='*70}")
            print(f"  Database: {db_path}")

            # Locate library.blend
            lib_blend = _find_library_blend(db_path)
            if not lib_blend:
                self.report({'ERROR'},
                    "library.blend not found. "
                    "Run bake_library_blend.py first.")
                logging_utils.stop_file_logging()
                return {'CANCELLED'}

            print(f"  Library:  {lib_blend}")

            # Disable legend if active
            if discipline_legend.is_legend_enabled():
                discipline_legend.disable_legend()

            # Register federation index
            if not hasattr(bpy.types.WindowManager, 'federation_index'):
                from .core.spatial_index import FederationIndex
                index = FederationIndex(db_path)
                index.build()
                bpy.types.WindowManager.federation_index = index
                props.index_loaded = True

            # Create GN parent collection
            gn_collection = bpy.data.collections.get("Federation_Library_GN")
            if not gn_collection:
                gn_collection = bpy.data.collections.new("Federation_Library_GN")
                context.scene.collection.children.link(gn_collection)

            # Load GN mode
            def report_fn(msg):
                self.report({'INFO'}, msg)
                context.workspace.status_text_set(msg)

            stats = load_library_linked_gn(
                db_path, lib_blend, gn_collection, report_fn)

            # Re-enable legend
            discipline_legend.enable_legend()

            # Hide per-element collection if it exists (both coexist)
            fed_lib = bpy.data.collections.get("Federation_Library")
            if fed_lib:
                for vl in context.scene.view_layers:
                    lc = self._find_lc(vl.layer_collection, "Federation_Library")
                    if lc:
                        lc.exclude = True
                print(f"  §FINE toggle: Library→GN (DLOD on)")

            # Summary
            print(f"\n{'='*70}")
            print(f"LIBRARY LINK GN COMPLETE")
            print(f"  Elements:     {stats['elements']:,}")
            print(f"  Unique meshes:{stats['unique_meshes']:,}")
            print(f"  GN objects:   {stats['gn_objects']}")
            print(f"  Total:        {stats['total_time']:.2f}s")
            print(f"{'='*70}\n")

            context.workspace.status_text_set(None)
            self.report({'INFO'},
                f"GN Library loaded: {stats['elements']:,} elements in "
                f"{stats['gn_objects']} GN objects ({stats['total_time']:.1f}s)")

            logging_utils.stop_file_logging()
            return {'FINISHED'}

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"\n  LIBRARY LINK GN FAILED: {e}")
            self.report({'ERROR'}, f"GN Library link failed: {str(e)}")
            context.workspace.status_text_set(None)
            logging_utils.stop_file_logging()
            return {'CANCELLED'}

    def _find_lc(self, layer_collection, name):
        if layer_collection.collection.name == name:
            return layer_collection
        for child in layer_collection.children:
            result = self._find_lc(child, name)
            if result:
                return result
        return None


class ToggleFederationGNMode(bpy.types.Operator):
    """Switch between GN (fast) and per-element (full color) — auto-loads if needed"""
    bl_idname = "bim.toggle_federation_gn_mode"
    bl_label = "Switch"
    bl_description = (
        "Switch between the two loaded modes.\n"
        "If the other mode isn't loaded yet, loads it automatically"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.BIMFederationProperties
        gn_col = bpy.data.collections.get("Federation_Library_GN")
        lib_col = bpy.data.collections.get("Federation_Library")

        if not gn_col and not lib_col:
            self.report({'WARNING'}, "No federation loaded. Click Library first.")
            return {'CANCELLED'}

        # Detect which is currently visible
        gn_lc = lib_lc = None
        gn_visible = False
        for vl in context.scene.view_layers:
            gn_lc = self._find_lc(vl.layer_collection, "Federation_Library_GN")
            lib_lc = self._find_lc(vl.layer_collection, "Federation_Library")
            if gn_lc:
                gn_visible = not gn_lc.exclude
            break

        if gn_visible:
            # ── GN → per-element (full color) ──
            if gn_lc:
                gn_lc.exclude = True
            try:
                from . import dlod_handler
                dlod_handler.unregister_handler()
            except Exception:
                pass

            if lib_col and lib_lc:
                lib_lc.exclude = False
                print(f"§FINE toggle: GN→Library (DLOD off)")
                self.report({'INFO'}, "Per-element mode (full colors)")
            else:
                # Auto-load per-element — set gn_mode=False so Library loads right path
                props.gn_mode = False
                context.workspace.status_text_set("Loading per-element (full colors)...")
                ret = bpy.ops.bim.link_federation_library()
                context.workspace.status_text_set(None)
                if ret != {'FINISHED'}:
                    props.gn_mode = True
                    if gn_lc:
                        gn_lc.exclude = False
                    self.report({'WARNING'}, "Per-element load failed")
                    return {'CANCELLED'}
                self.report({'INFO'}, "Per-element loaded (full colors)")
            props.gn_mode = False
        else:
            # ── per-element → GN (fast, DLOD) ──
            if lib_lc:
                lib_lc.exclude = True

            if gn_col and gn_lc:
                gn_lc.exclude = False
            else:
                # Auto-load GN — set gn_mode=True so Library loads right path
                props.gn_mode = True
                ret = bpy.ops.bim.link_federation_library()
                if ret != {'FINISHED'}:
                    props.gn_mode = False
                    if lib_lc:
                        lib_lc.exclude = False
                    self.report({'WARNING'}, "GN load failed")
                    return {'CANCELLED'}

            try:
                from . import dlod_handler
                dlod_handler.register_handler()
            except Exception:
                pass
            print(f"§FINE toggle: Library→GN (DLOD on)")
            self.report({'INFO'}, "GN mode (DLOD on)")
            props.gn_mode = True

        # ── §PROOF COMPARE — side-by-side performance + scene stats ──
        self._log_comparison(context)
        return {'FINISHED'}

    def _log_comparison(self, context):
        """Log GN vs per-element performance comparison after toggle.
        Writes to both console and file for later reading."""
        import os
        from datetime import datetime

        gn_col = bpy.data.collections.get("Federation_Library_GN")
        lib_col = bpy.data.collections.get("Federation_Library")

        gn_objs = gn_elements = lib_objs = 0
        gn_discs = lib_discs = 0
        gn_load_time = gn_link_time = gn_build_time = 0.0
        lib_load_time = lib_link_time = lib_instance_time = 0.0

        if gn_col:
            for child in gn_col.children:
                if child.name.startswith('_'):
                    continue
                gn_discs += 1
                for obj in child.objects:
                    gn_objs += 1
                    if obj.type == 'MESH' and obj.data:
                        gn_elements += len(obj.data.vertices)
            gn_load_time = gn_col.get('load_time', 0.0)
            gn_link_time = gn_col.get('link_time', 0.0)
            gn_build_time = gn_col.get('gn_build_time', 0.0)

        if lib_col:
            for child in lib_col.children:
                if child.name.startswith('_'):
                    continue
                lib_discs += 1
                lib_objs += len(child.objects)
            lib_load_time = lib_col.get('load_time', 0.0)
            lib_link_time = lib_col.get('link_time', 0.0)
            lib_instance_time = lib_col.get('instance_time', 0.0)

        # Count meshes + total vertex data in scene
        total_meshes = len(bpy.data.meshes)
        total_verts = sum(len(m.vertices) for m in bpy.data.meshes)
        total_objects = len(bpy.data.objects)

        # Blend file size (if saved)
        blend_path = bpy.data.filepath
        blend_size_mb = 0.0
        if blend_path and os.path.exists(blend_path):
            blend_size_mb = os.path.getsize(blend_path) / (1024 * 1024)

        # Build comparison report
        lines = [
            f"{'='*60}",
            f"§PROOF COMPARE — GN vs Per-Element — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"{'='*60}",
            f"",
            f"  GN MODE (link=True, discipline colors, DLOD):",
            f"    Objects:     {gn_objs} GN objects ({gn_discs} disciplines)",
            f"    Elements:    {gn_elements:,} points",
            f"    Link time:   {gn_link_time:.3f}s",
            f"    GN build:    {gn_build_time:.2f}s",
            f"    Total load:  {gn_load_time:.2f}s",
            f"    Rate:        {gn_elements/max(gn_load_time,0.001):.0f} elements/s",
            f"",
            f"  PER-ELEMENT MODE (link=False, full IFC colors, selectable):",
            f"    Objects:     {lib_objs:,} ({lib_discs} disciplines)",
            f"    Link time:   {lib_link_time:.3f}s",
            f"    Instance:    {lib_instance_time:.2f}s",
            f"    Total load:  {lib_load_time:.2f}s",
            f"    Rate:        {lib_objs/max(lib_load_time,0.001):.0f} elements/s",
            f"",
            f"  SPEEDUP:       {lib_load_time/max(gn_load_time,0.001):.1f}x faster (GN vs per-element)"
                if gn_load_time > 0 and lib_load_time > 0 else
            f"  SPEEDUP:       (need both modes loaded to compare)",
            f"",
            f"  SCENE TOTALS:",
            f"    Objects:     {total_objects:,}",
            f"    Meshes:      {total_meshes:,}",
            f"    Vertices:    {total_verts:,}",
            f"    .blend size: {blend_size_mb:.1f}MB" if blend_size_mb > 0 else
            f"    .blend size: (not saved yet — Ctrl+S to measure)",
            f"",
            f"  §PROOF BLEND_SIZE gn_outliner={gn_objs} perel_outliner={lib_objs:,} "
            f"speedup={lib_load_time/max(gn_load_time,0.001):.1f}x"
                if gn_load_time > 0 and lib_load_time > 0 else
            f"  §PROOF BLEND_SIZE (partial — load both modes for full comparison)",
            f"{'='*60}",
        ]

        # Print to console
        for line in lines:
            print(line)

        # Write to file for later reading
        props = context.scene.BIMFederationProperties
        db_path = bpy.path.abspath(props.federation_database_path) if props.federation_database_path else ""
        if db_path:
            log_dir = os.path.dirname(db_path)
        else:
            log_dir = os.path.join(os.path.expanduser("~"), "Documents", "bonsai")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "gn_compare.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        print(f"  §LOG comparison written to {log_path}")

    def _find_lc(self, layer_collection, name):
        if layer_collection.collection.name == name:
            return layer_collection
        for child in layer_collection.children:
            result = self._find_lc(child, name)
            if result:
                return result
        return None


class ClearFederationViewport(bpy.types.Operator):
    """Clear R-Tree preview (GPU overlay + legend). Library objects stay."""
    bl_idname = "bim.clear_federation_viewport"
    bl_label = "Clear"
    bl_description = (
        "Clear R-Tree GPU overlay and discipline legend\n"
        "Library-linked objects are NOT removed (use Outliner)"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import time
        t0 = time.time()
        cleared = []

        try:
            from . import discipline_legend
            legend_was = discipline_legend.is_legend_enabled()
            if legend_was:
                discipline_legend.disable_legend()
                cleared.append("legend")

            from . import bbox_visualization
            bbox_was = bbox_visualization.is_bbox_visualization_enabled()
            if bbox_was:
                bbox_visualization.disable_bbox_visualization()
                cleared.append("R-Tree")

            elapsed = time.time() - t0
            summary = ", ".join(cleared) if cleared else "nothing to clear"
            print(f"  §CLEAR {summary} ({elapsed:.3f}s)")
            print(f"    legend_was={legend_was} bbox_was={bbox_was}")
            self.report({'INFO'}, f"Cleared: {summary}")
            return {'FINISHED'}

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, f"Clear failed: {str(e)}")
            return {'CANCELLED'}


class ExtractSampleDatabase(bpy.types.Operator):
    """Extract a small sample database for fast testing (ELEC-anchored, ~5 min)"""
    bl_idname = "bim.extract_sample_database"
    bl_label = "Extract Sample Database"
    bl_description = "Analyze IFC files and extract optimal sample region (ELEC-anchored, 300-800 elements, ~5 min)"
    bl_options = {'REGISTER'}

    def execute(self, context):
        # Setup console log file
        from datetime import datetime
        log_file = Path.home() / "Documents" / "bonsai" / "consolelogs" / f"sample_extraction_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        def log_and_print(msg):
            """Print to console and save to log file"""
            print(msg)
            with open(log_file, 'a') as f:
                f.write(msg + '\n')

        log_and_print("\n" + "="*70)
        log_and_print("SAMPLE DATABASE EXTRACTION")
        log_and_print("="*70)

        try:
            props = context.scene.BIMFederationProperties

            # Get IFC directory from federated files
            ifc_files = [f.name for f in props.federated_files if f.name]
            if not ifc_files:
                self.report({'ERROR'}, "No IFC files configured. Add files first.")
                return {'CANCELLED'}

            # Get directory from first file
            ifc_dir = Path(ifc_files[0]).parent
            log_and_print(f"IFC directory: {ifc_dir}")

            # Find scripts directory
            addon_dir = Path(__file__).parent
            scripts_dir = Path.home() / "Documents" / "bonsai" / "Scripts"

            if not scripts_dir.exists():
                self.report({'ERROR'}, f"Scripts directory not found: {scripts_dir}")
                return {'CANCELLED'}

            # Step 1: Run IFC analysis to find optimal region
            log_and_print("\n📊 Step 1: Analyzing IFC files for optimal sampling region...")
            analyze_script = scripts_dir / "analyze_ifc_for_sampling.py"

            if not analyze_script.exists():
                self.report({'ERROR'}, f"Analysis script not found: {analyze_script}")
                return {'CANCELLED'}

            # Get anchor type from UI
            anchor_type = props.sample_anchor_type
            log_and_print(f"Anchor type: {anchor_type}")

            # Use Blender's Python with PYTHONPATH for ifcopenshell
            import os
            env = os.environ.copy()
            env['PYTHONPATH'] = str(Path.home() / "Projects" / "IfcOpenShell" / "src")

            # Use Blender's Python (same as current process)
            blender_python = sys.executable

            result = subprocess.run(
                [blender_python, str(analyze_script), "--ifc-dir", str(ifc_dir), "--anchor-type", anchor_type],
                capture_output=True,
                text=True,
                timeout=120,
                env=env
            )

            if result.returncode != 0:
                log_and_print(f"Analysis failed:\n{result.stderr}")
                self.report({'ERROR'}, "IFC analysis failed. Check console.")
                return {'CANCELLED'}

            log_and_print(result.stdout)
            log_and_print("✓ Analysis complete")

            # Step 2: Copy suggested config to active config
            suggested_config = scripts_dir / "sample_config_suggested.json"
            active_config = scripts_dir / "sample_config.json"

            if not suggested_config.exists():
                self.report({'ERROR'}, "Analysis did not generate sample_config_suggested.json")
                return {'CANCELLED'}

            import shutil
            shutil.copy(suggested_config, active_config)
            log_and_print(f"✓ Copied {suggested_config.name} → {active_config.name}")

            # Step 3: Run extraction
            log_and_print("\n⚙️  Step 2: Extracting sample database...")
            # Use extraction script from IfcOpenShell repo (absolute path)
            extract_script = Path.home() / "Projects" / "IfcOpenShell" / "src" / "bonsai" / "scripts" / "extract_tessellation_to_db_v2.py"

            if not extract_script.exists():
                self.report({'ERROR'}, f"Extraction script not found: {extract_script}")
                return {'CANCELLED'}

            # Determine output database path
            if props.federation_database_path:
                # Resolve Blender's // relative path prefix
                base_db = Path(bpy.path.abspath(props.federation_database_path))
                sample_db = base_db.parent / f"sample_{base_db.stem}.db"
            else:
                sample_db = scripts_dir.parent / "DatabaseFiles" / "sample_extraction.db"

            log_and_print(f"Output database: {sample_db}")

            result = subprocess.run(
                [sys.executable, str(extract_script), "--sample", "--output", str(sample_db)],
                capture_output=True,
                text=True,
                timeout=600  # 10 min timeout
            )

            if result.returncode != 0:
                log_and_print(f"Extraction failed:\n{result.stderr}")
                self.report({'ERROR'}, "Sample extraction failed. Check console.")
                return {'CANCELLED'}

            log_and_print(result.stdout)
            log_and_print("✓ Extraction complete")

            # Step 4: Validate sample
            log_and_print("\n✅ Step 3: Validating sample quality...")
            validate_script = scripts_dir / "validate_sample_quick.py"

            validation_summary = "Validation skipped"
            if validate_script.exists():
                result = subprocess.run(
                    [sys.executable, str(validate_script), str(sample_db)],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                log_and_print(result.stdout)

                # Parse validation result for status bar
                if "SAMPLE READY FOR TESTING" in result.stdout:
                    validation_summary = "✅ Sample ready (all checks passed)"
                    self.report({'INFO'}, validation_summary)
                elif "SAMPLE ACCEPTABLE WITH WARNINGS" in result.stdout:
                    validation_summary = "⚠ Sample acceptable (some warnings)"
                    self.report({'WARNING'}, validation_summary)
                elif "SAMPLE NOT SUITABLE" in result.stdout:
                    validation_summary = "✗ Sample not suitable (critical issues)"
                    self.report({'ERROR'}, validation_summary)
                else:
                    validation_summary = "Validation completed"
                    self.report({'INFO'}, validation_summary)
            else:
                log_and_print("⚠ Validation script not found, skipping")
                self.report({'WARNING'}, "Validation script not found")

            # Update props to point to sample database
            props.federation_database_path = str(sample_db)

            log_and_print(f"\n{'='*70}")
            log_and_print("✅ SAMPLE EXTRACTION COMPLETE")
            log_and_print(f"Database: {sample_db}")
            log_and_print(f"Validation: {validation_summary}")
            log_and_print(f"Log saved to: {log_file}")
            log_and_print("Next: Click 'Reload Viewport' to load sample")
            log_and_print(f"{'='*70}\n")

            return {'FINISHED'}

        except subprocess.TimeoutExpired:
            log_and_print("\n❌ Extraction timed out (>10 min)")
            self.report({'ERROR'}, "Extraction timed out (>10 min). Try smaller region.")
            return {'CANCELLED'}

        except Exception as e:
            log_and_print(f"\n❌ Sample extraction failed: {e}")
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, f"Extraction failed: {str(e)}")
            return {'CANCELLED'}


class ExtractFullDatabase(bpy.types.Operator):
    """Extract full database with all elements (~4-6 hours, production-ready)"""
    bl_idname = "bim.extract_full_database"
    bl_label = "Extract Full Database"
    bl_description = "Extract complete database with all ~68K elements (~4-6 hours)"
    bl_options = {'REGISTER'}

    def execute(self, context):
        # Setup console log file
        from datetime import datetime
        log_file = Path.home() / "Documents" / "bonsai" / "consolelogs" / f"full_extraction_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        def log_and_print(msg):
            """Print to console and save to log file"""
            print(msg)
            with open(log_file, 'a') as f:
                f.write(msg + '\n')

        log_and_print("\n" + "="*70)
        log_and_print("FULL DATABASE EXTRACTION")
        log_and_print("="*70)

        try:
            props = context.scene.BIMFederationProperties

            # Get IFC directory from federated files (validation only)
            ifc_files = [f.name for f in props.federated_files if f.name]
            if not ifc_files:
                self.report({'ERROR'}, "No IFC files configured. Add files first.")
                return {'CANCELLED'}

            # Get directory from first file
            ifc_dir = Path(ifc_files[0]).parent
            log_and_print(f"IFC directory: {ifc_dir}")
            log_and_print(f"Files to process: {len(ifc_files)}")

            # Find extraction script
            extract_script = Path.home() / "Projects" / "IfcOpenShell" / "src" / "bonsai" / "scripts" / "extract_tessellation_to_db_v2.py"

            if not extract_script.exists():
                self.report({'ERROR'}, f"Extraction script not found: {extract_script}")
                return {'CANCELLED'}

            # Determine output database path
            default_db = Path.home() / "Documents" / "bonsai" / "DatabaseFiles" / "IFCmigrated_IFC4_v2.db"

            log_and_print(f"Output database: {default_db}")
            log_and_print("\n⚙️  Starting full extraction...")
            log_and_print("⏱️  Expected time: 4-6 hours")
            log_and_print("⚠️  This will run in the background. Check console for progress.\n")

            # Run extraction without --sample flag (full mode)
            result = subprocess.run(
                [sys.executable, str(extract_script), "--output", str(default_db)],
                capture_output=True,
                text=True,
                timeout=25200  # 7 hour timeout (generous buffer)
            )

            if result.returncode != 0:
                log_and_print(f"Extraction failed:\n{result.stderr}")
                self.report({'ERROR'}, "Full extraction failed. Check console.")
                return {'CANCELLED'}

            log_and_print(result.stdout)
            log_and_print("✓ Extraction complete")

            # Auto-populate database path in UI
            props.federation_database_path = str(default_db)

            log_and_print(f"\n{'='*70}")
            log_and_print("✅ FULL EXTRACTION COMPLETE")
            log_and_print(f"Database: {default_db}")
            log_and_print(f"Database path auto-populated in UI")
            log_and_print(f"Log saved to: {log_file}")
            log_and_print("Next: Click 'Reload Viewport' to load full model")
            log_and_print(f"{'='*70}\n")

            self.report({'INFO'}, "Full extraction complete! Click 'Reload Viewport'")
            return {'FINISHED'}

        except subprocess.TimeoutExpired:
            log_and_print("\n❌ Extraction timed out (>7 hours)")
            self.report({'ERROR'}, "Extraction timed out. Check if process is stuck.")
            return {'CANCELLED'}

        except Exception as e:
            log_and_print(f"\n❌ Full extraction failed: {e}")
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, f"Extraction failed: {str(e)}")
            return {'CANCELLED'}


class RedoSampleExtraction(bpy.types.Operator):
    """Try extracting a different sample region (randomized)"""
    bl_idname = "bim.redo_sample_extraction"
    bl_label = "Redo Sample Extraction"
    bl_description = "Try a different sample region with randomized boundaries"
    bl_options = {'REGISTER'}

    def execute(self, context):
        print("\n" + "="*70)
        print("REDO SAMPLE EXTRACTION (Randomized)")
        print("="*70)

        try:
            props = context.scene.BIMFederationProperties

            # Get IFC directory from federated files
            ifc_files = [f.name for f in props.federated_files if f.name]
            if not ifc_files:
                self.report({'ERROR'}, "No IFC files configured. Add files first.")
                return {'CANCELLED'}

            ifc_dir = Path(ifc_files[0]).parent
            print(f"IFC directory: {ifc_dir}")

            # Find scripts directory
            scripts_dir = Path.home() / "Documents" / "bonsai" / "Scripts"

            # Step 1: Re-analyze with randomization
            print("\n📊 Re-analyzing IFC files (randomized boundaries)...")
            analyze_script = scripts_dir / "analyze_ifc_for_sampling.py"

            result = subprocess.run(
                [sys.executable, str(analyze_script), "--ifc-dir", str(ifc_dir), "--randomize"],
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode != 0:
                print(f"Analysis failed:\n{result.stderr}")
                self.report({'ERROR'}, "IFC re-analysis failed. Check console.")
                return {'CANCELLED'}

            print(result.stdout)
            print("✓ Re-analysis complete (new region found)")

            # Step 2: Copy suggested config
            suggested_config = scripts_dir / "sample_config_suggested.json"
            active_config = scripts_dir / "sample_config.json"

            import shutil
            shutil.copy(suggested_config, active_config)
            print(f"✓ Updated {active_config.name} with new region")

            # Step 3: Re-run extraction
            print("\n⚙️  Re-extracting sample with new region...")
            # Use extraction script from IfcOpenShell repo (absolute path)
            extract_script = Path.home() / "Projects" / "IfcOpenShell" / "src" / "bonsai" / "scripts" / "extract_tessellation_to_db_v2.py"

            # Generate new timestamped database name
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            sample_db = scripts_dir.parent / "DatabaseFiles" / f"sample_extraction_{timestamp}.db"

            print(f"Output database: {sample_db}")

            result = subprocess.run(
                [sys.executable, str(extract_script), "--sample", "--output", str(sample_db)],
                capture_output=True,
                text=True,
                timeout=600
            )

            if result.returncode != 0:
                print(f"Extraction failed:\n{result.stderr}")
                self.report({'ERROR'}, "Sample re-extraction failed. Check console.")
                return {'CANCELLED'}

            print(result.stdout)

            # Step 4: Validate
            print("\n✅ Validating new sample...")
            validate_script = scripts_dir / "validate_sample_quick.py"

            validation_summary = "Validation skipped"
            if validate_script.exists():
                result = subprocess.run(
                    [sys.executable, str(validate_script), str(sample_db)],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                print(result.stdout)

                # Parse validation result for status bar
                if "SAMPLE READY FOR TESTING" in result.stdout:
                    validation_summary = "✅ New sample ready (all checks passed)"
                    self.report({'INFO'}, validation_summary)
                elif "SAMPLE ACCEPTABLE WITH WARNINGS" in result.stdout:
                    validation_summary = "⚠ New sample acceptable (some warnings)"
                    self.report({'WARNING'}, validation_summary)
                elif "SAMPLE NOT SUITABLE" in result.stdout:
                    validation_summary = "✗ New sample not suitable - try Redo again"
                    self.report({'ERROR'}, validation_summary)
                else:
                    validation_summary = "Validation completed"
                    self.report({'INFO'}, validation_summary)
            else:
                self.report({'WARNING'}, "Validation script not found")

            # Update props
            props.federation_database_path = str(sample_db)

            print(f"\n{'='*70}")
            print("✅ REDO COMPLETE - NEW SAMPLE READY")
            print(f"Database: {sample_db}")
            print(f"Validation: {validation_summary}")
            print(f"{'='*70}\n")

            return {'FINISHED'}

        except Exception as e:
            print(f"\n❌ Redo failed: {e}")
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, f"Redo failed: {str(e)}")
            return {'CANCELLED'}
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

        # LOG: Show raw property values for debugging (use print to ensure it shows in console)
        print(f"\n{'='*70}")
        print(f"[CLASH DETECTION] Raw UI Property Values:")
        print(f"  discipline_a = '{props.discipline_a}'")
        print(f"  discipline_b = '{props.discipline_b}'")
        print(f"  tolerance = {props.discipline_tolerance}")
        print(f"  preset = '{props.clash_preset}'")
        print(f"{'='*70}\n")
        logger.info(f"[DEBUG] Raw UI values: discipline_a={props.discipline_a}, discipline_b={props.discipline_b}, tolerance={props.discipline_tolerance}")

        # Handle presets - convert preset to discipline pairs
        preset = props.clash_preset

        # Preset mapping
        preset_map = {
            'ARC_STR': ('ARC', 'STR'),
            'ELEC_ARC': ('ELEC', 'ARC'),
            'ACMV_ARC': ('ACMV', 'ARC'),
            'FP_ARC': ('FP', 'ARC'),
            'SP_ARC': ('SP', 'ARC'),
        }

        if preset in preset_map:
            # Apply preset discipline mapping
            disc_a, disc_b = preset_map[preset]
            disciplines_a = [disc_a]
            disciplines_b = [disc_b]
            print(f"[PRESET] Applied '{preset}' → {disc_a} vs {disc_b}")
        elif preset == 'ALL_MEP':
            # Expand ALL_MEP to all MEP disciplines
            disciplines_a = ['ACMV', 'ELEC', 'FP']
            disciplines_b = ['ACMV', 'ELEC', 'FP']
            print(f"[PRESET] Applied 'ALL_MEP' → All MEP combinations")
        else:
            # CUSTOM: Use manual discipline selection
            disciplines_a = [props.discipline_a]
            disciplines_b = [props.discipline_b]
            print(f"[CUSTOM] Using manual selection → {props.discipline_a} vs {props.discipline_b}")

        tolerance = props.discipline_tolerance

        # Convert tolerance from meters to millimeters for detector
        tolerance_mm = tolerance * 1000.0
        print(f"[TOLERANCE] {tolerance}m = {tolerance_mm}mm")

        logger.info("\n" + "="*70)
        logger.info("DISCIPLINE CLASH DETECTION - OPTIMIZED FEDERATION DATABASE")
        logger.info("="*70)
        logger.info(f"Discipline A: {', '.join(disciplines_a)}")
        logger.info(f"Discipline B: {', '.join(disciplines_b)}")
        logger.info(f"Tolerance: {tolerance}m ({tolerance_mm}mm)")
        logger.info(f"Database: {db_path}")
        logger.info("-"*70)

        candidates = []

        try:
            # Check if clash cache exists in clash_status table
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Check if there's a specific discipline pair in cache first
            # This allows partial cache usage
            cursor.execute("SELECT COUNT(*) FROM clash_status")
            cached_clash_count = cursor.fetchone()[0]

            logger.info("=" * 70)
            if cached_clash_count > 0:
                logger.info(f"CLASH CACHE: {cached_clash_count} clashes found")
                logger.info("Will use cache if discipline pair exists, otherwise run detection")
            else:
                logger.info("NO CACHE FOUND - Will run full clash detection")
            logger.info("=" * 70)

            # Run clash detection for all discipline combinations
            for disc_a in disciplines_a:
                for disc_b in disciplines_b:
                    # Skip self-clashes (same discipline vs itself)
                    if disc_a == disc_b:
                        logger.info(f"[SKIP] {disc_a} vs {disc_b} - Same discipline, skipping self-clash")
                        continue

                    logger.info(f"\n{'='*60}")
                    logger.info(f"[PROCESSING] Discipline Pair: {disc_a} vs {disc_b}")
                    logger.info(f"{'='*60}")
                    start_time = __import__('time').time()

                    # Check if this specific discipline pair exists in cache
                    cursor.execute("""
                        SELECT COUNT(*) FROM clash_status
                        WHERE (discipline_a = ? AND discipline_b = ?)
                           OR (discipline_a = ? AND discipline_b = ?)
                    """, (disc_a, disc_b, disc_b, disc_a))

                    pair_cache_count = cursor.fetchone()[0]
                    pair_in_cache = pair_cache_count > 0

                    if pair_in_cache:
                        # FAST PATH: This pair is in cache
                        logger.info(f"[CACHE HIT] Found {pair_cache_count} clashes for {disc_a}-{disc_b} in cache")
                        cursor.execute("""
                            SELECT
                                guid_a, guid_b, name_a, name_b,
                                ifc_class_a, ifc_class_b,
                                discipline_a, discipline_b, distance
                            FROM clash_status
                            WHERE (discipline_a = ? AND discipline_b = ?)
                               OR (discipline_a = ? AND discipline_b = ?)
                        """, (disc_a, disc_b, disc_b, disc_a))

                        clashes = []
                        for row in cursor.fetchall():
                            clashes.append({
                                'elem_a_guid': row[0],
                                'elem_b_guid': row[1],
                                'elem_a_ifc_class': row[4],
                                'elem_b_ifc_class': row[5],
                                'elem_a_discipline': row[6],
                                'elem_b_discipline': row[7],
                                'clearance': row[8] or 0
                            })
                        logger.info(f"[CACHE] Loaded {len(clashes)} clashes from cache")
                    else:
                        # SLOW PATH: Not in cache, run detection
                        logger.info(f"[CACHE MISS] {disc_a}-{disc_b} not in cache, will run detection")
                        logger.info(f"[DETECTION] Running bbox clash detection for {disc_a} vs {disc_b}...")
                        from .clash.detector import detect_clashes_from_database

                        all_clashes = detect_clashes_from_database(
                            db_path,
                            tolerance_mm=tolerance_mm,
                            discipline_a=disc_a,
                            discipline_b=disc_b
                        )
                        clashes = all_clashes

                        # Store in cache for future use
                        logger.info(f"[CACHING] Storing {len(clashes)} clashes in cache for {disc_a}-{disc_b}")
                        for clash in clashes:
                            cursor.execute("""
                                INSERT OR IGNORE INTO clash_status
                                (guid_a, guid_b, name_a, name_b, ifc_class_a, ifc_class_b,
                                 discipline_a, discipline_b, distance)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                clash['elem_a_guid'], clash['elem_b_guid'],
                                clash['elem_a_guid'][:8], clash['elem_b_guid'][:8],
                                clash['elem_a_ifc_class'], clash['elem_b_ifc_class'],
                                clash['elem_a_discipline'], clash['elem_b_discipline'],
                                abs(clash.get('clearance', 0))
                            ))
                        conn.commit()

                    query_time = __import__('time').time() - start_time
                    logger.info(f"[RESULT] {disc_a} vs {disc_b}: {len(clashes)} clashes found in {query_time:.2f}s")
                    logger.info(f"{'='*60}\n")

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

            # Close database connection
            conn.close()

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


class BIM_OT_rebuild_clash_cache(bpy.types.Operator):
    """Rebuild clash cache by detecting all clashes across all disciplines"""
    bl_idname = "bim.rebuild_clash_cache"
    bl_label = "Rebuild Clash Cache"
    bl_description = "Run full clash detection and rebuild cache (clears existing cache)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import sqlite3
        import logging

        logger = logging.getLogger(__name__)
        fed_props = context.scene.BIMFederationProperties

        # Get database path
        db_path = fed_props.federation_database_path
        if not db_path:
            self.report({'ERROR'}, "Please load Federation Database first")
            return {'CANCELLED'}

        db_path = Path(bpy.path.abspath(db_path))
        if not db_path.exists():
            self.report({'ERROR'}, f"Database not found: {db_path}")
            return {'CANCELLED'}

        try:
            # Clear existing cache
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM clash_status")
            conn.commit()

            logger.info("=" * 70)
            logger.info("REBUILDING CLASH CACHE - FULL DETECTION")
            logger.info("=" * 70)

            # Run full clash detection (all disciplines)
            from .clash.detector import detect_clashes_from_database

            start_time = __import__('time').time()
            all_clashes = detect_clashes_from_database(
                db_path,
                tolerance_mm=10.0,  # Default tolerance
                disciplines=None  # All disciplines
            )

            # Store in cache
            for clash in all_clashes:
                cursor.execute("""
                    INSERT OR IGNORE INTO clash_status
                    (guid_a, guid_b, name_a, name_b, ifc_class_a, ifc_class_b,
                     discipline_a, discipline_b, distance)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    clash['elem_a_guid'], clash['elem_b_guid'],
                    clash['elem_a_guid'][:8], clash['elem_b_guid'][:8],
                    clash['elem_a_ifc_class'], clash['elem_b_ifc_class'],
                    clash['elem_a_discipline'], clash['elem_b_discipline'],
                    abs(clash.get('clearance', 0))
                ))

            conn.commit()
            conn.close()

            elapsed = __import__('time').time() - start_time

            logger.info(f"✓ Cache rebuilt: {len(all_clashes)} clashes stored in {elapsed:.2f}s")
            self.report({'INFO'}, f"Cache rebuilt: {len(all_clashes)} clashes in {elapsed:.2f}s")
            return {'FINISHED'}

        except Exception as e:
            logger.exception(f"Cache rebuild failed: {str(e)}")
            self.report({'ERROR'}, f"Cache rebuild failed: {str(e)}")
            return {'CANCELLED'}


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
        from bonsai.bim.module.federation.clash import gizmo

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
        from bonsai.bim.module.federation.clash import visualization
        from bonsai.bim.module.federation.clash import gizmo
        from bonsai.bim.module.federation.visualization import federation_viz_helper

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
        from bonsai.bim.module.federation.clash import visualization

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
        from bonsai.bim.module.federation.clash import visualization

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
        from bonsai.bim.module.federation.clash import gizmo

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
        from bonsai.bim.module.federation.clash import gizmo

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
        from bonsai.bim.module.federation.visualization import semantic_shapes

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
        from bonsai.bim.module.federation.visualization import semantic_shapes

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
        from bonsai.bim.module.federation.visualization import semantic_shapes

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
        from bonsai.bim.module.federation.visualization import semantic_shapes

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
        from bonsai.bim.module.federation.clash import clash_grouping

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
            from bonsai.bim.module.federation.clash import resolution_database
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
            print(f"Clashes Grouped: {summary['total_grouped_clashes']}/{summary['total_clashes']} ({summary['grouping_efficiency']:.1f}%)")
            print(f"\nGroup Details:")
            for i, group in enumerate(groups, 1):
                print(f"  Group {i}: {group.cascade_element_guid} ({group.cascade_element_class})")
                print(f"    Discipline: {group.cascade_element_discipline}")
                print(f"    Clashes: {group.total_clashes}, Severity: {group.severity}")
                print(f"    Affected Disciplines: {', '.join(group.affected_disciplines)}")
                print(f"    Status: {', '.join(f'{k}={v}' for k, v in group.status_summary.items())}")
            print(f"{'='*60}\n")

            # Set flag to show resolution options UI
            props.clash_groups_analyzed = True

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
        from bonsai.bim.module.federation.clash import resolution_engine

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


class BIM_OT_preview_clash_group(bpy.types.Operator):
    """Preview entire clash group in 3D viewport"""
    bl_idname = "bim.preview_clash_group"
    bl_label = "Preview Clash Group"
    bl_description = "Load and visualize cascade element and all clashing elements in the selected group"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        import logging
        from pathlib import Path

        logger = logging.getLogger(__name__)

        try:
            # Get properties
            props = tool.Clash.get_clash_props()
            fed_props = context.scene.BIMFederationProperties

            # Get selected group
            selected_group = props.selected_clash_group
            if not selected_group or selected_group == "NONE":
                self.report({'WARNING'}, "Please select a clash group first")
                return {'CANCELLED'}

            # Get database path
            db_path = fed_props.federation_database_path
            if not db_path:
                self.report({'ERROR'}, "Federation database not loaded")
                return {'CANCELLED'}

            db_path = Path(bpy.path.abspath(db_path))
            if not db_path.exists():
                self.report({'ERROR'}, f"Database not found: {db_path}")
                return {'CANCELLED'}

            # Check if current DB has GI geometry tables
            import sqlite3
            test_conn = sqlite3.connect(str(db_path))
            test_cursor = test_conn.cursor()
            test_cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='base_geometries'")
            has_geometry = test_cursor.fetchone() is not None
            test_conn.close()

            clash_db_path = db_path
            fed_db_path = db_path

            if not has_geometry:
                # Find GI database in same directory
                found = None
                for candidate in db_path.parent.glob("*GI.db"):
                    try:
                        c = sqlite3.connect(str(candidate))
                        cur = c.cursor()
                        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='base_geometries'")
                        if cur.fetchone():
                            found = candidate
                            c.close()
                            break
                        c.close()
                    except:
                        continue
                if found:
                    fed_db_path = found
                    print(f"  ✓ Clash data: {clash_db_path.name}")
                    print(f"  ✓ Geometry: {fed_db_path.name}")
                else:
                    fed_db_path = db_path  # Use same DB as fallback

            # Query clash group data
            conn = sqlite3.connect(str(clash_db_path))
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get group info
            cursor.execute("""
                SELECT cascade_element_guid, cascade_element_class,
                       cascade_element_discipline, total_clashes
                FROM clash_groups
                WHERE group_id = ?
            """, (selected_group,))

            group = cursor.fetchone()
            if not group:
                conn.close()
                self.report({'ERROR'}, f"Group {selected_group} not found")
                return {'CANCELLED'}

            # Get all clashes in group
            cursor.execute("""
                SELECT cs.guid_a, cs.guid_b
                FROM clash_group_members cgm
                JOIN clash_status cs ON cgm.clash_id = cs.clash_id
                WHERE cgm.group_id = ?
            """, (selected_group,))

            clash_rows = cursor.fetchall()
            conn.close()

            if not clash_rows:
                self.report({'WARNING'}, f"No clashes found in group")
                return {'CANCELLED'}

            # Identify clash pair elements (guid_a and guid_b from first clash in group)
            # These are the two elements that are actually clashing
            first_clash = clash_rows[0]
            clash_pair_guid_a = first_clash['guid_a']
            clash_pair_guid_b = first_clash['guid_b']

            # Collect all unique GUIDs from clash pairs
            all_clash_guids = set()
            for row in clash_rows:
                all_clash_guids.add(row['guid_a'])
                all_clash_guids.add(row['guid_b'])

            # Build cascade levels for elements that clash with the clash pair elements
            # This creates the cascade: clash pair → immediate cascade → subsequent cascade
            cascade_levels = {}  # guid -> level (1=orange, 2+=yellow)

            # Level 1: Find elements that clash with the clash pair (ORANGE - immediate cascade)
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            placeholders = ','.join('?' * len(all_clash_guids))
            query = f"""
                SELECT DISTINCT guid_a, guid_b
                FROM clash_status
                WHERE (guid_a IN ({placeholders}) OR guid_b IN ({placeholders}))
                AND status != 'RESOLVED'
            """
            cursor.execute(query, list(all_clash_guids) * 2)
            level1_rows = cursor.fetchall()

            for guid_a, guid_b in level1_rows:
                # Add elements that aren't in the clash pair itself
                if guid_a not in all_clash_guids:
                    cascade_levels[guid_a] = 1  # Orange - immediate cascade
                if guid_b not in all_clash_guids:
                    cascade_levels[guid_b] = 1  # Orange - immediate cascade

            # Level 2+: Find elements that clash with level 1 (YELLOW - subsequent cascade)
            current_level_guids = set([g for g, l in cascade_levels.items() if l == 1])
            for level in range(2, 5):  # Levels 2, 3, 4 (all yellow)
                if not current_level_guids:
                    break

                placeholders = ','.join('?' * len(current_level_guids))
                query = f"""
                    SELECT DISTINCT guid_a, guid_b
                    FROM clash_status
                    WHERE (guid_a IN ({placeholders}) OR guid_b IN ({placeholders}))
                    AND status != 'RESOLVED'
                """
                cursor.execute(query, list(current_level_guids) * 2)
                next_level_rows = cursor.fetchall()

                next_level_guids = set()
                for guid_a, guid_b in next_level_rows:
                    if guid_a not in cascade_levels and guid_a not in all_clash_guids:
                        cascade_levels[guid_a] = level
                        next_level_guids.add(guid_a)
                    if guid_b not in cascade_levels and guid_b not in all_clash_guids:
                        cascade_levels[guid_b] = level
                        next_level_guids.add(guid_b)

                current_level_guids = next_level_guids

            conn.close()

            # All GUIDs to load: clash pair + cascade elements
            all_guids = all_clash_guids | set(cascade_levels.keys())

            logger.info(f"Loading group {selected_group}: {len(all_guids)} elements "
                       f"({len(all_clash_guids)} clash pair + {len(cascade_levels)} cascade)")

            # Create or get collection
            collection_name = f"Clash_Group_{selected_group}"
            if collection_name in bpy.data.collections:
                collection = bpy.data.collections[collection_name]
                # Clear existing objects
                for obj in collection.objects:
                    bpy.data.objects.remove(obj, do_unlink=True)
            else:
                collection = bpy.data.collections.new(collection_name)
                context.scene.collection.children.link(collection)

            # Load elements using visualization helper
            from .visualization.federation_viz_helper import find_or_create_element_from_database

            # Define colors
            clash_pair_color_a = (1.0, 0.0, 0.0, 1.0)  # RED - first element in clash pair
            clash_pair_color_b = (0.0, 0.5, 1.0, 1.0)  # BLUE - second element in clash pair
            immediate_cascade_color = (1.0, 0.5, 0.0, 1.0)  # ORANGE - immediate cascade (level 1)
            subsequent_cascade_color = (1.0, 1.0, 0.0, 1.0)  # YELLOW - subsequent cascade (levels 2+)

            loaded_count = 0
            for guid in all_guids:
                obj = find_or_create_element_from_database(
                    guid=guid,
                    db_path=str(fed_db_path),  # Use GI database for geometry
                    collection=collection
                )

                if obj:
                    # Determine color based on element type
                    if guid == clash_pair_guid_a:
                        color = clash_pair_color_a
                        color_name = "Clash_Pair_Red"
                    elif guid == clash_pair_guid_b:
                        color = clash_pair_color_b
                        color_name = "Clash_Pair_Blue"
                    elif guid in cascade_levels:
                        level = cascade_levels[guid]
                        if level == 1:
                            color = immediate_cascade_color
                            color_name = "Immediate_Cascade_Orange"
                        else:
                            color = subsequent_cascade_color
                            color_name = "Subsequent_Cascade_Yellow"
                    else:
                        # Other clash pair elements (if multiple clashes in group)
                        color = clash_pair_color_a
                        color_name = "Clash_Pair_Red"

                    # Apply material
                    if not obj.data.materials:
                        mat = bpy.data.materials.new(name=color_name)
                        mat.diffuse_color = color
                        mat.use_nodes = False
                        obj.data.materials.append(mat)
                    else:
                        # Modify existing material
                        obj.data.materials[0].diffuse_color = color

                    loaded_count += 1

            if loaded_count == 0:
                self.report({'WARNING'}, "No elements could be loaded")
                return {'CANCELLED'}

            # Focus camera on group
            # Select all objects in collection
            bpy.ops.object.select_all(action='DESELECT')
            for obj in collection.objects:
                obj.select_set(True)

            # Frame selected objects in viewport (if in 3D view)
            if collection.objects:
                context.view_layer.objects.active = collection.objects[0]

                # Try to frame view if in 3D viewport
                for area in context.screen.areas:
                    if area.type == 'VIEW_3D':
                        for region in area.regions:
                            if region.type == 'WINDOW':
                                with context.temp_override(area=area, region=region):
                                    bpy.ops.view3d.view_selected()
                                break
                        break

            # Report with color legend
            orange_count = len([g for g, l in cascade_levels.items() if l == 1])
            yellow_count = len([g for g, l in cascade_levels.items() if l > 1])

            color_legend = (
                f"Loaded {loaded_count} elements - Color legend: "
                f"RED/BLUE=clash pair, ORANGE=immediate cascade ({orange_count}), "
                f"YELLOW=subsequent cascade ({yellow_count})"
            )
            self.report({'INFO'}, color_legend)

            print(f"\n{'='*70}")
            print(f"CLASH GROUP PREVIEW - Color Scheme:")
            print(f"{'='*70}")
            print(f"  🔴 RED:    First element in clash pair")
            print(f"  🔵 BLUE:   Second element in clash pair")
            print(f"  🟠 ORANGE: Immediate cascade ({orange_count} elements - clash with pair)")
            print(f"  🟡 YELLOW: Subsequent cascade ({yellow_count} elements - levels 2-4)")
            print(f"{'='*70}\n")

            return {'FINISHED'}

        except Exception as e:
            logger.exception("Failed to preview clash group")
            self.report({'ERROR'}, f"Preview failed: {str(e)}")
            import traceback
            traceback.print_exc()
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
        name="Generate Snapshots (SLOW - may take minutes)",
        description="Render PNG images for each clash. WARNING: Slow for large scenes (>10K objects). Automatically disabled for scenes >10K objects to prevent OOM crashes",
        default=False
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
                # PERFORMANCE: Check scene size and choose rendering mode
                scene_obj_count = len([o for o in bpy.data.objects if o.type == 'MESH'])

                # Determine render mode based on scene size
                if scene_obj_count > 100000:
                    # VERY LARGE: Skip entirely
                    logger.warning(f"Scene has {scene_obj_count} objects - snapshot rendering disabled (too large)")
                    self.report({'WARNING'}, f"Scene too large ({scene_obj_count} objects) - exporting viewpoints only")
                    snapshots = None
                elif scene_obj_count > 50000:
                    # LARGE: Warn but allow fast mode
                    logger.info(f"Scene has {scene_obj_count} objects - using FAST viewport screenshot mode")
                    self.report({'INFO'}, f"Large scene detected - using fast snapshot mode (~30s for {len(viewpoints)} snapshots)")
                    fast_mode = True
                elif scene_obj_count > 10000:
                    # MEDIUM: Recommend fast mode
                    logger.info(f"Scene has {scene_obj_count} objects - using fast viewport screenshot mode")
                    self.report({'INFO'}, f"Rendering {len(viewpoints)} fast snapshots (~1min total)...")
                    fast_mode = True
                else:
                    # SMALL: Can use full render
                    logger.info(f"Scene has {scene_obj_count} objects - using standard render mode")
                    self.report({'INFO'}, f"Rendering {len(viewpoints)} quality snapshots (may take 3-5 minutes)...")
                    fast_mode = False

                if scene_obj_count <= 100000:
                    # Attempt rendering
                    try:
                        import time
                        start_time = time.time()

                        snapshots = snapshot_renderer.render_all_clash_snapshots(
                            viewpoints,
                            clash_ids,
                            width=800,
                            height=600,
                            fast_mode=fast_mode
                        )

                        elapsed = time.time() - start_time
                        if snapshots:
                            avg_time = elapsed / len(snapshots) if snapshots else 0
                            self.report({'INFO'}, f"✓ Rendered {len(snapshots)} snapshots in {elapsed:.1f}s ({avg_time:.1f}s each)")
                            logger.info(f"Snapshot rendering: {len(snapshots)} images in {elapsed:.1f}s")
                        else:
                            logger.warning("No snapshots were generated")
                            self.report({'WARNING'}, "Snapshot rendering produced no images")

                    except Exception as e:
                        logger.warning(f"Snapshot rendering failed: {e}")
                        self.report({'WARNING'}, f"Snapshot rendering failed: {str(e)[:100]}")
                        snapshots = None

            # Generate BCF ZIP file
            self.report({'INFO'}, "Creating BCF file...")
            logger.info("Generating BCF ZIP file...")

            success, message = bcf_generator.generate_bcf_zip(
                self.filepath,
                clash_ids=clash_ids,
                include_resolved=self.include_resolved,
                viewpoints=viewpoints,
                snapshots=snapshots
            )

            if success:
                # Log success with summary
                logger.info("="*70)
                logger.info("BCF EXPORT COMPLETED SUCCESSFULLY")
                logger.info("="*70)
                logger.info(f"  Output file: {self.filepath}")
                logger.info(f"  {message}")
                logger.info(f"  Clashes exported: {len(clash_ids) if clash_ids else 'all'}")
                logger.info(f"  Viewpoints: {len(viewpoints)}")
                logger.info(f"  Snapshots: {len(snapshots) if snapshots else 0}")
                if not snapshots:
                    logger.info("  Note: Snapshots skipped (large scene optimization)")
                logger.info("="*70)

                # User-facing messages
                self.report({'INFO'}, f"✅ BCF exported successfully!")
                self.report({'INFO'}, f"   File: {self.filepath}")
                self.report({'INFO'}, f"   {message}")
                print(f"\n{'='*70}")
                print(f"✅ BCF EXPORT SUCCESS")
                print(f"{'='*70}")
                print(f"File: {self.filepath}")
                print(f"Topics: {len(clash_ids) if clash_ids else 'all'}")
                print(f"Viewpoints: {len(viewpoints)}")
                print(f"Snapshots: {len(snapshots) if snapshots else 0}")
                if not snapshots:
                    print(f"Note: Snapshots skipped for performance (scene has {scene_obj_count if 'scene_obj_count' in dir() else '?'} objects)")
                print(f"{'='*70}\n")

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


class BIM_OT_generate_clash_resolution_report(bpy.types.Operator):
    """Generate Markdown report for clash resolution analysis"""
    bl_idname = "bim.generate_clash_resolution_report"
    bl_label = "Generate Resolution Report"
    bl_description = "Generate professional Markdown report with cost analysis and clash overview snapshots"
    bl_options = {'REGISTER'}

    # Properties
    output_directory: bpy.props.StringProperty(
        name="Output Directory",
        description="Directory to save report and snapshots",
        default="",
        subtype='DIR_PATH'
    )

    project_name: bpy.props.StringProperty(
        name="Project Name",
        description="Name of the project",
        default="BIM Project"
    )

    analyst_name: bpy.props.StringProperty(
        name="Analyst Name",
        description="Name of the analyst/reporter",
        default=""
    )

    include_snapshots: bpy.props.BoolProperty(
        name="Include Snapshots",
        description="Generate clash overview snapshots showing affected elements (adds ~2s per group)",
        default=True
    )

    def invoke(self, context, event):
        """Show dialog to configure report settings."""
        # Set default output directory
        if not self.output_directory:
            timestamp = __import__('datetime').datetime.now().strftime("%Y%m%d_%H%M%S")
            default_dir = Path.home() / "Documents" / "bonsai" / "clash_reports" / f"clash_resolution_{timestamp}"
            self.output_directory = str(default_dir)

        # Set default analyst name from user preferences
        if not self.analyst_name:
            # Try to get author from preferences (may not exist in all Blender versions)
            try:
                self.analyst_name = context.preferences.system.author or "[Analyst Name]"
            except AttributeError:
                self.analyst_name = "[Analyst Name]"

        return context.window_manager.invoke_props_dialog(self, width=500)

    def draw(self, context):
        """Draw the dialog UI."""
        layout = self.layout
        layout.prop(self, "project_name")
        layout.prop(self, "analyst_name")
        layout.prop(self, "output_directory")
        layout.prop(self, "include_snapshots")

        # Show estimate
        fed_props = context.scene.BIMFederationProperties
        db_path = fed_props.federation_database_path

        if db_path and Path(bpy.path.abspath(db_path)).exists():
            try:
                import sqlite3
                conn = sqlite3.connect(bpy.path.abspath(db_path))
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM clash_groups")
                num_groups = cursor.fetchone()[0]
                conn.close()

                # Estimate time
                base_time = 2  # seconds for report generation
                snapshot_time = num_groups * 2 if self.include_snapshots else 0
                total_time = base_time + snapshot_time

                box = layout.box()
                box.label(text=f"Clash Groups: {num_groups}", icon='INFO')
                box.label(text=f"Estimated Time: ~{total_time:.0f} seconds")

            except Exception as e:
                box = layout.box()
                box.label(text="Could not estimate time", icon='ERROR')

    def execute(self, context):
        """Execute the report generation."""
        import logging
        from datetime import datetime
        import tempfile

        # Setup dedicated logger for report generation
        logger = logging.getLogger('bonsai.report_generation')
        logger.setLevel(logging.INFO)

        # Clear any existing handlers to avoid spam
        logger.handlers.clear()

        # Setup console log file handler
        log_dir = Path.home() / "Documents/bonsai/consolelogs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"report_generation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(file_handler)

        # Also add console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter('%(message)s'))
        logger.addHandler(console_handler)

        # Get database path
        fed_props = context.scene.BIMFederationProperties
        db_path = fed_props.federation_database_path

        if not db_path:
            logger.error("No federation database loaded")
            self.report({'ERROR'}, "Please load Federation Database first")
            logger.removeHandler(file_handler)
            file_handler.close()
            return {'CANCELLED'}

        db_path = Path(bpy.path.abspath(db_path))
        if not db_path.exists():
            logger.error(f"Database not found: {db_path}")
            self.report({'ERROR'}, f"Database not found: {db_path}")
            logger.removeHandler(file_handler)
            file_handler.close()
            return {'CANCELLED'}

        # Create output directory
        output_path = Path(self.output_directory)

        try:
            output_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.error(f"Could not create output directory: {e}")
            self.report({'ERROR'}, f"Could not create output directory: {e}")
            logger.removeHandler(file_handler)
            file_handler.close()
            return {'CANCELLED'}

        logger.info("="*70)
        logger.info("GENERATING CLASH RESOLUTION REPORT")
        logger.info("="*70)
        logger.info(f"Project: {self.project_name}")
        logger.info(f"Analyst: {self.analyst_name}")
        logger.info(f"Database: {db_path}")
        logger.info(f"Output: {output_path}")
        logger.info(f"Include Snapshots: {self.include_snapshots}")
        logger.info(f"Log File: {log_file}")
        logger.info("-"*70)

        try:
            # Import report generator
            from .clash.report.report_generator import ReportGenerator

            # Generate report
            self.report({'INFO'}, "Generating report...")
            generator = ReportGenerator(str(db_path))

            success, message = generator.generate_report(
                output_dir=str(output_path),
                project_name=self.project_name,
                analyst_name=self.analyst_name
            )

            if not success:
                logger.error(f"Report generation failed: {message}")
                self.report({'ERROR'}, message)
                return {'CANCELLED'}

            logger.info(f"✅ Report generated: {message}")

            # Generate snapshots if requested
            if self.include_snapshots:
                self.report({'INFO'}, "Generating snapshots...")
                logger.info("Generating clash overview snapshots...")

                try:
                    from .clash.report.snapshot_manager import SnapshotManager

                    snapshot_mgr = SnapshotManager(str(db_path))

                    # Check feasibility
                    import sqlite3
                    conn = sqlite3.connect(str(db_path))
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM clash_groups")
                    num_groups = cursor.fetchone()[0]
                    conn.close()

                    feasible, feasibility_msg = snapshot_mgr.check_snapshot_feasibility(num_groups)
                    logger.info(f"Snapshot feasibility: {feasibility_msg}")

                    if not feasible:
                        logger.warning("Snapshot generation may take longer than expected")
                        self.report({'WARNING'}, "Snapshot generation may be slow - consider reducing group count")

                    # Generate snapshots
                    successful, failed, errors = snapshot_mgr.generate_all_group_snapshots(
                        output_path,
                        width=1920,
                        height=1080
                    )

                    if successful > 0:
                        logger.info(f"✅ Generated {successful} snapshots")
                        self.report({'INFO'}, f"Generated {successful} snapshots")

                    if failed > 0:
                        logger.warning(f"⚠️ Failed to generate {failed} snapshots")
                        self.report({'WARNING'}, f"Failed to generate {failed} snapshots")
                        for error in errors[:5]:  # Show first 5 errors
                            logger.warning(f"  - {error}")

                except ImportError as e:
                    logger.warning(f"Snapshot generation not available: {e}")
                    self.report({'WARNING'}, "Snapshots skipped - BCF renderer not available")
                except Exception as e:
                    logger.error(f"Snapshot generation failed: {e}")
                    self.report({'WARNING'}, f"Snapshots failed: {str(e)[:100]}")

            # Success summary
            logger.info("="*70)
            logger.info("REPORT GENERATION COMPLETED")
            logger.info("="*70)
            logger.info(f"Output: {output_path}")
            logger.info(f"Files: report.md, metadata.json, data_export.csv")
            if self.include_snapshots:
                logger.info(f"Snapshots: snapshots/ directory")
            logger.info("="*70)

            # User-facing message
            self.report({'INFO'}, f"✅ Report generated successfully!")
            self.report({'INFO'}, f"   Location: {output_path}")
            self.report({'INFO'}, f"   Open report.md to view and edit")

            print(f"\n{'='*70}")
            print(f"✅ CLASH RESOLUTION REPORT GENERATED")
            print(f"{'='*70}")
            print(f"Location: {output_path}")
            print(f"Files:")
            print(f"  - report.md (editable Markdown report)")
            print(f"  - metadata.json (report metadata)")
            print(f"  - data_export.csv (clash data)")
            if self.include_snapshots:
                print(f"  - snapshots/ (clash overview images)")
            print(f"\nNext steps:")
            print(f"  1. Open report.md in a text editor")
            print(f"  2. Customize as needed")
            print(f"  3. Convert to PDF: pandoc report.md -o report.pdf")
            print(f"  4. Distribute to project team")
            print(f"{'='*70}\n")

            return {'FINISHED'}

        except Exception as e:
            logger.exception("Report generation failed with exception")
            self.report({'ERROR'}, f"Report generation failed: {str(e)}")
            logger.info(f"Error details saved to: {log_file}")
            return {'CANCELLED'}
        finally:
            # Remove all handlers
            if 'file_handler' in locals():
                logger.removeHandler(file_handler)
                file_handler.close()
            if 'console_handler' in locals():
                logger.removeHandler(console_handler)


# ============================================================================
# 4D SCHEDULING OPERATORS
# ============================================================================

class BIM_OT_generate_construction_schedule(bpy.types.Operator):
    """Generate 4D construction schedule from federation database"""
    bl_idname = "bim.generate_construction_schedule"
    bl_label = "Generate Construction Schedule"
    bl_description = "Generate 4D construction schedule with task durations based on labor productivity"

    def execute(self, context):
        from datetime import datetime

        # Get database path
        fed_props = context.scene.BIMFederationProperties
        db_path = fed_props.federation_database_path

        if not db_path or not os.path.exists(db_path):
            self.report({'ERROR'}, "Federation database not found. Set database path first.")
            return {'CANCELLED'}

        try:
            self.report({'INFO'}, "Generating construction schedule...")

            # Import schedule generator
            from bonsai.bim.module.federation.schedule.schedule_generator import generate_construction_schedule

            # Generate schedule
            project_name = "Terminal 1 Construction"
            start_date = "2025-01-06"  # TODO: Make this configurable in UI

            tasks_created = generate_construction_schedule(db_path, start_date, project_name)

            self.report({'INFO'}, f"✅ Schedule generated: {tasks_created} tasks created")
            return {'FINISHED'}

        except Exception as e:
            logger.exception("Schedule generation failed")
            self.report({'ERROR'}, f"Schedule generation failed: {str(e)}")
            return {'CANCELLED'}


class BIM_OT_export_mpp_schedule(bpy.types.Operator):
    """Export construction schedule to MS Project XML format"""
    bl_idname = "bim.export_mpp_schedule"
    bl_label = "Export to MS Project"
    bl_description = "Export schedule to MS Project XML (compatible with MS Project, ProjectLibre, Primavera P6)"

    def execute(self, context):
        from datetime import datetime
        import subprocess
        import sys

        # Get database path
        fed_props = context.scene.BIMFederationProperties
        db_path = fed_props.federation_database_path

        if not db_path or not os.path.exists(db_path):
            self.report({'ERROR'}, "Federation database not found. Set database path first.")
            return {'CANCELLED'}

        # Check if construction_schedule table exists
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='construction_schedule'"
        )
        has_schedule_table = cursor.fetchone() is not None
        conn.close()

        if not has_schedule_table:
            self.report({'ERROR'}, "Schedule not generated yet. Click 'Generate Schedule' first.")
            return {'CANCELLED'}

        try:
            self.report({'INFO'}, "Exporting to MS Project XML...")

            # Import MPP exporter
            from bonsai.bim.module.federation.schedule.mpp_export import export_to_mpp_xml
            from pathlib import Path

            # Generate output path in WORK_DIR/schedules/
            # Database is in WORK_DIR/databases/, so go up one level to find WORK_DIR
            db_path_obj = Path(db_path)
            work_dir = db_path_obj.parent.parent  # ../.. from databases/Terminal1.db
            schedules_dir = work_dir / "schedules"
            schedules_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = schedules_dir / f"Terminal1_Schedule_{timestamp}.xml"

            # Export
            project_name = "Terminal 1 Construction"
            result_path = export_to_mpp_xml(str(db_path), str(output_path), project_name)

            self.report({'INFO'}, f"✅ Schedule exported: {os.path.basename(result_path)}")

            # Auto-open XML file (can be imported into MS Project/ProjectLibre)
            try:
                if sys.platform.startswith('linux'):
                    # Try to open with default XML viewer
                    subprocess.Popen(['xdg-open', result_path])
                elif sys.platform == 'darwin':
                    subprocess.Popen(['open', result_path])
                elif sys.platform == 'win32':
                    os.startfile(result_path)
            except Exception as e:
                logger.warning(f"Could not auto-open file: {e}")
                self.report({'INFO'}, f"File saved: {result_path}")

            return {'FINISHED'}

        except Exception as e:
            logger.exception("MPP export failed")
            self.report({'ERROR'}, f"MPP export failed: {str(e)}")
            return {'CANCELLED'}


class BIM_OT_export_schedule_excel(bpy.types.Operator):
    """Export construction schedule to Excel format (for users without MS Project)"""
    bl_idname = "bim.export_schedule_excel"
    bl_label = "Export to Excel"
    bl_description = "Export schedule to Excel spreadsheet with Gantt-style layout"

    def execute(self, context):
        from datetime import datetime
        import subprocess
        import sys

        # Get database path
        fed_props = context.scene.BIMFederationProperties
        db_path = fed_props.federation_database_path

        if not db_path or not os.path.exists(db_path):
            self.report({'ERROR'}, "Federation database not found. Set database path first.")
            return {'CANCELLED'}

        # Check if construction_schedule table exists
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='construction_schedule'"
        )
        has_schedule_table = cursor.fetchone() is not None
        conn.close()

        if not has_schedule_table:
            self.report({'ERROR'}, "Schedule not generated yet. Click 'Generate Schedule' first.")
            return {'CANCELLED'}

        try:
            self.report({'INFO'}, "Exporting to Excel...")

            # Import Excel exporter
            from bonsai.bim.module.federation.schedule.excel_export import export_schedule_to_excel
            from pathlib import Path

            # Generate output path in WORK_DIR/schedules/
            # Database is in WORK_DIR/databases/, so go up one level to find WORK_DIR
            db_path_obj = Path(db_path)
            work_dir = db_path_obj.parent.parent  # ../.. from databases/Terminal1.db
            schedules_dir = work_dir / "schedules"
            schedules_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = schedules_dir / f"Terminal1_Schedule_{timestamp}.xlsx"

            # Export
            project_name = "Terminal 1 Construction"
            result_path = export_schedule_to_excel(str(db_path), str(output_path), project_name)

            self.report({'INFO'}, f"✅ Schedule exported to Excel: {os.path.basename(result_path)}")

            # Auto-open Excel file
            try:
                if sys.platform.startswith('linux'):
                    subprocess.Popen(['xdg-open', result_path])
                elif sys.platform == 'darwin':
                    subprocess.Popen(['open', result_path])
                elif sys.platform == 'win32':
                    os.startfile(result_path)
            except Exception as e:
                logger.warning(f"Could not auto-open file: {e}")
                self.report({'INFO'}, f"File saved: {result_path}")

            return {'FINISHED'}

        except Exception as e:
            logger.exception("Excel export failed")
            self.report({'ERROR'}, f"Excel export failed: {str(e)}")
            return {'CANCELLED'}


class BIM_OT_animate_4d_construction(bpy.types.Operator):
    """Animate construction sequence in Blender viewport (4D BIM)"""
    bl_idname = "bim.animate_4d_construction"
    bl_label = "Animate 4D Construction"
    bl_description = "Create visibility animation showing construction sequence over time\n\nNote: All elements will be hidden at frame 0, then progressively appear based on construction schedule"

    frames_per_day: bpy.props.IntProperty(
        name="Frames per Day",
        description="How many Blender frames represent one calendar day (2 = 12 frames/week, smooth playback)",
        default=2,
        min=1,
        max=10
    )

    reset_to_end: bpy.props.BoolProperty(
        name="Show Complete Building After Creation",
        description="Jump to final frame after animation creation (shows complete building instead of empty frame 0)",
        default=True
    )

    def execute(self, context):
        # Get database path
        fed_props = context.scene.BIMFederationProperties
        db_path = fed_props.federation_database_path

        if not db_path or not os.path.exists(db_path):
            self.report({'ERROR'}, "Federation database not found. Set database path first.")
            return {'CANCELLED'}

        # Check if construction_schedule table exists
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='construction_schedule'"
        )
        has_schedule_table = cursor.fetchone() is not None
        conn.close()

        if not has_schedule_table:
            self.report({'ERROR'}, "Schedule not generated yet. Click 'Generate Schedule' first.")
            return {'CANCELLED'}

        try:
            self.report({'INFO'}, f"🎬 Creating 4D construction animation ({self.frames_per_day} frames/day)...")

            # Import optimized animator for better performance with large models
            from bonsai.bim.module.federation.schedule.animation_optimized import animate_construction_sequence_optimized

            # Create animation
            stats = animate_construction_sequence_optimized(db_path, self.frames_per_day)

            if stats['success']:
                # Optionally jump to end frame to show complete building
                if self.reset_to_end and stats['end_frame']:
                    bpy.context.scene.frame_set(stats['end_frame'])
                    self.report({'INFO'}, "Viewport reset to final frame (complete building)")

                self.report({'INFO'},
                    f"✅ Animation created: {stats['objects_animated']} objects, "
                    f"{stats['project_duration_days']:.0f} days, "
                    f"frames 0-{stats['end_frame']}"
                )
                self.report({'INFO'}, "Timeline: Frame 0 = empty, Frame {0} = complete | Press SPACE to play".format(stats['end_frame']))
                return {'FINISHED'}
            else:
                self.report({'WARNING'}, stats['message'])
                return {'CANCELLED'}

        except Exception as e:
            logger.exception("4D animation failed")
            self.report({'ERROR'}, f"Animation failed: {str(e)}")
            return {'CANCELLED'}


# ============================================================================
# BOQ (BILL OF QUANTITIES) OPERATORS
# ============================================================================

class BIM_OT_export_comprehensive_boq(bpy.types.Operator):
    """Export comprehensive Bill of Quantities with Malaysian standards"""
    bl_idname = "bim.export_comprehensive_boq"
    bl_label = "Export Comprehensive BOQ"
    bl_description = "Generate BOQ Excel report with Materials, Labor, Equipment breakdown"

    def execute(self, context):
        from datetime import datetime
        import subprocess
        import sys

        # Get database path
        fed_props = context.scene.BIMFederationProperties
        db_path = fed_props.federation_database_path

        if not db_path or not os.path.exists(db_path):
            self.report({'ERROR'}, "Federation database not found. Set database path first.")
            return {'CANCELLED'}

        # Check if simple_qto table exists
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='simple_qto'"
        )
        has_qto_table = cursor.fetchone() is not None
        conn.close()

        if not has_qto_table:
            self.report({'INFO'}, "Running QTO analysis first...")
            try:
                # Import and run QTO extraction
                from bonsai.bim.module.federation.dataintelligence.simple_qto_extract import extract_simple_qto

                print("\n" + "="*70)
                print("QTO EXTRACTION REQUIRED")
                print("="*70)
                print("Database lacks quantity takeoff data. Running extraction now...")
                print("This may take a few minutes depending on database size.\n")

                extract_simple_qto(db_path)

                print("\n✓ QTO extraction complete. Proceeding with BOQ generation...\n")
                self.report({'INFO'}, "QTO extraction complete. Generating BOQ...")

            except Exception as e:
                logger.exception("QTO extraction failed")
                self.report({'ERROR'}, f"QTO extraction failed: {str(e)}")
                return {'CANCELLED'}

        # Generate BOQ
        try:
            self.report({'INFO'}, "Generating comprehensive BOQ report...")

            # Import BOQ exporter
            from bonsai.bim.module.federation.dataintelligence.comprehensive_boq_export import ComprehensiveBOQExporter
            from pathlib import Path

            # Generate output path in WORK_DIR/boq_reports/
            # Database is in WORK_DIR/databases/, so go up one level to find WORK_DIR
            db_path_obj = Path(db_path)
            work_dir = db_path_obj.parent.parent  # ../.. from databases/Terminal1.db
            boq_reports_dir = work_dir / "boq_reports"
            boq_reports_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = boq_reports_dir / f"BOQ_Comprehensive_{timestamp}.xlsx"

            # Create exporter and generate
            exporter = ComprehensiveBOQExporter(str(output_path))
            project_name = "Terminal 1 Expansion Project"
            result_path = exporter.generate_comprehensive_boq(db_path, project_name)

            self.report({'INFO'}, f"✅ BOQ generated: {os.path.basename(result_path)}")

            # Auto-open Excel file
            try:
                if sys.platform.startswith('linux'):
                    subprocess.Popen(['xdg-open', result_path])
                elif sys.platform == 'darwin':
                    subprocess.Popen(['open', result_path])
                elif sys.platform == 'win32':
                    os.startfile(result_path)
            except Exception as e:
                logger.warning(f"Could not auto-open file: {e}")
                self.report({'INFO'}, f"File saved: {result_path}")

            return {'FINISHED'}

        except Exception as e:
            logger.exception("BOQ export failed")
            self.report({'ERROR'}, f"BOQ export failed: {str(e)}")
            return {'CANCELLED'}


class BIM_OT_open_boq_report(bpy.types.Operator):
    """Open existing BOQ Excel file"""
    bl_idname = "bim.open_boq_report"
    bl_label = "Open BOQ Report"
    bl_description = "Open the most recent BOQ Excel file"

    filepath: bpy.props.StringProperty(
        name="File Path",
        description="Path to BOQ Excel file",
        default=""
    )

    def execute(self, context):
        import subprocess
        import sys

        if not self.filepath or not os.path.exists(self.filepath):
            self.report({'ERROR'}, "BOQ file not found")
            return {'CANCELLED'}

        try:
            # Open file with default application
            if sys.platform.startswith('linux'):
                subprocess.Popen(['xdg-open', self.filepath])
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', self.filepath])
            elif sys.platform == 'win32':
                os.startfile(self.filepath)

            self.report({'INFO'}, f"Opening: {os.path.basename(self.filepath)}")
            return {'FINISHED'}

        except Exception as e:
            logger.exception("Failed to open BOQ file")
            self.report({'ERROR'}, f"Failed to open file: {str(e)}")
            return {'CANCELLED'}


class BIM_OT_regenerate_boq_report(bpy.types.Operator):
    """Regenerate BOQ Excel file (force refresh)"""
    bl_idname = "bim.regenerate_boq_report"
    bl_label = "Regenerate BOQ Report"
    bl_description = "Force regenerate BOQ report with latest database data"

    def execute(self, context):
        # Simply call the export operator (which generates a new timestamped file)
        return bpy.ops.bim.export_comprehensive_boq()


# ============================================================================
# Structural Works - Rebar & Concrete Operators
# ============================================================================


class BIM_OT_generate_rebar_structural(bpy.types.Operator):
    """Generate reinforcement (rebar) for structural concrete elements"""
    bl_idname = "bim.generate_rebar_structural"
    bl_label = "Generate Rebar Design"
    bl_description = "Automatically generate reinforcement for beams, slabs, and columns (MS 1347:2020)"

    def execute(self, context):
        from datetime import datetime

        # Get database path
        fed_props = context.scene.BIMFederationProperties
        db_path = fed_props.federation_database_path

        if not db_path or not os.path.exists(db_path):
            self.report({'ERROR'}, "Federation database not found. Set database path first.")
            return {'CANCELLED'}

        # Get structural settings
        structural_props = context.scene.BIMStructuralProperties
        is_airport = structural_props.is_airport_grade
        concrete_grade = structural_props.concrete_grade
        exposure_class = structural_props.exposure_class

        try:
            self.report({'INFO'}, f"Generating rebar design (Airport: {is_airport})...")

            # Import rebar generator
            from bonsai.bim.module.federation.structural.rebar_generator import RebarGenerator

            # Create generator
            generator = RebarGenerator(db_path, is_airport=is_airport)
            generator.connect()

            # Get STR elements count
            cursor = generator.conn.execute(
                "SELECT COUNT(*) FROM elements_meta WHERE discipline='STR' AND ifc_class IN ('IfcSlab', 'IfcBeam', 'IfcColumn')"
            )
            element_count = cursor.fetchone()[0]

            if element_count == 0:
                generator.disconnect()
                self.report({'WARNING'}, "No structural elements found in database")
                return {'CANCELLED'}

            self.report({'INFO'}, f"Processing {element_count} structural elements...")

            # Generate rebar for all STR elements
            results = generator.generate_all_rebar()

            generator.disconnect()

            # Report results - results is {'slabs': [...], 'beams': [...], 'columns': [...], 'errors': [...]}
            total_elements = len(results['slabs']) + len(results['beams']) + len(results['columns'])
            total_bars = 0
            total_weight = 0

            # Sum up rebar from all element types
            for element_list in [results['slabs'], results['beams'], results['columns']]:
                for rebar_data in element_list:
                    # Count bars from all bar groups (main_bars, distribution_bars, etc.)
                    for key, value in rebar_data.items():
                        if isinstance(value, dict) and 'count' in value:
                            total_bars += value['count']

                    # Sum total weight
                    if 'total_weight_kg' in rebar_data:
                        total_weight += rebar_data['total_weight_kg']

            # Convert kg to tonnes
            total_weight_tonnes = total_weight / 1000.0

            # Save results to database for BOQ export
            logger.info(f"Saving {total_elements} rebar designs to database...")
            generator.save_to_database(results)
            logger.info("Rebar data saved to reinforcement tables")

            # NEW: Save as REB discipline elements for visualization & clash detection
            logger.info("Creating REB discipline elements for federation viewer...")
            from bonsai.bim.module.federation.structural.rebar_to_discipline import save_rebar_as_discipline

            try:
                reb_stats = save_rebar_as_discipline(db_path, results)
                logger.info(f"✅ Created {reb_stats['total_reb_elements']} REB discipline elements")
                self.report({'INFO'},
                    f"✅ Rebar generated: {total_elements} STR elements → "
                    f"{reb_stats['total_reb_elements']} REB elements, "
                    f"{total_bars} bars, {total_weight_tonnes:.1f} tonnes")
            except Exception as e:
                logger.warning(f"REB discipline creation failed (non-critical): {e}")
                # Continue even if REB creation fails - BOQ export will still work
                self.report({'INFO'},
                    f"✅ Rebar generated: {total_elements} elements, {total_bars} bars, {total_weight_tonnes:.1f} tonnes "
                    f"(REB discipline creation skipped)")

            # Update UI property to indicate rebar is ready
            structural_props.rebar_generated = True
            structural_props.last_generation_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            return {'FINISHED'}

        except Exception as e:
            logger.exception("Rebar generation failed")
            self.report({'ERROR'}, f"Rebar generation failed: {str(e)}")
            return {'CANCELLED'}


class BIM_OT_export_structural_boq(bpy.types.Operator):
    """Export structural BOQ (Concrete + Rebar only) - MS 1347:2020"""
    bl_idname = "bim.export_structural_boq"
    bl_label = "Export Structural BOQ"
    bl_description = "Generate Excel BOQ for concrete and reinforcement works only"

    def execute(self, context):
        from datetime import datetime
        import subprocess
        import sys

        # Get database path
        fed_props = context.scene.BIMFederationProperties
        db_path = fed_props.federation_database_path

        if not db_path or not os.path.exists(db_path):
            self.report({'ERROR'}, "Federation database not found. Set database path first.")
            return {'CANCELLED'}

        # Check if rebar has been generated
        structural_props = context.scene.BIMStructuralProperties

        # Check if reinforcement_bars table exists
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='reinforcement_bars'"
        )
        has_rebar = cursor.fetchone() is not None
        conn.close()

        if not has_rebar:
            self.report({'WARNING'}, "No rebar data found. Run 'Generate Rebar Design' first.")
            # Offer to continue anyway (will show concrete only)
            self.report({'INFO'}, "Exporting concrete works only (no reinforcement)...")

        try:
            self.report({'INFO'}, "Generating structural BOQ report...")

            # Import BOQ exporter
            from bonsai.bim.module.federation.structural.boq_concrete_rebar_export import ConcreteRebarBOQ
            from pathlib import Path

            # Generate output path in WORK_DIR/boq_reports/
            # Database is in WORK_DIR/databases/, so go up one level to find WORK_DIR
            db_path_obj = Path(db_path)
            work_dir = db_path_obj.parent.parent  # ../.. from databases/Terminal1.db
            boq_reports_dir = work_dir / "boq_reports"
            boq_reports_dir.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = boq_reports_dir / f"BOQ_Structural_{timestamp}.xlsx"

            # Create exporter and generate complete BOQ
            exporter = ConcreteRebarBOQ(db_path, str(output_path))
            project_name = structural_props.project_name or "Terminal 1 Expansion Project"

            # Generate complete BOQ (orchestrates all sheets)
            exporter.generate_boq(project_name)

            self.report({'INFO'}, f"✅ Structural BOQ generated: {os.path.basename(output_path)}")

            # Update UI property
            structural_props.last_boq_export = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            structural_props.last_boq_file = output_path

            # Auto-open Excel file
            try:
                if sys.platform.startswith('linux'):
                    subprocess.Popen(['xdg-open', output_path])
                elif sys.platform == 'darwin':
                    subprocess.Popen(['open', output_path])
                elif sys.platform == 'win32':
                    os.startfile(output_path)
            except Exception as e:
                logger.warning(f"Could not auto-open file: {e}")

            return {'FINISHED'}

        except Exception as e:
            logger.exception("Structural BOQ export failed")
            self.report({'ERROR'}, f"Structural BOQ export failed: {str(e)}")
            return {'CANCELLED'}


# ============================================================================
# Natural Language Query (NLP) Operators
# ============================================================================


class BIM_OT_execute_nlp_query(bpy.types.Operator):
    """Execute natural language query against database"""
    bl_idname = "bim.execute_nlp_query"
    bl_label = "Execute NLP Query"
    bl_description = "Parse and execute natural language query using FTS5 search"

    def execute(self, context):
        props = context.scene.BIMFederationProperties
        query_text = props.nlp_query_text.strip()

        if not query_text:
            self.report({'WARNING'}, "Please enter a query")
            return {'CANCELLED'}

        # Get database path
        db_path = bpy.path.abspath(props.federation_database_path) if props.federation_database_path else None
        if not db_path or not os.path.exists(db_path):
            self.report({'ERROR'}, "Database not found. Please set database path first.")
            return {'CANCELLED'}

        try:
            # Import NLP modules
            from .dataintelligence.nlp.query_parser import NLPQueryParser
            from .dataintelligence.nlp.query_executor import QueryExecutor

            # Parse natural language query
            parser = NLPQueryParser()
            parse_result = parser.parse(query_text)

            if not parse_result['success']:
                error_msg = parse_result.get('error', 'Unknown parsing error')
                self.report({'ERROR'}, f"Query parsing failed: {error_msg}")
                props.nlp_results_text = f"❌ Error: {error_msg}"
                props.nlp_results_count = 0
                return {'CANCELLED'}

            # Execute SQL query
            executor = QueryExecutor(db_path)
            result = executor.execute_with_limit(parse_result['sql'], limit=100)

            if not result['success']:
                error_msg = result.get('error', 'Unknown execution error')
                self.report({'ERROR'}, f"Query execution failed: {error_msg}")
                props.nlp_results_text = f"❌ SQL Error: {error_msg}"
                props.nlp_results_count = 0
                return {'CANCELLED'}

            # Format results for display
            formatted_results = self._format_results(result, parse_result)
            props.nlp_results_text = formatted_results
            props.nlp_results_count = result['row_count']

            # Print full results to console
            print("\n" + "=" * 80)
            print(f"NLP Query: {query_text}")
            print(f"Category: {parse_result['category']}")
            print(f"Description: {parse_result['description']}")
            print(f"SQL: {parse_result['sql']}")
            print(f"Results: {result['row_count']} rows ({result['elapsed_ms']:.2f}ms)")
            print("=" * 80)
            print(formatted_results)
            print("=" * 80 + "\n")

            self.report({'INFO'}, f"Query executed: {result['row_count']} results in {result['elapsed_ms']:.2f}ms")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Query failed: {str(e)}")
            props.nlp_results_text = f"❌ Error: {str(e)}"
            props.nlp_results_count = 0
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}

    def _format_results(self, result, parse_result):
        """Format query results for display"""
        from .ifc_label_mapper import get_friendly_label

        lines = []

        # Check for special result types
        if result['row_count'] > 0 and 'result_type' in result['rows'][0]:
            result_type = result['rows'][0]['result_type']

            # Cost breakdown not available
            if result_type == 'BREAKDOWN_NOT_AVAILABLE':
                lines.append("💡 Cost Breakdown Information")
                lines.append("")
                lines.append("Cost breakdowns by material/labour/equipment are not stored in the database.")
                lines.append("")
                lines.append("📋 To get detailed cost breakdowns:")
                lines.append("  1. Navigate to Federation → BOQ Export")
                lines.append("  2. Generate a Bill of Quantities (BOQ)")
                lines.append("  3. The Excel export will include:")
                lines.append("     • Material costs")
                lines.append("     • Labour costs")
                lines.append("     • Equipment costs")
                lines.append("     • Complete cost breakdowns by element type")
                lines.append("")
                lines.append("💰 For total building cost, try: 'Total building cost'")
                return "\n".join(lines)

            # Storey information not available
            elif result_type == 'STOREY_NOT_AVAILABLE':
                lines.append("💡 Storey Information Not Available")
                lines.append("")
                lines.append("Storey/floor/level information is not populated in the current database.")
                lines.append("")
                lines.append("📋 To enable storey-based queries:")
                lines.append("  1. Ensure your IFC model has storey containment relationships")
                lines.append("  2. Re-extract the IFC files using Federation → Extract IFCs")
                lines.append("  3. The extraction process will populate storey information")
                lines.append("")
                lines.append("💡 Current working queries:")
                lines.append("  • 'How many doors?' (all doors in project)")
                lines.append("  • 'Count of beams' (all beams in project)")
                lines.append("  • 'Show ACMV elements' (by discipline)")
                return "\n".join(lines)

        # Header
        lines.append(f"📊 {parse_result['description']}")
        lines.append(f"⏱️ {result['elapsed_ms']:.2f}ms | {result['row_count']} rows")
        lines.append("")

        if result['row_count'] == 0:
            lines.append("No results found.")
            return "\n".join(lines)

        # Format based on category
        category = parse_result['category']
        rows = result['rows']

        if category == 'element_count':
            # Element count with friendly labels
            for row in rows[:15]:
                ifc_class = row.get('ifc_class', row.get('IFC_Class', ''))
                count = row.get('count', row.get('total', 0))

                if ifc_class:
                    friendly_name = get_friendly_label(ifc_class)
                    lines.append(f"  {friendly_name}: {count:,}")
                else:
                    lines.append(f"  Count: {count:,}")

        elif category == 'manufacturer':
            # Manufacturer search results with friendly labels
            for row in rows[:15]:
                element_name = row.get('element_name', row.get('Name', row.get('name', 'Unknown')))
                ifc_class = row.get('IFC_Class', row.get('ifc_class', ''))
                manufacturer = row.get('manufacturer', row.get('Manufacturer', ''))

                if ifc_class:
                    friendly_name = get_friendly_label(ifc_class, element_name)
                    lines.append(f"  • {friendly_name} - {manufacturer}")
                else:
                    lines.append(f"  • {element_name} - {manufacturer}")

        elif category == 'property_search':
            # Property search results
            for row in rows[:15]:
                name = row.get('Name', row.get('name', 'Unknown'))
                prop_name = row.get('PropertyName', row.get('property_name', ''))
                prop_value = row.get('PropertyValue', row.get('property_value', ''))
                lines.append(f"  • {name}: {prop_name} = {prop_value}")

        elif category in ['quantity', 'cost', 'material']:
            # Quantity, cost, and material aggregation results with friendly labels
            for row in rows[:15]:
                ifc_class = row.get('ifc_class', row.get('IFC_Class', ''))
                measurement_type = row.get('measurement_type', row.get('QuantityType', row.get('quantity_type', '')))
                total = row.get('total', row.get('Total', row.get('total_cost_rm', row.get('total_area', 0))))
                unit = row.get('uom', row.get('unit', row.get('Unit', '')))
                count = row.get('element_count', row.get('count', ''))

                if ifc_class:
                    friendly_name = get_friendly_label(ifc_class)

                    # Format based on what data we have
                    if category == 'cost' and 'total_cost_rm' in row:
                        cost_formatted = f"RM {total:,.2f}"
                        if count:
                            lines.append(f"  {friendly_name}: {cost_formatted} ({count:,} elements)")
                        else:
                            lines.append(f"  {friendly_name}: {cost_formatted}")
                    elif measurement_type:
                        lines.append(f"  {friendly_name} ({measurement_type}): {total:,.2f} {unit}")
                    else:
                        lines.append(f"  {friendly_name}: {total:,.2f} {unit}")
                else:
                    # No IFC class, format generically
                    if 'total_cost_rm' in row:
                        lines.append(f"  Total Cost: RM {total:,.2f}")
                    elif measurement_type:
                        lines.append(f"  {measurement_type}: {total:.2f} {unit}")
                    else:
                        lines.append(f"  Total: {total:.2f} {unit}")

        elif category == 'discipline':
            # Discipline breakdown - can show disciplines OR elements within a discipline
            for row in rows[:15]:
                discipline = row.get('Discipline', row.get('discipline', ''))
                ifc_class = row.get('ifc_class', row.get('IFC_Class', ''))
                count = row.get('element_count', row.get('count', row.get('Count', 0)))
                total_qty = row.get('total_quantity', '')
                uom = row.get('uom', '')

                if ifc_class:
                    # Showing elements within a discipline
                    friendly_name = get_friendly_label(ifc_class)
                    if total_qty:
                        lines.append(f"  {friendly_name}: {count:,} elements ({total_qty:.2f} {uom})")
                    else:
                        lines.append(f"  {friendly_name}: {count:,} elements")
                elif discipline:
                    # Showing discipline list
                    lines.append(f"  {discipline}: {count:,} elements")
                else:
                    lines.append(f"  {count:,} elements")

        elif category == 'freetext':
            # Free-text search results with friendly labels
            for row in rows[:15]:
                ifc_class = row.get('ifc_class', row.get('IFC_Class', ''))
                element_name = row.get('element_name', row.get('Name', row.get('name', '')))
                storey = row.get('storey', row.get('Storey', ''))

                if ifc_class:
                    friendly_name = get_friendly_label(ifc_class, element_name)
                    if storey:
                        lines.append(f"  • {friendly_name} (Level: {storey})")
                    else:
                        lines.append(f"  • {friendly_name}")
                else:
                    lines.append(f"  • {element_name}")

        else:
            # Generic table format with friendly labels where possible
            columns = result['columns']
            for row in rows[:15]:
                ifc_class = row.get('ifc_class', row.get('IFC_Class', ''))
                if ifc_class:
                    friendly_name = get_friendly_label(ifc_class)
                    # Replace ifc_class with friendly name in output
                    formatted_row = {k: (friendly_name if k in ['ifc_class', 'IFC_Class'] else v) for k, v in row.items()}
                    row_str = " | ".join(f"{k}: {v}" for k, v in formatted_row.items())
                else:
                    row_str = " | ".join(f"{k}: {v}" for k, v in row.items())
                lines.append(f"  {row_str}")

        if result['row_count'] > 15:
            lines.append(f"\n... and {result['row_count'] - 15} more rows (see console)")

        return "\n".join(lines)


class BIM_OT_set_nlp_query(bpy.types.Operator):
    """Set natural language query from suggested query button"""
    bl_idname = "bim.set_nlp_query"
    bl_label = "Set NLP Query"
    bl_description = "Set query text from suggested query"

    query_text: bpy.props.StringProperty(name="Query Text")

    def execute(self, context):
        props = context.scene.BIMFederationProperties
        props.nlp_query_text = self.query_text
        return {'FINISHED'}


class BIM_OT_clear_nlp_results(bpy.types.Operator):
    """Clear natural language query results"""
    bl_idname = "bim.clear_nlp_results"
    bl_label = "Clear NLP Results"
    bl_description = "Clear query results and reset query text"

    def execute(self, context):
        props = context.scene.BIMFederationProperties
        props.nlp_query_text = ""
        props.nlp_results_text = ""
        props.nlp_results_count = 0
        return {'FINISHED'}


class BIM_OT_export_nlp_results(bpy.types.Operator):
    """Export natural language query results to CSV"""
    bl_idname = "bim.export_nlp_results"
    bl_label = "Export NLP Results"
    bl_description = "Export query results to CSV file"

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    def invoke(self, context, event):
        props = context.scene.BIMFederationProperties

        if props.nlp_results_count == 0:
            self.report({'WARNING'}, "No results to export")
            return {'CANCELLED'}

        # Set default filename
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filepath = f"nlp_results_{timestamp}.csv"

        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        props = context.scene.BIMFederationProperties
        query_text = props.nlp_query_text.strip()

        if not query_text or props.nlp_results_count == 0:
            self.report({'WARNING'}, "No results to export")
            return {'CANCELLED'}

        # Get database path
        db_path = bpy.path.abspath(props.federation_database_path) if props.federation_database_path else None
        if not db_path or not os.path.exists(db_path):
            self.report({'ERROR'}, "Database not found")
            return {'CANCELLED'}

        try:
            import csv
            from .dataintelligence.nlp.query_parser import NLPQueryParser
            from .dataintelligence.nlp.query_executor import QueryExecutor

            # Re-execute query to get full results (not just display preview)
            parser = NLPQueryParser()
            parse_result = parser.parse(query_text)

            if not parse_result['success']:
                self.report({'ERROR'}, f"Query parsing failed: {parse_result.get('error', 'Unknown error')}")
                return {'CANCELLED'}

            executor = QueryExecutor(db_path)
            result = executor.execute(parse_result['sql'])  # No limit for export

            if not result['success']:
                self.report({'ERROR'}, f"Query execution failed: {result.get('error', 'Unknown error')}")
                return {'CANCELLED'}

            # Export to CSV
            with open(self.filepath, 'w', newline='', encoding='utf-8') as csvfile:
                if result['row_count'] > 0:
                    writer = csv.DictWriter(csvfile, fieldnames=result['columns'])
                    writer.writeheader()
                    writer.writerows(result['rows'])

            self.report({'INFO'}, f"Exported {result['row_count']} rows to {self.filepath}")
            return {'FINISHED'}

        except Exception as e:
            self.report({'ERROR'}, f"Export failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}


# =============================================================================
# WEB UI LAUNCHER (S56 — BIM_Designer_UserGuide.md §13)
# =============================================================================

class BIM_OT_launch_web_ui(bpy.types.Operator):
    """Open the BIM Designer Web UI in the default browser"""
    bl_idname = "bim.launch_web_ui"
    bl_label = "Open Web UI"
    bl_description = "Launch the BIM Designer Web UI at the specified tab"

    tab: bpy.props.StringProperty(
        name="Tab",
        default="1d",
        description="Tab to open (1d, 2d, 3d, 4d, 5d, 6d, 7d, 8, 9, 10)"
    )

    port: bpy.props.IntProperty(
        name="Port",
        default=9878,
        description="WebUIServer port"
    )

    def execute(self, context):
        import webbrowser
        url = f"http://localhost:{self.port}/#tab={self.tab}"
        webbrowser.open(url)
        self.report({'INFO'}, f"Opened Web UI: {url}")
        return {'FINISHED'}



# ── S178: RTree Inspector — Search + Pick operators ───────────────────────────

class FedRTreeSearch(bpy.types.Operator):
    """Search elements by name/GUID/discipline/class. Flies viewport to first match."""
    bl_idname = "bim.fed_rtree_search"
    bl_label = "Search & Fly"
    bl_description = "Search R-Tree DB and fly viewport to matching element"
    bl_options = {'REGISTER'}

    def execute(self, context):
        from . import bbox_visualization as bv
        props = context.scene.BIMFederationProperties
        term = props.rtree_search.strip()
        if not term:
            self.report({'WARNING'}, "Enter a search term first")
            return {'CANCELLED'}

        result = bv.navigate_to_element(term, context)

        if not result:
            props.rtree_result_name = ""
            props.rtree_result_disc = ""
            props.rtree_result_class = ""
            props.rtree_result_guid = ""
            props.rtree_result_count = 0
            self.report({'WARNING'}, f"No elements found for '{term}'")
            return {'CANCELLED'}

        # building-aware result: show building name + per-building match count
        building = result.get('building', '')
        count = result.get('count', 0)
        props.rtree_result_name = building or result.get('name', '') or result.get('guid', '')
        props.rtree_result_disc = result.get('disc', '')
        props.rtree_result_class = result.get('ifc_class', '')
        props.rtree_result_guid = result.get('guid', '')
        props.rtree_result_count = len(bv._highlighted_bboxes)  # number of buildings highlighted

        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

        n_buildings = props.rtree_result_count
        self.report({'INFO'}, f"{n_buildings} building(s) match — flew to '{building}' ({count} elements)")
        return {'FINISHED'}


class FedRTreeFlyToResult(bpy.types.Operator):
    """Fly to building and drill down to its matching elements (L2)."""
    bl_idname = "bim.fed_rtree_fly_to_result"
    bl_label = "Fly to Building"
    bl_options = {'REGISTER'}

    result_index: bpy.props.IntProperty(default=0)

    def execute(self, context):
        from . import bbox_visualization as bv
        ok = bv.fly_to_result(self.result_index, context)
        if not ok:
            self.report({'WARNING'}, "Result index out of range — run search first")
            return {'CANCELLED'}
        r = bv._search_results[self.result_index]

        # Drill into L2: fetch individual elements in this building
        props = context.scene.BIMFederationProperties
        bv.fetch_building_elements(r['building'], props.rtree_search)

        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()

        self.report({'INFO'}, f"→ {r['building']} | {len(bv._building_elements)} elements shown")
        return {'FINISHED'}


class FedRTreeFlyToElement(bpy.types.Operator):
    """Fly to a specific element from the L2 drill-down list."""
    bl_idname = "bim.fed_rtree_fly_to_element"
    bl_label = "Fly to Element"
    bl_options = {'REGISTER'}

    elem_index: bpy.props.IntProperty(default=0)

    def execute(self, context):
        from . import bbox_visualization as bv
        ok = bv.fly_to_element(self.elem_index, context)
        if not ok:
            self.report({'WARNING'}, "Element index out of range")
            return {'CANCELLED'}
        e = bv._building_elements[self.elem_index]
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        self.report({'INFO'}, f"{e['ifc_class']} | {e['storey']} | {e['guid'][:16]}")
        return {'FINISHED'}


class FedRTreePick(bpy.types.Operator):
    """Click on a bbox in the viewport to identify the element underneath."""
    bl_idname = "bim.fed_rtree_pick"
    bl_label = "Pick Element"
    bl_description = "Click a bounding box to identify the element (R-Tree query, no objects)"
    bl_options = {'REGISTER'}

    def invoke(self, context, event):
        context.window_manager.modal_handler_add(self)
        context.workspace.status_text_set("Click a bounding box to identify element — Esc to cancel")
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'ESC':
            context.workspace.status_text_set(None)
            return {'CANCELLED'}

        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            context.workspace.status_text_set(None)

            # Get world-space ray from mouse position
            try:
                from bpy_extras import view3d_utils
                region = None
                rv3d = None
                for area in context.screen.areas:
                    if area.type == 'VIEW_3D':
                        for reg in area.regions:
                            if reg.type == 'WINDOW':
                                region = reg
                                rv3d = area.spaces[0].region_3d
                                break
                        break

                if region is None or rv3d is None:
                    self.report({'WARNING'}, "No 3D viewport found")
                    return {'CANCELLED'}

                from mathutils import Vector
                mouse_co = (event.mouse_region_x, event.mouse_region_y)
                ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, mouse_co)
                ray_dir = view3d_utils.region_2d_to_vector_3d(region, rv3d, mouse_co)

            except Exception as e:
                self.report({'ERROR'}, f"Ray failed: {e}")
                return {'CANCELLED'}

            from . import bbox_visualization as bv
            result = bv.pick_element_at_ray(ray_origin, ray_dir)

            props = context.scene.BIMFederationProperties
            if result:
                if result.get('type') == 'building':
                    # S180 Pass 1: building envelope hit → drill into L2
                    building = result.get('building', '')
                    bv.fetch_building_elements(building, props.rtree_search)
                    props.rtree_picked_name = building
                    props.rtree_picked_disc = ''
                    props.rtree_picked_class = '(building envelope)'
                    props.rtree_picked_guid = ''
                    self.report({'INFO'}, f"§PROOF PICK_ENVELOPE building={building}")
                else:
                    # S180 Pass 2: individual element hit
                    props.rtree_picked_name = result.get('name', '') or result.get('guid', '')
                    props.rtree_picked_disc = result.get('disc', '')
                    props.rtree_picked_class = result.get('ifc_class', '')
                    props.rtree_picked_guid = result.get('guid', '')
                    self.report({'INFO'}, f"{result.get('disc','')} — {result.get('ifc_class','')}")
            else:
                self.report({'INFO'}, "No element hit — try clicking on a coloured box")

            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()

            return {'FINISHED'}

        return {'PASS_THROUGH'}
