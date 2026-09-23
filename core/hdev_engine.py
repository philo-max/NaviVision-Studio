"""
NaviVision Studio (OpenDevelop) - HDevelop DSL Engine
自研 HDevelop 4GL 语言原生解析器、解释执行沙箱与双向转译器:
1. HDevParser: 解析 .hdev XML 与纯文本脚本，支持四槽位语法与标准算子签名
2. HDevInterpreter: 纯 Python 隔离执行，维护 Iconic 与 Control 变量表，映射执行核心算子
3. HDevTranspiler: HDevelop 脚本与 NaviVision Pipeline 步骤 JSON 双向无损转译
"""

import os
import re
import xml.etree.ElementTree as ET
import time
import math
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
import numpy as np

from core.types import Region, RegionObject, XLDContour
from core import operators as ops
from core.pipeline import encode_image_base64, create_colored_label_mask


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
    "mean_image": (["Image"], ["ImageMean"], ["MaskWidth", "MaskHeight"], []),
    "gauss_filter": (["Image"], ["ImageGauss"], ["Size"], []),
    "median_image": (["Image"], ["ImageMedian"], ["MaskType", "Radius", "Margin"], []),
    "edges_subpix": (["Image"], ["Edges"], ["Filter", "Alpha", "Low", "High"], []),
    "measure_region": (["Regions"], [], [], ["Metrics"]),
    "smallest_rectangle2": (["Regions"], [], [], ["Row", "Column", "Phi", "Length1", "Length2"]),
    "smallest_circle": (["Regions"], [], [], ["Row", "Column", "Radius"]),
    "area_center": (["Regions"], [], [], ["Area", "Row", "Column"]),
    "count_obj": (["Objects"], [], [], ["Number"]),
    "dev_display": (["Object"], [], [], []),
    "disp_obj": (["Object"], [], ["WindowHandle"], []),
    "reduce_domain": (["Image", "Region"], ["ImageReduced"], [], []),
    "rgb_to_hsv": (["Image"], ["HSVImage"], [], []),
    "hsv_threshold": (["Image"], ["Region"], ["HMin", "HMax", "SMin", "SMax", "VMin", "VMax"], []),
    "find_shape_model": (["Image"], [], ["TemplateID", "AngleStart", "AngleExtent", "MinScore", "NumMatches"], ["Row", "Column", "Angle", "Score"]),
    "gen_contour_polygon_xld": (["Contour"], ["Polygons"], ["Type", "MaxDistance"], []),
    "read_barcode": (["Image"], [], [], ["DecodedStrings"]),
    "read_text": (["Image"], [], ["Lang"], ["RecognizedText"]),
    "calibrate": (["Image"], [], ["PatternWidth", "PatternHeight", "SquareSize"], ["PixelsPerUnit"]),
    "gen_cross_contour_xld": ([], ["Crosses"], ["Row", "Col", "Length", "Phi"], []),
    "hom_vector_to_proj_hom_mat2d": ([], [], ["Px", "Py", "Pw", "Qx", "Qy", "Qw", "Method"], ["HomMat2D"]),
    "vector_to_proj_hom_mat2d": ([], [], ["Px", "Py", "Qx", "Qy", "Method"], ["HomMat2D"]),
    "projective_trans_image": (["Image"], ["Image_rectified"], ["HomMat2D", "Interpolation", "AdaptImageSize", "TransformDomain"], []),
    "projective_trans_image_size": (["Image"], ["Image_rectified"], ["HomMat2D", "Interpolation", "Width", "Height", "TransformDomain"], []),
    "dev_update_off": ([], [], [], []),
    "dev_update_on": ([], [], [], []),
    "dev_close_window": ([], [], [], []),
    "dev_clear_window": ([], [], [], []),
    "dev_open_window": ([], [], ["Row", "Column", "Width", "Height", "Background"], ["WindowHandle"]),
    "dev_open_window_fit_image": (["Image"], [], ["Row", "Column", "WidthLimit", "HeightLimit"], ["WindowHandle"]),
    "dev_set_color": ([], [], ["ColorName"], []),
    "dev_set_line_width": ([], [], ["LineWidth"], []),
    "dev_set_draw": ([], [], ["DrawMode"], []),
    "distance_pp": ([], [], ["Row1", "Col1", "Row2", "Col2"], ["Distance"]),
    "distance_pl": ([], [], ["Row", "Col", "RowBegin", "ColBegin", "RowEnd", "ColEnd"], ["Distance"]),
    "angle_ll": ([], [], ["RowA1", "ColA1", "RowA2", "ColA2", "RowB1", "ColB1", "RowB2", "ColB2"], ["Angle"]),
    "fit_line_contour_xld": (["Contours"], [], ["Algorithm", "MaxNumPoints", "MaxDistance", "ClippingEndPoints"], ["RowBegin", "ColBegin", "RowEnd", "ColEnd", "Nr", "Nc", "Dist"]),
    "fit_circle_contour_xld": (["Contours"], [], ["Algorithm", "MaxNumPoints", "MaxDistance", "ClippingEndPoints"], ["Row", "Column", "Radius", "StartPhi", "EndPhi", "PointOrder"])
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

        # 普通文本解析
        for idx, l in enumerate(script_content.splitlines(), start=1):
            lines.append((idx, l.strip()))
        return lines

    @classmethod
    def _parse_value(cls, val_str: str) -> Any:
        """解析控制表达式的单个常量或变量字面量"""
        s = val_str.strip()
        if not s:
            return ""
        # 字符串常量: 'foo' 或 "foo"
        if (s.startswith("'") and s.endswith("'")) or (s.startswith('"') and s.endswith('"')):
            return s[1:-1]
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
        if ":" in args_str:
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
        # 脚本执行前的原始底图快照 (用于前后对比视图), 首次载入后不再变更
        self.original_snapshot: Optional[np.ndarray] = None
        # HALCON dev_display 叠加语义模拟: 显示图像会重绘整个画布并清空叠加层,
        # 而 Region/XLD 的显示则在当前画布上叠加绘制, 直到下次显示新图像或 dev_clear_window
        self.display_image_name: Optional[str] = None
        self.display_region_names: List[str] = []
        self.display_xld_names: List[str] = []
        # 脚本中是否显式调用过 dev_display/disp_obj (决定渲染走叠加模式还是单目标覆盖模式)
        self.explicit_display_used: bool = False
        # 默认底图注入
        if base_image is not None:
            self.iconic_vars["Image"] = base_image
            self.display_target = "Image"
            self.display_image_name = "Image"
            self.original_snapshot = base_image.copy()

    def log(self, msg: str):
        self.stdout.append(str(msg))

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
            # 仅允许安全数学运算
            allowed_names = {k: v for k, v in self.control_vars.items() if isinstance(v, (int, float, list, str))}
            allowed_names.update({"max": max, "min": min, "abs": abs, "round": round})
            return eval(s, {"__builtins__": None}, allowed_names)
        except Exception:
            return s

    def execute_script(self, script_content: str, timeout_sec: float = 3.0) -> Dict[str, Any]:
        """执行完整 HDevelop 脚本"""
        t0 = time.perf_counter()
        instructions = HDevParser.parse_script(script_content)
        
        self.log(f"[*] HDevelop 解释器启动: 共载入 {len(instructions)} 条指令")
        
        pc = 0
        total_inst = len(instructions)
        start_time = time.time()

        try:
            while pc < total_inst:
                # 超时熔断保护
                if time.time() - start_time > timeout_sec:
                    raise TimeoutError(f"HDevelop 脚本执行超时 (强制熔断阈值: {timeout_sec:.1f}s)")

                inst = instructions[pc]
                
                # 处理控制流
                if inst.op_type == "assign":
                    val = self._eval_expr(inst.assign_expr)
                    self.control_vars[inst.assign_var] = val
                    self.log(f"  [{inst.line_num}] {inst.assign_var} := {val}")
                    pc += 1

                elif inst.op_type == "operator":
                    self._execute_operator(inst)
                    pc += 1

                elif inst.op_type in ("for", "while", "if"):
                    # 基础跳步处理 (简单块顺序推进)
                    pc += 1
                else:
                    pc += 1

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
                "display_target": self.display_target,
                **render_res
            }

        except Exception as e:
            duration_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            err_msg = f"第 {inst.line_num} 行执行失败: {e}" if pc < total_inst else str(e)
            self.log(f"[!] {err_msg}")
            return {
                "success": False,
                "error": err_msg,
                "duration_ms": duration_ms,
                "stdout": "\n".join(self.stdout),
                "iconic_vars": self._list_iconic_vars(),
                "control_vars": {k: str(v) for k, v in self.control_vars.items()}
            }

    def _execute_operator(self, inst: HDevInstruction):
        """执行单个算子调用"""
        op = inst.op_name.lower()
        i_in = inst.iconic_in
        i_out = inst.iconic_out
        c_in = [self._eval_expr(x) for x in inst.control_in]
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
            if self.original_snapshot is None:
                self.original_snapshot = img.copy()
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
            self.iconic_vars[out_name] = reg
            self.display_target = out_name
            self.log(f"  [{inst.line_num}] threshold: 分割范围 [{min_gray}, {max_gray}], 生成区域 '{out_name}'")

        # 4. auto_threshold (Image, Regions, Sigma)
        elif op in ("auto_threshold", "binary_threshold"):
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
            metrics = ops.measure_region(src_reg)

            if op == "smallest_rectangle2" and len(c_out) >= 5:
                # Row, Column, Phi, Length1, Length2
                rows, cols, phis, l1s, l2s = [], [], [], [], []
                for item in metrics.get("items", []):
                    obb = item.get("obb", {})
                    cols.append(obb.get("center_x", 0.0))
                    rows.append(obb.get("center_y", 0.0))
                    phis.append(obb.get("angle_rad", 0.0))
                    l1s.append(obb.get("half_width", 0.0))
                    l2s.append(obb.get("half_height", 0.0))
                self.control_vars[c_out[0]] = rows
                self.control_vars[c_out[1]] = cols
                self.control_vars[c_out[2]] = phis
                self.control_vars[c_out[3]] = l1s
                self.control_vars[c_out[4]] = l2s
                self.log(f"  [{inst.line_num}] smallest_rectangle2: 输出旋转矩形特征到变量 {c_out}")

            elif op == "smallest_circle" and len(c_out) >= 3:
                rows, cols, radii = [], [], []
                for item in metrics.get("items", []):
                    sc = item.get("smallest_circle", {})
                    cols.append(sc.get("center_x", 0.0))
                    rows.append(sc.get("center_y", 0.0))
                    radii.append(sc.get("radius", 0.0))
                self.control_vars[c_out[0]] = rows
                self.control_vars[c_out[1]] = cols
                self.control_vars[c_out[2]] = radii
                self.log(f"  [{inst.line_num}] smallest_circle: 输出最小外接圆特征到变量 {c_out}")

            elif op == "area_center" and len(c_out) >= 3:
                areas = [obj.area for obj in src_reg.objects]
                rows = [obj.centroid[0] for obj in src_reg.objects]
                cols = [obj.centroid[1] for obj in src_reg.objects]
                self.control_vars[c_out[0]] = areas
                self.control_vars[c_out[1]] = rows
                self.control_vars[c_out[2]] = cols
                self.log(f"  [{inst.line_num}] area_center: 输出面积与中心坐标到变量 {c_out}")
            else:
                self.control_vars["Metrics"] = metrics
                self.log(f"  [{inst.line_num}] measure_region: 计算完成并存入 Metrics")

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
                if isinstance(obj, np.ndarray):
                    # 显示新图像 = 整个画布被重绘, 之前叠加的 Region/XLD 不再可见
                    self.display_image_name = in_name
                    self.display_region_names = []
                    self.display_xld_names = []
                    self.log(f"  [{inst.line_num}] {op}: 显示图像 '{in_name}' (画布重绘, 叠加层已清空)")
                elif isinstance(obj, Region):
                    if in_name not in self.display_region_names:
                        self.display_region_names.append(in_name)
                    self.log(f"  [{inst.line_num}] {op}: 叠加显示 Region '{in_name}' (当前叠加层: {self.display_region_names})")
                elif isinstance(obj, list) and obj and isinstance(obj[0], XLDContour):
                    if in_name not in self.display_xld_names:
                        self.display_xld_names.append(in_name)
                    self.log(f"  [{inst.line_num}] {op}: 叠加显示 XLD 轮廓 '{in_name}' (当前叠加层: {self.display_xld_names})")

        # 12b. dev_clear_window: 清空当前图形窗口的所有叠加层
        elif op == "dev_clear_window":
            self.display_image_name = None
            self.display_region_names = []
            self.display_xld_names = []
            self.log(f"  [{inst.line_num}] dev_clear_window: 已清空画布叠加层")

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
        elif op.startswith("dev_") or op.startswith("set_"):
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

        else:
            self.log(f"  [{inst.line_num}] 未实现或通用算子 '{op}', 跳过执行")

    def _list_iconic_vars(self) -> List[Dict[str, Any]]:
        """枚举当前所有的 Iconic 图像/几何变量信息"""
        out = []
        for k, v in self.iconic_vars.items():
            if isinstance(v, np.ndarray):
                out.append({
                    "name": k,
                    "type": "Image",
                    "shape": list(v.shape),
                    "dtype": str(v.dtype)
                })
            elif isinstance(v, Region):
                out.append({
                    "name": k,
                    "type": "Region",
                    "object_count": len(v.objects),
                    "is_connected": v.is_connected
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
        if self.explicit_display_used:
            return self._build_layered_visualization_payload()
        return self._build_single_target_visualization_payload()

    def _build_layered_visualization_payload(self) -> Dict[str, Any]:
        """
        叠加模式 (脚本中显式调用过 dev_display/disp_obj 时启用):
        模拟 HALCON 图形窗口语义 —— 当前显示的图像作为画布底图,
        其后所有仍处于叠加状态的 Region/XLD 依次叠加绘制在其上。
        """
        res: Dict[str, Any] = {
            "preview_base64": None,
            "original_base64": None,
            "mask_base64": None,
            "contours": [],
            "objects": []
        }

        if self.original_snapshot is not None:
            res["original_base64"] = encode_image_base64(self.original_snapshot)

        base_img = self.iconic_vars.get(self.display_image_name) if self.display_image_name else None
        if base_img is None:
            for v in self.iconic_vars.values():
                if isinstance(v, np.ndarray):
                    base_img = v
                    break
        if base_img is not None:
            res["preview_base64"] = encode_image_base64(base_img)

        merged_mask = None
        all_objects: List[Dict[str, Any]] = []
        for name in self.display_region_names:
            reg = self.iconic_vars.get(name)
            if not isinstance(reg, Region) or base_img is None:
                continue
            color_mask = create_colored_label_mask(reg, base_img.shape[:2])
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
                    "centroid": [round(x, 1) for x in obj.centroid],
                    "bbox": list(obj.bbox)
                }
                for obj in reg.objects
            ])
        if merged_mask is not None:
            res["mask_base64"] = encode_image_base64(merged_mask)
            res["objects"] = all_objects

        all_contours: List[List[Tuple[float, float]]] = []
        for name in self.display_xld_names:
            xld_list = self.iconic_vars.get(name)
            if isinstance(xld_list, list):
                all_contours.extend([c.points for c in xld_list if isinstance(c, XLDContour)])
        res["contours"] = all_contours

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

        if base_img is not None:
            res["preview_base64"] = encode_image_base64(base_img)

        if self.original_snapshot is not None:
            res["original_base64"] = encode_image_base64(self.original_snapshot)

        # 检查当前目标
        target = self.iconic_vars.get(self.display_target) if self.display_target else None

        if isinstance(target, np.ndarray):
            res["preview_base64"] = encode_image_base64(target)
        elif isinstance(target, Region):
            if base_img is not None:
                color_mask = create_colored_label_mask(target, base_img.shape[:2])
                res["mask_base64"] = encode_image_base64(color_mask)
            res["objects"] = [
                {
                    "id": obj.id,
                    "area": obj.area,
                    "circularity": obj.circularity,
                    "centroid": [round(x, 1) for x in obj.centroid],
                    "bbox": list(obj.bbox)
                }
                for obj in target.objects
            ]
        elif isinstance(target, list) and target and isinstance(target[0], XLDContour):
            res["contours"] = [c.points for c in target]

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
