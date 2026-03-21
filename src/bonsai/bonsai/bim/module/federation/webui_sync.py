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
        # Check if timer already running
        if hasattr(bpy.app, '_webui_sync_active') and bpy.app._webui_sync_active:
            self.report({'INFO'}, "Web UI sync already running")
            # Still open browser if requested
            if self.open_browser:
                _open_browser()
            return {'FINISHED'}

        bpy.app._webui_sync_active = True
        bpy.app._webui_sync_last_selection = set()
        bpy.app._webui_sync_last_name = ""

        bpy.app.timers.register(_sync_timer, first_interval=1.0)

        if self.open_browser:
            _open_browser()

        self.report({'INFO'}, "Web UI sync started — two-way Bonsai ↔ browser link active")
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
        bpy.app._webui_sync_active = False
        self.report({'INFO'}, "Web UI sync stopped")
        return {'FINISHED'}


def _sync_timer():
    """Timer callback — runs every 0.5s. Checks selection + polls commands."""
    if not getattr(bpy.app, '_webui_sync_active', False):
        return None  # unregister timer

    try:
        _check_selection()
        _poll_commands()
    except Exception as e:
        print(f"[WebUI Sync] Error: {e}")

    return 0.5  # re-run in 0.5s


def _check_selection():
    """Detect viewport selection change and push to WebUI."""
    context = bpy.context
    if not hasattr(context, 'selected_objects'):
        return

    active = context.active_object
    current_name = active.name if active else ""

    if current_name == getattr(bpy.app, '_webui_sync_last_name', ''):
        return  # no change

    bpy.app._webui_sync_last_name = current_name

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

    for cmd in result["commands"]:
        command = cmd.get("command", "")
        if command == "applyScheme":
            _apply_scheme_command(cmd)
        elif command == "loadOutput":
            _load_output_command(cmd)


def _apply_scheme_command(cmd):
    """Apply a color scheme command received from Web UI."""
    scheme = cmd.get("schemeName", "")
    target = cmd.get("objectName", "")
    discipline_filter = cmd.get("filterDiscipline", "")
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
    bpy.app._webui_sync_active = False
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
