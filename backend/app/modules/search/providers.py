"""搜索源抽象与实现：DDGS（默认）/ Tavily / SearXNG。

单源失败时由工厂调用方（service）自动降级到 DDGS。
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any

import httpx

from app.core.config import settings
from app.modules.search import urlguard

logger = logging.getLogger(__name__)

SEARCH_TIMEOUT = httpx.Timeout(15.0, connect=10.0)


class SearchProvider(ABC):
    """搜索源基类：返回 [{title, url, snippet}]。"""

    name = "base"

    @abstractmethod
    async def search(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        ...


class DDGSProvider(SearchProvider):
    """DuckDuckGo（ddgs 库），免费无需 Key；同步库用线程包装。"""

    name = "ddgs"

    async def search(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        def _search() -> list[dict[str, Any]]:
            from ddgs import DDGS

            with DDGS() as ddgs:
                return list(ddgs.text(query, max_results=max_results))

        # 部分网络环境下多数引擎超时，偶发整体失败：空结果/异常时重试一次
        try:
            raw = await asyncio.to_thread(_search)
        except Exception:
            logger.warning("DDGS 首次请求失败，准备重试 (query=%r)", query, exc_info=True)
            raw = []
        if not raw:
            await asyncio.sleep(1.0)
            raw = await asyncio.to_thread(_search)
        logger.info("DDGS 原始返回 %d 条 (query=%r)", len(raw), query)
        results = []
        for item in raw:
            url = item.get("href") or item.get("url") or ""
            if not url:
                continue
            results.append(
                {
                    "title": str(item.get("title") or url),
                    "url": url,
                    "snippet": str(item.get("body") or ""),
                }
            )
        return results


class TavilyProvider(SearchProvider):
    """Tavily 搜索 API（https://api.tavily.com/search）。"""

    name = "tavily"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    async def search(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"query": query, "max_results": max_results},
            )
            resp.raise_for_status()
            data = resp.json()
        results = []
        for item in data.get("results") or []:
            url = item.get("url") or ""
            if not url:
                continue
            results.append(
                {
                    "title": str(item.get("title") or url),
                    "url": url,
                    "snippet": str(item.get("content") or ""),
                }
            )
        return results


class SearXNGProvider(SearchProvider):
    """自建 SearXNG 实例（需开启 JSON 输出）。"""

    name = "searxng"

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")

    async def search(self, query: str, max_results: int = 5) -> list[dict[str, str]]:
        # SSRF 防护：即使绕过设置接口直接写库，请求前也要再校验一次
        error = await urlguard.validate_public_url_async(
            self.base_url, allow_private=settings.allow_private_searxng
        )
        if error:
            raise ValueError(f"SearXNG URL 校验未通过: {error}")
        async with httpx.AsyncClient(
            timeout=SEARCH_TIMEOUT, max_redirects=3
        ) as client:
            resp = await client.get(
                f"{self.base_url}/search",
                params={"q": query, "format": "json"},
            )
            resp.raise_for_status()
            data = resp.json()
        results = []
        for item in (data.get("results") or [])[:max_results]:
            url = item.get("url") or ""
            if not url:
                continue
            results.append(
                {
                    "title": str(item.get("title") or url),
                    "url": url,
                    "snippet": str(item.get("content") or ""),
                }
            )
        return results


def build_provider(
    provider_name: str,
    *,
    tavily_api_key: str | None = None,
    searxng_url: str | None = None,
) -> SearchProvider:
    """按配置构造搜索源；配置不完整时回退 DDGS。"""
    if provider_name == "tavily" and tavily_api_key:
        return TavilyProvider(tavily_api_key)
    if provider_name == "searxng" and searxng_url:
        return SearXNGProvider(searxng_url)
    return DDGSProvider()
