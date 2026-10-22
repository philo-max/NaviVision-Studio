"""
文件列表与字符串筛选算子: list_files, tuple_regexp_select。
"""

import re
from pathlib import Path
from typing import Any, List

MAX_LISTED_FILES = 5000


def list_files(directory: str, options: Any = "files") -> List[str]:
    """
    HALCON list_files: 列出目录下的文件 (不递归, 只含文件), 返回以 / 分隔的完整路径, 按文件名排序。
    options 里的 'files' / 'follow_links' 等选项被接受, 子目录与递归选项不在支持范围内。
    """
    folder = Path(str(directory))
    if not folder.is_absolute():
        # 相对路径按程序目录解析 (与 read_image 一致), 这样随程序一起发出去的 samples 在任何电脑上都能找到
        folder = Path(__file__).resolve().parent.parent / folder
    if not folder.is_dir():
        raise FileNotFoundError(f"目录不存在: {directory}")
    wanted = options if isinstance(options, list) else [options]
    if any(str(o).lower() in ("directories", "recursive") for o in wanted):
        raise ValueError("list_files 暂不支持 'directories' 与 'recursive' 选项")
    files = sorted(p for p in folder.iterdir() if p.is_file())
    if len(files) > MAX_LISTED_FILES:
        raise ValueError(f"目录里的文件超过 {MAX_LISTED_FILES} 个")
    return [p.as_posix() for p in files]


def regexp_select(data: Any, expression: Any) -> List[str]:
    """HALCON tuple_regexp_select: 取出匹配正则表达式的字符串; expression 可为 [模式, 'ignore_case']"""
    options = expression if isinstance(expression, list) else [expression]
    if not options or not isinstance(options[0], str):
        raise ValueError("tuple_regexp_select 的 Expression 必须是正则表达式字符串")
    flags = re.IGNORECASE if any(str(o).lower() == "ignore_case" for o in options[1:]) else 0
    try:
        pattern = re.compile(options[0], flags)
    except re.error as exc:
        raise ValueError(f"正则表达式无效: {exc}") from exc
    items = data if isinstance(data, list) else [data]
    return [str(item) for item in items if pattern.search(str(item))]
