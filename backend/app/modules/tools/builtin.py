"""内置示例工具：计算器（ast 白名单求值，禁用 eval）与当前时间。"""

import ast
import logging
import operator
from datetime import datetime
from typing import Any

from app.modules.tools.registry import tool

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# calculator：ast 白名单表达式求值
# ---------------------------------------------------------------------------

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

# 幂运算指数绝对值上限，防止 2**999999999 之类的资源耗尽攻击
_MAX_POW_EXPONENT = 10_000
# 中间/最终整数结果的位宽上限（4096 bit ≈ 1234 位十进制）；
# 既用于幂运算前的位宽估算拦截（对任意嵌套深度有效），
# 也用作乘法链等其他放大路径的兑底检查
_MAX_INT_BITS = 4096
# 结果绝对值上限（超出视为异常表达式）
_MAX_RESULT = 1e300


def _check_int_size(value: int | float) -> int | float:
    """兑底：整数结果超过位宽上限即拒绝，防乘法链等放大路径阻塞事件循环。"""
    if isinstance(value, int) and value.bit_length() > _MAX_INT_BITS:
        raise ValueError("计算结果过大")
    return value


def _safe_eval_node(node: ast.AST) -> int | float:
    """递归求值白名单节点；任何不支持的语法一律抛 ValueError。"""
    if isinstance(node, ast.Expression):
        return _safe_eval_node(node.body)
    if isinstance(node, ast.Constant):
        # bool 是 int 的子类，显式排除；字符串/其他常量不允许
        if isinstance(node.value, (int, float)) and not isinstance(
            node.value, bool
        ):
            return node.value
        raise ValueError("仅支持数字与算术运算")
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        left = _safe_eval_node(node.left)
        right = _safe_eval_node(node.right)
        if isinstance(node.op, ast.Pow):
            if (
                isinstance(right, (int, float))
                and abs(right) > _MAX_POW_EXPONENT
            ):
                raise ValueError("指数过大")
            # 执行幂运算**之前**用位宽估算拦截：嵌套幂如 (9**9999)**9999
            # 每层都会在此被拒绝，绝不真正计算大整数幂。
            # abs(left) <= 1 时结果必为 -1/0/1，无需拦截。
            if (
                isinstance(left, int)
                and isinstance(right, int)
                and abs(left) > 1
                and left.bit_length() * abs(right) > _MAX_INT_BITS
            ):
                raise ValueError("计算结果过大")
        return _check_int_size(_ALLOWED_BINOPS[type(node.op)](left, right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _check_int_size(
            _ALLOWED_UNARYOPS[type(node.op)](_safe_eval_node(node.operand))
        )
    raise ValueError("仅支持数字与算术运算（+ - * / // % ** 与括号）")


def safe_calculate(expression: str) -> int | float:
    """安全计算算术表达式；非法输入抛 ValueError。"""
    tree = ast.parse(expression, mode="eval")
    result = _safe_eval_node(tree)
    if not isinstance(result, (int, float)) or abs(result) > _MAX_RESULT:
        raise ValueError("计算结果超出范围")
    return result


def _format_number(value: int | float) -> str:
    """整数去小数点；浮点保留至多 10 位有效数字。"""
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.10g}"
    return str(value)


@tool(
    name="calculator",
    description=(
        "计算数学表达式。支持加减乘除、整除//、取余%、幂**与括号，"
        "例如 \"(1+2)*3/4\" 或 \"2**10\"。仅支持纯算术，不支持变量与函数。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "要计算的数学表达式，例如 \"123*456\"",
            }
        },
        "required": ["expression"],
    },
    timeout=15.0,
)
async def calculator(ctx: Any, arguments: dict[str, Any]) -> str:
    expression = str(arguments.get("expression") or "").strip()
    if not expression:
        return "计算失败：表达式为空。"
    if len(expression) > 500:
        return "计算失败：表达式过长。"
    try:
        result = safe_calculate(expression)
    except ZeroDivisionError:
        return f"计算失败：{expression} 出现除以零。"
    except (ValueError, SyntaxError, TypeError, OverflowError) as exc:
        return f"计算失败：表达式 {expression} 不合法（{exc or '语法错误'}）。"
    return f"{expression} = {_format_number(result)}"


# ---------------------------------------------------------------------------
# current_time：本地日期时间与星期
# ---------------------------------------------------------------------------

_WEEKDAY_NAMES = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]


@tool(
    name="current_time",
    description="获取当前的本地日期、时间与星期。用户询问现在几点、今天日期等问题时调用。",
    parameters={"type": "object", "properties": {}, "required": []},
    timeout=15.0,
)
async def current_time(ctx: Any, arguments: dict[str, Any]) -> str:
    now = datetime.now()
    return (
        f"当前本地时间：{now.strftime('%Y-%m-%d %H:%M:%S')}"
        f"（{_WEEKDAY_NAMES[now.weekday()]}）"
    )
