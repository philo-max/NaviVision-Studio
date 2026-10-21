"""
NaviVision Studio (OpenDevelop) - Pipeline Execution Engine
支持多步骤算子级联、智能增量缓存 (避免重复前置计算)、执行计时与序列化
"""

import time
import base64
import hashlib
import json
import cv2
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from core.types import Region, XLDContour, StepResult
from core import operators as ops


def encode_image_base64(img: np.ndarray, format_ext: str = ".png") -> str:
    """将图像矩阵编码为 Base64 字符串"""
    success, buffer = cv2.imencode(format_ext, img)
    if not success:
        return ""
    return f"data:image/png;base64,{base64.b64encode(buffer).decode('utf-8')}"


def _compute_image_fingerprint(img: np.ndarray) -> str:
    """计算底图完整内容指纹，避免不同图像复用错误缓存。"""
    contiguous = np.ascontiguousarray(img)
    return hashlib.sha256(contiguous.tobytes()).hexdigest()[:16]


def _compute_step_fingerprint(prev_fp: str, op: str, params: Dict[str, Any], enabled: bool) -> str:
    """计算单个步骤的级联内容指纹 (包含前置指纹、算子类型、规范化参数与使能状态)"""
    norm_params = json.dumps(params, sort_keys=True, default=str)
    raw = f"{prev_fp}|{op}|{norm_params}|{enabled}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def create_colored_label_mask(
    region: Region,
    base_shape: Tuple[int, int],
    alpha: Optional[int] = None
) -> np.ndarray:
    """为连通域渲染高对比色彩叠加层 (仿 HALCON 彩色多通道 Region 显示); alpha 给定时覆盖默认的半透明度"""
    h, w = base_shape[:2]
    color_mask = np.zeros((h, w, 4), dtype=np.uint8)  # RGBA

    if not region.is_connected or not region.objects:
        # 单一区域，使用标志性亮荧光青色 (Cyan)
        y_idx, x_idx = np.where(region.mask > 0)
        color_mask[y_idx, x_idx] = [0, 240, 255, 140 if alpha is None else alpha]  # R, G, B, Alpha
        return color_mask

    # 预设高饱和度区别色系 (P5 / Cyberpunk 风格调色板)
    palette = [
        [0, 240, 255],    # 霓虹青
        [255, 51, 102],   # 绯红
        [255, 184, 0],    # 琥珀金
        [51, 255, 119],   # 翠绿
        [189, 0, 255],    # 霓虹紫
        [0, 153, 255],    # 蔚蓝
        [255, 102, 0],    # 亮橙
        [255, 230, 0],    # 柠檬黄
        [0, 255, 204],    # 薄荷绿
        [255, 0, 153],    # 荧光粉
    ]
    
    for i, obj in enumerate(region.objects):
        color = palette[i % len(palette)]
        # 提取当前对象的内部点
        y, x, y2, x2 = obj.bbox
        sub_mask = obj.bbox_mask(region.mask)
        yy, xx = np.where(sub_mask > 0)
        color_mask[y + yy, x + xx] = [color[0], color[1], color[2], 160 if alpha is None else alpha]
        
    return color_mask


class Pipeline:
    def __init__(self):
        self.steps: List[Dict[str, Any]] = []
        # 缓存每个步骤的中间输出: step_id -> {"fingerprint": str, "data": Any, "result": StepResult}
        self._cache: Dict[str, Dict[str, Any]] = {}
        # 原始底图
        self.source_image: Optional[np.ndarray] = None
        self.source_gray: Optional[np.ndarray] = None
        self.source_hist: Optional[List[int]] = None
        self.source_fp: str = ""
        # 分支 / 多图: 记录每个步骤的输出, 供 input_from 跨链引用
        self._step_outputs: Dict[str, Any] = {}

    def load_source_image(self, img: np.ndarray):
        """设置原始图像并重置流水线缓存"""
        self.source_image = img
        self.source_gray = ops.rgb1_to_gray(img)
        self.source_hist = ops.calc_histogram(self.source_gray)
        self.source_fp = _compute_image_fingerprint(img)
        self._cache.clear()

    def set_steps(self, steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """更新流水线步骤定义并执行增量重算"""
        self.steps = steps
        return self.execute()

    def execute(self) -> List[Dict[str, Any]]:
        """智能增量执行整个流水线 (严格基于内容与级联指纹哈希)"""
        if self.source_image is None:
            return []

        results = []
        current_data = self.source_image
        h, w = self.source_image.shape[:2]
        self._step_outputs = {"__source__": self.source_image}

        prev_fp = self.source_fp
        cache_valid = True

        # 清理多余步骤的孤儿缓存
        current_step_ids = {s["id"] for s in self.steps}
        for cached_id in list(self._cache.keys()):
            if cached_id not in current_step_ids:
                del self._cache[cached_id]

        for i, step in enumerate(self.steps):
            step_id = step["id"]
            op = step["operator"]
            params = step.get("params", {})
            enabled = step.get("enabled", True)

            # 计算本步骤的级联内容指纹
            cur_fp = _compute_step_fingerprint(prev_fp, op, params, enabled)

            # 若前序全部有效且本步骤缓存指纹完全匹配，则直接复用
            if cache_valid and step_id in self._cache and self._cache[step_id].get("fingerprint") == cur_fp:
                cached_entry = self._cache[step_id]
                current_data = cached_entry["data"]
                results.append(cached_entry["result"])
                self._step_outputs[step_id] = current_data
                prev_fp = cur_fp
                continue

            # 发生缓存未命中 (本步参数被改，或上游步骤被改)，彻底熔断失效后续所有缓存！
            cache_valid = False
            if step_id in self._cache:
                del self._cache[step_id]

            if not enabled:
                # 禁用时直接透传前置数据
                summary = {"status": "skipped", "info": "步骤已禁用"}
                res = StepResult(
                    step_id=step_id,
                    operator=op,
                    duration_ms=0.0,
                    output_type="pass",
                    summary=summary
                )
                self._cache[step_id] = {"fingerprint": cur_fp, "data": current_data, "result": res}
                results.append(res)
                self._step_outputs[step_id] = current_data
                prev_fp = cur_fp
                continue

            # 分支/多图: 若步骤声明 input_from, 则从对应上游步骤的输出取输入
            step_input = current_data
            src_id = params.get("input_from")
            if src_id and isinstance(src_id, str) and src_id in self._step_outputs:
                step_input = self._step_outputs[src_id]
            elif src_id == "__source__":
                step_input = self.source_image

            # 执行该步骤
            t0 = time.perf_counter()
            next_data, res = self._execute_operator(op, params, step_input, (h, w), step_id)
            duration_ms = (time.perf_counter() - t0) * 1000.0
            res.duration_ms = round(duration_ms, 2)

            self._cache[step_id] = {"fingerprint": cur_fp, "data": next_data, "result": res}
            current_data = next_data
            self._step_outputs[step_id] = next_data
            results.append(res)
            prev_fp = cur_fp

        return [self._format_result(r) for r in results]

    def _execute_operator(
        self,
        op: str,
        params: Dict[str, Any],
        input_data: Any,
        base_shape: Tuple[int, int],
        step_id: str
    ) -> Tuple[Any, StepResult]:
        """执行单个具体算子"""
        h, w = base_shape
        gray = self.source_gray if self.source_gray is not None else ops.rgb1_to_gray(self.source_image)

        if op == "read_image":
            # 支持流水线中途读取新图像 (多图/分支); 未给路径时返回原始底图
            img_path = str(params.get("image_path", "")).strip()
            if img_path:
                try:
                    loaded = ops.read_image_from_path(img_path)
                    lh, lw = loaded.shape[:2]
                    lg = ops.rgb1_to_gray(loaded)
                    res = StepResult(
                        step_id=step_id,
                        operator=op,
                        duration_ms=0.0,
                        output_type="image",
                        preview_base64=encode_image_base64(loaded),
                        histogram=ops.calc_histogram(lg),
                        summary={"width": lw, "height": lh, "path": img_path}
                    )
                    return loaded, res
                except Exception as exc:
                    res = StepResult(
                        step_id=step_id, operator=op, duration_ms=0.0,
                        output_type="image", summary={"error": f"读取失败: {exc}", "path": img_path}
                    )
                    return input_data, res
            # 返回原始底图
            summary = {"width": w, "height": h, "channels": 3 if len(self.source_image.shape) == 3 else 1}
            res = StepResult(
                step_id=step_id,
                operator=op,
                duration_ms=0.0,
                output_type="image",
                preview_base64=encode_image_base64(self.source_image),
                histogram=self.source_hist,
                summary=summary
            )
            return self.source_image, res

        elif op == "rgb1_to_gray":
            gray_res = ops.rgb1_to_gray(input_data if isinstance(input_data, np.ndarray) else self.source_image)
            hist = ops.calc_histogram(gray_res)
            res = StepResult(
                step_id=step_id,
                operator=op,
                duration_ms=0.0,
                output_type="image",
                preview_base64=encode_image_base64(gray_res),
                histogram=hist,
                summary={"channels": 1, "mean_gray": round(float(np.mean(gray_res)), 1)}
            )
            return gray_res, res

        elif op == "threshold":
            min_g = int(params.get("min_gray", 0))
            max_g = int(params.get("max_gray", 128))
            target_img = input_data if (isinstance(input_data, np.ndarray) and len(input_data.shape) == 2) else gray
            region = ops.threshold(target_img, min_g, max_g)
            
            color_mask = create_colored_label_mask(region, (h, w))
            mask_b64 = encode_image_base64(color_mask)
            
            area_px = int(np.count_nonzero(region.mask))
            ratio = round(area_px / (h * w) * 100, 2)
            summary = {"area_pixels": area_px, "area_percent": f"{ratio}%", "min_gray": min_g, "max_gray": max_g}
            
            res = StepResult(
                step_id=step_id,
                operator=op,
                duration_ms=0.0,
                output_type="region",
                mask_base64=mask_b64,
                histogram=self.source_hist,
                summary=summary
            )
            return region, res

        elif op == "auto_threshold":
            invert = bool(params.get("invert", False))
            target_img = input_data if (isinstance(input_data, np.ndarray) and len(input_data.shape) == 2) else gray
            region = ops.auto_threshold_otsu(target_img, invert=invert)
            
            color_mask = create_colored_label_mask(region, (h, w))
            mask_b64 = encode_image_base64(color_mask)
            area_px = int(np.count_nonzero(region.mask))
            
            res = StepResult(
                step_id=step_id,
                operator=op,
                duration_ms=0.0,
                output_type="region",
                mask_base64=mask_b64,
                histogram=self.source_hist,
                summary={"method": "Otsu", "area_pixels": area_px, "inverted": invert}
            )
            return region, res

        elif op == "connection":
            conn_type = int(params.get("connectivity", 8))
            if not isinstance(input_data, Region):
                # 若前置不是 Region，先自动进行默认二值化
                input_data = ops.threshold(gray, 0, 128)
                
            region = ops.connection(input_data, connectivity=conn_type)
            color_mask = create_colored_label_mask(region, (h, w))
            mask_b64 = encode_image_base64(color_mask)
            
            summary = {
                "object_count": len(region.objects),
                "connectivity": conn_type,
                "objects_info": [
                    {"id": o.id, "area": o.area, "circularity": round(o.circularity, 3), "bbox": o.bbox}
                    for o in region.objects[:20]  # 前 20 个概览
                ]
            }
            res = StepResult(
                step_id=step_id,
                operator=op,
                duration_ms=0.0,
                output_type="region",
                mask_base64=mask_b64,
                summary=summary
            )
            return region, res

        elif op == "select_shape":
            min_area = int(params.get("min_area", 20))
            max_area = int(params.get("max_area", 999999))
            min_circ = float(params.get("min_circularity", 0.0))
            max_circ = float(params.get("max_circularity", 1.0))
            min_asp = float(params.get("min_aspect", 0.0))
            max_asp = float(params.get("max_aspect", 50.0))
            min_rect = float(params.get("min_rectangularity", 0.0))
            max_rect = float(params.get("max_rectangularity", 1.0))
            hu_match_raw = params.get("hu_match")
            hu_match = None
            if hu_match_raw is not None and str(hu_match_raw).strip() != "":
                try:
                    hu_match = [float(x) for x in str(hu_match_raw).replace(";", ",").split(",") if x.strip() != ""]
                except Exception:
                    hu_match = None
                if hu_match is not None and len(hu_match) != 7:
                    hu_match = None
            max_hu = float(params.get("max_hu_distance", 1.0))

            if not isinstance(input_data, Region):
                input_data = ops.connection(ops.threshold(gray, 0, 128))

            filtered = ops.select_shape(
                input_data,
                min_area=min_area, max_area=max_area,
                min_circularity=min_circ, max_circularity=max_circ,
                min_aspect=min_asp, max_aspect=max_asp,
                min_rectangularity=min_rect, max_rectangularity=max_rect,
                hu_match=hu_match, max_hu_distance=max_hu
            )
            color_mask = create_colored_label_mask(filtered, (h, w))
            mask_b64 = encode_image_base64(color_mask)

            summary = {
                "matched_count": len(filtered.objects),
                "total_before": len(input_data.objects) if input_data.is_connected else "N/A",
                "filter_criteria": {
                    "area": [min_area, max_area],
                    "circularity": [min_circ, max_circ],
                    "aspect_ratio": [min_asp, max_asp]
                },
                "objects": [
                    {
                        "id": o.id,
                        "area": o.area,
                        "circularity": round(o.circularity, 3),
                        "aspect_ratio": round(o.aspect_ratio, 2),
                        "rectangularity": round(o.rectangularity, 3),
                        "centroid": [round(o.centroid[0], 1), round(o.centroid[1], 1)],
                        "bbox": list(o.bbox)
                    } for o in filtered.objects
                ]
            }
            res = StepResult(
                step_id=step_id,
                operator=op,
                duration_ms=0.0,
                output_type="region",
                mask_base64=mask_b64,
                summary=summary
            )
            return filtered, res

        elif op == "morphology":
            op_type = str(params.get("op_type", "opening"))
            kernel_shape = str(params.get("kernel_shape", "circle"))
            kernel_size = int(params.get("kernel_size", 5))

            if not isinstance(input_data, Region):
                input_data = ops.threshold(gray, 0, 128)

            morphed = ops.morphology(input_data, op_type, kernel_shape, kernel_size)
            color_mask = create_colored_label_mask(morphed, (h, w))
            mask_b64 = encode_image_base64(color_mask)

            summary = {
                "operation": op_type,
                "kernel": f"{kernel_shape} ({kernel_size}x{kernel_size})",
                "remaining_area": int(np.count_nonzero(morphed.mask))
            }
            res = StepResult(
                step_id=step_id,
                operator=op,
                duration_ms=0.0,
                output_type="region",
                mask_base64=mask_b64,
                summary=summary
            )
            return morphed, res

        elif op == "filter":
            f_type = str(params.get("filter_type", "gaussian")).lower()
            k_size = int(params.get("kernel_size", 5))
            sigma = float(params.get("sigma", 1.5))

            # 滤波对象: 优先承接上游图像数据, 否则使用底图灰度
            target_img = input_data if isinstance(input_data, np.ndarray) else gray
            filtered = ops.filter_image(target_img, f_type, k_size, sigma)

            gray_filtered = ops.rgb1_to_gray(filtered)
            hist = ops.calc_histogram(gray_filtered)

            k_effective = max(1, k_size)
            if k_effective % 2 == 0:
                k_effective += 1
            if f_type == "median":
                k_effective = max(3, k_effective)

            summary = {
                "filter_type": f_type,
                "kernel_size": k_effective,
                "sigma": round(sigma, 3) if f_type == "gaussian" else None,
                "output_channels": 1 if len(filtered.shape) == 2 else filtered.shape[2]
            }
            res = StepResult(
                step_id=step_id,
                operator=op,
                duration_ms=0.0,
                output_type="image",
                preview_base64=encode_image_base64(filtered),
                histogram=hist,
                summary=summary
            )
            return filtered, res

        elif op == "edges_subpix":
            low_t = float(params.get("low_threshold", 30))
            high_t = float(params.get("high_threshold", 90))

            xld_list = ops.edges_subpix(gray, low_t, high_t)
            # 导出轮廓折线数据给前端矢量 Canvas
            cnts_for_fe = [
                [[p[1], p[0]] for p in x.points]  # [col, row] 即 [x, y] 供 canvas 绘制
                for x in xld_list
            ]
            summary = {
                "contour_count": len(xld_list),
                "total_length": round(sum(x.length for x in xld_list), 2),
                "subpixel_mode": "Sobel-Parabolic-Normal-Interpolation"
            }
            res = StepResult(
                step_id=step_id,
                operator=op,
                duration_ms=0.0,
                output_type="xld",
                contours=cnts_for_fe,
                summary=summary
            )
            return xld_list, res

        elif op == "rgb_to_hsv":
            target_img = input_data if isinstance(input_data, np.ndarray) else self.source_image
            hsv = ops.rgb_to_hsv(target_img)
            # 预览: HSV 三通道拼接为可视化图
            preview = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
            summary = {
                "channels": ["H(0-179)", "S(0-255)", "V(0-255)"],
                "shape": list(hsv.shape)
            }
            res = StepResult(
                step_id=step_id,
                operator=op,
                duration_ms=0.0,
                output_type="image",
                preview_base64=encode_image_base64(preview),
                summary=summary
            )
            return hsv, res

        elif op == "hsv_threshold":
            h_min = int(params.get("h_min", 0))
            h_max = int(params.get("h_max", 179))
            s_min = int(params.get("s_min", 0))
            s_max = int(params.get("s_max", 255))
            v_min = int(params.get("v_min", 0))
            v_max = int(params.get("v_max", 255))

            if isinstance(input_data, np.ndarray) and input_data.ndim == 3:
                hsv_img = input_data
            else:
                hsv_img = ops.rgb_to_hsv(self.source_image)

            region = ops.hsv_threshold(hsv_img, h_min, h_max, s_min, s_max, v_min, v_max)
            color_mask = create_colored_label_mask(region, (h, w))
            mask_b64 = encode_image_base64(color_mask)

            summary = {
                "matched_area": int(np.count_nonzero(region.mask)),
                "hsv_range": {"H": [h_min, h_max], "S": [s_min, s_max], "V": [v_min, v_max]}
            }
            res = StepResult(
                step_id=step_id,
                operator=op,
                duration_ms=0.0,
                output_type="region",
                mask_base64=mask_b64,
                summary=summary
            )
            return region, res

        elif op == "find_shape_model":
            min_score = float(params.get("min_score", 0.5))
            max_matches = int(params.get("max_matches", 10))
            nms_dist = float(params.get("nms_distance", 10.0))
            scales_raw = str(params.get("scales", "1.0"))
            angles_raw = str(params.get("angles", "0"))
            try:
                scales = [float(x) for x in scales_raw.replace(";", ",").split(",") if x.strip()]
            except Exception:
                scales = [1.0]
            try:
                angles = [float(x) for x in angles_raw.replace(";", ",").split(",") if x.strip()]
            except Exception:
                angles = [0.0]

            tmpl = input_data if isinstance(input_data, np.ndarray) else gray
            matches = ops.find_shape_model(
                self.source_image, tmpl,
                min_score=min_score, scales=scales, angles=angles,
                max_matches=max_matches, nms_distance=nms_dist
            )

            annotated = self.source_image.copy()
            for m in matches:
                tl = m["top_left"]
                tw, th = m["template_size"]
                cv2.rectangle(annotated, (tl[0], tl[1]), (tl[0] + tw, tl[1] + th), (0, 215, 255), 1, cv2.LINE_AA)
                cx, cy = int(m["center"][0]), int(m["center"][1])
                cv2.drawMarker(annotated, (cx, cy), (102, 51, 255), markerType=cv2.MARKER_CROSS, markerSize=10, thickness=1)
                cv2.putText(annotated, f"{m['score']:.2f}", (tl[0], max(10, tl[1] - 3)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 204), 1, cv2.LINE_AA)

            summary = {
                "match_count": len(matches),
                "min_score": min_score,
                "scales": scales,
                "angles": angles,
                "matches": matches
            }
            res = StepResult(
                step_id=step_id,
                operator=op,
                duration_ms=0.0,
                output_type="image",
                preview_base64=encode_image_base64(annotated),
                summary=summary
            )
            return annotated, res

        elif op == "gen_contour_polygon":
            epsilon = float(params.get("epsilon", 2.0))
            source = input_data
            if not isinstance(source, Region):
                source = ops.connection(ops.threshold(gray, 0, 128))
            polygons = ops.gen_contour_polygon(source, epsilon)

            annotated = self.source_image.copy()
            colors = [(0, 240, 255), (255, 51, 102), (255, 184, 0), (51, 255, 119), (189, 0, 255)]
            cnts_for_fe = []
            for pi, poly in enumerate(polygons):
                pts = np.array([[p[0], p[1]] for p in poly["corner_points"]], dtype=np.int32)
                if len(pts) >= 2:
                    cv2.polylines(annotated, [pts], True, colors[pi % len(colors)], 1, cv2.LINE_AA)
                for p in poly["corner_points"]:
                    cv2.circle(annotated, (int(p[0]), int(p[1])), 3, (255, 230, 0), -1, cv2.LINE_AA)
                cnts_for_fe.append(poly["corner_points"])

            summary = {
                "polygon_count": len(polygons),
                "epsilon": epsilon,
                "total_corners": int(sum(p["corner_count"] for p in polygons)),
                "polygons": polygons[:50]
            }
            res = StepResult(
                step_id=step_id,
                operator=op,
                duration_ms=0.0,
                output_type="xld",
                contours=cnts_for_fe,
                preview_base64=encode_image_base64(annotated),
                summary=summary
            )
            return polygons, res

        elif op == "read_barcode":
            target_img = input_data if isinstance(input_data, np.ndarray) else self.source_image
            codes = ops.read_barcode(target_img)

            annotated = self.source_image.copy()
            for c in codes:
                for (x, y) in c.get("points", []):
                    cv2.circle(annotated, (int(x), int(y)), 4, (0, 255, 204), -1, cv2.LINE_AA)
                if c.get("points"):
                    p0 = c["points"][0]
                    cv2.putText(annotated, str(c["data"])[:24], (int(p0[0]), max(12, int(p0[1]) - 6)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 51, 102), 1, cv2.LINE_AA)

            summary = {
                "code_count": len(codes),
                "codes": codes
            }
            res = StepResult(
                step_id=step_id,
                operator=op,
                duration_ms=0.0,
                output_type="image",
                preview_base64=encode_image_base64(annotated),
                summary=summary
            )
            return annotated, res

        elif op == "calibrate":
            cols = int(params.get("pattern_cols", 9))
            rows = int(params.get("pattern_rows", 6))
            square = float(params.get("square_size", 1.0))
            target_img = input_data if isinstance(input_data, np.ndarray) else self.source_image
            calib = ops.estimate_scale_from_checkerboard(target_img, cols, rows, square)

            annotated = self.source_image.copy()
            for (x, y) in calib.get("corners", []):
                cv2.circle(annotated, (int(x), int(y)), 3, (0, 215, 255), -1, cv2.LINE_AA)

            summary = {
                "calibration_found": calib.get("found", False),
                "pixels_per_unit": calib.get("pixels_per_unit"),
                "avg_square_pixels": calib.get("avg_square_pixels"),
                "square_size": square
            }
            res = StepResult(
                step_id=step_id,
                operator=op,
                duration_ms=0.0,
                output_type="image",
                preview_base64=encode_image_base64(annotated),
                summary=summary
            )
            return calib, res

        elif op == "read_text":
            lang = str(params.get("lang", "eng"))
            target_img = input_data if isinstance(input_data, np.ndarray) else self.source_image
            try:
                text = ops.read_text(target_img, lang)
                error = None
            except Exception as exc:
                text = ""
                error = str(exc)
            summary = {
                "text": text,
                "lang": lang,
                "engine": "Tesseract (pytesseract)",
                "error": error
            }
            res = StepResult(
                step_id=step_id,
                operator=op,
                duration_ms=0.0,
                output_type="text",
                summary=summary
            )
            return text, res

        elif op == "measure_region":
            if not isinstance(input_data, Region):
                input_data = ops.connection(ops.threshold(gray, 0, 128))

            measurements = ops.measure_region(input_data)
            color_mask = create_colored_label_mask(input_data, (h, w))
            mask_b64 = encode_image_base64(color_mask)

            # 在原图上绘制 HALCON 风格的几何测量注记 (OBB 旋转矩形 + 最小外接圆 + 重心十字)
            annotated = self.source_image.copy()
            for item in measurements.get("objects", []):
                # 绘制旋转外接矩形 OBB (亮金黄色)
                box_pts = item["smallest_rectangle2"]["box_points"]
                pts_arr = np.array([[int(p[1]), int(p[0])] for p in box_pts], dtype=np.int32)
                cv2.polylines(annotated, [pts_arr], isClosed=True, color=(0, 215, 255), thickness=1, lineType=cv2.LINE_AA)

                # 绘制最小外接圆 (翠绿色)
                cc = item["smallest_circle"]["center"]
                cr = int(item["smallest_circle"]["radius"])
                cv2.circle(annotated, (int(cc[1]), int(cc[0])), cr, (119, 255, 51), thickness=1, lineType=cv2.LINE_AA)

                # 绘制重心十字 (霓虹红)
                cy, cx = int(item["centroid"][0]), int(item["centroid"][1])
                cv2.drawMarker(annotated, (cx, cy), (102, 51, 255), markerType=cv2.MARKER_CROSS, markerSize=10, thickness=1)

            objects_for_summary = [
                {
                    "id": o["id"],
                    "area": o["area"],
                    "centroid": o["centroid"],
                    "bbox": o["bbox_aabb"],
                    "circularity": o["circularity"],
                    "convexity": o["convexity"],
                    "compactness": o["compactness"],
                    "smallest_rectangle2": o["smallest_rectangle2"],
                    "smallest_circle": o["smallest_circle"],
                    "elliptic_axis": o["elliptic_axis"]
                }
                for o in measurements["objects"]
            ]

            summary = {
                "object_count": measurements["object_count"],
                "global_summary": measurements["summary"],
                "objects": objects_for_summary[:50]
            }

            res = StepResult(
                step_id=step_id,
                operator=op,
                duration_ms=0.0,
                output_type="region",
                preview_base64=encode_image_base64(annotated),
                mask_base64=mask_b64,
                summary=summary
            )
            return input_data, res



        elif op == "reduce_domain":
            # ROI: 由几何形状生成掩膜并归约图像 (区域外置为 fill_value, 画布尺寸不变)
            geometry = params.get("geometry")
            if geometry is None:
                rtype = str(params.get("roi_type", "rect")).lower()
                geometry = {"type": rtype}
                if rtype == "circle":
                    geometry.update({"cx": params.get("cx", w // 2), "cy": params.get("cy", h // 2),
                                     "r": params.get("r", min(h, w) // 4)})
                elif rtype == "polygon":
                    geometry.update({"points": params.get("points", [])})
                else:
                    geometry.update({"x": params.get("x", 0), "y": params.get("y", 0),
                                     "w": params.get("w", w), "h": params.get("h", h)})
            base_img = input_data if isinstance(input_data, np.ndarray) else self.source_image
            region = ops.create_mask_from_geometry((h, w), geometry)
            reduced = ops.reduce_domain(base_img, region, fill_value=int(params.get("fill_value", 0)))
            gray_r = ops.rgb1_to_gray(reduced)
            summary = {
                "roi_type": geometry.get("type"),
                "roi_area_pixels": int(np.count_nonzero(region.mask)),
                "geometry": geometry
            }
            res = StepResult(
                step_id=step_id,
                operator=op,
                duration_ms=0.0,
                output_type="image",
                preview_base64=encode_image_base64(reduced),
                mask_base64=encode_image_base64(create_colored_label_mask(region, (h, w))),
                histogram=ops.calc_histogram(gray_r),
                summary=summary
            )
            return reduced, res

        elif op == "measure_pos":
            # 一维卡尺测量: 沿测量线定位亚像素边缘点
            x0 = float(params.get("x0", 0))
            y0 = float(params.get("y0", 0))
            x1 = float(params.get("x1", max(1, w - 1)))
            y1 = float(params.get("y1", max(1, h - 1)))
            sigma_m = float(params.get("sigma", 1.0))
            thr = float(params.get("threshold", 20.0))
            sel = str(params.get("select", "all"))
            target_img = input_data if isinstance(input_data, np.ndarray) else self.source_image
            edges = ops.measure_pos(target_img, x0, y0, x1, y1, sigma_m, thr, sel)

            annotated = self.source_image.copy()
            cv2.line(annotated, (int(x0), int(y0)), (int(x1), int(y1)), (0, 215, 255), 1, cv2.LINE_AA)
            for e in edges:
                cv2.circle(annotated, (int(round(e["x"])), int(round(e["y"]))), 3, (102, 51, 255), -1, cv2.LINE_AA)

            span = None
            if len(edges) >= 2:
                span = round(float(np.hypot(edges[-1]["x"] - edges[0]["x"],
                                            edges[-1]["y"] - edges[0]["y"])), 3)
            summary = {
                "edge_count": len(edges),
                "edges": edges[:50],
                "span_distance": span,
                "select": sel,
                "measure_line": [x0, y0, x1, y1]
            }
            res = StepResult(
                step_id=step_id,
                operator=op,
                duration_ms=0.0,
                output_type="xld",
                preview_base64=encode_image_base64(annotated),
                contours=[[[round(e["x"], 3), round(e["y"], 3)] for e in edges]],
                summary=summary
            )
            return edges, res

        elif op == "merge_images":
            # 多图/分支汇聚: 合并当前链图像与 input_from 指向的支路图像
            mode = str(params.get("mode", "blend"))
            alpha = float(params.get("alpha", 0.5))
            img_a = input_data if isinstance(input_data, np.ndarray) else self.source_image
            src_id = params.get("input_from")
            other = None
            if src_id and src_id in getattr(self, "_step_outputs", {}):
                other = self._step_outputs[src_id]
            if not isinstance(other, np.ndarray):
                other = self.source_image
            merged = ops.merge_images(img_a, other, mode=mode, alpha=alpha)
            gray_m = ops.rgb1_to_gray(merged)
            summary = {"mode": mode, "alpha": alpha, "input_from": src_id,
                       "output_shape": list(merged.shape)}
            res = StepResult(
                step_id=step_id,
                operator=op,
                duration_ms=0.0,
                output_type="image",
                preview_base64=encode_image_base64(merged),
                histogram=ops.calc_histogram(gray_m),
                summary=summary
            )
            return merged, res

        elif op == "onnx_inference":
            # 深度学习推理节点 (可选 onnxruntime, 缺失时优雅降级)
            model_path = str(params.get("model_path", "")).strip()
            task = str(params.get("task", "classification"))
            top_k = int(params.get("top_k", 5))
            target_img = input_data if isinstance(input_data, np.ndarray) else self.source_image
            try:
                out = ops.onnx_inference(target_img, model_path, task=task, top_k=top_k)
                err = None
            except Exception as exc:
                out = {"status": "unavailable", "model": model_path}
                err = str(exc)
            summary = {"result": out, "error": err, "task": task, "model_path": model_path}
            res = StepResult(
                step_id=step_id,
                operator=op,
                duration_ms=0.0,
                output_type="text",
                summary=summary
            )
            return out, res

        else:
            # 未知算子
            res = StepResult(
                step_id=step_id,
                operator=op,
                duration_ms=0.0,
                output_type="unknown",
                summary={"error": f"未支持算子: {op}"}
            )
            return input_data, res

    def _format_result(self, r: StepResult) -> Dict[str, Any]:
        return {
            "step_id": r.step_id,
            "operator": r.operator,
            "duration_ms": r.duration_ms,
            "output_type": r.output_type,
            "preview_base64": r.preview_base64,
            "mask_base64": r.mask_base64,
            "histogram": r.histogram,
            "summary": r.summary,
            "contours": r.contours
        }
