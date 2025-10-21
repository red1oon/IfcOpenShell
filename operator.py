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
    """Select an IFC file to add to federation"""
    bl_idname = "bim.select_federated_file"
    bl_label = "Select IFC File"
    bl_description = "Select an IFC file to add to the federation"
    bl_options = {"REGISTER", "UNDO"}
    
    filename_ext = ".ifc"
    filter_glob: StringProperty(default="*.ifc;*.ifczip", options={"HIDDEN"})
    index: IntProperty(options={"HIDDEN"})
    
    def execute(self, context):
        props = context.scene.BIMFederationProperties
        federated_file = props.federated_files[self.index]
        federated_file.name = self.filepath
        
        # Auto-detect discipline from filename
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
        
        # Set progress path
        db_path = Path(props.federation_database_path)
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
            # Run in background (non-blocking)
            subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
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
        
        props = context.scene.BIMFederationProperties
        db_path = Path(props.federation_database_path)
        
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
    """Test query the federation index"""
    bl_idname = "bim.query_federation_index"
    bl_label = "Test Query"
    bl_description = "Run a test spatial query on the federation index"
    bl_options = {"REGISTER"}
    
    @classmethod
    def poll(cls, context):
        props = context.scene.BIMFederationProperties
        if not props.index_loaded:
            cls.poll_message_set("Load federation index first")
            return False
        return True
    
    def execute(self, context):
        props = context.scene.BIMFederationProperties
        
        try:
            # Get index from window manager
            if not hasattr(bpy.types.WindowManager, 'federation_index'):
                self.report({'ERROR'}, "Index not found in memory")
                return {"CANCELLED"}
            
            index = bpy.types.WindowManager.federation_index
            
            # Test query: 10m cube at origin
            buffer = 5000  # 5 meters in mm
            results = index.query_by_bbox(
                (-buffer, -buffer, -buffer),
                (buffer, buffer, buffer)
            )
            
            # Report results
            self.report({'INFO'}, f"Test query found {len(results)} elements in 10m cube at origin")
            
            # Print details to console
            print("\nFederation Query Results:")
            print(f"  Total elements: {len(results)}")
            
            # Group by discipline
            by_discipline = {}
            for element in results:
                by_discipline.setdefault(element.discipline, []).append(element)
            
            for discipline, elements in by_discipline.items():
                print(f"  {discipline}: {len(elements)} elements")
            
            # Show first few elements
            print("\nFirst 5 elements:")
            for element in results[:5]:
                print(f"    {element}")
            
        except Exception as e:
            self.report({'ERROR'}, f"Query failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return {"CANCELLED"}
        
        return {"FINISHED"}