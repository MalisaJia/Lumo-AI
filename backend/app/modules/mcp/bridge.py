"""MCP 工具桥接：将 MCP 工具定义转换为 Lumo Tool 并注册到 ToolRegistry。"""

import logging
from typing import Any

from app.modules.tools.registry import Tool, get_registry

logger = logging.getLogger(__name__)


def mcp_tool_to_openai_params(mcp_tool: dict[str, Any]) -> dict[str, Any]:
    """将 MCP 的 JSON Schema 转换为 OpenAI function parameters 格式。"""
    schema = mcp_tool.get("inputSchema") or mcp_tool.get("input_schema")
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    return schema


def _make_handler(server_name: str, tool_name: str):
    """创建绑定服务器和原始工具名的异步处理器，避免循环闭包串值。"""

    async def handler(ctx: Any, arguments: dict[str, Any]) -> str:
        del ctx
        from app.modules.mcp.client import get_mcp_manager

        try:
            return await get_mcp_manager().call_tool(
                server_name, tool_name, arguments
            )
        except Exception as exc:
            logger.warning(
                "MCP 工具执行失败：%s/%s：%s",
                server_name,
                tool_name,
                exc,
                exc_info=True,
            )
            return f"MCP 工具 {tool_name} 执行失败：{exc}"

    return handler


def register_mcp_tools(server_name: str, tools: list[dict[str, Any]]) -> int:
    """将一个 MCP 服务器的工具注册到 Lumo ToolRegistry。"""
    registry = get_registry()
    count = 0

    for tool_def in tools:
        original_name = tool_def.get("name")
        if not isinstance(original_name, str) or not original_name:
            logger.warning("跳过缺少有效名称的 MCP 工具：%r", tool_def)
            continue

        tool_name = f"mcp_{server_name}_{original_name}"
        description = tool_def.get("description") or f"MCP tool: {original_name}"
        registry.register(
            Tool(
                name=tool_name,
                description=f"[MCP:{server_name}] {description}",
                parameters=mcp_tool_to_openai_params(tool_def),
                handler=_make_handler(server_name, original_name),
                timeout=30.0,
            )
        )
        count += 1
        logger.info("注册 MCP 工具：%s（来自 %s）", tool_name, server_name)

    return count


def unregister_mcp_tools(server_name: str) -> int:
    """取消注册指定 MCP 服务器的所有工具。"""
    registry = get_registry()
    prefix = f"mcp_{server_name}_"
    names = [name for name in registry.names() if name.startswith(prefix)]
    return sum(registry.unregister(name) for name in names)
