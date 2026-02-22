import sys, os, json, zipfile

argv = sys.argv
idx = argv.index("--") if "--" in argv else len(argv)
src = argv[idx + 1]

import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)

# Enable the addon properly
bpy.ops.preferences.addon_enable(module="bambu_3mf_io")

# Import
bpy.ops.import_scene.bambu_3mf(filepath=src)

# Check stored metadata
for col in bpy.data.collections:
    ms_p = col.get("bambu_ms_plates", "")
    ms_a = col.get("bambu_ms_assemble", "")
    print(f"Collection '{col.name}':")
    print(f"  bambu_ms_plates present: {bool(ms_p)}")
    print(f"  bambu_ms_assemble present: {bool(ms_a)}")
    if ms_p:
        plates = json.loads(ms_p)
        print(f"  Plate count: {len(plates)}")
        for i, p in enumerate(plates):
            print(f"  Plate {i}: {len(p.get('instances',[]))} instances")

# Export
out_path = os.path.join(os.path.dirname(src), "test_roundtrip_out.3mf")
bpy.ops.export_scene.bambu_3mf(filepath=out_path)

# Verify
print("\n=== Exported model_settings.config ===")
with zipfile.ZipFile(out_path) as zf:
    ms = zf.read("Metadata/model_settings.config").decode("utf-8")
    print(ms)
    
    has_plate = "<plate>" in ms
    has_assemble = "<assemble>" in ms
    has_model_instance = "<model_instance>" in ms
    plate_count_ms = ms.count("<plate>")
    
    si = zf.read("Metadata/slice_info.config").decode("utf-8")
    plate_count_si = si.count("<plate>")
    
    main = zf.read("3D/3dmodel.model").decode("utf-8")
    has_app = '<metadata name="Application">' in main
    has_bambu_ns = 'xmlns:BambuStudio' in main

    print(f"\nmodel_settings: {plate_count_ms} plates, has_model_instance={has_model_instance}, has_assemble={has_assemble}")
    print(f"slice_info: {plate_count_si} plates")
    print(f"Main model: Application={has_app}, BambuStudio_ns={has_bambu_ns}")

    all_ok = has_plate and has_model_instance and has_assemble and has_app and has_bambu_ns and plate_count_ms == 2
    print(f"\n{'ALL CHECKS PASSED' if all_ok else 'SOME CHECKS FAILED'}")

os.remove(out_path)
