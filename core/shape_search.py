"""
形状模板搜索 (HALCON find_shape_model / find_scaled_shape_model 的 OpenCV 实现)。

采用由粗到细的两级搜索: 先在降采样图上以较大的角度/缩放步长遍历, 提取候选位置;
再在原分辨率的局部窗口内细化角度、缩放与位置 (可选抛物线亚像素插值)。
得分为带掩膜的归一化互相关 (TM_CCOEFF_NORMED), 取值 0~1; 角度以逆时针 (视觉方向) 为正。
匹配得分与 HALCON 的数值不会逐位一致, 但目标位置、角度与缩放的含义相同。
"""

import math
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from core.shape_model import ShapeModel, gradient_magnitude, to_gray

COARSE_SCORE_FACTOR = 0.7
MIN_COARSE_THRESHOLD = 0.05
MAX_COARSE_SCALES = 5
MAX_DOWNSCALE = 4
MIN_COARSE_RADIUS_PX = 8
MAX_COARSE_ANGLE_STEP = math.radians(6)
PEAKS_PER_POSE = 5
MIN_CANDIDATES = 10
MAX_CANDIDATES = 40
CLUSTER_RADIUS_FACTOR = 0.5
REFINE_MARGIN_FACTOR = 3
MIN_MASK_PIXELS = 20
MAX_SUBPIXEL_SHIFT = 0.5

Pose = Tuple[float, float, float, float, float]


def _is_none(value: Any) -> bool:
    return isinstance(value, str) and value.lower() == "none"


def _prepare(gray: np.ndarray, metric: str) -> np.ndarray:
    return gradient_magnitude(gray) if metric == "ignore_local_polarity" else gray


def _transform(template: np.ndarray, mask: np.ndarray, origin: Tuple[float, float], phi: float, scale: float):
    oy, ox = origin
    mat = cv2.getRotationMatrix2D((ox, oy), math.degrees(phi), scale)
    h, w = template.shape
    corners = np.array([[0, 0, 1], [w, 0, 1], [w, h, 1], [0, h, 1]], dtype=np.float64) @ mat.T
    min_x, min_y = corners.min(axis=0)
    max_x, max_y = corners.max(axis=0)
    mat[0, 2] -= min_x
    mat[1, 2] -= min_y
    size = (int(math.ceil(max_x - min_x)), int(math.ceil(max_y - min_y)))
    warped = cv2.warpAffine(template, mat, size, flags=cv2.INTER_LINEAR)
    warped_mask = (cv2.warpAffine(mask, mat, size, flags=cv2.INTER_LINEAR) > 127).astype(np.uint8) * 255
    new_origin = (mat[1, 0] * ox + mat[1, 1] * oy + mat[1, 2], mat[0, 0] * ox + mat[0, 1] * oy + mat[0, 2])
    return warped, warped_mask, new_origin


def _correlate(search: np.ndarray, template: np.ndarray, mask: np.ndarray, use_abs: bool) -> Optional[np.ndarray]:
    if template.shape[0] > search.shape[0] or template.shape[1] > search.shape[1]:
        return None
    if np.count_nonzero(mask) < MIN_MASK_PIXELS:
        return None
    res = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED, mask=mask)
    res = np.nan_to_num(res, nan=0.0, posinf=0.0, neginf=0.0)
    return np.clip(np.abs(res) if use_abs else res, 0.0, 1.0)


def _steps(start: float, extent: float, step: float) -> List[float]:
    if extent <= 0:
        return [start]
    count = int(math.ceil(extent / step - 1e-9))
    return [start + min(i * step, extent) for i in range(count + 1)]


def _parabola(left: float, centre: float, right: float) -> float:
    denom = left - 2.0 * centre + right
    if abs(denom) < 1e-12:
        return 0.0
    return float(np.clip(0.5 * (left - right) / denom, -MAX_SUBPIXEL_SHIFT, MAX_SUBPIXEL_SHIFT))


def _downscale_factor(model: ShapeModel, num_levels: Any) -> int:
    levels = model.num_levels if isinstance(num_levels, str) else max(1, int(num_levels))
    factor = 2 ** (levels - 1)
    while factor > 1 and model.radius / factor < MIN_COARSE_RADIUS_PX:
        factor //= 2
    return min(factor, MAX_DOWNSCALE)


def _coarse_candidates(search, model, tmpl, factor, angles, scales, min_score, use_abs) -> List[Pose]:
    small_search = search if factor == 1 else cv2.resize(search, None, fx=1.0 / factor, fy=1.0 / factor, interpolation=cv2.INTER_AREA)
    small_tmpl = tmpl if factor == 1 else cv2.resize(tmpl, None, fx=1.0 / factor, fy=1.0 / factor, interpolation=cv2.INTER_AREA)
    small_mask = model.mask if factor == 1 else (cv2.resize(model.mask, small_tmpl.shape[::-1], interpolation=cv2.INTER_AREA) > 127).astype(np.uint8) * 255
    small_origin = (model.origin[0] / factor, model.origin[1] / factor)
    threshold = max(MIN_COARSE_THRESHOLD, min_score * COARSE_SCORE_FACTOR)
    kernel_size = max(3, int(model.radius / factor * 0.8) | 1)
    kernel = np.ones((kernel_size, kernel_size), np.uint8)

    found: List[Pose] = []
    for phi in angles:
        for scale in scales:
            warped, warped_mask, (oy, ox) = _transform(small_tmpl, small_mask, small_origin, phi, scale)
            res = _correlate(small_search, warped, warped_mask, use_abs)
            if res is None:
                continue
            peaks = (res >= cv2.dilate(res, kernel)) & (res >= threshold)
            ys, xs = np.nonzero(peaks)
            order = np.argsort(res[ys, xs])[::-1][:PEAKS_PER_POSE]
            for i in order:
                found.append((float(res[ys[i], xs[i]]), (ys[i] + oy) * factor, (xs[i] + ox) * factor, phi, scale))
    found.sort(key=lambda c: c[0], reverse=True)
    return found


def _cluster(candidates: List[Pose], radius: float, limit: int) -> List[Pose]:
    kept: List[Pose] = []
    for cand in candidates:
        if all(math.hypot(cand[1] - k[1], cand[2] - k[2]) > radius for k in kept):
            kept.append(cand)
            if len(kept) >= limit:
                break
    return kept


def _local_match(search, model, tmpl, phi, scale, row, col, margin, use_abs, subpixel):
    warped, warped_mask, (oy, ox) = _transform(tmpl, model.mask, model.origin, phi, scale)
    h, w = warped.shape
    top = int(round(row - oy)) - margin
    left = int(round(col - ox)) - margin
    top, left = max(0, top), max(0, left)
    bottom = min(search.shape[0], int(round(row - oy)) + h + margin)
    right = min(search.shape[1], int(round(col - ox)) + w + margin)
    res = _correlate(search[top:bottom, left:right], warped, warped_mask, use_abs)
    if res is None:
        return None
    py, px = np.unravel_index(int(np.argmax(res)), res.shape)
    dy = dx = 0.0
    if subpixel and 0 < py < res.shape[0] - 1 and 0 < px < res.shape[1] - 1:
        dy = _parabola(res[py - 1, px], res[py, px], res[py + 1, px])
        dx = _parabola(res[py, px - 1], res[py, px], res[py, px + 1])
    return float(res[py, px]), top + py + oy + dy, left + px + ox + dx


def _refine(search, model, tmpl, cand, factor, params, use_abs, subpixel):
    _, row, col, phi, scale = cand
    margin = factor * REFINE_MARGIN_FACTOR
    angle_lo, angle_hi, scale_lo, scale_hi, coarse_angle_step, coarse_scale_step = params
    best = (-1.0, row, col, phi, scale)

    def probe(p, s, centre):
        out = _local_match(search, model, tmpl, p, s, centre[0], centre[1], margin, use_abs, subpixel)
        return None if out is None else (out[0], out[1], out[2], p, s)

    n_angle = int(math.ceil(coarse_angle_step / model.angle_step))
    for k in range(-n_angle, n_angle + 1):
        p = phi + k * model.angle_step
        if angle_lo - 1e-9 <= p <= angle_hi + 1e-9:
            hit = probe(p, scale, (row, col))
            if hit and hit[0] > best[0]:
                best = hit
    n_scale = int(math.ceil(coarse_scale_step / model.scale_step))
    base = best
    for k in range(-n_scale, n_scale + 1):
        s = base[4] + k * model.scale_step
        if scale_lo - 1e-9 <= s <= scale_hi + 1e-9:
            hit = probe(base[3], s, (base[1], base[2]))
            if hit and hit[0] > best[0]:
                best = hit
    base = best
    for k in (-2, -1, 1, 2):
        p = base[3] + k * model.angle_step * 0.5
        if angle_lo - 1e-9 <= p <= angle_hi + 1e-9:
            hit = probe(p, base[4], (base[1], base[2]))
            if hit and hit[0] > best[0]:
                best = hit
    return best


def _circle_overlap(r1: float, r2: float, dist: float) -> float:
    small, big = min(r1, r2), max(r1, r2)
    if dist >= r1 + r2:
        return 0.0
    if dist <= big - small:
        return 1.0
    a = r1 * r1 * math.acos((dist * dist + r1 * r1 - r2 * r2) / (2 * dist * r1))
    b = r2 * r2 * math.acos((dist * dist + r2 * r2 - r1 * r1) / (2 * dist * r2))
    c = 0.5 * math.sqrt((-dist + r1 + r2) * (dist + r1 - r2) * (dist - r1 + r2) * (dist + r1 + r2))
    return (a + b - c) / (math.pi * small * small)


def find_shape_models(
    image: np.ndarray,
    model: ShapeModel,
    angle_start: float,
    angle_extent: float,
    scale_min: float,
    scale_max: float,
    min_score: float,
    num_matches: int,
    max_overlap: float,
    subpixel: Any,
    num_levels: Any,
) -> List[Dict[str, float]]:
    use_abs = model.metric in ("ignore_global_polarity", "ignore_color_polarity")
    use_subpixel = not _is_none(subpixel)
    search = _prepare(to_gray(image), model.metric)
    tmpl = _prepare(model.template, model.metric)
    factor = _downscale_factor(model, num_levels)

    coarse_angle_step = min(model.angle_step * factor, MAX_COARSE_ANGLE_STEP)
    scale_span = scale_max - scale_min
    coarse_scale_step = max(model.scale_step * factor, scale_span / (MAX_COARSE_SCALES - 1)) if scale_span > 0 else model.scale_step
    angles = _steps(angle_start, angle_extent, coarse_angle_step)
    scales = _steps(scale_min, scale_span, coarse_scale_step)

    candidates = _coarse_candidates(search, model, tmpl, factor, angles, scales, min_score, use_abs)
    limit = MIN_CANDIDATES if num_matches <= 0 else min(MAX_CANDIDATES, max(MIN_CANDIDATES, 3 * num_matches))
    candidates = _cluster(candidates, max(model.radius * scale_min * CLUSTER_RADIUS_FACTOR, factor * 3.0), limit)

    params = (angle_start, angle_start + max(angle_extent, 0.0), scale_min, scale_max, coarse_angle_step, coarse_scale_step)
    refined = [_refine(search, model, tmpl, c, factor, params, use_abs, use_subpixel) for c in candidates]
    refined = [r for r in refined if r[0] >= min_score]
    refined.sort(key=lambda r: r[0], reverse=True)

    kept: List[Pose] = []
    for r in refined:
        clash = any(
            _circle_overlap(model.radius * r[4], model.radius * k[4], math.hypot(r[1] - k[1], r[2] - k[2])) > max_overlap
            for k in kept
        )
        if not clash:
            kept.append(r)
    if num_matches > 0:
        kept = kept[:num_matches]
    return [
        {"score": float(k[0]), "row": float(k[1]), "column": float(k[2]), "angle": float(k[3]), "scale": float(k[4])}
        for k in kept
    ]
