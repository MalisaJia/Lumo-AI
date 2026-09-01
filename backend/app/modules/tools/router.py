from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user_id
from app.core.db import get_session
from app.modules.tools import service
from app.schemas import ToolsSettingsOut, ToolsSettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/tools", response_model=ToolsSettingsOut)
async def get_tools_settings(
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    return await service.get_tools_settings(session, user_id)


@router.put("/tools", response_model=ToolsSettingsOut)
async def update_tools_settings(
    body: ToolsSettingsUpdate,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    return await service.update_tools_settings(session, user_id, enabled=body.enabled)
