"""Import FlowerClock.3mf, export, and verify the output has plate data."""
import sys
import zipfile
import os
import importlib.util

argv = sys.argv
idx = argv.index("--") if "--" in argv else len(argv)
src = argv[idx + 1] if idx + 1 < len(argv) else None
if not src:
    print("ERROR: provide source 3mf path after --")
    sys.exit(1)

addon_dir = os.path.dirname(src)
sys.path.insert(0, addon_dir)

import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)

# Import using direct module calls
from bambu_3mf_io.core.parser import parse_3mf
from bambu_3mf_io.core.builder import build_scene
from bambu_3mf_io.core.serializer import export_3mf

data = parse_3mf(src)
data["_filepath"] = src
build_scene(bpy.context, data)

print(f"Imported: {len(data['objects'])} objects, {len(data['build_items'])} build items")
print(f"ms_plates parsed: {len(data.get('ms_plates', []))}")
print(f"ms_assemble parsed: {len(data.get('ms_assemble', []))}")

# Check stored metadata on collection
for col in bpy.data.collections:
    ms_p = col.get("bambu_ms_plates", "")
    ms_a = col.get("bambu_ms_assemble", "")
    if ms_p:
        print(f"Collection '{col.name}' has bambu_ms_plates: {ms_p[:200]}...")
    if ms_a:
        print(f"Collection '{col.name}' has bambu_ms_assemble: {ms_a[:200]}...")

# Export
out_path = os.path.join(addon_dir, "test_roundtrip_out.3mf")
result = export_3mf(bpy.context, out_path)
print(f"\nExport result: {result}")

# Verify
print("\n=== Verifying exported 3MF ===")
with zipfile.ZipFile(out_path) as zf:
    ms = zf.read("Metadata/model_settings.config").decode("utf-8")
    print(f"\n--- model_settings.config ---")
    print(ms)
    
    has_plate = "<plate>" in ms
    has_assemble = "<assemble>" in ms
    has_model_instance = "<model_instance>" in ms
    
    print(f"\nHas <plate> sections: {has_plate}")
    print(f"Has <model_instance>: {has_model_instance}")
    print(f"Has <assemble>: {has_assemble}")
    
    si = zf.read("Metadata/slice_info.config").decode("utf-8")
    plate_count = si.count("<plate>")
    print(f"\nslice_info.config plate count: {plate_count}")
    
    main = zf.read("3D/3dmodel.model").decode("utf-8")
    has_app = '<metadata name="Application">' in main
    has_bambu_ns = 'xmlns:BambuStudio' in main
    print(f"Main model has Application: {has_app}")
    print(f"Main model has BambuStudio ns: {has_bambu_ns}")

    all_ok = has_plate and has_model_instance and has_assemble and has_app and has_bambu_ns
    print(f"\n{'ALL CHECKS PASSED' if all_ok else 'SOME CHECKS FAILED'}")

os.remove(out_path)
