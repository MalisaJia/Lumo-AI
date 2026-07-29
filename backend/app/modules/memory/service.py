"""长期记忆：开关设置、CRUD 与上下文组装。

- 设置存 settings KV 表（复用 search 设置的读写模式）
- build_memory_context 按关键词重合度 + 时新性挑选记忆，组装 system 提示块
"""

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Memory
from app.modules.search.service import _get_setting, _set_setting

logger = logging.getLogger(__name__)

# settings 表中的键名；值 "true"/"false"，缺省视为开启
KEY_MEMORY_ENABLED = "memory_enabled"

# 上下文组装参数：候选上限 / 选中条数上限 / 累计字数上限
CONTEXT_CANDIDATE_LIMIT = 200
CONTEXT_MAX_ITEMS = 12
CONTEXT_MAX_CHARS = 1500

_TYPE_LABELS = {"fact": "事实", "preference": "偏好", "summary": "摘要"}


# ---------------------------------------------------------------------------
# 开关设置
# ---------------------------------------------------------------------------


async def is_memory_enabled(session: AsyncSession) -> bool:
    """内部使用：仅显式保存 "false" 时关闭，默认开启。"""
    return (await _get_setting(session, KEY_MEMORY_ENABLED)) != "false"


async def get_memory_settings(session: AsyncSession) -> dict[str, Any]:
    return {"enabled": await is_memory_enabled(session)}


async def update_memory_settings(
    session: AsyncSession, *, enabled: bool
) -> dict[str, Any]:
    await _set_setting(session, KEY_MEMORY_ENABLED, "true" if enabled else "false")
    await session.commit()
    return await get_memory_settings(session)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def _parse_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [str(t) for t in parsed]
    except ValueError:
        pass
    return []


def _to_dict(memory: Memory) -> dict[str, Any]:
    """转成响应数据：tags JSON 字符串解析成数组。"""
    return {
        "id": memory.id,
        "memory_type": memory.memory_type,
        "content": memory.content,
        "tags": _parse_tags(memory.tags),
        "source_conversation_id": memory.source_conversation_id,
        "is_enabled": memory.is_enabled,
        "created_at": memory.created_at,
        "updated_at": memory.updated_at,
    }


async def list_memories(
    session: AsyncSession,
    since: datetime | None = None,
    type_: str | None = None,
) -> list[dict[str, Any]]:
    stmt = select(Memory).order_by(Memory.created_at.desc())
    if since is not None:
        # DB 存 naive UTC，带时区的入参先归一
        if since.tzinfo is not None:
            since = since.astimezone(timezone.utc).replace(tzinfo=None)
        stmt = stmt.where(Memory.created_at >= since)
    if type_ is not None:
        stmt = stmt.where(Memory.memory_type == type_)
    result = await session.execute(stmt)
    return [_to_dict(m) for m in result.scalars().all()]


async def create_memory(
    session: AsyncSession,
    *,
    content: str,
    memory_type: str = "fact",
    tags: list[str] | None = None,
    source_conversation_id: str | None = None,
    source_message_id: str | None = None,
) -> dict[str, Any]:
    memory = Memory(
        memory_type=memory_type,
        content=content.strip(),
        tags=json.dumps(tags, ensure_ascii=False) if tags else None,
        source_conversation_id=source_conversation_id,
        source_message_id=source_message_id,
    )
    session.add(memory)
    await session.commit()
    return _to_dict(memory)


async def get_memory(session: AsyncSession, memory_id: str) -> Memory | None:
    result = await session.execute(select(Memory).where(Memory.id == memory_id))
    return result.scalar_one_or_none()


async def update_memory(
    session: AsyncSession,
    memory: Memory,
    *,
    content: str | None = None,
    tags: list[str] | None = None,
    is_enabled: bool | None = None,
) -> dict[str, Any]:
    if content is not None:
        memory.content = content.strip()
    if tags is not None:
        memory.tags = json.dumps(tags, ensure_ascii=False) if tags else None
    if is_enabled is not None:
        memory.is_enabled = is_enabled
    await session.commit()
    return _to_dict(memory)


async def delete_memory(session: AsyncSession, memory: Memory) -> None:
    await session.delete(memory)
    await session.commit()


# ---------------------------------------------------------------------------
# 上下文组装
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> set[str]:
    """简单分词：英文/数字按词切，中文取字符 2-gram（对中文友好）。"""
    text = text.lower()
    tokens = set(re.findall(r"[a-z0-9]+", text))
    han = re.sub(r"[^\u4e00-\u9fff]", "", text)
    tokens.update(han[i : i + 2] for i in range(len(han) - 1))
    return tokens


async def build_memory_context(
    session: AsyncSession, user_message: str
) -> str | None:
    """挑选与当前问题最相关的记忆，组装成中文提示块；无记忆返回 None。"""
    result = await session.execute(
        select(Memory)
        .where(Memory.is_enabled.is_(True), Memory.memory_type != "summary")
        .order_by(Memory.updated_at.desc())
        .limit(CONTEXT_CANDIDATE_LIMIT)
    )
    memories = list(result.scalars().all())
    if not memories:
        return None

    query_tokens = _tokenize(user_message or "")
    scored: list[tuple[float, Memory]] = []
    for rank, m in enumerate(memories):
        overlap = len(query_tokens & _tokenize(m.content + " " + (m.tags or "")))
        # 关键词重合度为主，updated_at 时新性为次（列表已按 updated_at 降序）
        recency = (len(memories) - rank) / len(memories)
        scored.append((overlap * 10 + recency, m))
    scored.sort(key=lambda item: item[0], reverse=True)

    lines: list[str] = []
    total_chars = 0
    for _, m in scored[:CONTEXT_MAX_ITEMS]:
        line = f"- [{_TYPE_LABELS.get(m.memory_type, m.memory_type)}] {m.content}"
        if total_chars + len(line) > CONTEXT_MAX_CHARS:
            break
        lines.append(line)
        total_chars += len(line)
    if not lines:
        return None
    return (
        "以下是你在过往对话中了解到的用户长期信息（按相关性排序），"
        "回答时自然地参考，不要主动提及“记忆”这个机制：\n" + "\n".join(lines)
    )
