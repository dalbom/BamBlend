"""N-panel sidebar showing Bambu 3MF metadata for the selected object."""

import json
import bpy


class VIEW3D_PT_bambu_metadata(bpy.types.Panel):
    bl_label = "Bambu 3MF"
    bl_idname = "VIEW3D_PT_bambu_metadata"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Bambu"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object

        if obj is None:
            layout.label(text="No object selected")
            return

        has_bambu = False

        # --- Assembly-level info (Empty parent) ---
        if "bambu_object_id" in obj:
            has_bambu = True
            box = layout.box()
            box.label(text="Assembly Object", icon="EMPTY_AXIS")
            col = box.column(align=True)
            col.label(text=f"Name: {obj.name}")
            col.label(text=f"Object ID: {obj['bambu_object_id']}")
            col.label(text=f"Extruder: {obj.get('bambu_extruder', 'N/A')}")
            col.label(text=f"Plate: {obj.get('bambu_plate_id', 'N/A')}")
            col.label(text=f"Printable: {obj.get('bambu_printable', True)}")

            child_count = sum(1 for c in obj.children if c.type == "MESH")
            col.label(text=f"Parts: {child_count}")

        # --- Part-level info (mesh child) ---
        if "bambu_part_id" in obj:
            has_bambu = True
            box = layout.box()
            box.label(text="Part", icon="MESH_DATA")
            col = box.column(align=True)
            col.label(text=f"Part: {obj.get('bambu_part_name', obj.name)}")
            col.label(text=f"Part ID: {obj['bambu_part_id']}")
            col.label(text=f"Extruder: {obj.get('bambu_extruder', 'N/A')}")
            col.label(text=f"Subtype: {obj.get('bambu_subtype', 'N/A')}")
            col.label(text=f"Faces: {obj.get('bambu_face_count', 'N/A')}")
            col.label(text=f"Source: {obj.get('bambu_source_path', 'N/A')}")

        # --- Material / filament info ---
        if obj.type == "MESH" and obj.data.materials:
            for mat in obj.data.materials:
                if mat and "bambu_filament_id" in mat:
                    has_bambu = True
                    box = layout.box()
                    box.label(text="Filament", icon="MATERIAL")
                    col = box.column(align=True)
                    col.label(text=f"Slot: {mat['bambu_filament_id']}")
                    col.label(text=f"Type: {mat.get('bambu_filament_type', '?')}")
                    col.label(text=f"Color: {mat.get('bambu_filament_color', '?')}")

        # --- Collection-level info ---
        bambu_col = _find_bambu_collection(obj)
        if bambu_col and "bambu_plates" in bambu_col:
            has_bambu = True
            box = layout.box()
            box.label(text="Project", icon="FILE_3D")
            try:
                plates = json.loads(bambu_col["bambu_plates"])
                box.label(text=f"Plates: {len(plates)}")
            except (json.JSONDecodeError, TypeError):
                pass
            try:
                filaments = json.loads(bambu_col["bambu_filaments"])
                for fid, info in filaments.items():
                    box.label(text=f"  Slot {fid}: {info['type']} {info['color']}")
            except (json.JSONDecodeError, TypeError, KeyError):
                pass

        if not has_bambu:
            layout.label(text="No Bambu metadata", icon="INFO")


def _find_bambu_collection(obj):
    """Walk up from obj to find a collection with Bambu metadata."""
    for col in bpy.data.collections:
        if "bambu_plates" in col:
            # Check if obj is somewhere in this collection
            if _obj_in_collection(obj, col):
                return col
    return None


def _obj_in_collection(obj, col):
    if obj.name in col.objects:
        return True
    for child_col in col.children:
        if _obj_in_collection(obj, child_col):
            return True
    return False
