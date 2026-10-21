"""
形状模板 (HALCON create_shape_model / create_scaled_shape_model 的 OpenCV 实现)。

模型保存模板区域内的灰度图块与区域掩膜, 以区域重心为模型原点, 并提取边缘轮廓
(坐标相对于模型原点, 供 get_shape_model_contours 使用)。
"""

import math
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

import cv2
import numpy as np

from core.types import XLDContour

DEFAULT_NUM_LEVELS = 4
DEFAULT_CONTRAST = 30.0
MIN_MODEL_PIXELS = 50
MIN_CONTOUR_POINTS = 5
CANNY_LOW_FACTOR = 2.0
CANNY_HIGH_FACTOR = 4.0
MIN_ANGLE_STEP = math.radians(0.5)
MAX_ANGLE_STEP = math.radians(2.0)
MIN_SCALE_STEP = 0.01
MAX_SCALE_STEP = 0.05

METRICS = ("use_polarity", "ignore_global_polarity", "ignore_local_polarity", "ignore_color_polarity")


@dataclass
class ShapeModel:
    template: np.ndarray
    mask: np.ndarray
    origin: Tuple[float, float]
    radius: float
    num_levels: int
    angle_start: float
    angle_extent: float
    angle_step: float
    scale_min: float
    scale_max: float
    scale_step: float
    metric: str
    min_contrast: float
    contours: List[XLDContour] = field(default_factory=list)


def _is_auto(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() == "auto"


def _first_number(value: Any, default: float) -> float:
    if isinstance(value, list):
        value = value[0] if value else "auto"
    if _is_auto(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def to_gray(img: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if img.ndim == 3 else img


def gradient_magnitude(gray: np.ndarray) -> np.ndarray:
    """极性无关的匹配用梯度幅值图 (uint8)"""
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    gx = cv2.Sobel(blurred, cv2.CV_32F, 1, 0)
    gy = cv2.Sobel(blurred, cv2.CV_32F, 0, 1)
    return cv2.convertScaleAbs(cv2.magnitude(gx, gy), alpha=0.25)


def _extract_contours(template: np.ndarray, mask: np.ndarray, origin: Tuple[float, float], contrast: float) -> List[XLDContour]:
    blurred = cv2.GaussianBlur(template, (3, 3), 0)
    edges = cv2.Canny(blurred, contrast * CANNY_LOW_FACTOR, contrast * CANNY_HIGH_FACTOR)
    inner = cv2.erode(mask, np.ones((3, 3), np.uint8))
    edges = cv2.bitwise_and(edges, inner)
    found, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    contours: List[XLDContour] = []
    for cnt in found:
        if len(cnt) < MIN_CONTOUR_POINTS:
            continue
        pts = [(float(p[0][1]) - origin[0], float(p[0][0]) - origin[1]) for p in cnt]
        length = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1))
        contours.append(XLDContour(id=len(contours) + 1, points=pts, is_closed=False, length=length))
    return contours


def create_shape_model(
    image: np.ndarray,
    domain: Optional[np.ndarray],
    num_levels: Any,
    angle_start: float,
    angle_extent: float,
    angle_step: Any,
    scale_min: float,
    scale_max: float,
    scale_step: Any,
    metric: Any,
    contrast: Any,
    min_contrast: Any,
) -> ShapeModel:
    gray = to_gray(image)
    region = np.ones(gray.shape[:2], dtype=bool) if domain is None else domain.astype(bool)
    ys, xs = np.nonzero(region)
    if ys.size < MIN_MODEL_PIXELS:
        raise ValueError("模板区域太小, 无法创建形状模型 (至少需要 %d 个像素)" % MIN_MODEL_PIXELS)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    template = np.ascontiguousarray(gray[y0:y1, x0:x1])
    mask = region[y0:y1, x0:x1].astype(np.uint8) * 255
    origin = (float(ys.mean()) - y0, float(xs.mean()) - x0)
    radius = float(np.max(np.hypot(ys - y0 - origin[0], xs - x0 - origin[1]))) + 1.0

    metric_name = str(metric).lower() if not _is_auto(metric) else "use_polarity"
    if metric_name not in METRICS:
        raise ValueError(f"不支持的 Metric '{metric}', 可选: {', '.join(METRICS)}")
    contrast_value = _first_number(contrast, DEFAULT_CONTRAST)
    angle_step_value = float(np.clip(1.0 / radius, MIN_ANGLE_STEP, MAX_ANGLE_STEP)) if _is_auto(angle_step) else float(angle_step)
    scale_step_value = float(np.clip(1.0 / radius, MIN_SCALE_STEP, MAX_SCALE_STEP)) if _is_auto(scale_step) else float(scale_step)
    if angle_step_value <= 0 or scale_step_value <= 0:
        raise ValueError("AngleStep 和 ScaleStep 必须大于 0")
    if scale_min <= 0 or scale_max < scale_min:
        raise ValueError("缩放范围无效: 需要 0 < ScaleMin <= ScaleMax")

    return ShapeModel(
        template=template,
        mask=mask,
        origin=origin,
        radius=radius,
        num_levels=DEFAULT_NUM_LEVELS if _is_auto(num_levels) else max(1, int(num_levels)),
        angle_start=float(angle_start),
        angle_extent=float(angle_extent),
        angle_step=angle_step_value,
        scale_min=float(scale_min),
        scale_max=float(scale_max),
        scale_step=scale_step_value,
        metric=metric_name,
        min_contrast=_first_number(min_contrast, contrast_value / 4.0),
        contours=_extract_contours(template, mask, origin, contrast_value),
    )
