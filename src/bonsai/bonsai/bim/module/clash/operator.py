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

from . import prefilter
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
from bpy_extras.io_utils import ExportHelper, ImportHelper
from math import radians
from mathutils import Matrix, Vector
from bonsai.bim.ifc import IfcStore
from bonsai.bim.module.clash.decorator import ClashDecorator
from typing import TYPE_CHECKING


class ExportClashSets(bpy.types.Operator, ExportHelper):
    bl_idname = "bim.export_clash_sets"
    bl_label = "Export Clash Sets"
    bl_description = "Export clash sets to a selected file"
    filename_ext = ".json"
    filter_glob: bpy.props.StringProperty(default="*.json", options={"HIDDEN"})

    def execute(self, context):
        self.filepath = bpy.path.ensure_ext(self.filepath, ".json")
        clash_sets = tool.Clash.export_clash_sets()
        with open(self.filepath, "w") as destination:
            destination.write(json.dumps(clash_sets, indent=4))
        return {"FINISHED"}


class ImportClashSets(bpy.types.Operator, ImportHelper):
    bl_idname = "bim.import_clash_sets"
    bl_label = "Import Clash Sets"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Import clash sets from a selected file"
    filename_ext = ".json"
    filter_glob: bpy.props.StringProperty(default="*.json", options={"HIDDEN"})

    def invoke(self, context, event):
        self.filepath = bpy.path.ensure_ext(bpy.data.filepath, ".json")
        return ImportHelper.invoke(self, context, event)

    def execute(self, context):
        tool.Clash.load_clash_sets(self.filepath)
        props = tool.Clash.get_clash_props()
        props.clash_sets.clear()
        for clash_set in tool.Clash.get_clash_sets():
            new = props.clash_sets.add()
            new.name = clash_set["name"]
            new.mode = clash_set["mode"]
            if new.mode == "intersection":
                new.tolerance = clash_set["tolerance"]
                new.check_all = clash_set["check_all"]
            elif new.mode == "collision":
                new.allow_touching = clash_set["allow_touching"]
            elif new.mode == "clearance":
                new.clearance = clash_set["clearance"]
                new.check_all = clash_set["check_all"]
            for clash_source in clash_set["a"]:
                new_source = new.a.add()
                new_source.name = clash_source["file"]
                if "selector" in clash_source:
                    tool.Search.import_filter_query(clash_source["selector"], new_source.filter_groups)
                    new_source.mode = clash_source["mode"]
            if "b" in clash_set and clash_set["b"]:
                for clash_source in clash_set["b"]:
                    new_source = new.b.add()
                    new_source.name = clash_source["file"]
                    if "selector" in clash_source:
                        tool.Search.import_filter_query(clash_source["selector"], new_source.filter_groups)
                        new_source.mode = clash_source["mode"]
        tool.Clash.import_active_clashes()
        return {"FINISHED"}


class AddClashSet(bpy.types.Operator):
    bl_idname = "bim.add_clash_set"
    bl_label = "Add Clash Set"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Add a clash set"

    def execute(self, context):
        props = tool.Clash.get_clash_props()
        new = props.clash_sets.add()
        new.name = "New Clash Set"
        return {"FINISHED"}


class RemoveClashSet(bpy.types.Operator):
    bl_idname = "bim.remove_clash_set"
    bl_label = "Remove Clash Set"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Remove the selected clash set"
    index: bpy.props.IntProperty()

    def execute(self, context):
        props = tool.Clash.get_clash_props()
        props.clash_sets.remove(self.index)
        return {"FINISHED"}


class AddClashSource(bpy.types.Operator):
    bl_idname = "bim.add_clash_source"
    bl_label = "Add Clash Source"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Add a clash source to this group"
    group: bpy.props.StringProperty()

    def execute(self, context):
        props = tool.Clash.get_clash_props()
        clash_set = props.active_clash_set
        assert clash_set
        clash_set.get_clash_sources_group(self.group).add()
        return {"FINISHED"}


class RemoveClashSource(bpy.types.Operator):
    bl_idname = "bim.remove_clash_source"
    bl_label = "Remove Clash Source"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Remove this clash source"
    index: bpy.props.IntProperty()
    group: bpy.props.StringProperty()

    def execute(self, context):
        props = tool.Clash.get_clash_props()
        clash_set = props.active_clash_set
        assert clash_set
        clash_set.get_clash_sources_group(self.group).remove(self.index)
        return {"FINISHED"}


class SelectClashSource(bpy.types.Operator, ImportHelper):
    bl_idname = "bim.select_clash_source"
    bl_label = "Select Clash Source"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Select an IFC file to add as a clash source"
    filter_glob: bpy.props.StringProperty(default="*.ifc", options={"HIDDEN"})
    index: bpy.props.IntProperty(options={"HIDDEN"})
    group: bpy.props.StringProperty(options={"HIDDEN"})
    filename_ext = ".ifc"

    def execute(self, context):
        props = tool.Clash.get_clash_props()
        clash_set = props.active_clash_set
        assert clash_set
        clash_source = clash_set.get_clash_sources_group(self.group)[self.index]
        clash_source.name = self.filepath
        return {"FINISHED"}


class SelectClashResults(bpy.types.Operator, ImportHelper):
    bl_idname = "bim.select_clash_results"
    bl_label = "Select Clash Results"
    bl_description = "Select filepath for clash results."
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = tool.Clash.get_clash_props()
        props.clash_results_path = self.filepath
        return {"FINISHED"}


class SelectSmartGroupedClashesPath(bpy.types.Operator, ImportHelper):
    bl_idname = "bim.select_smart_grouped_clashes_path"
    bl_label = "Select Smart-Grouped Clashes Path"
    bl_description = "Select filepath for smart-grouped clashes."
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = tool.Clash.get_clash_props()
        props.smart_grouped_clashes_path = self.filepath
        return {"FINISHED"}


class ExecuteIfcClash(bpy.types.Operator, ExportHelper):
    bl_idname = "bim.execute_ifc_clash"
    bl_label = "Execute IFC Clash"
    bl_description = (
        "Execute clash detection and save the information to a .bcf or .json file.\n\n"
        "ALT+click to run a quick clash without selecting a file to save."
    )

    filter_glob: bpy.props.StringProperty(  # pyright: ignore[reportRedeclaration]
        default="*.bcf;*.json", options={"HIDDEN"}
    )
    format: bpy.props.EnumProperty(  # pyright: ignore[reportRedeclaration]
        name="Format", items=[(i, i, "") for i in ("bcf", "json")]
    )
    filepath: bpy.props.StringProperty(  # pyright: ignore[reportRedeclaration]
        subtype="FILE_PATH", options={"SKIP_SAVE"}
    )
    quick_clash: bpy.props.BoolProperty(  # pyright: ignore[reportRedeclaration]
        options={"SKIP_SAVE"},
    )

    if TYPE_CHECKING:
        filter_glob: str
        format: str
        filepath: str
        quick_clash: bool

    @property
    def filename_ext(self) -> str:
        return f".{self.format.lower()}"

    def invoke(self, context, event):
        if event.alt:
            self.quick_clash = True
            return self.execute(context)

        if self.filepath:
            return self.execute(context)
        return ExportHelper.invoke(self, context, event)

    def execute(self, context):
        from ifcclash import ifcclash

        self.props = tool.Clash.get_clash_props()

        for clash_set in self.props.clash_sets:
            for clash_sources in clash_set.get_clash_sources().values():
                for clash_source in clash_sources:
                    if not Path(clash_source.name).is_file():
                        self.report(
                            {"ERROR"},
                            f"One of the provided clash source filepaths do not exist: '{clash_source.name}'.",
                        )
                        return {"CANCELLED"}

        temp_file = None
        if self.quick_clash:
            temp_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w")
            temp_file.close()
            extension = ".json"
            self.filepath = temp_file.name
        else:
            extension = Path(self.filepath).suffix.lower()
            if extension != ".bcf":
                self.filepath = bpy.path.ensure_ext(self.filepath, ".json")
            # TODO Temporarily until BCF support comes back
            if extension != ".json":
                self.filepath = bpy.path.ensure_ext(self.filepath, ".bcf")
            assert extension in (".bcf", ".json")
            self.props.export_path = self.filepath

        settings = ifcclash.ClashSettings()
        settings.output = self.filepath
        settings.logger = logging.getLogger("Clash")
        settings.logger.setLevel(logging.DEBUG)
        clasher = ifcclash.Clasher(settings)

        if self.props.should_create_clash_snapshots:

            def get_viewpoint_snapshot(viewpoint) -> tuple[str, bytes]:
                assert context.scene

                camera = bpy.data.objects.get("IFC Clash Camera")
                if not camera:
                    camera = bpy.data.objects.new("IFC Clash Camera", bpy.data.cameras.new("IFC Clash Camera"))
                    context.scene.collection.objects.link(camera)
                assert isinstance(camera.data, bpy.types.Camera)

                bcf_camera = viewpoint.visualization_info.perspective_camera
                p = bcf_camera.camera_view_point
                z = bcf_camera.camera_direction
                z = Vector([z.x, z.y, z.z]) * -1
                y = bcf_camera.camera_up_vector
                y = Vector([y.x, y.y, y.z])
                x = y.cross(z)
                assert isinstance(x, Vector)

                mat = Matrix(
                    [
                        [x[0], y[0], z[0], p.x],
                        [x[1], y[1], z[1], p.y],
                        [x[2], y[2], z[2], p.z],
                        [0, 0, 0, 0],
                    ]
                )

                camera.matrix_world = mat
                context.scene.camera = camera
                camera.data.angle = radians(60)
                assert (space := tool.Blender.get_view3d_space()) and space.region_3d
                space.region_3d.view_perspective = "CAMERA"
                space.shading.show_xray = True
                context.scene.render.resolution_x = 480
                context.scene.render.resolution_y = 270
                context.scene.render.image_settings.file_format = "PNG"
                context.scene.render.filepath = tool.Blender.get_data_dir_path("shapshot.png").__str__()
                bpy.ops.render.opengl(write_still=True)
                with open(context.scene.render.filepath, "rb") as f:
                    return ("snapshot.png", f.read())

            clasher.get_viewpoint_snapshot = get_viewpoint_snapshot

        # Bbox prefilter hook (if enabled)
        if self.props.enable_bbox_prefilter and self.props.bbox_database_path:
            try:
                from bonsai.bim.module.federation.core.spatial_index import FederationIndex

                db_path = Path(self.props.bbox_database_path)

                if prefilter.validate_spatial_index(db_path):
                    spatial_index = FederationIndex(str(db_path))
                    spatial_index.build()

                    # Apply prefilter to clash sets
                    for clash_set in self.props.clash_sets:
                        set_a = [src.name for src in clash_set.a]
                        set_b = [src.name for src in clash_set.b]

                        # Use clash set's tolerance/clearance for prefilter
                        tolerance = 0.0
                        if clash_set.mode == "clearance":
                            tolerance = clash_set.clearance
                        elif clash_set.mode == "intersection":
                            tolerance = clash_set.tolerance

                        candidates = prefilter.get_candidate_pairs(
                            set_a, set_b, spatial_index, tolerance=tolerance
                        )

                        self.report({'INFO'},
                            f"Bbox prefilter: {len(candidates)} candidate pairs "
                            f"(see ~/Documents/bonsai.log for details)")
                else:
                    self.report({'WARNING'}, "Invalid spatial index database, skipping prefilter")
            except Exception as e:
                self.report({'WARNING'}, f"Prefilter failed: {str(e)}, continuing without prefilter")

        clasher.clash_sets = tool.Clash.export_clash_sets()
        clasher.clash()
        clasher.export()

        # Load clash results to UI.
        if extension == ".bcf":
            with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tmp:
                try:
                    tmp.close()
                    settings.output = tmp.name
                    clasher.export()
                    tool.Clash.load_clash_sets(tmp.name)
                finally:
                    Path(tmp.name).unlink()
        else:
            tool.Clash.load_clash_sets(self.filepath)
        tool.Clash.import_active_clashes()

        if self.quick_clash:
            assert temp_file is not None
            Path(temp_file.name).unlink()
            self.report({"INFO"}, "IFC Clash completed and results are loaded.")
        else:
            self.report({"INFO"}, f"IFC Clash results are saved to '{Path(self.filepath).name}'.")
        return {"FINISHED"}


class SelectIfcClashResults(bpy.types.Operator, ImportHelper):
    bl_idname = "bim.select_ifc_clash_results"
    bl_label = "Select IFC Clash Results"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Select the clashing IFC geometry stored in a file"
    filter_glob: bpy.props.StringProperty(default="*.json", options={"HIDDEN"})
    filename_ext = ".json"

    def invoke(self, context, event):
        self.filepath = bpy.path.ensure_ext(bpy.data.filepath, ".json")
        return ImportHelper.invoke(self, context, event)

    def execute(self, context):
        # TODO refactor into new clash results system
        self.file = tool.Ifc.get()
        self.filepath = bpy.path.ensure_ext(self.filepath, ".json")
        with open(self.filepath) as f:
            clash_sets = json.load(f)
        clash_props = tool.Clash.get_clash_props()
        assert clash_props.active_clash_set
        clash_set_name = clash_props.active_clash_set.name
        global_ids = []
        for clash_set in clash_sets:
            if clash_set["name"] != clash_set_name:
                continue
            if not "clashes" in clash_set.keys():
                self.report({"WARNING"}, "No clashes found for the selected Clash Set.")
                return {"CANCELLED"}
            for clash in clash_set["clashes"].values():
                global_ids.extend([clash["a_global_id"], clash["b_global_id"]])

        for obj in context.visible_objects:
            props = tool.Blender.get_object_bim_props(obj)
            if not props.ifc_definition_id:
                continue

            ifc_file = ""
            for scene in obj.users_scene:
                bim_props = tool.Blender.get_bim_props(scene)
                if bim_props.ifc_file:
                    ifc_file = bim_props.ifc_file
                    if scene.library:
                        break

            if ifc_file:
                if ifc_file not in IfcStore.session_files:
                    IfcStore.session_files[ifc_file] = ifcopenshell.open(ifc_file)
                element_file = IfcStore.session_files[ifc_file]
            else:
                element_file = self.file

            try:
                element = element_file.by_id(props.ifc_definition_id)
            except:
                continue

            global_id = getattr(element, "GlobalId", None)
            if not global_id:
                continue
            if global_id in global_ids:
                obj.select_set(True)
        return {"FINISHED"}


class SelectClash(bpy.types.Operator):
    bl_idname = "bim.select_clash"
    bl_label = "Select Clash"
    bl_options = {"REGISTER", "UNDO"}
    bl_description = "Select the clashing IFC geometry stored in a file"
    index: bpy.props.IntProperty()

    def execute(self, context):
        self.props = tool.Clash.get_clash_props()
        assert (active_clash := self.props.active_clash)
        assert (active_clash_set := self.props.active_clash_set)
        clash_set = tool.Clash.get_clash_set(active_clash_set.name)
        assert clash_set
        clash = tool.Clash.get_clash(clash_set, active_clash.a_global_id, active_clash.b_global_id)

        if not clash:
            return {"FINISHED"}

        products: list[ifcopenshell.entity_instance] = []

        for global_id in (clash["a_global_id"], clash["b_global_id"]):
            try:
                products.append(tool.Ifc.get().by_guid(global_id))
            except:
                pass

        tool.Spatial.select_products(products, unhide=True)
        ClashDecorator.install(bpy.context)
        target = Vector(clash["p1"])
        tool.Clash.look_at(target, target + Vector((5, 5, 5)))
        self.props.p1 = clash["p1"]
        self.props.p2 = clash["p2"]
        self.props.active_clash_text = clash["type"].title() + " " + str(round(clash["distance"] * 1000)) + "mm"
        return {"FINISHED"}


class SmartClashGroup(bpy.types.Operator):
    bl_idname = "bim.smart_clash_group"
    bl_label = "Smart Group Clashes"
    bl_options = {"REGISTER", "UNDO"}
    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    @classmethod
    def poll(cls, context):
        props = tool.Clash.get_clash_props()
        return bool(props.clash_results_path)

    def execute(self, context):
        from ifcclash import ifcclash

        settings = ifcclash.ClashSettings()
        props = tool.Clash.get_clash_props()
        self.filepath = bpy.path.ensure_ext(props.clash_results_path, ".json")
        settings.output = self.filepath
        settings.logger = logging.getLogger("Clash")
        settings.logger.setLevel(logging.DEBUG)
        ifc_clasher = ifcclash.Clasher(settings)

        with open(self.filepath) as f:
            clash_sets = json.load(f)

        # execute the smart grouping
        save_path = bpy.path.ensure_ext(props.smart_grouped_clashes_path, ".json")
        smart_grouped_clashes = ifc_clasher.smart_group_clashes(clash_sets, props.smart_clash_grouping_max_distance)

        # save smart_groups to json
        with open(save_path, "w") as f:
            f.write(json.dumps(smart_grouped_clashes))

        assert props.active_clash_set
        clash_set_name = props.active_clash_set.name

        # Reset the list of smart_clash_groups for the UI
        props.smart_clash_groups.clear()

        for clash_set, smart_groups in smart_grouped_clashes.items():
            # Only select the clashes that correspond to the actively selected IFC Clash Set
            if clash_set != clash_set_name:
                continue
            else:
                for smart_group, global_id_pairs in smart_groups[0].items():
                    new_group = props.smart_clash_groups.add()
                    new_group.number = f"{smart_group}"

                    for pair in global_id_pairs:
                        for id in pair:
                            new_global_id = new_group.global_ids.add()
                            new_global_id.name = id

        return {"FINISHED"}


class LoadSmartGroupsForActiveClashSet(bpy.types.Operator):
    bl_idname = "bim.load_smart_groups_for_active_clash_set"
    bl_label = "Load Smart Groups for Active Clash Set"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        props = tool.Clash.get_clash_props()
        return bool(props.active_clash_set)

    def execute(self, context):
        props = tool.Clash.get_clash_props()
        smart_groups_path = bpy.path.ensure_ext(props.smart_grouped_clashes_path, ".json")

        assert props.active_clash_set
        clash_set_name = props.active_clash_set.name

        with open(smart_groups_path) as f:
            smart_grouped_clashes = json.load(f)

        # Reset the list of smart_clash_groups for the UI
        props.smart_clash_groups.clear()

        for clash_set, smart_groups in smart_grouped_clashes.items():
            # Only select the clashes that correspond to the actively selected IFC Clash Set
            if clash_set != clash_set_name:
                continue
            else:
                for smart_group, global_id_pairs in smart_groups[0].items():
                    new_group = props.smart_clash_groups.add()
                    new_group.number = f"{smart_group}"
                    for pair in global_id_pairs:
                        for guid in pair:
                            new_global_id = new_group.global_ids.add()
                            new_global_id.name = guid

        return {"FINISHED"}


class SelectSmartGroup(bpy.types.Operator):
    bl_idname = "bim.select_smart_group"
    bl_label = "Select Smart Group"
    bl_options = {"REGISTER", "UNDO"}

    @classmethod
    def poll(cls, context):
        props = tool.Clash.get_clash_props()
        return tool.Ifc.get() and context.visible_objects and props.active_smart_group

    def execute(self, context):
        ifc_file = tool.Ifc.get()
        props = tool.Clash.get_clash_props()
        selected_smart_group = props.active_smart_group
        assert selected_smart_group
        products: list[ifcopenshell.entity_instance] = []
        for global_id in selected_smart_group.global_ids:
            try:
                products.append(ifc_file.by_guid(global_id.name))
            except RuntimeError:
                continue
        tool.Spatial.select_products(products, unhide=True)
        context_override = tool.Blender.get_viewport_context()
        with bpy.context.temp_override(**context_override):
            bpy.ops.view3d.view_selected()
        return {"FINISHED"}


class _DEPRECATED_BIM_OT_clash_by_discipline(bpy.types.Operator):
    """DEPRECATED: Moved to federation_analysis module"""
    bl_idname = "bim._deprecated_clash_by_discipline"
    bl_label = "Clash by Discipline"
    bl_description = "Quick clash detection by discipline using spatial index"
    bl_options = {"REGISTER"}

    def execute(self, context):
        import time
        from pathlib import Path

        props = tool.Clash.get_clash_props()
        fed_props = context.scene.BIMFederationProperties

        # Setup logging to ~/Documents/bonsai/bonsai.log
        log_dir = Path.home() / "Documents" / "bonsai"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "bonsai.log"

        logger = logging.getLogger('DisciplineClash')
        logger.setLevel(logging.INFO)
        logger.handlers.clear()

        file_handler = logging.FileHandler(str(log_path), mode='a')
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        logger.info("=" * 70)
        logger.info("DISCIPLINE-BASED CLASH DETECTION")
        logger.info("=" * 70)

        # Load federation database from Federation panel
        if not fed_props.federation_database_path:
            error_msg = "Please load Federation Database in Multi-Model Federation panel"
            logger.error(error_msg)
            self.report({'ERROR'}, error_msg)
            return {"CANCELLED"}

        # Resolve Blender relative paths (// prefix)
        db_path = Path(bpy.path.abspath(fed_props.federation_database_path))
        if not db_path.exists():
            error_msg = f"Federation database not found: {db_path}"
            logger.error(error_msg)
            self.report({'ERROR'}, error_msg)
            return {"CANCELLED"}

        logger.info(f"Database: {db_path}")

        # Apply preset if selected
        disc_a = props.discipline_a
        disc_b = props.discipline_b

        # Handle multi-discipline expansion for ALL_MEP preset
        disciplines_a = []
        disciplines_b = []

        if props.clash_preset == 'ALL_MEP':
            # Expand ALL_MEP to all MEP disciplines
            disciplines_a = ['ELEC', 'ACMV', 'FP', 'SP']
            disciplines_b = ['ARC', 'STR']
            logger.info(f"Applied preset: ALL_MEP - Expanding to all combinations")
            logger.info(f"  MEP disciplines: {', '.join(disciplines_a)}")
            logger.info(f"  vs: {', '.join(disciplines_b)}")
        elif props.clash_preset != 'CUSTOM':
            preset_map = {
                'ARC_STR': ('ARC', 'STR'),
                'ACMV_ARC': ('ACMV', 'ARC'),
                'ELEC_ARC': ('ELEC', 'ARC'),
                'FP_ARC': ('FP', 'ARC'),
                'SP_ARC': ('SP', 'ARC'),
            }
            if props.clash_preset in preset_map:
                disc_a, disc_b = preset_map[props.clash_preset]
                disciplines_a = [disc_a]
                disciplines_b = [disc_b]
                logger.info(f"Applied preset: {props.clash_preset}")
        else:
            # Custom selection
            disciplines_a = [disc_a] if disc_a else []
            disciplines_b = [disc_b] if disc_b else []

        if not disciplines_a or not disciplines_b:
            error_msg = "Please select disciplines for clash detection"
            logger.error(error_msg)
            self.report({'ERROR'}, error_msg)
            return {"CANCELLED"}

        logger.info(f"Discipline A: {', '.join(disciplines_a)}")
        logger.info(f"Discipline B: {', '.join(disciplines_b)}")
        logger.info(f"Tolerance: {props.discipline_tolerance}")

        print("\n" + "=" * 70)
        print(f"CLASH DETECTION: {', '.join(disciplines_a)} vs {', '.join(disciplines_b)}")
        print("=" * 70)

        try:
            from bonsai.bim.module.federation.core.spatial_index import FederationIndex

            # Load spatial index
            start_time = time.time()
            index = FederationIndex(db_path)
            index.build()
            load_time = time.time() - start_time

            logger.info(f"Loaded spatial index in {load_time:.2f} seconds")
            logger.info(f"Total elements: {index.stats['total_elements']:,}")
            logger.info(f"Available disciplines: {', '.join(sorted(index.stats['disciplines']))}")

            print(f"\n✓ Loaded spatial index ({load_time:.2f}s)")
            print(f"  Total elements: {index.stats['total_elements']:,}")

            # Query and combine elements from all specified disciplines
            print(f"\nQuerying disciplines...")
            elements_a = []
            for disc in disciplines_a:
                disc_elements = index.query_by_discipline(disc)
                elements_a.extend(disc_elements)
                logger.info(f"  {disc}: {len(disc_elements):,} elements")
                print(f"  {disc}: {len(disc_elements):,} elements")

            elements_b = []
            for disc in disciplines_b:
                disc_elements = index.query_by_discipline(disc)
                elements_b.extend(disc_elements)
                logger.info(f"  {disc}: {len(disc_elements):,} elements")
                print(f"  {disc}: {len(disc_elements):,} elements")

            logger.info(f"Total Group A elements: {len(elements_a):,}")
            logger.info(f"Total Group B elements: {len(elements_b):,}")
            print(f"\nTotal Group A: {len(elements_a):,} elements")
            print(f"Total Group B: {len(elements_b):,} elements")

            if not elements_a:
                error_msg = f"No elements found for disciplines: {', '.join(disciplines_a)}"
                logger.error(error_msg)
                self.report({'ERROR'}, error_msg)
                return {"CANCELLED"}

            if not elements_b:
                error_msg = f"No elements found for disciplines: {', '.join(disciplines_b)}"
                logger.error(error_msg)
                self.report({'ERROR'}, error_msg)
                return {"CANCELLED"}

            # Define noise filters - IFC types to ignore
            NOISE_TYPES = {
                'IfcSpace',           # Abstract spatial volumes
                'IfcOpeningElement',  # Designed openings (doors, windows)
                'IfcAnnotation',      # 2D annotations, text, dimensions
                'IfcGrid',            # Grid lines
                'IfcAxis2Placement3D', # Coordinate systems
            }

            # Find bbox intersections with noise filtering using R-tree spatial queries
            print(f"\nAnalyzing bbox intersections (with R-tree optimization + noise filtering)...")
            start_time = time.time()
            candidates = []
            filtered_count = 0
            rtree_queries = 0

            # Use spatial index for efficient queries
            for elem_a in elements_a:
                # Filter: Skip noise types
                if elem_a.ifc_class in NOISE_TYPES:
                    filtered_count += len(elements_b)
                    continue

                # Expand bbox by tolerance for query
                tol = props.discipline_tolerance
                min_x, min_y, min_z, max_x, max_y, max_z = elem_a.bbox
                query_bbox = (
                    (min_x - tol, min_y - tol, min_z - tol),
                    (max_x + tol, max_y + tol, max_z + tol)
                )

                # Query spatial index for nearby elements in group B
                nearby_elements = index.query_by_bbox(
                    min_xyz=query_bbox[0],
                    max_xyz=query_bbox[1],
                    disciplines=disciplines_b
                )
                rtree_queries += 1

                # Check each nearby element for actual clash
                for elem_b in nearby_elements:
                    # Filter: Skip noise types
                    if elem_b.ifc_class in NOISE_TYPES:
                        filtered_count += 1
                        continue

                    # Precise bbox intersection check
                    if prefilter.bboxes_intersect(elem_a.bbox, elem_b.bbox, tolerance=tol):
                        candidates.append({
                            'guid_a': elem_a.guid,
                            'guid_b': elem_b.guid,
                            'name_a': elem_a.ifc_class,
                            'name_b': elem_b.ifc_class,
                            'ifc_class_a': elem_a.ifc_class,
                            'ifc_class_b': elem_b.ifc_class,
                        })

            analysis_time = time.time() - start_time

            # Calculate statistics
            total_combinations = len(elements_a) * len(elements_b)
            filtered_combinations = total_combinations - filtered_count
            reduction = 100 * (1 - len(candidates) / filtered_combinations) if filtered_combinations > 0 else 0

            logger.info(f"Filtered out {filtered_count:,} noise combinations (Spaces, Openings, Annotations)")
            logger.info(f"R-tree optimization: {rtree_queries:,} spatial queries (vs {total_combinations:,} brute force)")

            # Report results
            logger.info("=" * 70)
            logger.info("RESULTS:")
            logger.info(f"Total combinations:     {total_combinations:,}")
            logger.info(f"R-tree queries:         {rtree_queries:,}")
            logger.info(f"Filtered noise:         {filtered_count:,}")
            logger.info(f"After filtering:        {filtered_combinations:,}")
            logger.info(f"Clash candidates:       {len(candidates):,}")
            logger.info(f"Reduction:              {reduction:.1f}%")
            logger.info(f"Analysis time:          {analysis_time:.2f} seconds")
            logger.info(f"Speed: {total_combinations / rtree_queries:.0f}x faster than brute force")
            logger.info("=" * 70)

            print(f"\n{'=' * 70}")
            print("RESULTS:")
            print(f"  Total combinations:     {total_combinations:,}")
            print(f"  R-tree queries:         {rtree_queries:,}")
            print(f"  Filtered noise:         {filtered_count:,}")
            print(f"  After filtering:        {filtered_combinations:,}")
            print(f"  Clash candidates:       {len(candidates):,}")
            print(f"  Reduction:              {reduction:.1f}%")
            print(f"  Analysis time:          {analysis_time:.2f} seconds")
            print(f"  Speed: {total_combinations / rtree_queries:.0f}x faster than brute force")
            print(f"{'=' * 70}\n")

            # Store candidates in scene properties
            props.discipline_clash_candidates.clear()
            for candidate in candidates:
                new = props.discipline_clash_candidates.add()
                new.guid_a = candidate['guid_a']
                new.guid_b = candidate['guid_b']
                new.name_a = candidate['name_a']
                new.name_b = candidate['name_b']
                new.ifc_class_a = candidate['ifc_class_a']
                new.ifc_class_b = candidate['ifc_class_b']
                # bbox_center queried from federation DB when needed (lazy loading)

            props.discipline_clash_loaded = len(candidates) > 0
            props.active_discipline_clash_index = 0

            # Sync bbox_database_path for visualization operators
            props.bbox_database_path = str(db_path)

            self.report({'INFO'},
                f"Found {len(candidates):,} clash candidates "
                f"({reduction:.1f}% reduction, {analysis_time:.1f}s)")

            return {"FINISHED"}

        except Exception as e:
            error_msg = f"Clash detection failed: {str(e)}"
            logger.error(error_msg)
            logger.error("Exception traceback:", exc_info=True)
            self.report({'ERROR'}, error_msg)
            import traceback
            traceback.print_exc()
            return {"CANCELLED"}


class BIM_OT_select_discipline_clash(bpy.types.Operator):
    """Select and zoom to discipline clash elements"""
    bl_idname = "bim.select_discipline_clash"
    bl_label = "Select Discipline Clash"
    bl_description = "Select and zoom to the clash elements in viewport"
    bl_options = {"REGISTER", "UNDO"}

    def find_element_by_spatial_proximity(self, ifc_file, ifc_class, bbox_center, tolerance=1.0):
        """
        Find IFC element by spatial proximity to bbox center.

        Args:
            ifc_file: IFC file to search
            ifc_class: IFC class name (e.g., "IfcWall")
            bbox_center: Tuple (x, y, z) of bbox center coordinates
            tolerance: Search radius in meters (default 1.0m)

        Returns:
            IFC element if found, None otherwise
        """
        import ifcopenshell.geom

        # Get all elements of this IFC class
        elements = ifc_file.by_type(ifc_class)
        if not elements:
            return None

        settings = ifcopenshell.geom.settings()
        settings.set(settings.DISABLE_OPENING_SUBTRACTIONS, True)  # Faster

        target_x, target_y, target_z = bbox_center
        closest_elem = None
        closest_dist = float('inf')

        # Find element with bbox center closest to target
        for elem in elements:
            try:
                # Get element's bounding box
                shape = ifcopenshell.geom.create_shape(settings, elem)
                verts = shape.geometry.verts

                # Calculate bbox from vertices
                xs = [verts[i] for i in range(0, len(verts), 3)]
                ys = [verts[i+1] for i in range(0, len(verts), 3)]
                zs = [verts[i+2] for i in range(0, len(verts), 3)]

                if not xs:
                    continue

                # Calculate bbox center
                elem_center_x = (min(xs) + max(xs)) / 2
                elem_center_y = (min(ys) + max(ys)) / 2
                elem_center_z = (min(zs) + max(zs)) / 2

                # Calculate distance to target
                dist = ((elem_center_x - target_x)**2 +
                       (elem_center_y - target_y)**2 +
                       (elem_center_z - target_z)**2) ** 0.5

                if dist < closest_dist and dist <= tolerance:
                    closest_dist = dist
                    closest_elem = elem

            except Exception as e:
                # Skip elements that fail geometry creation
                continue

        return closest_elem

    def execute(self, context):
        props = tool.Clash.get_clash_props()

        if not props.discipline_clash_loaded:
            self.report({'WARNING'}, "No discipline clash results loaded")
            return {"CANCELLED"}

        if not (0 <= props.active_discipline_clash_index < len(props.discipline_clash_candidates)):
            self.report({'WARNING'}, "Invalid clash selection")
            return {"CANCELLED"}

        candidate = props.discipline_clash_candidates[props.active_discipline_clash_index]

        # NEW: Use federation database for visualization (NO IFC NEEDED!)
        db_path = props.bbox_database_path
        if not db_path:
            self.report({'ERROR'}, "No federation database loaded")
            return {"CANCELLED"}

        from ..federation_analysis.visualization import federation_viz_helper

        # Find or create elements from database
        print(f"Finding clash elements from database (no IFC needed)...")
        obj_a, obj_b = federation_viz_helper.get_clash_elements_for_visualization(
            candidate.guid_a,
            candidate.guid_b,
            db_path
        )

        # Report status
        if not obj_a:
            self.report({'WARNING'}, f"Element A ({candidate.name_a}) not found in database")
        if not obj_b:
            self.report({'WARNING'}, f"Element B ({candidate.name_b}) not found in database")

        if not obj_a and not obj_b:
            self.report({'ERROR'}, "Neither clash element found in federation database")
            return {"CANCELLED"}

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

        # Zoom to selected
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        override = {'area': area, 'region': region}
                        with context.temp_override(**override):
                            bpy.ops.view3d.view_selected()
                        break

        self.report({'INFO'}, f"Selected clash: {candidate.name_a} vs {candidate.name_b}")
        return {"FINISHED"}


class BIM_OT_analyze_bbox_candidates(bpy.types.Operator):
    """Analyze bbox intersection candidates (POC - no geometry loading)"""
    bl_idname = "bim.analyze_bbox_candidates"
    bl_label = "Analyze Bbox Candidates"
    bl_description = "Test bbox prefiltering on federation database (ARC vs STR)"
    bl_options = {"REGISTER"}

    def execute(self, context):
        import time
        from pathlib import Path

        # Setup logging to ~/Documents/bonsai.log
        log_path = Path.home() / "Documents" / "bonsai.log"
        logger = logging.getLogger('BboxAnalysis')
        logger.setLevel(logging.INFO)
        logger.handlers.clear()

        file_handler = logging.FileHandler(str(log_path), mode='a')
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

        logger.info("=" * 70)
        logger.info("BBOX PREFILTERING POC - Terminal 1/2 Dataset")
        logger.info("=" * 70)

        # Load federation index
        db_path = Path.home() / "federatedmodel.db"
        if not db_path.exists():
            error_msg = f"Database not found: {db_path}"
            logger.error(error_msg)
            self.report({'ERROR'}, error_msg)
            return {"CANCELLED"}

        logger.info(f"Database path: {db_path}")

        print("\n" + "=" * 70)
        print("BBOX PREFILTERING POC - Terminal 1/2 Dataset")
        print("=" * 70)

        try:
            from bonsai.bim.module.federation.core.spatial_index import FederationIndex

            # Build index
            start_time = time.time()
            index = FederationIndex(db_path)
            index.build()
            load_time = time.time() - start_time

            logger.info(f"Loaded spatial index in {load_time:.2f} seconds")
            logger.info(f"Total elements: {index.stats['total_elements']:,}")
            logger.info(f"Disciplines: {', '.join(sorted(index.stats['disciplines']))}")

            print(f"\n✓ Loaded spatial index in {load_time:.2f} seconds")
            print(f"  Total elements: {index.stats['total_elements']:,}")
            print(f"  Disciplines: {', '.join(sorted(index.stats['disciplines']))}")

            # Query disciplines
            logger.info("Querying disciplines...")
            print("\nQuerying disciplines...")
            arc_elements = index.query_by_discipline("ARC")
            str_elements = index.query_by_discipline("STR")

            logger.info(f"ARC elements: {len(arc_elements):,}")
            logger.info(f"STR elements: {len(str_elements):,}")
            print(f"  ARC elements: {len(arc_elements):,}")
            print(f"  STR elements: {len(str_elements):,}")

            # Find bbox intersections
            logger.info("Analyzing bbox intersections...")
            print("\nAnalyzing bbox intersections...")
            start_time = time.time()
            candidates = []

            for arc in arc_elements:
                for str_elem in str_elements:
                    if arc.intersects_bbox(str_elem.bbox):
                        candidates.append((arc.guid, str_elem.guid))

            analysis_time = time.time() - start_time

            # Calculate statistics
            total_combinations = len(arc_elements) * len(str_elements)
            if total_combinations > 0:
                reduction = 100 * (1 - len(candidates) / total_combinations)
            else:
                reduction = 0

            # Report results
            logger.info("=" * 70)
            logger.info("RESULTS:")
            logger.info(f"Total combinations: {total_combinations:,}")
            logger.info(f"Bbox candidates:    {len(candidates):,}")
            logger.info(f"Reduction:          {reduction:.1f}%")
            logger.info(f"Analysis time:      {analysis_time:.2f} seconds")
            logger.info("=" * 70)

            print(f"\n{'=' * 70}")
            print("RESULTS:")
            print(f"{'=' * 70}")
            print(f"  Total combinations: {total_combinations:,}")
            print(f"  Bbox candidates:    {len(candidates):,}")
            print(f"  Reduction:          {reduction:.1f}%")
            print(f"  Analysis time:      {analysis_time:.2f} seconds")
            print(f"{'=' * 70}\n")

            self.report({'INFO'},
                f"Found {len(candidates):,} candidates from "
                f"{total_combinations:,} combinations ({reduction:.1f}% reduction)")

            return {"FINISHED"}

        except Exception as e:
            error_msg = f"Analysis failed: {str(e)}"
            logger.error(error_msg)
            logger.error("Exception traceback:", exc_info=True)
            self.report({'ERROR'}, error_msg)
            import traceback
            traceback.print_exc()
            return {"CANCELLED"}


class BIM_OT_visualize_selected_discipline_clashes(bpy.types.Operator):
    """Visualize selected discipline clash candidates in viewport"""
    bl_idname = "bim.visualize_selected_discipline_clashes"
    bl_label = "Visualize Selected Clashes"
    bl_description = "Show selected clash candidates as colored spheres in viewport (max 10)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = tool.Clash.get_clash_props()

        # Get selected clashes
        selected_clashes = [c for c in props.discipline_clash_candidates if c.selected]

        if not selected_clashes:
            self.report({'WARNING'}, "No clashes selected. Please check clashes in the list to visualize them.")
            return {"CANCELLED"}

        # Enforce 10-item limit
        if len(selected_clashes) > 10:
            self.report({'ERROR'}, f"Too many clashes selected ({len(selected_clashes)}). Maximum is 10 for visualization.")
            return {"CANCELLED"}

        # Create collection for clash markers
        collection_name = "Selected_Clash_Markers"

        # Remove old collection if exists
        if collection_name in bpy.data.collections:
            old_collection = bpy.data.collections[collection_name]
            for obj in old_collection.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.collections.remove(old_collection)

        # Create new collection
        clash_collection = bpy.data.collections.new(collection_name)
        context.scene.collection.children.link(clash_collection)

        print(f"\n=== Visualizing {len(selected_clashes)} Selected Clashes ===")
        print(f"Collection: {collection_name}")

        # Import gizmo module for DB query helper
        from ..federation_analysis.clash import gizmo

        # Get federation DB path
        db_path = props.bbox_database_path

        # Create individual markers for each selected clash
        created_objects = []
        for idx, candidate in enumerate(selected_clashes):
            # Query federation DB for bbox centers (lazy loading)
            center_a, center_b = gizmo.get_clash_bbox_centers(
                candidate.guid_a,
                candidate.guid_b,
                db_path
            )

            if not center_a or not center_b:
                print(f"  ⚠️  Skipping clash {idx+1}: bbox not found in federation DB")
                continue

            # Convert IFC world coords → Blender scene coords (apply offset)
            from mathutils import Vector
            blender_a = gizmo.ifc_to_blender_coords(Vector(center_a))
            blender_b = gizmo.ifc_to_blender_coords(Vector(center_b))

            # Calculate midpoint between elements (in Blender space)
            midpoint_vec = (blender_a + blender_b) / 2
            midpoint = tuple(midpoint_vec)

            print(f"  Clash {idx+1}: {candidate.ifc_class_a} vs {candidate.ifc_class_b}")
            print(f"    IFC Center A: ({center_a[0]:.2f}, {center_a[1]:.2f}, {center_a[2]:.2f})")
            print(f"    IFC Center B: ({center_b[0]:.2f}, {center_b[1]:.2f}, {center_b[2]:.2f})")
            print(f"    Blender Midpoint: ({midpoint[0]:.2f}, {midpoint[1]:.2f}, {midpoint[2]:.2f})")

            # Create marker sphere
            sphere_name = f"Clash_{idx+1}_{candidate.ifc_class_a}_vs_{candidate.ifc_class_b}"
            empty = bpy.data.objects.new(sphere_name, None)
            empty.empty_display_type = 'SPHERE'
            empty.empty_display_size = 8.0  # 8 meters - visible at building scale
            empty.location = midpoint
            empty.color = (1.0, 0.0, 0.0, 1.0)  # Red
            empty.show_name = True  # Show clash description

            # Add to collection
            clash_collection.objects.link(empty)
            created_objects.append(empty)
            print(f"    Created: {sphere_name}")

        # Frame all created markers in viewport using context override
        print(f"\n--- Auto-framing {len(created_objects)} markers in viewport ---")
        if created_objects:
            # Deselect all objects first (optimize: only iterate created objects list)
            bpy.ops.object.select_all(action='DESELECT')

            # Select all clash markers
            for obj in created_objects:
                obj.select_set(True)

            print(f"Selected {len(created_objects)} markers for framing")

            # Find 3D viewport and frame with context override
            viewport_found = False
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            # Use context override to call view_selected from Properties panel
                            override = {'area': area, 'region': region}
                            with context.temp_override(**override):
                                try:
                                    bpy.ops.view3d.view_selected()
                                    print("✓ Successfully framed markers in viewport")
                                    viewport_found = True
                                except Exception as e:
                                    print(f"⚠ Failed to frame viewport: {e}")
                            break
                    if viewport_found:
                        break

            if not viewport_found:
                print("⚠ No 3D viewport found - markers created but not framed")

            # Deselect markers (cleanup)
            for obj in created_objects:
                obj.select_set(False)
        else:
            print("⚠ No objects created to frame")

        self.report({'INFO'}, f"Visualized {len(selected_clashes)} clash markers - framed in viewport")
        print(f"\n✓ COMPLETE: Created {len(selected_clashes)} clash markers\n")

        return {"FINISHED"}


class BIM_OT_deselect_all_clashes(bpy.types.Operator):
    """Uncheck all selected clash candidates"""
    bl_idname = "bim.deselect_all_clashes"
    bl_label = "Uncheck All"
    bl_description = "Deselect all checked clash candidates"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        props = tool.Clash.get_clash_props()
        count = 0

        for candidate in props.discipline_clash_candidates:
            if candidate.selected:
                candidate.selected = False
                count += 1

        self.report({'INFO'}, f"Unchecked {count} clashes")
        return {"FINISHED"}


class BIM_OT_clear_discipline_clash_visualization(bpy.types.Operator):
    """Clear ALL clash visualizations (GPU overlays, gizmos, and mesh objects)"""
    bl_idname = "bim.clear_discipline_clash_visualization"
    bl_label = "Clear All Overlays"
    bl_description = "Remove all clash visualizations: GPU overlays, gizmos, and mesh objects"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        print("\n=== Clearing ALL Clash Visualizations ===")

        # 1. Disable GPU overlay visualization
        from ..federation_analysis.clash import visualization
        if visualization.is_enabled():
            visualization.disable_visualization()
            print("✓ Disabled GPU overlay visualization")

        # 2. Disable Gizmo visualization
        from ..federation_analysis.clash import gizmo
        props = tool.Clash.get_clash_props()
        if gizmo.is_gizmo_group_active():
            props.gizmo_visualization_enabled = False
            gizmo.disable_clash_gizmos()
            print("✓ Disabled gizmo visualization")

        # 3. Clear mesh object collections
        collection_names = ["Selected_Clash_Markers", "Discipline_Clash_Clusters"]
        cleared_collections = 0
        cleared_objects = 0

        for collection_name in collection_names:
            if collection_name in bpy.data.collections:
                clash_collection = bpy.data.collections[collection_name]
                print(f"Found collection: {collection_name} with {len(clash_collection.objects)} objects")

                # Remove all objects in collection
                objects_to_remove = list(clash_collection.objects)
                for obj in objects_to_remove:
                    print(f"  Removing: {obj.name}")
                    bpy.data.objects.remove(obj, do_unlink=True)
                    cleared_objects += 1

                # Remove collection from scene
                bpy.data.collections.remove(clash_collection)
                cleared_collections += 1
                print(f"  Removed collection: {collection_name}")

        # Also look for any orphaned clash markers not in collections
        orphaned = 0
        for obj in list(bpy.data.objects):
            if obj.name.startswith("Clash_") or "Cluster_" in obj.name:
                print(f"Found orphaned clash marker: {obj.name}")
                bpy.data.objects.remove(obj, do_unlink=True)
                orphaned += 1
                cleared_objects += 1

        print(f"\nCleared: {cleared_collections} collections, {cleared_objects} objects ({orphaned} orphaned)")

        # After clearing, frame the building to return user to context
        if cleared_objects > 0:
            print("Returning viewport to building view...")
            # Find 3D viewport and frame all objects (like pressing Home)
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    for region in area.regions:
                        if region.type == 'WINDOW':
                            override = {'area': area, 'region': region}
                            with context.temp_override(**override):
                                try:
                                    bpy.ops.view3d.view_all()  # Home key equivalent
                                    print("✓ Returned to building view")
                                except Exception as e:
                                    print(f"⚠ Could not frame building: {e}")
                            break
                    break

        if cleared_objects == 0:
            self.report({'INFO'}, "No clash visualizations to clear")
        else:
            self.report({'INFO'}, f"Cleared {cleared_objects} clash markers - returned to building view")

        return {"FINISHED"}


class BIM_OT_enable_clash_gpu_visualization(bpy.types.Operator):
    """Enable GPU overlay clash visualization (Google Maps style)"""
    bl_idname = "bim.enable_clash_gpu_visualization"
    bl_label = "Enable GPU Visualization"
    bl_description = "Show clash markers using GPU overlays with zoom-adaptive detail"
    bl_options = {"REGISTER"}

    def execute(self, context):
        from ..federation_analysis.clash import visualization

        props = tool.Clash.get_clash_props()

        if not props.discipline_clash_loaded or not props.discipline_clash_candidates:
            self.report({'WARNING'}, "No clash candidates loaded")
            return {"CANCELLED"}

        # Calculate and cache offset if not already cached
        if "MEP_cached_offset" not in context.scene:
            print("\n📍 Calculating model offset for clash visualization...")

            # Find first placed IFC object in scene as reference
            offset_x, offset_y, offset_z = 0.0, 0.0, 0.0

            for obj in context.scene.objects:
                if not obj or obj.type != 'MESH':
                    continue
                if abs(obj.location.x) < 1.0 and abs(obj.location.y) < 1.0:
                    continue
                if not hasattr(obj, 'BIMObjectProperties'):
                    continue
                if not obj.BIMObjectProperties.ifc_definition_id:
                    continue

                # Found reference - query DB for first clash bbox center as IFC reference
                if props.discipline_clash_candidates:
                    from ..federation_analysis.clash import gizmo
                    first_clash = props.discipline_clash_candidates[0]
                    db_path = props.bbox_database_path
                    ifc_ref = gizmo.get_element_bbox_center(first_clash.guid_a, db_path)

                    if ifc_ref:
                        offset_x = ifc_ref[0] - obj.location.x
                        offset_y = ifc_ref[1] - obj.location.y
                        offset_z = ifc_ref[2] - obj.location.z

                        context.scene["MEP_cached_offset"] = (offset_x, offset_y, offset_z)
                        print(f"   ✓ Cached offset: ({offset_x:.1f}, {offset_y:.1f}, {offset_z:.1f})")
                    break

        # Convert candidates to visualization format (query DB for coords)
        from ..federation_analysis.clash import gizmo
        from pathlib import Path

        db_path = props.bbox_database_path

        # Validate DB path before querying
        if not db_path or not Path(db_path).exists():
            self.report({'ERROR'}, f"Federation database not found: {db_path}")
            print(f"\n⚠️  Federation database not found or not set")
            print(f"   Current path: {db_path}")
            print(f"   Set path in MEP Engineering > Federation Database Path")
            return {"CANCELLED"}

        clash_data = []
        for candidate in props.discipline_clash_candidates:
            center_a, center_b = gizmo.get_clash_bbox_centers(
                candidate.guid_a,
                candidate.guid_b,
                db_path
            )
            if center_a and center_b:
                clash_data.append({
                    'center_a': tuple(center_a),
                    'center_b': tuple(center_b),
                    'id': f"{candidate.guid_a}_{candidate.guid_b}",
                    'distance': 0.0  # Could calculate if needed
                })

        print(f"\n=== Enabling GPU Visualization ===")
        print(f"Loading {len(clash_data)} clash markers...")

        # Load markers and enable visualization
        visualization.load_clash_markers(clash_data)
        visualization.enable_visualization()

        self.report({'INFO'}, f"GPU visualization enabled - {len(clash_data)} markers loaded")
        return {"FINISHED"}


class BIM_OT_disable_clash_gpu_visualization(bpy.types.Operator):
    """Disable GPU overlay clash visualization"""
    bl_idname = "bim.disable_clash_gpu_visualization"
    bl_label = "Disable GPU Visualization"
    bl_description = "Hide GPU overlay clash markers"
    bl_options = {"REGISTER"}

    def execute(self, context):
        from ..federation_analysis.clash import visualization

        if not visualization.is_enabled():
            self.report({'INFO'}, "GPU visualization already disabled")
            return {"FINISHED"}

        visualization.disable_visualization()

        self.report({'INFO'}, "GPU visualization disabled")
        return {"FINISHED"}


class BIM_OT_enable_clash_gizmo_visualization(bpy.types.Operator):
    """Enable Blender gizmo-based clash visualization (clickable spheres)"""
    bl_idname = "bim.enable_clash_gizmo_visualization"
    bl_label = "Enable Gizmo Visualization"
    bl_description = "Show clash markers as interactive gizmos (clickable, colored spheres)"
    bl_options = {"REGISTER"}

    def execute(self, context):
        from ..federation_analysis.clash import gizmo

        props = tool.Clash.get_clash_props()

        if not props.discipline_clash_loaded or not props.discipline_clash_candidates:
            self.report({'WARNING'}, "No clash candidates loaded")
            return {"CANCELLED"}

        # Check if any clashes are selected for visualization
        selected_count = sum(1 for c in props.discipline_clash_candidates if c.selected)
        if selected_count == 0:
            self.report({'WARNING'}, "No clashes selected. Select clashes from the list first.")
            return {"CANCELLED"}

        # Calculate and cache offset if not already cached
        if "MEP_cached_offset" not in context.scene:
            print("\n📍 Calculating model offset for clash gizmo visualization...")

            # Find first placed IFC object in scene as reference
            offset_x, offset_y, offset_z = 0.0, 0.0, 0.0

            for obj in context.scene.objects:
                if not obj or obj.type != 'MESH':
                    continue
                if abs(obj.location.x) < 1.0 and abs(obj.location.y) < 1.0:
                    continue
                if not hasattr(obj, 'BIMObjectProperties'):
                    continue
                if not obj.BIMObjectProperties.ifc_definition_id:
                    continue

                # Found reference - query DB for first clash bbox center as IFC reference
                if props.discipline_clash_candidates:
                    from ..federation_analysis.clash import gizmo
                    first_clash = props.discipline_clash_candidates[0]
                    db_path = props.bbox_database_path
                    ifc_ref = gizmo.get_element_bbox_center(first_clash.guid_a, db_path)

                    if ifc_ref:
                        offset_x = ifc_ref[0] - obj.location.x
                        offset_y = ifc_ref[1] - obj.location.y
                        offset_z = ifc_ref[2] - obj.location.z

                        context.scene["MEP_cached_offset"] = (offset_x, offset_y, offset_z)
                        print(f"   ✓ Cached offset: ({offset_x:.1f}, {offset_y:.1f}, {offset_z:.1f})")
                    break

        print(f"\n=== Enabling Gizmo Visualization ===")
        print(f"Loading {selected_count} selected clash gizmos (out of {len(props.discipline_clash_candidates)} total)...")

        # Enable gizmo visualization flag (makes poll() return True)
        props.gizmo_visualization_enabled = True

        # Enable gizmo visualization
        gizmo.enable_clash_gizmos(context)

        self.report({'INFO'}, f"Gizmo visualization enabled - {selected_count} markers")
        return {"FINISHED"}


class BIM_OT_disable_clash_gizmo_visualization(bpy.types.Operator):
    """Disable gizmo-based clash visualization"""
    bl_idname = "bim.disable_clash_gizmo_visualization"
    bl_label = "Disable Gizmo Visualization"
    bl_description = "Hide gizmo clash markers"
    bl_options = {"REGISTER"}

    def execute(self, context):
        from ..federation_analysis.clash import gizmo

        props = tool.Clash.get_clash_props()

        if not gizmo.is_gizmo_group_active():
            self.report({'INFO'}, "Gizmo visualization already disabled")
            return {"FINISHED"}

        # Disable gizmo visualization flag (makes poll() return False)
        props.gizmo_visualization_enabled = False

        gizmo.disable_clash_gizmos()

        self.report({'INFO'}, "Gizmo visualization disabled")
        return {"FINISHED"}


class BIM_OT_load_clash_geometry(bpy.types.Operator):
    """Load geometry for selected clash elements on-demand"""
    bl_idname = "bim.load_clash_geometry"
    bl_label = "Load Clash Geometry"
    bl_description = "Load only the two elements involved in the selected clash (lazy loading from discipline IFCs)"
    bl_options = {"REGISTER", "UNDO"}

    clash_index: bpy.props.IntProperty()

    @classmethod
    def poll(cls, context):
        props = tool.Clash.get_clash_props()
        return props.discipline_clash_loaded and props.discipline_clash_candidates

    def execute(self, context):
        import ifcopenshell
        import ifcopenshell.geom
        from mathutils import Matrix, Vector
        from pathlib import Path
        import time

        props = tool.Clash.get_clash_props()

        # Get selected clash
        if self.clash_index >= 0:
            clash_idx = self.clash_index
        else:
            clash_idx = props.active_discipline_clash_index

        if clash_idx >= len(props.discipline_clash_candidates):
            self.report({'ERROR'}, "Invalid clash index")
            return {"CANCELLED"}

        candidate = props.discipline_clash_candidates[clash_idx]

        print(f"\n{'='*70}")
        print(f"LOADING CLASH GEOMETRY (Lazy Loading)")
        print(f"{'='*70}")
        print(f"Clash {clash_idx + 1}: {candidate.ifc_class_a} vs {candidate.ifc_class_b}")
        print(f"GUID A: {candidate.guid_a}")
        print(f"GUID B: {candidate.guid_b}")

        # Query federation DB for source IFC file paths
        db_path = props.bbox_database_path
        if not db_path or not Path(db_path).exists():
            self.report({'ERROR'}, "Federation database not found. Run clash detection first.")
            return {"CANCELLED"}

        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Get source file paths for both elements
        cursor.execute("SELECT filepath FROM elements_meta WHERE guid = ?", (candidate.guid_a,))
        row_a = cursor.fetchone()
        cursor.execute("SELECT filepath FROM elements_meta WHERE guid = ?", (candidate.guid_b,))
        row_b = cursor.fetchone()
        conn.close()

        if not row_a or not row_b:
            self.report({'ERROR'}, "Source IFC files not found in database")
            return {"CANCELLED"}

        ifc_path_a = row_a[0]
        ifc_path_b = row_b[0]

        # Check if filepaths are available (database-only mode may have None)
        if not ifc_path_a or not ifc_path_b:
            self.report({'WARNING'}, "Database-only mode: Load geometry from database not yet implemented")
            print("\n⚠️  Database-only mode detected (filepaths are None)")
            print("   Geometry loading from database vertices not yet implemented")
            print("   This feature requires loading geometry from element_geometry table")
            return {"CANCELLED"}

        print(f"\nSource IFC A: {Path(ifc_path_a).name}")
        print(f"Source IFC B: {Path(ifc_path_b).name}")

        # Create or get inspection collection
        collection_name = "Clash_Inspection"
        if collection_name in bpy.data.collections:
            collection = bpy.data.collections[collection_name]
            # Clear existing objects
            for obj in collection.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
            print(f"\n✓ Cleared previous inspection geometry")
        else:
            collection = bpy.data.collections.new(collection_name)
            context.scene.collection.children.link(collection)
            print(f"\n✓ Created {collection_name} collection")

        # Get model offset for coordinate conversion
        offset = Vector((0, 0, 0))
        if "MEP_cached_offset" in context.scene:
            offset = Vector(context.scene["MEP_cached_offset"])
            print(f"✓ Using cached offset: ({offset.x:.1f}, {offset.y:.1f}, {offset.z:.1f})")

        # Load Element A
        start_time = time.time()
        obj_a = self.load_single_element(
            ifc_path_a,
            candidate.guid_a,
            f"Clash_{clash_idx+1}_A_{candidate.ifc_class_a}",
            collection,
            offset
        )

        # Load Element B
        obj_b = self.load_single_element(
            ifc_path_b,
            candidate.guid_b,
            f"Clash_{clash_idx+1}_B_{candidate.ifc_class_b}",
            collection,
            offset
        )

        load_time = time.time() - start_time

        if not obj_a or not obj_b:
            self.report({'ERROR'}, "Failed to load clash elements")
            return {"CANCELLED"}

        print(f"\n✓ Loaded 2 elements in {load_time:.2f}s")
        print(f"  Element A: {obj_a.name}")
        print(f"  Element B: {obj_b.name}")

        # Focus viewport on loaded elements
        for obj in collection.objects:
            obj.select_set(True)

        # Frame selected in viewport
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        override = {'area': area, 'region': region}
                        with context.temp_override(**override):
                            bpy.ops.view3d.view_selected()
                        break

        print(f"✓ Focused viewport on clash elements")
        print(f"{'='*70}\n")

        self.report({'INFO'}, f"Loaded clash geometry ({load_time:.1f}s)")
        return {"FINISHED"}

    def load_single_element(self, ifc_path, guid, obj_name, collection, offset):
        """Load a single IFC element by GUID and create Blender object"""
        import ifcopenshell
        import ifcopenshell.geom
        import numpy as np

        try:
            # Open IFC file (lightweight, doesn't process geometry yet)
            ifc_file = ifcopenshell.open(ifc_path)

            # Get element by GUID
            element = ifc_file.by_guid(guid)
            if not element:
                print(f"  ⚠️  Element not found: {guid}")
                return None

            # Generate geometry using IfcOpenShell (use world coords for simplicity)
            settings = ifcopenshell.geom.settings()
            settings.set(settings.USE_WORLD_COORDS, True)

            shape = ifcopenshell.geom.create_shape(settings, element)
            if not shape:
                print(f"  ⚠️  Failed to generate geometry for {guid}")
                return None

            # Get geometry data (in IFC world coordinates)
            verts = shape.geometry.verts
            faces = shape.geometry.faces

            # Convert vertices to Blender format and apply offset
            # IFC world coords → Blender scene coords: vertex - offset
            vertices = []
            for i in range(0, len(verts), 3):
                # Apply offset to convert IFC world → Blender scene
                blender_x = verts[i] - offset.x
                blender_y = verts[i+1] - offset.y
                blender_z = verts[i+2] - offset.z
                vertices.append([blender_x, blender_y, blender_z])

            faces_list = [[faces[i], faces[i+1], faces[i+2]] for i in range(0, len(faces), 3)]

            # Create mesh with transformed vertices
            mesh = bpy.data.meshes.new(obj_name)
            mesh.from_pydata(vertices, [], faces_list)
            mesh.update()

            # Create object at origin (vertices already in Blender scene coords)
            obj = bpy.data.objects.new(obj_name, mesh)
            collection.objects.link(obj)
            obj.location = (0, 0, 0)  # Vertices already transformed

            # Store IFC metadata
            obj["ifc_guid"] = guid
            obj["ifc_class"] = element.is_a()
            obj["ifc_source"] = str(ifc_path)

            print(f"  ✓ Loaded: {element.is_a()} (GUID: {guid[:8]}...)")

            return obj

        except Exception as e:
            print(f"  ⚠️  Error loading {guid}: {e}")
            import traceback
            traceback.print_exc()
            return None


# ============================================================================
# BBox Semantic Geometry - Phase 2: Visualization Operators
# ============================================================================


class BIM_OT_enable_bbox_visualization(bpy.types.Operator):
    """Enable BBox wireframe visualization for federation elements"""
    bl_idname = "bim.enable_bbox_visualization"
    bl_label = "Enable BBox Visualization"
    bl_description = "Render federation elements as colored wireframe bounding boxes (instant loading, <10MB)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from ..federation import bbox_visualization

        props = tool.Clash.get_clash_props()
        fed_props = context.scene.BIMFederationProperties

        # Validate database path (from Federation panel)
        db_path = fed_props.federation_database_path
        if not db_path:
            self.report({'ERROR'}, "Please load Federation Database in Multi-Model Federation panel")
            return {'CANCELLED'}

        # Resolve Blender relative paths (// prefix)
        db_path = Path(bpy.path.abspath(db_path))
        if not db_path.exists():
            self.report({'ERROR'}, f"Federation database not found: {db_path}")
            return {'CANCELLED'}

        # Get element limit (0 = all elements)
        limit = props.bbox_element_limit if props.bbox_element_limit > 0 else None

        # Enable visualization
        success, message = bbox_visualization.enable_bbox_visualization(str(db_path), limit)

        if success:
            props.bbox_visualization_enabled = True
            props.lod_visualization_mode = 'BBOX_WIREFRAME'
            self.report({'INFO'}, message)
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, message)
            return {'CANCELLED'}


class BIM_OT_disable_bbox_visualization(bpy.types.Operator):
    """Disable BBox wireframe visualization"""
    bl_idname = "bim.disable_bbox_visualization"
    bl_label = "Disable BBox Visualization"
    bl_description = "Remove BBox wireframe rendering from viewport"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from ..federation import bbox_visualization

        props = tool.Clash.get_clash_props()

        # Disable visualization
        success, message = bbox_visualization.disable_bbox_visualization()

        if success:
            props.bbox_visualization_enabled = False
            props.lod_visualization_mode = 'NONE'
            self.report({'INFO'}, message)
            return {'FINISHED'}
        else:
            self.report({'ERROR'}, message)
            return {'CANCELLED'}


class BIM_OT_enable_semantic_proxy_visualization(bpy.types.Operator):
    """Enable semantic proxy geometry (basic templates)"""
    bl_idname = "bim.enable_semantic_proxy_visualization"
    bl_label = "Enable Semantic Proxies"
    bl_description = "Generate basic procedural geometry from semantic metadata"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from ..federation_analysis.visualization import semantic_shapes as semantic_visualization

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
        success, message = semantic_visualization.enable_semantic_visualization(
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
        from ..federation_analysis.visualization import semantic_shapes as semantic_visualization

        props = tool.Clash.get_clash_props()

        success, message = semantic_visualization.disable_semantic_visualization()

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
        from ..federation_analysis.visualization import semantic_shapes as semantic_visualization

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
        success, message = semantic_visualization.enable_semantic_visualization(
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
        from ..federation_analysis.visualization import semantic_shapes as semantic_visualization

        props = tool.Clash.get_clash_props()

        success, message = semantic_visualization.disable_semantic_visualization()

        props.bbox_visualization_enabled = False
        props.lod_visualization_mode = 'NONE'

        self.report({'INFO'}, message)
        return {'FINISHED'}

# ============================================================================
# INTELLIGENT CLASH GROUPING & RESOLUTION OPERATORS (POC)
# ============================================================================

class BIM_OT_analyze_clash_groups(bpy.types.Operator):
    """Analyze clashes and group by cascade detection"""
    bl_idname = "bim.analyze_clash_groups"
    bl_label = "Analyze & Group Clashes"
    bl_description = "Detect cascade clash patterns (elements with 3+ clashes)"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from ..federation_analysis.clash import clash_grouping
        from pathlib import Path

        props = tool.Clash.get_clash_props()
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

        # Check if clashes are loaded
        if not props.discipline_clash_loaded or not props.discipline_clash_candidates:
            self.report({'ERROR'}, "Run clash detection first")
            return {'CANCELLED'}

        # Initialize grouping analyzer
        analyzer = clash_grouping.ClashGroupAnalyzer(str(db_path))

        # Convert discipline clash candidates to format expected by analyzer
        # (list of tuples: (clash_id, element1_guid, element2_guid))
        clashes = []
        for idx, candidate in enumerate(props.discipline_clash_candidates):
            clashes.append((idx, candidate.guid_a, candidate.guid_b))

        self.report({'INFO'}, f"Analyzing {len(clashes)} clashes for grouping...")

        # Analyze and create groups
        groups = analyzer.group_clashes(clashes, cascade_threshold=3)

        # Clear existing groups
        props.clash_groups.clear()

        # Populate clash groups property collection
        for group_data in groups:
            group = props.clash_groups.add()
            group.group_id = group_data['group_id']
            group.element_guid = group_data['element_guid']
            group.element_name = group_data['element_name']
            group.ifc_class = group_data['ifc_class']
            group.discipline = group_data['discipline']
            group.clash_count = group_data['clash_count']
            group.severity = group_data['severity']
            group.member_clash_ids = ','.join(str(cid) for cid in group_data['member_clash_ids'])

        props.clash_groups_loaded = True
        props.active_clash_group_index = 0

        self.report({'INFO'}, f"Found {len(groups)} clash groups")
        return {'FINISHED'}


class BIM_OT_suggest_resolutions(bpy.types.Operator):
    """Generate resolution options for selected clash group"""
    bl_idname = "bim.suggest_resolutions"
    bl_label = "Suggest Resolutions"
    bl_description = "Generate ranked resolution options with cost/effort estimates"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        from ..federation_analysis.clash import resolution_engine
        from pathlib import Path

        props = tool.Clash.get_clash_props()
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

        # Check if groups are loaded
        if not props.clash_groups_loaded or not props.clash_groups:
            self.report({'ERROR'}, "Run clash grouping first")
            return {'CANCELLED'}

        # Get active group
        if props.active_clash_group_index < 0 or props.active_clash_group_index >= len(props.clash_groups):
            self.report({'ERROR'}, "No clash group selected")
            return {'CANCELLED'}

        group = props.clash_groups[props.active_clash_group_index]

        # Initialize resolution engine
        engine = resolution_engine.ResolutionEngine(str(db_path))

        self.report({'INFO'}, f"Generating resolutions for {group.element_name}...")

        # Generate resolution options
        options = engine.generate_resolution_options(
            group_id=group.group_id,
            element_guid=group.element_guid,
            clash_count=group.clash_count,
            discipline=group.discipline
        )

        # Clear existing options
        props.resolution_options.clear()

        # Populate resolution options property collection
        for opt_data in options:
            option = props.resolution_options.add()
            option.option_id = opt_data['option_id']
            option.description = opt_data['description']
            option.total_hours = opt_data['total_hours']
            option.total_cost = opt_data['total_cost']
            option.risk_level = opt_data['risk_level']
            option.clashes_resolved = opt_data['clashes_resolved']
            option.schedule_days = opt_data['schedule_days']
            option.recommended = opt_data.get('recommended', False)

        props.active_resolution_option_index = 0

        self.report({'INFO'}, f"Generated {len(options)} resolution options")
        return {'FINISHED'}


class BIM_OT_select_resolution_option(bpy.types.Operator):
    """Select and track resolution option choice"""
    bl_idname = "bim.select_resolution_option"
    bl_label = "Select Resolution"
    bl_description = "Choose this resolution option and track in database"
    bl_options = {'REGISTER', 'UNDO'}

    option_index: bpy.props.IntProperty(name="Option Index", default=0)

    def execute(self, context):
        from ..federation_analysis.clash import resolution_engine
        from pathlib import Path

        props = tool.Clash.get_clash_props()
        fed_props = context.scene.BIMFederationProperties

        # Get database path
        db_path = fed_props.federation_database_path
        if not db_path:
            self.report({'ERROR'}, "Please load Federation Database first")
            return {'CANCELLED'}

        db_path = Path(bpy.path.abspath(db_path))

        # Get selected option
        if self.option_index < 0 or self.option_index >= len(props.resolution_options):
            self.report({'ERROR'}, "Invalid option selected")
            return {'CANCELLED'}

        option = props.resolution_options[self.option_index]
        group = props.clash_groups[props.active_clash_group_index]

        # Initialize engine and track selection
        engine = resolution_engine.ResolutionEngine(str(db_path))

        # Track user selection in database (for Phase 2 learning)
        engine.track_user_selection(
            group_id=group.group_id,
            option_id=option.option_id,
            selected_description=option.description,
            estimated_hours=option.total_hours,
            estimated_cost=option.total_cost
        )

        self.report({'INFO'}, f"Selected: {option.description} (${option.total_cost:.0f}, {option.total_hours:.1f} hrs)")
        return {'FINISHED'}
