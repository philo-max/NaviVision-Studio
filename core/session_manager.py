"""
NaviVision Studio - Multi-Tenant Session Manager
按 Session ID 隔离 Pipeline 实例，彻底解决并发与多标签页状态串扰。

新增 (P3-10): 可选磁盘 JSON 落盘持久化，重启不丢会话。
启用方式: 设置环境变量 NAVIVISION_SESSION_DIR 指向落盘目录。
"""

import json
import os
import time
import threading
from pathlib import Path
from typing import Dict, Optional, List, Any

from core.pipeline import Pipeline
from core import operators as ops


class SessionManager:
    def __init__(
        self,
        max_idle_seconds: float = 3600.0,
        max_sessions: int = 100,
        persist_dir: Optional[str] = None
    ):
        self._sessions: Dict[str, Pipeline] = {}
        self._last_active: Dict[str, float] = {}
        self._lock = threading.Lock()
        self.max_idle_seconds = max_idle_seconds
        self.max_sessions = max_sessions
        self.persist_dir = persist_dir or None
        if self.persist_dir:
            os.makedirs(self.persist_dir, exist_ok=True)

    # --- 默认会话初始化 (保留原行为: 载入默认样本 + 默认步骤) ---
    def _default_pipeline(self) -> Pipeline:
        pipeline = Pipeline()
        default_sample_path = Path(__file__).resolve().parent.parent / "samples" / "pills_inspection.png"
        if default_sample_path.exists():
            img = ops.read_image_from_path(default_sample_path)
            pipeline.load_source_image(img)
            pipeline.set_steps([
                {"id": "s_read", "operator": "read_image", "enabled": True, "params": {}},
                {"id": "s_thresh", "operator": "threshold", "enabled": True, "params": {"min_gray": 180, "max_gray": 255}},
                {"id": "s_conn", "operator": "connection", "enabled": True, "params": {"connectivity": 8}},
                {"id": "s_select", "operator": "select_shape", "enabled": True, "params": {"min_area": 1000, "max_area": 3000, "min_circularity": 0.8, "max_circularity": 1.0}}
            ])
        return pipeline

    # --- 磁盘持久化内部工具 ---
    def _session_path(self, sid: str) -> str:
        if not self.persist_dir:
            return ""
        safe = "".join(ch for ch in str(sid) if ch.isalnum() or ch in "-_") or "default"
        return os.path.join(self.persist_dir, f"{safe}.json")

    def _persist(self, sid: str) -> None:
        """将会话流水线步骤原子化落盘 (先写临时文件再 replace)。"""
        if not self.persist_dir:
            return
        pipeline = self._sessions.get(sid)
        if pipeline is None:
            return
        try:
            payload = {
                "session_id": sid,
                "saved_at": time.time(),
                "steps": getattr(pipeline, "steps", []),
            }
            path = self._session_path(sid)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False)
            os.replace(tmp, path)
        except Exception:
            pass

    def _load_steps(self, sid: str) -> Optional[List[Dict[str, Any]]]:
        if not self.persist_dir:
            return None
        path = self._session_path(sid)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            steps = payload.get("steps")
            return steps if steps else None
        except Exception:
            return None

    # --- 对外接口 ---
    def get_pipeline(self, session_id: Optional[str] = None) -> Pipeline:
        sid = session_id.strip() if session_id and session_id.strip() else "default"
        now = time.time()

        with self._lock:
            self._cleanup_expired(now)

            if sid not in self._sessions:
                pipeline = self._default_pipeline()
                saved_steps = self._load_steps(sid)
                if saved_steps:
                    try:
                        pipeline.set_steps(saved_steps)
                    except Exception:
                        pass
                self._sessions[sid] = pipeline
                self._cleanup_expired(now)

            self._last_active[sid] = now
            return self._sessions[sid]

    def save_session(self, session_id: str) -> None:
        with self._lock:
            self._persist(session_id)

    def remove_session(self, session_id: str):
        with self._lock:
            self._sessions.pop(session_id, None)
            self._last_active.pop(session_id, None)
            path = self._session_path(session_id)
            if path:
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass

    def restore_all(self) -> int:
        """启动时从磁盘恢复全部已落盘会话, 返回恢复数量。"""
        if not self.persist_dir:
            return 0
        try:
            names = os.listdir(self.persist_dir)
        except Exception:
            return 0
        count = 0
        with self._lock:
            for name in names:
                if not name.endswith(".json"):
                    continue
                sid = name[:-5]
                steps = self._load_steps(sid)
                if steps:
                    pipeline = self._default_pipeline()
                    try:
                        pipeline.set_steps(steps)
                    except Exception:
                        pass
                    self._sessions[sid] = pipeline
                    self._last_active[sid] = time.time()
                    count += 1
        return count

    def _cleanup_expired(self, now: float) -> None:
        expired = [
            sid for sid, last_t in self._last_active.items()
            if now - last_t > self.max_idle_seconds
        ]
        for sid in expired:
            self._persist(sid)
            self._sessions.pop(sid, None)
            self._last_active.pop(sid, None)

        overflow = len(self._sessions) - self.max_sessions
        if overflow > 0:
            oldest_sessions = sorted(self._last_active, key=self._last_active.get)[:overflow]
            for sid in oldest_sessions:
                self._persist(sid)
                self._sessions.pop(sid, None)
                self._last_active.pop(sid, None)


# 全局单例管理器: 设置 NAVIVISION_SESSION_DIR 可开启磁盘持久化
session_manager = SessionManager(persist_dir=os.environ.get("NAVIVISION_SESSION_DIR") or None)
