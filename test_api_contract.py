import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app import app


class ApiContractTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_check_reports_runtime_capabilities(self):
        response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertFalse(response.json()["script_runner_enabled"])

    def test_select_shape_summary_objects_carry_bbox(self):
        import numpy as np
        from core.pipeline import Pipeline

        img = np.zeros((60, 60, 3), dtype=np.uint8)
        img[10:30, 10:30] = 255
        pipeline = Pipeline()
        pipeline.load_source_image(img)
        results = pipeline.set_steps([
            {"id": "s1", "operator": "read_image", "enabled": True},
            {"id": "s2", "operator": "threshold", "params": {"min_gray": 200, "max_gray": 255}, "enabled": True},
            {"id": "s3", "operator": "connection", "params": {"connectivity": 8}, "enabled": True},
            {"id": "s4", "operator": "select_shape", "params": {"min_area": 10, "max_area": 9999}, "enabled": True},
        ])
        objects = results[3]["summary"]["objects"]
        self.assertEqual(len(objects), 1)
        self.assertEqual(objects[0]["bbox"], [10, 10, 30, 30])

    def test_pipeline_rejects_unknown_operator(self):
        response = self.client.post(
            "/api/pipeline/update",
            json={"steps": [{"id": "read", "operator": "unknown", "params": {}}]},
        )

        self.assertEqual(response.status_code, 422)

    def test_pipeline_requires_image_source_step(self):
        response = self.client.post(
            "/api/pipeline/update",
            json={"steps": [{"id": "threshold", "operator": "threshold", "params": {}}]},
        )

        self.assertEqual(response.status_code, 422)

    def test_pipeline_accepts_filter_operator(self):
        response = self.client.post(
            "/api/pipeline/update",
            json={"steps": [
                {"id": "read", "operator": "read_image", "params": {}},
                {"id": "flt", "operator": "filter", "params": {"filter_type": "gaussian", "kernel_size": 5, "sigma": 1.5}},
            ]},
        )

        self.assertEqual(response.status_code, 200)

    def test_pipeline_accepts_new_color_and_shape_operators(self):
        response = self.client.post(
            "/api/pipeline/update",
            json={"steps": [
                {"id": "read", "operator": "read_image", "params": {}},
                {"id": "hsv", "operator": "rgb_to_hsv", "params": {}},
                {"id": "hthr", "operator": "hsv_threshold", "params": {"h_min": 0, "h_max": 179}},
                {"id": "poly", "operator": "gen_contour_polygon", "params": {"epsilon": 2.0}},
                {"id": "barcode", "operator": "read_barcode", "params": {}},
            ]},
        )

        self.assertEqual(response.status_code, 200)

    def test_pipeline_accepts_shape_model_and_calibrate(self):
        response = self.client.post(
            "/api/pipeline/update",
            json={"steps": [
                {"id": "read", "operator": "read_image", "params": {}},
                {"id": "fsm", "operator": "find_shape_model", "params": {"min_score": 0.5, "scales": "1.0", "angles": "0"}},
                {"id": "cal", "operator": "calibrate", "params": {"pattern_cols": 9, "pattern_rows": 6, "square_size": 1.0}},
                {"id": "ocr", "operator": "read_text", "params": {"lang": "eng"}},
            ]},
        )

        self.assertEqual(response.status_code, 200)

    # --- P3-11 上传 / 脚本执行边界 (异常路径自动化测试) ---
    def test_upload_rejects_empty_payload(self):
        response = self.client.post(
            "/api/v1/predict",
            files=[("file", ("empty.png", b"", "image/png"))],
        )

        self.assertEqual(response.status_code, 400)

    def test_upload_rejects_invalid_image_format(self):
        response = self.client.post(
            "/api/v1/predict",
            files=[("file", ("bad.txt", b"this is definitely not an image", "text/plain"))],
        )

        self.assertEqual(response.status_code, 400)

    def test_upload_rejects_oversized_file(self):
        oversized = b"\x00" * (15 * 1024 * 1024 + 1024)
        response = self.client.post(
            "/api/v1/predict",
            files=[("file", ("huge.png", oversized, "image/png"))],
        )

        self.assertEqual(response.status_code, 413)

    def test_batch_rejects_too_many_files(self):
        sample_path = Path("samples/pills_inspection.png")
        files = []
        with sample_path.open("rb") as sample:
            payload = sample.read()
        for i in range(26):
            files.append(("files", (f"p{i}.png", payload, "image/png")))

        response = self.client.post(
            "/api/v1/batch-predict",
            data={"rules": '{"min_objects": 1}'},
            files=files,
        )

        self.assertEqual(response.status_code, 413)

    def test_script_runner_is_disabled_by_default(self):
        response = self.client.post("/api/script/run", json={"code": "print('test')"})

        self.assertEqual(response.status_code, 403)

    def test_script_runner_blocks_malicious_code_when_enabled(self):
        import app as app_module
        original = app_module.ENABLE_SCRIPT_RUNNER
        app_module.ENABLE_SCRIPT_RUNNER = True
        try:
            self.client.post("/api/pipeline/update", json={"steps": [
                {"id": "read", "operator": "read_image", "params": {}},
            ]})
            response = self.client.post(
                "/api/script/run",
                json={"code": "import os\nos.system('dir')"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertFalse(response.json()["success"])
        finally:
            app_module.ENABLE_SCRIPT_RUNNER = original

    def test_batch_inspection_and_csv_report(self):
        sample_path = Path("samples/pills_inspection.png")
        with sample_path.open("rb") as sample:
            response = self.client.post(
                "/api/v1/batch-predict",
                data={"rules": '{"min_objects": 1}'},
                files=[("files", ("pills.png", sample, "image/png"))],
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["records"][0]["status"], "PASS")

        report = self.client.post("/api/report/csv", json={"records": payload["records"]})
        self.assertEqual(report.status_code, 200)
        self.assertIn("pills.png", report.text)


if __name__ == "__main__":
    unittest.main()
