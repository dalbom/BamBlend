# BamBlend

A Blender addon for lossless import/export of Bambu Studio 3MF files.

BamBlend preserves all Bambu Studio metadata during the round-trip — plate assignments, filament mappings, per-part settings, project configuration — so your edited models open back in Bambu Studio without the "not from Bambu Lab" warning.

## Features

- **Import** Bambu Studio `.3mf` files with full metadata preservation
- **Export** back to `.3mf` that Bambu Studio recognizes as its own
- **From-scratch export** — models created entirely in Blender get proper plate assignments and part entries
- **Multi-plate support** — plate layouts, object-to-plate mapping, and assemble transforms are round-tripped
- **Stale cleanup** — deleted objects are automatically removed from plate references on export
- **Auto version detection** — reads the installed Bambu Studio version (Windows registry/PE, macOS plist) so the Application tag always matches
- **STL export** with mm-scaling for direct use in slicers
- **N-panel sidebar** (View3D > Sidebar > Bambu) showing per-object metadata

## Requirements

- Blender 4.0 or later

## Installation

### From release (recommended)
1. Download `BamBlend-v1.0.0.zip` from the [latest release](https://github.com/dalbom/BamBlend/releases/latest)
2. In Blender: **Edit > Preferences > Add-ons > Install from Disk**
3. Select the downloaded zip
4. Enable **BamBlend – Bambu Studio 3MF Import/Export**

### From source
1. Clone this repository
2. Rename the cloned folder to `bamblend`
3. Copy it into your Blender addons directory (e.g. `%APPDATA%\Blender Foundation\Blender\4.x\scripts\addons\`)
4. In Blender, go to **Edit > Preferences > Add-ons** and enable **BamBlend – Bambu Studio 3MF Import/Export**

## Usage

### Import
**File > Import > Bambu 3MF (.3mf)**

Options:
- Import Materials — create Blender materials from filament/color data
- Apply Build Plate Transforms — position objects as arranged on the build plate

### Export
**File > Export > Bambu 3MF (.3mf)**

Options:
- Selection Only — export only selected objects

### STL Export
**File > Export > Bambu STL (.stl)**

Options:
- Units (mm/m) — automatic scaling
- Merge All — combine all meshes into a single STL

## Project Structure

```
__init__.py          # Addon registration (bl_info)
import_bambu_3mf.py  # Import operator
export_bambu_3mf.py  # Export operator
export_stl.py        # STL export operator
core/
  parser.py          # 3MF ZIP/XML parser
  builder.py         # Blender scene builder
  serializer.py      # 3MF ZIP/XML writer
  metadata.py        # Metadata handling
  transform.py       # Matrix/transform utilities
  version.py         # Bambu Studio version detection
  materials.py       # Material creation
ui/
  panels.py          # N-panel sidebar
```

## License

[GPL v3](LICENSE)
