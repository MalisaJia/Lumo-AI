"""模型自动路由设置：settings KV 表读写（复用 search 设置的读写模式）。"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.search.service import _get_setting, _set_setting

# settings 表中的键名；值 "true"/"false"，缺省视为开启
KEY_AUTO_ROUTING = "auto_routing"
# 任务感知智能选模开关；值 "true"/"false"，缺省视为关闭
KEY_SMART_SELECTION = "smart_model_selection"


async def is_auto_routing_enabled(session: AsyncSession, user_id: str) -> bool:
    """内部使用：仅显式保存 "false" 时关闭，默认开启。"""
    return (await _get_setting(session, user_id, KEY_AUTO_ROUTING)) != "false"


async def is_smart_selection_enabled(session: AsyncSession, user_id: str) -> bool:
    """内部使用：仅显式保存 "true" 时开启，默认关闭。"""
    return (await _get_setting(session, user_id, KEY_SMART_SELECTION)) == "true"


async def get_routing_settings(session: AsyncSession, user_id: str) -> dict[str, Any]:
    return {
        "enabled": await is_auto_routing_enabled(session, user_id),
        "smart_selection_enabled": await is_smart_selection_enabled(
            session, user_id
        ),
    }


async def update_routing_settings(
    session: AsyncSession,
    user_id: str,
    *,
    enabled: bool,
    smart_selection_enabled: bool | None,
) -> dict[str, Any]:
    await _set_setting(
        session, user_id, KEY_AUTO_ROUTING, "true" if enabled else "false"
    )
    # None 表示请求未携带该字段（旧客户端），保持现值不写入
    if smart_selection_enabled is not None:
        await _set_setting(
            session,
            user_id,
            KEY_SMART_SELECTION,
            "true" if smart_selection_enabled else "false",
        )
    await session.commit()
    return await get_routing_settings(session, user_id)
