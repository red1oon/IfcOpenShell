# Bonsai - OpenBIM Blender Add-on
# Copyright (C) 2025 Your Engineering Firm
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
Qualified Path: src/bonsai/bonsai/bim/module/federation/__init__.py

Federation Module - Multi-Model Coordination
--------------------------------------------
Enables spatial queries across multiple discipline IFC files without merging,
solving spatial hierarchy mismatch problems through coordinate-based queries.
"""

import bpy
from bpy.app.handlers import persistent
from pathlib import Path
from . import ui, prop, operator
from .unified_progressive_loader import GlassOutlineLoader

# Expose classes so main __init__.py can find them
classes = (
    prop.FederatedFile,
    prop.BIMFederationProperties,
    operator.AddFederatedFile,
    operator.RemoveFederatedFile,
    operator.SelectFederatedFile,
    operator.SelectFederatedFolder,
    operator.PreprocessFederatedModels,
    operator.LoadFederationIndex,
    operator.UnloadFederationIndex,
    operator.QueryFederationIndex,
    operator.LoadFederationModel,
    operator.LoadFederationStage2Background,
    operator.DetectFederationClashes,
    operator.PreviewFederationViewport,
    operator.LoadSolidFederationViewport,
    operator.LoadFullFederationViewport,
    operator.ReloadFederationViewport,
    operator.UnloadFederationViewport,
    operator.ExtractSampleDatabase,
    operator.ExtractFullDatabase,
    operator.RedoSampleExtraction,
    GlassOutlineLoader,
    ui.BIM_PT_federation,
    ui.BIM_UL_federated_files,
)

@persistent
def restore_federation_index_on_load(dummy):
    """
    Restore federation index when .blend file is loaded.

    The federation database path is stored in the .blend file,
    but the FederationIndex Python object is not. This handler
    recreates the index when the file is opened.
    """
    if not hasattr(bpy.context, 'scene'):
        return

    props = bpy.context.scene.BIMFederationProperties

    # Check if database path is set and file exists
    if props.federation_database_path and Path(props.federation_database_path).exists():
        try:
            from .spatial_index import FederationIndex

            # Only register if not already loaded
            if not hasattr(bpy.types.WindowManager, 'federation_index'):
                print(f"Restoring federation index: {props.federation_database_path}")

                index = FederationIndex(props.federation_database_path)
                index.build()

                bpy.types.WindowManager.federation_index = index

                stats = index.get_statistics()
                props.index_loaded = True
                props.total_elements = stats['total_elements']
                props.loaded_disciplines = ', '.join(stats['disciplines'])

                print(f"✓ Federation index restored: {stats['total_elements']:,} elements")
        except Exception as e:
            print(f"⚠ Could not restore federation index: {e}")


def register():
    """Called when addon is enabled"""
    # Attach properties to Blender's Scene
    bpy.types.Scene.BIMFederationProperties = bpy.props.PointerProperty(
        type=prop.BIMFederationProperties
    )

    # Register load handler to restore federation index
    if restore_federation_index_on_load not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(restore_federation_index_on_load)

def unregister():
    """Called when addon is disabled - cleanup"""
    # Remove load handler
    if restore_federation_index_on_load in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.remove(restore_federation_index_on_load)

    # Remove properties from Scene
    del bpy.types.Scene.BIMFederationProperties