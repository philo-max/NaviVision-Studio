"""
NaviVision Studio - Multi-Tenant Session Manager
按 Session ID 隔离 Pipeline 实例，彻底解决并发与多标签页状态串扰
"""

import time
import threading
from pathlib import Path
from typing import Dict, Optional, List, Any
from core.pipeline import Pipeline
from core import operators as ops


class SessionManager:
    def __init__(self, max_idle_seconds: float = 3600.0, max_sessions: int = 100):
        self._sessions: Dict[str, Pipeline] = {}
        self._last_active: Dict[str, float] = {}
        self._lock = threading.Lock()
        self.max_idle_seconds = max_idle_seconds
        self.max_sessions = max_sessions

    def get_pipeline(self, session_id: Optional[str] = None) -> Pipeline:
        sid = session_id.strip() if session_id and session_id.strip() else "default"
        now = time.time()

        with self._lock:
            self._cleanup_expired(now)

            if sid not in self._sessions:
                pipeline = Pipeline()
                # 为新会话载入默认样本
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
                self._sessions[sid] = pipeline
                self._cleanup_expired(now)

            self._last_active[sid] = now
            return self._sessions[sid]

    def remove_session(self, session_id: str):
        with self._lock:
            self._sessions.pop(session_id, None)
            self._last_active.pop(session_id, None)

    def _cleanup_expired(self, now: float):
        expired = [
            sid for sid, last_t in self._last_active.items()
            if now - last_t > self.max_idle_seconds
        ]
        for sid in expired:
            self._sessions.pop(sid, None)
            self._last_active.pop(sid, None)

        overflow = len(self._sessions) - self.max_sessions
        if overflow > 0:
            oldest_sessions = sorted(self._last_active, key=self._last_active.get)[:overflow]
            for sid in oldest_sessions:
                self._sessions.pop(sid, None)
                self._last_active.pop(sid, None)


# 全局单例管理器
session_manager = SessionManager()
