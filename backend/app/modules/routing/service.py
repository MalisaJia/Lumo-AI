"""模型自动路由设置：settings KV 表读写（复用 search 设置的读写模式）。"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.search.service import _get_setting, _set_setting

# settings 表中的键名；值 "true"/"false"，缺省视为开启
KEY_AUTO_ROUTING = "auto_routing"


async def is_auto_routing_enabled(session: AsyncSession) -> bool:
    """内部使用：仅显式保存 "false" 时关闭，默认开启。"""
    return (await _get_setting(session, KEY_AUTO_ROUTING)) != "false"


async def get_routing_settings(session: AsyncSession) -> dict[str, Any]:
    return {"enabled": await is_auto_routing_enabled(session)}


async def update_routing_settings(
    session: AsyncSession, *, enabled: bool
) -> dict[str, Any]:
    await _set_setting(session, KEY_AUTO_ROUTING, "true" if enabled else "false")
    await session.commit()
    return await get_routing_settings(session)
