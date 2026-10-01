"""
NaviVision Studio desktop client entry point.

Starts the FastAPI server on a free local port in a background thread and shows the
UI in a native window (pywebview / WebView2). Closing the window stops the server.
Used as the PyInstaller entry; `python app.py` still runs the plain web server.
"""

import ctypes
import os
import socket
import sys
import threading
import time
from pathlib import Path

APP_TITLE = "NaviVision Studio"
PREFERRED_PORT = 8080
WINDOW_SIZE = (1440, 900)
WINDOW_MIN_SIZE = (1024, 680)
SERVER_START_TIMEOUT_S = 20.0
SERVER_POLL_INTERVAL_S = 0.05
LOG_DIR_NAME = "NaviVisionStudio"
MB_ICONERROR = 0x10


def show_error(message: str) -> None:
    ctypes.windll.user32.MessageBoxW(None, message, APP_TITLE, MB_ICONERROR)


def attach_log_file() -> None:
    """窗口模式下没有控制台, stdout/stderr 为 None; 重定向到日志文件, 避免 uvicorn 写日志时崩溃"""
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    log_dir = Path(base) / LOG_DIR_NAME
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = open(log_dir / "app.log", "a", encoding="utf-8", buffering=1)
    if sys.stdout is None:
        sys.stdout = log_file
    if sys.stderr is None:
        sys.stderr = log_file


def pick_port() -> int:
    for port in (PREFERRED_PORT, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("无法找到可用的本地端口")


def start_server(port: int):
    import uvicorn
    from app import app

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None)
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.time() + SERVER_START_TIMEOUT_S
    while not server.started:
        if time.time() > deadline:
            raise RuntimeError("内置服务启动超时")
        time.sleep(SERVER_POLL_INTERVAL_S)
    return server


def main() -> None:
    if "--script-worker" in sys.argv:
        from core.script_worker import main as run_script_worker
        run_script_worker()
        raise SystemExit(0)

    attach_log_file()
    try:
        import webview
    except ImportError:
        show_error("缺少 pywebview 组件, 无法打开客户端窗口。")
        raise SystemExit(1)

    port = pick_port()
    server = start_server(port)
    webview.settings["ALLOW_DOWNLOADS"] = True
    webview.create_window(
        APP_TITLE,
        f"http://127.0.0.1:{port}",
        width=WINDOW_SIZE[0],
        height=WINDOW_SIZE[1],
        min_size=WINDOW_MIN_SIZE,
    )
    try:
        webview.start()
    except Exception as exc:
        show_error(f"无法创建应用窗口 (可能缺少 Microsoft Edge WebView2 运行库):\n{exc}")
        raise SystemExit(1)
    finally:
        server.should_exit = True


if __name__ == "__main__":
    main()
