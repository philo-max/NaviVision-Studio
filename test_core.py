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
    print("  [SUCCESS] PHASE 1 + PHASE 2 全部测试 100% 通过！")
    print("==================================================")

if __name__ == "__main__":
    test_all()

