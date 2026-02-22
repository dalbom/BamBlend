"""STL export operator with unit-aware scaling.

Exports individual mesh objects or all meshes merged into one STL.
Writes binary STL for compactness.
"""

import struct

import bmesh
import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy_extras.io_utils import ExportHelper

from .core.transform import M_TO_MM


class EXPORT_OT_bambu_stl(bpy.types.Operator, ExportHelper):
    """Export meshes as STL (optionally merged, mm-scaled)"""

    bl_idname = "export_mesh.bambu_stl"
    bl_label = "Export Bambu STL"
    bl_options = {"REGISTER"}

    filename_ext = ".stl"
    filter_glob: StringProperty(default="*.stl", options={"HIDDEN"})  # type: ignore

    unit_scale: EnumProperty(
        name="Units",
        items=[
            ("MM", "Millimeters", "Scale from Blender meters to mm"),
            ("M", "Meters (no conversion)", "Keep Blender units"),
        ],
        default="MM",
    )  # type: ignore

    selection_only: BoolProperty(
        name="Selection Only",
        description="Export only selected meshes",
        default=False,
    )  # type: ignore

    merge: BoolProperty(
        name="Merge All",
        description="Merge all meshes into a single STL",
        default=False,
    )  # type: ignore

    def execute(self, context):
        scale = M_TO_MM if self.unit_scale == "MM" else 1.0
        source = context.selected_objects if self.selection_only else context.scene.objects
        meshes = [o for o in source if o.type == "MESH"]

        if not meshes:
            self.report({"WARNING"}, "No mesh objects to export")
            return {"CANCELLED"}

        depsgraph = context.evaluated_depsgraph_get()

        if self.merge:
            bm = bmesh.new()
            for obj in meshes:
                eval_obj = obj.evaluated_get(depsgraph)
                temp = eval_obj.to_mesh()
                # Transform vertices to world space
                temp.transform(obj.matrix_world)
                bm.from_mesh(temp)
                eval_obj.to_mesh_clear()
            bmesh.ops.triangulate(bm, faces=bm.faces[:])
            _write_stl_bmesh(self.filepath, bm, scale)
            bm.free()
        else:
            # Export each mesh separately (appending _name before .stl)
            import os
            base, ext = os.path.splitext(self.filepath)
            for obj in meshes:
                eval_obj = obj.evaluated_get(depsgraph)
                temp = eval_obj.to_mesh()
                temp.transform(obj.matrix_world)
                bm = bmesh.new()
                bm.from_mesh(temp)
                eval_obj.to_mesh_clear()
                bmesh.ops.triangulate(bm, faces=bm.faces[:])
                path = f"{base}_{obj.name}{ext}" if len(meshes) > 1 else self.filepath
                _write_stl_bmesh(path, bm, scale)
                bm.free()

        self.report({"INFO"}, f"Exported STL to {self.filepath}")
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "unit_scale")
        layout.prop(self, "selection_only")
        layout.prop(self, "merge")


def _write_stl_bmesh(filepath, bm, scale):
    """Write a bmesh as a binary STL file."""
    bm.normal_update()
    with open(filepath, "wb") as f:
        # 80-byte header
        f.write(b"\x00" * 80)
        # Triangle count
        f.write(struct.pack("<I", len(bm.faces)))
        for face in bm.faces:
            n = face.normal
            f.write(struct.pack("<3f", n.x, n.y, n.z))
            for vert in face.verts:
                f.write(struct.pack("<3f",
                                    vert.co.x * scale,
                                    vert.co.y * scale,
                                    vert.co.z * scale))
            f.write(struct.pack("<H", 0))  # attribute byte count


def menu_func_export(self, context):
    self.layout.operator(
        EXPORT_OT_bambu_stl.bl_idname, text="Bambu STL (.stl)"
    )
