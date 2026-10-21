"""
HDevelop 控制表达式求值器 (安全的 AST 解释, 不使用 eval)。

支持的语法与 HALCON 元组语义:
- 数字 / 字符串 / 布尔 / 元组字面量, 变量名, 一元与二元运算, 比较与 and/or/not
- 元组下标 Row[I]、元组长度 |Score|
- 逐元素运算: [1, 2] + 1 -> [2, 3]; 数字与字符串相加时数字被转成字符串
- 内置函数: rad / deg / sqrt / sin / cos / tan / int / real / sum / max / min / abs / round 等
"""

import ast
import math
import operator
import re
from typing import Any, Callable, Dict, List

_MAX_STRING_LENGTH = 100000


class UnsupportedExpression(ValueError):
    """文本不是本求值器支持的表达式 (调用方可据此把它当作普通字符串)"""

_BINARY: Dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.FloorDiv: operator.floordiv,
}

_COMPARE: Dict[type, Callable[[Any, Any], bool]] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
}


def _format_number(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    return f"{value:.15g}"


def _add(left: Any, right: Any) -> Any:
    if isinstance(left, str) or isinstance(right, str):
        result = (left if isinstance(left, str) else _format_number(left)) + \
                 (right if isinstance(right, str) else _format_number(right))
        if len(result) > _MAX_STRING_LENGTH:
            raise ValueError("字符串过长")
        return result
    return left + right


def _scalar_op(op_type: type, left: Any, right: Any) -> Any:
    if op_type is ast.Add:
        return _add(left, right)
    return _BINARY[op_type](left, right)


def _broadcast(op_type: type, left: Any, right: Any) -> Any:
    left_is_tuple, right_is_tuple = isinstance(left, list), isinstance(right, list)
    if not left_is_tuple and not right_is_tuple:
        return _scalar_op(op_type, left, right)
    if left_is_tuple and right_is_tuple:
        if len(left) != len(right):
            if len(left) == 1:
                left = left * len(right)
            elif len(right) == 1:
                right = right * len(left)
            else:
                raise ValueError(f"元组长度不一致: {len(left)} 与 {len(right)}")
        return [_broadcast(op_type, a, b) for a, b in zip(left, right)]
    if left_is_tuple:
        return [_broadcast(op_type, a, right) for a in left]
    return [_broadcast(op_type, left, b) for b in right]


def _map_tuple(func: Callable[[Any], Any]) -> Callable[[Any], Any]:
    def wrapper(value: Any) -> Any:
        return [func(v) for v in value] if isinstance(value, list) else func(value)
    return wrapper


def _tuple_length(value: Any) -> int:
    return len(value) if isinstance(value, (list, str)) else 1


def _aggregate(func: Callable[[List[Any]], Any]) -> Callable[..., Any]:
    def wrapper(*args: Any) -> Any:
        items = args[0] if len(args) == 1 and isinstance(args[0], list) else list(args)
        return func(items)
    return wrapper


FUNCTIONS: Dict[str, Callable[..., Any]] = {
    "rad": _map_tuple(math.radians),
    "deg": _map_tuple(math.degrees),
    "sqrt": _map_tuple(math.sqrt),
    "sin": _map_tuple(math.sin),
    "cos": _map_tuple(math.cos),
    "tan": _map_tuple(math.tan),
    "exp": _map_tuple(math.exp),
    "log": _map_tuple(math.log),
    "int": _map_tuple(lambda v: int(float(v))),
    "real": _map_tuple(float),
    "abs": _map_tuple(abs),
    "round": _map_tuple(lambda v: int(round(v))),
    "floor": _map_tuple(math.floor),
    "ceil": _map_tuple(math.ceil),
    "tuple_length": _tuple_length,
    "sum": _aggregate(sum),
    "max": _aggregate(max),
    "min": _aggregate(min),
    "mean": _aggregate(lambda items: sum(items) / len(items)),
    "sort": lambda value: sorted(value),
    "str": _map_tuple(lambda v: v if isinstance(v, str) else _format_number(v)),
}

CONSTANTS: Dict[str, Any] = {"true": True, "false": False, "pi": math.pi}


_ESCAPES = {"\\": "\\", "'": "'", '"': '"', "n": "\n", "t": "\t"}


def unescape_string(text: str) -> str:
    """HALCON 字符串转义：两个反斜杠得一个反斜杠，反斜杠加单引号或双引号得引号本身，反斜杠加 n 为换行，反斜杠加 t 为制表符；其它反斜杠原样保留（如 Windows 路径）"""
    return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(0)), text, flags=re.S)


def _normalise_source(expr: str) -> str:
    """
    把 HALCON 的写法整理成可交给 Python 解析器的源码: 字符串字面量按 HALCON 的转义规则解码后重新输出
    (这样 Windows 路径里的单个反斜杠不会被当成非法的 Python 转义), 并把元组长度 |x| 转成 tuple_length(x)。
    """
    out: List[str] = []
    open_pipe = False
    i, n = 0, len(expr)
    while i < n:
        ch = expr[i]
        if ch in ("'", '"'):
            j = i + 1
            while j < n and expr[j] != ch:
                j += 2 if expr[j] == "\\" else 1
            if j >= n:
                raise UnsupportedExpression("字符串没有结束引号")
            out.append(repr(unescape_string(expr[i + 1:j])))
            i = j + 1
        elif ch == "|":
            out.append(")" if open_pipe else "tuple_length(")
            open_pipe = not open_pipe
            i += 1
        else:
            out.append(ch)
            i += 1
    if open_pipe:
        raise UnsupportedExpression("表达式中的 | 没有成对出现")
    return "".join(out)


class _Evaluator:
    def __init__(self, names: Dict[str, Any]):
        self.names = names

    def visit(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return self.visit(node.body)
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float, str, bool)):
                return node.value
            raise UnsupportedExpression(f"不支持的常量: {node.value!r}")
        if isinstance(node, ast.Name):
            if node.id in self.names:
                return self.names[node.id]
            if node.id in CONSTANTS:
                return CONSTANTS[node.id]
            raise NameError(node.id)
        if isinstance(node, (ast.List, ast.Tuple)):
            items: List[Any] = []
            for element in node.elts:
                value = self.visit(element)
                items.extend(value if isinstance(value, list) else [value])
            return items
        if isinstance(node, ast.UnaryOp):
            operand = self.visit(node.operand)
            if isinstance(node.op, ast.USub):
                return _map_tuple(operator.neg)(operand)
            if isinstance(node.op, ast.UAdd):
                return operand
            if isinstance(node.op, ast.Not):
                return not operand
            raise UnsupportedExpression("不支持的一元运算")
        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in _BINARY:
                raise UnsupportedExpression("不支持的二元运算")
            return _broadcast(op_type, self.visit(node.left), self.visit(node.right))
        if isinstance(node, ast.BoolOp):
            values = [self.visit(v) for v in node.values]
            return all(values) if isinstance(node.op, ast.And) else any(values)
        if isinstance(node, ast.Compare):
            left = self.visit(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = self.visit(comparator)
                if type(op) not in _COMPARE:
                    raise UnsupportedExpression("不支持的比较运算")
                if not _COMPARE[type(op)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.Subscript):
            target = self.visit(node.value)
            index = self.visit(node.slice)
            if not isinstance(target, list):
                raise UnsupportedExpression("只有元组支持下标访问")
            if isinstance(index, list):
                return [target[int(i)] for i in index]
            return target[int(index)]
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in FUNCTIONS or node.keywords:
                raise UnsupportedExpression("不支持的函数调用")
            return FUNCTIONS[node.func.id](*[self.visit(arg) for arg in node.args])
        raise UnsupportedExpression(f"不支持的表达式: {type(node).__name__}")


def evaluate(expr: str, names: Dict[str, Any]) -> Any:
    """求值一条 HDevelop 控制表达式; 变量未定义时抛出 NameError, 语法错误时抛出 SyntaxError"""
    tree = ast.parse(_normalise_source(expr.strip()), mode="eval")
    return _Evaluator(names).visit(tree)
