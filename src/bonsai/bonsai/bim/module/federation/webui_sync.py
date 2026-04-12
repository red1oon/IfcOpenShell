"""
WebUI Sync — Bidirectional Bonsai ↔ Web UI communication.

Selection in Bonsai viewport → pushed to Web UI via HTTP POST → SSE to browser.
Color commands from Web UI → polled by Bonsai timer → applied to viewport.

Architecture:
  Bonsai timer (0.5s) → POST /api selectionChanged → WebUIServer SSE → Browser
  Browser → POST /api applyScheme → WebUIServer queue → Bonsai pollCommands → apply

// Implementing BIM_Designer_SRS.md §29.5 — Bonsai ↔ Web UI sync (S57)
"""

import bpy
from bpy.types import Operator
from bpy.props import BoolProperty
import json
import threading
import urllib.request
import urllib.error

# WebUI server URL (same machine, port 9878)
WEBUI_URL = "http://localhost:9878/api"

# Discipline color map (matches Web UI PALETTES.discipline)
DISCIPLINE_COLORS = {
    'ARC': (0.545, 0.616, 0.765, 1.0),
    'STR': (0.831, 0.647, 0.455, 1.0),
    'MEP': (0.420, 0.710, 0.878, 1.0),
    'ELEC': (0.961, 0.843, 0.431, 1.0),
    'PLB': (0.365, 0.678, 0.886, 1.0),
    'FP':  (0.906, 0.298, 0.235, 1.0),
    'HVAC': (0.282, 0.788, 0.690, 1.0),
    'CW':  (0.733, 0.561, 0.808, 1.0),
}

# Module-level sync state (Blender 5.0+ does not allow setting attrs on bpy.app)
_sync_active = False
_sync_last_selection = set()
_sync_last_name = ""


def _post_json(action, data=None):
    """Non-blocking HTTP POST to WebUI server. Runs in background thread."""
    payload = {"action": action}
    if data:
        payload.update(data)
    try:
        req = urllib.request.Request(
            WEBUI_URL,
            data=json.dumps(payload).encode('utf-8'),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def _post_json_bg(action, data=None):
    """Fire-and-forget POST in background thread."""
    t = threading.Thread(target=_post_json, args=(action, data), daemon=True)
    t.start()


class BIM_OT_start_webui_sync(Operator):
    """Start bidirectional sync between Bonsai viewport and Web UI, opens browser"""
    bl_idname = "bim.start_webui_sync"
    bl_label = "Start Web UI Sync"
    bl_options = {'REGISTER'}

    open_browser: BoolProperty(name="Open Browser", default=True,
                               description="Also open Web UI in browser")

    def execute(self, context):
        global _sync_active, _sync_last_selection, _sync_last_name
        # Check if timer already running
        if _sync_active:
            self.report({'INFO'}, "Web UI sync already running")
            # Still open browser if requested
            if self.open_browser:
                _open_browser()
            return {'FINISHED'}

        _sync_active = True
        _sync_last_selection = set()
        _sync_last_name = ""

        bpy.app.timers.register(_sync_timer, first_interval=1.0)
        print(f"[WebUI Sync] Timer registered. _sync_active={_sync_active}")

        if self.open_browser:
            _open_browser()

        self.report({'INFO'}, "Web UI sync started — two-way Bonsai ↔ browser link active")
        print("[WebUI Sync] START complete — polling every 0.5s")
        return {'FINISHED'}


def _open_browser(tab="10"):
    """Open Web UI in default browser."""
    import webbrowser
    webbrowser.open(f"http://localhost:9878/#tab={tab}")


class BIM_OT_stop_webui_sync(Operator):
    """Stop bidirectional sync"""
    bl_idname = "bim.stop_webui_sync"
    bl_label = "Stop Web UI Sync"
    bl_options = {'REGISTER'}

    def execute(self, context):
        global _sync_active
        _sync_active = False
        self.report({'INFO'}, "Web UI sync stopped")
        return {'FINISHED'}


_sync_tick = 0

def _sync_timer():
    """Timer callback — runs every 0.5s. Checks selection + polls commands."""
    global _sync_tick
    if not _sync_active:
        print("[WebUI Sync] Timer stopped (_sync_active=False)")
        return None  # unregister timer

    _sync_tick += 1
    # Log every 20th tick (~10s) to confirm timer is alive
    if _sync_tick % 20 == 1:
        print(f"[WebUI Sync] Timer alive — tick {_sync_tick}")

    try:
        _check_selection()
        _poll_commands()
    except Exception as e:
        print(f"[WebUI Sync] Error: {e}")
        import traceback
        traceback.print_exc()

    return 0.5  # re-run in 0.5s


def _check_selection():
    """Detect viewport selection change and push to WebUI."""
    global _sync_last_name
    context = bpy.context
    if not hasattr(context, 'selected_objects'):
        return

    active = context.active_object
    current_name = active.name if active else ""

    if current_name == _sync_last_name:
        return  # no change

    _sync_last_name = current_name

    if not active or active.type != 'MESH':
        _post_json_bg("selectionChanged", {
            "objectName": "", "ifcClass": "", "guid": "",
            "discipline": "", "material": "", "productId": ""
        })
        return

    # Extract BIM metadata from object custom properties
    sel_data = {
        "objectName": active.name,
        "ifcClass": active.get('ifc_class', active.get('IfcClass', '')),
        "guid": active.get('GlobalId', active.get('guid', '')),
        "discipline": active.get('discipline', active.get('Discipline', '')),
        "material": active.get('material', active.get('Material', '')),
        "productId": active.get('product_id', active.get('ProductId', '')),
        "hostType": active.get('host_type', active.get('HostType', '')),
    }

    _post_json_bg("selectionChanged", sel_data)


def _poll_commands():
    """Poll WebUI for pending commands (color changes, etc.)."""
    result = _post_json("pollCommands")
    if not result or not result.get("commands"):
        return

    cmds = result["commands"]
    print(f"[WebUI Sync] pollCommands returned {len(cmds)} command(s): {[c.get('command','?') for c in cmds]}")

    for cmd in cmds:
        print(f"[WebUI Sync] RAW CMD: {cmd}")
        command = cmd.get("command", "")
        if command == "applyScheme":
            _apply_scheme_command(cmd)
        elif command == "loadOutput":
            _load_output_command(cmd)
        elif command == "previewBBoxes":
            _preview_bboxes_command(cmd)


def _preview_bboxes_command(cmd):
    """Fetch order lines from Java server and render as wireframe bboxes.

    Lightweight preview — no compile. Category-coloured wireframe boxes via
    design_bbox.enable(). Same visual as Design Mode / Federation Preview.
    """
    building_id = cmd.get("buildingId", "")
    if not building_id:
        print("[WebUI Sync] previewBBoxes: no buildingId")
        return

    print(f"[WebUI Sync] previewBBoxes: {building_id}")

    # Fetch order lines from Java server via HTTP
    result = _post_json("listOrderLines", {"buildingId": building_id})
    if not result:
        print("[WebUI Sync] previewBBoxes: server unreachable")
        return

    lines = result.get("lines", result.get("orderLines", []))
    if not lines:
        print(f"[WebUI Sync] previewBBoxes: no order lines for {building_id}")
        return

    # Convert to bbox format
    bboxes = []
    for line in lines:
        w = line.get("widthMm", line.get("aabb_width_mm", 0))
        d = line.get("depthMm", line.get("aabb_depth_mm", 0))
        h = line.get("heightMm", line.get("aabb_height_mm", 0))
        dx = line.get("dx", 0)
        dy = line.get("dy", 0)
        dz = line.get("dz", 0)
        if w <= 0 and d <= 0 and h <= 0:
            continue
        bboxes.append({
            "bomId": str(line.get("orderLineId", "")),
            "name": line.get("familyRef", line.get("productId", "?")),
            "bomType": line.get("hostType", "ITEM"),
            "category": line.get("bomCategory", "ARC"),
            "minX": dx, "minY": dy, "minZ": dz,
            "maxX": dx + w, "maxY": dy + d, "maxZ": dz + h,
        })

    if not bboxes:
        print(f"[WebUI Sync] previewBBoxes: 0 valid bboxes from {len(lines)} lines")
        return

    # Try BIM Designer design_bbox first (GPU wireframe overlay)
    try:
        from bonsai.bim.module.federation import design_bbox
        design_bbox.enable(bboxes)
        print(f"[WebUI Sync] previewBBoxes: {len(bboxes)} bboxes rendered (federation)")
        _force_viewport_refresh()
        return
    except Exception:
        pass

    # Fallback: try BIM Designer addon's design_bbox
    try:
        import importlib
        dbbox = importlib.import_module("bonsai_bim_designer.design_bbox")
        dbbox.enable(bboxes)
        print(f"[WebUI Sync] previewBBoxes: {len(bboxes)} bboxes rendered (designer)")
        _force_viewport_refresh()
        return
    except Exception as e:
        print(f"[WebUI Sync] previewBBoxes: design_bbox not available ({e})")

    # Last resort: create simple cube wireframes
    import bpy
    collection_name = "BIM_Preview_BBoxes"
    if collection_name in bpy.data.collections:
        coll = bpy.data.collections[collection_name]
        for obj in list(coll.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
    else:
        coll = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(coll)

    for bb in bboxes:
        cx = (bb["minX"] + bb["maxX"]) / 2000.0  # mm → m
        cy = (bb["minY"] + bb["maxY"]) / 2000.0
        cz = (bb["minZ"] + bb["maxZ"]) / 2000.0
        sx = (bb["maxX"] - bb["minX"]) / 1000.0
        sy = (bb["maxY"] - bb["minY"]) / 1000.0
        sz = (bb["maxZ"] - bb["minZ"]) / 1000.0
        if sx <= 0 or sy <= 0 or sz <= 0:
            continue
        bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz), scale=(sx, sy, sz))
        obj = bpy.context.active_object
        obj.name = bb.get("name", "bbox")
        obj.display_type = 'WIRE'
        # Category color
        cat_colors = {
            'STR': (0.831, 0.647, 0.455, 1.0),
            'ARC': (0.545, 0.616, 0.765, 1.0),
            'MEP': (0.420, 0.710, 0.878, 1.0),
            'FP':  (0.906, 0.298, 0.235, 1.0),
        }
        obj.color = cat_colors.get(bb.get("category", ""), (0.6, 0.6, 0.6, 1.0))
        # Move to preview collection
        for c in obj.users_collection:
            c.objects.unlink(obj)
        coll.objects.link(obj)

    print(f"[WebUI Sync] previewBBoxes: {len(bboxes)} wireframe cubes created")
    _force_viewport_refresh()


def _apply_scheme_command(cmd):
    """Apply a color scheme command received from Web UI."""
    scheme = cmd.get("schemeName", "")
    target = cmd.get("objectName", "")
    discipline_filter = cmd.get("filterDiscipline", "")

    # Route previewBBoxes — buildingId passed via guid field (Java server whitelist)
    if scheme == "previewBBoxes":
        building_id = cmd.get("guid", target)
        print(f"[WebUI Sync] previewBBoxes via schemeName, building={building_id}")
        _preview_bboxes_command({"buildingId": building_id})
        return

    # Route loadOutput — outputDbPath passed via guid field (Java server whitelist)
    if scheme == "loadOutput":
        db_path = cmd.get("guid", "")
        print(f"[WebUI Sync] loadOutput via schemeName, path={db_path}")
        _load_output_command({"outputDbPath": db_path, "objectName": target})
        return

    color_str = cmd.get("color", "")

    if scheme == "reset":
        # Reset all to default gray
        for obj in bpy.data.objects:
            if obj.type == 'MESH':
                obj.color = (0.75, 0.75, 0.75, 1.0)
        _force_viewport_refresh()
        return

    if scheme == "discipline":
        # Apply discipline-based coloring
        if discipline_filter:
            color = DISCIPLINE_COLORS.get(discipline_filter, (0.5, 0.5, 0.5, 1.0))
            for obj in bpy.data.objects:
                if obj.type == 'MESH':
                    obj_disc = obj.get('discipline', obj.get('Discipline', ''))
                    if obj_disc == discipline_filter:
                        obj.color = color
        else:
            # Apply all discipline colors
            for obj in bpy.data.objects:
                if obj.type == 'MESH':
                    obj_disc = obj.get('discipline', obj.get('Discipline', ''))
                    if obj_disc in DISCIPLINE_COLORS:
                        obj.color = DISCIPLINE_COLORS[obj_disc]
        _force_viewport_refresh()
        return

    # Apply specific color to selected or named object
    if color_str:
        try:
            # Parse color — could be hex string or JSON array
            if color_str.startswith('#'):
                r = int(color_str[1:3], 16) / 255
                g = int(color_str[3:5], 16) / 255
                b = int(color_str[5:7], 16) / 255
                color = (r, g, b, 1.0)
            elif color_str.startswith('"#'):
                hex_str = color_str.strip('"')
                r = int(hex_str[1:3], 16) / 255
                g = int(hex_str[3:5], 16) / 255
                b = int(hex_str[5:7], 16) / 255
                color = (r, g, b, 1.0)
            else:
                color = tuple(json.loads(color_str))
                if len(color) == 3:
                    color = color + (1.0,)
        except (ValueError, json.JSONDecodeError):
            color = (0.5, 0.5, 0.5, 1.0)

        if target == '*':
            for obj in bpy.data.objects:
                if obj.type == 'MESH':
                    obj.color = color
        else:
            obj = bpy.data.objects.get(target)
            if obj and obj.type == 'MESH':
                obj.color = color

        _force_viewport_refresh()


def _load_output_command(cmd):
    """Load compiled output database into Bonsai viewport."""
    db_path = cmd.get("outputDbPath", "")
    element_count = cmd.get("elementCount", 0)

    if not db_path:
        print("[WebUI Sync] loadOutput: no outputDbPath")
        return

    # Resolve relative path to absolute
    import os
    if not os.path.isabs(db_path):
        # Relative to bim-compiler project root
        project_root = os.path.expanduser("~/bim-compiler")
        db_path = os.path.join(project_root, db_path)

    if not os.path.exists(db_path):
        print(f"[WebUI Sync] loadOutput: file not found: {db_path}")
        return

    print(f"[WebUI Sync] Loading compiled output: {db_path} ({element_count} elements)")

    try:
        # Set the federation database path
        props = bpy.context.scene.BIMFederationProperties
        props.federation_database_path = db_path

        # Try fast bbox preview first (2-second load)
        try:
            from . import fast_bbox_loader
            fast_bbox_loader.load_bboxes_from_db(db_path)
            print(f"[WebUI Sync] BBox preview loaded: {element_count} elements")
        except Exception as bbox_err:
            print(f"[WebUI Sync] BBox loader unavailable ({bbox_err}), trying operator...")
            # Fall back to operator
            try:
                bpy.ops.bim.preview_federation_viewport()
            except Exception:
                try:
                    bpy.ops.bim.load_full_federation_viewport_gi()
                except Exception as op_err:
                    print(f"[WebUI Sync] Load operator failed: {op_err}")

        _force_viewport_refresh()

    except Exception as e:
        print(f"[WebUI Sync] loadOutput failed: {e}")


def _force_viewport_refresh():
    """Force Blender to update the 3D viewport after color changes."""
    try:
        for area in bpy.context.screen.areas:
            if area.type == 'VIEW_3D':
                for space in area.spaces:
                    if space.type == 'VIEW_3D':
                        space.shading.color_type = 'OBJECT'
                area.tag_redraw()
    except Exception:
        pass


# Registration
classes = (
    BIM_OT_start_webui_sync,
    BIM_OT_stop_webui_sync,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    # Stop timer if running
    global _sync_active
    _sync_active = False
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
