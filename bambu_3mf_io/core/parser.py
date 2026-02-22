"""
3MF ZIP / XML parsing engine.

Reads the OPC package, parses the assembly root, resolves sub-model
mesh files, and extracts Bambu-specific metadata from Metadata/*.
"""

import json
import xml.etree.ElementTree as ET
import zipfile

# ------------------------------------------------------------------ #
# XML namespace helpers
# ------------------------------------------------------------------ #

NS_CORE = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
NS_PROD = "http://schemas.microsoft.com/3dmanufacturing/production/2015/06"
NS_BAMBU = "http://schemas.bambulab.com/package/2021"

_NS_MAP = {"core": NS_CORE, "p": NS_PROD, "bambu": NS_BAMBU}


def _qn(prefix, tag):
    """Build a fully-qualified XML tag name: {uri}tag."""
    return f"{{{_NS_MAP[prefix]}}}{tag}"


def _attr(prefix, name):
    """Build a fully-qualified XML attribute name."""
    return f"{{{_NS_MAP[prefix]}}}{name}"


# ------------------------------------------------------------------ #
# Public API
# ------------------------------------------------------------------ #

def parse_3mf(filepath):
    """Parse a Bambu Studio 3MF file and return a structured dict.

    Returns
    -------
    dict with keys:
        metadata        – model-level metadata (title, designer, …)
        objects         – {obj_id: {id, uuid, extruder, name, components: [...]}}
        build_items     – [{objectid, uuid, transform, printable}, …]
        meshes          – {(path, objectid): {vertices: [...], triangles: [...]}}
        filaments       – {slot_id: {id, type, color, tray_info_idx}}
        plates          – [{index, objects: [...], filaments: [...], …}]
        model_settings  – per-object/part settings from model_settings.config
        project_settings – raw JSON string from project_settings.config
    """
    with zipfile.ZipFile(filepath, "r") as zf:
        names = zf.namelist()

        # 1. Parse assembly root
        model_xml = _read_zip(zf, "3D/3dmodel.model")
        metadata, objects, build_items = _parse_assembly(model_xml)

        # 2. Collect unique sub-model paths, parse meshes
        sub_paths = set()
        for obj in objects.values():
            for comp in obj["components"]:
                sub_paths.add(comp["path"])

        meshes = {}
        for path in sub_paths:
            zip_path = path.lstrip("/")
            xml_bytes = _read_zip(zf, zip_path)
            if xml_bytes is None:
                continue
            for obj_id, mesh in _parse_sub_model(xml_bytes):
                meshes[(path, obj_id)] = mesh

        # 3. Parse Bambu metadata files
        ms_xml = _read_zip(zf, "Metadata/model_settings.config")
        model_settings = _parse_model_settings(ms_xml)
        ms_plates, ms_assemble = _parse_model_settings_plates(ms_xml)
        filaments, plates = _parse_slice_info(
            _read_zip(zf, "Metadata/slice_info.config")
        )
        project_settings = _read_zip_str(zf, "Metadata/project_settings.config")

        # 4. Enrich objects with names / extruder from model_settings
        _enrich_objects(objects, model_settings)

    return {
        "metadata": metadata,
        "objects": objects,
        "build_items": build_items,
        "meshes": meshes,
        "filaments": filaments,
        "plates": plates,
        "model_settings": model_settings,
        "ms_plates": ms_plates,
        "ms_assemble": ms_assemble,
        "project_settings": project_settings or "",
    }


# ------------------------------------------------------------------ #
# Assembly root (3D/3dmodel.model)
# ------------------------------------------------------------------ #

def _parse_assembly(xml_bytes):
    root = ET.fromstring(xml_bytes)

    # Metadata
    metadata = {}
    for m in root.findall(_qn("core", "metadata")):
        name = m.get("name", "")
        metadata[name] = (m.text or "").strip()

    # Objects  (assembly-level; mesh data lives in sub-model files)
    objects = {}
    resources = root.find(_qn("core", "resources"))
    if resources is not None:
        for obj_el in resources.findall(_qn("core", "object")):
            obj_id = int(obj_el.get("id"))
            obj = {
                "id": obj_id,
                "uuid": obj_el.get(_attr("p", "UUID"), ""),
                "name": "",
                "extruder": 1,
                "components": [],
            }
            comps_el = obj_el.find(_qn("core", "components"))
            if comps_el is not None:
                for c in comps_el.findall(_qn("core", "component")):
                    obj["components"].append({
                        "path": c.get(_attr("p", "path"), ""),
                        "objectid": int(c.get("objectid", 0)),
                        "uuid": c.get(_attr("p", "UUID"), ""),
                        "transform": c.get("transform", ""),
                    })
            objects[obj_id] = obj

    # Build items
    build_items = []
    build = root.find(_qn("core", "build"))
    if build is not None:
        for item in build.findall(_qn("core", "item")):
            build_items.append({
                "objectid": int(item.get("objectid", 0)),
                "uuid": item.get(_attr("p", "UUID"), ""),
                "transform": item.get("transform", ""),
                "printable": item.get("printable", "1") == "1",
            })

    return metadata, objects, build_items


# ------------------------------------------------------------------ #
# Sub-model mesh files (3D/Objects/object_N.model)
# ------------------------------------------------------------------ #

def _parse_sub_model(xml_bytes):
    """Yield (object_id, mesh_dict) for every <object> with mesh data."""
    root = ET.fromstring(xml_bytes)
    resources = root.find(_qn("core", "resources"))
    if resources is None:
        return

    for obj_el in resources.findall(_qn("core", "object")):
        obj_id = int(obj_el.get("id"))
        mesh_el = obj_el.find(_qn("core", "mesh"))
        if mesh_el is None:
            continue

        vertices = []
        verts_el = mesh_el.find(_qn("core", "vertices"))
        if verts_el is not None:
            for v in verts_el.findall(_qn("core", "vertex")):
                vertices.append((
                    float(v.get("x")),
                    float(v.get("y")),
                    float(v.get("z")),
                ))

        triangles = []
        tris_el = mesh_el.find(_qn("core", "triangles"))
        if tris_el is not None:
            for t in tris_el.findall(_qn("core", "triangle")):
                triangles.append((
                    int(t.get("v1")),
                    int(t.get("v2")),
                    int(t.get("v3")),
                ))

        yield obj_id, {"vertices": vertices, "triangles": triangles}


# ------------------------------------------------------------------ #
# Metadata/model_settings.config
# ------------------------------------------------------------------ #

def _parse_model_settings(xml_bytes):
    """Return {object_id: {name, extruder, parts: [{id, name, extruder, …}]}}."""
    if xml_bytes is None:
        return {}
    root = ET.fromstring(xml_bytes)
    result = {}
    for obj_el in root.findall("object"):
        obj_id = int(obj_el.get("id"))
        entry = {"name": "", "extruder": 1, "parts": {}}
        for meta in obj_el.findall("metadata"):
            key = meta.get("key")
            val = meta.get("value")
            if key == "name":
                entry["name"] = val or ""
            elif key == "extruder":
                entry["extruder"] = int(val) if val else 1
        for part_el in obj_el.findall("part"):
            part_id = int(part_el.get("id"))
            part = {
                "id": part_id,
                "subtype": part_el.get("subtype", "normal_part"),
                "name": "",
                "extruder": None,
                "face_count": 0,
            }
            for meta in part_el.findall("metadata"):
                key = meta.get("key")
                val = meta.get("value")
                if key == "name":
                    part["name"] = val or ""
                elif key == "extruder":
                    part["extruder"] = int(val) if val else None
            ms = part_el.find("mesh_stat")
            if ms is not None:
                part["face_count"] = int(ms.get("face_count", 0))
            entry["parts"][part_id] = part
        result[obj_id] = entry
    return result


def _parse_model_settings_plates(xml_bytes):
    """Extract <plate> and <assemble> sections from model_settings.config.

    Returns (plates_list, assemble_list) for round-trip storage.
    """
    if xml_bytes is None:
        return [], []
    root = ET.fromstring(xml_bytes)

    plates = []
    for plate_el in root.findall("plate"):
        plate = {"metadata": {}, "instances": []}
        for meta in plate_el.findall("metadata"):
            plate["metadata"][meta.get("key", "")] = meta.get("value", "")
        for mi_el in plate_el.findall("model_instance"):
            instance = {}
            for meta in mi_el.findall("metadata"):
                instance[meta.get("key", "")] = meta.get("value", "")
            plate["instances"].append(instance)
        plates.append(plate)

    assemble = []
    asm_el = root.find("assemble")
    if asm_el is not None:
        for item in asm_el.findall("assemble_item"):
            assemble.append({
                "object_id": item.get("object_id", ""),
                "instance_id": item.get("instance_id", ""),
                "transform": item.get("transform", ""),
                "offset": item.get("offset", ""),
            })

    return plates, assemble


# ------------------------------------------------------------------ #
# Metadata/slice_info.config
# ------------------------------------------------------------------ #

def _parse_slice_info(xml_bytes):
    """Return (filaments_dict, plates_list)."""
    filaments = {}
    plates = []
    if xml_bytes is None:
        return filaments, plates

    root = ET.fromstring(xml_bytes)
    for plate_el in root.findall("plate"):
        plate = {"index": 0, "objects": [], "filaments": [], "metadata": {}}
        for meta in plate_el.findall("metadata"):
            key = meta.get("key")
            val = meta.get("value")
            plate["metadata"][key] = val
            if key == "index":
                plate["index"] = int(val)

        for obj_el in plate_el.findall("object"):
            plate["objects"].append({
                "identify_id": obj_el.get("identify_id", ""),
                "name": obj_el.get("name", ""),
                "skipped": obj_el.get("skipped", "false") == "true",
            })

        for fil_el in plate_el.findall("filament"):
            fid = int(fil_el.get("id"))
            info = {
                "id": fid,
                "type": fil_el.get("type", ""),
                "color": fil_el.get("color", "#808080"),
                "tray_info_idx": fil_el.get("tray_info_idx", ""),
                "used_m": fil_el.get("used_m", ""),
                "used_g": fil_el.get("used_g", ""),
            }
            plate["filaments"].append(info)
            # Global filament dict (union across plates)
            if fid not in filaments:
                filaments[fid] = {
                    "id": fid,
                    "type": info["type"],
                    "color": info["color"],
                    "tray_info_idx": info["tray_info_idx"],
                }

        plates.append(plate)
    return filaments, plates


# ------------------------------------------------------------------ #
# Enrichment: merge model_settings into objects
# ------------------------------------------------------------------ #

def _enrich_objects(objects, model_settings):
    """Copy name / extruder from model_settings into the assembly objects dict."""
    for obj_id, obj in objects.items():
        ms = model_settings.get(obj_id)
        if ms:
            obj["name"] = ms["name"]
            obj["extruder"] = ms["extruder"]


# ------------------------------------------------------------------ #
# ZIP helpers
# ------------------------------------------------------------------ #

def _read_zip(zf, path):
    """Read raw bytes from *path* inside the ZIP, or None if missing."""
    try:
        return zf.read(path)
    except KeyError:
        return None


def _read_zip_str(zf, path):
    """Read a UTF-8 string from *path* inside the ZIP, or None."""
    raw = _read_zip(zf, path)
    return raw.decode("utf-8") if raw else None
