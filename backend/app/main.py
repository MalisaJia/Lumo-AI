import logging
import mimetypes
from contextlib import asynccontextmanager

import sqlalchemy as sa
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import app.models  # noqa: F401  确保模型注册到 Base.metadata
from app.core.config import BACKEND_DIR, settings
from app.core.db import Base, engine
from app.modules.auth.router import router as auth_router
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

# Windows 注册表可能把 .js 的 Content-Type 改成 text/plain，导致打包后前端模块脚本被浏览器拒绝
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")


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

    - 存在 alembic_version 表：校验库内 revision 与代码 head 一致，落后则快速失败，
      禁止带部分 schema 静默运行（否则查询新列时随机报 no such column）
    - 不存在：create_all 后写入当前 head（等价 alembic stamp head），
      保证之后执行 alembic upgrade 不会重跑初始迁移报 table already exists
    """
    if sa.inspect(conn).has_table("alembic_version"):
        head = _alembic_head()
        try:
            current = conn.execute(
                sa.text("SELECT version_num FROM alembic_version")
            ).scalar()
        except Exception:
            logger.warning(
                "读取 alembic_version.version_num 失败，跳过 schema 版本校验",
                exc_info=True,
            )
            return
        if head and current != head:
            logger.error(
                "数据库 schema 版本不匹配：当前版本 %s，目标版本 %s。"
                "请在 backend 目录运行 alembic upgrade head 升级数据库后再启动。",
                current,
                head,
            )
            raise RuntimeError(
                f"数据库 schema 版本不匹配（当前 {current}，目标 {head}），"
                "请运行 alembic upgrade head 后重试"
            )
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
    # 多用户模式下 MASTER_KEY 不能为空，否则 JWT 密钥退化为固定弱值
    if settings.auth_enabled and not settings.master_key:
        logger.error("AUTH_ENABLED=true 时必须配置 MASTER_KEY，请在 backend/.env 中设置")
        raise RuntimeError("AUTH_ENABLED=true 时必须配置 MASTER_KEY")
    # startup：仅在未纳入 alembic 管理时自动建表并 stamp head
    async with engine.begin() as conn:
        await conn.run_sync(_bootstrap_schema)
    yield


app = FastAPI(title="Lumo AI", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    # 逗号分隔多源（如 http://localhost:5173,https://example.com）
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
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


# 桌面版/生产模式：条件挂载前端静态文件（SPA）。
# FastAPI 中路由优先于 mount 匹配，但 "/" 挂载仍放在所有路由定义之后保险。
# 依次探测：PyInstaller 打包产物内的 frontend_dist/ -> 仓库内 frontend/dist/；
# 都不存在则不挂载（dev 模式走 vite 开发服务器）。
for _frontend_dir in (
    BACKEND_DIR / "frontend_dist",
    BACKEND_DIR.parent / "frontend" / "dist",
):
    if _frontend_dir.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=str(_frontend_dir), html=True),
            name="frontend",
        )
        logger.info("前端静态文件已挂载：%s", _frontend_dir)
        break
