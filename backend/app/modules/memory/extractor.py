"""对话后的后台记忆提取与长历史压缩（非流式轻量 LLM 调用）。

extract_after_reply 由 chat 路由以 asyncio.create_task 触发：
全程 try/except 仅 logger.warning，绝不影响聊天主链路。
"""

import json
import logging
import re

import httpx
from sqlalchemy import func, select

from app.core.db import async_session_factory
from app.models import Memory, Message
from app.modules.memory import service as memory_service

logger = logging.getLogger(__name__)

# 提取/摘要属后台轻量调用，超时收紧到 15s，失败直接放弃本轮
LLM_TIMEOUT = httpx.Timeout(15.0, connect=5.0)

# 每轮最多入库的新记忆条数
MAX_NEW_MEMORIES = 3
# 提取 prompt 附带的既有记忆条数上限
EXISTING_MEMORIES_LIMIT = 50

# 长历史压缩参数：触发消息数阈值 / 保留最近条数 / 增量触发步长
SUMMARY_THRESHOLD = 60
SUMMARY_KEEP_RECENT = 24
SUMMARY_MIN_DELTA = 20
# 摘要输入限制：单条截断 / 总量上限
SUMMARY_MSG_CHARS = 500
SUMMARY_TOTAL_CHARS = 12000

_EXTRACT_SYSTEM = (
    "你是记忆提取助手。从「用户消息」中提取值得长期记住的用户事实(fact)或偏好(preference)。"
    "只提取关于用户本人的稳定信息（身份、职业、喜好、习惯、长期目标、重要背景），"
    "不提取一次性任务内容、闲聊或常识。"
    "只输出与已有记忆不重复的**新**信息；与已有记忆重复或语义相同的不要输出。"
    '输出严格 JSON 数组：[{"type":"fact|preference","content":"简洁中文一句话","tags":["关键词"]}]，'
    "没有可提取的信息则输出 []。不要输出任何其他文字。"
)

_SUMMARY_SYSTEM = (
    "你是对话摘要助手。把下面的历史对话压缩成不超过 300 字的中文段落，"
    "保留用户的关键信息、已得出的结论和未决事项，不要逐句复述。只输出摘要正文。"
)


async def _llm_complete(
    base_url: str,
    api_key: str,
    model_name: str,
    messages: list[dict[str, str]],
    max_tokens: int = 500,
) -> str | None:
    """非流式调用上游；失败返回 None。"""
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": False,
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
            resp = await client.post(
                f"{base_url}/chat/completions", headers=headers, json=payload
            )
            if resp.status_code >= 400:
                return None
            data = resp.json()
        content = (data.get("choices") or [{}])[0].get("message", {}).get("content")
        return str(content).strip() if content else None
    except (httpx.HTTPError, ValueError, KeyError):
        return None


def _parse_json_array(raw: str | None) -> list[dict]:
    """容错提取 JSON 数组（剥 ```json 围栏、截取首尾方括号）；失败视为 []。"""
    if not raw:
        return []
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        return []
    try:
        parsed = json.loads(text[start : end + 1])
    except ValueError:
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _normalize(text: str) -> str:
    """去重用规范化：去空白/标点、小写。"""
    return re.sub(r"[\s\W_]+", "", text, flags=re.UNICODE).lower()


def _is_duplicate(content: str, existing_normalized: list[str]) -> bool:
    """与既有记忆精确匹配或互相包含即视为重复。"""
    norm = _normalize(content)
    if not norm:
        return True
    return any(norm == e or norm in e or e in norm for e in existing_normalized)


async def _extract_memories(
    session, conversation_id: str, user_message: str,
    base_url: str, api_key: str, model_name: str,
) -> None:
    """LLM 提取新记忆并去重入库（每轮最多 MAX_NEW_MEMORIES 条）。"""
    existing_rows = (
        (
            await session.execute(
                select(Memory)
                .where(Memory.memory_type != "summary")
                .order_by(Memory.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    recent_contents = [m.content for m in existing_rows[:EXISTING_MEMORIES_LIMIT]]
    existing_block = (
        "已有记忆列表：\n" + "\n".join(f"- {c}" for c in recent_contents)
        if recent_contents
        else "已有记忆列表：（空）"
    )
    raw = await _llm_complete(
        base_url,
        api_key,
        model_name,
        [
            {"role": "system", "content": _EXTRACT_SYSTEM},
            {
                "role": "user",
                "content": f"{existing_block}\n\n用户消息：\n{user_message}",
            },
        ],
        max_tokens=500,
    )
    items = _parse_json_array(raw)
    if not items:
        return

    # 服务端二次去重：与现有全部非 summary 记忆比对
    existing_normalized = [_normalize(m.content) for m in existing_rows]
    added = 0
    for item in items:
        if added >= MAX_NEW_MEMORIES:
            break
        content = str(item.get("content") or "").strip()
        if not content or _is_duplicate(content, existing_normalized):
            continue
        memory_type = item.get("type")
        if memory_type not in ("fact", "preference"):
            memory_type = "fact"
        tags_raw = item.get("tags")
        tags = (
            [str(t) for t in tags_raw if str(t).strip()]
            if isinstance(tags_raw, list)
            else None
        )
        await memory_service.create_memory(
            session,
            content=content,
            memory_type=memory_type,
            tags=tags or None,
            source_conversation_id=conversation_id,
            source_message_id=None,
        )
        existing_normalized.append(_normalize(content))
        added += 1
    if added:
        logger.info("记忆提取：新增 %d 条 (conversation=%s)", added, conversation_id)


async def _compress_history(
    session, conversation_id: str,
    base_url: str, api_key: str, model_name: str,
) -> None:
    """长历史压缩：消息数超阈值时把较早消息摘要成 summary 记忆行。"""
    count = (
        await session.execute(
            select(func.count(Message.id)).where(
                Message.conversation_id == conversation_id
            )
        )
    ).scalar_one()
    if count < SUMMARY_THRESHOLD:
        return

    # 与 chat_pipeline 注入侧对齐：只处理启用中的 summary 行；存在多行时
    # （如旧行被停用后新建了一行）取最近更新的一行，避免多行报错
    summary_row = (
        (
            await session.execute(
                select(Memory)
                .where(
                    Memory.source_conversation_id == conversation_id,
                    Memory.memory_type == "summary",
                    Memory.is_enabled.is_(True),
                )
                .order_by(Memory.updated_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    covered = 0
    if summary_row is not None and summary_row.extra:
        try:
            covered = int(json.loads(summary_row.extra).get("coveredCount") or 0)
        except (ValueError, TypeError):
            covered = 0

    target = count - SUMMARY_KEEP_RECENT
    if target < covered + SUMMARY_MIN_DELTA:
        return

    messages = (
        (
            await session.execute(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.created_at.asc(), Message.id.asc())
                .limit(target)
            )
        )
        .scalars()
        .all()
    )
    blocks: list[str] = []
    total = 0
    role_labels = {"user": "用户", "assistant": "助手"}
    for m in messages:
        line = f"{role_labels.get(m.role, m.role)}：{m.content[:SUMMARY_MSG_CHARS]}"
        if total + len(line) > SUMMARY_TOTAL_CHARS:
            break
        blocks.append(line)
        total += len(line)
    if summary_row is not None:
        # 增量摘要：把旧摘要一并交给 LLM 合并
        blocks.insert(0, f"（此前的对话摘要）{summary_row.content}")

    summary_text = await _llm_complete(
        base_url,
        api_key,
        model_name,
        [
            {"role": "system", "content": _SUMMARY_SYSTEM},
            {"role": "user", "content": "\n".join(blocks)},
        ],
        max_tokens=500,
    )
    if not summary_text:
        return

    extra = json.dumps({"coveredCount": target}, ensure_ascii=False)
    if summary_row is None:
        session.add(
            Memory(
                memory_type="summary",
                content=summary_text,
                source_conversation_id=conversation_id,
                extra=extra,
            )
        )
    else:
        summary_row.content = summary_text
        summary_row.extra = extra
    await session.commit()
    logger.info(
        "长历史压缩：conversation=%s coveredCount=%d", conversation_id, target
    )


async def extract_after_reply(
    conversation_id: str,
    user_message: str,
    response_text: str,
    base_url: str | None,
    api_key: str | None,
    model_name: str | None,
) -> None:
    """后台任务入口：记忆提取 + 长历史压缩；任何异常仅记日志。"""
    try:
        if not base_url or not api_key or not model_name:
            return
        async with async_session_factory() as session:
            if not await memory_service.is_memory_enabled(session):
                return
            if len((user_message or "").strip()) >= 4:
                await _extract_memories(
                    session, conversation_id, user_message,
                    base_url, api_key, model_name,
                )
            await _compress_history(
                session, conversation_id, base_url, api_key, model_name
            )
    except Exception:
        logger.warning("后台记忆提取失败（已忽略）", exc_info=True)
