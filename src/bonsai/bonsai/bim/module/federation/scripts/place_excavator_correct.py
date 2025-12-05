#!/usr/bin/env python3
"""
Append excavator correctly - try collection method
"""
import bpy

RIVER_SCENE = "/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/databases/river_blosm_gi_full.blend"
EXCAVATOR_BLEND = "/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/models/excavator_fixed_orientation.blend"
OUTPUT_FILE = "/home/red1/Projects/IfcOpenShell/WORK_DIR/RIVER/databases/river_blosm_gi_full.blend"  # Overwrite the original
TARGET_LOCATION = (21.96, 6.54, 0.00)

def main():
    # Load river scene
    bpy.ops.wm.open_mainfile(filepath=RIVER_SCENE)

    # Ensure Federated collection exists
    if "Federated" not in bpy.data.collections:
        federated = bpy.data.collections.new("Federated")
        bpy.context.scene.collection.children.link(federated)
    else:
        federated = bpy.data.collections["Federated"]

    # Use bpy.ops.wm.append instead - this handles units correctly
    bpy.ops.wm.append(
        filepath=EXCAVATOR_BLEND + "/Object/Excavator_CAT336",
        directory=EXCAVATOR_BLEND + "/Object/",
        filename="Excavator_CAT336"
    )

    # Get the appended object
    excavator_obj = bpy.data.objects.get("Excavator_CAT336")

    if excavator_obj:
        # Move to Federated collection
        for coll in excavator_obj.users_collection:
            coll.objects.unlink(excavator_obj)
        federated.objects.link(excavator_obj)

        # Set location only
        excavator_obj.location = TARGET_LOCATION

        print(f"✓ Placed {excavator_obj.name} at {TARGET_LOCATION}")
        print(f"  Rotation: {excavator_obj.rotation_euler}")
        print(f"  Scale: {excavator_obj.scale}")
        print(f"  Dimensions: {excavator_obj.dimensions}")

    # Save
    bpy.ops.wm.save_as_mainfile(filepath=OUTPUT_FILE)
    print(f"\n✓ Saved to: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
