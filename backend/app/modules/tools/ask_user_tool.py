"""Structured user-question tool for coding agents."""

from typing import Any

from app.modules.agents.events import AgentEvent, event_bus
from app.modules.tools.registry import tool


def _event_conversation_id(ctx: Any) -> str:
    extra = getattr(ctx, "extra", {})
    parent_id = extra.get("event_conversation_id") if isinstance(extra, dict) else None
    return str(parent_id or getattr(ctx, "conversation_id", ""))


@tool(
    name="ask_user",
    description="向用户提问并提供 2 到 5 个结构化选项；需要用户做决策时使用。",
    parameters={
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "要问用户的问题"},
            "options": {
                "type": "array",
                "minItems": 2,
                "maxItems": 5,
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "description": {"type": "string"},
                    },
                    "required": ["label"],
                },
                "description": "选项列表（2-5 个）",
            },
        },
        "required": ["question", "options"],
    },
    timeout=15.0,
)
async def ask_user(ctx: Any, arguments: dict[str, Any]) -> str:
    question = str(arguments.get("question") or "").strip()
    if not question:
        return "提问失败：question 不能为空。"

    raw_options = arguments.get("options")
    if not isinstance(raw_options, list) or not 2 <= len(raw_options) <= 5:
        return "提问失败：options 必须包含 2 到 5 个选项。"

    options: list[dict[str, str]] = []
    for item in raw_options:
        if not isinstance(item, dict):
            return "提问失败：每个选项必须是对象。"
        label = str(item.get("label") or "").strip()
        if not label:
            return "提问失败：选项 label 不能为空。"
        option = {"label": label}
        description = str(item.get("description") or "").strip()
        if description:
            option["description"] = description
        options.append(option)

    conversation_id = _event_conversation_id(ctx)
    await event_bus.publish(
        AgentEvent(
            type="askUser",
            data={
                "question": question,
                "options": options,
                "toolCallId": str(arguments.get("_tool_call_id") or ""),
            },
            conversation_id=conversation_id,
        )
    )
    return f"[已向用户展示问题：{question}。等待用户在聊天中回复。]"
