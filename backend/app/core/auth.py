"""鉴权内核：JWT 签发/校验、密码哈希、当前用户依赖。

默认 AUTH_ENABLED=false 的休眠鉴权体系：
- 单用户模式下 get_current_user_id 直接返回 settings.default_user_id（不查库、不看头）
- 多用户模式下解析 Authorization: Bearer 头，校验 JWT 并确认用户存在且激活
"""

import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session

# JWT 算法固定 HS256
_JWT_ALGORITHM = "HS256"


def _jwt_secret() -> bytes:
    """JWT 密钥从 MASTER_KEY 派生（sha256(master_key + ":jwt")），不引入新密钥。"""
    return hashlib.sha256(f"{settings.master_key}:jwt".encode("utf-8")).digest()


def create_access_token(user_id: str) -> str:
    """签发访问令牌：sub=user_id，有效期 jwt_expire_days 天。"""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_expire_days),
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str) -> str:
    """解析访问令牌并返回 user_id；过期/无效由 PyJWT 抛出异常。"""
    payload = jwt.decode(token, _jwt_secret(), algorithms=[_JWT_ALGORITHM])
    user_id = payload.get("sub")
    if not user_id:
        raise jwt.InvalidTokenError("token 缺少 sub")
    return user_id


def hash_password(plain: str) -> str:
    """bcrypt 哈希密码（含随机盐）。"""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码与 bcrypt 哈希是否匹配。"""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # 哈希格式非法（如脏数据）视为不匹配
        return False


async def get_current_user_id(
    request: Request, session: AsyncSession = Depends(get_session)
) -> str:
    """FastAPI 依赖：解析当前请求归属的用户 ID。

    - auth_enabled=false：直接返回默认用户（不查库、不看头，本机零变化）
    - auth_enabled=true：校验 Bearer JWT 并确认用户存在且激活，失败一律 401
    """
    if not settings.auth_enabled:
        return settings.default_user_id

    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="未提供有效的认证凭据")

    try:
        user_id = decode_access_token(token.strip())
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的认证凭据")

    # 延迟导入避免 models -> core 的循环依赖
    from app.models import User

    user = (
        await session.execute(select(User).where(User.id == user_id))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已被禁用")
    return user.id
