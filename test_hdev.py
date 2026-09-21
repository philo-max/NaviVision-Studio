"""
NaviVision Studio - HDevelop DSL Engine Test Suite
验证 HDevelop 语言解析器、解释执行沙箱、双向转译器与 REST API 契约
"""

import unittest
import os
import sys
import numpy as np
from pathlib import Path
from fastapi.testclient import TestClient

from core.hdev_engine import HDevParser, HDevInterpreter, HDevTranspiler, HDEV_SIGNATURES
from core import operators as ops
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
        resp = self.client.post(
            "/api/hdev/upload",
            files={"file": ("test_script.hdev", dummy_hdev, "application/octet-stream")}
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["instruction_count"], 2)


if __name__ == "__main__":
    unittest.main()
