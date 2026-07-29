"""Provider 业务逻辑：CRUD、上游 Key 验证、baseUrl 规范化。"""

import json
from typing import Any

import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.crypto import decrypt_key, encrypt_key, mask_key
from app.models import Model, Provider
from app.schemas import ModelIn

VALIDATE_TIMEOUT = 15.0


def normalize_base_url(url: str) -> str:
    """去掉尾部 /；用户填写的 /v1 保留。"""
    return url.strip().rstrip("/")


async def validate_upstream(base_url: str, api_key: str) -> dict[str, Any]:
    """调用上游验证 Key。

    先 GET {baseUrl}/models；401/403 视为 Key 无效；若端点不存在（404 等）
    降级 POST {baseUrl}/chat/completions 发 max_tokens=1 测试。
    网络错误/超时返回 valid=False + error 描述。
    """
    base_url = normalize_base_url(base_url)
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        async with httpx.AsyncClient(timeout=VALIDATE_TIMEOUT) as client:
            resp = await client.get(f"{base_url}/models", headers=headers)
            if resp.status_code in (401, 403):
                return {"valid": False, "error": "API Key 无效或无权限"}
            if resp.status_code < 300:
                model_ids: list[str] = []
                try:
                    data = resp.json()
                    items = data.get("data", data) if isinstance(data, dict) else data
                    if isinstance(items, list):
                        model_ids = [
                            m["id"]
                            for m in items
                            if isinstance(m, dict) and isinstance(m.get("id"), str)
                        ]
                except (ValueError, KeyError, TypeError):
                    pass  # 尽力而为：解析失败仍视为验证通过
                return {"valid": True, "models": model_ids or None}
            # 兼容端点无 /models：降级用最小 chat 请求探测
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [{"role": "user", "content": "hi"}],
                    "max_tokens": 1,
                },
            )
            if resp.status_code in (401, 403):
                return {"valid": False, "error": "API Key 无效或无权限"}
            if resp.status_code < 500:
                # 2xx 或 4xx（如模型名不存在）都说明 Key 已通过鉴权
                return {"valid": True}
            return {
                "valid": False,
                "error": f"上游服务异常（HTTP {resp.status_code}）",
            }
    except httpx.TimeoutException:
        return {"valid": False, "error": "连接上游超时（15 秒），请检查 Base URL"}
    except httpx.HTTPError as exc:
        return {"valid": False, "error": f"网络错误：{exc.__class__.__name__}"}


def _parse_capability_tags(raw: str | None) -> list[str] | None:
    """DB 中为 JSON 数组字符串；解析失败/非数组视为无值。"""
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None
    return [str(t) for t in parsed] if isinstance(parsed, list) else None


def to_provider_dict(p: Provider) -> dict[str, Any]:
    """组装响应：只暴露 maskedKey，不含任何明文/密文 Key。"""
    try:
        masked = mask_key(decrypt_key(p.encrypted_api_key))
    except Exception:
        masked = "****"
    return {
        "id": p.id,
        "name": p.name,
        "base_url": p.base_url,
        "masked_key": masked,
        "is_default": p.is_default,
        "models": [
            {
                "id": m.id,
                "name": m.name,
                "label": m.label,
                "is_default": m.is_default,
                "context_length": m.context_length,
                "capability_tags": _parse_capability_tags(m.capability_tags),
            }
            for m in p.models
        ],
    }


async def list_providers(session: AsyncSession, user_id: str) -> list[Provider]:
    result = await session.execute(
        select(Provider)
        .options(selectinload(Provider.models))
        .where(Provider.user_id == user_id)
        .order_by(Provider.created_at)
    )
    return list(result.scalars().all())


async def get_provider(
    session: AsyncSession, provider_id: str, user_id: str
) -> Provider | None:
    """按 id + user_id 双条件查询：他人 Provider 查不到即 None（路由层转 404）。"""
    result = await session.execute(
        select(Provider)
        .options(selectinload(Provider.models))
        .where(Provider.id == provider_id, Provider.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _clear_other_defaults(
    session: AsyncSession, user_id: str, keep_id: str
) -> None:
    """isDefault 互斥：仅在同一用户范围内把其他记录置 False。"""
    await session.execute(
        update(Provider)
        .where(Provider.user_id == user_id, Provider.id != keep_id)
        .values(is_default=False)
    )


def _build_models(provider_id: str, items: list[ModelIn]) -> list[Model]:
    models = [
        Model(
            provider_id=provider_id,
            name=item.name,
            label=item.label or item.name,
            is_default=item.is_default,
            context_length=item.context_length,
            # 空列表/None 存 NULL，读取时降级默认能力表
            capability_tags=(
                json.dumps(item.capability_tags, ensure_ascii=False)
                if item.capability_tags
                else None
            ),
        )
        for item in items
    ]
    # 模型级 isDefault 互斥：仅保留第一个默认
    seen_default = False
    for m in models:
        if m.is_default:
            if seen_default:
                m.is_default = False
            seen_default = True
    return models


async def create_provider(
    session: AsyncSession,
    user_id: str,
    *,
    name: str,
    base_url: str,
    api_key: str,
    models: list[ModelIn],
    is_default: bool,
) -> Provider:
    provider = Provider(
        user_id=user_id,
        name=name,
        base_url=normalize_base_url(base_url),
        encrypted_api_key=encrypt_key(api_key),
        is_default=is_default,
    )
    session.add(provider)
    await session.flush()
    for m in _build_models(provider.id, models):
        session.add(m)
    if is_default:
        await _clear_other_defaults(session, user_id, provider.id)
    await session.commit()
    return await get_provider(session, provider.id, user_id)  # type: ignore[return-value]


async def update_provider(
    session: AsyncSession,
    provider: Provider,
    *,
    name: str | None,
    base_url: str | None,
    api_key: str | None,
    models: list[ModelIn] | None,
    is_default: bool | None,
) -> Provider:
    if name is not None:
        provider.name = name
    if base_url is not None:
        provider.base_url = normalize_base_url(base_url)
    if api_key is not None:
        provider.encrypted_api_key = encrypt_key(api_key)
    if is_default is not None:
        provider.is_default = is_default
        if is_default:
            # provider 已经过归属校验，按其 user_id 限定互斥范围
            await _clear_other_defaults(session, provider.user_id, provider.id)
    if models is not None:
        await session.execute(delete(Model).where(Model.provider_id == provider.id))
        for m in _build_models(provider.id, models):
            session.add(m)
    await session.commit()
    return await get_provider(session, provider.id, provider.user_id)  # type: ignore[return-value]


async def delete_provider(session: AsyncSession, provider: Provider) -> None:
    await session.execute(delete(Model).where(Model.provider_id == provider.id))
    await session.delete(provider)
    await session.commit()
