"""工具注册框架：Tool 定义、模块级注册表、@tool 装饰器、统一执行入口。

设计要点：
- handler 签名固定为 ``async def handler(ctx: ChatContext, arguments: dict) -> str``；
- ``execute()`` 统一 try/except + asyncio.wait_for(tool.timeout)，任何失败
  （未注册/参数非法/超时/异常）都返回可读中文文本，绝不向管线抛异常；
- ``build_openai_tools()`` 全量清单构建一次并缓存，exclude 仅做运行时过滤。
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# 工具 handler 类型：接收管线上下文与模型给出的参数，返回文本结果
ToolHandler = Callable[[Any, dict[str, Any]], Awaitable[str]]


@dataclass(frozen=True)
class Tool:
    """单个工具的元数据与执行体。"""

    name: str
    description: str
    # OpenAI function calling 的 parameters JSON Schema
    parameters: dict[str, Any]
    handler: ToolHandler
    # 分级超时（秒）：快工具 15 / 联网搜索 30 / 制作 PPT 300
    timeout: float = 15.0


class ToolRegistry:
    """模块级工具注册表（进程内单例，见 get_registry）。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}
        # OpenAI tools 全量清单缓存；注册新工具时失效重建
        self._openai_cache: list[dict[str, Any]] | None = None

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            logger.warning("工具重复注册，后者覆盖前者：%s", tool.name)
        self._tools[tool.name] = tool
        self._openai_cache = None

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def build_openai_tools(
        self, exclude: set[str] | None = None
    ) -> list[dict[str, Any]]:
        """生成 OpenAI tools 字段；全量清单只构建一次，exclude 运行时过滤。"""
        if self._openai_cache is None:
            self._openai_cache = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in self._tools.values()
            ]
        if not exclude:
            return list(self._openai_cache)
        return [
            t for t in self._openai_cache if t["function"]["name"] not in exclude
        ]

    async def execute(self, ctx: Any, name: str, arguments: dict[str, Any]) -> str:
        """执行工具并保证返回字符串；任何异常都转成可读文本，绝不抛出。"""
        tool = self._tools.get(name)
        if tool is None:
            logger.warning("模型请求了未注册的工具：%s", name)
            return f"工具 {name} 不存在，请改用其他工具或直接回答。"
        try:
            result = await asyncio.wait_for(
                tool.handler(ctx, arguments or {}), timeout=tool.timeout
            )
            return str(result)
        except asyncio.TimeoutError:
            logger.warning("工具 %s 执行超时（%.0fs）", name, tool.timeout)
            return f"工具 {name} 执行超时，请基于已有信息直接回答。"
        except Exception as exc:
            logger.warning("工具 %s 执行异常：%s", name, exc, exc_info=True)
            return f"工具 {name} 执行失败：{exc.__class__.__name__}。请基于已有信息直接回答。"


_registry = ToolRegistry()


def get_registry() -> ToolRegistry:
    """进程内单例注册表；工具模块导入时经 @tool 装饰器完成注册。"""
    return _registry


def tool(
    name: str,
    description: str,
    parameters: dict[str, Any],
    timeout: float = 15.0,
) -> Callable[[ToolHandler], ToolHandler]:
    """装饰器：把异步函数注册为工具。

    用法::

        @tool("calculator", "…", {"type": "object", ...}, timeout=15.0)
        async def calculator(ctx, arguments): ...
    """

    def decorator(handler: ToolHandler) -> ToolHandler:
        _registry.register(
            Tool(
                name=name,
                description=description,
                parameters=parameters,
                handler=handler,
                timeout=timeout,
            )
        )
        return handler

    return decorator


def normalize_arguments(arguments: Any) -> str:
    """归一化工具参数为稳定字符串，用于请求内去重缓存键。"""
    try:
        return json.dumps(arguments, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return repr(arguments)
