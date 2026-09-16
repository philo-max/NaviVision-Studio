"""
NaviVision Studio (OpenDevelop) - Safe Subprocess Script Runner
安全子进程沙箱执行器:
1. AST 静态语法审查: 禁止危险系统模块导入与底层反射逃逸
2. 独立子进程执行: 隔离内存与主服务，彻底防止主进程崩溃
3. 3.0s 强制超时熔断: 防御死循环与计算挂起
4. 独立标准输出捕获: 不污染 FastAPI 服务端日志
"""

import sys
import os
import ast
import time
import pickle
import subprocess
from typing import Dict, Any, Optional
import numpy as np


# 危险模块黑名单
BLOCKED_MODULES = {
    "os", "sys", "subprocess", "shutil", "socket", "ctypes", "builtins",
    "importlib", "pathlib", "multiprocessing", "threading", "signal",
    "pty", "commands", "pdb", "posix", "winreg", "msvcrt"
}

# 危险反射探测属性
BLOCKED_ATTRS = {
    "__subclasses__", "__globals__", "__code__", "__bases__",
    "__mro__", "__dict__", "__builtins__", "__import__"
}

# 危险函数调用
BLOCKED_CALLS = {
    "eval", "exec", "compile", "open", "input", "__import__",
    "globals", "locals", "help", "quit", "exit", "breakpoint"
}


def validate_code_security(code_str: str) -> Optional[str]:
    """
    AST 静态代码安全审查:
    检查是否尝试导入敏感模块、访问底层反射属性或调用危险函数
    返回 None 表示安全，返回 str 表示被拦截原因
    """
    try:
        tree = ast.parse(code_str)
    except SyntaxError as se:
        return f"Python 语法错误: {se}"

    for node in ast.walk(tree):
        # 1. 检查 import xxx
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_module = alias.name.split(".")[0].lower()
                if root_module in BLOCKED_MODULES:
                    return f"安全审查拦截: 严禁导入系统底层或网络模块 '{alias.name}'"

        # 2. 检查 from xxx import yyy
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_module = node.module.split(".")[0].lower()
                if root_module in BLOCKED_MODULES:
                    return f"安全审查拦截: 严禁从受控模块 '{node.module}' 导入属性"

        # 3. 检查对象属性访问 (防止 obj.__class__.__subclasses__ 等逃逸)
        elif isinstance(node, ast.Attribute):
            if node.attr in BLOCKED_ATTRS:
                return f"安全审查拦截: 严禁访问底层私有反射属性 '{node.attr}'"

        # 4. 检查高危内置调用
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in BLOCKED_CALLS:
                    return f"安全审查拦截: 严禁直接调用内置控制函数 '{node.func.id}()'"

    return None


def execute_custom_script(
    code_str: str,
    source_image: np.ndarray,
    source_gray: Optional[np.ndarray] = None,
    timeout_sec: float = 3.0
) -> Dict[str, Any]:
    """
    在隔离子进程中安全执行用户提交的 Python 脚本，支持超时熔断与安全预检
    """
    if source_image is None:
        return {"success": False, "error": "当前未载入任何底图", "stdout": "", "duration_ms": 0.0}

    # 1. 静态代码安全扫描
    security_error = validate_code_security(code_str)
    if security_error:
        return {
            "success": False,
            "duration_ms": 0.0,
            "error": security_error,
            "stdout": f"[SECURITY REJECTED]\n{security_error}"
        }

    # 2. 打包输入载荷
    payload = {
        "code": code_str,
        "source_image": source_image,
        "source_gray": source_gray
    }
    input_bytes = pickle.dumps(payload)

    t0 = time.perf_counter()
    cmd = [sys.executable, "--script-worker"] if getattr(sys, "frozen", False) else [sys.executable, "-m", "core.script_worker"]

    try:
        proc = subprocess.run(
            cmd,
            input=input_bytes,
            capture_output=True,
            timeout=timeout_sec,
            cwd=os.getcwd()
        )
    except subprocess.TimeoutExpired:
        duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return {
            "success": False,
            "duration_ms": duration_ms,
            "error": f"执行超时 (熔断阈值 {timeout_sec}s)！子进程已被系统强制终止，请检查是否存在死循环或复杂度过高的操作。",
            "stdout": "[TIMEOUT FORCED TERMINATION]\nSubprocess exceeded time quota and was terminated."
        }
    except Exception as e:
        duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        return {
            "success": False,
            "duration_ms": duration_ms,
            "error": f"子进程启动异常: {str(e)}",
            "stdout": ""
        }

    duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    # 3. 检查子进程返回值
    if proc.returncode != 0:
        err_text = proc.stderr.decode("utf-8", errors="replace")
        return {
            "success": False,
            "duration_ms": duration_ms,
            "error": f"子进程执行崩溃 (退出码 {proc.returncode}):\n{err_text}",
            "stdout": proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
        }

    # 4. 反序列化子进程输出
    try:
        result = pickle.loads(proc.stdout)
        result["duration_ms"] = duration_ms
        return result
    except Exception as e:
        return {
            "success": False,
            "duration_ms": duration_ms,
            "error": f"解析子进程响应失败: {str(e)}",
            "stdout": proc.stdout.decode("utf-8", errors="replace")
        }
