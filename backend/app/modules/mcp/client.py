"""MCP stdio 客户端与服务器进程生命周期管理。"""

import json
import logging
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import PaginatedRequestParams

logger = logging.getLogger(__name__)


def _as_json(value: Any) -> str:
    """将 MCP/Pydantic 对象转换为可读 JSON。"""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", by_alias=True, exclude_none=True)
    return json.dumps(value, ensure_ascii=False, default=str)


def _format_tool_result(result: Any) -> str:
    """将 MCP CallToolResult 的多种内容块归一化为 Lumo 文本结果。"""
    parts: list[str] = []
    for item in getattr(result, "content", []) or []:
        if getattr(item, "type", None) == "text":
            parts.append(str(item.text))
        else:
            parts.append(_as_json(item))

    structured = getattr(result, "structured_content", None)
    if structured is not None:
        parts.append(_as_json(structured))

    text = "\n".join(part for part in parts if part)
    if not text:
        text = _as_json(result)
    if getattr(result, "is_error", False):
        return f"MCP 工具返回错误：{text}"
    return text


class MCPServerManager:
    """管理 MCP stdio 服务器进程及客户端会话的生命周期。"""

    def __init__(self) -> None:
        self._servers: dict[str, dict[str, Any]] = {}
        self._sessions: dict[str, ClientSession] = {}

    async def start_server(
        self,
        name: str,
        command: str,
        args: list[str],
        env: dict[str, str] | None = None,
    ) -> None:
        """启动一个 MCP 服务器进程、初始化会话并缓存其工具清单。"""
        if not name.strip():
            raise ValueError("MCP 服务器名称不能为空")
        if not command.strip():
            raise ValueError("MCP 服务器启动命令不能为空")
        if name in self._servers:
            await self.stop_server(name)

        stack = AsyncExitStack()
        try:
            parameters = StdioServerParameters(
                command=command,
                args=list(args),
                env=dict(env) if env is not None else None,
            )
            read_stream, write_stream = await stack.enter_async_context(
                stdio_client(parameters)
            )
            session = await stack.enter_async_context(
                ClientSession(read_stream, write_stream)
            )
            await session.initialize()

            self._sessions[name] = session
            self._servers[name] = {
                "command": command,
                "args": list(args),
                "env": dict(env) if env is not None else None,
                "tools": [],
                "exit_stack": stack,
            }
            await self.list_tools(name)
            logger.info("MCP 服务器已启动：%s", name)
        except BaseException:
            self._sessions.pop(name, None)
            self._servers.pop(name, None)
            await stack.aclose()
            raise

    async def stop_server(self, name: str) -> None:
        """关闭会话并停止指定 MCP 服务器进程。"""
        server = self._servers.pop(name, None)
        self._sessions.pop(name, None)
        if server is None:
            return
        await server["exit_stack"].aclose()
        logger.info("MCP 服务器已停止：%s", name)

    async def stop_all(self) -> None:
        """停止所有 MCP 服务器；单个服务器清理失败不影响其余服务器。"""
        for name in reversed(list(self._servers)):
            try:
                await self.stop_server(name)
            except Exception:
                logger.exception("停止 MCP 服务器失败：%s", name)

    async def list_tools(self, server_name: str) -> list[dict[str, Any]]:
        """列出指定服务器的全部工具，并使用 OpenAI 兼容字段名缓存。"""
        session = self._sessions.get(server_name)
        if session is None:
            raise KeyError(f"MCP 服务器未连接：{server_name}")

        tools: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params = PaginatedRequestParams(cursor=cursor) if cursor else None
            result = await session.list_tools(params=params)
            tools.extend(
                tool.model_dump(mode="json", by_alias=True, exclude_none=True)
                for tool in result.tools
            )
            cursor = result.next_cursor
            if not cursor:
                break

        self._servers[server_name]["tools"] = tools
        return [dict(tool) for tool in tools]

    async def call_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any]
    ) -> str:
        """调用指定服务器上的工具，并将 MCP 内容块转换为文本。"""
        session = self._sessions.get(server_name)
        if session is None:
            raise KeyError(f"MCP 服务器未连接：{server_name}")
        result = await session.call_tool(tool_name, arguments=arguments or {})
        return _format_tool_result(result)

    def get_all_tools(self) -> dict[str, list[dict[str, Any]]]:
        """返回当前所有服务器已缓存的工具清单。"""
        return {
            name: [dict(tool) for tool in server["tools"]]
            for name, server in self._servers.items()
        }


_manager = MCPServerManager()


def get_mcp_manager() -> MCPServerManager:
    """返回进程内 MCP 服务器管理器单例。"""
    return _manager
