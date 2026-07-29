from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.modules.memory import service
from app.schemas import (
    MemoryCreate,
    MemoryOut,
    MemorySettingsOut,
    MemorySettingsUpdate,
    MemoryUpdate,
)

settings_router = APIRouter(prefix="/api/settings", tags=["settings"])
router = APIRouter(prefix="/api/memories", tags=["memories"])


@settings_router.get("/memory", response_model=MemorySettingsOut)
async def get_memory_settings(session: AsyncSession = Depends(get_session)):
    return await service.get_memory_settings(session)


@settings_router.put("/memory", response_model=MemorySettingsOut)
async def update_memory_settings(
    body: MemorySettingsUpdate, session: AsyncSession = Depends(get_session)
):
    return await service.update_memory_settings(session, enabled=body.enabled)


@router.get("", response_model=list[MemoryOut])
async def list_memories(
    since: datetime | None = Query(default=None),
    type: str | None = Query(default=None, pattern="^(fact|preference|summary)$"),
    session: AsyncSession = Depends(get_session),
):
    return await service.list_memories(session, since=since, type_=type)


@router.post("", response_model=MemoryOut, status_code=201)
async def create_memory(
    body: MemoryCreate, session: AsyncSession = Depends(get_session)
):
    return await service.create_memory(
        session, content=body.content, memory_type=body.type, tags=body.tags
    )


@router.put("/{memory_id}", response_model=MemoryOut)
async def update_memory(
    memory_id: str, body: MemoryUpdate, session: AsyncSession = Depends(get_session)
):
    memory = await service.get_memory(session, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    return await service.update_memory(
        session,
        memory,
        content=body.content,
        tags=body.tags,
        is_enabled=body.is_enabled,
    )


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(memory_id: str, session: AsyncSession = Depends(get_session)):
    memory = await service.get_memory(session, memory_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="记忆不存在")
    await service.delete_memory(session, memory)
