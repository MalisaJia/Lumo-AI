"""搜索词改写与轻量 LLM 判定调用（非流式、小 max_tokens）。"""

import json
import logging

import httpx

from app.pipeline.chat_pipeline import ChatContext

logger = logging.getLogger(__name__)

# 判定/改写属轻量调用，超时收紧到 10s，失败时由调用方回退（默认搜索/原查询）
LLM_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

_REWRITE_SYSTEM = (
    "你是搜索查询优化助手。把用户的问题改写成 1 个最适合搜索引擎的查询词。"
    "只输出查询词本身，不要任何解释、引号或标点包裹。"
    "中文问题可以混合关键的英文术语以提升检索质量。"
)


async def llm_complete(
    ctx: ChatContext, messages: list[dict[str, str]], max_tokens: int = 60
) -> str | None:
    """用当前会话的 Provider/模型做一次非流式调用；失败返回 None。"""
    payload = {
        "model": ctx.model_name,
        "messages": messages,
        "stream": False,
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    headers = {
        "Authorization": f"Bearer {ctx.api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            resp = await client.post(
                f"{ctx.base_url}/chat/completions", headers=headers, json=payload
            )
            if resp.status_code >= 400:
                return None
            data = resp.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
        return str(content).strip() if content else None
    except (httpx.HTTPError, ValueError, KeyError, json.JSONDecodeError):
        return None


async def rewrite_query(ctx: ChatContext, question: str) -> str:
    """将用户问题改写为搜索词；失败降级用原问题。"""
    result = await llm_complete(
        ctx,
        [
            {"role": "system", "content": _REWRITE_SYSTEM},
            {"role": "user", "content": question},
        ],
        max_tokens=60,
    )
    if not result:
        logger.warning("搜索词改写失败，降级用原问题 (question=%r)", question)
        return question
    # 防御：剥除引号/多行时取第一行
    query = result.splitlines()[0].strip().strip('"\u201c\u201d')
    logger.info("搜索词改写: %r -> %r", question, query or question)
    return query or question
