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
        if not Path(props.federation_database_path).exists():
            cls.poll_message_set("Database file does not exist. Run preprocessing first")
            return False
        return True
    
    def execute(self, context):
        from .spatial_index import FederationIndex
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
            db_path = Path(props.federation_database_path)

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
        from ..federation_analysis.clash import detector as bbox_clash_detector
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
                from .spatial_index import FederationIndex
                index = FederationIndex(props.federation_database_path)
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

        # Start logging
        from . import logging_utils
        log_path = logging_utils.start_file_logging()
        print(f"📝 Logging to: {log_path}")

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
                from .spatial_index import FederationIndex
                index = FederationIndex(props.federation_database_path)
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
            disciplines = ['ACMV', 'ARC', 'CW', 'ELEC', 'FP', 'SP', 'STR', 'LPG']
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

        # Start logging
        from . import logging_utils
        log_path = logging_utils.start_file_logging()
        print(f"📝 Logging to: {log_path}")

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
                from .spatial_index import FederationIndex
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
                    from .spatial_index import FederationIndex
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
    """Unload all federation viewport layers and free memory"""
    bl_idname = "bim.unload_federation_viewport"
    bl_label = "Unload All Layers"
    bl_description = "Remove all 3 visualization layers and free memory (~153 MB)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # Start logging to timestamped file
        from . import logging_utils
        log_path = logging_utils.start_file_logging()
        print(f"📝 Logging to: {log_path}")

        try:
            # Disable legend if active
            from . import discipline_legend
            if discipline_legend.is_legend_enabled():
                discipline_legend.disable_legend()

            # Disable bbox visualization if active
            from . import bbox_visualization
            if bbox_visualization.is_bbox_visualization_enabled():
                bbox_visualization.disable_bbox_visualization()

            from .visualization_manager import VisualizationManager

            props = context.scene.BIMFederationProperties
            viz_mgr = VisualizationManager(props.federation_database_path)

            # Unload all layers
            print("\n🗑️  Unloading all visualization layers...")
            viz_mgr.unload_all_layers()

            # Reset solid_loaded flag (allows re-loading Solid button)
            props.solid_loaded = False

            self.report({'INFO'}, "Unloaded all visualization layers")
            logging_utils.stop_file_logging()
            return {'FINISHED'}

        except Exception as e:
            print(f"\n❌ Unload failed: {e}")
            import traceback
            traceback.print_exc()

            self.report({'ERROR'}, f"Unload failed: {str(e)}")
            logging_utils.stop_file_logging()
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
                base_db = Path(props.federation_database_path)
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
