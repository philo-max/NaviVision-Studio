"""
NaviVision Studio - Isolated Script Runner Subprocess Worker
由 core.script_runner 通过独立子进程拉起，隔离内存空间与主服务
"""

import sys
import io
import time
import traceback
import pickle
import cv2
import numpy as np
import math
import json
from typing import Dict, Any, Optional

from core import operators as ops
from core.pipeline import encode_image_base64, create_colored_label_mask
from core.types import Region


def main():
    try:
        raw_data = sys.stdin.buffer.read()
        if not raw_data:
            return
        payload = pickle.loads(raw_data)
    except Exception as e:
        sys.stderr.write(f"Worker unpack error: {e}\n")
        sys.exit(1)

    code_str = payload.get("code", "")
    source_image = payload.get("source_image")
    source_gray = payload.get("source_gray")

    if source_image is None:
        res = {"success": False, "error": "当前未载入任何底图", "stdout": "", "duration_ms": 0.0}
        sys.stdout.buffer.write(pickle.dumps(res))
        return

    h, w = source_image.shape[:2]
    gray_img = source_gray if source_gray is not None else ops.rgb1_to_gray(source_image)

    import builtins
    b_dict = builtins.__dict__ if hasattr(builtins, "__dict__") else (
        __builtins__ if isinstance(__builtins__, dict) else vars(__builtins__)
    )
    unsafe_names = {
        "open", "eval", "exec", "compile", "input", "__import__",
        "globals", "locals", "help", "quit", "exit", "breakpoint"
    }
    safe_builtins = {
        k: v for k, v in b_dict.items()
        if k not in unsafe_names
    }

    exec_globals = {
        "__builtins__": safe_builtins,
        "cv2": cv2,
        "np": np,
        "numpy": np,
        "math": math,
        "json": json,
        "ops": ops,
        "image": source_image.copy(),
        "gray": gray_img.copy(),
        "result_image": None,
        "result_mask": None,
        "result_contours": None,
        "result_data": None
    }

    old_stdout = sys.stdout
    old_stderr = sys.stderr
    redirected_output = io.StringIO()
    sys.stdout = redirected_output
    sys.stderr = redirected_output

    t0 = time.perf_counter()
    success = True
    error_msg = None

    try:
        exec(code_str, exec_globals)
    except Exception as e:
        success = False
        error_msg = traceback.format_exc()
        print(f"\n[EXECUTION ERROR]\n{error_msg}")
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    stdout_text = redirected_output.getvalue()

    if not success:
        out = {
            "success": False,
            "duration_ms": duration_ms,
            "error": error_msg,
            "stdout": stdout_text
        }
        sys.stdout.buffer.write(pickle.dumps(out))
        return

    # 提取输出变量
    res_img = exec_globals.get("result_image")
    res_mask = exec_globals.get("result_mask")
    res_cnts = exec_globals.get("result_contours")
    res_data = exec_globals.get("result_data")

    preview_b64 = None
    mask_b64 = None
    contours_list = []
    objects_list = []

    # 1. 图像输出
    if isinstance(res_img, np.ndarray):
        preview_b64 = encode_image_base64(res_img)

    # 2. 掩膜输出
    if isinstance(res_mask, Region):
        color_mask = create_colored_label_mask(res_mask, (h, w))
        mask_b64 = encode_image_base64(color_mask)
        objects_list = [
            {"id": o.id, "area": o.area, "circularity": round(o.circularity, 3), "bbox": o.bbox, "centroid": o.centroid}
            for o in res_mask.objects
        ]
    elif isinstance(res_mask, np.ndarray):
        if len(res_mask.shape) == 3:
            res_mask = cv2.cvtColor(res_mask, cv2.COLOR_BGR2GRAY)
        connected_reg = ops.connection(Region(mask=res_mask), connectivity=8)
        color_mask = create_colored_label_mask(connected_reg, (h, w))
        mask_b64 = encode_image_base64(color_mask)
        objects_list = [
            {"id": o.id, "area": o.area, "circularity": round(o.circularity, 3), "bbox": o.bbox, "centroid": o.centroid}
            for o in connected_reg.objects
        ]

    # 3. 轮廓输出
    if isinstance(res_cnts, list):
        for c in res_cnts:
            if isinstance(c, np.ndarray):
                pts = [[float(p[0][0]), float(p[0][1])] for p in c]
                contours_list.append(pts)
            elif isinstance(c, list):
                contours_list.append(c)

    out = {
        "success": True,
        "duration_ms": duration_ms,
        "stdout": stdout_text,
        "preview_base64": preview_b64,
        "mask_base64": mask_b64,
        "contours": contours_list,
        "objects": objects_list,
        "custom_data": res_data
    }
    sys.stdout.buffer.write(pickle.dumps(out))


if __name__ == "__main__":
    main()
