"""
HALCON 2D 齐次矩阵 (hom_mat2d_*) 与轮廓仿射变换。

矩阵用 6 元组 (a, b, c, d, e, f) 表示 2x3 矩阵 [[a, b, c], [d, e, f]],
作用在 (row, column) 坐标上, 与 HALCON 的约定一致: x 对应 row, y 对应 column。
每个 hom_mat2d_* 算子把新变换左乘在已有矩阵之后 (即先做原有变换, 再做新变换)。
正角度为逆时针 (图像显示上的视觉方向)。
"""

import math
from typing import List, Sequence, Tuple

import cv2
import numpy as np

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


_INTERPOLATIONS = {
    "nearest_neighbor": cv2.INTER_NEAREST,
    "constant": cv2.INTER_LINEAR,
    "bilinear": cv2.INTER_LINEAR,
    "weighted": cv2.INTER_LINEAR,
    "bicubic": cv2.INTER_CUBIC,
}


def _interpolation_flag(name: str) -> int:
    key = str(name).lower()
    if key not in _INTERPOLATIONS:
        raise ValueError(f"不支持的插值方式 '{name}', 可选: {', '.join(_INTERPOLATIONS)}")
    return _INTERPOLATIONS[key]


def affine_trans_image(img: np.ndarray, mat: Sequence[float], interpolation: str = "bilinear",
                       adapt_image_size: bool = False) -> np.ndarray:
    """
    HALCON affine_trans_image: 把图像按 HomMat2D (作用在 (行, 列) 上) 仿射变换, 区域外填 0。
    adapt_image_size 为 True 时输出画布扩大到刚好容纳变换后的整幅图像。
    """
    a, b, c, d, e, f = _as_matrix(mat)
    cv_mat = np.array([[e, d, f], [b, a, c]], dtype=np.float64)
    height, width = img.shape[:2]
    out_size = (width, height)
    if adapt_image_size:
        corners = np.array([[0, 0, 1], [width, 0, 1], [width, height, 1], [0, height, 1]], dtype=np.float64) @ cv_mat.T
        min_x, min_y = corners.min(axis=0)
        cv_mat[0, 2] -= min_x
        cv_mat[1, 2] -= min_y
        out_size = (int(math.ceil(corners[:, 0].max() - min_x)), int(math.ceil(corners[:, 1].max() - min_y)))
    return cv2.warpAffine(img, cv_mat, out_size, flags=_interpolation_flag(interpolation))


def rotate_image(img: np.ndarray, phi_degrees: float, interpolation: str = "bilinear") -> np.ndarray:
    """HALCON rotate_image: 绕图像中心 (像素中心坐标系下的几何中心) 旋转 phi (角度, 逆时针为正), 画布大小不变"""
    height, width = img.shape[:2]
    mat = cv2.getRotationMatrix2D(((width - 1) / 2.0, (height - 1) / 2.0), float(phi_degrees), 1.0)
    return cv2.warpAffine(img, mat, (width, height), flags=_interpolation_flag(interpolation))
