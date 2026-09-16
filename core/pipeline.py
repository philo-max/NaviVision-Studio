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


def create_colored_label_mask(region: Region, base_shape: Tuple[int, int]) -> np.ndarray:
    """为连通域渲染高对比色彩叠加层 (仿 HALCON 彩色多通道 Region 显示)"""
    h, w = base_shape[:2]
    color_mask = np.zeros((h, w, 4), dtype=np.uint8)  # RGBA
    
    if not region.is_connected or not region.objects:
        # 单一区域，使用标志性亮荧光青色 (Cyan)
        y_idx, x_idx = np.where(region.mask > 0)
        color_mask[y_idx, x_idx] = [0, 240, 255, 140]  # R, G, B, Alpha
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
        sub_mask = region.mask[y:y2, x:x2]
        yy, xx = np.where(sub_mask > 0)
        color_mask[y + yy, x + xx] = [color[0], color[1], color[2], 160]
        
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
                prev_fp = cur_fp
                continue

            # 执行该步骤
            t0 = time.perf_counter()
            next_data, res = self._execute_operator(op, params, current_data, (h, w), step_id)
            duration_ms = (time.perf_counter() - t0) * 1000.0
            res.duration_ms = round(duration_ms, 2)

            self._cache[step_id] = {"fingerprint": cur_fp, "data": next_data, "result": res}
            current_data = next_data
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

            if not isinstance(input_data, Region):
                input_data = ops.connection(ops.threshold(gray, 0, 128))

            filtered = ops.select_shape(
                input_data,
                min_area=min_area, max_area=max_area,
                min_circularity=min_circ, max_circularity=max_circ,
                min_aspect=min_asp, max_aspect=max_asp
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
                        "centroid": [round(o.centroid[0], 1), round(o.centroid[1], 1)]
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
