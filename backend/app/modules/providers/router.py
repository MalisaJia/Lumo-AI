from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.modules.providers import service
from app.schemas import (
    ProviderCreate,
    ProviderOut,
    ProviderUpdate,
    ValidateRequest,
    ValidateResponse,
)

router = APIRouter(prefix="/api/providers", tags=["providers"])


@router.get("", response_model=list[ProviderOut])
async def list_providers(session: AsyncSession = Depends(get_session)):
    providers = await service.list_providers(session)
    return [service.to_provider_dict(p) for p in providers]


@router.post("", response_model=ProviderOut, status_code=201)
async def create_provider(
    body: ProviderCreate, session: AsyncSession = Depends(get_session)
):
    # 保存前先调用上游验证 Key，失败则 422
    result = await service.validate_upstream(body.base_url, body.api_key)
    if not result["valid"]:
        raise HTTPException(
            status_code=422, detail=result.get("error") or "API Key 验证失败"
        )
    provider = await service.create_provider(
        session,
        name=body.name,
        base_url=body.base_url,
        api_key=body.api_key,
        models=body.models,
        is_default=body.is_default,
    )
    return service.to_provider_dict(provider)


@router.put("/{provider_id}", response_model=ProviderOut)
async def update_provider(
    provider_id: str, body: ProviderUpdate, session: AsyncSession = Depends(get_session)
):
    provider = await service.get_provider(session, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider 不存在")
    # 若更换了 Key 或 baseUrl，则用最终生效的组合重新验证
    if body.api_key is not None or body.base_url is not None:
        from app.core.crypto import decrypt_key

        effective_url = body.base_url or provider.base_url
        effective_key = body.api_key or decrypt_key(provider.encrypted_api_key)
        result = await service.validate_upstream(effective_url, effective_key)
        if not result["valid"]:
            raise HTTPException(
                status_code=422, detail=result.get("error") or "API Key 验证失败"
            )
    provider = await service.update_provider(
        session,
        provider,
        name=body.name,
        base_url=body.base_url,
        api_key=body.api_key,
        models=body.models,
        is_default=body.is_default,
    )
    return service.to_provider_dict(provider)


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(
    provider_id: str, session: AsyncSession = Depends(get_session)
):
    provider = await service.get_provider(session, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider 不存在")
    await service.delete_provider(session, provider)


@router.post("/validate", response_model=ValidateResponse)
async def validate_provider(body: ValidateRequest):
    result = await service.validate_upstream(body.base_url, body.api_key)
    return ValidateResponse(**result)
