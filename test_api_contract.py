import unittest

from fastapi.testclient import TestClient

from app import app
from fixtures import encode_png, make_blob_image


class ApiContractTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_health_check_reports_runtime_capabilities(self):
        response = self.client.get("/healthz")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertFalse(response.json()["script_runner_enabled"])

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

    def test_script_runner_is_disabled_by_default(self):
        response = self.client.post("/api/script/run", json={"code": "print('test')"})

        self.assertEqual(response.status_code, 403)

    def test_batch_requires_configured_pipeline(self):
        response = self.client.post(
            "/api/v1/batch-predict",
            headers={"X-Session-ID": "unconfigured_batch"},
            data={"rules": '{"min_objects": 1}'},
            files=[("files", ("blobs.png", encode_png(make_blob_image()), "image/png"))],
        )

        self.assertEqual(response.status_code, 409)

    def test_batch_inspection_and_csv_report(self):
        headers = {"X-Session-ID": "configured_batch"}
        configured = self.client.post(
            "/api/pipeline/update",
            headers=headers,
            json={"steps": [
                {"id": "read", "operator": "read_image", "params": {}},
                {"id": "thr", "operator": "threshold", "params": {"min_gray": 180, "max_gray": 255}},
                {"id": "conn", "operator": "connection", "params": {"connectivity": 8}},
            ]},
        )
        self.assertEqual(configured.status_code, 200)

        response = self.client.post(
            "/api/v1/batch-predict",
            headers=headers,
            data={"rules": '{"min_objects": 1}'},
            files=[("files", ("blobs.png", encode_png(make_blob_image()), "image/png"))],
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["records"][0]["status"], "PASS")

        report = self.client.post("/api/report/csv", json={"records": payload["records"]})
        self.assertEqual(report.status_code, 200)
        self.assertIn("blobs.png", report.text)

    def test_new_session_starts_without_image(self):
        response = self.client.post(
            "/api/pipeline/update",
            headers={"X-Session-ID": "fresh_empty_session"},
            json={"steps": [{"id": "read", "operator": "read_image", "params": {}}]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])


if __name__ == "__main__":
    unittest.main()
