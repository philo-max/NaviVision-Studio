"""
脚本读写文件的工作区: 训练文件 (.trf)、分类器 (.omc)、输出文本等都放在这个专用目录里。
脚本给出的路径只取文件名部分, 目录部分一律忽略, 避免脚本读写工作区之外的文件。
"""

import os
from pathlib import Path

WORKSPACE_ENV = "NAVIVISION_WORKSPACE"
APP_DIR_NAME = "NaviVisionStudio"
WORKSPACE_DIR_NAME = "workspace"


def workspace_dir() -> Path:
    """工作区目录 (不存在时创建): 环境变量 NAVIVISION_WORKSPACE, 否则 %LOCALAPPDATA%/NaviVisionStudio/workspace"""
    override = os.environ.get(WORKSPACE_ENV)
    if override:
        base = Path(override)
    else:
        root = os.environ.get("LOCALAPPDATA") or str(Path.home())
        base = Path(root) / APP_DIR_NAME / WORKSPACE_DIR_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def workspace_path(file_name: str) -> Path:
    """把脚本里的文件名 (可带目录) 映射到工作区内的同名文件"""
    name = str(file_name).replace("\\", "/").rsplit("/", 1)[-1].strip()
    if not name or name in (".", ".."):
        raise ValueError(f"无效的文件名 '{file_name}'")
    return workspace_dir() / name
