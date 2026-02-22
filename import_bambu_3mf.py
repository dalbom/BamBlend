"""Import operator for Bambu Studio 3MF files."""

import bpy
from bpy.props import BoolProperty, FloatProperty, StringProperty
from bpy_extras.io_utils import ImportHelper

from .core.parser import parse_3mf
from .core.builder import build_scene


class IMPORT_OT_bambu_3mf(bpy.types.Operator, ImportHelper):
    """Import a Bambu Studio 3MF file"""

    bl_idname = "import_scene.bambu_3mf"
    bl_label = "Import Bambu 3MF"
    bl_options = {"REGISTER", "UNDO"}

    filename_ext = ".3mf"
    filter_glob: StringProperty(default="*.3mf", options={"HIDDEN"})  # type: ignore

    import_materials: BoolProperty(
        name="Import Materials",
        description="Create Blender materials from filament/color data",
        default=True,
    )  # type: ignore

    apply_build_transforms: BoolProperty(
        name="Apply Build Plate Transforms",
        description="Position objects as arranged on the build plate",
        default=True,
    )  # type: ignore

    scale: FloatProperty(
        name="Scale",
        description="Import scale (0.001 = mm to meters)",
        default=0.001,
        min=0.0001,
        max=10.0,
    )  # type: ignore

    def execute(self, context):
        data = parse_3mf(self.filepath)
        data["_filepath"] = self.filepath
        build_scene(
            context,
            data,
            import_materials=self.import_materials,
            apply_build_transforms=self.apply_build_transforms,
            scale=self.scale,
        )
        obj_count = len(data.get("build_items", []))
        mesh_count = sum(
            len(o["components"]) for o in data.get("objects", {}).values()
        )
        self.report(
            {"INFO"},
            f"Imported {obj_count} objects ({mesh_count} mesh parts) from Bambu 3MF",
        )
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "import_materials")
        layout.prop(self, "apply_build_transforms")
        layout.prop(self, "scale")


def menu_func_import(self, context):
    self.layout.operator(
        IMPORT_OT_bambu_3mf.bl_idname, text="Bambu 3MF (.3mf)"
    )
