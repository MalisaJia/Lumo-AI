import os
import secrets
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录（config.py 位于 backend/app/core/ 下）
BACKEND_DIR = Path(__file__).resolve().parents[2]
# 可写数据目录（db/.env/uploads 所在）：Electron 桌面版通过 LUMO_DATA_DIR
# 重定向到 %APPDATA%，未设置时回退 BACKEND_DIR（本地开发行为零变化）
DATA_DIR = (
    Path(os.environ["LUMO_DATA_DIR"]) if os.environ.get("LUMO_DATA_DIR") else BACKEND_DIR
)
ENV_FILE = DATA_DIR / ".env"


def _ensure_master_key() -> None:
    """若 DATA_DIR/.env 缺少非空的 MASTER_KEY，首次启动自动生成 32 字节随机 hex 并写入。"""
    content = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    lines = content.splitlines()
    for line in lines:
        name, _, value = line.partition("=")
        if name.strip() == "MASTER_KEY" and value.strip():
            return
    key = secrets.token_hex(32)  # 32 字节 -> 64 位 hex
    # 已存在空值的 MASTER_KEY= 行则原地替换，否则追加
    replaced = False
    for i, line in enumerate(lines):
        if line.partition("=")[0].strip() == "MASTER_KEY":
            lines[i] = f"MASTER_KEY={key}"
            replaced = True
            break
    if not replaced:
        lines.append(f"MASTER_KEY={key}")
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


# 确保数据目录存在（来自 LUMO_DATA_DIR 时首次启动需创建；BACKEND_DIR 本就存在，无害）
DATA_DIR.mkdir(parents=True, exist_ok=True)
_ensure_master_key()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 默认使用 DATA_DIR/lumo.db 的绝对路径，避免受启动时工作目录影响
    database_url: str = f"sqlite+aiosqlite:///{(DATA_DIR / 'lumo.db').as_posix()}"
    port: int = 8000
    master_key: str = ""
    # SSRF 例外开关：自建 SearXNG 常部署在 127.0.0.1，置 true 放行私网 searxngUrl
    allow_private_searxng: bool = False
    # 多用户鉴权总开关：false 时休眠，所有请求归属 default_user_id（本机零变化）
    auth_enabled: bool = False
    # 单用户模式下的默认用户 ID
    default_user_id: str = "local"
    # JWT 有效期（天）
    jwt_expire_days: int = 30
    # CORS 允许的来源（逗号分隔多源）
    cors_origins: str = "http://localhost:5173"


settings = Settings()
