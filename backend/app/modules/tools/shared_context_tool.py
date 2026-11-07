"""Tools for agents to exchange findings within one parent conversation."""

from typing import Any

from app.modules.agents.shared_context import shared_context
from app.modules.tools.registry import tool


def _context_identity(ctx: Any) -> tuple[str, str, str]:
    extra = getattr(ctx, "extra", None)
    extra = extra if isinstance(extra, dict) else {}
    conversation_id = str(
        extra.get("shared_conversation_id")
        or getattr(ctx, "conversation_id", "")
    ).strip()
    agent_id = str(
        extra.get("shared_agent_id") or getattr(ctx, "conversation_id", "")
    ).strip()
    agent_type = str(extra.get("shared_agent_type") or "coding").strip()
    return conversation_id, agent_id, agent_type


@tool(
    name="publish_context",
    description="发布信息到共享上下文板，供其他 agent 读取",
    parameters={
        "type": "object",
        "properties": {
            "key": {
                "type": "string",
                "description": "信息类别或主题键",
            },
            "content": {
                "type": "string",
                "description": "要共享的发现、结论或输出",
            },
        },
        "required": ["key", "content"],
    },
)
async def publish_context_handler(ctx: Any, arguments: dict[str, Any]) -> str:
    """Publish one entry under the logical parent conversation."""
    conversation_id, agent_id, agent_type = _context_identity(ctx)
    key = str(arguments.get("key", "")).strip()
    content = str(arguments.get("content", "")).strip()
    if not conversation_id:
        return "发布共享上下文失败：缺少会话 ID。"
    if not key or not content:
        return "发布共享上下文失败：key 和 content 不能为空。"
    await shared_context.publish(
        conversation_id, agent_id, agent_type, key, content
    )
    return f"已发布共享上下文：{key}"


@tool(
    name="read_shared_context",
    description="读取其他 agent 发布的共享上下文",
    parameters={"type": "object", "properties": {}},
)
async def read_shared_context_handler(
    ctx: Any, arguments: dict[str, Any]
) -> str:
    """Read entries from sibling agents while excluding the caller."""
    del arguments
    conversation_id, agent_id, _agent_type = _context_identity(ctx)
    if not conversation_id:
        return "读取共享上下文失败：缺少会话 ID。"
    entries = await shared_context.read_all(
        conversation_id, exclude_agent_id=agent_id or None
    )
    formatted = shared_context.format_for_prompt(entries)
    return formatted or "暂无其他 agent 发布的共享上下文。"
