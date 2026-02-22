"""
Scene construction: turn parsed 3MF data into Blender objects.

Creates a collection per file, Empty parents per assembly object,
and child mesh objects per component/part.
"""

import os
import bpy

from .transform import parse_3mf_transform, scale_vertices
from .materials import create_filament_materials, assign_material
from .metadata import (
    store_assembly_metadata,
    store_part_metadata,
    store_project_settings,
    store_plate_info,
    store_model_settings_extras,
)


def build_scene(context, data, import_materials=True, apply_build_transforms=True, scale=0.001):
    """Build the full Blender scene from parsed 3MF data.

    Parameters
    ----------
    context : bpy.types.Context
    data : dict returned by parser.parse_3mf
    import_materials : bool – create materials from filament data
    apply_build_transforms : bool – apply build-plate placement
    scale : float – mm-to-m factor (default 0.001)
    """
    filename = os.path.basename(data.get("_filepath", "Bambu3MF"))
    col_name = os.path.splitext(filename)[0] or "Bambu3MF"

    # Deduplicate collection names
    collection = bpy.data.collections.new(col_name)
    context.scene.collection.children.link(collection)

    # Materials
    materials_map = {}
    if import_materials and data["filaments"]:
        materials_map = create_filament_materials(data["filaments"])

    # Store project-wide metadata
    store_project_settings(
        collection,
        data.get("project_settings", ""),
        data.get("metadata", {}),
    )
    store_plate_info(collection, data.get("plates", []), data.get("filaments", {}))
    store_model_settings_extras(
        collection,
        data.get("ms_plates", []),
        data.get("ms_assemble", []),
    )

    # Build a lookup: object_id -> build_item
    build_map = {bi["objectid"]: bi for bi in data["build_items"]}

    # Model settings lookup
    model_settings = data.get("model_settings", {})

    # Create objects following the build order
    for bi in data["build_items"]:
        obj_id = bi["objectid"]
        obj_data = data["objects"].get(obj_id)
        if obj_data is None:
            continue

        obj_name = obj_data.get("name") or f"Object_{obj_id}"
        obj_extruder = obj_data.get("extruder", 1)

        # Parent empty
        empty = bpy.data.objects.new(obj_name, None)
        empty.empty_display_type = "PLAIN_AXES"
        empty.empty_display_size = 0.02
        collection.objects.link(empty)

        if apply_build_transforms and bi.get("transform"):
            empty.matrix_world = parse_3mf_transform(bi["transform"], scale)

        store_assembly_metadata(empty, obj_data, bi)

        # Look up plate for this object
        _assign_plate_id(empty, obj_name, data.get("plates", []))

        # Resolve parts from model_settings
        ms_entry = model_settings.get(obj_id, {})
        parts_info = ms_entry.get("parts", {})

        # Create child meshes for each component
        for comp in obj_data["components"]:
            mesh_key = (comp["path"], comp["objectid"])
            mesh_data = data["meshes"].get(mesh_key)
            if mesh_data is None:
                continue

            # Determine part name
            part_info = parts_info.get(comp["objectid"])
            part_name = (part_info["name"] if part_info and part_info.get("name")
                         else f"Part_{comp['objectid']}")

            # Build mesh
            mesh_obj = _create_mesh_object(
                part_name, mesh_data, comp, empty, collection, scale
            )

            # Extruder: part-level override > object-level default
            part_extruder = (part_info.get("extruder")
                             if part_info and part_info.get("extruder") is not None
                             else obj_extruder)
            mesh_obj["bambu_extruder"] = part_extruder

            store_part_metadata(mesh_obj, comp, part_info)

            if import_materials:
                assign_material(mesh_obj, part_extruder, materials_map)

    return collection


def _create_mesh_object(name, mesh_data, component, parent, collection, scale):
    """Create a single Blender mesh object from parsed vertex/face data."""
    mesh = bpy.data.meshes.new(name)

    verts = scale_vertices(mesh_data["vertices"], scale)
    faces = mesh_data["triangles"]

    mesh.from_pydata(verts, [], faces)
    mesh.update()

    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.parent = parent

    # Component transform (already applies scale to translation only)
    if component.get("transform"):
        obj.matrix_local = parse_3mf_transform(component["transform"], scale)

    return obj


def _assign_plate_id(empty, obj_name, plates):
    """Match an assembly object to its plate by name."""
    for plate in plates:
        for po in plate.get("objects", []):
            if po.get("name", "") == obj_name:
                empty["bambu_plate_id"] = plate.get("index", 0)
                return
