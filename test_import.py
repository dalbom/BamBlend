"""
Test script for the Bambu 3MF import addon.

Usage:
    blender --background --python test_import.py -- C:\\dev\\3mf\\FlowerClock.3mf

Or to run from inside Blender's scripting workspace, set FILEPATH below.
"""

import sys
import os

# ------------------------------------------------------------------ #
# Bootstrap: ensure the addon package is importable
# ------------------------------------------------------------------ #

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import bpy

# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

_failures = []
_passes = 0


def check(condition, message):
    global _passes
    if condition:
        _passes += 1
        print(f"  PASS: {message}")
    else:
        _failures.append(message)
        print(f"  FAIL: {message}")


def report():
    print()
    print("=" * 60)
    print(f"Results: {_passes} passed, {len(_failures)} failed")
    if _failures:
        print()
        for f in _failures:
            print(f"  FAIL: {f}")
        print()
    print("=" * 60)
    return len(_failures) == 0


# ------------------------------------------------------------------ #
# Test: pure-Python parser (no Blender dependency)
# ------------------------------------------------------------------ #

def test_parser(filepath):
    """Verify the parser extracts the correct structure from FlowerClock.3mf."""
    print("\n--- Parser Tests ---")

    from bambu_3mf_io.core.parser import parse_3mf
    data = parse_3mf(filepath)

    # Metadata
    check(data["metadata"].get("Title") == "Flower Clock",
          f"Title = '{data['metadata'].get('Title')}'")
    check(data["metadata"].get("Designer") == "Jack Kelke",
          f"Designer = '{data['metadata'].get('Designer')}'")
    check("BambuStudio-01.10" in data["metadata"].get("Application", ""),
          f"Application = '{data['metadata'].get('Application')}'")

    # Assembly objects
    check(len(data["objects"]) == 3,
          f"Assembly objects: {len(data['objects'])} (expected 3)")

    # Object names from model_settings enrichment
    names = {o["name"] for o in data["objects"].values()}
    expected_names = {"FlowerClock_B", "FlowerClock_A_B", "FlowerClock_A_A"}
    check(names == expected_names,
          f"Object names: {names}")

    # Build items
    check(len(data["build_items"]) == 3,
          f"Build items: {len(data['build_items'])} (expected 3)")

    # Mesh counts per sub-model
    # object_3.model: 1 mesh, 10090 verts, 20180 tris
    # object_4.model: 27 meshes, 7986 verts, 15972 tris
    # object_5.model: 3 meshes, 576 verts, 1140 tris
    total_verts = sum(len(m["vertices"]) for m in data["meshes"].values())
    total_tris = sum(len(m["triangles"]) for m in data["meshes"].values())

    check(total_verts == 18652,
          f"Total vertices: {total_verts} (expected 18652)")
    check(total_tris == 37292,
          f"Total triangles: {total_tris} (expected 37292)")

    # Per-file vertex counts
    verts_by_file = {}
    for (path, _), mesh in data["meshes"].items():
        verts_by_file[path] = verts_by_file.get(path, 0) + len(mesh["vertices"])

    check(verts_by_file.get("/3D/Objects/object_3.model") == 10090,
          f"object_3 vertices: {verts_by_file.get('/3D/Objects/object_3.model')}")
    check(verts_by_file.get("/3D/Objects/object_4.model") == 7986,
          f"object_4 vertices: {verts_by_file.get('/3D/Objects/object_4.model')}")
    check(verts_by_file.get("/3D/Objects/object_5.model") == 576,
          f"object_5 vertices: {verts_by_file.get('/3D/Objects/object_5.model')}")

    # Component counts
    total_components = sum(len(o["components"]) for o in data["objects"].values())
    check(total_components == 31,
          f"Total components: {total_components} (expected 31)")

    # Filaments
    check(len(data["filaments"]) >= 2,
          f"Filament slots: {len(data['filaments'])} (expected >= 2)")

    # Check specific filament colors
    fil4 = data["filaments"].get(4, {})
    check(fil4.get("color") == "#C12E1F",
          f"Filament 4 color: {fil4.get('color')} (expected #C12E1F)")
    check(fil4.get("type") == "PLA",
          f"Filament 4 type: {fil4.get('type')} (expected PLA)")

    # Plates
    check(len(data["plates"]) == 2,
          f"Plates: {len(data['plates'])} (expected 2)")

    # Project settings (should be non-empty JSON)
    check(len(data["project_settings"]) > 100,
          f"Project settings length: {len(data['project_settings'])}")

    # Model settings - per-part extruder overrides
    ms_34 = data["model_settings"].get(34, {})
    parts_34 = ms_34.get("parts", {})
    ext2_parts = [p for p in parts_34.values() if p.get("extruder") == 2]
    ext1_parts = [p for p in parts_34.values()
                  if p.get("extruder") == 1 or p.get("extruder") is None]
    check(len(ext2_parts) == 19,
          f"Object 34 parts with extruder=2: {len(ext2_parts)} (expected 19)")

    return data


# ------------------------------------------------------------------ #
# Test: Blender scene construction
# ------------------------------------------------------------------ #

def test_blender_import(filepath):
    """Import into Blender and verify the resulting scene."""
    print("\n--- Blender Import Tests ---")

    # Clear scene
    bpy.ops.wm.read_factory_settings(use_empty=True)

    # Register addon
    import bambu_3mf_io
    bambu_3mf_io.register()

    # Import
    result = bpy.ops.import_scene.bambu_3mf(filepath=filepath)
    check(result == {"FINISHED"}, f"Import operator result: {result}")

    # Check empties (assembly parents)
    empties = [o for o in bpy.data.objects
               if o.type == "EMPTY" and "bambu_object_id" in o]
    check(len(empties) == 3,
          f"Assembly empties: {len(empties)} (expected 3)")

    empty_names = {e.name for e in empties}
    expected_names = {"FlowerClock_B", "FlowerClock_A_B", "FlowerClock_A_A"}
    check(empty_names == expected_names,
          f"Empty names: {empty_names}")

    # Check total mesh objects: 1 + 3 + 27 = 31
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    check(len(meshes) == 31,
          f"Mesh objects: {len(meshes)} (expected 31)")

    # Vertex counts (should match source data exactly)
    total_verts = sum(len(o.data.vertices) for o in meshes)
    check(total_verts == 18652,
          f"Total Blender vertices: {total_verts} (expected 18652)")

    # Triangle counts (all faces should be triangles)
    total_faces = sum(len(o.data.polygons) for o in meshes)
    check(total_faces == 37292,
          f"Total Blender faces: {total_faces} (expected 37292)")

    # Per-assembly vertex counts
    for empty in empties:
        children = [c for c in empty.children if c.type == "MESH"]
        child_verts = sum(len(c.data.vertices) for c in children)

        if empty.name == "FlowerClock_B":
            check(child_verts == 10090,
                  f"FlowerClock_B vertices: {child_verts} (expected 10090)")
            check(len(children) == 1,
                  f"FlowerClock_B parts: {len(children)} (expected 1)")

        elif empty.name == "FlowerClock_A_B":
            check(child_verts == 576,
                  f"FlowerClock_A_B vertices: {child_verts} (expected 576)")
            check(len(children) == 3,
                  f"FlowerClock_A_B parts: {len(children)} (expected 3)")

        elif empty.name == "FlowerClock_A_A":
            check(child_verts == 7986,
                  f"FlowerClock_A_A vertices: {child_verts} (expected 7986)")
            check(len(children) == 27,
                  f"FlowerClock_A_A parts: {len(children)} (expected 27)")

    # Materials
    filament_mats = [m for m in bpy.data.materials if "bambu_filament_id" in m]
    check(len(filament_mats) >= 2,
          f"Filament materials: {len(filament_mats)} (expected >= 2)")

    # Check that red PLA material exists
    red_mat = next((m for m in filament_mats if m.get("bambu_filament_color") == "#C12E1F"), None)
    check(red_mat is not None,
          f"Red PLA material exists: {red_mat is not None}")

    # Per-part extruder metadata on FlowerClock_A_A children
    aa_empty = next((e for e in empties if e.name == "FlowerClock_A_A"), None)
    if aa_empty:
        children_ext2 = [c for c in aa_empty.children
                         if c.type == "MESH" and c.get("bambu_extruder") == 2]
        children_ext1 = [c for c in aa_empty.children
                         if c.type == "MESH" and c.get("bambu_extruder") == 1]
        check(len(children_ext2) == 19,
              f"A_A parts extruder=2: {len(children_ext2)} (expected 19)")
        check(len(children_ext1) == 8,
              f"A_A parts extruder=1: {len(children_ext1)} (expected 8)")

    # Metadata on empties
    for empty in empties:
        check("bambu_uuid" in empty,
              f"{empty.name} has bambu_uuid")
        check("bambu_build_transform" in empty or "bambu_printable" in empty,
              f"{empty.name} has build metadata")

    # Collection metadata
    bambu_cols = [c for c in bpy.data.collections if "bambu_model_metadata" in c]
    check(len(bambu_cols) >= 1,
          f"Collections with Bambu metadata: {len(bambu_cols)}")

    # Cleanup
    bambu_3mf_io.unregister()


# ------------------------------------------------------------------ #
# Main
# ------------------------------------------------------------------ #

def main():
    # Get filepath from command-line args (after --)
    argv = sys.argv
    if "--" in argv:
        filepath = argv[argv.index("--") + 1]
    else:
        filepath = os.path.join(SCRIPT_DIR, "FlowerClock.3mf")

    if not os.path.isfile(filepath):
        print(f"ERROR: File not found: {filepath}")
        sys.exit(1)

    print(f"Testing with: {filepath}")
    print(f"Blender version: {bpy.app.version_string}")

    # Run parser tests (no Blender scene needed)
    test_parser(filepath)

    # Run Blender import tests
    test_blender_import(filepath)

    # Report
    success = report()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
