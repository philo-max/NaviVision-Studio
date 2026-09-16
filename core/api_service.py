"""
NaviVision Studio (OpenDevelop) - REST API Service
为外部工业工控机、PLC、MES 系统与云端服务提供标准推理接口
"""

import time
import cv2
import numpy as np
from typing import Dict, Any, List
from core.pipeline import Pipeline, encode_image_base64
from core import operators as ops


def run_pipeline_inference(
    pipeline: Pipeline,
    input_image: np.ndarray,
    custom_steps: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """对传入的图片执行当前流水线推理并返回标准化工业遥测 JSON"""
    t0 = time.perf_counter()
    h, w = input_image.shape[:2]

    inference_pipeline = Pipeline()
    inference_pipeline.load_source_image(input_image)
    if custom_steps:
        results = inference_pipeline.set_steps(custom_steps)
    else:
        results = inference_pipeline.set_steps(pipeline.steps)

    duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    # 寻找最终步骤的 Mask 与提取的对象
    final_res = results[-1] if results else None
    objects = []
    mask_b64 = None

    for r in reversed(results):
        if r.get("mask_base64"):
            mask_b64 = r["mask_base64"]
            objects = r.get("summary", {}).get("objects") or r.get("summary", {}).get("objects_info") or []
            break

    return {
        "status": "success",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_ms": duration_ms,
        "image_size": {"width": w, "height": h},
        "object_count": len(objects),
        "objects": objects,
        "step_timings": [{"operator": r["operator"], "ms": r["duration_ms"]} for r in results],
        "mask_preview": mask_b64
    }
