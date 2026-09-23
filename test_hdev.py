"""
NaviVision Studio - HDevelop DSL Engine Test Suite
验证 HDevelop 语言解析器、解释执行沙箱、双向转译器与 REST API 契约
"""

import unittest
import os
import sys
import math
import numpy as np
from pathlib import Path
from fastapi.testclient import TestClient

from core.hdev_engine import HDevParser, HDevInterpreter, HDevTranspiler, HDEV_SIGNATURES
from core import operators as ops
from core.types import XLDContour
from app import app


class TestHDevelopEngine(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.project_root = Path(__file__).resolve().parent
        cls.pills_path = str(cls.project_root / "samples" / "pills_inspection.png")

    def test_01_hdev_parser_text(self):
        """测试纯文本 HDevelop 代码解析 (4槽位与标准签名推导)"""
        script = """
        * 经典药丸检测流水线
        read_image (Image, 'pills')
        threshold (Image, BrightRegion, 180, 255)
        connection (BrightRegion, Connected)
        select_shape (Connected, Selected, 'area', 'and', 1000, 3000)
        count_obj (Selected, Count)
        
        * 四槽位语法测试
        threshold (Image : CustomRegion : 100, 200 :)
        """
        instructions = HDevParser.parse_script(script)
        self.assertEqual(len(instructions), 6)

        # 验证第 1 条: read_image
        self.assertEqual(instructions[0].op_name, "read_image")
        self.assertEqual(instructions[0].iconic_out, ["Image"])
        self.assertEqual(instructions[0].control_in, ["pills"])

        # 验证第 2 条: threshold
        self.assertEqual(instructions[1].op_name, "threshold")
        self.assertEqual(instructions[1].iconic_in, ["Image"])
        self.assertEqual(instructions[1].iconic_out, ["BrightRegion"])
        self.assertEqual(instructions[1].control_in, [180, 255])

        # 验证第 6 条: 四槽位语法
        self.assertEqual(instructions[5].op_name, "threshold")
        self.assertEqual(instructions[5].iconic_in, ["Image"])
        self.assertEqual(instructions[5].iconic_out, ["CustomRegion"])
        self.assertEqual(instructions[5].control_in, [100, 200])

    def test_02_hdev_parser_xml(self):
        """测试标准 .hdev XML 文件格式解析"""
        xml_script = """<?xml version="1.0" encoding="UTF-8"?>
<hdevelop version="1.4">
  <procedure name="main">
    <interface/>
    <body>
      <line>* XML 封装的 HDevelop 脚本</line>
      <line>read_image (Image, 'pills')</line>
      <line>rgb1_to_gray (Image, GrayImage)</line>
      <line>threshold (GrayImage, Region, 150, 255)</line>
    </body>
  </procedure>
</hdevelop>"""
        instructions = HDevParser.parse_script(xml_script)
        self.assertEqual(len(instructions), 3)
        self.assertEqual(instructions[0].op_name, "read_image")
        self.assertEqual(instructions[1].op_name, "rgb1_to_gray")
        self.assertEqual(instructions[2].op_name, "threshold")

    def test_03_hdev_interpreter_execution(self):
        """测试 HDevelop 解释执行引擎 (全流程检测与变量表检查)"""
        script = """
        read_image (Image, 'pills')
        rgb1_to_gray (Image, Gray)
        threshold (Gray, Region, 180, 255)
        connection (Region, ConnectedRegions)
        select_shape (ConnectedRegions, SelectedPills, 'area', 'and', 1000, 3000)
        count_obj (SelectedPills, NumberOfPills)
        smallest_rectangle2 (SelectedPills, Rows, Cols, Phis, L1, L2)
        dev_display (SelectedPills)
        """
        interpreter = HDevInterpreter()
        result = interpreter.execute_script(script)

        self.assertTrue(result["success"], f"Execution failed: {result.get('error')}")
        self.assertIn("SelectedPills", interpreter.iconic_vars)
        self.assertIn("NumberOfPills", interpreter.control_vars)
        
        # 验证检测到的药丸目标数量
        pill_count = interpreter.control_vars["NumberOfPills"]
        self.assertGreater(pill_count, 10)
        self.assertEqual(interpreter.display_target, "SelectedPills")
        
        # 验证渲染数据有效生成
        self.assertIsNotNone(result.get("preview_base64"))
        self.assertIsNotNone(result.get("mask_base64"))
        self.assertGreater(len(result.get("objects", [])), 10)

    def test_04_hdev_subpix_and_filter(self):
        """测试亚像素边缘提取与滤波算子在 HDevelop 中的调用"""
        script = """
        read_image (Image, 'pills')
        mean_image (Image, Filtered, 5, 5)
        edges_subpix (Filtered, Edges, 'canny', 1.0, 40, 100)
        dev_display (Edges)
        """
        interpreter = HDevInterpreter()
        result = interpreter.execute_script(script)
        self.assertTrue(result["success"], f"Execution failed: {result.get('error')}")
        self.assertIn("Edges", interpreter.iconic_vars)
        contours = result.get("contours", [])
        self.assertGreater(len(contours), 0)

    def test_05_hdev_transpiler_roundtrip(self):
        """测试 HDevelop 脚本与 Pipeline 双向转译"""
        hdev_source = """
        read_image (Image, 'pills')
        rgb1_to_gray (Image, GrayImage)
        threshold (GrayImage, Region, 180, 255)
        connection (Region, ConnectedRegions)
        select_shape (ConnectedRegions, SelectedRegions, 'area', 'and', 1000, 3000)
        edges_subpix (GrayImage, Edges, 'canny', 1.0, 30, 90)
        """
        # 转译为 Pipeline 步骤
        steps = HDevTranspiler.hdev_to_pipeline(hdev_source)
        self.assertEqual(len(steps), 6)
        self.assertEqual(steps[0]["operator"], "read_image")
        self.assertEqual(steps[2]["operator"], "threshold")
        self.assertEqual(steps[2]["params"]["min_gray"], 180)
        self.assertEqual(steps[2]["params"]["max_gray"], 255)
        self.assertEqual(steps[4]["operator"], "select_shape")
        self.assertEqual(steps[4]["params"]["min_area"], 1000)

        # 逆向导出为 HDevelop 文本
        exported_text = HDevTranspiler.pipeline_to_hdev(steps, format_as_xml=False)
        self.assertIn("threshold (", exported_text)
        self.assertIn("select_shape (", exported_text)
        self.assertIn("edges_subpix (", exported_text)

        # 逆向导出为 XML
        exported_xml = HDevTranspiler.pipeline_to_hdev(steps, format_as_xml=True)
        self.assertTrue(exported_xml.startswith("<?xml"))
        self.assertIn("<line>threshold (", exported_xml)

    def test_06_api_hdev_endpoints(self):
        """测试 FastAPI 服务端针对 HDevelop 的 REST 接口契约"""
        # 1. 运行 HDevelop 脚本接口: POST /api/hdev/run
        resp = self.client.post("/api/hdev/run", json={
            "code": "read_image (Image, 'pills')\nthreshold (Image, Reg, 180, 255)\nconnection (Reg, Conn)\ncount_obj (Conn, N)"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("Conn", [v["name"] for v in data["iconic_vars"]])

        # 2. HDevelop 脚本同步到流水线接口: POST /api/hdev/to_pipeline
        resp = self.client.post("/api/hdev/to_pipeline", json={
            "code": "read_image (Image, 'pills')\nthreshold (Image, Reg, 160, 255)\nconnection (Reg, Conn)"
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["steps"]), 3)

        # 3. 流水线导出为 HDevelop 接口: POST /api/hdev/from_pipeline
        resp = self.client.post("/api/hdev/from_pipeline", json={"format": "plain"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertIn("threshold", data["code"])

        # 4. 上传 .hdev 文件接口: POST /api/hdev/upload
        dummy_hdev = b"read_image (Image, 'pills')\nthreshold (Image, R, 128, 255)"
        resp_upload = self.client.post(
            "/api/hdev/upload",
            files={"file": ("test_script.hdev", dummy_hdev, "application/octet-stream")}
        )
        self.assertEqual(resp_upload.status_code, 200)
        data = resp_upload.json()
        self.assertTrue(resp_upload.json()["success"])
        self.assertIn("threshold (", resp_upload.json()["code"])

    def test_07_hdev_projective_rectification(self):
        """测试透视矫正与单应性矩阵求解完整流程 (hom_vector_to_proj_hom_mat2d + projective_trans_image)"""
        script = """
        read_image (Image, '4-3.png')
        X := [163, 280, 362, 75]
        Y := [125, 120, 361, 340]
        gen_cross_contour_xld (Crosses, X, Y, 6, 0.78)
        QX := [75, 360, 360, 75]
        QY := [110, 110, 360, 360]
        hom_vector_to_proj_hom_mat2d (X, Y, [1,1,1,1], QX, QY, [1,1,1,1], 'normalized_dlt', HomMat2D)
        projective_trans_image (Image, Image_rectified, HomMat2D, 'bilinear', 'false', 'false')
        dev_display (Image_rectified)
        """
        interpreter = HDevInterpreter()
        res = interpreter.execute_script(script)
        self.assertTrue(res["success"], f"Execution error: {res.get('error')}")
        self.assertIn("Image_rectified", interpreter.iconic_vars)
        self.assertIn("HomMat2D", interpreter.control_vars)
        self.assertEqual(interpreter.display_target, "Image_rectified")
        self.assertIsNotNone(res.get("preview_base64"))
        rectified_img = interpreter.iconic_vars["Image_rectified"]
        self.assertEqual(rectified_img.shape, (500, 500, 3))

    def test_08_hdev_distance_angle_operators(self):
        """测试点线距离与直线夹角测量算子 (distance_pp / distance_pl / angle_ll)"""
        script = """
        distance_pp (0, 0, 3, 4, Dpp)
        distance_pl (5, 0, 0, 0, 0, 10, Dpl)
        angle_ll (0, 0, 0, 10, 0, 0, 10, 10, Ang)
        """
        interpreter = HDevInterpreter()
        res = interpreter.execute_script(script)
        self.assertTrue(res["success"], f"Execution error: {res.get('error')}")
        self.assertAlmostEqual(interpreter.control_vars["Dpp"], 5.0, places=3)
        self.assertAlmostEqual(interpreter.control_vars["Dpl"], 5.0, places=3)
        self.assertAlmostEqual(interpreter.control_vars["Ang"], -math.pi / 4, places=3)

    def test_09_hdev_fit_line_and_circle_contour_xld(self):
        """测试 XLD 轮廓最小二乘拟合算子 (fit_line_contour_xld / fit_circle_contour_xld)"""
        interpreter = HDevInterpreter()
        interpreter.iconic_vars["LineContours"] = [
            XLDContour(id=1, points=[(2.0, 0.0), (2.0, 5.0), (2.0, 10.0)])
        ]
        center_r, center_c, radius = 10.0, 10.0, 5.0
        circle_pts = [
            (center_r + radius * math.sin(t), center_c + radius * math.cos(t))
            for t in np.linspace(0, 2 * math.pi, 24, endpoint=False)
        ]
        interpreter.iconic_vars["CircleContours"] = [XLDContour(id=1, points=circle_pts)]

        script = """
        fit_line_contour_xld (LineContours, 'tukey', -1, 5, 'false', RowBegin, ColBegin, RowEnd, ColEnd, Nr, Nc, Dist)
        fit_circle_contour_xld (CircleContours, 'atukey', -1, 3, 'false', Row, Column, Radius, StartPhi, EndPhi, PointOrder)
        """
        res = interpreter.execute_script(script)
        self.assertTrue(res["success"], f"Execution error: {res.get('error')}")

        self.assertAlmostEqual(abs(interpreter.control_vars["Nr"][0]), 1.0, places=2)
        self.assertAlmostEqual(abs(interpreter.control_vars["Dist"][0]), 2.0, places=1)
        self.assertAlmostEqual(interpreter.control_vars["Row"][0], center_r, places=1)
        self.assertAlmostEqual(interpreter.control_vars["Column"][0], center_c, places=1)
        self.assertAlmostEqual(interpreter.control_vars["Radius"][0], radius, places=1)


if __name__ == "__main__":
    unittest.main()
