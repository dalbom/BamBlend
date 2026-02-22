"""Export operator for Bambu Studio 3MF files."""

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy_extras.io_utils import ExportHelper

from .core.serializer import export_3mf


class EXPORT_OT_bambu_3mf(bpy.types.Operator, ExportHelper):
    """Export scene as a Bambu Studio 3MF file"""

    bl_idname = "export_scene.bambu_3mf"
    bl_label = "Export Bambu 3MF"
    bl_options = {"REGISTER"}

    filename_ext = ".3mf"
    filter_glob: StringProperty(default="*.3mf", options={"HIDDEN"})  # type: ignore

    selection_only: BoolProperty(
        name="Selection Only",
        description="Export only selected objects",
        default=False,
    )  # type: ignore

    def execute(self, context):
        result = export_3mf(context, self.filepath, selection_only=self.selection_only)
        if result == {"CANCELLED"}:
            self.report({"WARNING"}, "No exportable objects found")
            return {"CANCELLED"}
        self.report({"INFO"}, f"Exported Bambu 3MF to {self.filepath}")
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "selection_only")


def menu_func_export(self, context):
    self.layout.operator(
        EXPORT_OT_bambu_3mf.bl_idname, text="Bambu 3MF (.3mf)"
    )
