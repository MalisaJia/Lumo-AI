"""web_search 工具：复用现有联网搜索链路（检索 + 抓取 + 上下文组装）。

工具自建 DB session（async_session_factory），不与管线共享；
精简来源写入 ctx.extra["sources"]，复用现有 persist/sources 链路。
"""

import logging
from typing import Any

from app.core.db import async_session_factory
from app.modules.search import fetcher
from app.modules.search import service as search_service
from app.modules.tools.registry import tool

logger = logging.getLogger(__name__)


@tool(
    name="web_search",
    description=(
        "联网搜索实时信息（新闻、时效数据、你不了解的事实等）。"
        "需要获取互联网上的最新内容时调用。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词，尽量具体明确",
            }
        },
        "required": ["query"],
    },
    timeout=30.0,
)
async def web_search(ctx: Any, arguments: dict[str, Any]) -> str:
    query = str(arguments.get("query") or "").strip()
    if not query:
        return "联网搜索失败：搜索关键词为空。"

    try:
        async with async_session_factory() as session:
            results = await search_service.run_search(session, ctx.user_id, query)
        if not results:
            return f"联网搜索「{query}」未找到相关结果，请结合自身知识回答。"
        sources = await fetcher.fetch_contents(results)
        if not sources:
            return f"联网搜索「{query}」抓取正文失败，请结合自身知识回答。"
    except Exception as exc:
        logger.warning("web_search 工具执行失败 (query=%r)：%s", query, exc, exc_info=True)
        return f"联网搜索失败：{exc.__class__.__name__}。请结合自身知识回答。"

    # 精简来源写入 extra，复用现有 persist/sources 链路（前端来源徽标）
    ctx.extra["sources"] = [
        {"id": s["id"], "title": s["title"], "url": s["url"]} for s in sources
    ]
    return search_service.build_search_context(sources)
