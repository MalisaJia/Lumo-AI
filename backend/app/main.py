import logging
import mimetypes
import re
from contextlib import asynccontextmanager

import sqlalchemy as sa
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
# StaticFiles 抛的是 starlette 基类 HTTPException（fastapi.HTTPException 是它的子类），
# 因此这里必须用基类才能接住静态目录的 404/405
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.types import Scope

import app.models  # noqa: F401  确保模型注册到 Base.metadata
from app.core.config import BACKEND_DIR, settings
from app.core.db import Base, engine
from app.modules.auth.router import router as auth_router
from app.modules.chat.router import computer_use_router, router as chat_router
from app.modules.conversations.router import messages_router
from app.modules.conversations.router import router as conversations_router
from app.modules.export.router import router as export_router
from app.modules.memory.router import router as memories_router
from app.modules.memory.router import settings_router as memory_settings_router
from app.modules.ppt_master.router import router as ppt_router
from app.modules.providers.router import router as providers_router
from app.modules.routing.router import router as routing_settings_router
from app.modules.search.router import router as settings_router
from app.modules.tasks.router import router as tasks_router
from app.modules.tools.router import router as tools_settings_router
from app.modules.uploads.router import UPLOAD_DIR
from app.modules.uploads.router import router as uploads_router
from app.modules.workspace.router import router as workspace_router

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
    """Upgrade managed databases before serving requests; stamp fresh schemas.

    Reuse the startup connection so migrations target the same database and
    do not open a competing connection inside the async startup transaction.
    Unknown revisions or failed migrations must still abort startup.
    """
    if sa.inspect(conn).has_table("alembic_version"):
        head = _alembic_head()
        if not head:
            raise RuntimeError("Cannot determine the bundled Alembic schema revision")
        current = conn.execute(
            sa.text("SELECT version_num FROM alembic_version")
        ).scalar_one_or_none()
        if current != head:
            from alembic import command
            from alembic.config import Config

            logger.info("Automatically upgrading database schema: %s -> %s", current, head)
            cfg = Config(str(BACKEND_DIR / "alembic.ini"))
            cfg.attributes["connection"] = conn
            try:
                command.upgrade(cfg, "head")
                migrated = conn.execute(
                    sa.text("SELECT version_num FROM alembic_version")
                ).scalar_one()
                if migrated != head:
                    raise RuntimeError(f"Migration finished at {migrated}, expected {head}")
            except Exception as exc:
                logger.exception("Automatic database migration failed: %s -> %s", current, head)
                raise RuntimeError(
                    f"Automatic database migration failed ({current} -> {head})"
                ) from exc
            logger.info("Database schema migration completed: %s", head)
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
    # Upgrade retained databases, or create and stamp a fresh schema, before serving.
    async with engine.begin() as conn:
        await conn.run_sync(_bootstrap_schema)

    # MCP 故障不应阻止主应用启动；每个服务器也相互隔离。
    if settings.mcp_config_path:
        try:
            from app.modules.mcp.bridge import register_mcp_tools
            from app.modules.mcp.client import get_mcp_manager
            from app.modules.mcp.config import load_mcp_config

            servers_config = load_mcp_config(settings.mcp_config_path)
            manager = get_mcp_manager()
            started_servers = 0
            registered_tools = 0
            for name, cfg in servers_config.items():
                try:
                    await manager.start_server(
                        name=name,
                        command=cfg["command"],
                        args=cfg.get("args", []),
                        env=cfg.get("env"),
                    )
                    tools = await manager.list_tools(name)
                    registered = register_mcp_tools(name, tools)
                    started_servers += 1
                    registered_tools += registered
                    logger.info(
                        "MCP server '%s': %d tools registered", name, registered
                    )
                except Exception as exc:
                    logger.warning("Failed to start MCP server '%s': %s", name, exc)
            logger.info(
                "MCP initialization complete: %d servers and %d tools loaded",
                started_servers,
                registered_tools,
            )
        except Exception as exc:
            logger.warning("MCP initialization failed: %s", exc)

    try:
        yield
    finally:
        try:
            from app.modules.mcp.client import get_mcp_manager

            await get_mcp_manager().stop_all()
        except Exception as exc:
            logger.warning("MCP shutdown failed: %s", exc)


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
app.include_router(computer_use_router)
app.include_router(settings_router)
app.include_router(routing_settings_router)
app.include_router(tasks_router)
app.include_router(tools_settings_router)
app.include_router(memory_settings_router)
app.include_router(memories_router)
app.include_router(uploads_router)
app.include_router(export_router)
app.include_router(ppt_router)
app.include_router(workspace_router)

# 上传图片静态服务（目录不存在时自动创建）
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """全局兜底：未捕获异常统一返回 {detail}，并记录完整堆栈便于排查。"""
    # handler 不一定处于 except 上下文中，显式传 exc_info 确保堆栈被记录
    logger.exception(
        "未处理异常：%s %s", request.method, request.url.path, exc_info=exc
    )
    return JSONResponse(status_code=500, content={"detail": "服务器内部错误"})


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# 前端静态资源缓存策略（仅作用于下方静态挂载，不影响 /api 与 SSE）：
# - Vite 输出到 assets/ 的文件名自带内容 hash（如 index-DQloli65.js），内容变化
#   必然改名，可放心永久缓存；
# - index.html、favicon/图标等无 hash 文件一律 no-cache，每次都回源走条件请求
#   （StaticFiles 原有的 ETag/Last-Modified -> 304 机制保留），避免 Chromium 启发式
#   新鲜度（约 33 小时）在升级后继续复用旧前端页面。
_HASHED_ASSET_RE = re.compile(
    r"^[A-Za-z0-9._\-]+-[A-Za-z0-9_\-]{8,}"
    r"\.(?:js|mjs|css|map|woff|woff2|ttf|otf|eot|svg|png|jpe?g|gif|webp|avif|ico|json)$",
    re.IGNORECASE,
)


def _is_hashed_asset(path: str) -> bool:
    """判断是否为 assets/ 目录下文件名带内容 hash 的构建产物。"""
    normalized = path.replace("\\", "/").strip("/")
    if not normalized.startswith("assets/"):
        return False
    return bool(_HASHED_ASSET_RE.match(normalized.rsplit("/", 1)[-1]))


class FrontendStaticFiles(StaticFiles):
    """按文件类型附加 Cache-Control 的前端静态目录挂载。"""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            # 未命中静态文件时（404 等）也下 no-cache，否则 Chromium 启发式缓存
            # 会把“文件不存在”这个结果缓存一段时间，后续版本补上文件也拿不到
            exc.headers = {**(exc.headers or {}), "Cache-Control": "no-cache"}
            raise
        if _is_hashed_asset(path):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            # HTML（root/目录 index/404.html）与无 hash 的图标等保守处理
            response.headers["Cache-Control"] = "no-cache"
        return response


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
            FrontendStaticFiles(directory=str(_frontend_dir), html=True),
            name="frontend",
        )
        logger.info("前端静态文件已挂载：%s", _frontend_dir)
        break
