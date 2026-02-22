import sys, os, json
argv = sys.argv
idx = argv.index("--") if "--" in argv else len(argv)
src = argv[idx + 1]
sys.path.insert(0, os.path.dirname(src))

import bpy
bpy.ops.wm.read_factory_settings(use_empty=True)

from bambu_3mf_io.core.parser import parse_3mf
from bambu_3mf_io.core.builder import build_scene

data = parse_3mf(src)
data["_filepath"] = src
build_scene(bpy.context, data)

print(f"ms_plates from parser: {len(data.get('ms_plates', []))}")
print(f"ms_assemble from parser: {len(data.get('ms_assemble', []))}")

# Check what's stored on collections
for col in bpy.data.collections:
    print(f"\nCollection: {col.name}")
    for key in col.keys():
        val = col[key]
        if isinstance(val, str) and len(val) > 200:
            print(f"  {key}: (len={len(val)}) {val[:100]}...")
        else:
            print(f"  {key}: {val}")

# Now check if _find_bambu_collection finds it
from bambu_3mf_io.core.serializer import _find_bambu_collection
found = _find_bambu_collection(bpy.context)
print(f"\n_find_bambu_collection result: {found}")
if found:
    ms_p = found.get("bambu_ms_plates", "MISSING")
    ms_a = found.get("bambu_ms_assemble", "MISSING")
    print(f"bambu_ms_plates: {ms_p[:200] if isinstance(ms_p, str) else ms_p}")
    print(f"bambu_ms_assemble: {ms_a[:200] if isinstance(ms_a, str) else ms_a}")
