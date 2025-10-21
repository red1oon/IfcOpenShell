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
from . import ui, prop, operator

# Expose classes so main __init__.py can find them
classes = (
    prop.FederatedFile,
    prop.BIMFederationProperties,
    operator.AddFederatedFile,
    operator.RemoveFederatedFile,
    operator.SelectFederatedFile,
    operator.PreprocessFederatedModels,
    operator.LoadFederationIndex,
    operator.UnloadFederationIndex,
    operator.QueryFederationIndex,
    ui.BIM_PT_federation,
    ui.BIM_UL_federated_files,
)

def register():
    """Called when addon is enabled"""
    # Attach properties to Blender's Scene
    bpy.types.Scene.BIMFederationProperties = bpy.props.PointerProperty(
        type=prop.BIMFederationProperties
    )

def unregister():
    """Called when addon is disabled - cleanup"""
    # Remove properties from Scene
    del bpy.types.Scene.BIMFederationProperties