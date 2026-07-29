"""联网搜索编排：LLM 判定 → 改写 → 搜索 → 抓取 → 组装 sources。

run_search_pipeline 以异步生成器产出阶段事件，供 chat 路由转成 SSE：
- {"type": "status", "stage": "searching" | "reading"}
- {"type": "notice", "reason": "skipped" | "noResults"}（跳过/空结果，结束事件）
- {"type": "result", "sources": [{id,title,url,snippet,content}]}（结束事件）
"""

import logging
from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_key, encrypt_key, mask_key
from app.models import Setting
from app.modules.search import fetcher, rewriter
from app.modules.search.providers import DDGSProvider, build_provider
from app.pipeline.chat_pipeline import ChatContext

logger = logging.getLogger(__name__)

SEARCH_MAX_RESULTS = 5

# settings 表中的键名
KEY_PROVIDER = "search_provider"
KEY_TAVILY_KEY = "search_tavily_key"  # AESGCM 加密存储
KEY_SEARXNG_URL = "search_searxng_url"

_JUDGE_SYSTEM = (
    "判断回答用户的问题是否需要检索互联网上的实时或外部信息"
    "（如新闻、时效数据、具体事实、你可能不了解的内容）。"
    "只输出 YES 或 NO，不要输出其他任何内容。"
)


# ---------------------------------------------------------------------------
# 设置存取（key-value）
# ---------------------------------------------------------------------------


async def _get_setting(
    session: AsyncSession, user_id: str, key: str
) -> str | None:
    # settings 主键已是 (user_id, key) 复合键，读取必须双条件
    result = await session.execute(
        select(Setting).where(Setting.user_id == user_id, Setting.key == key)
    )
    setting = result.scalar_one_or_none()
    return setting.value if setting else None


async def _set_setting(
    session: AsyncSession, user_id: str, key: str, value: str | None
) -> None:
    result = await session.execute(
        select(Setting).where(Setting.user_id == user_id, Setting.key == key)
    )
    setting = result.scalar_one_or_none()
    if setting is None:
        session.add(Setting(user_id=user_id, key=key, value=value))
    else:
        setting.value = value


async def get_search_settings(session: AsyncSession, user_id: str) -> dict[str, Any]:
    """GET 响应数据：Tavily Key 只给脱敏形式。"""
    provider = await _get_setting(session, user_id, KEY_PROVIDER) or "ddgs"
    encrypted = await _get_setting(session, user_id, KEY_TAVILY_KEY)
    masked: str | None = None
    if encrypted:
        try:
            masked = mask_key(decrypt_key(encrypted))
        except Exception:
            masked = "****"
    return {
        "search_provider": provider,
        "tavily_masked_key": masked,
        "searxng_url": await _get_setting(session, user_id, KEY_SEARXNG_URL),
    }


async def update_search_settings(
    session: AsyncSession,
    user_id: str,
    *,
    search_provider: str | None,
    tavily_api_key: str | None,
    searxng_url: str | None,
) -> dict[str, Any]:
    """PUT：tavilyApiKey 不传则保留原 Key；写入前 AESGCM 加密。"""
    if search_provider is not None:
        await _set_setting(session, user_id, KEY_PROVIDER, search_provider)
    if tavily_api_key is not None:
        await _set_setting(
            session, user_id, KEY_TAVILY_KEY, encrypt_key(tavily_api_key)
        )
    if searxng_url is not None:
        await _set_setting(
            session, user_id, KEY_SEARXNG_URL, searxng_url.strip() or None
        )
    await session.commit()
    return await get_search_settings(session, user_id)


async def _load_search_config(
    session: AsyncSession, user_id: str
) -> dict[str, str | None]:
    """内部使用：解密后的完整搜索配置。"""
    tavily_key: str | None = None
    encrypted = await _get_setting(session, user_id, KEY_TAVILY_KEY)
    if encrypted:
        try:
            tavily_key = decrypt_key(encrypted)
        except Exception:
            tavily_key = None
    return {
        "provider": await _get_setting(session, user_id, KEY_PROVIDER) or "ddgs",
        "tavily_key": tavily_key,
        "searxng_url": await _get_setting(session, user_id, KEY_SEARXNG_URL),
    }


# ---------------------------------------------------------------------------
# 搜索管线
# ---------------------------------------------------------------------------


async def should_search(ctx: ChatContext, question: str) -> bool:
    """LLM 判定是否需要联网搜索；调用失败默认需要（YES）。"""
    answer = await rewriter.llm_complete(
        ctx,
        [
            {"role": "system", "content": _JUDGE_SYSTEM},
            {"role": "user", "content": question},
        ],
        max_tokens=5,
    )
    if not answer:
        logger.warning("搜索判定 LLM 调用失败，默认需要搜索")
        return True
    needed = "NO" not in answer.upper()
    logger.info("搜索判定: %s (raw=%r)", "需要" if needed else "不需要", answer)
    return needed


async def run_search(
    session: AsyncSession,
    user_id: str,
    query: str,
    max_results: int = SEARCH_MAX_RESULTS,
) -> list[dict[str, str]]:
    """按配置的搜索源检索；失败或无结果时自动降级到 DDGS。"""
    config = await _load_search_config(session, user_id)
    provider = build_provider(
        config["provider"] or "ddgs",
        tavily_api_key=config["tavily_key"],
        searxng_url=config["searxng_url"],
    )
    try:
        results = await provider.search(query, max_results)
        logger.info("搜索源 %s 返回 %d 条 (query=%r)", provider.name, len(results), query)
    except Exception:
        logger.warning("搜索源 %s 调用失败 (query=%r)", provider.name, query, exc_info=True)
        results = []
    if not results and provider.name != "ddgs":
        logger.info("降级到 DDGS 重试 (query=%r)", query)
        try:
            results = await DDGSProvider().search(query, max_results)
            logger.info("DDGS 降级返回 %d 条 (query=%r)", len(results), query)
        except Exception:
            logger.warning("DDGS 降级也失败 (query=%r)", query, exc_info=True)
            results = []
    return results


def build_search_context(sources: list[dict[str, Any]]) -> str:
    """把 sources 组装成注入本次上下文的 system 消息内容。"""
    blocks = []
    for s in sources:
        blocks.append(
            f"[{s['id']}] {s['title']}\nURL: {s['url']}\n内容：{s['content']}"
        )
    joined = "\n\n".join(blocks)
    return (
        "以下是针对用户最新问题的联网搜索结果，供回答时参考：\n\n"
        f"{joined}\n\n"
        "回答要求：回答中用 [1][2] 形式行内引用对应编号的来源；"
        "与问题不相关的来源不要引用；若来源信息不足，结合自身知识作答即可。"
    )


async def run_search_pipeline(
    session: AsyncSession, ctx: ChatContext, question: str
) -> AsyncGenerator[dict[str, Any], None]:
    """完整编排；判定不需要搜索/空结果时以 notice 事件结束。"""
    # 先产出 searching 状态再做判定 LLM 调用，让前端立刻展示搜索提示
    yield {"type": "status", "stage": "searching"}
    if not await should_search(ctx, question):
        yield {"type": "notice", "reason": "skipped"}
        return
    query = await rewriter.rewrite_query(ctx, question)
    results = await run_search(session, ctx.user_id, query)
    if not results:
        logger.warning("搜索链路最终无可用结果 (question=%r, query=%r)", question, query)
        yield {"type": "notice", "reason": "noResults"}
        return
    yield {"type": "status", "stage": "reading"}
    sources = await fetcher.fetch_contents(results)
    yield {"type": "result", "sources": sources}
