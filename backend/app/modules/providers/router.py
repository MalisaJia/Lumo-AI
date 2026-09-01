from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user_id
from app.core.db import get_session
from app.modules.providers import service
from app.modules.routing.classifier import TASK_TYPES
from app.schemas import (
    ModelIn,
    ProviderCreate,
    ProviderOut,
    ProviderUpdate,
    ValidateRequest,
    ValidateResponse,
)

router = APIRouter(prefix="/api/providers", tags=["providers"])


def _validate_models(models: list[ModelIn] | None) -> None:
    """模型条目校验：保留名 "auto" 禁用；能力标签限六种任务类型。"""
    for m in models or []:
        if m.name.strip().lower() == "auto":
            raise HTTPException(
                status_code=422, detail="auto 为保留名称，不能用作模型名"
            )
        for tag in m.capability_tags or []:
            if tag not in TASK_TYPES:
                raise HTTPException(
                    status_code=422,
                    detail=f"非法能力标签：{tag}（允许：{', '.join(TASK_TYPES)}）",
                )


@router.get("", response_model=list[ProviderOut])
async def list_providers(
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    providers = await service.list_providers(session, user_id)
    return [service.to_provider_dict(p) for p in providers]


@router.post("", response_model=ProviderOut, status_code=201)
async def create_provider(
    body: ProviderCreate,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    _validate_models(body.models)
    # 保存前先调用上游验证 Key，失败则 422
    result = await service.validate_upstream(body.base_url, body.api_key)
    if not result["valid"]:
        raise HTTPException(
            status_code=422, detail=result.get("error") or "API Key 验证失败"
        )
    provider = await service.create_provider(
        session,
        user_id,
        name=body.name,
        base_url=body.base_url,
        api_key=body.api_key,
        models=body.models,
        is_default=body.is_default,
    )
    return service.to_provider_dict(provider)


@router.put("/{provider_id}", response_model=ProviderOut)
async def update_provider(
    provider_id: str,
    body: ProviderUpdate,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    _validate_models(body.models)
    provider = await service.get_provider(session, provider_id, user_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider 不存在")
    # 若更换了 Key 或 baseUrl，则用最终生效的组合重新验证
    if body.api_key is not None or body.base_url is not None:
        from app.core.crypto import DecryptionError, decrypt_key

        effective_url = body.base_url or provider.base_url
        if body.api_key:
            effective_key = body.api_key
        else:
            try:
                effective_key = decrypt_key(provider.encrypted_api_key)
            except DecryptionError as exc:
                raise HTTPException(
                    status_code=422,
                    detail="已保存的 API Key 解密失败，请重新填写并保存",
                ) from exc
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
    provider_id: str,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    provider = await service.get_provider(session, provider_id, user_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider 不存在")
    await service.delete_provider(session, provider)


@router.post("/validate", response_model=ValidateResponse)
async def validate_provider(body: ValidateRequest):
    result = await service.validate_upstream(body.base_url, body.api_key)
    return ValidateResponse(**result)
