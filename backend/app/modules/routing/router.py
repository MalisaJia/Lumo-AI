from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user_id
from app.core.db import get_session
from app.modules.routing import service
from app.schemas import RoutingSettingsOut, RoutingSettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/routing", response_model=RoutingSettingsOut)
async def get_routing_settings(
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    return await service.get_routing_settings(session, user_id)


@router.put("/routing", response_model=RoutingSettingsOut)
async def update_routing_settings(
    body: RoutingSettingsUpdate,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    return await service.update_routing_settings(
        session,
        user_id,
        enabled=body.enabled,
        smart_selection_enabled=body.smart_selection_enabled,
    )
