import sys, os, json, zipfile, importlib, importlib.util

argv = sys.argv
idx = argv.index("--") if "--" in argv else len(argv)
src = argv[idx + 1]
addon_dir = os.path.dirname(src)

# Force-load the dev version of parser.py using importlib
def load_module(name, filepath):
    spec = importlib.util.spec_from_file_location(name, filepath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

parser = load_module("parser", os.path.join(addon_dir, "bambu_3mf_io", "core", "parser.py"))
print(f"Parser loaded from: {parser.__file__}")
print(f"Has _parse_model_settings_plates: {hasattr(parser, '_parse_model_settings_plates')}")

data = parser.parse_3mf(src)
print(f"ms_plates: {len(data.get('ms_plates', []))}")
print(f"ms_assemble: {len(data.get('ms_assemble', []))}")
if data.get('ms_plates'):
    print(f"First plate: {json.dumps(data['ms_plates'][0], indent=2)}")
if data.get('ms_assemble'):
    print(f"Assemble items: {json.dumps(data['ms_assemble'], indent=2)}")
