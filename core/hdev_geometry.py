"""
HALCON 2D 齐次矩阵 (hom_mat2d_*) 与轮廓仿射变换。

矩阵用 6 元组 (a, b, c, d, e, f) 表示 2x3 矩阵 [[a, b, c], [d, e, f]],
作用在 (row, column) 坐标上, 与 HALCON 的约定一致: x 对应 row, y 对应 column。
每个 hom_mat2d_* 算子把新变换左乘在已有矩阵之后 (即先做原有变换, 再做新变换)。
正角度为逆时针 (图像显示上的视觉方向)。
"""

import math
from typing import List, Sequence, Tuple

from core.types import XLDContour

HomMat2D = Tuple[float, float, float, float, float, float]


def _as_matrix(values: Sequence[float]) -> HomMat2D:
    if not isinstance(values, (list, tuple)) or len(values) != 6:
        raise ValueError("HomMat2D 必须是由 hom_mat2d_* 算子产生的 6 元组")
    return tuple(float(v) for v in values)


def _compose(after: HomMat2D, before: HomMat2D) -> HomMat2D:
    a, b, c, d, e, f = after
    p, q, r, s, t, u = before
    return (
        a * p + b * s, a * q + b * t, a * r + b * u + c,
        d * p + e * s, d * q + e * t, d * r + e * u + f,
    )


def identity() -> HomMat2D:
    return (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)


def translate(mat: Sequence[float], tx: float, ty: float) -> HomMat2D:
    return _compose((1.0, 0.0, float(tx), 0.0, 1.0, float(ty)), _as_matrix(mat))


def rotate(mat: Sequence[float], phi: float, px: float, py: float) -> HomMat2D:
    cos_p, sin_p = math.cos(phi), math.sin(phi)
    about_point = (
        cos_p, -sin_p, px - cos_p * px + sin_p * py,
        sin_p, cos_p, py - sin_p * px - cos_p * py,
    )
    return _compose(about_point, _as_matrix(mat))


def scale(mat: Sequence[float], sx: float, sy: float, px: float, py: float) -> HomMat2D:
    about_point = (sx, 0.0, px - sx * px, 0.0, sy, py - sy * py)
    return _compose(about_point, _as_matrix(mat))


def vector_angle_to_rigid(row1: float, col1: float, angle1: float,
                          row2: float, col2: float, angle2: float) -> HomMat2D:
    """把位姿 (row1, col1, angle1) 刚体变换到位姿 (row2, col2, angle2): 先绕点 1 旋转, 再平移"""
    rotated = rotate(identity(), angle2 - angle1, row1, col1)
    return translate(rotated, row2 - row1, col2 - col1)


def apply_to_point(mat: Sequence[float], row: float, col: float) -> Tuple[float, float]:
    a, b, c, d, e, f = _as_matrix(mat)
    return a * row + b * col + c, d * row + e * col + f


def affine_trans_contours(contours: List[XLDContour], mat: Sequence[float]) -> List[XLDContour]:
    """对一组 XLD 轮廓做仿射变换, 返回新轮廓 (长度按变换后的点重算)"""
    matrix = _as_matrix(mat)
    out: List[XLDContour] = []
    for contour in contours:
        points = [apply_to_point(matrix, r, c) for r, c in contour.points]
        length = sum(math.dist(points[i], points[i + 1]) for i in range(len(points) - 1))
        out.append(XLDContour(id=contour.id, points=points, is_closed=contour.is_closed, length=length))
    return out
