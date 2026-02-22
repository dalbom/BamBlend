"""
Export Blender scene data back to a Bambu Studio 3MF file.

Collects mesh objects, rebuilds the XML structure with proper namespaces,
and writes everything into an OPC-compliant ZIP package.
"""

import json
import uuid
import xml.etree.ElementTree as ET
import zipfile

import bmesh
import bpy

from .transform import matrix_to_3mf_transform, M_TO_MM
from .version import get_bambu_version_string

# Register namespace prefixes so ElementTree serializes them correctly
ET.register_namespace("", "http://schemas.microsoft.com/3dmanufacturing/core/2015/02")
ET.register_namespace("p", "http://schemas.microsoft.com/3dmanufacturing/production/2015/06")
ET.register_namespace("BambuStudio", "http://schemas.bambulab.com/package/2021")

NS_CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
NS_PROD = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
NS_BAMBU = "http://schemas.bambulab.com/package/2021"


def _qn(ns, tag):
    return f"{{{ns}}}{tag}"


def export_3mf(context, filepath, selection_only=False):
    """Write the current scene (or selection) as a Bambu Studio 3MF file."""
    groups = _collect_export_groups(context, selection_only)
    if not groups:
        return {"CANCELLED"}

    # Retrieve round-trip metadata from the Bambu collection
    collection = _find_bambu_collection(context)
    project_settings = ""
    model_metadata = {}
    plates_json = []
    filaments_json = {}
    ms_plates_json = []
    ms_assemble_json = []
    if collection:
        ref = collection.get("bambu_project_settings_ref", "")
        if ref and ref in bpy.data.texts:
            project_settings = bpy.data.texts[ref].as_string()
        try:
            model_metadata = json.loads(collection.get("bambu_model_metadata", "{}"))
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            plates_json = json.loads(collection.get("bambu_plates", "[]"))
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            filaments_json = json.loads(collection.get("bambu_filaments", "{}"))
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            ms_plates_json = json.loads(collection.get("bambu_ms_plates", "[]"))
        except (json.JSONDecodeError, TypeError):
            pass
        try:
            ms_assemble_json = json.loads(collection.get("bambu_ms_assemble", "[]"))
        except (json.JSONDecodeError, TypeError):
            pass

    # Build the 3MF ZIP
    with zipfile.ZipFile(filepath, "w", zipfile.ZIP_DEFLATED) as zf:
        sub_model_refs = []
        sub_model_xmls = {}
        assembly_objects = []
        build_items = []

        # Use a global ID counter so all part IDs across all sub-models
        # are unique (as required by Bambu Studio's model_settings.config)
        next_part_id = 1

        for group in groups:
            parent = group["parent"]
            children = group["children"]

            # Use original assembly ID if available, else allocate one
            assembly_id = parent.get("bambu_object_id")
            if assembly_id is None:
                assembly_id = next_part_id
                next_part_id += 1

            sub_path = f"/3D/Objects/object_{assembly_id}.model"
            sub_model_refs.append(sub_path)

            # Build sub-model: use original part IDs from metadata
            sub_xml, component_list, id_map = _build_sub_model(children)
            sub_model_xmls[sub_path] = sub_xml

            # Assembly object entry
            obj_uuid = parent.get("bambu_uuid", str(uuid.uuid4()))
            components = []
            for comp in component_list:
                components.append({
                    "path": sub_path,
                    "objectid": comp["id"],
                    "uuid": comp.get("uuid", str(uuid.uuid4())),
                    "transform": comp["transform"],
                })
            assembly_objects.append({
                "id": assembly_id,
                "uuid": obj_uuid,
                "components": components,
            })

            # Build item
            bi_transform = parent.get("bambu_build_transform", "")
            if not bi_transform:
                bi_transform = matrix_to_3mf_transform(parent.matrix_world)
            build_items.append({
                "objectid": assembly_id,
                "uuid": str(uuid.uuid4()),
                "transform": bi_transform,
                "printable": parent.get("bambu_printable", True),
            })

        # ---- Clean stale references & generate defaults ----
        valid_object_ids = {str(asm["id"]) for asm in assembly_objects}
        valid_names = {group["parent"].name for group in groups}

        ms_plates_json = _clean_stale_plates(
            ms_plates_json, valid_object_ids
        )
        ms_assemble_json = _clean_stale_assemble(
            ms_assemble_json, valid_object_ids
        )
        plates_json = _clean_stale_slice_plates(
            plates_json, valid_names
        )

        if not ms_plates_json:
            ms_plates_json, ms_assemble_json = _generate_default_plates(
                groups, assembly_objects
            )
        if not plates_json:
            plates_json = _generate_default_slice_plates(
                groups, assembly_objects
            )

        # ---- Write all files into the ZIP ----
        main_xml = _build_main_model(assembly_objects, build_items, model_metadata)

        zf.writestr("[Content_Types].xml", _content_types_xml())
        zf.writestr("_rels/.rels", _root_rels_xml())
        zf.writestr("3D/3dmodel.model", main_xml)
        zf.writestr("3D/_rels/3dmodel.model.rels", _model_rels_xml(sub_model_refs))

        for path, xml_str in sub_model_xmls.items():
            zf.writestr(path.lstrip("/"), xml_str)

        # Model settings (IDs aligned with assembly model)
        model_settings_xml = _build_model_settings(
            groups, assembly_objects, ms_plates_json, ms_assemble_json
        )
        if model_settings_xml:
            zf.writestr("Metadata/model_settings.config", model_settings_xml)

        # Slice info (plates + filaments)
        slice_info_xml = _build_slice_info(groups, plates_json, filaments_json)
        if slice_info_xml:
            zf.writestr("Metadata/slice_info.config", slice_info_xml)

        # Project settings (round-trip)
        if project_settings:
            zf.writestr("Metadata/project_settings.config", project_settings)

    return {"FINISHED"}


# ------------------------------------------------------------------ #
# Object collection
# ------------------------------------------------------------------ #

def _collect_export_groups(context, selection_only):
    """Return a list of {parent: Empty, children: [mesh_objects]}."""
    groups = []
    source = context.selected_objects if selection_only else context.scene.objects

    empties = [o for o in source if o.type == "EMPTY" and "bambu_object_id" in o]
    if empties:
        for empty in empties:
            children = [c for c in empty.children if c.type == "MESH"]
            if children:
                groups.append({"parent": empty, "children": children})
        return groups

    # Fallback: each mesh is a standalone assembly
    meshes = [o for o in source if o.type == "MESH"]
    for m in meshes:
        groups.append({"parent": m, "children": [m]})
    return groups


def _find_bambu_collection(context):
    for col in bpy.data.collections:
        if "bambu_project_settings_ref" in col or "bambu_model_metadata" in col:
            return col
    return None


# ------------------------------------------------------------------ #
# Sub-model XML (mesh data)
# ------------------------------------------------------------------ #

def _build_sub_model(mesh_objects):
    """Build the XML string for a sub-model file containing mesh data.

    Uses original part IDs from bambu_part_id metadata when available.
    Returns (xml_string, component_list, id_map).
    """
    components = []
    depsgraph = bpy.context.evaluated_depsgraph_get()

    # Allocate IDs: prefer original part IDs, else sequential
    fallback_id = 1
    used_ids = set()
    for obj in mesh_objects:
        pid = obj.get("bambu_part_id")
        if pid is not None:
            used_ids.add(int(pid))

    # Build XML by hand as a string for precise control over namespaces
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<model unit="millimeter" xml:lang="en-US"'
        ' xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"'
        ' xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06"'
        ' xmlns:BambuStudio="http://schemas.bambulab.com/package/2021"'
        ' requiredextensions="p">',
        ' <metadata name="BambuStudio:3mfVersion">1</metadata>',
        ' <resources>',
    ]

    for obj in mesh_objects:
        # Determine the part ID
        part_id = obj.get("bambu_part_id")
        if part_id is None:
            while fallback_id in used_ids:
                fallback_id += 1
            part_id = fallback_id
            used_ids.add(fallback_id)
            fallback_id += 1
        else:
            part_id = int(part_id)

        obj_uuid = obj.get("bambu_part_uuid", str(uuid.uuid4()))

        # Extract mesh (triangulated, in mm)
        eval_obj = obj.evaluated_get(depsgraph)
        temp_mesh = eval_obj.to_mesh()

        bm = bmesh.new()
        bm.from_mesh(temp_mesh)
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        bm.to_mesh(temp_mesh)
        bm.free()

        lines.append(f'  <object id="{part_id}" p:UUID="{obj_uuid}" type="model">')
        lines.append('   <mesh>')
        lines.append('    <vertices>')
        for v in temp_mesh.vertices:
            lines.append(
                f'     <vertex x="{v.co.x * M_TO_MM:.8g}"'
                f' y="{v.co.y * M_TO_MM:.8g}"'
                f' z="{v.co.z * M_TO_MM:.8g}" />'
            )
        lines.append('    </vertices>')
        lines.append('    <triangles>')
        for poly in temp_mesh.polygons:
            lines.append(
                f'     <triangle v1="{poly.vertices[0]}"'
                f' v2="{poly.vertices[1]}"'
                f' v3="{poly.vertices[2]}" />'
            )
        lines.append('    </triangles>')
        lines.append('   </mesh>')
        lines.append('  </object>')

        eval_obj.to_mesh_clear()

        comp_transform = obj.get("bambu_component_transform", "")
        if not comp_transform:
            comp_transform = matrix_to_3mf_transform(obj.matrix_local)

        components.append({
            "id": part_id,
            "uuid": obj_uuid,
            "transform": comp_transform,
        })

    lines.append(' </resources>')
    lines.append('</model>')

    return "\n".join(lines), components, {}


# ------------------------------------------------------------------ #
# Main model XML (assembly root)
# ------------------------------------------------------------------ #

def _build_main_model(assembly_objects, build_items, model_metadata=None):
    """Build the 3D/3dmodel.model XML string with full Bambu metadata."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<model unit="millimeter" xml:lang="en-US"'
        ' xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"'
        ' xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06"'
        ' xmlns:BambuStudio="http://schemas.bambulab.com/package/2021"'
        ' requiredextensions="p">',
    ]

    # ---- Metadata block ----
    # Application tag is critical: Bambu Studio checks this to recognize its own files
    app = get_bambu_version_string()
    if model_metadata:
        app = model_metadata.get("Application", app)
    lines.append(f' <metadata name="Application">{_esc(app)}</metadata>')
    lines.append(' <metadata name="BambuStudio:3mfVersion">1</metadata>')

    # Round-trip all stored metadata (except the two we already wrote)
    _written = {"Application", "BambuStudio:3mfVersion"}
    if model_metadata:
        for key, val in model_metadata.items():
            if key not in _written and val:
                lines.append(f' <metadata name="{_esc(key)}">{_esc(val)}</metadata>')

    # ---- Resources (assembly objects) ----
    lines.append(' <resources>')
    for asm in assembly_objects:
        lines.append(
            f'  <object id="{asm["id"]}" p:UUID="{asm["uuid"]}" type="model">'
        )
        lines.append('   <components>')
        for comp in asm["components"]:
            lines.append(
                f'    <component p:path="{comp["path"]}"'
                f' objectid="{comp["objectid"]}"'
                f' p:UUID="{comp["uuid"]}"'
                f' transform="{comp["transform"]}" />'
            )
        lines.append('   </components>')
        lines.append('  </object>')
    lines.append(' </resources>')

    # ---- Build ----
    build_uuid = str(uuid.uuid4())
    lines.append(f' <build p:UUID="{build_uuid}">')
    for bi in build_items:
        printable = "1" if bi["printable"] else "0"
        lines.append(
            f'  <item objectid="{bi["objectid"]}"'
            f' p:UUID="{bi["uuid"]}"'
            f' transform="{bi["transform"]}"'
            f' printable="{printable}" />'
        )
    lines.append(' </build>')
    lines.append('</model>')

    return "\n".join(lines)


# ------------------------------------------------------------------ #
# Model settings (Metadata/model_settings.config)
# ------------------------------------------------------------------ #

def _build_model_settings(groups, assembly_objects, ms_plates=None, ms_assemble=None):
    """Reconstruct model_settings.config using IDs that match the assembly model.

    Includes <plate> sections (object-to-plate mapping) and <assemble> section
    from round-tripped data, which are required for Bambu Studio multi-plate support.
    """
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<config>']

    for group, asm in zip(groups, assembly_objects):
        parent = group["parent"]
        asm_id = asm["id"]  # Use the assembly-model ID, not the stored one

        lines.append(f'  <object id="{asm_id}">')
        lines.append(f'    <metadata key="name" value="{_esc(parent.name)}" />')
        lines.append(
            f'    <metadata key="extruder"'
            f' value="{parent.get("bambu_extruder", 1)}" />'
        )

        # Parts: IDs must match the objectids used in the sub-model file.
        # zip() is safe because _build_sub_model(children) builds components
        # in the same order as the children list.
        for child, comp in zip(group["children"], asm["components"]):
            part_id = comp["objectid"]
            subtype = child.get("bambu_subtype", "normal_part")
            part_name = child.get("bambu_part_name", child.name)
            extruder = child.get("bambu_extruder")

            lines.append(f'    <part id="{part_id}" subtype="{_esc(subtype)}">')
            lines.append(f'      <metadata key="name" value="{_esc(part_name)}" />')
            if extruder is not None:
                lines.append(
                    f'      <metadata key="extruder" value="{extruder}" />'
                )
            lines.append('    </part>')

        lines.append('  </object>')

    # Plate sections: object-to-plate mapping (critical for multi-plate support)
    if ms_plates:
        for plate in ms_plates:
            lines.append('  <plate>')
            for key, val in plate.get("metadata", {}).items():
                lines.append(
                    f'    <metadata key="{_esc(key)}" value="{_esc(str(val))}" />'
                )
            for instance in plate.get("instances", []):
                lines.append('    <model_instance>')
                for key, val in instance.items():
                    lines.append(
                        f'      <metadata key="{_esc(key)}"'
                        f' value="{_esc(str(val))}" />'
                    )
                lines.append('    </model_instance>')
            lines.append('  </plate>')

    # Assemble section
    if ms_assemble:
        lines.append('  <assemble>')
        for item in ms_assemble:
            lines.append(
                f'   <assemble_item'
                f' object_id="{_esc(item.get("object_id", ""))}"'
                f' instance_id="{_esc(item.get("instance_id", ""))}"'
                f' transform="{_esc(item.get("transform", ""))}"'
                f' offset="{_esc(item.get("offset", ""))}" />'
            )
        lines.append('  </assemble>')

    lines.append('</config>')
    return "\n".join(lines)



# ------------------------------------------------------------------ #
# Default plate generation (from-scratch exports)
# ------------------------------------------------------------------ #

def _generate_default_plates(groups, assembly_objects):
    """Generate model_settings plate + assemble data for from-scratch exports.

    Assigns all objects to plate 1 with sequential identify_ids.
    Returns (ms_plates, ms_assemble) in the same format as round-trip data.
    """
    instances = []
    assemble_items = []
    for idx, (group, asm) in enumerate(zip(groups, assembly_objects)):
        instances.append({
            "object_id": str(asm["id"]),
            "instance_id": "0",
            "identify_id": str(idx),
        })
        assemble_items.append({
            "object_id": str(asm["id"]),
            "instance_id": "0",
            "transform": "",
            "offset": "",
        })

    ms_plates = [
        {
            "metadata": {"index": "1", "locked": "false"},
            "instances": instances,
        }
    ]
    return ms_plates, assemble_items


def _generate_default_slice_plates(groups, assembly_objects):
    """Generate slice_info plate data for from-scratch exports.

    Creates a single plate with <object> entries for each assembly.
    Returns plates list in the same format as parsed slice_info.
    """
    objects = []
    for idx, (group, asm) in enumerate(zip(groups, assembly_objects)):
        objects.append({
            "name": group["parent"].name,
            "identify_id": str(idx),
            "skipped": False,
        })
    return [{"metadata": {"index": "1"}, "objects": objects, "filaments": []}]


# ------------------------------------------------------------------ #
# Stale reference cleanup (deleted objects)
# ------------------------------------------------------------------ #

def _clean_stale_plates(ms_plates, valid_object_ids):
    """Remove model_instance entries referencing deleted objects.

    Drops empty plates and renumbers remaining ones.
    """
    if not ms_plates:
        return ms_plates

    cleaned = []
    for plate in ms_plates:
        kept = [
            inst for inst in plate.get("instances", [])
            if inst.get("object_id", "") in valid_object_ids
        ]
        if kept:
            new_plate = dict(plate)
            new_plate["instances"] = kept
            cleaned.append(new_plate)

    # Renumber plates sequentially
    for i, plate in enumerate(cleaned):
        meta = dict(plate.get("metadata", {}))
        meta["index"] = str(i + 1)
        plate["metadata"] = meta

    return cleaned


def _clean_stale_assemble(ms_assemble, valid_object_ids):
    """Remove assemble_item entries referencing deleted objects."""
    if not ms_assemble:
        return ms_assemble
    return [
        item for item in ms_assemble
        if item.get("object_id", "") in valid_object_ids
    ]


def _clean_stale_slice_plates(plates_json, valid_names):
    """Remove <object> entries from slice_info plates referencing deleted objects.

    Drops empty plates and renumbers remaining ones.
    """
    if not plates_json:
        return plates_json

    cleaned = []
    for plate in plates_json:
        kept = [
            obj for obj in plate.get("objects", [])
            if obj.get("name", "") in valid_names
        ]
        if kept:
            new_plate = dict(plate)
            new_plate["objects"] = kept
            cleaned.append(new_plate)

    # Renumber plates sequentially
    for i, plate in enumerate(cleaned):
        meta = dict(plate.get("metadata", {}))
        meta["index"] = str(i + 1)
        plate["metadata"] = meta

    return cleaned


# ------------------------------------------------------------------ #
# Slice info (Metadata/slice_info.config) — plate & filament defs
# ------------------------------------------------------------------ #

def _build_slice_info(groups, plates_json, filaments_json):
    """Reconstruct slice_info.config for plate layout and filament definitions."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<config>']

    # Header
    # Extract raw version number from "BambuStudio-XX.XX.XX.XX"
    ver_string = get_bambu_version_string()
    raw_ver = ver_string.split("-", 1)[1] if "-" in ver_string else ver_string
    lines.append('  <header>')
    lines.append('    <header_item key="X-BBL-Client-Type" value="slicer" />')
    lines.append(
        f'    <header_item key="X-BBL-Client-Version" value="{raw_ver}" />'
    )
    lines.append('  </header>')

    if plates_json:
        # Round-trip stored plate definitions
        for plate in plates_json:
            lines.append('  <plate>')
            meta = plate.get("metadata", {})
            for key, val in meta.items():
                lines.append(
                    f'    <metadata key="{_esc(key)}" value="{_esc(str(val))}" />'
                )
            for obj_entry in plate.get("objects", []):
                name = _esc(obj_entry.get("name", ""))
                ident = _esc(str(obj_entry.get("identify_id", "")))
                skipped = "true" if obj_entry.get("skipped") else "false"
                lines.append(
                    f'    <object identify_id="{ident}" name="{name}"'
                    f' skipped="{skipped}" />'
                )
            for fil in plate.get("filaments", []):
                fid = fil.get("id", "")
                ftype = _esc(fil.get("type", ""))
                fcolor = _esc(fil.get("color", ""))
                tray = _esc(fil.get("tray_info_idx", ""))
                used_m = fil.get("used_m", "")
                used_g = fil.get("used_g", "")
                lines.append(
                    f'    <filament id="{fid}" tray_info_idx="{tray}"'
                    f' type="{ftype}" color="{fcolor}"'
                    f' used_m="{used_m}" used_g="{used_g}" />'
                )
            lines.append('  </plate>')
    else:
        # Fallback: create a single plate with all objects
        lines.append('  <plate>')
        lines.append('    <metadata key="index" value="1" />')
        for group in groups:
            parent = group["parent"]
            lines.append(
                f'    <object identify_id="0" name="{_esc(parent.name)}"'
                f' skipped="false" />'
            )
        # Write filament entries from stored data
        for fid_str, info in filaments_json.items():
            fid = info.get("id", fid_str)
            ftype = _esc(info.get("type", "PLA"))
            fcolor = _esc(info.get("color", "#808080"))
            tray = _esc(info.get("tray_info_idx", ""))
            lines.append(
                f'    <filament id="{fid}" tray_info_idx="{tray}"'
                f' type="{ftype}" color="{fcolor}" used_m="" used_g="" />'
            )
        lines.append('  </plate>')

    lines.append('</config>')
    return "\n".join(lines)


# ------------------------------------------------------------------ #
# OPC boilerplate
# ------------------------------------------------------------------ #

def _content_types_xml():
    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        ' <Default Extension="rels"'
        ' ContentType="application/vnd.openxmlformats-package.relationships+xml" />',
        ' <Default Extension="model"'
        ' ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml" />',
        ' <Default Extension="png" ContentType="image/png" />',
        ' <Default Extension="config" ContentType="text/xml" />',
        '</Types>',
    ])


def _root_rels_xml():
    return "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
        ' <Relationship Target="/3D/3dmodel.model" Id="rel0"'
        ' Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel" />',
        '</Relationships>',
    ])


def _model_rels_xml(sub_model_paths):
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">',
    ]
    for i, path in enumerate(sub_model_paths):
        lines.append(
            f' <Relationship Target="{path}" Id="rel{i + 1}"'
            f' Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel" />'
        )
    lines.append("</Relationships>")
    return "\n".join(lines)


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _esc(text):
    """Escape XML special characters in attribute/text values."""
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
