"""Agent 工具（skills）特性开关：settings KV 表读写（复用 routing 模式）。"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.search.service import _get_setting, _set_setting

# settings 表中的键名；值 "true"/"false"，缺省视为开启
KEY_AGENT_TOOLS = "agent_tools"


async def is_tools_enabled(session: AsyncSession, user_id: str) -> bool:
    """内部使用：仅显式保存 "false" 时关闭，默认开启。"""
    return (await _get_setting(session, user_id, KEY_AGENT_TOOLS)) != "false"


async def get_tools_settings(session: AsyncSession, user_id: str) -> dict[str, Any]:
    return {"enabled": await is_tools_enabled(session, user_id)}


async def update_tools_settings(
    session: AsyncSession, user_id: str, *, enabled: bool
) -> dict[str, Any]:
    await _set_setting(
        session, user_id, KEY_AGENT_TOOLS, "true" if enabled else "false"
    )
    await session.commit()
    return await get_tools_settings(session, user_id)
