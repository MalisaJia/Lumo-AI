from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user_id
from app.core.db import get_session
from app.modules.conversations import service
from app.schemas import (
    ConversationCreate,
    ConversationOut,
    ConversationUpdate,
    MessageOut,
    MessageUpdate,
)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

# PUT /api/messages/{id} 与 DELETE /api/messages/{id}/after 挂在独立前缀下
messages_router = APIRouter(prefix="/api/messages", tags=["messages"])


@router.get("", response_model=list[ConversationOut])
async def list_conversations(
    q: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    return await service.list_conversations(session, user_id, q)


@router.post("", response_model=ConversationOut, status_code=201)
async def create_conversation(
    body: ConversationCreate,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    return await service.create_conversation(
        session,
        user_id,
        title=body.title,
        provider_id=body.provider_id,
        model_name=body.model_name,
    )


@router.patch("/{conversation_id}", response_model=ConversationOut)
async def update_conversation(
    conversation_id: str,
    body: ConversationUpdate,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    conversation = await service.get_conversation(session, conversation_id, user_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return await service.update_conversation(
        session,
        conversation,
        title=body.title,
        provider_id=body.provider_id,
        model_name=body.model_name,
    )


@router.delete("/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    conversation = await service.get_conversation(session, conversation_id, user_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    await service.delete_conversation(session, conversation)


@router.get("/{conversation_id}/messages", response_model=list[MessageOut])
async def list_messages(
    conversation_id: str,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    conversation = await service.get_conversation(session, conversation_id, user_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return await service.list_messages(session, conversation_id)


@messages_router.put("/{message_id}", response_model=MessageOut)
async def update_message(
    message_id: str,
    body: MessageUpdate,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    message = await service.get_message(session, message_id, user_id)
    if message is None:
        raise HTTPException(status_code=404, detail="消息不存在")
    if message.role != "user":
        raise HTTPException(status_code=422, detail="仅允许编辑用户消息")
    return await service.update_user_message(session, message, body.content)


@messages_router.delete("/{message_id}/after", status_code=204)
async def delete_messages_after(
    message_id: str,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    message = await service.get_message(session, message_id, user_id)
    if message is None:
        raise HTTPException(status_code=404, detail="消息不存在")
    await service.delete_messages_after(session, message)
    await session.commit()
