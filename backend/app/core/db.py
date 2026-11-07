from collections.abc import AsyncGenerator

from sqlalchemy import event as sa_event
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
)


# Enable WAL mode and busy timeout on every new SQLite connection
@sa_event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")  # 5s retry on SQLITE_BUSY
    cursor.execute("PRAGMA synchronous=NORMAL")  # WAL-safe, faster than FULL
    cursor.close()


async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：提供一个异步数据库会话。"""
    async with async_session_factory() as session:
        yield session
