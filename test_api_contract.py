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

    def test_script_runner_is_disabled_by_default(self):
        response = self.client.post("/api/script/run", json={"code": "print('test')"})

        self.assertEqual(response.status_code, 403)

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
