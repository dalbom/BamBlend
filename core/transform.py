"""
3MF <-> Blender matrix transform utilities.

3MF stores transforms as 12 floats (4x3 row-major, row-vector convention):
    "m00 m01 m02 m10 m11 m12 m20 m21 m22 tx ty tz"

    Meaning: [x' y' z' 1] = [x y z 1] * | m00 m01 m02 0 |
                                          | m10 m11 m12 0 |
                                          | m20 m21 m22 0 |
                                          | tx  ty  tz  1 |

Blender uses column-vector convention: v' = M * v, so we transpose.
3MF units are millimeters; Blender uses meters (scale factor 0.001).
"""

from mathutils import Matrix

MM_TO_M = 0.001
M_TO_MM = 1000.0

IDENTITY_3MF = "1 0 0 0 1 0 0 0 1 0 0 0"


def parse_3mf_transform(transform_str, scale=MM_TO_M):
    """Parse a 3MF 4x3 transform string into a Blender 4x4 Matrix.

    Only translation components are scaled (rotation/scale in the
    upper-left 3x3 are dimensionless).
    """
    if not transform_str or not transform_str.strip():
        return Matrix.Identity(4)

    vals = [float(v) for v in transform_str.strip().split()]
    if len(vals) != 12:
        return Matrix.Identity(4)

    # Transpose from row-vector to column-vector layout
    return Matrix((
        (vals[0], vals[3], vals[6], vals[9] * scale),
        (vals[1], vals[4], vals[7], vals[10] * scale),
        (vals[2], vals[5], vals[8], vals[11] * scale),
        (0.0,     0.0,     0.0,     1.0),
    ))


def matrix_to_3mf_transform(mat, scale=M_TO_MM):
    """Convert a Blender 4x4 Matrix back to a 3MF transform string.

    Transposes from column-vector back to row-vector layout and scales
    translation from meters to millimeters.
    """
    return (
        f"{mat[0][0]:.9g} {mat[1][0]:.9g} {mat[2][0]:.9g} "
        f"{mat[0][1]:.9g} {mat[1][1]:.9g} {mat[2][1]:.9g} "
        f"{mat[0][2]:.9g} {mat[1][2]:.9g} {mat[2][2]:.9g} "
        f"{mat[0][3] * scale:.9g} {mat[1][3] * scale:.9g} {mat[2][3] * scale:.9g}"
    )


def scale_vertices(vertices, scale=MM_TO_M):
    """Scale a list of (x, y, z) tuples by the given factor."""
    return [(x * scale, y * scale, z * scale) for x, y, z in vertices]
