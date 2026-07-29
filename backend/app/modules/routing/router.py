from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.modules.routing import service
from app.schemas import RoutingSettingsOut, RoutingSettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/routing", response_model=RoutingSettingsOut)
async def get_routing_settings(session: AsyncSession = Depends(get_session)):
    return await service.get_routing_settings(session)


@router.put("/routing", response_model=RoutingSettingsOut)
async def update_routing_settings(
    body: RoutingSettingsUpdate, session: AsyncSession = Depends(get_session)
):
    return await service.update_routing_settings(session, enabled=body.enabled)
