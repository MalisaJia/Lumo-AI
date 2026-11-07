"""CLI 模式会话管理：创建/恢复编码会话。"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation


async def create_coding_session(
    session: AsyncSession,
    user_id: str,
    workspace_dir: str,
    provider_id: str | None = None,
    model_name: str | None = None,
    agent_type: str = "coding",
) -> Conversation:
    """创建一个预配置了所选 Agent 系统提示词的新会话。"""
    from app.modules.tools.agent_profiles import get_default_profile, get_profile

    profile = get_profile(agent_type) or get_default_profile()
    conversation = Conversation(
        id=uuid.uuid4().hex,
        user_id=user_id,
        title=profile.display_name,
        system_prompt=profile.build_prompt(workspace_dir),
        provider_id=provider_id,
        model_name=model_name,
    )
    session.add(conversation)
    await session.commit()
    return conversation


async def resume_session(
    session: AsyncSession,
    conversation_id: str,
    user_id: str,
) -> Conversation | None:
    """加载当前用户已有的会话。"""
    result = await session.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    return result.scalars().first()
