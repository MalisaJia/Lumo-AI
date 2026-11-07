"""Agent 间共享上下文板。同一对话内的 agent 可以读写共享信息。"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ContextEntry:
    agent_id: str
    agent_type: str
    key: str
    content: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


class SharedContextBoard:
    """进程级共享上下文板，按 conversation_id 隔离。"""

    def __init__(self):
        self._boards: dict[str, list[ContextEntry]] = {}
        self._lock = asyncio.Lock()

    async def publish(
        self,
        conversation_id: str,
        agent_id: str,
        agent_type: str,
        key: str,
        content: str,
    ):
        """发布一条上下文信息。"""
        async with self._lock:
            entries = self._boards.setdefault(conversation_id, [])
            entries.append(
                ContextEntry(
                    agent_id=agent_id,
                    agent_type=agent_type,
                    key=key,
                    content=content,
                )
            )

    async def read_all(
        self, conversation_id: str, exclude_agent_id: str | None = None
    ) -> list[ContextEntry]:
        """读取对话内所有共享上下文（可排除自己）。"""
        async with self._lock:
            entries = list(self._boards.get(conversation_id, []))
        if exclude_agent_id:
            return [entry for entry in entries if entry.agent_id != exclude_agent_id]
        return entries

    async def read_by_key(
        self, conversation_id: str, key: str
    ) -> list[ContextEntry]:
        """按 key 读取。"""
        async with self._lock:
            return [
                entry
                for entry in self._boards.get(conversation_id, [])
                if entry.key == key
            ]

    async def clear(self, conversation_id: str):
        """清理对话的共享上下文。"""
        async with self._lock:
            self._boards.pop(conversation_id, None)

    def format_for_prompt(self, entries: list[ContextEntry]) -> str:
        """将共享上下文格式化为可注入 prompt 的文本。"""
        if not entries:
            return ""
        parts = []
        for entry in entries:
            parts.append(
                f"[{entry.agent_type}] {entry.key}:\n{entry.content[:1000]}"
            )
        return "\n\n---\n\n".join(parts)


shared_context = SharedContextBoard()
