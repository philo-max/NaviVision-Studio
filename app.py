"""
NaviVision Studio (OpenDevelop) - FastAPI Server
提供高效 REST API、安全在线代码沙箱、多会话隔离与交互式 Web IDE 服务
"""

import os
import io
import sys
import time
import re
import csv
import json
from pathlib import Path
import cv2
import numpy as np
from fastapi import FastAPI, UploadFile, File, Form, Body, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator
from typing import Any, Dict, List, Literal

from core.pipeline import Pipeline
from core.session_manager import session_manager
from core.code_generator import generate_python_code
from core.script_runner import execute_custom_script
from core.api_service import run_pipeline_inference
from core import operators as ops

app = FastAPI(
    title="NaviVision Studio API",
    description="工业级机器视觉与 HALCON/HDevelop 平替开放接口平台 (带会话隔离与安全沙箱)",
    version="1.1.0"
)

BASE_DIR = Path(__file__).resolve().parent
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
MAX_PIPELINE_STEPS = 40
MAX_BATCH_FILES = 25
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
ENABLE_SCRIPT_RUNNER = os.getenv("NAVIVISION_ENABLE_SCRIPT_RUNNER", "0") == "1"


def get_pipeline(request: Request) -> Pipeline:
    """按会话标识获取当前隔离流水线实例"""
    sid = request.headers.get("X-Session-ID") or request.query_params.get("session_id") or "default"
    if not SESSION_ID_PATTERN.fullmatch(sid):
        raise HTTPException(status_code=400, detail="X-Session-ID 仅支持 1-64 位字母、数字、下划线和连字符")
    return session_manager.get_pipeline(sid)


def read_uploaded_image(contents: bytes) -> np.ndarray:
    if not contents:
        raise HTTPException(status_code=400, detail="上传文件为空")
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"上传文件超过 {MAX_UPLOAD_BYTES // 1024 // 1024} MB 限制")
    try:
        image = ops.read_image_from_bytes(contents)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if image.shape[0] * image.shape[1] > MAX_IMAGE_PIXELS:
        raise HTTPException(status_code=413, detail="图像像素数超过 2000 万限制")
    return image


# 静态测试样本定义
SAMPLES = [
    {
        "id": "pills",
        "title": "药板药丸瑕疵检测",
        "desc": "双阈值 + 连通域 + 面积筛选 (检测缺失/残缺药丸)",
        "path": "samples/pills_inspection.png",
        "default_steps": [
            {"id": "s_read", "operator": "read_image", "enabled": True, "params": {}},
            {"id": "s_thresh", "operator": "threshold", "enabled": True, "params": {"min_gray": 180, "max_gray": 255}},
            {"id": "s_conn", "operator": "connection", "enabled": True, "params": {"connectivity": 8}},
            {"id": "s_select", "operator": "select_shape", "enabled": True, "params": {"min_area": 1000, "max_area": 3000, "min_circularity": 0.8, "max_circularity": 1.0}}
        ]
    },
    {
        "id": "pcb",
        "title": "PCB 芯片引脚与过孔",
        "desc": "Canny/XLD 亚像素轮廓提取 + 引脚焊盘形态学检测",
        "path": "samples/pcb_components.png",
        "default_steps": [
            {"id": "s_read", "operator": "read_image", "enabled": True, "params": {}},
            {"id": "s_edge", "operator": "edges_subpix", "enabled": True, "params": {"low_threshold": 40, "high_threshold": 120}},
            {"id": "s_thresh", "operator": "threshold", "enabled": True, "params": {"min_gray": 160, "max_gray": 255}},
            {"id": "s_morph", "operator": "morphology", "enabled": True, "params": {"op_type": "closing", "kernel_shape": "circle", "kernel_size": 3}}
        ]
    },
    {
        "id": "gears",
        "title": "工业工件与垫圈测量",
        "desc": "Otsu 大津自适应分割 + 开运算降噪 + 特征度量",
        "path": "samples/metal_parts.png",
        "default_steps": [
            {"id": "s_read", "operator": "read_image", "enabled": True, "params": {}},
            {"id": "s_otsu", "operator": "auto_threshold", "enabled": True, "params": {"invert": False}},
            {"id": "s_morph", "operator": "morphology", "enabled": True, "params": {"op_type": "opening", "kernel_shape": "circle", "kernel_size": 3}},
            {"id": "s_conn", "operator": "connection", "enabled": True, "params": {"connectivity": 8}},
            {"id": "s_select", "operator": "select_shape", "enabled": True, "params": {"min_area": 500, "max_area": 999999, "min_circularity": 0.2, "max_circularity": 1.0}}
        ]
    }
]

# 挂载静态资源
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def get_index():
    with (BASE_DIR / "static" / "index.html").open("r", encoding="utf-8") as f:
        return f.read()


@app.get("/api/samples")
async def get_samples():
    return JSONResponse(content=SAMPLES)


@app.get("/healthz")
async def health_check():
    return {"status": "ok", "version": app.version, "script_runner_enabled": ENABLE_SCRIPT_RUNNER}


@app.post("/api/load_sample")
async def load_sample(request: Request, payload: Dict[str, str]):
    sample_id = payload.get("id")
    match = next((s for s in SAMPLES if s["id"] == sample_id), None)
    if not match:
        return JSONResponse(status_code=404, content={"error": "Sample not found"})

    pipeline = get_pipeline(request)
    img = ops.read_image_from_path(BASE_DIR / match["path"])
    pipeline.load_source_image(img)
    results = pipeline.set_steps(match["default_steps"])
    return {
        "success": True,
        "sample": match,
        "steps": match["default_steps"],
        "results": results
    }


@app.post("/api/upload")
async def upload_image(request: Request, file: UploadFile = File(...)):
    contents = await file.read()
    img = read_uploaded_image(contents)
    pipeline = get_pipeline(request)
    pipeline.load_source_image(img)

    default_steps = [
        {"id": "s_read", "operator": "read_image", "enabled": True, "params": {}},
        {"id": "s_thresh", "operator": "threshold", "enabled": True, "params": {"min_gray": 50, "max_gray": 200}},
        {"id": "s_conn", "operator": "connection", "enabled": True, "params": {"connectivity": 8}}
    ]
    results = pipeline.set_steps(default_steps)
    return {
        "success": True,
        "filename": file.filename,
        "steps": default_steps,
        "results": results
    }


class PipelineStep(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    operator: Literal[
        "read_image", "rgb1_to_gray", "threshold", "auto_threshold", "connection",
        "select_shape", "morphology", "filter", "edges_subpix", "measure_region"
    ]
    enabled: bool = True
    params: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("params")
    @classmethod
    def validate_params(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        if len(value) > 20:
            raise ValueError("单个算子最多支持 20 个参数")
        if any(isinstance(item, (dict, list, tuple, set)) for item in value.values()):
            raise ValueError("算子参数必须是基础 JSON 值")
        return value


class PipelineUpdateRequest(BaseModel):
    steps: List[PipelineStep] = Field(min_length=1, max_length=MAX_PIPELINE_STEPS)

    @model_validator(mode="after")
    def validate_pipeline(self):
        step_ids = [step.id for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("流水线步骤 ID 必须唯一")
        if self.steps[0].operator != "read_image":
            raise ValueError("流水线必须以 read_image 作为首步骤")
        return self

    def as_dicts(self) -> List[Dict[str, Any]]:
        return [step.model_dump() for step in self.steps]


class InspectionRule(BaseModel):
    min_objects: int | None = Field(default=None, ge=0)
    max_objects: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_bounds(self):
        if self.min_objects is not None and self.max_objects is not None and self.min_objects > self.max_objects:
            raise ValueError("min_objects 不能大于 max_objects")
        return self

    def evaluate(self, object_count: int) -> tuple[str, str]:
        if self.min_objects is not None and object_count < self.min_objects:
            return "FAIL", f"目标数 {object_count} 小于下限 {self.min_objects}"
        if self.max_objects is not None and object_count > self.max_objects:
            return "FAIL", f"目标数 {object_count} 大于上限 {self.max_objects}"
        return "PASS", "判定通过"


class BatchInspectionRecord(BaseModel):
    filename: str
    status: Literal["PASS", "FAIL", "ERROR"]
    object_count: int | None = Field(default=None, ge=0)
    duration_ms: float | None = Field(default=None, ge=0)
    message: str


class BatchReportRequest(BaseModel):
    records: List[BatchInspectionRecord] = Field(min_length=1, max_length=MAX_BATCH_FILES)


def get_object_count(inference: Dict[str, Any]) -> int:
    if inference["objects"]:
        return len(inference["objects"])
    for timing in reversed(inference["step_timings"]):
        if timing["operator"] == "measure_region":
            return 0
    return inference["object_count"]


@app.post("/api/pipeline/update")
async def update_pipeline(request: Request, req: PipelineUpdateRequest):
    pipeline = get_pipeline(request)
    results = pipeline.set_steps(req.as_dicts())
    return {"success": True, "results": results}


@app.post("/api/pipeline/export")
async def export_pipeline(req: PipelineUpdateRequest):
    code = generate_python_code(req.as_dicts(), "target_image.png")
    return {"success": True, "code": code}


@app.post("/api/v1/batch-predict")
async def batch_predict(
    request: Request,
    files: List[UploadFile] = File(...),
    rules: str = Form("{}")
):
    if not files:
        raise HTTPException(status_code=400, detail="请至少上传一张图像")
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(status_code=413, detail=f"单次批量检测最多支持 {MAX_BATCH_FILES} 张图像")
    try:
        rule = InspectionRule.model_validate_json(rules)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="检测规则格式无效") from exc

    pipeline = get_pipeline(request)
    if not pipeline.steps:
        raise HTTPException(status_code=409, detail="请先配置并保存一条流水线")

    records = []
    for file in files:
        try:
            image = read_uploaded_image(await file.read())
            inference = run_pipeline_inference(pipeline, image)
            object_count = get_object_count(inference)
            status, message = rule.evaluate(object_count)
            records.append({
                "filename": file.filename or "unnamed-image",
                "status": status,
                "object_count": object_count,
                "duration_ms": inference["duration_ms"],
                "message": message
            })
        except HTTPException as exc:
            records.append({
                "filename": file.filename or "unnamed-image",
                "status": "ERROR",
                "object_count": None,
                "duration_ms": None,
                "message": str(exc.detail)
            })
        except Exception as exc:
            records.append({
                "filename": file.filename or "unnamed-image",
                "status": "ERROR",
                "object_count": None,
                "duration_ms": None,
                "message": f"检测执行失败: {exc}"
            })

    passed = sum(record["status"] == "PASS" for record in records)
    failed = sum(record["status"] == "FAIL" for record in records)
    return {"success": True, "summary": {"total": len(records), "passed": passed, "failed": failed, "errors": len(records) - passed - failed}, "records": records}


@app.post("/api/report/csv")
async def export_batch_report(payload: BatchReportRequest):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["filename", "status", "object_count", "duration_ms", "message"])
    for record in payload.records:
        writer.writerow([record.filename, record.status, record.object_count, record.duration_ms, record.message])
    return Response(
        content="\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=navivision-inspection-report.csv"}
    )


# --- 工程持久化 API ---
@app.get("/api/project/export")
async def export_project(request: Request):
    """导出当前会话流水线工程为 JSON (.nvproj)"""
    pipeline = get_pipeline(request)
    sid = request.headers.get("X-Session-ID") or "default"
    project_data = {
        "format": "navivision_project",
        "version": "1.0",
        "session_id": sid,
        "exported_at": time.time(),
        "steps": pipeline.steps
    }
    return JSONResponse(content=project_data)


@app.post("/api/project/import")
async def import_project(request: Request, payload: PipelineUpdateRequest = Body(...)):
    """加载导入的工程配置并立即重算"""
    pipeline = get_pipeline(request)
    steps = payload.as_dicts()
    results = pipeline.set_steps(steps)
    return {
        "success": True,
        "steps": steps,
        "results": results
    }


# --- 安全代码沙箱执行接口 ---
class ScriptRunRequest(BaseModel):
    code: str


@app.post("/api/script/run")
async def run_custom_script(request: Request, req: ScriptRunRequest):
    """在隔离子进程中安全执行用户提交的 Python 脚本 (带 AST 审查与 3.0s 超时熔断)"""
    if not ENABLE_SCRIPT_RUNNER:
        raise HTTPException(
            status_code=403,
            detail="脚本执行默认关闭。仅在受信任的本机开发环境中设置 NAVIVISION_ENABLE_SCRIPT_RUNNER=1 后启用。"
        )
    pipeline = get_pipeline(request)
    if pipeline.source_image is None:
        return JSONResponse(status_code=400, content={"success": False, "error": "请先载入一张底图"})

    res = execute_custom_script(
        req.code,
        source_image=pipeline.source_image,
        source_gray=pipeline.source_gray,
        timeout_sec=3.0
    )
    return JSONResponse(content=res)


# --- 外部工业推理 REST API ---
@app.post("/api/v1/predict")
async def api_predict(request: Request, file: UploadFile = File(...)):
    """外部系统调用接口: 上传图片并由当前会话流水线进行推理"""
    contents = await file.read()
    input_img = read_uploaded_image(contents)
    pipeline = get_pipeline(request)
    result = run_pipeline_inference(pipeline, input_img)
    return JSONResponse(content=result)


@app.get("/api/v1/info")
async def get_api_info():
    """获取 API 快速接入指南"""
    return {
        "endpoint": "/api/v1/predict",
        "method": "POST",
        "content_type": "multipart/form-data",
        "curl_example": 'curl -X POST "http://127.0.0.1:8080/api/v1/predict" -F "file=@your_image.png"',
        "python_example": '''import requests

url = "http://127.0.0.1:8080/api/v1/predict"
with open("test.png", "rb") as f:
    files = {"file": f}
    resp = requests.post(url, files=files)
    print(resp.json())
'''
    }


if __name__ == "__main__":
    if "--script-worker" in sys.argv:
        from core.script_worker import main as run_script_worker
        run_script_worker()
        raise SystemExit(0)

    import uvicorn
    print("NaviVision Studio starting on http://localhost:8080 ...")
    uvicorn.run(app, host="127.0.0.1", port=8080, reload=False)
