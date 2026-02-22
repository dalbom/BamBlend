"""
Bambu Studio 3MF Import/Export addon for Blender 4.x

Provides:
  - File > Import > Bambu 3MF (.3mf)
  - File > Export > Bambu 3MF (.3mf)
  - File > Export > Bambu STL (.stl)
  - N-panel sidebar (View3D > Sidebar > Bambu) showing object metadata
"""

bl_info = {
    "name": "BamBlend – Bambu Studio 3MF Import/Export",
    "author": "BamBlend Contributors",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "File > Import/Export, View3D > Sidebar > Bambu",
    "description": "Import and export Bambu Studio 3MF files with full metadata preservation",
    "category": "Import-Export",
}

import bpy

from .import_bambu_3mf import IMPORT_OT_bambu_3mf, menu_func_import
from .export_bambu_3mf import EXPORT_OT_bambu_3mf
from .export_bambu_3mf import menu_func_export as menu_func_export_3mf
from .export_stl import EXPORT_OT_bambu_stl
from .export_stl import menu_func_export as menu_func_export_stl
from .ui.panels import VIEW3D_PT_bambu_metadata

_classes = (
    IMPORT_OT_bambu_3mf,
    EXPORT_OT_bambu_3mf,
    EXPORT_OT_bambu_stl,
    VIEW3D_PT_bambu_metadata,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(menu_func_import)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export_3mf)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export_stl)


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export_stl)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export_3mf)
    bpy.types.TOPBAR_MT_file_import.remove(menu_func_import)
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
