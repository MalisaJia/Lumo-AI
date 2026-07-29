"""Auth 模块业务逻辑：用户注册与凭据校验。"""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import hash_password, verify_password
from app.models import User


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    """按用户名查用户。"""
    result = await session.execute(select(User).where(User.username == username))
    return result.scalar_one_or_none()


async def register_user(
    session: AsyncSession, username: str, password: str, email: str | None = None
) -> User:
    """注册新用户：用户名查重（重复抛 400 由 router 处理为 HTTPException），bcrypt 哈希后写库。"""
    user = User(
        username=username,
        password_hash=hash_password(password),
        email=email,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError:
        # 并发注册同名用户时唯一约束兜底：回滚后上抛，由 router 转 400
        await session.rollback()
        raise
    await session.refresh(user)
    return user


async def authenticate(
    session: AsyncSession, username: str, password: str
) -> User | None:
    """校验用户名密码：任一不匹配或用户被禁用返回 None。"""
    user = await get_user_by_username(session, username)
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user
