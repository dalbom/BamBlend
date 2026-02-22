"""
Filament / material management.

Creates Blender materials from Bambu filament definitions and assigns
them to mesh objects based on extruder slot IDs.
"""

import bpy


def hex_to_linear_rgb(hex_color):
    """Convert a hex color string like '#C12E1F' to linear RGB (0-1).

    Blender's Principled BSDF expects linear-space values.
    """
    h = hex_color.lstrip("#")
    if len(h) == 8:          # ARGB format used by some Bambu files
        h = h[2:]            # drop alpha prefix
    r, g, b = int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0
    # sRGB -> linear
    def srgb_to_linear(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b)


def create_filament_materials(filaments):
    """Create Blender materials from a dict of {slot_id: FilamentInfo}.

    Returns a dict {slot_id: bpy.types.Material}.
    """
    materials = {}
    for slot_id, info in filaments.items():
        mat_name = f"Filament_{slot_id}_{info['type']}_{info['color']}"
        mat = bpy.data.materials.new(name=mat_name)
        mat.use_nodes = True

        r, g, b = hex_to_linear_rgb(info["color"])
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)

        # Store filament metadata on the material for round-trip
        mat["bambu_filament_id"] = slot_id
        mat["bambu_filament_type"] = info["type"]
        mat["bambu_filament_color"] = info["color"]
        mat["bambu_tray_info_idx"] = info.get("tray_info_idx", "")

        materials[slot_id] = mat
    return materials


def create_default_material(extruder_id):
    """Fallback material when no filament info is available."""
    mat_name = f"Extruder_{extruder_id}"
    mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    mat["bambu_filament_id"] = extruder_id
    return mat


def assign_material(obj, extruder_id, materials_map):
    """Assign the filament material for *extruder_id* to *obj*."""
    mat = materials_map.get(extruder_id)
    if mat is None:
        mat = create_default_material(extruder_id)
        materials_map[extruder_id] = mat
    if mat.name not in [m.name for m in obj.data.materials if m]:
        obj.data.materials.append(mat)
