"""上下文窗口管理器 — token 预算追踪与自动压缩。"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


def estimate_tokens(text: str) -> int:
    """粗略估算文本 token 数：英文约 4 字符/token，非 ASCII 约 1.5 token/字符。"""
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    cjk_chars = len(text) - ascii_chars
    return (ascii_chars // 4) + int(cjk_chars * 1.5)


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """估算 OpenAI messages 列表的 token 数，包含每条消息的结构开销。"""
    total = 0
    for message in messages:
        content = message.get("content", "")
        if isinstance(content, str):
            total += estimate_tokens(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    total += estimate_tokens(part["text"])
        total += 4
    return total


@dataclass
class ContextBudget:
    """单次 Agent 运行使用的上下文预算。"""

    max_tokens: int = 128000
    compress_threshold: float = 0.8
    keep_recent: int = 10


class ContextManager:
    """跟踪消息预算，并在接近上下文上限时压缩较早历史。"""

    def __init__(self, budget: ContextBudget | None = None):
        self.budget = budget or ContextBudget()
        self.compressed_summary: str | None = None

    def estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """返回消息列表的近似 token 数。"""
        return estimate_messages_tokens(messages)

    def should_compress(self, messages: list[dict[str, Any]]) -> bool:
        tokens = self.estimate_tokens(messages)
        threshold = int(self.budget.max_tokens * self.budget.compress_threshold)
        return tokens > threshold

    async def compress(
        self,
        messages: list[dict[str, Any]],
        call_llm: Callable[[list[dict[str, str]]], Awaitable[str]],
    ) -> list[dict[str, Any]]:
        """压缩历史消息，保留首条 system 指令和最近 keep_recent 条消息。"""
        prefix: list[dict[str, Any]] = []
        body = messages
        if messages and messages[0].get("role") == "system":
            prefix = messages[:1]
            body = messages[1:]

        keep_recent = max(self.budget.keep_recent, 0)
        if len(body) <= keep_recent:
            return messages

        split_at = len(body) - keep_recent if keep_recent else len(body)
        # 不从 tool 消息中间切断，确保保留与其配对的 assistant tool_calls。
        while 0 < split_at < len(body) and body[split_at].get("role") == "tool":
            split_at -= 1
        old_messages = body[:split_at]
        recent_messages = body[split_at:]
        if not old_messages:
            return messages

        summary_prompt = [
            {
                "role": "system",
                "content": "请将以下对话历史压缩为简洁的摘要，保留关键信息、决策和代码变更。用中文回复。",
            },
            {
                "role": "user",
                "content": self._format_messages_for_summary(old_messages),
            },
        ]

        try:
            summary = (await call_llm(summary_prompt)).strip()
            if not summary:
                raise ValueError("上游未返回摘要内容")
            self.compressed_summary = summary
            logger.info(
                "Context compressed: %d messages → summary (%d tokens)",
                len(old_messages),
                estimate_tokens(summary),
            )
            return [
                *prefix,
                {"role": "system", "content": f"[对话历史摘要]\n{summary}"},
                *recent_messages,
            ]
        except Exception as exc:
            logger.warning("Context compression failed: %s", exc)
            return messages

    def _format_messages_for_summary(self, messages: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for message in messages:
            role = message.get("role", "unknown")
            content = message.get("content", "")
            if isinstance(content, str):
                parts.append(f"{role}: {content[:2000]}")
            elif isinstance(content, list):
                text_parts = [
                    str(part.get("text", ""))
                    for part in content
                    if isinstance(part, dict) and part.get("text")
                ]
                if text_parts:
                    parts.append(f"{role}: {' '.join(text_parts)[:2000]}")
        return "\n\n".join(parts)
