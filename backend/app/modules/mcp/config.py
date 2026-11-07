"""MCP 配置加载器。"""

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def load_mcp_config(config_path: str) -> dict[str, Any]:
    """加载 JSON 文件中的 ``mcpServers`` 配置映射。

    配置格式为 ``{"mcpServers": {"name": {"command": "...",
    "args": [...], "env": {...}}}}``，其中 ``env`` 可选。
    """
    if not config_path:
        return {}

    path = Path(config_path).expanduser()
    if not path.is_file():
        logger.warning("MCP 配置文件不存在：%s", config_path)
        return {}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("加载 MCP 配置失败：%s", exc)
        return {}

    if not isinstance(data, dict) or not isinstance(data.get("mcpServers", {}), dict):
        logger.warning("MCP 配置格式无效：mcpServers 必须是对象")
        return {}

    servers = data.get("mcpServers", {})
    logger.info("加载了 %d 个 MCP 服务器配置", len(servers))
    return servers
