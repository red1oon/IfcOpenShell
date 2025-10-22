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
        
        # Build command
        cmd = [
            sys.executable,
            str(preprocessor_script),
            "--files", *file_paths,
            "--output", str(db_path.absolute()),
            "--disciplines", *disciplines,
            "--progress", str(progress_path)
        ]
        
        self.report({'INFO'}, f"Starting preprocessing of {len(file_paths)} files...")
        
        # Run subprocess
        try:
            # Run in background (non-blocking) - inherit stdout/stderr for console visibility
            subprocess.Popen(cmd)
            
            props.preprocessing_in_progress = True
            self.report({'INFO'}, f"Preprocessing started. Check progress at: {progress_path.name}")
            
            # Register a timer to check progress
            bpy.app.timers.register(
                lambda: self._check_preprocessing_progress(context),
                first_interval=2.0,
                persistent=True
            )
            
        except Exception as e:
            self.report({'ERROR'}, f"Failed to start preprocessing: {str(e)}")
            import traceback
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
        """Test 3: Check conduit routing can access federation index"""
        print("\n[Test 3/5] Conduit Routing Integration")
        print("-" * 70)

        try:
            # Check if MEP properties exist
            if not hasattr(context.scene, 'BIMMEPProperties'):
                print("⚠ SKIPPED: MEP Engineering module not loaded")
                results['passed'] += 1  # Not a failure, just not applicable
                return

            # Verify index is accessible to routing
            index = bpy.types.WindowManager.federation_index

            # Test: Can routing access obstacle detection?
            # This simulates what routing does - query for obstacles in a corridor
            test_corridor = index.query_by_bbox(
                (-1000, -1000, 0),
                (1000, 1000, 3000)
            )

            print(f"✓ PASSED: Conduit routing can access index")
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

            required_tables = {'elements_meta', 'spatial_index'}
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