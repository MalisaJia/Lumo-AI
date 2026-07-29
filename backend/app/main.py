import logging
from contextlib import asynccontextmanager

import sqlalchemy as sa
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import app.models  # noqa: F401  确保模型注册到 Base.metadata
from app.core.config import BACKEND_DIR
from app.core.db import Base, engine
from app.modules.chat.router import router as chat_router
from app.modules.conversations.router import messages_router
from app.modules.conversations.router import router as conversations_router
from app.modules.memory.router import router as memories_router
from app.modules.memory.router import settings_router as memory_settings_router
from app.modules.providers.router import router as providers_router
from app.modules.routing.router import router as routing_settings_router
from app.modules.search.router import router as settings_router
from app.modules.uploads.router import UPLOAD_DIR
from app.modules.uploads.router import router as uploads_router

logger = logging.getLogger(__name__)


def _alembic_head() -> str | None:
    """从 alembic 脚本目录读当前 head revision（不走 subprocess）。"""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        cfg = Config(str(BACKEND_DIR / "alembic.ini"))
        return ScriptDirectory.from_config(cfg).get_current_head()
    except Exception:
        logger.warning("读取 alembic head revision 失败", exc_info=True)
        return None


def _bootstrap_schema(conn: sa.Connection) -> None:
    """建表引导：已由 alembic 管理的库不再 create_all，避免与迁移冲突。

    - 存在 alembic_version 表：跳过，schema 全部交给 alembic upgrade 管理
    - 不存在：create_all 后写入当前 head（等价 alembic stamp head），
      保证之后执行 alembic upgrade 不会重跑初始迁移报 table already exists
    """
    if sa.inspect(conn).has_table("alembic_version"):
        return
    Base.metadata.create_all(conn)
    head = _alembic_head()
    if not head:
        return
    conn.execute(
        sa.text(
            "CREATE TABLE IF NOT EXISTS alembic_version ("
            "version_num VARCHAR(32) NOT NULL, "
            "CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num))"
        )
    )
    conn.execute(
        sa.text("INSERT INTO alembic_version (version_num) VALUES (:rev)"),
        {"rev": head},
    )
    logger.info("初次建表完成并 stamp alembic head=%s", head)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup：仅在未纳入 alembic 管理时自动建表并 stamp head
    async with engine.begin() as conn:
        await conn.run_sync(_bootstrap_schema)
    yield


app = FastAPI(title="Lumo AI", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(providers_router)
app.include_router(conversations_router)
app.include_router(messages_router)
app.include_router(chat_router)
app.include_router(settings_router)
app.include_router(routing_settings_router)
app.include_router(memory_settings_router)
app.include_router(memories_router)
app.include_router(uploads_router)

# 上传图片静态服务（目录不存在时自动创建）
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """全局兜底：未捕获异常统一返回 {detail}。"""
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误"})


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
