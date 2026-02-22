"""
Read / write Bambu-specific metadata as Blender custom properties.

Assembly-level metadata lives on the parent Empty.
Part-level metadata lives on each child mesh object.
Project-wide data (large JSON) is stored in bpy.data.texts.
"""

import json
import bpy


def store_assembly_metadata(obj, object_data, build_item):
    """Store assembly-level Bambu metadata on an Empty object."""
    obj["bambu_object_id"] = object_data["id"]
    obj["bambu_uuid"] = object_data.get("uuid", "")
    obj["bambu_extruder"] = object_data.get("extruder", 1)
    if build_item:
        obj["bambu_build_transform"] = build_item.get("transform", "")
        obj["bambu_printable"] = build_item.get("printable", True)


def store_part_metadata(obj, component, part_info):
    """Store part-level Bambu metadata on a mesh object."""
    obj["bambu_part_id"] = component.get("objectid", 0)
    obj["bambu_part_uuid"] = component.get("uuid", "")
    obj["bambu_source_path"] = component.get("path", "")
    obj["bambu_source_objectid"] = component.get("objectid", 0)
    obj["bambu_component_transform"] = component.get("transform", "")
    if part_info:
        obj["bambu_part_name"] = part_info.get("name", obj.name)
        obj["bambu_subtype"] = part_info.get("subtype", "normal_part")
        obj["bambu_face_count"] = part_info.get("face_count", 0)
        ext = part_info.get("extruder")
        if ext is not None:
            obj["bambu_extruder"] = ext
    else:
        obj["bambu_part_name"] = obj.name


def store_project_settings(collection, project_json_str, model_metadata):
    """Persist large project settings as a Text datablock, metadata on collection."""
    if project_json_str:
        text_name = f"bambu_project_settings_{collection.name}"
        if text_name in bpy.data.texts:
            text_block = bpy.data.texts[text_name]
            text_block.clear()
        else:
            text_block = bpy.data.texts.new(text_name)
        text_block.write(project_json_str)
        collection["bambu_project_settings_ref"] = text_name

    if model_metadata:
        collection["bambu_model_metadata"] = json.dumps(model_metadata, ensure_ascii=False)


def read_project_settings(collection):
    """Retrieve the project settings JSON from the referenced Text datablock."""
    ref = collection.get("bambu_project_settings_ref", "")
    if ref and ref in bpy.data.texts:
        return bpy.data.texts[ref].as_string()
    return ""


def store_plate_info(collection, plates, filaments):
    """Store plate and filament info on the collection."""
    collection["bambu_plates"] = json.dumps(plates, ensure_ascii=False)
    collection["bambu_filaments"] = json.dumps(filaments, ensure_ascii=False)


def store_model_settings_extras(collection, ms_plates, ms_assemble):
    """Store model_settings.config <plate> and <assemble> sections for round-trip."""
    if ms_plates:
        collection["bambu_ms_plates"] = json.dumps(ms_plates, ensure_ascii=False)
    if ms_assemble:
        collection["bambu_ms_assemble"] = json.dumps(ms_assemble, ensure_ascii=False)
