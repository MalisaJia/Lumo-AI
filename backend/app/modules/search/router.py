from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.modules.search import service, urlguard
from app.schemas import SearchSettingsOut, SearchSettingsUpdate

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/search", response_model=SearchSettingsOut)
async def get_search_settings(session: AsyncSession = Depends(get_session)):
    return await service.get_search_settings(session)


@router.put("/search", response_model=SearchSettingsOut)
async def update_search_settings(
    body: SearchSettingsUpdate, session: AsyncSession = Depends(get_session)
):
    # SSRF 防护：searxngUrl 入库前校验；ALLOW_PRIVATE_SEARXNG=true 时放行私网
    if body.searxng_url is not None and body.searxng_url.strip():
        error = await urlguard.validate_public_url_async(
            body.searxng_url.strip(),
            allow_private=settings.allow_private_searxng,
        )
        if error:
            raise HTTPException(
                status_code=422, detail=f"searxngUrl 不合法：{error}"
            )
    return await service.update_search_settings(
        session,
        search_provider=body.search_provider,
        tavily_api_key=body.tavily_api_key,
        searxng_url=body.searxng_url,
    )
