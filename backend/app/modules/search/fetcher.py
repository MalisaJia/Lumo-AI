"""网页正文抓取：并行抓取搜索结果 URL，trafilatura 提取正文。

单页超时 8s；抓取/提取失败降级用搜索 snippet。
"""

import asyncio
import logging
import re

import httpx

from app.modules.search import urlguard

logger = logging.getLogger(__name__)

FETCH_TIMEOUT = httpx.Timeout(8.0, connect=5.0)
MAX_CONTENT_CHARS = 1500  # 单条正文注入上限
FETCH_TOP_N = 3  # 只抓取前 N 条结果的正文

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )
}


def _clean_text(text: str) -> str:
    """压缩连续空白行/空格并截断。"""
    text = re.sub(r"[ \t\u3000]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:MAX_CONTENT_CHARS]


async def _fetch_one(client: httpx.AsyncClient, url: str) -> str | None:
    """抓取单页并提取正文；任何失败返回 None（由调用方降级 snippet）。"""
    # SSRF 防护：搜索结果 URL 一律拒绝非公网地址（无例外）
    error = await urlguard.validate_public_url_async(url)
    if error:
        logger.warning("SSRF 防护拦截抓取 (url=%s): %s", url, error)
        return None
    try:
        resp = await client.get(url, headers=_HEADERS, follow_redirects=True)
        if resp.status_code >= 400:
            return None
        content_type = resp.headers.get("content-type", "")
        if "html" not in content_type and "xml" not in content_type:
            return None
        html = resp.text
    except Exception:
        return None

    def _extract() -> str | None:
        import trafilatura

        return trafilatura.extract(html, include_comments=False, include_tables=False)

    try:
        text = await asyncio.to_thread(_extract)
    except Exception:
        return None
    if not text:
        return None
    return _clean_text(text)


async def fetch_contents(results: list[dict[str, str]]) -> list[dict[str, str]]:
    """并行抓取 top-N 结果正文，组装编号 sources 列表。

    返回 [{id, title, url, snippet, content}]；content 失败时降级为 snippet。
    """
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT, max_redirects=3) as client:
        texts = await asyncio.gather(
            *(_fetch_one(client, r["url"]) for r in results[:FETCH_TOP_N]),
            return_exceptions=True,
        )

    sources: list[dict[str, str]] = []
    for i, result in enumerate(results):
        text = texts[i] if i < len(texts) else None
        content = text if isinstance(text, str) and text else result.get("snippet", "")
        if i < len(texts) and not (isinstance(text, str) and text):
            logger.info("正文抓取失败降级 snippet (url=%s)", result["url"])
        sources.append(
            {
                "id": i + 1,
                "title": result["title"],
                "url": result["url"],
                "snippet": result.get("snippet", ""),
                "content": content,
            }
        )
    return sources
