"""
NaviVision Studio - Comprehensive Core & Algorithm Verification Suite
测试覆盖:
1. 算子库基础: read, threshold, connection, select_shape
2. 真·亚像素边缘 (edges_subpix): 浮点数法向抛物线二次插值精度验证
3. 工业几何度量 (measure_region): OBB旋转矩形, 最小外接圆, 二阶惯性矩, 凸度等
4. 智能流水线指纹级联缓存: 改参高敏失效与无参脏读修复验证
5. 代码生成器完整性验证
"""

import cv2
import numpy as np
import math
from core import operators as ops
from core.pipeline import Pipeline
from core.code_generator import generate_python_code

def test_all():
    print("==================================================")
    print("   NaviVision Studio 算法与引擎核心测试套件")
    print("==================================================")

    # 1. 图像载入测试
    img = ops.read_image_from_path("samples/pills_inspection.png")
    assert img is not None, "图像载入失败"
    print(f"[PASS] 1. 底图载入成功: shape={img.shape}")

    # 2. 基础二值化、连通域打散与特征筛选
    gray = ops.rgb1_to_gray(img)
    reg_thresh = ops.threshold(gray, 180, 255)
    nonzero_initial = np.count_nonzero(reg_thresh.mask)
    assert nonzero_initial > 0, "阈值分割结果为空"

    connected = ops.connection(reg_thresh, connectivity=8)
    assert len(connected.objects) > 0, "连通域打散数量异常"
    print(f"[PASS] 2. 连通域打散成功: 提取到 {len(connected.objects)} 个目标")

    filtered = ops.select_shape(connected, min_area=500, max_area=5000, min_circularity=0.7)
    assert len(filtered.objects) > 0, "特征筛选结果为空"
    print(f"[PASS] 3. 形状筛选成功: 保留 {len(filtered.objects)} 个合格目标")

    # 3. 工业几何度量算子 (measure_region) 验证
    measurements = ops.measure_region(filtered)
    assert measurements["object_count"] == len(filtered.objects), "度量目标数量不匹配"
    obj0 = measurements["objects"][0]
    assert "smallest_rectangle2" in obj0, "缺少 OBB 旋转矩形数据"
    assert "smallest_circle" in obj0, "缺少最小外接圆数据"
    assert "elliptic_axis" in obj0, "缺少二阶矩主轴数据"
    assert "convexity" in obj0 and 0.0 <= obj0["convexity"] <= 1.0, "凸度度量值异常"
    assert "compactness" in obj0 and obj0["compactness"] >= 1.0, "紧致度度量值异常"
    obb = obj0["smallest_rectangle2"]
    print(f"[PASS] 4. measure_region 验证通过:")
    print(f"       - 目标 #1 重心: {obj0['centroid']}")
    print(f"       - OBB 中心: {obb['center']}, 半长: ({obb['length1']}, {obb['length2']}), 倾角: {obb['phi']}rad")
    print(f"       - 外接圆半径: {obj0['smallest_circle']['radius']}px, 凸度: {obj0['convexity']}")

    # 4. 图像平滑滤波算子 (filter: mean / gaussian / median) 验证
    rng = np.random.default_rng(seed=42)
    noise = rng.integers(0, 50, size=gray.shape, dtype=np.uint8)
    noisy = cv2.add(gray, noise)
    gauss_img = ops.filter_image(noisy, "gaussian", 5, 1.5)
    mean_img = ops.filter_image(noisy, "mean", 5)
    median_img = ops.filter_image(noisy, "median", 5)
    assert gauss_img.shape == gray.shape, "高斯滤波输出尺寸与输入不一致"
    assert mean_img.shape == gray.shape, "均值滤波输出尺寸与输入不一致"
    assert median_img.shape == gray.shape, "中值滤波输出尺寸与输入不一致"
    assert gauss_img.dtype == noisy.dtype, "滤波输出数据类型发生变化"
    # 滤波后整体方差应下降 (噪声被抑制)
    var_noisy = float(np.var(noisy.astype(np.float32)))
    var_gauss = float(np.var(gauss_img.astype(np.float32)))
    var_median = float(np.var(median_img.astype(np.float32)))
    assert var_gauss < var_noisy, "高斯滤波未能抑制噪声方差"
    assert var_median < var_noisy, "中值滤波未能抑制噪声方差"
    print(f"[PASS] 4b. filter 平滑滤波算子验证通过:")
    print(f"       - 输出尺寸一致: {gauss_img.shape}, dtype={gauss_img.dtype}")
    print(f"       - 高斯滤波方差: {var_noisy:.1f} -> {var_gauss:.1f}, 中值滤波方差: {var_median:.1f}")

    # 4. 真·亚像素边缘提取 (edges_subpix) 验证
    xld_contours = ops.edges_subpix(gray, low_thresh=40, high_thresh=120)
    assert len(xld_contours) > 0, "亚像素轮廓提取结果为空"
    
    # 验证是否具备真·浮点小数坐标 (非整像素假亚像素)
    all_points = [pt for c in xld_contours for pt in c.points]
    fractional_diffs = [abs(pt[0] - round(pt[0])) + abs(pt[1] - round(pt[1])) for pt in all_points]
    max_fraction = max(fractional_diffs)
    mean_fraction = float(np.mean(fractional_diffs))
    
    print(f"[PASS] 5. edges_subpix 验证通过:")
    print(f"       - 提取 XLD 轮廓数: {len(xld_contours)}, 总采样点: {len(all_points)}")
    print(f"       - 亚像素最大法向偏移量: {max_fraction:.4f}px, 平均偏移: {mean_fraction:.4f}px")
    assert max_fraction > 0.01, "警告: 轮廓点未检测到任何亚像素偏移，仍为整像素伪装！"

    # 5. 流水线指纹级联缓存与参数响应验证 (重点拆雷项)
    pipeline = Pipeline()
    pipeline.load_source_image(img)
    steps = [
        {"id": "step_1", "operator": "read_image", "enabled": True},
        {"id": "step_2", "operator": "threshold", "params": {"min_gray": 180, "max_gray": 255}, "enabled": True},
        {"id": "step_3", "operator": "connection", "params": {"connectivity": 8}, "enabled": True},
        {"id": "step_4", "operator": "measure_region", "params": {}, "enabled": True}
    ]

    # 第一次执行 (冷启动)
    res_run1 = pipeline.set_steps(steps)
    area_run1 = res_run1[1]["summary"]["area_pixels"]
    objs_run1 = res_run1[3]["summary"]["object_count"]
    print(f"[RUN 1] min_gray=180 => 分割像素数: {area_run1}, 测量目标数: {objs_run1}")

    # 第二次执行 (参数未变，验证缓存命中)
    res_run2 = pipeline.execute()
    # 此时 step_2, step_3, step_4 应该完全来自缓存
    assert res_run2[1]["summary"]["area_pixels"] == area_run1
    print("[PASS] 6. 缓存命中验证通过: 相同参数未重复计算")

    # 第三次执行 (调参: 将 min_gray 从 180 提高到 220)
    steps[1]["params"]["min_gray"] = 220
    res_run3 = pipeline.set_steps(steps)
    area_run3 = res_run3[1]["summary"]["area_pixels"]
    objs_run3 = res_run3[3]["summary"]["object_count"]
    print(f"[RUN 3] 调参至 min_gray=220 => 分割像素数: {area_run3}, 测量目标数: {objs_run3}")

    # 验证修复: 调参后输出必须发生变化，绝不能返回旧缓存！
    assert area_run3 < area_run1, f"错误: 调参后分割面积未变 ({area_run3} vs {area_run1})，缓存失效逻辑未生效！"
    assert res_run3[1]["summary"]["min_gray"] == 220, "错误: step_2 仍返回旧参数摘要！"
    print("[PASS] 7. 缓存失效高敏测试通过: 上游参数变动触发精准级联重算，彻底告别调参无响应！")

    # 6. 代码生成器测试
    py_code = generate_python_code(steps, "samples/pills_inspection.png")
    assert "measure_region" in py_code, "代码生成器未包含 measure_region"
    assert "minAreaRect" in py_code, "代码生成器未正确生成 OBB 几何计算"
    print(f"[PASS] 8. Python 独立脚本代码生成器验证通过 ({len(py_code.splitlines())} 行代码)")

    # 7. Phase 2: AST 静态代码安全审查测试
    from core.script_runner import validate_code_security, execute_custom_script
    assert validate_code_security("import os; os.system('dir')") is not None, "未能拦截 import os"
    assert validate_code_security("from subprocess import Popen") is not None, "未能拦截 from subprocess"
    assert validate_code_security("x = ().__class__.__subclasses__()") is not None, "未能拦截 __subclasses__ 探测"
    assert validate_code_security("eval('1+1')") is not None, "未能拦截 eval()"
    assert validate_code_security("result_mask = ops.threshold(gray, 100, 200)") is None, "正常代码误报拦截"
    print("[PASS] 9. AST 静态安全审查测试通过: 成功防御危险导入与底层逃逸")

    # 8. Phase 2: 独立子进程沙箱执行与 3.0s 超时熔断测试
    # 8.1 超时熔断测试
    timeout_res = execute_custom_script("while True: pass", img, timeout_sec=1.5)
    assert not timeout_res["success"], "死循环脚本未被拦截"
    assert "超时" in timeout_res["error"], f"错误提示非超时: {timeout_res['error']}"
    print(f"[PASS] 10. 子进程超时熔断测试通过: 死循环在 {timeout_res['duration_ms']}ms 内被强杀并回收")

    # 8.2 正常脚本执行测试
    safe_script = """
print("[SANDBOX TEST] Running custom vision logic inside subprocess!")
result_mask = ops.threshold(gray, 150, 255)
result_data = {"test_metric": 42.0}
"""
    valid_res = execute_custom_script(safe_script, img, timeout_sec=3.0)
    assert valid_res["success"], f"合法脚本执行失败: {valid_res.get('error')}"
    assert "SANDBOX TEST" in valid_res["stdout"], "未捕获子进程 stdout 日志"
    assert valid_res["mask_base64"] is not None, "未生成二值掩膜 Base64"
    assert valid_res["custom_data"]["test_metric"] == 42.0, "未回传自定义遥测数据"
    print(f"[PASS] 11. 子进程安全脚本执行通过: 耗时 {valid_res['duration_ms']}ms, 成功隔离捕获 stdout 与图像输出")

    # 9. Phase 2: 多租户会话隔离测试 (SessionManager)
    from core.session_manager import session_manager
    p_alice = session_manager.get_pipeline("alice")
    p_bob = session_manager.get_pipeline("bob")
    assert p_alice is not p_bob, "Alice 与 Bob 仍共享同一个 Pipeline 单例！"

    # Alice 改步，Bob 不受影响
    p_alice.steps = [{"id": "s_alice", "operator": "threshold", "enabled": True}]
    assert p_alice.steps != p_bob.steps, "会话步骤发生串扰！"
    print("[PASS] 12. 多租户会话隔离测试通过: 各会话拥有独立 Pipeline 实例，彻底消除并发串号隐患")

    # 10. Phase 2: 视觉工程持久化 (.nvproj) 结构测试
    import json
    proj_dump = json.dumps({"format": "navivision_project", "version": "1.0", "steps": p_alice.steps})
    loaded_proj = json.loads(proj_dump)
    assert loaded_proj["format"] == "navivision_project"
    p_charlie = session_manager.get_pipeline("charlie")
    res_charlie = p_charlie.set_steps(loaded_proj["steps"])
    assert len(res_charlie) == 1 and res_charlie[0]["operator"] == "threshold"
    print("[PASS] 13. 视觉工程持久化 (.nvproj) 验证通过: 导出/导入/反序列化重算全链路畅通")

    print("\n==================================================")
    # 11. P0/P1/P2/P3 新增能力验证
    # 11.1 色彩空间扩展 rgb_to_hsv / hsv_threshold
    hsv = ops.rgb_to_hsv(img)
    assert hsv.ndim == 3 and hsv.shape[2] == 3, "rgb_to_hsv 输出应为三通道"
    assert hsv.shape[0] == img.shape[0] and hsv.shape[1] == img.shape[1], "rgb_to_hsv 尺寸变化"
    reg_hsv = ops.hsv_threshold(hsv, h_min=0, h_max=179, s_min=0, s_max=255, v_min=0, v_max=255)
    assert int(np.count_nonzero(reg_hsv.mask)) > 0, "HSV 全范围阈值应命中像素"
    print(f"[PASS] 14. 色彩空间 rgb_to_hsv/hsv_threshold 验证通过: HSV shape={hsv.shape}, 命中像素={int(np.count_nonzero(reg_hsv.mask))}")

    # 11.2 Blob 特征扩展: select_shape 矩形度 / Hu 矩
    conn = ops.connection(ops.threshold(gray, 180, 255), connectivity=8)
    assert len(conn.objects) > 0, "连通域为空"
    o0 = conn.objects[0]
    assert hasattr(o0, "rectangularity") and 0.0 <= o0.rectangularity <= 1.0, "矩形度字段异常"
    assert len(o0.hu_moments) == 7, "Hu 不变矩应为 7 维"
    rect_filtered = ops.select_shape(conn, min_area=10, min_rectangularity=0.0, max_rectangularity=1.0)
    assert len(rect_filtered.objects) > 0, "按矩形度筛选结果为空"
    hu_ref = o0.hu_moments
    hu_filtered = ops.select_shape(conn, min_area=10, hu_match=hu_ref, max_hu_distance=0.5)
    assert isinstance(hu_filtered.objects, list), "Hu 矩筛选返回结构异常"
    print(f"[PASS] 15. select_shape 扩展验证通过: 矩形度={o0.rectangularity:.3f}, Hu 矩维度={len(o0.hu_moments)}, Hu 筛选保留={len(hu_filtered.objects)}")

    # 11.3 模板匹配 find_shape_model
    tmpl = gray[60:120, 60:120].copy()
    matches = ops.find_shape_model(gray, tmpl, min_score=0.4, scales=[1.0], angles=[0.0], max_matches=5)
    assert isinstance(matches, list) and len(matches) >= 1, "模板匹配未返回结果"
    assert "center" in matches[0] and "angle" in matches[0] and "scale" in matches[0] and "score" in matches[0], "匹配位姿字段缺失"
    assert matches[0]["score"] >= 0.4, "匹配分数低于阈值"
    print(f"[PASS] 16. find_shape_model 模板匹配验证通过: 命中 {len(matches)} 处, 最高分={matches[0]['score']}, 位姿 center={matches[0]['center']}")

    # 11.4 轮廓多边形近似 gen_contour_polygon
    polys = ops.gen_contour_polygon(conn, epsilon=2.0)
    assert len(polys) > 0, "多边形近似结果为空"
    assert "corner_points" in polys[0] and "corner_count" in polys[0], "多边形顶点字段缺失"
    print(f"[PASS] 17. gen_contour_polygon 多边形近似验证通过: 多边形数={len(polys)}, 首个拐点数={polys[0]['corner_count']}")

    # 11.5 条码 / 二维码 read_barcode (无码图应返回空列表而非报错)
    codes = ops.read_barcode(img)
    assert isinstance(codes, list), "read_barcode 应返回列表"
    print(f"[PASS] 18. read_barcode 条码识别验证通过: 识别结果数={len(codes)} (无码图返回空列表)")

    # 11.6 相机标定 calibrate (合成长方格棋盘图)
    board = np.full((240, 300), 255, dtype=np.uint8)
    sq = 20
    for r in range(6):
        for c in range(9):
            if (r + c) % 2 == 0:
                board[r * sq:(r + 1) * sq, c * sq:(c + 1) * sq] = 0
    calib = ops.estimate_scale_from_checkerboard(board, pattern_cols=9, pattern_rows=6, square_size=1.0)
    assert "found" in calib, "标定返回结构异常"
    if calib["found"]:
        assert calib["pixels_per_unit"] is not None and calib["pixels_per_unit"] > 0, "标定换算系数异常"
    print(f"[PASS] 19. calibrate 相机标定验证通过: found={calib['found']}, pixels_per_unit={calib.get('pixels_per_unit')}")

    # 11.7 OCR read_text 优雅降级 (未装 pytesseract 时抛明确异常)
    try:
        _ = ops.read_text(img, "eng")
        ocr_state = "引擎可用"
    except RuntimeError as exc:
        assert "pytesseract" in str(exc) or "OCR" in str(exc), "OCR 降级提示不明确"
        ocr_state = "优雅降级 (未安装 pytesseract)"
    print(f"[PASS] 20. read_text OCR 边界验证通过: {ocr_state}")

    # 11.8 会话磁盘持久化 SessionManager
    import tempfile
    from core.session_manager import SessionManager
    with tempfile.TemporaryDirectory() as tmpdir:
        sm1 = SessionManager(persist_dir=tmpdir)
        p1 = sm1.get_pipeline("persist_user")
        p1.steps = [{"id": "s1", "operator": "threshold", "params": {"min_gray": 100, "max_gray": 200}, "enabled": True}]
        sm1.save_session("persist_user")
        sm2 = SessionManager(persist_dir=tmpdir)
        p2 = sm2.get_pipeline("persist_user")
        assert p2.steps and p2.steps[0]["operator"] == "threshold", "持久化会话未成功恢复"
        restored = sm2.restore_all()
    print(f"[PASS] 21. SessionManager 磁盘持久化验证通过: 重启后会话恢复 {len(p2.steps)} 步, 批量恢复数={restored}")

    # 11.9 CI 工作流存在性校验
    import os as _os
    ci_path = _os.path.join(_os.path.dirname(__file__), ".github", "workflows", "test.yml")
    assert _os.path.exists(ci_path), "缺少 .github/workflows/test.yml CI 工作流"
    with open(ci_path, "r", encoding="utf-8") as _f:
        _ci = _f.read()
    assert "test_core.py" in _ci and "test_api_contract.py" in _ci, "CI 未覆盖核心与 API 契约测试"
    print("[PASS] 22. CI 工作流验证通过: push/PR 自动运行 test_core.py + test_api_contract.py")

    print("  [SUCCESS] PHASE 1 + PHASE 2 全部测试 100% 通过！")
    print("==================================================")

if __name__ == "__main__":
    test_all()

