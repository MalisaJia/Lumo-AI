"""Auth 模块 Schema（沿用项目 CamelModel 风格，JSON 字段 camelCase）。"""

from datetime import datetime

from app.schemas import CamelModel


class RegisterIn(CamelModel):
    username: str
    password: str
    email: str | None = None


class LoginIn(CamelModel):
    username: str
    password: str


class UserOut(CamelModel):
    id: str
    username: str
    email: str | None = None
    created_at: datetime


class TokenOut(CamelModel):
    token: str
    user: UserOut
