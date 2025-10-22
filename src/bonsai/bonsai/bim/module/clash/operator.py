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
                from bonsai.bim.module.federation.spatial_index import FederationIndex

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


class BIM_OT_clash_by_discipline(bpy.types.Operator):
    """Run discipline-based clash detection using federation database"""
    bl_idname = "bim.clash_by_discipline"
    bl_label = "Clash by Discipline"
    bl_description = "Quick clash detection by discipline using spatial index"
    bl_options = {"REGISTER"}

    def execute(self, context):
        import time
        from pathlib import Path

        props = tool.Clash.get_clash_props()

        # Setup logging
        log_path = Path.home() / "Documents" / "bonsai.log"
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

        # Load federation database
        db_path = Path.home() / "federatedmodel.db"
        if not db_path.exists():
            error_msg = f"Federation database not found: {db_path}"
            logger.error(error_msg)
            self.report({'ERROR'}, error_msg)
            return {"CANCELLED"}

        logger.info(f"Database: {db_path}")

        # Apply preset if selected
        disc_a = props.discipline_a
        disc_b = props.discipline_b

        if props.clash_preset != 'CUSTOM':
            preset_map = {
                'ARC_STR': ('ARC', 'STR'),
                'MEP_ARC': ('MEP', 'ARC'),
                'MEP_STR': ('MEP', 'STR'),
                'ACMV_ARC': ('ACMV', 'ARC'),
                'ELEC_ARC': ('ELEC', 'ARC'),
            }
            if props.clash_preset in preset_map:
                disc_a, disc_b = preset_map[props.clash_preset]
                logger.info(f"Applied preset: {props.clash_preset}")

        logger.info(f"Discipline A: {disc_a}")
        logger.info(f"Discipline B: {disc_b}")
        logger.info(f"Tolerance: {props.discipline_tolerance}")

        print("\n" + "=" * 70)
        print(f"CLASH DETECTION: {disc_a} vs {disc_b}")
        print("=" * 70)

        try:
            from bonsai.bim.module.federation.spatial_index import FederationIndex

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

            # Query disciplines
            print(f"\nQuerying disciplines...")
            elements_a = index.query_by_discipline(disc_a)
            elements_b = index.query_by_discipline(disc_b)

            logger.info(f"{disc_a} elements: {len(elements_a):,}")
            logger.info(f"{disc_b} elements: {len(elements_b):,}")

            print(f"  {disc_a}: {len(elements_a):,} elements")
            print(f"  {disc_b}: {len(elements_b):,} elements")

            if not elements_a:
                error_msg = f"No elements found for discipline {disc_a}"
                logger.error(error_msg)
                self.report({'ERROR'}, error_msg)
                return {"CANCELLED"}

            if not elements_b:
                error_msg = f"No elements found for discipline {disc_b}"
                logger.error(error_msg)
                self.report({'ERROR'}, error_msg)
                return {"CANCELLED"}

            # Find bbox intersections
            print(f"\nAnalyzing bbox intersections...")
            start_time = time.time()
            candidates = []

            for elem_a in elements_a:
                for elem_b in elements_b:
                    if prefilter.bboxes_intersect(elem_a.bbox, elem_b.bbox, tolerance=props.discipline_tolerance):
                        candidates.append({
                            'guid_a': elem_a.guid,
                            'guid_b': elem_b.guid,
                            'name_a': elem_a.ifc_class,  # Use IFC class as name (FederationElement doesn't have name)
                            'name_b': elem_b.ifc_class,
                            'ifc_class_a': elem_a.ifc_class,
                            'ifc_class_b': elem_b.ifc_class,
                            'bbox_center_a': elem_a.centroid,  # Store bbox center for spatial lookup
                            'bbox_center_b': elem_b.centroid,
                        })

            analysis_time = time.time() - start_time

            # Calculate statistics
            total_combinations = len(elements_a) * len(elements_b)
            reduction = 100 * (1 - len(candidates) / total_combinations) if total_combinations > 0 else 0

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
            print(f"  Total combinations: {total_combinations:,}")
            print(f"  Bbox candidates:    {len(candidates):,}")
            print(f"  Reduction:          {reduction:.1f}%")
            print(f"  Analysis time:      {analysis_time:.2f} seconds")
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
                new.bbox_center_a = candidate['bbox_center_a']
                new.bbox_center_b = candidate['bbox_center_b']

            props.discipline_clash_loaded = len(candidates) > 0
            props.active_discipline_clash_index = 0

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

        # Get the merged IFC file
        ifc_file = tool.Ifc.get()
        if not ifc_file:
            self.report({'ERROR'}, "No IFC file loaded")
            return {"CANCELLED"}

        # Try to find elements by GUID first (fast path)
        elem_a = None
        elem_b = None

        try:
            elem_a = ifc_file.by_guid(candidate.guid_a)
            print(f"✓ Found Element A by GUID")
        except RuntimeError:
            print(f"Element A not found by GUID, using spatial lookup")

        try:
            elem_b = ifc_file.by_guid(candidate.guid_b)
            print(f"✓ Found Element B by GUID")
        except RuntimeError:
            print(f"Element B not found by GUID, using spatial lookup")

        # If GUID lookup failed, use spatial lookup (robust fallback)
        if not elem_a:
            elem_a = self.find_element_by_spatial_proximity(
                ifc_file,
                candidate.ifc_class_a,
                candidate.bbox_center_a
            )
            if elem_a:
                print(f"✓ Found Element A by spatial proximity")

        if not elem_b:
            elem_b = self.find_element_by_spatial_proximity(
                ifc_file,
                candidate.ifc_class_b,
                candidate.bbox_center_b
            )
            if elem_b:
                print(f"✓ Found Element B by spatial proximity")

        if not elem_a and not elem_b:
            self.report({'ERROR'},
                f"Neither clash element found in loaded IFC. "
                f"Elements may not be loaded or geometries may have changed.")
            return {"CANCELLED"}

        # Find corresponding Blender objects (only for found elements)
        obj_a = tool.Ifc.get_object(elem_a) if elem_a else None
        obj_b = tool.Ifc.get_object(elem_b) if elem_b else None

        # Report which elements were found/not found
        if not elem_a:
            self.report({'WARNING'}, f"Element A ({candidate.name_a}) not in loaded IFC file")
        elif not obj_a:
            self.report({'WARNING'}, f"Element A ({candidate.name_a}) found but not loaded in viewport")

        if not elem_b:
            self.report({'WARNING'}, f"Element B ({candidate.name_b}) not in loaded IFC file")
        elif not obj_b:
            self.report({'WARNING'}, f"Element B ({candidate.name_b}) found but not loaded in viewport")

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
            from bonsai.bim.module.federation.spatial_index import FederationIndex

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
