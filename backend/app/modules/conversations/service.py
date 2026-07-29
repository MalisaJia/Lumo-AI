"""会话与消息的业务逻辑。"""

from datetime import datetime, timezone

from sqlalchemy import delete, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Message


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def list_conversations(
    session: AsyncSession, user_id: str, q: str | None = None
) -> list[Conversation]:
    stmt = (
        select(Conversation)
        .where(Conversation.user_id == user_id)
        .order_by(Conversation.updated_at.desc())
    )
    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                Conversation.title.ilike(pattern),
                exists(
                    select(Message.id).where(
                        Message.conversation_id == Conversation.id,
                        Message.content.ilike(pattern),
                    )
                ),
            )
        )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_conversation(
    session: AsyncSession, conversation_id: str, user_id: str
) -> Conversation | None:
    """按 id + user_id 双条件查询：他人会话查不到即 None（路由层转 404）。"""
    result = await session.execute(
        select(Conversation).where(
            Conversation.id == conversation_id,
            Conversation.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def create_conversation(
    session: AsyncSession,
    user_id: str,
    *,
    title: str | None,
    provider_id: str | None,
    model_name: str | None,
) -> Conversation:
    conversation = Conversation(
        user_id=user_id,
        title=title or "新对话",
        provider_id=provider_id,
        model_name=model_name,
    )
    session.add(conversation)
    await session.commit()
    return conversation


async def update_conversation(
    session: AsyncSession,
    conversation: Conversation,
    *,
    title: str | None,
    provider_id: str | None,
    model_name: str | None,
) -> Conversation:
    if title is not None:
        conversation.title = title
    if provider_id is not None:
        conversation.provider_id = provider_id
    if model_name is not None:
        conversation.model_name = model_name
    conversation.updated_at = _now()
    await session.commit()
    return conversation


async def delete_conversation(
    session: AsyncSession, conversation: Conversation
) -> None:
    # 级联删除消息（模型上有 cascade，此处显式删除以兼容 SQLite）
    await session.execute(
        delete(Message).where(Message.conversation_id == conversation.id)
    )
    await session.delete(conversation)
    await session.commit()


async def list_messages(
    session: AsyncSession, conversation_id: str
) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    return list(result.scalars().all())


async def get_message(
    session: AsyncSession, message_id: str, user_id: str
) -> Message | None:
    """join 所属会话校验 user_id 归属：他人消息查不到即 None（路由层转 404）。"""
    result = await session.execute(
        select(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Message.id == message_id, Conversation.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def delete_messages_after(session: AsyncSession, message: Message) -> None:
    """删除该消息之后（不含自身）的所有消息。"""
    await session.execute(
        delete(Message).where(
            Message.conversation_id == message.conversation_id,
            or_(
                Message.created_at > message.created_at,
                # created_at 相同时用 id 兜底（同一事务批量插入的场景）
                (Message.created_at == message.created_at)
                & (Message.id > message.id),
            ),
        )
    )


async def update_user_message(
    session: AsyncSession, message: Message, content: str
) -> Message:
    """更新 user 消息内容并删除其后的所有消息。"""
    message.content = content
    await delete_messages_after(session, message)
    await session.commit()
    return message
