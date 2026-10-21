"""
NaviVision Studio (OpenDevelop) - HDevelop DSL Engine
自研 HDevelop 4GL 语言原生解析器、解释执行沙箱与双向转译器:
1. HDevParser: 解析 .hdev XML 与纯文本脚本，支持四槽位语法与标准算子签名
2. HDevInterpreter: 纯 Python 隔离执行，维护 Iconic 与 Control 变量表，映射执行核心算子
3. HDevTranspiler: HDevelop 脚本与 NaviVision Pipeline 步骤 JSON 双向无损转译
"""

import os
from functools import lru_cache
import re
import xml.etree.ElementTree as ET
import time
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
import cv2
import numpy as np

from core.types import Region, RegionObject, XLDContour
from core import operators as ops
from core import ocr_chars
from core import hdev_expr
from core import hdev_geometry
from core.shape_model import ShapeModel, create_shape_model as build_shape_model
from core.shape_search import find_shape_models
from core import file_ops, ocr_mlp, text_region_ops, workspace
from core.ocr_mlp import TrainedOcrClassifier
from core.pipeline import encode_image_base64, create_colored_label_mask

GRAPHICS_STYLE_OPERATORS = frozenset({
    "dev_set_color", "dev_set_line_width", "dev_set_draw", "dev_set_part", "dev_set_lut", "dev_set_paint",
    "dev_set_shape", "dev_set_check", "dev_set_window_extents", "dev_error_var",
    "dev_update_off", "dev_update_on", "dev_update_window", "dev_update_pc", "dev_update_var",
    "set_system",
})
CONTROL_VALUE_MAX_ITEMS = 100
CONTROL_VALUE_SIGNIFICANT_DIGITS = 6


def _to_plain(value: Any) -> Any:
    """把 numpy 标量 / 数组转换为 Python 原生类型, 便于格式化与序列化"""
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (list, tuple)):
        return [_to_plain(v) for v in value]
    return value


def format_control_value(value: Any) -> str:
    """按 HDevelop 变量窗口的风格显示控制变量: 实数保留 6 位有效数字且带小数点, 字符串带单引号, 元组用方括号"""
    value = _to_plain(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        text = f"{value:.{CONTROL_VALUE_SIGNIFICANT_DIGITS}g}"
        return text if any(ch in text for ch in ".eni") else text + ".0"
    if isinstance(value, str):
        return f"'{value}'"
    if isinstance(value, list):
        items = [format_control_value(v) for v in value[:CONTROL_VALUE_MAX_ITEMS]]
        if len(value) > CONTROL_VALUE_MAX_ITEMS:
            items.append(f"… 共 {len(value)} 个")
        return "[" + ", ".join(items) + "]"
    return str(value)


def _control_type(value: Any) -> str:
    if isinstance(value, list):
        return "tuple"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "real"
    if isinstance(value, str):
        return "string"
    return type(value).__name__


HDEV_REGION_ALPHA = 255
THUMBNAIL_MAX_SIDE = 96


@dataclass
class _WindowState:
    """模拟 HALCON 单个图形窗口的叠加显示状态"""
    handle: int
    image_name: Optional[str] = None
    region_names: List[str] = field(default_factory=list)
    xld_names: List[str] = field(default_factory=list)
    messages: List[Dict[str, Any]] = field(default_factory=list)

    def is_empty(self) -> bool:
        return self.image_name is None and not self.region_names and not self.xld_names and not self.messages


MESSAGE_COLORS_BGR: Dict[str, Tuple[int, int, int]] = {
    "black": (0, 0, 0), "white": (255, 255, 255), "red": (0, 0, 255), "green": (0, 160, 0),
    "blue": (255, 0, 0), "yellow": (0, 255, 255), "cyan": (255, 255, 0), "magenta": (255, 0, 255),
    "orange": (0, 140, 255), "gray": (128, 128, 128),
}
MESSAGE_BASE_FONT_PX = 18
MESSAGE_BOX_PADDING = 4
MESSAGE_LINE_SPACING = 1.3
MESSAGE_DARK_BOX_BGR = (40, 40, 40)
MESSAGE_LIGHT_BOX_BGR = (235, 235, 235)
MESSAGE_LUMA_THRESHOLD = 128


_CJK_FONT_FILES = ("msyh.ttc", "msyhl.ttc", "simhei.ttf", "simsun.ttc", "NotoSansCJK-Regular.ttc", "wqy-microhei.ttc")
_CJK_FONT_DIRS = (r"C:\Windows\Fonts", "/usr/share/fonts/truetype/wqy", "/usr/share/fonts/opentype/noto", "/Library/Fonts", "/System/Library/Fonts")


@lru_cache(maxsize=8)
def _cjk_font(size: int):
    """找一个能显示汉字的系统字体 (Pillow); 找不到时返回 None"""
    from PIL import ImageFont
    for directory in _CJK_FONT_DIRS:
        for name in _CJK_FONT_FILES:
            path = os.path.join(directory, name)
            if os.path.exists(path):
                try:
                    return ImageFont.truetype(path, size)
                except OSError:
                    continue
    return None


def _draw_message_unicode(canvas: np.ndarray, msg: Dict[str, Any], lines: List[str], color: Tuple[int, int, int], scale: float) -> np.ndarray:
    """含汉字等非 ASCII 字符的文字: 用 Pillow 绘制 (OpenCV 自带字体画不出汉字)"""
    from PIL import Image, ImageDraw
    font = _cjk_font(max(8, int(round(MESSAGE_BASE_FONT_PX * scale))))
    if font is None:
        return canvas
    image = Image.fromarray(cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(image)
    boxes = [draw.textbbox((0, 0), ln, font=font) for ln in lines]
    line_h = int(max(b[3] - b[1] for b in boxes) * MESSAGE_LINE_SPACING) + 2
    x0, y0, pad = int(msg["col"]), int(msg["row"]), MESSAGE_BOX_PADDING
    if msg["box"]:
        luma = 0.114 * color[0] + 0.587 * color[1] + 0.299 * color[2]
        box_color = MESSAGE_LIGHT_BOX_BGR if luma < MESSAGE_LUMA_THRESHOLD else MESSAGE_DARK_BOX_BGR
        box_w = max(b[2] - b[0] for b in boxes) + 2 * pad
        draw.rectangle((x0, y0, x0 + box_w, y0 + line_h * len(lines) + pad), fill=box_color[::-1])
    for i, ln in enumerate(lines):
        draw.text((x0 + pad, y0 + line_h * i + pad // 2), ln, font=font, fill=color[::-1])
    return cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)


def _draw_messages(img: np.ndarray, messages: List[Dict[str, Any]]) -> np.ndarray:
    """将 disp_message 记录的文字叠加绘制到图像副本上 (行/列为图像像素坐标, 文字左上角对齐)"""
    if not messages:
        return img
    canvas = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR) if img.ndim == 2 else img.copy()
    scale = max(1.0, canvas.shape[1] / 512.0)
    font_scale = MESSAGE_BASE_FONT_PX / 30.0 * scale
    thickness = max(1, int(round(scale)))
    for msg in messages:
        lines = str(msg["text"]).split("\n")
        color = MESSAGE_COLORS_BGR.get(str(msg["color"]).lower(), MESSAGE_COLORS_BGR["black"])
        if any(ord(ch) > 127 for ln in lines for ch in ln):
            canvas = _draw_message_unicode(canvas, msg, lines, color, scale)
            continue
        sizes = [cv2.getTextSize(ln, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)[0] for ln in lines]
        line_h = int(max(s[1] for s in sizes) * MESSAGE_LINE_SPACING) + 2
        x0, y0 = int(msg["col"]), int(msg["row"])
        pad = MESSAGE_BOX_PADDING
        if msg["box"]:
            luma = 0.114 * color[0] + 0.587 * color[1] + 0.299 * color[2]
            box_color = MESSAGE_LIGHT_BOX_BGR if luma < MESSAGE_LUMA_THRESHOLD else MESSAGE_DARK_BOX_BGR
            box_w = max(s[0] for s in sizes) + 2 * pad
            cv2.rectangle(canvas, (x0, y0), (x0 + box_w, y0 + line_h * len(lines) + pad), box_color, -1)
        for i, ln in enumerate(lines):
            cv2.putText(canvas, ln, (x0 + pad, y0 + line_h * (i + 1) - 2), cv2.FONT_HERSHEY_SIMPLEX,
                        font_scale, color, thickness, cv2.LINE_AA)
    return canvas


# ----------------------------------------------------------------------
# 1. 经典 HALCON 算子签名映射表 (支持非冒号简写语法的参数自动推导)
# ----------------------------------------------------------------------
# 定义每个算子的参数槽位分类:
# (iconic_in, iconic_out, control_in, control_out)
HDEV_SIGNATURES: Dict[str, Tuple[List[str], List[str], List[str], List[str]]] = {
    "read_image": ([], ["Image"], ["FileName"], []),
    "rgb1_to_gray": (["Image"], ["GrayImage"], [], []),
    "threshold": (["Image"], ["Region"], ["MinGray", "MaxGray"], []),
    "auto_threshold": (["Image"], ["Regions"], ["Sigma"], []),
    "binary_threshold": (["Image"], ["Region"], ["Method", "LightDark"], ["UsedThreshold"]),
    "connection": (["Region"], ["ConnectedRegions"], [], []),
    "select_shape": (["Regions"], ["SelectedRegions"], ["Features", "Operation", "Min", "Max"], []),
    "dilation_circle": (["Region"], ["RegionDilation"], ["Radius"], []),
    "erosion_circle": (["Region"], ["RegionErosion"], ["Radius"], []),
    "opening_circle": (["Region"], ["RegionOpening"], ["Radius"], []),
    "closing_circle": (["Region"], ["RegionClosing"], ["Radius"], []),
    "dilation_rectangle1": (["Region"], ["RegionDilation"], ["Width", "Height"], []),
    "erosion_rectangle1": (["Region"], ["RegionErosion"], ["Width", "Height"], []),
    "opening_rectangle1": (["Region"], ["RegionOpening"], ["Width", "Height"], []),
    "closing_rectangle1": (["Region"], ["RegionClosing"], ["Width", "Height"], []),
    "erosion1": (["Region", "StructElement"], ["RegionErosion"], ["Iterations"], []),
    "erosion2": (["Region", "StructElement"], ["RegionErosion"], ["Row", "Column", "Iterations"], []),
    "dilation1": (["Region", "StructElement"], ["RegionDilation"], ["Iterations"], []),
    "dilation2": (["Region", "StructElement"], ["RegionDilation"], ["Row", "Column", "Iterations"], []),
    "opening": (["Region", "StructElement"], ["RegionOpening"], [], []),
    "closing": (["Region", "StructElement"], ["RegionClosing"], [], []),
    "gen_ellipse": ([], ["Ellipse"], ["Row", "Column", "Phi", "Radius1", "Radius2"], []),
    "gen_circle": ([], ["Circle"], ["Row", "Column", "Radius"], []),
    "fill_up": (["Region"], ["RegionFillUp"], [], []),
    "difference": (["Region", "Sub"], ["RegionDifference"], [], []),
    "union1": (["Region"], ["RegionUnion"], [], []),
    "union2": (["Region1", "Region2"], ["RegionUnion"], [], []),
    "intersection": (["Region1", "Region2"], ["RegionIntersection"], [], []),
    "complement": (["Region"], ["RegionComplement"], [], []),
    "boundary": (["Region"], ["RegionBorder"], ["BoundaryType"], []),
    "dev_set_colored": ([], [], ["NumColors"], []),
    "set_display_font": ([], [], ["WindowHandle", "Size", "Font", "Bold", "Slant"], []),
    "get_image_size": (["Image"], [], [], ["Width", "Height"]),
    "smallest_rectangle1": (["Regions"], [], [], ["Row1", "Column1", "Row2", "Column2"]),
    "sort_region": (["Regions"], ["SortedRegions"], ["SortMode", "Order", "RowOrCol"], []),
    "char_threshold": (["Image", "HistoRegion"], ["Characters"], ["Sigma", "Percent"], ["Threshold"]),
    "draw_rectangle1": ([], [], ["WindowHandle"], ["Row1", "Column1", "Row2", "Column2"]),
    "dev_get_window": ([], [], [], ["WindowHandle"]),
    "stop": ([], [], [], []),
    "affine_trans_image": (["Image"], ["ImageAffinTrans"], ["HomMat2D", "Interpolation", "AdaptImageSize"], []),
    "rotate_image": (["Image"], ["ImageRotate"], ["Phi", "Interpolation"], []),
    "append_ocr_trainf": (["Character", "Image"], [], ["Class", "TrainingFile"], []),
    "read_ocr_trainf_names": ([], [], ["TrainingFile"], ["CharacterNames", "CharacterCount"]),
    "create_ocr_class_mlp": ([], [], ["WidthCharacter", "HeightCharacter", "Interpolation", "Features", "Characters", "NumHidden", "Preprocessing", "NumComponents", "RandSeed"], ["OCRHandle"]),
    "trainf_ocr_class_mlp": ([], [], ["OCRHandle", "TrainingFile", "MaxIterations", "WeightTolerance", "ErrorTolerance"], ["Error", "ErrorLog"]),
    "write_ocr_class_mlp": ([], [], ["OCRHandle", "FileName"], []),
    "clear_ocr_class_mlp": ([], [], ["OCRHandle"], []),
    "open_file": ([], [], ["FileName", "Mode"], ["FileHandle"]),
    "fwrite_string": ([], [], ["FileHandle", "String"], []),
    "fnew_line": ([], [], ["FileHandle"], []),
    "close_file": ([], [], ["FileHandle"], []),
    "list_files": ([], [], ["Directory", "Options"], ["Files"]),
    "tuple_regexp_select": ([], [], ["Data", "Expression"], ["Selected"]),
    "mean_image": (["Image"], ["ImageMean"], ["MaskWidth", "MaskHeight"], []),
    "gauss_filter": (["Image"], ["ImageGauss"], ["Size"], []),
    "median_image": (["Image"], ["ImageMedian"], ["MaskType", "Radius", "Margin"], []),
    "edges_subpix": (["Image"], ["Edges"], ["Filter", "Alpha", "Low", "High"], []),
    "measure_region": (["Regions"], [], [], ["Metrics"]),
    "smallest_rectangle2": (["Regions"], [], [], ["Row", "Column", "Phi", "Length1", "Length2"]),
    "smallest_circle": (["Regions"], [], [], ["Row", "Column", "Radius"]),
    "area_center": (["Regions"], [], [], ["Area", "Row", "Column"]),
    "count_obj": (["Objects"], [], [], ["Number"]),
    "select_obj": (["Objects"], ["ObjectSelected"], ["Index"], []),
    "dev_display": (["Object"], [], [], []),
    "disp_obj": (["Object"], [], ["WindowHandle"], []),
    "reduce_domain": (["Image", "Region"], ["ImageReduced"], [], []),
    "gen_rectangle1": ([], ["Rectangle"], ["Row1", "Column1", "Row2", "Column2"], []),
    "rgb_to_hsv": (["Image"], ["HSVImage"], [], []),
    "hsv_threshold": (["Image"], ["Region"], ["HMin", "HMax", "SMin", "SMax", "VMin", "VMax"], []),
    "create_shape_model": (["Template"], [], ["NumLevels", "AngleStart", "AngleExtent", "AngleStep", "Optimization", "Metric", "Contrast", "MinContrast"], ["ModelID"]),
    "create_scaled_shape_model": (["Template"], [], ["NumLevels", "AngleStart", "AngleExtent", "AngleStep", "ScaleMin", "ScaleMax", "ScaleStep", "Optimization", "Metric", "Contrast", "MinContrast"], ["ModelID"]),
    "find_shape_model": (["Image"], [], ["ModelID", "AngleStart", "AngleExtent", "MinScore", "NumMatches", "MaxOverlap", "SubPixel", "NumLevels", "Greediness"], ["Row", "Column", "Angle", "Score"]),
    "find_scaled_shape_model": (["Image"], [], ["ModelID", "AngleStart", "AngleExtent", "ScaleMin", "ScaleMax", "MinScore", "NumMatches", "MaxOverlap", "SubPixel", "NumLevels", "Greediness"], ["Row", "Column", "Angle", "Scale", "Score"]),
    "get_shape_model_params": ([], [], ["ModelID"], ["NumLevels", "AngleStart", "AngleExtent", "AngleStep", "ScaleMin", "ScaleMax", "ScaleStep", "Metric", "MinContrast"]),
    "get_shape_model_contours": ([], ["ModelContours"], ["ModelID", "Level"], []),
    "clear_shape_model": ([], [], ["ModelID"], []),
    "hom_mat2d_identity": ([], [], [], ["HomMat2DIdentity"]),
    "hom_mat2d_translate": ([], [], ["HomMat2D", "Tx", "Ty"], ["HomMat2DTranslate"]),
    "hom_mat2d_rotate": ([], [], ["HomMat2D", "Phi", "Px", "Py"], ["HomMat2DRotate"]),
    "hom_mat2d_scale": ([], [], ["HomMat2D", "Sx", "Sy", "Px", "Py"], ["HomMat2DScale"]),
    "vector_angle_to_rigid": ([], [], ["Row1", "Column1", "Angle1", "Row2", "Column2", "Angle2"], ["HomMat2D"]),
    "affine_trans_contour_xld": (["Contours"], ["ContoursAffineTrans"], ["HomMat2D"], []),
    "draw_circle": ([], [], ["WindowHandle"], ["Row", "Column", "Radius"]),
    "dev_disp_text": ([], [], ["String", "CoordSystem", "Row", "Column", "Color", "GenParamName", "GenParamValue"], []),
    "gen_contour_polygon_xld": (["Contour"], ["Polygons"], ["Type", "MaxDistance"], []),
    "read_barcode": (["Image"], [], [], ["DecodedStrings"]),
    "read_text": (["Image"], [], ["Lang"], ["RecognizedText"]),
    "calibrate": (["Image"], [], ["PatternWidth", "PatternHeight", "SquareSize"], ["PixelsPerUnit"]),
    "gen_cross_contour_xld": ([], ["Crosses"], ["Row", "Col", "Length", "Phi"], []),
    "hom_vector_to_proj_hom_mat2d": ([], [], ["Px", "Py", "Pw", "Qx", "Qy", "Qw", "Method"], ["HomMat2D"]),
    "vector_to_proj_hom_mat2d": ([], [], ["Px", "Py", "Qx", "Qy", "Method"], ["HomMat2D"]),
    "projective_trans_image": (["Image"], ["Image_rectified"], ["HomMat2D", "Interpolation", "AdaptImageSize", "TransformDomain"], []),
    "projective_trans_image_size": (["Image"], ["Image_rectified"], ["HomMat2D", "Interpolation", "Width", "Height", "TransformDomain"], []),
    "read_ocr_class_mlp": ([], [], ["FileName"], ["OCRHandle"]),
    "do_ocr_multi_class_mlp": (["Character", "Image"], [], ["OCRHandle"], ["Class", "Confidence"]),
    "disp_message": ([], [], ["WindowHandle", "String", "CoordSystem", "Row", "Column", "Color", "Box"], []),
    "dev_update_off": ([], [], [], []),
    "dev_update_on": ([], [], [], []),
    "dev_close_window": ([], [], [], []),
    "dev_clear_window": ([], [], [], []),
    "dev_open_window": ([], [], ["Row", "Column", "Width", "Height", "Background"], ["WindowHandle"]),
    "dev_open_window_fit_image": (["Image"], [], ["Row", "Column", "WidthLimit", "HeightLimit"], ["WindowHandle"]),
    "dev_set_window": ([], [], ["WindowHandle"], []),
    "dev_set_color": ([], [], ["ColorName"], []),
    "dev_set_line_width": ([], [], ["LineWidth"], []),
    "dev_set_draw": ([], [], ["DrawMode"], []),
    "distance_pp": ([], [], ["Row1", "Col1", "Row2", "Col2"], ["Distance"]),
    "distance_pl": ([], [], ["Row", "Col", "RowBegin", "ColBegin", "RowEnd", "ColEnd"], ["Distance"]),
    "angle_ll": ([], [], ["RowA1", "ColA1", "RowA2", "ColA2", "RowB1", "ColB1", "RowB2", "ColB2"], ["Angle"]),
    "fit_line_contour_xld": (["Contours"], [], ["Algorithm", "MaxNumPoints", "MaxDistance", "ClippingEndPoints"], ["RowBegin", "ColBegin", "RowEnd", "ColEnd", "Nr", "Nc", "Dist"]),
    "fit_circle_contour_xld": (["Contours"], [], ["Algorithm", "MaxNumPoints", "MaxDistance", "ClippingEndPoints"], ["Row", "Column", "Radius", "StartPhi", "EndPhi", "PointOrder"]),
    "sobel_amp": (["Image"], ["EdgeAmplitude"], ["FilterType", "Size"], []),
    "skeleton": (["Region"], ["Skeleton"], [], []),
    "laplace": (["Image"], ["ImageLaplace"], ["Result", "MaskSize", "FilterMask"], [])
}


# ----------------------------------------------------------------------
# 2. HDevParser: 语法与结构解析器
# ----------------------------------------------------------------------
class HDevInstruction:
    """单条解析后的 HDevelop 指令"""
    def __init__(
        self,
        raw_line: str,
        line_num: int,
        op_type: str,  # 'operator' | 'assign' | 'for' | 'endfor' | 'if' | 'else' | 'elseif' | 'endif' | 'while' | 'endwhile' | 'comment'
        op_name: str = "",
        iconic_in: Optional[List[str]] = None,
        iconic_out: Optional[List[str]] = None,
        control_in: Optional[List[Any]] = None,
        control_out: Optional[List[str]] = None,
        assign_var: str = "",
        assign_expr: str = "",
        condition: str = "",
        for_loop_meta: Optional[Dict[str, Any]] = None
    ):
        self.raw_line = raw_line
        self.line_num = line_num
        self.op_type = op_type
        self.op_name = op_name
        self.iconic_in = iconic_in or []
        self.iconic_out = iconic_out or []
        self.control_in = control_in or []
        self.control_out = control_out or []
        self.assign_var = assign_var
        self.assign_expr = assign_expr
        self.condition = condition
        self.for_loop_meta = for_loop_meta or {}


class HDevParser:
    """HDevelop 脚本解析器，支持 XML 与纯文本"""

    @classmethod
    def extract_lines(cls, script_content: str) -> List[Tuple[int, str]]:
        """从字符串中提取有效代码行 (兼容 XML .hdev 格式与普通纯文本)"""
        content = script_content.strip()
        lines: List[Tuple[int, str]] = []

        # 检查是否为 XML 包装的 .hdev / .hdvp
        if content.startswith("<?xml") or "<hdevelop" in content:
            try:
                root = ET.fromstring(content)
                # 寻找所有 procedure 下的 line 节点
                line_idx = 1
                for line_elem in root.findall(".//line"):
                    txt = line_elem.text or ""
                    lines.append((line_idx, txt.strip()))
                    line_idx += 1
                if lines:
                    return lines
            except Exception:
                # 若 XML 解析失败则降级为纯文本行解析
                pass

        # 普通文本解析 (行尾的 \ 表示续行: 与下一行合并为同一条语句, 行号取首行)
        pending: Optional[Tuple[int, str]] = None
        for idx, raw in enumerate(script_content.splitlines(), start=1):
            text = raw.strip()
            if pending is not None:
                text = f"{pending[1]} {text}"
                idx = pending[0]
                pending = None
            if text.endswith("\\") and not text.startswith(("*", "//")):
                pending = (idx, text[:-1].rstrip())
                continue
            lines.append((idx, text))
        if pending is not None:
            lines.append(pending)
        return lines

    @staticmethod
    def _is_single_literal(s: str) -> bool:
        if len(s) < 2 or s[0] not in ("'", '"') or s[-1] != s[0]:
            return False
        quote, i = s[0], 1
        while i < len(s) - 1:
            if s[i] == "\\":
                i += 2
                continue
            if s[i] == quote:
                return False
            i += 1
        return i == len(s) - 1

    @staticmethod
    def _unescape(text: str) -> str:
        return hdev_expr.unescape_string(text)

    @classmethod
    def _parse_value(cls, val_str: str) -> Any:
        """解析控制表达式的单个常量或变量字面量"""
        s = val_str.strip()
        if not s:
            return ""
        # 字符串常量: 'foo' 或 "foo" (整个参数恰好是一个引号字面量; 'a' + 'b' 这类表达式留给求值器)
        if cls._is_single_literal(s):
            return cls._unescape(s[1:-1])
        # 数组 / 元组常量: [1, 2, 3]
        if s.startswith("[") and s.endswith("]"):
            inner = s[1:-1].strip()
            if not inner:
                return []
            items = [cls._parse_value(x) for x in cls._split_comma(inner)]
            return items
        # 布尔常量
        if s.lower() == "true":
            return True
        if s.lower() == "false":
            return False
        # 数字: int 或 float
        try:
            if "." in s or "e" in s.lower():
                return float(s)
            return int(s)
        except ValueError:
            # 保持为变量名标识符
            return s

    @classmethod
    def _split_comma(cls, s: str) -> List[str]:
        """安全按逗号切分，忽略方括号及单双引号内部的逗号"""
        parts = []
        cur = []
        depth = 0
        in_quote = None
        for ch in s:
            if in_quote:
                cur.append(ch)
                if ch == in_quote:
                    in_quote = None
            elif ch in ("'", '"'):
                in_quote = ch
                cur.append(ch)
            elif ch in ("[", "("):
                depth += 1
                cur.append(ch)
            elif ch in ("]", ")"):
                depth -= 1
                cur.append(ch)
            elif ch == "," and depth == 0:
                parts.append("".join(cur).strip())
                cur = []
            else:
                cur.append(ch)
        if cur:
            parts.append("".join(cur).strip())
        return [p for p in parts if p]

    @classmethod
    def _has_toplevel_colon(cls, s: str) -> bool:
        """
        检测字符串中是否存在不在引号/括号内的顶层冒号, 用于判断是否为四槽位语法。
        单纯的 ":" in s 会被字符串参数里的内容误判成四槽位语法, 例如 Windows 绝对路径
        'C:\\Users\\...' 本身就带一个冒号, 从而把整条调用彻底解析错乱。
        """
        depth = 0
        in_quote = None
        for ch in s:
            if in_quote:
                if ch == in_quote:
                    in_quote = None
            elif ch in ("'", '"'):
                in_quote = ch
            elif ch in ("[", "("):
                depth += 1
            elif ch in ("]", ")"):
                depth -= 1
            elif ch == ":" and depth == 0:
                return True
        return False

    @classmethod
    def parse_line(cls, line: str, line_num: int) -> Optional[HDevInstruction]:
        """解析单行 HDevelop 语句"""
        trimmed = line.strip()
        if not trimmed:
            return None

        # 注释行: * 或 //
        if trimmed.startswith("*") or trimmed.startswith("//"):
            return HDevInstruction(raw_line=line, line_num=line_num, op_type="comment")

        # 赋值语句: Var := Expression 或 assign (Value, Var)
        assign_match = re.match(r"^([a-zA-Z0-9_]+)\s*:=\s*(.+)$", trimmed)
        if assign_match:
            var_name = assign_match.group(1).strip()
            expr = assign_match.group(2).strip()
            return HDevInstruction(
                raw_line=line,
                line_num=line_num,
                op_type="assign",
                assign_var=var_name,
                assign_expr=expr
            )

        # 控制流关键字: for, endfor, if, else, elseif, endif, while, endwhile
        low = trimmed.lower()
        if low.startswith("for ") and " to " in low:
            # for Index := Start to End by Step
            m = re.match(r"^for\s+([a-zA-Z0-9_]+)\s*:=\s*(.+?)\s+to\s+(.+?)(?:\s+by\s+(.+?))?$", trimmed, re.IGNORECASE)
            if m:
                var_name = m.group(1)
                start_val = cls._parse_value(m.group(2))
                end_val = cls._parse_value(m.group(3))
                step_val = cls._parse_value(m.group(4)) if m.group(4) else 1
                return HDevInstruction(
                    raw_line=line,
                    line_num=line_num,
                    op_type="for",
                    assign_var=var_name,
                    for_loop_meta={"start": start_val, "end": end_val, "step": step_val}
                )

        if low == "endfor":
            return HDevInstruction(raw_line=line, line_num=line_num, op_type="endfor")

        if low.startswith("if ") or low.startswith("if("):
            cond = trimmed[2:].strip()
            if cond.startswith("(") and cond.endswith(")"):
                cond = cond[1:-1].strip()
            return HDevInstruction(raw_line=line, line_num=line_num, op_type="if", condition=cond)

        if low.startswith("elseif ") or low.startswith("elseif("):
            cond = trimmed[6:].strip()
            if cond.startswith("(") and cond.endswith(")"):
                cond = cond[1:-1].strip()
            return HDevInstruction(raw_line=line, line_num=line_num, op_type="elseif", condition=cond)

        if low == "else":
            return HDevInstruction(raw_line=line, line_num=line_num, op_type="else")

        if low == "endif":
            return HDevInstruction(raw_line=line, line_num=line_num, op_type="endif")

        if low.startswith("while ") or low.startswith("while("):
            cond = trimmed[5:].strip()
            if cond.startswith("(") and cond.endswith(")"):
                cond = cond[1:-1].strip()
            return HDevInstruction(raw_line=line, line_num=line_num, op_type="while", condition=cond)

        if low == "endwhile":
            return HDevInstruction(raw_line=line, line_num=line_num, op_type="endwhile")

        # 算子调用匹配: op_name ( ... )
        op_match = re.match(r"^([a-zA-Z0-9_]+)\s*\((.*)\)$", trimmed, re.DOTALL)
        if not op_match:
            # 兼容无需括号的简写，或未知语法
            return HDevInstruction(raw_line=line, line_num=line_num, op_type="unknown")

        op_name = op_match.group(1).strip()
        args_str = op_match.group(2).strip()

        # 检查是否包含冒号 ':' 四槽位语法:
        # op ( IconicIn : IconicOut : ControlIn : ControlOut )
        if cls._has_toplevel_colon(args_str):
            slots = [s.strip() for s in args_str.split(":")]
            # 补齐 4 个槽位
            while len(slots) < 4:
                slots.append("")
            iconic_in = [x.strip() for x in cls._split_comma(slots[0])] if slots[0] else []
            iconic_out = [x.strip() for x in cls._split_comma(slots[1])] if slots[1] else []
            control_in = [cls._parse_value(x) for x in cls._split_comma(slots[2])] if slots[2] else []
            control_out = [x.strip() for x in cls._split_comma(slots[3])] if slots[3] else []
            return HDevInstruction(
                raw_line=line,
                line_num=line_num,
                op_type="operator",
                op_name=op_name,
                iconic_in=iconic_in,
                iconic_out=iconic_out,
                control_in=control_in,
                control_out=control_out
            )

        # 非冒号简写，按参数列表依次填充，结合已知签名表推导槽位
        args = [cls._parse_value(x) for x in cls._split_comma(args_str)] if args_str else []
        sig = HDEV_SIGNATURES.get(op_name.lower())

        if sig:
            # 根据签名槽位数量依次消费参数
            sig_i_in, sig_i_out, sig_c_in, sig_c_out = sig
            arg_idx = 0

            i_in = []
            for _ in sig_i_in:
                if arg_idx < len(args):
                    i_in.append(str(args[arg_idx]))
                    arg_idx += 1

            i_out = []
            for _ in sig_i_out:
                if arg_idx < len(args):
                    i_out.append(str(args[arg_idx]))
                    arg_idx += 1

            c_in = []
            for _ in sig_c_in:
                if arg_idx < len(args):
                    c_in.append(args[arg_idx])
                    arg_idx += 1

            c_out = []
            for _ in sig_c_out:
                if arg_idx < len(args):
                    c_out.append(str(args[arg_idx]))
                    arg_idx += 1

            return HDevInstruction(
                raw_line=line,
                line_num=line_num,
                op_type="operator",
                op_name=op_name,
                iconic_in=i_in,
                iconic_out=i_out,
                control_in=c_in,
                control_out=c_out
            )

        # 未知签名，默认全部归入 control_in
        return HDevInstruction(
            raw_line=line,
            line_num=line_num,
            op_type="operator",
            op_name=op_name,
            control_in=args
        )

    @classmethod
    def parse_script(cls, script_content: str) -> List[HDevInstruction]:
        """完整解析一段 HDevelop 脚本"""
        lines = cls.extract_lines(script_content)
        instructions: List[HDevInstruction] = []
        for line_num, l in lines:
            inst = cls.parse_line(l, line_num)
            if inst and inst.op_type != "comment":
                instructions.append(inst)
        return instructions


# ----------------------------------------------------------------------
# 3. HDevInterpreter: 解释执行沙箱
# ----------------------------------------------------------------------
class _FlowMap:
    """for/while/if 块配对表: 把控制流指令映射为可跳转的指令下标"""

    def __init__(self, instructions: List[HDevInstruction]):
        self.end_of: Dict[int, int] = {}
        self.start_of: Dict[int, int] = {}
        self.next_branch: Dict[int, int] = {}
        self.if_end: Dict[int, int] = {}
        loops: List[Tuple[str, int]] = []
        ifs: List[List[int]] = []
        closers = {"endfor": "for", "endwhile": "while"}
        for pc, inst in enumerate(instructions):
            t = inst.op_type
            if t in ("for", "while"):
                loops.append((t, pc))
            elif t in closers:
                if not loops or loops[-1][0] != closers[t]:
                    raise ValueError(f"第 {inst.line_num} 行: {t} 没有匹配的 {closers[t]}")
                start = loops.pop()[1]
                self.end_of[start] = pc
                self.start_of[pc] = start
            elif t == "if":
                ifs.append([pc])
            elif t in ("elseif", "else", "endif"):
                if not ifs:
                    raise ValueError(f"第 {inst.line_num} 行: {t} 没有匹配的 if")
                branch_pcs = ifs[-1]
                self.next_branch[branch_pcs[-1]] = pc
                branch_pcs.append(pc)
                if t == "endif":
                    for b in ifs.pop():
                        self.if_end[b] = pc
        if loops:
            raise ValueError(f"第 {instructions[loops[-1][1]].line_num} 行: {loops[-1][0]} 缺少结束语句")
        if ifs:
            raise ValueError(f"第 {instructions[ifs[-1][0]].line_num} 行: if 缺少 endif")


class HDevInterpreter:
    """HDevelop 脚本解释执行引擎"""

    def __init__(self, base_image: Optional[np.ndarray] = None, session_id: str = "default"):
        self.session_id = session_id
        # Iconic 变量表: Name -> np.ndarray | Region | List[XLDContour]
        self.iconic_vars: Dict[str, Any] = {}
        # Control 变量表: Name -> int | float | str | list
        self.control_vars: Dict[str, Any] = {}
        # 终端输出日志
        self.stdout: List[str] = []
        # 当前活跃显示目标 (Iconic 变量名)
        self.display_target: Optional[str] = None
        # 脚本执行前的原始底图快照 (用于前后对比视图)。默认取会话当前底图作为兜底,
        # 但若脚本自己也调用了 read_image, 应以脚本内首次加载的图像为准 (见 _original_snapshot_claimed),
        # 否则无论脚本实际处理哪张图, "处理前"对比画面都会被锁死在会话残留的旧图上
        self.original_snapshot: Optional[np.ndarray] = None
        self._original_snapshot_claimed: bool = False
        # HALCON 多图形窗口模拟: 每个窗口独立维护自己的叠加显示状态
        # (显示图像会重绘整个画布并清空该窗口的叠加层, 而 Region/XLD 的显示
        # 则在当前活跃窗口上叠加绘制, 直到下次显示新图像或 dev_clear_window)
        self.windows: Dict[int, _WindowState] = {0: _WindowState(handle=0)}
        self.active_window: int = 0
        self._next_window_handle: int = 1
        # 脚本中是否显式调用过 dev_display/disp_obj/dev_open_window (决定渲染走叠加模式还是单目标覆盖模式)
        self.explicit_display_used: bool = False
        # OCR 分类器句柄表: 句柄 -> 字符集名称 (由 read_ocr_class_mlp 创建)
        self.ocr_handles: Dict[int, Any] = {}
        # 脚本打开的文件句柄表 (open_file 创建, close_file / 脚本结束时关闭)
        self.open_files: Dict[int, Any] = {}
        # dev_display 时刻的 Region / XLD 快照: 叠加层键 -> 对象
        self._display_snapshots: Dict[str, Any] = {}
        # 形状模板句柄表: 句柄 -> ShapeModel (由 create_shape_model / create_scaled_shape_model 创建)
        self.shape_models: Dict[int, ShapeModel] = {}
        # 图形窗口里用户预先画好的 ROI 几何 (供 draw_circle 读取), 形如 {"type": "circle", "cx", "cy", "r"}
        self.roi_geometry: Optional[Dict[str, Any]] = None
        # 图像定义域 (reduce_domain 产出): 图像变量名 -> 布尔掩膜; threshold 等算子只在域内取像素
        self.domains: Dict[str, np.ndarray] = {}
        # 最近一次 do_ocr_multi_class_mlp 的逐字符识别结果 (供前端结果面板展示)
        self.ocr_result: Optional[Dict[str, Any]] = None
        # 单步调试执行指针: 已解析的指令序列与当前待执行指令下标 (由 load_script 填充)
        self.instructions: List[HDevInstruction] = []
        self.pc: int = 0
        self._flow: Optional[_FlowMap] = None
        self._active_loops: set = set()
        self._loop_bounds: Dict[int, Tuple[Any, Any]] = {}
        # 默认底图注入 (注意: 不标记窗口 0 为"已使用", 否则会在多窗口场景下
        # 被误判为脚本主动打开的窗口而出现在窗口切换标签页里; 各窗口合成画面时
        # 仍会在找不到自己专属底图时回退取用这张预注入的图像, 见 _composite_window)
        if base_image is not None:
            self.iconic_vars["Image"] = base_image
            self.display_target = "Image"
            self.original_snapshot = base_image.copy()
            # 注意: 不设置 _original_snapshot_claimed=True, 这样如果脚本自己也调用了
            # read_image, 会在下面的算子分支里用脚本实际加载的图像替换掉这张兜底快照

    def log(self, msg: str):
        self.stdout.append(str(msg))

    def _cur_win(self) -> _WindowState:
        """返回当前活跃图形窗口的叠加显示状态"""
        return self.windows[self.active_window]

    def _eval_expr(self, expr: Any) -> Any:
        """解析并计算表达式或变量求值"""
        if not isinstance(expr, str):
            return expr
        s = expr.strip()
        # 检查是否为控制变量名
        if s in self.control_vars:
            return self.control_vars[s]
        # 常量或简单四则运算
        try:
            return self._eval_strict(s)
        except (NameError, SyntaxError, hdev_expr.UnsupportedExpression):
            return s
        except IndexError:
            raise ValueError(f"表达式 '{s}' 的元组下标越界")
        except ZeroDivisionError:
            raise ValueError(f"表达式 '{s}' 除数为零")

    def _eval_strict(self, expr: str) -> Any:
        """仅允许安全数学运算; 求值失败直接抛出异常 (供条件判断使用)"""
        allowed_names = {k: v for k, v in self.control_vars.items() if isinstance(v, (int, float, list, str))}
        return hdev_expr.evaluate(expr, allowed_names)

    def _eval_condition(self, cond: str) -> bool:
        """求值 if/while 条件: HALCON 的 '=' 视为相等比较, '#' 视为不等"""
        normalized = re.sub(r"(?<![<>!=:])=(?!=)", "==", cond).replace("#", "!=")
        try:
            return bool(self._eval_strict(normalized))
        except Exception as e:
            raise ValueError(f"无法求值条件 '{cond}': {e}")

    def _run_single_instruction(self, inst: HDevInstruction) -> None:
        """执行单条指令 (赋值语句或算子调用), 不负责 pc 步进与异常捕获, 供整段执行与单步调试共用"""
        if inst.op_type == "assign":
            val = self._eval_expr(inst.assign_expr)
            self.control_vars[inst.assign_var] = val
            self.log(f"  [{inst.line_num}] {inst.assign_var} := {val}")
        elif inst.op_type == "operator":
            self._execute_operator(inst)

    def _prepare(self, instructions: List[HDevInstruction]) -> None:
        """装载指令序列并建立 for/while/if 的块配对表"""
        self.instructions = instructions
        self._flow = _FlowMap(instructions)
        self._active_loops = set()
        self._loop_bounds = {}

    def _advance(self, pc: int) -> int:
        """执行 pc 处的指令并返回下一条应执行的指令下标 (处理 for/while/if 的跳转)"""
        inst = self.instructions[pc]
        t = inst.op_type
        flow = self._flow
        if t == "for":
            meta = inst.for_loop_meta
            if pc not in self._active_loops:
                # HALCON 只在循环开始时计算一次上界与步长 (如 for Number := 1 to Number by 1 里的 Number)
                self._active_loops.add(pc)
                start = self._eval_expr(meta["start"])
                self._loop_bounds[pc] = (self._eval_expr(meta["end"]), self._eval_expr(meta["step"]))
                self.control_vars[inst.assign_var] = start
            end, step = self._loop_bounds[pc]
            idx = self.control_vars[inst.assign_var]
            if (step >= 0 and idx > end) or (step < 0 and idx < end):
                self._active_loops.discard(pc)
                self._loop_bounds.pop(pc, None)
                return flow.end_of[pc] + 1
            return pc + 1
        if t == "endfor":
            for_pc = flow.start_of[pc]
            step = self._loop_bounds[for_pc][1]
            self.control_vars[self.instructions[for_pc].assign_var] += step
            return for_pc
        if t == "while":
            return pc + 1 if self._eval_condition(inst.condition) else flow.end_of[pc] + 1
        if t == "endwhile":
            return flow.start_of[pc]
        if t == "if":
            return self._select_branch(pc)
        if t in ("elseif", "else"):
            return flow.if_end[pc] + 1
        if t == "endif":
            return pc + 1
        if t == "operator" and inst.op_name.lower() == "stop":
            self.log(f"  [{inst.line_num}] stop: 程序在此停止 (其后的语句不再执行)")
            return len(self.instructions)
        self._run_single_instruction(inst)
        return pc + 1

    def _select_branch(self, pc: int) -> int:
        """在 if/elseif 处按条件选择分支, 返回所选分支体的首条指令下标 (无分支命中则返回 endif 之后)"""
        inst = self.instructions[pc]
        if self._eval_condition(inst.condition):
            return pc + 1
        nxt = self._flow.next_branch[pc]
        kind = self.instructions[nxt].op_type
        if kind == "elseif":
            return self._select_branch(nxt)
        return nxt + 1

    def execute_script(self, script_content: str, timeout_sec: float = 3.0) -> Dict[str, Any]:
        """执行完整 HDevelop 脚本"""
        t0 = time.perf_counter()
        instructions = HDevParser.parse_script(script_content)

        self.log(f"[*] HDevelop 解释器启动: 共载入 {len(instructions)} 条指令")

        pc = 0
        total_inst = len(instructions)
        start_time = time.time()

        try:
            self._prepare(instructions)
            while pc < total_inst:
                # 超时熔断保护
                if time.time() - start_time > timeout_sec:
                    raise TimeoutError(f"HDevelop 脚本执行超时 (强制熔断阈值: {timeout_sec:.1f}s)")

                pc = self._advance(pc)

            duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            self.log(f"[✓] 脚本执行完毕，耗时 {duration_ms} ms")
            
            # 提取可视化输出
            render_res = self._build_visualization_payload()
            return {
                "success": True,
                "duration_ms": duration_ms,
                "stdout": "\n".join(self.stdout),
                "iconic_vars": self._list_iconic_vars(),
                "control_vars": {k: str(v) for k, v in self.control_vars.items()},
                "control_var_list": self._list_control_vars(),
                "display_target": self.display_target,
                **render_res
            }

        except Exception as e:
            duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            err_msg = f"第 {instructions[pc].line_num} 行执行失败: {e}" if pc < total_inst else str(e)
            self.log(f"[!] {err_msg}")
            return {
                "success": False,
                "error": err_msg,
                "duration_ms": duration_ms,
                "stdout": "\n".join(self.stdout),
                "iconic_vars": self._list_iconic_vars(),
                "control_vars": {k: str(v) for k, v in self.control_vars.items()},
                "control_var_list": self._list_control_vars()
            }
        finally:
            self._close_open_files()

    def _close_open_files(self) -> None:
        """脚本结束 (成功或出错) 时关闭 open_file 打开却没有 close_file 的文件, 保证内容落盘"""
        for stream in self.open_files.values():
            stream.close()
        self.open_files.clear()

    # ------------------------------------------------------------------
    # 单步调试 / 断点续跑 / 变量监视器: 与 execute_script 共用 _run_single_instruction,
    # 但把 pc 步进暴露为可持久化的解释器状态, 供服务端跨请求保持调试会话
    # ------------------------------------------------------------------
    def load_script(self, script_content: str) -> Dict[str, Any]:
        """解析脚本并重置单步调试执行指针, 返回初始调试状态快照 (尚未执行任何指令)"""
        self.pc = 0
        try:
            self._prepare(HDevParser.parse_script(script_content))
        except ValueError as e:
            self.instructions = []
            self.log(f"[!] {e}")
            return self._debug_status(finished=True, error=str(e), stopped_reason="error")
        self.log(f"[*] 调试会话已加载脚本: 共 {len(self.instructions)} 条指令")
        return self._debug_status(finished=len(self.instructions) == 0, stopped_reason="ready")

    def _debug_status(self, finished: bool, error: Optional[str] = None, stopped_reason: str = "step") -> Dict[str, Any]:
        """打包单步/断点调试当前状态快照 (下一条待执行指令 + 变量表 + 画面), 供前端调试面板渲染"""
        next_inst = self.instructions[self.pc] if self.pc < len(self.instructions) else None
        render_res = self._build_visualization_payload()
        return {
            "success": error is None,
            "error": error,
            "finished": finished,
            "stopped_reason": stopped_reason,
            "pc": self.pc,
            "total_instructions": len(self.instructions),
            "current_line": next_inst.line_num if next_inst else None,
            "current_raw_line": next_inst.raw_line if next_inst else None,
            "stdout": "\n".join(self.stdout),
            "iconic_vars": self._list_iconic_vars(),
            "control_vars": {k: str(v) for k, v in self.control_vars.items()},
            "control_var_list": self._list_control_vars(),
            "display_target": self.display_target,
            **render_res
        }

    def step_once(self) -> Dict[str, Any]:
        """单步调试: 执行 pc 指向的一条指令后立即暂停, 返回执行后的状态快照"""
        if self.pc >= len(self.instructions):
            return self._debug_status(finished=True, stopped_reason="finished")

        inst = self.instructions[self.pc]
        try:
            self.pc = self._advance(self.pc)
            finished = self.pc >= len(self.instructions)
            return self._debug_status(finished=finished, stopped_reason="finished" if finished else "step")
        except Exception as e:
            err_msg = f"第 {inst.line_num} 行执行失败: {e}"
            self.log(f"[!] {err_msg}")
            return self._debug_status(finished=True, error=err_msg, stopped_reason="error")

    def continue_run(self, breakpoints: Optional[List[int]] = None, max_steps: int = 500) -> Dict[str, Any]:
        """
        断点续跑: 从当前 pc 持续单步执行, 直到命中断点行号 / 脚本结束 / 出错 / 达到步数上限。
        当前 pc 所在指令自身不受断点拦截 (保证从断点处再次 continue 时脚本总能向前推进)。
        """
        bp_set = set(breakpoints or [])
        steps_taken = 0
        while self.pc < len(self.instructions) and steps_taken < max_steps:
            inst = self.instructions[self.pc]
            if steps_taken > 0 and inst.line_num in bp_set:
                return self._debug_status(finished=False, stopped_reason="breakpoint")
            try:
                self.pc = self._advance(self.pc)
                steps_taken += 1
            except Exception as e:
                err_msg = f"第 {inst.line_num} 行执行失败: {e}"
                self.log(f"[!] {err_msg}")
                return self._debug_status(finished=True, error=err_msg, stopped_reason="error")

        finished = self.pc >= len(self.instructions)
        return self._debug_status(finished=finished, stopped_reason="finished" if finished else "max_steps")

    def _execute_operator(self, inst: HDevInstruction):
        """执行单个算子调用"""
        op = inst.op_name.lower()
        i_in = inst.iconic_in
        i_out = inst.iconic_out
        # HALCON 里只有一个元素的元组与单个值等价 (如 area_center 输出的 Row 可直接当标量参数), 这里统一展开
        c_in = [self._unwrap_single(self._eval_expr(x)) for x in inst.control_in]
        c_out = inst.control_out

        # 1. read_image (Image, FileName)
        if op == "read_image":
            out_name = i_out[0] if i_out else "Image"
            target_path = str(c_in[0]) if c_in else "pills"
            # 智能映射内置样本
            sample_map = {
                "pills": "samples/pills_inspection.png",
                "pcb": "samples/pcb_components.png",
                "metal_parts": "samples/metal_parts.png",
                "gears": "samples/metal_parts.png"
            }
            resolved_path = sample_map.get(target_path, target_path)
            # 拼接项目根目录
            if not os.path.isabs(resolved_path):
                project_root = Path(__file__).resolve().parent.parent
                cand = project_root / resolved_path
                if cand.exists():
                    resolved_path = str(cand)

            img = ops.read_image_from_path(resolved_path)
            self.iconic_vars[out_name] = img
            self.display_target = out_name
            if not self._original_snapshot_claimed:
                # 脚本自己的首次 read_image 才是这次运行真正的"处理前"图像,
                # 覆盖掉构造时兜底注入的会话旧图 (否则前后对比会一直锁在旧图上)
                self.original_snapshot = img.copy()
                self._original_snapshot_claimed = True
            self.log(f"  [{inst.line_num}] read_image: 载入图像 '{out_name}', shape={img.shape}")

        # 2. rgb1_to_gray (Image, GrayImage)
        elif op == "rgb1_to_gray":
            in_name = i_in[0] if i_in else "Image"
            out_name = i_out[0] if i_out else "GrayImage"
            src = self.iconic_vars.get(in_name)
            if src is None:
                raise ValueError(f"未找到输入图像 '{in_name}'")
            gray = ops.rgb1_to_gray(src)
            self.iconic_vars[out_name] = gray
            if in_name in self.domains:
                self.domains[out_name] = self.domains[in_name]
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] rgb1_to_gray: 转换为灰度图 '{out_name}'")

        # 3. threshold (Image, Region, MinGray, MaxGray)
        elif op == "threshold":
            in_name = i_in[0] if i_in else "Image"
            out_name = i_out[0] if i_out else "Region"
            min_gray = int(c_in[0]) if len(c_in) > 0 else 128
            max_gray = int(c_in[1]) if len(c_in) > 1 else 255
            src = self.iconic_vars.get(in_name)
            if src is None:
                raise ValueError(f"未找到输入图像 '{in_name}'")
            gray = ops.rgb1_to_gray(src) if len(src.shape) == 3 else src
            reg = ops.threshold(gray, min_gray, max_gray)
            if in_name in self.domains:
                reg.mask[~self.domains[in_name]] = 0
            self.iconic_vars[out_name] = reg
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] threshold: 分割范围 [{min_gray}, {max_gray}], 生成区域 '{out_name}'")

        # 4a. binary_threshold (Image, Region, Method, LightDark, UsedThreshold): 在定义域内由直方图自动定阈值
        elif op == "binary_threshold":
            in_name = i_in[0] if i_in else "Image"
            src = self.iconic_vars.get(in_name)
            if not isinstance(src, np.ndarray):
                raise ValueError(f"未找到输入图像 '{in_name}'")
            if len(c_in) < 2:
                raise ValueError("binary_threshold 需要 Method 与 LightDark 两个参数")
            gray = ops.rgb1_to_gray(src) if src.ndim == 3 else src
            reg, used = text_region_ops.binary_threshold(gray, self.domains.get(in_name), c_in[0], c_in[1])
            out_name = i_out[0] if i_out else "Region"
            self.iconic_vars[out_name] = reg
            self.display_target = out_name
            if c_out:
                self.control_vars[c_out[0]] = used
            self.log(f"  [{inst.line_num}] binary_threshold: {c_in[0]} / {c_in[1]}, 阈值 {used}, 区域 {int(np.count_nonzero(reg.mask))} px -> '{out_name}'")

        # 4. auto_threshold (Image, Regions, Sigma)
        elif op == "auto_threshold":
            in_name = i_in[0] if i_in else "Image"
            out_name = i_out[0] if i_out else "Regions"
            src = self.iconic_vars.get(in_name)
            if src is None:
                raise ValueError(f"未找到输入图像 '{in_name}'")
            gray = ops.rgb1_to_gray(src) if len(src.shape) == 3 else src
            reg = ops.auto_threshold_otsu(gray, invert=False)
            self.iconic_vars[out_name] = reg
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] auto_threshold: Otsu 自动分割生成 '{out_name}'")

        # 5. connection (Region, ConnectedRegions)
        elif op == "connection":
            in_name = i_in[0] if i_in else "Region"
            out_name = i_out[0] if i_out else "ConnectedRegions"
            src_reg = self.iconic_vars.get(in_name)
            if not isinstance(src_reg, Region):
                raise ValueError(f"输入对象 '{in_name}' 不是有效的 Region")
            conn_reg = ops.connection(src_reg, connectivity=8)
            self.iconic_vars[out_name] = conn_reg
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] connection: 打散为 {len(conn_reg.objects)} 个独立连通域 '{out_name}'")

        # 6. select_shape (Regions, SelectedRegions, Features, Operation, Min, Max)
        elif op == "select_shape":
            in_name = i_in[0] if i_in else "Regions"
            out_name = i_out[0] if i_out else "SelectedRegions"
            feature = str(c_in[0]) if len(c_in) > 0 else "area"
            # 兼容单特征与多特征
            min_v = float(c_in[2]) if len(c_in) > 2 else 0.0
            max_v = float(c_in[3]) if len(c_in) > 3 else 999999.0
            src_reg = self.iconic_vars.get(in_name)
            if not isinstance(src_reg, Region):
                raise ValueError(f"输入对象 '{in_name}' 不是有效的 Region")

            kwargs: Dict[str, Any] = {}
            if "area" in feature:
                kwargs["min_area"] = int(min_v)
                kwargs["max_area"] = int(max_v)
            elif "circularity" in feature:
                kwargs["min_circularity"] = float(min_v)
                kwargs["max_circularity"] = float(max_v)
            elif "rectangularity" in feature:
                kwargs["min_rectangularity"] = float(min_v)
                kwargs["max_rectangularity"] = float(max_v)

            filtered = ops.select_shape(src_reg, **kwargs)
            self.iconic_vars[out_name] = filtered
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] select_shape: 按 {feature} 筛选，保留 {len(filtered.objects)} 个目标 -> '{out_name}'")

        # 7. 形态学: opening_circle, closing_circle, dilation_circle, erosion_circle
        elif op in ("opening_circle", "closing_circle", "dilation_circle", "erosion_circle"):
            in_name = i_in[0] if i_in else "Region"
            out_name = i_out[0] if i_out else "RegionMorph"
            radius = int(c_in[0]) if c_in else 3
            op_type = op.split("_")[0]
            src_reg = self.iconic_vars.get(in_name)
            if not isinstance(src_reg, Region):
                raise ValueError(f"输入对象 '{in_name}' 不是有效的 Region")
            m_reg = ops.morphology(src_reg, op_type=op_type, kernel_shape="circle", kernel_size=radius * 2 + 1)
            self.iconic_vars[out_name] = m_reg
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] {op}: 半径={radius} 形态学处理生成 '{out_name}'")

        # 7b. 矩形结构元素形态学: *_rectangle1 (Region, Out, Width, Height)
        elif op in ("dilation_rectangle1", "erosion_rectangle1", "opening_rectangle1", "closing_rectangle1"):
            in_name = i_in[0] if i_in else "Region"
            out_name = i_out[0] if i_out else "RegionMorph"
            if len(c_in) < 2:
                raise ValueError(f"{op} 需要 2 个参数: Width, Height")
            width, height = int(c_in[0]), int(c_in[1])
            src_reg = self.iconic_vars.get(in_name)
            if not isinstance(src_reg, Region):
                raise ValueError(f"输入对象 '{in_name}' 不是有效的 Region")
            self.iconic_vars[out_name] = ops.morphology_rectangle(src_reg, op.split("_")[0], width, height)
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] {op}: 矩形 {width}x{height} 形态学处理生成 '{out_name}'")

        # 7c. 自定义结构元素形态学: erosion1/2, dilation1/2, opening, closing (Region, StructElement, Out, ...)
        elif op in ("erosion1", "erosion2", "dilation1", "dilation2", "opening", "closing"):
            in_name = i_in[0] if len(i_in) > 0 else "Region"
            se_name = i_in[1] if len(i_in) > 1 else "StructElement"
            out_name = i_out[0] if i_out else "RegionMorph"
            src_reg = self.iconic_vars.get(in_name)
            struct_elem = self.iconic_vars.get(se_name)
            if not isinstance(src_reg, Region):
                raise ValueError(f"输入对象 '{in_name}' 不是有效的 Region")
            if not isinstance(struct_elem, Region):
                raise ValueError(f"结构元素 '{se_name}' 不是有效的 Region")
            op_type = op.rstrip("12")
            reference = None
            iterations = 1
            if op.endswith("2"):
                if len(c_in) < 2:
                    raise ValueError(f"{op} 需要参考点参数: Row, Column[, Iterations]")
                reference = (float(c_in[0]), float(c_in[1]))
                iterations = int(c_in[2]) if len(c_in) > 2 else 1
            elif op.endswith("1"):
                iterations = int(c_in[0]) if c_in else 1
            self.iconic_vars[out_name] = ops.morphology_struct_element(
                src_reg, struct_elem, op_type, iterations=iterations, reference=reference
            )
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] {op}: 以 '{se_name}' 为结构元素 (迭代 {iterations} 次) 生成 '{out_name}'")

        # 7d. gen_ellipse (Ellipse, Row, Column, Phi, Radius1, Radius2)
        elif op == "gen_ellipse":
            out_name = i_out[0] if i_out else "Ellipse"
            if len(c_in) < 5:
                raise ValueError("gen_ellipse 需要 5 个参数: Row, Column, Phi, Radius1, Radius2")
            row, col, phi, radius1, radius2 = (float(v) for v in c_in[:5])
            base = next((v for v in reversed(list(self.iconic_vars.values())) if isinstance(v, np.ndarray)), None)
            if base is None:
                raise ValueError("gen_ellipse 之前需要先 read_image 载入图像以确定画布尺寸")
            self.iconic_vars[out_name] = ops.gen_ellipse_region(base.shape[:2], row, col, phi, radius1, radius2)
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] gen_ellipse: 椭圆中心 ({row:g},{col:g}), 半径 {radius1:g}/{radius2:g} -> '{out_name}'")

        # 7f. 区域集合运算与形状算子: fill_up, difference, union1/2, intersection, complement, boundary
        elif op in ("fill_up", "difference", "union1", "union2", "intersection", "complement", "boundary"):
            regions = []
            for name in i_in:
                reg = self.iconic_vars.get(name)
                if not isinstance(reg, Region):
                    raise ValueError(f"输入对象 '{name}' 不是有效的 Region")
                regions.append(reg)
            out_name = i_out[0] if i_out else "RegionResult"
            if op == "fill_up":
                result = ops.fill_up(regions[0])
            elif op == "difference":
                result = ops.region_difference(regions[0], regions[1])
            elif op in ("union1", "union2"):
                result = ops.region_union(*regions)
            elif op == "intersection":
                result = ops.region_intersection(regions[0], regions[1])
            elif op == "complement":
                result = ops.region_complement(regions[0])
            else:
                result = ops.region_boundary(regions[0], str(c_in[0]) if c_in else "inner")
            self.iconic_vars[out_name] = result
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] {op}: 生成 '{out_name}' (面积 {int(np.count_nonzero(result.mask))} px)")

        # 7g. gen_circle (Circle, Row, Column, Radius)
        elif op == "gen_circle":
            out_name = i_out[0] if i_out else "Circle"
            if len(c_in) < 3:
                raise ValueError("gen_circle 需要 3 个参数: Row, Column, Radius")
            row, col, radius = (float(v) for v in c_in[:3])
            base = next((v for v in reversed(list(self.iconic_vars.values())) if isinstance(v, np.ndarray)), None)
            if base is None:
                raise ValueError("gen_circle 之前需要先 read_image 载入图像以确定画布尺寸")
            self.iconic_vars[out_name] = ops.gen_circle_region(base.shape[:2], row, col, radius)
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] gen_circle: 圆心 ({row:g},{col:g}), 半径 {radius:g} -> '{out_name}'")

        # 7i. 形状模板创建: create_shape_model / create_scaled_shape_model
        elif op in ("create_shape_model", "create_scaled_shape_model"):
            tmpl_name = i_in[0] if i_in else "Template"
            template = self.iconic_vars.get(tmpl_name)
            if not isinstance(template, np.ndarray):
                raise ValueError(f"未找到模板图像 '{tmpl_name}'")
            scaled = op == "create_scaled_shape_model"
            expected = 11 if scaled else 8
            if len(c_in) < expected:
                raise ValueError(f"{op} 需要 {expected} 个输入参数, 实际只有 {len(c_in)} 个")
            if scaled:
                num_levels, angle_start, angle_extent, angle_step, scale_min, scale_max, scale_step, _, metric, contrast, min_contrast = c_in[:11]
            else:
                num_levels, angle_start, angle_extent, angle_step, _, metric, contrast, min_contrast = c_in[:8]
                scale_min = scale_max = 1.0
                scale_step = "auto"
            model = build_shape_model(
                template, self.domains.get(tmpl_name), num_levels, float(angle_start), float(angle_extent),
                angle_step, float(scale_min), float(scale_max), scale_step, metric, contrast, min_contrast
            )
            handle = max(self.shape_models, default=-1) + 1
            self.shape_models[handle] = model
            self.control_vars[c_out[0] if c_out else "ModelID"] = handle
            self.log(f"  [{inst.line_num}] {op}: 模板 '{tmpl_name}' 创建形状模型 #{handle} "
                     f"(模板 {model.template.shape[1]}x{model.template.shape[0]} px, {len(model.contours)} 条轮廓)")

        # 7j. 形状模板搜索: find_shape_model / find_scaled_shape_model
        elif op in ("find_shape_model", "find_scaled_shape_model"):
            img_name = i_in[0] if i_in else "Image"
            search_img = self.iconic_vars.get(img_name)
            if not isinstance(search_img, np.ndarray):
                raise ValueError(f"未找到搜索图像 '{img_name}'")
            scaled = op == "find_scaled_shape_model"
            expected = 11 if scaled else 9
            if len(c_in) < expected:
                raise ValueError(f"{op} 需要 {expected} 个输入参数, 实际只有 {len(c_in)} 个")
            model = self.shape_models.get(int(c_in[0]))
            if model is None:
                raise ValueError("形状模型句柄无效: 请先调用 create_shape_model")
            if scaled:
                angle_start, angle_extent, scale_min, scale_max, min_score, num_matches, max_overlap, subpixel, num_levels = c_in[1:10]
            else:
                angle_start, angle_extent, min_score, num_matches, max_overlap, subpixel, num_levels = c_in[1:8]
                scale_min = scale_max = 1.0
            hits = find_shape_models(
                search_img, model, float(angle_start), float(angle_extent), float(scale_min), float(scale_max),
                float(min_score), int(num_matches), float(max_overlap), subpixel, num_levels
            )
            columns = [[h["row"] for h in hits], [h["column"] for h in hits], [h["angle"] for h in hits]]
            if scaled:
                columns.append([h["scale"] for h in hits])
            columns.append([h["score"] for h in hits])
            for name, values in zip(c_out, columns):
                self.control_vars[name] = values
            best = f", 最高得分 {hits[0]['score']:.3f}" if hits else ""
            self.log(f"  [{inst.line_num}] {op}: 在 '{img_name}' 中找到 {len(hits)} 个目标{best}")

        # 7k. 形状模型信息: get_shape_model_params / get_shape_model_contours / clear_shape_model
        elif op in ("get_shape_model_params", "get_shape_model_contours", "clear_shape_model"):
            model = self.shape_models.get(int(c_in[0])) if c_in else None
            if model is None:
                raise ValueError("形状模型句柄无效: 请先调用 create_shape_model")
            if op == "get_shape_model_params":
                values = [model.num_levels, model.angle_start, model.angle_extent, model.angle_step,
                          model.scale_min, model.scale_max, model.scale_step, model.metric, model.min_contrast]
                for name, value in zip(c_out, values):
                    self.control_vars[name] = value
            elif op == "get_shape_model_contours":
                out_name = i_out[0] if i_out else "ModelContours"
                self.iconic_vars[out_name] = list(model.contours)
                self.log(f"  [{inst.line_num}] {op}: 取得 {len(model.contours)} 条模型轮廓 -> '{out_name}' (以模型原点为 (0, 0))")
            else:
                del self.shape_models[int(c_in[0])]

        # 7l. 2D 齐次矩阵与轮廓仿射变换
        elif op in ("hom_mat2d_identity", "hom_mat2d_translate", "hom_mat2d_rotate", "hom_mat2d_scale", "vector_angle_to_rigid"):
            if op == "hom_mat2d_identity":
                mat = hdev_geometry.identity()
            elif op == "hom_mat2d_translate":
                mat = hdev_geometry.translate(c_in[0], float(c_in[1]), float(c_in[2]))
            elif op == "hom_mat2d_rotate":
                mat = hdev_geometry.rotate(c_in[0], float(c_in[1]), float(c_in[2]), float(c_in[3]))
            elif op == "hom_mat2d_scale":
                mat = hdev_geometry.scale(c_in[0], float(c_in[1]), float(c_in[2]), float(c_in[3]), float(c_in[4]))
            else:
                mat = hdev_geometry.vector_angle_to_rigid(*(float(v) for v in c_in[:6]))
            self.control_vars[c_out[0] if c_out else "HomMat2D"] = list(mat)

        elif op == "affine_trans_contour_xld":
            in_name = i_in[0] if i_in else "Contours"
            out_name = i_out[0] if i_out else "ContoursAffineTrans"
            contours = self.iconic_vars.get(in_name)
            if not (isinstance(contours, list) and all(isinstance(c, XLDContour) for c in contours)):
                raise ValueError(f"输入对象 '{in_name}' 不是有效的 XLD 轮廓")
            if not c_in:
                raise ValueError("affine_trans_contour_xld 需要 HomMat2D 参数")
            self.iconic_vars[out_name] = hdev_geometry.affine_trans_contours(contours, c_in[0])
            self.display_target = out_name

        # 7m. draw_circle: 读取用户在图形窗口里预先画好的圆形 ROI (脚本一次性运行, 不能中途等待鼠标)
        elif op == "draw_circle":
            geom = self.roi_geometry
            if not geom or geom.get("type") != "circle":
                raise ValueError('draw_circle 需要先用图形窗口工具栏的"圆"画出圆形 ROI, 然后再运行脚本')
            for name, value in zip(c_out, (float(geom["cy"]), float(geom["cx"]), float(geom["r"]))):
                self.control_vars[name] = value
            self.log(f"  [{inst.line_num}] draw_circle: 使用已画好的圆形 ROI, 圆心 ({geom['cy']},{geom['cx']}), 半径 {geom['r']}")

        # 7n. dev_disp_text: 在当前窗口显示文字 (行列可为像素数值, 'top'/'left' 等关键字按左上角 12 像素处理)
        elif op == "dev_disp_text":
            text = c_in[0] if c_in else ""
            win = self._cur_win()
            win.messages.append({
                "text": "\n".join(map(str, text)) if isinstance(text, list) else str(text),
                "row": c_in[2] if len(c_in) > 2 and isinstance(c_in[2], (int, float)) else 12,
                "col": c_in[3] if len(c_in) > 3 and isinstance(c_in[3], (int, float)) else 12,
                "color": c_in[4] if len(c_in) > 4 and isinstance(c_in[4], str) else "black",
                "box": True,
            })

        # 7o. 文字区域算子: smallest_rectangle1, sort_region, char_threshold
        elif op in ("smallest_rectangle1", "sort_region"):
            in_name = i_in[0] if i_in else "Regions"
            src_reg = self.iconic_vars.get(in_name)
            if not isinstance(src_reg, Region):
                raise ValueError(f"输入对象 '{in_name}' 不是有效的 Region")
            if op == "smallest_rectangle1":
                for var, values in zip(c_out, text_region_ops.smallest_rectangle1(src_reg)):
                    self.control_vars[var] = values
                self.log(f"  [{inst.line_num}] smallest_rectangle1: 输出 {len(self.control_vars.get(c_out[0], [])) if c_out else 0} 个外接矩形")
            else:
                if len(c_in) < 3:
                    raise ValueError("sort_region 需要 3 个参数: SortMode, Order, RowOrCol")
                out_name = i_out[0] if i_out else "SortedRegions"
                self.iconic_vars[out_name] = text_region_ops.sort_region(src_reg, c_in[0], c_in[1], c_in[2])
                self.display_target = out_name
                self.log(f"  [{inst.line_num}] sort_region: 按 '{c_in[0]}' / row-or-column '{c_in[2]}' 排序 -> '{out_name}'")

        elif op == "char_threshold":
            img_name = i_in[0] if i_in else "Image"
            src = self.iconic_vars.get(img_name)
            if not isinstance(src, np.ndarray):
                raise ValueError(f"未找到输入图像 '{img_name}'")
            gray = ops.rgb1_to_gray(src) if src.ndim == 3 else src
            histo = self.iconic_vars.get(i_in[1]) if len(i_in) > 1 else None
            domain = histo.mask > 0 if isinstance(histo, Region) else self.domains.get(img_name)
            sigma = float(c_in[0]) if c_in else text_region_ops.DEFAULT_SIGMA
            region, threshold = text_region_ops.char_threshold(gray, domain, sigma)
            out_name = i_out[0] if i_out else "Characters"
            self.iconic_vars[out_name] = region
            self.display_target = out_name
            if c_out:
                self.control_vars[c_out[0]] = threshold
            self.log(f"  [{inst.line_num}] char_threshold: 阈值 {threshold}, 字符区域 {int(np.count_nonzero(region.mask))} px -> '{out_name}'")

        # 7p. 交互与窗口: draw_rectangle1 读取预先画好的矩形 ROI, dev_get_window 返回当前窗口句柄
        elif op == "draw_rectangle1":
            geom = self.roi_geometry
            if not geom or geom.get("type") != "rect":
                raise ValueError('draw_rectangle1 需要先用图形窗口工具栏的"矩形"画出矩形 ROI, 然后再运行脚本')
            x, y, w, h = (int(geom[k]) for k in ("x", "y", "w", "h"))
            for name, value in zip(c_out, (y, x, y + h - 1, x + w - 1)):
                self.control_vars[name] = value
            self.log(f"  [{inst.line_num}] draw_rectangle1: 使用已画好的矩形 ROI ({y},{x})-({y + h - 1},{x + w - 1})")

        elif op == "dev_get_window":
            self.control_vars[c_out[0] if c_out else "WindowHandle"] = self.active_window

        # 7q. 图像矫正: affine_trans_image / rotate_image
        elif op in ("affine_trans_image", "rotate_image"):
            in_name = i_in[0] if i_in else "Image"
            src = self.iconic_vars.get(in_name)
            if not isinstance(src, np.ndarray):
                raise ValueError(f"未找到输入图像 '{in_name}'")
            if op == "affine_trans_image":
                if len(c_in) < 1:
                    raise ValueError("affine_trans_image 需要 HomMat2D 参数")
                adapt = str(c_in[2]).lower() == "true" if len(c_in) > 2 else False
                result = hdev_geometry.affine_trans_image(src, c_in[0], str(c_in[1]) if len(c_in) > 1 else "bilinear", adapt)
            else:
                if len(c_in) < 1:
                    raise ValueError("rotate_image 需要 Phi 参数 (角度)")
                result = hdev_geometry.rotate_image(src, float(c_in[0]), str(c_in[1]) if len(c_in) > 1 else "bilinear")
            out_name = i_out[0] if i_out else "ImageResult"
            self.iconic_vars[out_name] = result
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] {op}: 输出 {result.shape[1]}x{result.shape[0]} 图像 -> '{out_name}'")

        # 7r. OCR 训练: append_ocr_trainf / read_ocr_trainf_names / create_ocr_class_mlp /
        #     trainf_ocr_class_mlp / write_ocr_class_mlp / clear_ocr_class_mlp
        elif op == "append_ocr_trainf":
            char_name = i_in[0] if i_in else "Character"
            reg = self.iconic_vars.get(char_name)
            if not isinstance(reg, Region):
                raise ValueError(f"输入对象 '{char_name}' 不是有效的 Region")
            if len(c_in) < 2:
                raise ValueError("append_ocr_trainf 需要 Class 与 TrainingFile 两个参数")
            classes = c_in[0] if isinstance(c_in[0], list) else [c_in[0]]
            connected = reg if reg.is_connected else ops.connection(reg)
            features = []
            for obj in connected.objects:
                feat = ocr_mlp.glyph_feature(obj.bbox_mask(connected.mask))
                if feat is None:
                    raise ValueError("字符区域太小, 无法作为训练样本")
                features.append(feat)
            path = workspace.workspace_path(c_in[1])
            ocr_mlp.append_samples(path, features, [str(c) for c in classes])
            self.log(f"  [{inst.line_num}] append_ocr_trainf: 追加 {len(features)} 个样本 ({''.join(str(c) for c in classes)}) -> {path.name}")

        elif op == "read_ocr_trainf_names":
            names, counts = ocr_mlp.read_names(workspace.workspace_path(c_in[0] if c_in else ""))
            if len(c_out) > 0:
                self.control_vars[c_out[0]] = names
            if len(c_out) > 1:
                self.control_vars[c_out[1]] = counts
            self.log(f"  [{inst.line_num}] read_ocr_trainf_names: {len(names)} 个字符 {names}")

        elif op == "create_ocr_class_mlp":
            if len(c_in) < 9:
                raise ValueError("create_ocr_class_mlp 需要 9 个参数: WidthCharacter ... RandSeed")
            characters = c_in[4] if isinstance(c_in[4], list) else [c_in[4]]
            classifier = TrainedOcrClassifier(characters, int(c_in[5]), int(c_in[8]))
            handle = max(self.ocr_handles, default=-1) + 1
            self.ocr_handles[handle] = classifier
            self.control_vars[c_out[0] if c_out else "OCRHandle"] = handle
            self.log(f"  [{inst.line_num}] create_ocr_class_mlp: 创建 MLP 分类器 #{handle} ({len(classifier.characters)} 类, 隐藏单元 {classifier.num_hidden}); "
                     "字符宽高 / 插值 / 特征 / 预处理参数在本平台由内部固定的字形归一化代替")

        elif op in ("trainf_ocr_class_mlp", "write_ocr_class_mlp", "clear_ocr_class_mlp"):
            handle = int(c_in[0]) if c_in else -1
            classifier = self.ocr_handles.get(handle)
            if op == "clear_ocr_class_mlp":
                self.ocr_handles.pop(handle, None)
            elif not isinstance(classifier, TrainedOcrClassifier):
                raise ValueError("OCR 句柄无效: 需要先用 create_ocr_class_mlp 创建 (或 read_ocr_class_mlp 读取) 可训练的分类器")
            elif op == "trainf_ocr_class_mlp":
                if len(c_in) < 5:
                    raise ValueError("trainf_ocr_class_mlp 需要 5 个输入参数")
                features, labels = ocr_mlp.load_samples(workspace.workspace_path(c_in[1]))
                error, error_log = classifier.train(features, labels, int(c_in[2]), float(c_in[4]))
                if len(c_out) > 0:
                    self.control_vars[c_out[0]] = error
                if len(c_out) > 1:
                    self.control_vars[c_out[1]] = error_log
                self.log(f"  [{inst.line_num}] trainf_ocr_class_mlp: 用 {len(labels)} 个样本训练, 平均平方误差 {error:.5f} (记录 {len(error_log)} 次)")
            else:
                path = workspace.workspace_path(c_in[1] if len(c_in) > 1 else "")
                classifier.save(path)
                self.log(f"  [{inst.line_num}] write_ocr_class_mlp: 已保存分类器 -> {path.name}")

        # 7s. 文件读写 (限定在工作区): open_file / fwrite_string / fnew_line / close_file
        elif op == "open_file":
            if len(c_in) < 2:
                raise ValueError("open_file 需要 FileName 与 Mode 两个参数")
            modes = {"output": "w", "append": "a"}
            mode = str(c_in[1]).lower()
            if mode not in modes:
                raise ValueError("open_file 的 Mode 只支持 'output' 与 'append'")
            path = workspace.workspace_path(c_in[0])
            handle = max(self.open_files, default=-1) + 1
            self.open_files[handle] = open(path, modes[mode], encoding="utf-8")
            self.control_vars[c_out[0] if c_out else "FileHandle"] = handle
            self.log(f"  [{inst.line_num}] open_file: 打开 {path} ({mode})")

        elif op in ("fwrite_string", "fnew_line", "close_file"):
            handle = int(c_in[0]) if c_in else -1
            stream = self.open_files.get(handle)
            if stream is None:
                raise ValueError("文件句柄无效: 请先调用 open_file")
            if op == "fwrite_string":
                value = c_in[1] if len(c_in) > 1 else ""
                stream.write("".join(str(v) for v in value) if isinstance(value, list) else str(value))
            elif op == "fnew_line":
                stream.write("\n")
            else:
                stream.close()
                del self.open_files[handle]
                self.log(f"  [{inst.line_num}] close_file: 已关闭文件句柄 {handle}")

        # 7t. 文件列表与字符串筛选: list_files / tuple_regexp_select
        elif op == "list_files":
            files = file_ops.list_files(c_in[0] if c_in else "", c_in[1] if len(c_in) > 1 else "files")
            self.control_vars[c_out[0] if c_out else "Files"] = files
            self.log(f"  [{inst.line_num}] list_files: 找到 {len(files)} 个文件")

        elif op == "tuple_regexp_select":
            if len(c_in) < 2:
                raise ValueError("tuple_regexp_select 需要 Data 与 Expression 两个参数")
            selected = file_ops.regexp_select(c_in[0], c_in[1])
            self.control_vars[c_out[0] if c_out else "Selected"] = selected
            self.log(f"  [{inst.line_num}] tuple_regexp_select: 选出 {len(selected)} 项")

        # 7h. 纯显示样式设置: 区域本平台已按对象自动分色, 字体不影响计算结果
        elif op in ("dev_set_colored", "set_display_font"):
            self.log(f"  [{inst.line_num}] {op}: 仅影响显示样式, 本平台已自动处理, 无需执行")

        # 7e. get_image_size (Image, Width, Height)
        elif op == "get_image_size":
            in_name = i_in[0] if i_in else "Image"
            src = self.iconic_vars.get(in_name)
            if isinstance(src, Region):
                shape = src.mask.shape
            elif isinstance(src, np.ndarray):
                shape = src.shape
            else:
                raise ValueError(f"未找到输入图像 '{in_name}'")
            width_var = c_out[0] if len(c_out) > 0 else "Width"
            height_var = c_out[1] if len(c_out) > 1 else "Height"
            self.control_vars[width_var] = int(shape[1])
            self.control_vars[height_var] = int(shape[0])
            self.log(f"  [{inst.line_num}] get_image_size: {width_var}={shape[1]}, {height_var}={shape[0]}")

        # 8. 平滑滤波: mean_image, gauss_filter, median_image
        elif op in ("mean_image", "gauss_filter", "median_image"):
            in_name = i_in[0] if i_in else "Image"
            out_name = i_out[0] if i_out else "ImageFiltered"
            src = self.iconic_vars.get(in_name)
            if src is None:
                raise ValueError(f"未找到输入图像 '{in_name}'")
            if op == "mean_image":
                k = int(c_in[0]) if c_in else 5
                filt = ops.filter_image(src, filter_type="mean", kernel_size=k)
            elif op == "gauss_filter":
                sz = int(c_in[0]) if c_in else 5
                filt = ops.filter_image(src, filter_type="gaussian", kernel_size=sz, sigma=1.5)
            else:
                rad = int(c_in[1]) if len(c_in) > 1 else (int(c_in[0]) if c_in else 3)
                filt = ops.filter_image(src, filter_type="median", kernel_size=rad * 2 + 1)
            self.iconic_vars[out_name] = filt
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] {op}: 滤波输出图像 '{out_name}'")

        # 9. edges_subpix (Image, Edges, Filter, Alpha, Low, High)
        elif op == "edges_subpix":
            in_name = i_in[0] if i_in else "Image"
            out_name = i_out[0] if i_out else "Edges"
            low_t = float(c_in[2]) if len(c_in) > 2 else (float(c_in[0]) if len(c_in) > 0 else 30.0)
            high_t = float(c_in[3]) if len(c_in) > 3 else (float(c_in[1]) if len(c_in) > 1 else 90.0)
            src = self.iconic_vars.get(in_name)
            if src is None:
                raise ValueError(f"未找到输入图像 '{in_name}'")
            gray = ops.rgb1_to_gray(src) if len(src.shape) == 3 else src
            contours = ops.edges_subpix(gray, low_thresh=low_t, high_thresh=high_t)
            self.iconic_vars[out_name] = contours
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] edges_subpix: 提取到 {len(contours)} 条亚像素 XLD 轮廓 -> '{out_name}'")

        # 10. 几何特征测量算子: smallest_rectangle2, smallest_circle, area_center, count_obj
        elif op in ("smallest_rectangle2", "smallest_circle", "area_center", "measure_region"):
            in_name = i_in[0] if i_in else "Regions"
            src_reg = self.iconic_vars.get(in_name)
            if not isinstance(src_reg, Region):
                raise ValueError(f"输入对象 '{in_name}' 不是有效的 Region")
            if op == "smallest_rectangle2" and len(c_out) >= 5:
                # Row, Column, Phi, Length1, Length2: Phi 为最长边与水平方向的夹角 (弧度, 逆时针为正)
                for name, values in zip(c_out, text_region_ops.smallest_rectangle2(src_reg)):
                    self.control_vars[name] = values
                self.log(f"  [{inst.line_num}] smallest_rectangle2: 输出旋转矩形特征到变量 {c_out}")

            elif op == "smallest_circle" and len(c_out) >= 3:
                for name, values in zip(c_out, text_region_ops.smallest_circle(src_reg)):
                    self.control_vars[name] = values
                self.log(f"  [{inst.line_num}] smallest_circle: 输出最小外接圆特征到变量 {c_out}")

            elif op == "area_center" and len(c_out) >= 3:
                items = text_region_ops.region_items(src_reg)
                areas = [area for _, area, _ in items]
                rows = [centroid[0] for _, _, centroid in items]
                cols = [centroid[1] for _, _, centroid in items]
                self.control_vars[c_out[0]] = areas
                self.control_vars[c_out[1]] = rows
                self.control_vars[c_out[2]] = cols
                self.log(f"  [{inst.line_num}] area_center: 输出面积与中心坐标到变量 {c_out}")
            else:
                self.control_vars["Metrics"] = ops.measure_region(src_reg)
                self.log(f"  [{inst.line_num}] measure_region: 计算完成并存入 Metrics")

        # 10c. select_obj (Objects, ObjectSelected, Index): 按 1 起始下标取出单个连通域
        elif op == "select_obj":
            in_name = i_in[0] if i_in else "Objects"
            out_name = i_out[0] if i_out else "ObjectSelected"
            src_reg = self.iconic_vars.get(in_name)
            if not isinstance(src_reg, Region):
                raise ValueError(f"输入对象 '{in_name}' 不是有效的 Region")
            index = int(c_in[0]) if c_in else 1
            if not 1 <= index <= len(src_reg.objects):
                raise ValueError(f"select_obj 下标 {index} 超出范围 (共 {len(src_reg.objects)} 个目标)")
            obj = src_reg.objects[index - 1]
            r0, c0, r1, c1 = obj.bbox
            mask = np.zeros_like(src_reg.mask)
            mask[r0:r1, c0:c1] = obj.bbox_mask(src_reg.mask)
            self.iconic_vars[out_name] = Region(mask=mask, objects=[obj], is_connected=True)
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] select_obj: 取第 {index} 个目标 -> '{out_name}'")

        # 11. count_obj (Objects, Number)
        elif op == "count_obj":
            in_name = i_in[0] if i_in else "Objects"
            out_var = c_out[0] if c_out else "Number"
            obj = self.iconic_vars.get(in_name)
            count = len(obj.objects) if isinstance(obj, Region) else (len(obj) if isinstance(obj, list) else (1 if obj is not None else 0))
            self.control_vars[out_var] = count
            self.log(f"  [{inst.line_num}] count_obj: 目标数量 = {count} -> {out_var}")

        # 12. dev_display / disp_obj (Object): 模拟 HALCON 图形窗口叠加语义
        elif op in ("dev_display", "disp_obj"):
            in_name = i_in[0] if i_in else "Object"
            obj = self.iconic_vars.get(in_name)
            if obj is not None:
                self.explicit_display_used = True
                self.display_target = in_name
                win = self._cur_win()
                if isinstance(obj, np.ndarray):
                    # 显示新图像 = 整个画布被重绘, 之前叠加的 Region/XLD 不再可见
                    win.image_name = in_name
                    win.region_names = []
                    win.xld_names = []
                    win.messages = []
                    self.log(f"  [{inst.line_num}] {op}: 窗口 #{win.handle} 显示图像 '{in_name}' (画布重绘, 叠加层已清空)")
                elif isinstance(obj, Region):
                    self._pin_display_object(win.region_names, in_name, obj)
                    self.log(f"  [{inst.line_num}] {op}: 窗口 #{win.handle} 叠加显示 Region '{in_name}' (当前叠加层: {win.region_names})")
                elif isinstance(obj, list) and obj and isinstance(obj[0], XLDContour):
                    self._pin_display_object(win.xld_names, in_name, obj)
                    self.log(f"  [{inst.line_num}] {op}: 窗口 #{win.handle} 叠加显示 XLD 轮廓 '{in_name}' (当前叠加层: {win.xld_names})")

        # 12b. dev_clear_window: 清空当前活跃图形窗口的所有叠加层
        elif op == "dev_clear_window":
            win = self._cur_win()
            win.image_name = None
            win.region_names = []
            win.xld_names = []
            win.messages = []
            self.log(f"  [{inst.line_num}] dev_clear_window: 已清空窗口 #{win.handle} 的叠加层")

        # 12c. dev_open_window / dev_open_window_fit_image: 新建图形窗口并设为当前活跃窗口
        elif op in ("dev_open_window", "dev_open_window_fit_image"):
            handle = self._next_window_handle
            self._next_window_handle += 1
            self.windows[handle] = _WindowState(handle=handle)
            self.active_window = handle
            self.explicit_display_used = True
            out_var = c_out[0] if c_out else "WindowHandle"
            self.control_vars[out_var] = handle
            self.log(f"  [{inst.line_num}] {op}: 打开图形窗口 #{handle} 并设为当前活跃窗口 -> {out_var}")

        # 12d. dev_close_window: 关闭当前活跃图形窗口
        elif op == "dev_close_window":
            closed = self.active_window
            self.windows.pop(closed, None)
            if not self.windows:
                self.windows[0] = _WindowState(handle=0)
                self.active_window = 0
            else:
                self.active_window = max(self.windows.keys())
            self.log(f"  [{inst.line_num}] dev_close_window: 关闭窗口 #{closed}, 当前活跃窗口切换为 #{self.active_window}")

        # 12e. dev_set_window: 切换当前活跃图形窗口 (用于在多窗口间来回绘制)
        elif op == "dev_set_window":
            handle = int(c_in[0]) if c_in else 0
            if handle not in self.windows:
                self.windows[handle] = _WindowState(handle=handle)
            self.active_window = handle
            self.explicit_display_used = True
            self.log(f"  [{inst.line_num}] dev_set_window: 切换当前活跃窗口为 #{handle}")

        # 13. 色彩空间转换: rgb_to_hsv, hsv_threshold
        elif op == "rgb_to_hsv":
            in_name = i_in[0] if i_in else "Image"
            out_name = i_out[0] if i_out else "HSVImage"
            src = self.iconic_vars.get(in_name)
            hsv = ops.rgb_to_hsv(src)
            self.iconic_vars[out_name] = hsv
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] rgb_to_hsv: 转换为 HSV 图像 '{out_name}'")

        # 14. 轮廓多边形近似: gen_contour_polygon_xld
        elif op == "gen_contour_polygon_xld":
            in_name = i_in[0] if i_in else "Contour"
            out_name = i_out[0] if i_out else "Polygons"
            dist = float(c_in[1]) if len(c_in) > 1 else 2.0
            contours = self.iconic_vars.get(in_name, [])
            polys = ops.gen_contour_polygon(contours, epsilon=dist)
            self.iconic_vars[out_name] = polys
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] gen_contour_polygon_xld: 多边形折线简化 -> '{out_name}'")

        # 15. 十字交叉 XLD 轮廓生成: gen_cross_contour_xld (Crosses, Row, Col, Length, Phi)
        elif op == "gen_cross_contour_xld":
            out_name = i_out[0] if i_out else "Crosses"
            rows = c_in[0] if len(c_in) > 0 else []
            cols = c_in[1] if len(c_in) > 1 else []
            length = float(c_in[2]) if len(c_in) > 2 else 6.0
            phi = float(c_in[3]) if len(c_in) > 3 else 0.785398
            crosses = ops.gen_cross_contour_xld(rows, cols, length=length, phi=phi)
            self.iconic_vars[out_name] = crosses
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] gen_cross_contour_xld: 生成 {len(crosses)//2} 组十字交叉标定标记 -> '{out_name}'")

        # 16. 单应性投影矩阵求解: hom_vector_to_proj_hom_mat2d
        elif op in ("hom_vector_to_proj_hom_mat2d", "vector_to_proj_hom_mat2d"):
            out_var = c_out[0] if c_out else "HomMat2D"
            px = c_in[0] if len(c_in) > 0 else []
            py = c_in[1] if len(c_in) > 1 else []
            # 跳过 Pw (如果有的话)
            if op == "hom_vector_to_proj_hom_mat2d" and len(c_in) >= 6:
                qx = c_in[3]
                qy = c_in[4]
                method = str(c_in[6]) if len(c_in) > 6 else "normalized_dlt"
            else:
                qx = c_in[2] if len(c_in) > 2 else []
                qy = c_in[3] if len(c_in) > 3 else []
                method = str(c_in[4]) if len(c_in) > 4 else "normalized_dlt"

            H = ops.hom_vector_to_proj_hom_mat2d(px, py, qx, qy, method=method)
            self.control_vars[out_var] = H.tolist()
            self.log(f"  [{inst.line_num}] {op}: 计算 3x3 投影单应性矩阵 -> {out_var}")

        # 17. 图像投影变换矫正: projective_trans_image
        elif op in ("projective_trans_image", "projective_trans_image_size"):
            in_name = i_in[0] if i_in else "Image"
            out_name = i_out[0] if i_out else "Image_rectified"
            mat_val = c_in[0] if len(c_in) > 0 else self.control_vars.get("HomMat2D", "HomMat2D")
            interp = str(c_in[1]) if len(c_in) > 1 else "bilinear"
            
            src = self.iconic_vars.get(in_name)
            if src is None:
                raise ValueError(f"未找到输入图像 '{in_name}'")
            
            rectified = ops.projective_trans_image(src, mat_val, interpolation=interp)
            self.iconic_vars[out_name] = rectified
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] {op}: 透视矫正完成 -> '{out_name}', 分辨率={rectified.shape}")

        # 18. HALCON 图形窗口与渲染属性控制 (静默无损映射)
        elif op in GRAPHICS_STYLE_OPERATORS:
            # 记录属性配置
            if op == "dev_set_color" and c_in:
                self.control_vars["_draw_color"] = str(c_in[0])
            elif op == "dev_set_line_width" and c_in:
                self.control_vars["_line_width"] = float(c_in[0])
            self.log(f"  [{inst.line_num}] {op}: 图形环境配置更新 {c_in}")

        # 19. 点/直线间距离与夹角测量: distance_pp, distance_pl, angle_ll
        elif op == "distance_pp":
            r1, c1, r2, c2 = (float(c_in[i]) for i in range(4))
            dist = ops.distance_pp(r1, c1, r2, c2)
            out_var = c_out[0] if c_out else "Distance"
            self.control_vars[out_var] = dist
            self.log(f"  [{inst.line_num}] distance_pp: 两点距离 = {dist}")

        elif op == "distance_pl":
            r, c, rb, cb, re_, ce = (float(c_in[i]) for i in range(6))
            dist = ops.distance_pl(r, c, rb, cb, re_, ce)
            out_var = c_out[0] if c_out else "Distance"
            self.control_vars[out_var] = dist
            self.log(f"  [{inst.line_num}] distance_pl: 点到直线距离 = {dist}")

        elif op == "angle_ll":
            vals = [float(c_in[i]) for i in range(8)]
            angle = ops.angle_ll(*vals)
            out_var = c_out[0] if c_out else "Angle"
            self.control_vars[out_var] = angle
            self.log(f"  [{inst.line_num}] angle_ll: 直线夹角 = {angle} rad")

        # 20. XLD 轮廓最小二乘拟合: fit_line_contour_xld, fit_circle_contour_xld
        elif op in ("fit_line_contour_xld", "fit_circle_contour_xld"):
            in_name = i_in[0] if i_in else "Contours"
            contours = self.iconic_vars.get(in_name)
            if not contours:
                raise ValueError(f"未找到输入轮廓 '{in_name}'")
            if isinstance(contours, XLDContour):
                contours = [contours]

            if op == "fit_line_contour_xld":
                keys = ["row_begin", "col_begin", "row_end", "col_end", "nr", "nc", "dist"]
                results = [ops.fit_line_contour_xld(cnt.points) for cnt in contours]
            else:
                keys = ["row", "col", "radius", "start_phi", "end_phi", "point_order"]
                results = [ops.fit_circle_contour_xld(cnt.points) for cnt in contours]

            for idx, key in enumerate(keys):
                if idx < len(c_out):
                    self.control_vars[c_out[idx]] = [r[key] for r in results]
            self.log(f"  [{inst.line_num}] {op}: 对 {len(contours)} 条轮廓完成最小二乘拟合 -> {c_out}")

        # 21. Sobel 边缘幅值: sobel_amp
        elif op == "sobel_amp":
            in_name = i_in[0] if i_in else "Image"
            out_name = i_out[0] if i_out else "EdgeAmplitude"
            src = self.iconic_vars.get(in_name)
            if src is None:
                raise ValueError(f"未找到输入图像 '{in_name}'")
            filter_type = str(c_in[0]) if len(c_in) > 0 else "sum_abs"
            size = int(c_in[1]) if len(c_in) > 1 else 3
            amp = ops.sobel_amp(src, filter_type=filter_type, size=size)
            self.iconic_vars[out_name] = amp
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] sobel_amp: 计算 Sobel 边缘幅值图像 ({filter_type}) -> '{out_name}'")

        # 22. 区域骨架细化: skeleton
        elif op == "skeleton":
            in_name = i_in[0] if i_in else "Region"
            out_name = i_out[0] if i_out else "Skeleton"
            src_reg = self.iconic_vars.get(in_name)
            if not isinstance(src_reg, Region):
                raise ValueError(f"输入对象 '{in_name}' 不是有效的 Region")
            skel = ops.skeleton(src_reg)
            self.iconic_vars[out_name] = skel
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] skeleton: 完成区域骨架细化 -> '{out_name}'")

        # 23. 拉普拉斯边缘增强: laplace
        elif op == "laplace":
            in_name = i_in[0] if i_in else "Image"
            out_name = i_out[0] if i_out else "ImageLaplace"
            src = self.iconic_vars.get(in_name)
            if src is None:
                raise ValueError(f"未找到输入图像 '{in_name}'")
            result_type = str(c_in[0]) if len(c_in) > 0 else "signed"
            mask_size = int(c_in[1]) if len(c_in) > 1 else 3
            lap = ops.laplace_filter(src, result=result_type, mask_size=mask_size)
            self.iconic_vars[out_name] = lap
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] laplace: 拉普拉斯滤波完成 ({result_type}) -> '{out_name}'")

        # 23b. gen_rectangle1 (Rectangle, Row1, Column1, Row2, Column2): 轴对齐矩形 ROI
        elif op == "gen_rectangle1":
            out_name = i_out[0] if i_out else "Rectangle"
            if len(c_in) < 4:
                raise ValueError("gen_rectangle1 需要 4 个参数: Row1, Column1, Row2, Column2")
            row1, col1, row2, col2 = (int(v) for v in c_in[:4])
            base = next((v for v in reversed(list(self.iconic_vars.values())) if isinstance(v, np.ndarray)), None)
            if base is None:
                raise ValueError("gen_rectangle1 之前需要先 read_image 载入图像以确定画布尺寸")
            geometry = {"type": "rect", "x": col1, "y": row1, "w": col2 - col1 + 1, "h": row2 - row1 + 1}
            self.iconic_vars[out_name] = ops.create_mask_from_geometry(base.shape[:2], geometry)
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] gen_rectangle1: ROI 矩形 ({row1},{col1})-({row2},{col2}) -> '{out_name}'")

        # 23c. reduce_domain (Image, Region, ImageReduced): 把图像定义域限制到 ROI 内
        elif op == "reduce_domain":
            img_name = i_in[0] if len(i_in) > 0 else "Image"
            reg_name = i_in[1] if len(i_in) > 1 else "Region"
            out_name = i_out[0] if i_out else "ImageReduced"
            src = self.iconic_vars.get(img_name)
            roi = self.iconic_vars.get(reg_name)
            if src is None:
                raise ValueError(f"未找到输入图像 '{img_name}'")
            if not isinstance(roi, Region):
                raise ValueError(f"输入对象 '{reg_name}' 不是有效的 Region")
            if roi.mask.shape[:2] != src.shape[:2]:
                fitted = np.zeros(src.shape[:2], dtype=np.uint8)
                rows, cols = min(fitted.shape[0], roi.mask.shape[0]), min(fitted.shape[1], roi.mask.shape[1])
                fitted[:rows, :cols] = roi.mask[:rows, :cols]
                roi = Region(mask=fitted, is_connected=False)
            self.iconic_vars[out_name] = ops.reduce_domain(src, roi)
            self.domains[out_name] = roi.mask > 0
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] reduce_domain: 图像 '{img_name}' 限制到 ROI '{reg_name}' -> '{out_name}'")

        # 24. OCR 字符识别: read_ocr_class_mlp / do_ocr_multi_class_mlp
        elif op == "read_ocr_class_mlp":
            handle_var = c_out[0] if c_out else "OCRHandle"
            library = str(c_in[0]) if c_in else ""
            saved_path = workspace.workspace_path(library) if library else None
            handle = max(self.ocr_handles, default=-1) + 1
            if saved_path is not None and saved_path.exists():
                self.ocr_handles[handle] = TrainedOcrClassifier.load(saved_path)
                message = f"已读取训练好的分类器 {saved_path.name}"
            elif ocr_chars.is_builtin_library(library):
                charset_name = ocr_chars.charset_name_for_library(library)
                ocr_chars.get_classifier(charset_name)
                self.ocr_handles[handle] = charset_name
                message = f"已载入内置字符分类器 ({charset_name}), 请求的字符库 '{library}' 以此替代"
            else:
                raise FileNotFoundError(f"找不到分类器文件 '{library}': 工作区里没有这个文件, 也不是内置字符库名 (请先训练并 write_ocr_class_mlp)")
            self.control_vars[handle_var] = handle
            self.log(f"  [{inst.line_num}] read_ocr_class_mlp: {message} -> {handle_var}")

        elif op == "do_ocr_multi_class_mlp":
            char_name = i_in[0] if i_in else "Character"
            src_reg = self.iconic_vars.get(char_name)
            if not isinstance(src_reg, Region):
                raise ValueError(f"输入对象 '{char_name}' 不是有效的 Region")
            handle = c_in[0] if c_in else None
            if handle not in self.ocr_handles:
                raise ValueError("OCR 句柄无效: 请先调用 read_ocr_class_mlp")
            details = ocr_chars.recognize_regions(src_reg, self.ocr_handles[handle])
            classes = [d["char"] for d in details]
            confidences = [d["confidence"] for d in details]
            self.ocr_result = {
                "text": "".join(classes),
                "mean_confidence": round(sum(confidences) / len(confidences), 3) if confidences else 0.0,
                "chars": [{"index": i + 1, **d} for i, d in enumerate(details)],
            }
            class_var = c_out[0] if len(c_out) > 0 else "Class"
            conf_var = c_out[1] if len(c_out) > 1 else "Confidence"
            self.control_vars[class_var] = classes
            self.control_vars[conf_var] = confidences
            self.log(f"  [{inst.line_num}] do_ocr_multi_class_mlp: 识别 {len(classes)} 个字符 -> {class_var} = {''.join(classes)}")

        # 25. disp_message (WindowHandle, String, CoordSystem, Row, Column, Color, Box)
        elif op == "disp_message":
            text_val = c_in[1] if len(c_in) > 1 else ""
            if isinstance(text_val, list):
                text = "".join(map(str, text_val)) if all(len(str(t)) == 1 for t in text_val) else "\n".join(map(str, text_val))
            else:
                text = str(text_val)
            handle = int(c_in[0]) if len(c_in) > 0 and str(c_in[0]).lstrip("-").isdigit() else self.active_window
            win = self.windows.get(handle, self._cur_win())
            row_val = c_in[3] if len(c_in) > 3 else 12
            col_val = c_in[4] if len(c_in) > 4 else 12
            color = c_in[5] if len(c_in) > 5 else "black"
            box = str(c_in[6]).lower() == "true" if len(c_in) > 6 else True
            per_position = (isinstance(text_val, list) and isinstance(row_val, list) and isinstance(col_val, list)
                            and len(text_val) == len(row_val) == len(col_val) and len(text_val) > 0)
            if per_position:
                for item, row, col in zip(text_val, row_val, col_val):
                    win.messages.append({"text": str(item), "row": row, "col": col, "color": color, "box": box})
                self.log(f"  [{inst.line_num}] disp_message: 窗口 #{win.handle} 在 {len(text_val)} 个位置分别显示文字")
            else:
                win.messages.append({"text": text, "row": row_val, "col": col_val, "color": color, "box": box})
                self.log(f"  [{inst.line_num}] disp_message: 窗口 #{win.handle} 显示文字 '{text}'")

        else:
            raise NotImplementedError(f"算子 '{op}' 本平台尚未实现")

    @staticmethod
    def _make_thumbnail(arr: np.ndarray) -> str:
        """生成变量窗口使用的缩略图 (等比缩放到长边 THUMBNAIL_MAX_SIDE 像素)"""
        if arr.dtype != np.uint8:
            lo, hi = float(arr.min()), float(arr.max())
            arr = ((arr - lo) / (hi - lo) * 255).astype(np.uint8) if hi > lo else np.zeros(arr.shape, dtype=np.uint8)
        scale = THUMBNAIL_MAX_SIDE / max(arr.shape[:2])
        if scale < 1:
            size = (max(1, round(arr.shape[1] * scale)), max(1, round(arr.shape[0] * scale)))
            arr = cv2.resize(arr, size, interpolation=cv2.INTER_AREA)
        return encode_image_base64(arr)

    @staticmethod
    def _unwrap_single(value: Any) -> Any:
        return value[0] if isinstance(value, list) and len(value) == 1 and not isinstance(value[0], list) else value

    def _pin_display_object(self, overlay: List[str], name: str, obj: Any) -> None:
        """记录 dev_display 那一刻的对象快照: 同名变量被重新赋值后再次显示, 先前显示的内容仍留在叠加层里 (与 HALCON 一致)"""
        if any(self._display_snapshots.get(key) is obj for key in overlay):
            return
        key = f"{name}#{len(self._display_snapshots) + 1}"
        self._display_snapshots[key] = obj
        overlay.append(key)

    def _list_control_vars(self) -> List[Dict[str, Any]]:
        """枚举控制变量 (按出现顺序), 值按 HDevelop 变量窗口的风格格式化; 以下划线开头的内部变量不显示"""
        out = []
        for name, value in self.control_vars.items():
            if name.startswith("_"):
                continue
            value = _to_plain(value)
            entry = {"name": name, "value": format_control_value(value), "type": _control_type(value)}
            if isinstance(value, list):
                entry["length"] = len(value)
            out.append(entry)
        return out

    def _list_iconic_vars(self) -> List[Dict[str, Any]]:
        """枚举当前所有的 Iconic 图像/几何变量信息"""
        out = []
        for k, v in self.iconic_vars.items():
            if isinstance(v, np.ndarray):
                out.append({
                    "name": k,
                    "type": "Image",
                    "shape": list(v.shape),
                    "dtype": str(v.dtype),
                    "thumbnail": self._make_thumbnail(v)
                })
            elif isinstance(v, Region):
                out.append({
                    "name": k,
                    "type": "Region",
                    "object_count": v.count,
                    "is_connected": v.is_connected,
                    "area": int(np.count_nonzero(v.mask)),
                    "shape": list(v.mask.shape),
                    "thumbnail": self._make_thumbnail(v.mask)
                })
            elif isinstance(v, list) and v and isinstance(v[0], XLDContour):
                out.append({
                    "name": k,
                    "type": "XLD",
                    "contour_count": len(v)
                })
        return out

    def _build_visualization_payload(self) -> Dict[str, Any]:
        """为 Web 端 Canvas Viewport 打包当前渲染数据"""
        payload = (self._build_layered_visualization_payload() if self.explicit_display_used
                   else self._build_single_target_visualization_payload())
        payload["ocr"] = self.ocr_result
        return payload

    def _composite_window(self, win: _WindowState) -> Dict[str, Any]:
        """将单个图形窗口当前的叠加状态 (底图 + Region 掩膜 + XLD 轮廓) 合成为可渲染的画面数据"""
        res: Dict[str, Any] = {
            "preview_base64": None,
            "mask_base64": None,
            "contours": [],
            "objects": []
        }

        base_img = self.iconic_vars.get(win.image_name) if win.image_name else None
        if base_img is None:
            for v in self.iconic_vars.values():
                if isinstance(v, np.ndarray):
                    base_img = v
                    break
        if base_img is not None:
            res["preview_base64"] = encode_image_base64(_draw_messages(base_img, win.messages))

        merged_mask = None
        all_objects: List[Dict[str, Any]] = []
        for name in win.region_names:
            reg = self._display_snapshots.get(name)
            if not isinstance(reg, Region) or base_img is None:
                continue
            color_mask = create_colored_label_mask(reg, base_img.shape[:2], alpha=HDEV_REGION_ALPHA)
            if merged_mask is None:
                merged_mask = color_mask
            else:
                covered = np.any(color_mask > 0, axis=-1)
                merged_mask[covered] = color_mask[covered]
            all_objects.extend([
                {
                    "id": obj.id,
                    "area": obj.area,
                    "circularity": obj.circularity,
                    "aspect_ratio": round(obj.aspect_ratio, 3),
                    "rectangularity": round(obj.rectangularity, 3),
                    "centroid": [round(x, 1) for x in obj.centroid],
                    "bbox": list(obj.bbox)
                }
                for obj in reg.objects
            ])
        if merged_mask is not None:
            res["mask_base64"] = encode_image_base64(merged_mask)
            res["objects"] = all_objects

        all_contours: List[List[Tuple[float, float]]] = []
        for name in win.xld_names:
            xld_list = self._display_snapshots.get(name)
            if isinstance(xld_list, list):
                all_contours.extend([[[p[1], p[0]] for p in c.points] for c in xld_list if isinstance(c, XLDContour)])
        res["contours"] = all_contours

        return res

    def _build_layered_visualization_payload(self) -> Dict[str, Any]:
        """
        叠加模式 (脚本中显式调用过 dev_display/disp_obj/dev_open_window 时启用):
        模拟 HALCON 多图形窗口语义 —— 每个窗口独立合成自己的底图 + Region + XLD 叠加画面,
        接口主字段始终反映当前活跃窗口, 若脚本打开过多个仍有内容的窗口, 则额外在
        `windows` 数组中列出每个窗口各自的画面数据, 供前端渲染窗口切换标签页。
        """
        res = self._composite_window(self._cur_win())
        res["original_base64"] = encode_image_base64(self.original_snapshot) if self.original_snapshot is not None else None

        used_windows = [w for w in self.windows.values() if not w.is_empty()]
        if len(used_windows) > 1:
            res["windows"] = [
                {
                    "handle": w.handle,
                    "label": f"窗口 #{w.handle}",
                    "active": w.handle == self.active_window,
                    **self._composite_window(w)
                }
                for w in sorted(used_windows, key=lambda w: w.handle)
            ]
        else:
            res["windows"] = []

        return res

    def _build_single_target_visualization_payload(self) -> Dict[str, Any]:
        """单目标覆盖模式 (脚本未显式调用 dev_display 时的默认兼容行为): 仅渲染最近一次产出的对象"""
        # 寻找底图
        base_img = None
        for v in self.iconic_vars.values():
            if isinstance(v, np.ndarray):
                base_img = v
                break

        res: Dict[str, Any] = {
            "preview_base64": None,
            "original_base64": None,
            "mask_base64": None,
            "contours": [],
            "objects": []
        }

        messages = self._cur_win().messages
        if base_img is not None:
            res["preview_base64"] = encode_image_base64(_draw_messages(base_img, messages))

        if self.original_snapshot is not None:
            res["original_base64"] = encode_image_base64(self.original_snapshot)

        # 检查当前目标
        target = self.iconic_vars.get(self.display_target) if self.display_target else None

        if isinstance(target, np.ndarray):
            res["preview_base64"] = encode_image_base64(_draw_messages(target, messages))
        elif isinstance(target, Region):
            if base_img is not None:
                color_mask = create_colored_label_mask(target, base_img.shape[:2], alpha=HDEV_REGION_ALPHA)
                res["mask_base64"] = encode_image_base64(color_mask)
            res["objects"] = [
                {
                    "id": obj.id,
                    "area": obj.area,
                    "circularity": obj.circularity,
                    "aspect_ratio": round(obj.aspect_ratio, 3),
                    "rectangularity": round(obj.rectangularity, 3),
                    "centroid": [round(x, 1) for x in obj.centroid],
                    "bbox": list(obj.bbox)
                }
                for obj in target.objects
            ]
        elif isinstance(target, list) and target and isinstance(target[0], XLDContour):
            res["contours"] = [[[p[1], p[0]] for p in c.points] for c in target]

        res["windows"] = []
        return res


# ----------------------------------------------------------------------
# 4. HDevTranspiler: HDevelop <-> Pipeline 步骤双向转译器
# ----------------------------------------------------------------------
class HDevTranspiler:
    """双向转译器"""

    @classmethod
    def hdev_to_pipeline(cls, hdev_script: str) -> List[Dict[str, Any]]:
        """将 HDevelop 脚本转译为 NaviVision Pipeline 步骤定义列表"""
        instructions = HDevParser.parse_script(hdev_script)
        steps: List[Dict[str, Any]] = []
        step_idx = 1

        for inst in instructions:
            if inst.op_type != "operator":
                continue
            op = inst.op_name.lower()
            c_in = inst.control_in

            step_def: Optional[Dict[str, Any]] = None

            if op == "read_image":
                step_def = {"id": f"step_{step_idx}", "operator": "read_image", "enabled": True, "params": {}}
            elif op == "rgb1_to_gray":
                step_def = {"id": f"step_{step_idx}", "operator": "rgb1_to_gray", "enabled": True, "params": {}}
            elif op == "threshold":
                min_g = int(c_in[0]) if len(c_in) > 0 else 128
                max_g = int(c_in[1]) if len(c_in) > 1 else 255
                step_def = {"id": f"step_{step_idx}", "operator": "threshold", "enabled": True, "params": {"min_gray": min_g, "max_gray": max_g}}
            elif op in ("auto_threshold", "binary_threshold"):
                step_def = {"id": f"step_{step_idx}", "operator": "auto_threshold", "enabled": True, "params": {"invert": False}}
            elif op == "connection":
                step_def = {"id": f"step_{step_idx}", "operator": "connection", "enabled": True, "params": {"connectivity": 8}}
            elif op == "select_shape":
                feature = str(c_in[0]) if len(c_in) > 0 else "area"
                min_v = float(c_in[2]) if len(c_in) > 2 else 0.0
                max_v = float(c_in[3]) if len(c_in) > 3 else 999999.0
                params: Dict[str, Any] = {}
                if "area" in feature:
                    params["min_area"] = int(min_v)
                    params["max_area"] = int(max_v)
                elif "circularity" in feature:
                    params["min_circularity"] = float(min_v)
                    params["max_circularity"] = float(max_v)
                elif "rectangularity" in feature:
                    params["min_rectangularity"] = float(min_v)
                    params["max_rectangularity"] = float(max_v)
                step_def = {"id": f"step_{step_idx}", "operator": "select_shape", "enabled": True, "params": params}
            elif op in ("opening_circle", "closing_circle", "dilation_circle", "erosion_circle"):
                rad = int(c_in[0]) if c_in else 3
                op_type = op.split("_")[0]
                step_def = {"id": f"step_{step_idx}", "operator": "morphology", "enabled": True, "params": {"op_type": op_type, "kernel_shape": "circle", "kernel_size": rad * 2 + 1}}
            elif op in ("mean_image", "gauss_filter", "median_image"):
                ft = "mean" if op == "mean_image" else ("gaussian" if op == "gauss_filter" else "median")
                sz = int(c_in[0]) if c_in else 5
                step_def = {"id": f"step_{step_idx}", "operator": "filter", "enabled": True, "params": {"filter_type": ft, "kernel_size": sz}}
            elif op == "edges_subpix":
                low_t = float(c_in[2]) if len(c_in) > 2 else 30.0
                high_t = float(c_in[3]) if len(c_in) > 3 else 90.0
                step_def = {"id": f"step_{step_idx}", "operator": "edges_subpix", "enabled": True, "params": {"low_threshold": low_t, "high_threshold": high_t}}
            elif op in ("measure_region", "smallest_rectangle2", "smallest_circle"):
                step_def = {"id": f"step_{step_idx}", "operator": "measure_region", "enabled": True, "params": {}}
            elif op == "rgb_to_hsv":
                step_def = {"id": f"step_{step_idx}", "operator": "rgb_to_hsv", "enabled": True, "params": {}}

            if step_def:
                steps.append(step_def)
                step_idx += 1

        return steps

    @classmethod
    def pipeline_to_hdev(cls, steps: List[Dict[str, Any]], format_as_xml: bool = False) -> str:
        """将流水线步骤逆向导出为标准 HDevelop 脚本"""
        lines: List[str] = [
            "* ==========================================================",
            "* NaviVision Studio (OpenDevelop) - Auto Generated HDevelop Script",
            f"* Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "* ==========================================================",
            ""
        ]

        current_img = "Image"
        current_reg = "Region"

        for idx, step in enumerate(steps, start=1):
            if not step.get("enabled", True):
                continue
            op = step.get("operator", "")
            params = step.get("params", {})

            if op == "read_image":
                lines.append(f"* Step {idx}: 载入测试底图")
                lines.append(f"read_image ({current_img}, 'pills')")
            elif op == "rgb1_to_gray":
                lines.append(f"* Step {idx}: 灰度化转换")
                lines.append(f"rgb1_to_gray ({current_img}, GrayImage)")
                current_img = "GrayImage"
            elif op == "threshold":
                min_g = params.get("min_gray", 128)
                max_g = params.get("max_gray", 255)
                lines.append(f"* Step {idx}: 双阈值二值化分割")
                lines.append(f"threshold ({current_img}, {current_reg}, {min_g}, {max_g})")
            elif op == "auto_threshold":
                lines.append(f"* Step {idx}: Otsu 自适应大津阈值分割")
                lines.append(f"binary_threshold ({current_img}, {current_reg}, 'max_separability', 'dark', UsedThreshold)")
            elif op == "connection":
                lines.append(f"* Step {idx}: 打散连通域")
                lines.append(f"connection ({current_reg}, ConnectedRegions)")
                current_reg = "ConnectedRegions"
            elif op == "select_shape":
                lines.append(f"* Step {idx}: 形态与面积筛选")
                if "min_area" in params or "max_area" in params:
                    min_a = params.get("min_area", 0)
                    max_a = params.get("max_area", 999999)
                    lines.append(f"select_shape ({current_reg}, SelectedRegions, 'area', 'and', {min_a}, {max_a})")
                    current_reg = "SelectedRegions"
                if "min_circularity" in params:
                    min_c = params.get("min_circularity", 0.0)
                    max_c = params.get("max_circularity", 1.0)
                    lines.append(f"select_shape ({current_reg}, SelectedRegions, 'circularity', 'and', {min_c}, {max_c})")
                    current_reg = "SelectedRegions"
            elif op == "morphology":
                op_t = params.get("op_type", "opening")
                k_size = params.get("kernel_size", 5)
                rad = max(1, (k_size - 1) // 2)
                lines.append(f"* Step {idx}: 形态学处理 ({op_t})")
                lines.append(f"{op_t}_circle ({current_reg}, MorphRegion, {rad})")
                current_reg = "MorphRegion"
            elif op == "filter":
                ft = params.get("filter_type", "gaussian")
                sz = params.get("kernel_size", 5)
                lines.append(f"* Step {idx}: 图像平滑滤波")
                if ft == "mean":
                    lines.append(f"mean_image ({current_img}, FilteredImage, {sz}, {sz})")
                elif ft == "median":
                    lines.append(f"median_image ({current_img}, FilteredImage, 'circle', {(sz-1)//2}, 'mirrored')")
                else:
                    lines.append(f"gauss_filter ({current_img}, FilteredImage, {sz})")
                current_img = "FilteredImage"
            elif op == "edges_subpix":
                low = params.get("low_threshold", 30.0)
                high = params.get("high_threshold", 90.0)
                lines.append(f"* Step {idx}: 真·亚像素边缘轮廓提取")
                lines.append(f"edges_subpix ({current_img}, Edges, 'canny', 1.0, {low}, {high})")
            elif op == "measure_region":
                lines.append(f"* Step {idx}: 工业几何度量 (旋转矩形与惯性主轴)")
                lines.append(f"smallest_rectangle2 ({current_reg}, Row, Column, Phi, Length1, Length2)")
                lines.append(f"count_obj ({current_reg}, NumberOfObjects)")
            lines.append("")

        lines.append(f"* 最终结果投射到视口")
        lines.append(f"dev_display ({current_reg})")

        plain_text = "\n".join(lines)
        if not format_as_xml:
            return plain_text

        # 封装为标准 .hdev XML 格式
        xml_lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            '<hdevelop version="1.4">',
            '  <procedure name="main">',
            '    <interface/>',
            '    <body>'
        ]
        for l in lines:
            xml_lines.append(f'      <line>{l}</line>')
        xml_lines.extend([
            '    </body>',
            '  </procedure>',
            '</hdevelop>'
        ])
        return "\n".join(xml_lines)
