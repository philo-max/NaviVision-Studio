"""
字符区域相关算子: 区域外接矩形 (smallest_rectangle1)、区域排序 (sort_region)、
字符分割阈值 (char_threshold)。
"""

from typing import List, Optional, Tuple

import cv2
import numpy as np

from core.operators import connection, halcon_phi
from core.types import Region, RegionObject

LINE_GAP_FACTOR = 0.5
DEFAULT_SIGMA = 2.0
HIST_BINS = 256
POINT_MODES = ("upper_left", "upper_right", "lower_left", "lower_right", "first_point", "last_point")


def region_items(region: Region) -> List[Tuple[Tuple[int, int, int, int], int, Tuple[float, float]]]:
    """返回 [(bbox, area, centroid)]: 已打散的区域取每个目标, 否则把整个区域当作一个目标 (bbox 末端不含)"""
    if region.objects:
        return [(o.bbox, o.area, o.centroid) for o in region.objects]
    ys, xs = np.nonzero(region.mask)
    if ys.size == 0:
        return []
    bbox = (int(ys.min()), int(xs.min()), int(ys.max()) + 1, int(xs.max()) + 1)
    return [(bbox, int(ys.size), (float(ys.mean()), float(xs.mean())))]


def smallest_rectangle1(region: Region) -> Tuple[List[int], List[int], List[int], List[int]]:
    """HALCON smallest_rectangle1: 每个目标与坐标轴对齐的最小外接矩形, 返回 Row1, Column1, Row2, Column2 (含端点)"""
    rows1, cols1, rows2, cols2 = [], [], [], []
    for (r0, c0, r1, c1), _, _ in region_items(region):
        rows1.append(r0)
        cols1.append(c0)
        rows2.append(r1 - 1)
        cols2.append(c1 - 1)
    return rows1, cols1, rows2, cols2


def _object_points(region: Region) -> List[np.ndarray]:
    """每个目标 (没打散的区域视为一个目标) 的像素点坐标, 形状 (N, 2), 列为 (x=列, y=行)"""
    if region.objects:
        groups = []
        for obj in region.objects:
            ys, xs = np.nonzero(obj.bbox_mask(region.mask))
            groups.append(np.stack([xs + obj.bbox[1], ys + obj.bbox[0]], axis=1).astype(np.float32))
        return groups
    ys, xs = np.nonzero(region.mask)
    return [np.stack([xs, ys], axis=1).astype(np.float32)] if ys.size else []


def smallest_rectangle2(region: Region) -> Tuple[List[float], List[float], List[float], List[float], List[float]]:
    """HALCON smallest_rectangle2: 每个目标的最小外接旋转矩形, 返回 Row, Column, Phi, Length1, Length2"""
    rows, cols, phis, len1, len2 = [], [], [], [], []
    for pts in _object_points(region):
        rect = cv2.minAreaRect(pts)
        (cx, cy), (w, h), _ = rect
        rows.append(float(cy))
        cols.append(float(cx))
        phis.append(halcon_phi(cv2.boxPoints(rect)))
        len1.append(float(max(w, h) / 2.0))
        len2.append(float(min(w, h) / 2.0))
    return rows, cols, phis, len1, len2


def smallest_circle(region: Region) -> Tuple[List[float], List[float], List[float]]:
    """HALCON smallest_circle: 每个目标的最小外接圆, 返回 Row, Column, Radius"""
    rows, cols, radii = [], [], []
    for pts in _object_points(region):
        (cx, cy), radius = cv2.minEnclosingCircle(pts)
        rows.append(float(cy))
        cols.append(float(cx))
        radii.append(float(radius))
    return rows, cols, radii


def _cluster_lines(objects: List[RegionObject], axis: int) -> List[List[RegionObject]]:
    """沿 axis (0=按行聚成文本行, 1=按列聚成文本列) 聚类: 中心距小于半个字高 (字宽) 视为同一行 (列)"""
    sizes = sorted(o.bbox[axis + 2] - o.bbox[axis] for o in objects)
    gap = LINE_GAP_FACTOR * sizes[len(sizes) // 2]
    ordered = sorted(objects, key=lambda o: o.centroid[axis])
    groups: List[List[RegionObject]] = [[ordered[0]]]
    for obj in ordered[1:]:
        if abs(obj.centroid[axis] - groups[-1][-1].centroid[axis]) <= gap:
            groups[-1].append(obj)
        else:
            groups.append([obj])
    return groups


def _sort_key(obj: RegionObject, mode: str, row_or_col: str) -> Tuple[float, float]:
    r0, c0, r1, c1 = obj.bbox
    row = {"upper_left": r0, "upper_right": r0, "first_point": r0, "lower_left": r1 - 1, "lower_right": r1 - 1, "last_point": r1 - 1}[mode]
    col = {"upper_left": c0, "lower_left": c0, "first_point": c0, "upper_right": c1 - 1, "lower_right": c1 - 1, "last_point": c1 - 1}[mode]
    return (row, col) if row_or_col == "row" else (col, row)


def sort_region(region: Region, mode: str, order: str, row_or_col: str) -> Region:
    """
    HALCON sort_region。mode: 'character' 按书写顺序 (row: 先分行再从左到右; column: 先分列再从上到下),
    或按外接矩形的某个角点排序 ('upper_left' 等); order: 'true' 升序, 'false' 降序; row_or_col: 'row' / 'column'。
    """
    mode, order, row_or_col = str(mode).lower(), str(order).lower(), str(row_or_col).lower()
    if row_or_col not in ("row", "column"):
        raise ValueError("sort_region 的 RowOrCol 只能是 'row' 或 'column'")
    if mode != "character" and mode not in POINT_MODES:
        raise ValueError(f"sort_region 不支持排序方式 '{mode}'")
    connected = region if region.is_connected else connection(region)
    objects = list(connected.objects)
    if objects:
        if mode == "character":
            axis = 0 if row_or_col == "row" else 1
            ordered: List[RegionObject] = []
            for group in _cluster_lines(objects, axis):
                ordered.extend(sorted(group, key=lambda o: o.centroid[1 - axis]))
            objects = ordered
        else:
            objects.sort(key=lambda o: _sort_key(o, mode, row_or_col))
        if order == "false":
            objects.reverse()
    return Region(mask=connected.mask, objects=objects, is_connected=True, ordered=True)


def _histogram(gray: np.ndarray, domain: Optional[np.ndarray], sigma: float) -> np.ndarray:
    pixels = gray[domain] if domain is not None else gray.ravel()
    hist = np.bincount(pixels.ravel(), minlength=HIST_BINS).astype(np.float64)
    if sigma and sigma > 0:
        hist = cv2.GaussianBlur(hist.reshape(1, -1), (0, 0), sigmaX=float(sigma)).ravel()
    if hist.sum() <= 0:
        raise ValueError("阈值分割: 直方图区域为空")
    return hist


def _otsu_threshold(hist: np.ndarray) -> int:
    """大津法 (最大类间方差): 返回使两类分离度最大的灰度阈值 (<= 阈值为暗类)"""
    total = hist.sum()
    levels = np.arange(HIST_BINS)
    weight_dark = np.cumsum(hist)
    mean_dark = np.cumsum(hist * levels)
    weight_light = total - weight_dark
    with np.errstate(divide="ignore", invalid="ignore"):
        mu_dark = mean_dark / weight_dark
        mu_light = (mean_dark[-1] - mean_dark) / weight_light
        between = weight_dark * weight_light * (mu_dark - mu_light) ** 2
    return int(np.nanargmax(np.nan_to_num(between)))


def _valley_threshold(hist: np.ndarray) -> int:
    """双峰直方图谷底: 取平滑直方图上最高的两个局部峰之间的最低点; 找不到两个峰时退回大津法"""
    peaks = [i for i in range(1, HIST_BINS - 1) if hist[i] >= hist[i - 1] and hist[i] > hist[i + 1]]
    peaks = sorted(peaks, key=lambda i: hist[i], reverse=True)[:2]
    if len(peaks) < 2:
        return _otsu_threshold(hist)
    low, high = sorted(peaks)
    return int(low + np.argmin(hist[low:high + 1]))


def binary_threshold(gray: np.ndarray, domain: Optional[np.ndarray], method: str, light_dark: str) -> Tuple[Region, int]:
    """
    HALCON binary_threshold: 由直方图自动确定阈值并分割。method: 'max_separability' (大津法) 或
    'smooth_histo' (平滑直方图的谷底); light_dark: 'dark' 取暗于阈值的目标, 'light' 取亮于阈值的目标。
    直方图只统计定义域 (ROI) 内的像素。返回 (区域, 实际使用的阈值)。
    """
    method, light_dark = str(method).lower(), str(light_dark).lower()
    if light_dark not in ("dark", "light"):
        raise ValueError("binary_threshold 的 LightDark 只能是 'dark' 或 'light'")
    if method == "max_separability":
        threshold = _otsu_threshold(_histogram(gray, domain, 0.0))
    elif method == "smooth_histo":
        threshold = _valley_threshold(_histogram(gray, domain, 2.0))
    else:
        raise ValueError("binary_threshold 的 Method 只支持 'max_separability' 或 'smooth_histo'")
    inside = gray <= threshold if light_dark == "dark" else gray > threshold
    mask = inside.astype(np.uint8) * 255
    if domain is not None:
        mask[~domain] = 0
    return Region(mask=mask, is_connected=False), threshold


def char_threshold(gray: np.ndarray, domain: Optional[np.ndarray], sigma: float) -> Tuple[Region, int]:
    """
    HALCON char_threshold 的近似实现 (深色字符、浅色背景): 先用 sigma 平滑灰度直方图, 再按大津法在平滑后的
    直方图上确定阈值; 返回 (字符区域, 阈值)。HALCON 的 Percent 参数在此不参与计算。
    """
    threshold = _otsu_threshold(_histogram(gray, domain, sigma))
    mask = (gray <= threshold).astype(np.uint8) * 255
    if domain is not None:
        mask[~domain] = 0
    return Region(mask=mask, is_connected=False), threshold
