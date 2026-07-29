"""Auth 模块路由：注册 / 登录 / 当前用户。

所有端点入口先检查 settings.auth_enabled：单用户模式下鉴权体系休眠，一律 403。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import create_access_token, get_current_user_id
from app.core.config import settings
from app.core.db import get_session
from app.models import User
from app.modules.auth import service
from app.modules.auth.schemas import LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 密码最少长度
_MIN_PASSWORD_LENGTH = 8


def _ensure_auth_enabled() -> None:
    """单用户模式下鉴权端点不可用。"""
    if not settings.auth_enabled:
        raise HTTPException(status_code=403, detail="多用户模式未启用")


def _validate_register(body: RegisterIn) -> None:
    """注册基本校验：用户名非空、密码最少长度。"""
    if not body.username.strip():
        raise HTTPException(status_code=422, detail="用户名不能为空")
    if len(body.password) < _MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=422, detail=f"密码长度至少 {_MIN_PASSWORD_LENGTH} 位"
        )


@router.post("/register", response_model=UserOut, status_code=201)
async def register(body: RegisterIn, session: AsyncSession = Depends(get_session)):
    _ensure_auth_enabled()
    _validate_register(body)
    username = body.username.strip()
    # 用户名查重（常规路径的友好检查，并发竞态由唯一约束兜底）
    if await service.get_user_by_username(session, username) is not None:
        raise HTTPException(status_code=400, detail="用户名已存在")
    try:
        user = await service.register_user(
            session, username=username, password=body.password, email=body.email
        )
    except IntegrityError:
        raise HTTPException(status_code=400, detail="用户名已存在")
    return UserOut.model_validate(user)


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, session: AsyncSession = Depends(get_session)):
    _ensure_auth_enabled()
    user = await service.authenticate(session, body.username.strip(), body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return TokenOut(
        token=create_access_token(user.id), user=UserOut.model_validate(user)
    )


@router.get("/me", response_model=UserOut)
async def me(
    user_id: str = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_session),
):
    _ensure_auth_enabled()
    user = await session.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="用户不存在或已被禁用")
    return UserOut.model_validate(user)
