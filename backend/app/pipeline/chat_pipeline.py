"""聊天处理管线：load_history -> select_model -> call_provider(流式) -> persist。

未来的扩展挂载点：
- memory：在 load_history 之后接入长期记忆检索/摘要压缩
- model_router：在 select_model 中按会话配置/负载策略路由到具体 Provider+Model
- skills：在 call_provider 前后插入工具调用（function calling）等技能层
"""

import base64
import io
import json
import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import BACKEND_DIR
from app.core.crypto import decrypt_key
from app.models import Conversation, Memory, Message, Model, Provider
from app.modules.conversations import service as conv_service

logger = logging.getLogger(__name__)

STREAM_TIMEOUT = httpx.Timeout(120.0, connect=15.0)

# 同渠道模型自动路由：可重试的上游 HTTP 状态码（限流/服务端故障）
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
# 可重试失败后的模型冷却时长（秒）
MODEL_COOLDOWN_SECONDS = 60.0
# 模块级内存冷却表 {(provider_id, model_name): 冷却截止时间（time.monotonic）}；
# 进程重启即清零，可接受
_model_cooldowns: dict[tuple[str, str], float] = {}


def _set_cooldown(provider_id: str, model_name: str) -> None:
    _model_cooldowns[(provider_id, model_name)] = (
        time.monotonic() + MODEL_COOLDOWN_SECONDS
    )


def _in_cooldown(provider_id: str, model_name: str) -> bool:
    return _model_cooldowns.get((provider_id, model_name), 0.0) > time.monotonic()


# 发给视觉模型前的图片压缩参数：最长边上限与 JPEG 质量
IMAGE_MAX_SIDE = 1568
IMAGE_JPEG_QUALITY = 85

UPLOAD_DIR = BACKEND_DIR / "uploads"


class PipelineError(Exception):
    """携带人类可读错误说明的管线异常。"""


class RetryableUpstreamError(PipelineError):
    """可重试的上游错误（429/5xx/连接错误/超时），触发同渠道模型自动路由。"""


@dataclass
class ChatContext:
    """贯穿整条管线的上下文对象。"""

    conversation_id: str
    user_message: str = ""
    provider_id: str | None = None
    model_name: str | None = None
    system_prompt: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)
    base_url: str | None = None
    api_key: str | None = None  # 解密后的 Key，仅存在于内存中
    response_text: str = ""
    usage: dict[str, int] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class ChatPipeline:
    """对话管线；子类可覆写单个步骤以定制行为。"""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def load_history(self, ctx: ChatContext) -> ChatContext:
        """加载会话历史消息并组装 OpenAI messages。

        （未来在此之后挂载 memory：长期记忆检索/摘要压缩）
        """
        conversation = await conv_service.get_conversation(
            self.session, ctx.conversation_id
        )
        if conversation is None:
            raise PipelineError("会话不存在")
        ctx.provider_id = ctx.provider_id or conversation.provider_id
        ctx.model_name = ctx.model_name or conversation.model_name
        ctx.system_prompt = conversation.system_prompt

        messages: list[dict[str, Any]] = []
        if ctx.system_prompt:
            messages.append({"role": "system", "content": ctx.system_prompt})
        for m in await conv_service.list_messages(self.session, ctx.conversation_id):
            entry: dict[str, Any] = {"role": m.role, "content": m.content}
            # 图片附件元数据暂存在历史条目上（content 保持纯文本，
            # 搜索管线等只读文本的环节不受影响），发送上游前才转换
            if m.role == "user" and m.attachments:
                try:
                    parsed = json.loads(m.attachments)
                    if isinstance(parsed, list) and parsed:
                        entry["attachments"] = parsed
                except ValueError:
                    pass
            messages.append(entry)

        # 长历史压缩：存在该会话的 summary 记忆时，用一条摘要 system 消息
        # 替代较早的 K 条消息；任何异常/越界都忽略摘要走全量历史
        try:
            # 局部导入避免循环依赖（memory.service -> search.service -> 本模块）
            from app.modules.memory import service as memory_service

            if await memory_service.is_memory_enabled(self.session):
                # 存在多行 summary（旧行被停用后新建）时取最近更新的一行
                summary_row = (
                    (
                        await self.session.execute(
                            select(Memory)
                            .where(
                                Memory.source_conversation_id == ctx.conversation_id,
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
                if summary_row is not None and summary_row.extra:
                    covered = int(
                        json.loads(summary_row.extra).get("coveredCount") or 0
                    )
                    offset = 1 if ctx.system_prompt else 0
                    if 0 < covered <= len(messages) - offset:
                        summary_msg = {
                            "role": "system",
                            "content": (
                                f"早前对话摘要（更早的 {covered} 条消息已压缩）：\n"
                                + summary_row.content
                            ),
                        }
                        messages = (
                            messages[:offset]
                            + [summary_msg]
                            + messages[offset + covered :]
                        )
        except Exception:
            logger.warning("加载会话摘要失败，降级为全量历史", exc_info=True)

        ctx.history = messages
        return ctx

    async def select_model(self, ctx: ChatContext) -> ChatContext:
        """确定本次调用的 Provider 与模型，并解密 Key。

        （未来在此挂载 model_router：按策略路由）
        """
        provider: Provider | None = None
        if ctx.provider_id:
            provider = (
                await self.session.execute(
                    select(Provider).where(Provider.id == ctx.provider_id)
                )
            ).scalar_one_or_none()
        if provider is None:
            # 缺省：默认 Provider，否则第一个
            provider = (
                await self.session.execute(
                    select(Provider)
                    .order_by(Provider.is_default.desc(), Provider.created_at)
                    .limit(1)
                )
            ).scalar_one_or_none()
        if provider is None:
            raise PipelineError("尚未配置任何模型服务商，请先在设置中添加")

        if not ctx.model_name:
            model = (
                await self.session.execute(
                    select(Model)
                    .where(Model.provider_id == provider.id)
                    .order_by(Model.is_default.desc(), Model.created_at)
                    .limit(1)
                )
            ).scalar_one_or_none()
            if model is None:
                raise PipelineError("该服务商下没有可用模型，请先在设置中添加")
            ctx.model_name = model.name

        ctx.provider_id = provider.id
        ctx.base_url = provider.base_url.rstrip("/")
        try:
            ctx.api_key = decrypt_key(provider.encrypted_api_key)
        except Exception as exc:
            raise PipelineError("API Key 解密失败，请重新保存服务商配置") from exc
        return ctx

    # ------------------------------------------------------------------
    # 多模态：把带附件的历史转成 OpenAI 兼容的 messages
    # ------------------------------------------------------------------

    @staticmethod
    def _load_image_data_url(url: str) -> str | None:
        """读取 /uploads/xxx 本地文件，压缩后返回 data URL；失败返回 None。"""
        # 只取文件名，防路径穿越
        file_path = UPLOAD_DIR / Path(url).name
        if not file_path.is_file():
            logger.warning("图片附件文件不存在，跳过：%s", url)
            return None
        raw = file_path.read_bytes()
        suffix = file_path.suffix.lower()
        mime = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".gif": "image/gif",
        }.get(suffix, "image/png")
        data, mime = ChatPipeline._compress_image(raw, mime)
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"

    @staticmethod
    def _compress_image(raw: bytes, mime: str) -> tuple[bytes, str]:
        """缩放到最长边 ≤ IMAGE_MAX_SIDE 并适度压缩；失败降级返原图。

        GIF 取第一帧；带透明通道输出 PNG，否则输出 JPEG。
        """
        try:
            from PIL import Image

            with Image.open(io.BytesIO(raw)) as img:
                img.seek(0)  # GIF/多帧图取第一帧
                img.load()
                width, height = img.size
                longest = max(width, height)
                if longest > IMAGE_MAX_SIDE:
                    scale = IMAGE_MAX_SIDE / longest
                    img = img.resize(
                        (max(int(width * scale), 1), max(int(height * scale), 1)),
                        Image.LANCZOS,
                    )
                has_alpha = img.mode in ("RGBA", "LA", "PA") or (
                    img.mode == "P" and "transparency" in img.info
                )
                buf = io.BytesIO()
                if has_alpha:
                    img.convert("RGBA").save(buf, format="PNG", optimize=True)
                    out_mime = "image/png"
                else:
                    img.convert("RGB").save(
                        buf, format="JPEG", quality=IMAGE_JPEG_QUALITY, optimize=True
                    )
                    out_mime = "image/jpeg"
                return buf.getvalue(), out_mime
        except Exception:
            logger.warning("图片压缩失败，降级发送原图", exc_info=True)
            return raw, mime

    @staticmethod
    def _build_upstream_messages(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """组装发给上游的 messages：仅最新一条带图 user 消息携带真实图片，
        更早轮次退化为纯文本占位，控制 token 消耗。"""
        latest_idx = -1
        for i in range(len(history) - 1, -1, -1):
            if history[i].get("role") == "user" and history[i].get("attachments"):
                latest_idx = i
                break

        messages: list[dict[str, Any]] = []
        for i, m in enumerate(history):
            attachments = m.get("attachments")
            if not attachments:
                messages.append({"role": m["role"], "content": m["content"]})
                continue
            text = str(m.get("content") or "")
            if i != latest_idx:
                # 历史带图消息：退化为文本占位
                messages.append(
                    {"role": m["role"], "content": f"{text}\n[图片]".strip()}
                )
                continue
            parts: list[dict[str, Any]] = [
                # 纯图无文字时用默认提示词兑底
                {"type": "text", "text": text or "请分析这张图片"}
            ]
            for a in attachments:
                data_url = ChatPipeline._load_image_data_url(str(a.get("url") or ""))
                if data_url:
                    parts.append(
                        {"type": "image_url", "image_url": {"url": data_url}}
                    )
            if len(parts) == 1:
                # 图片全部丢失：退化为纯文本
                messages.append({"role": m["role"], "content": parts[0]["text"]})
            else:
                messages.append({"role": m["role"], "content": parts})
        return messages

    async def call_provider(self, ctx: ChatContext) -> AsyncGenerator[str, None]:
        """流式调用上游 chat/completions，逐段产出增量文本。

        （未来在此前后挂载 skills：工具调用/function calling）
        产出的每个 chunk 会同步累积到 ctx.response_text；usage 写入 ctx.usage。
        """
        payload = {
            "model": ctx.model_name,
            "messages": self._build_upstream_messages(ctx.history),
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {ctx.api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=STREAM_TIMEOUT) as client:
                async with client.stream(
                    "POST",
                    f"{ctx.base_url}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as resp:
                    if resp.status_code >= 400:
                        body = await resp.aread()
                        summary = self._summarize_error(resp.status_code, body, ctx)
                        # 429/5xx 视为可重试；401/403/400/404 等直接报错
                        if resp.status_code in RETRYABLE_STATUS_CODES:
                            raise RetryableUpstreamError(summary)
                        raise PipelineError(summary)
                    async for line in resp.aiter_lines():
                        line = line.strip()
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            break
                        try:
                            event = json.loads(data)
                        except ValueError:
                            continue
                        usage = event.get("usage")
                        if isinstance(usage, dict):
                            ctx.usage = {
                                "promptTokens": int(usage.get("prompt_tokens") or 0),
                                "completionTokens": int(
                                    usage.get("completion_tokens") or 0
                                ),
                            }
                        choices = event.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta") or {}
                        content = delta.get("content")
                        if content:
                            ctx.response_text += content
                            yield content
        except PipelineError:
            raise
        except httpx.TimeoutException as exc:
            raise RetryableUpstreamError("连接上游模型服务超时") from exc
        except httpx.HTTPError as exc:
            raise RetryableUpstreamError(
                f"网络错误：无法连接上游模型服务（{exc.__class__.__name__}）"
            ) from exc

    # ------------------------------------------------------------------
    # 同渠道模型自动路由（故障转移）
    # ------------------------------------------------------------------

    async def _routing_candidates(self, ctx: ChatContext) -> list[str]:
        """路由候选模型：当前选定模型优先，其余按默认优先+创建顺序；
        跳过冷却中的模型，若全部在冷却中则忽略冷却（保证有模型可用）。"""
        models = (
            (
                await self.session.execute(
                    select(Model)
                    .where(Model.provider_id == ctx.provider_id)
                    .order_by(Model.is_default.desc(), Model.created_at)
                )
            )
            .scalars()
            .all()
        )
        names = [m.name for m in models]
        if ctx.model_name:
            if ctx.model_name in names:
                names.remove(ctx.model_name)
            names.insert(0, ctx.model_name)
        provider_id = ctx.provider_id or ""
        available = [n for n in names if not _in_cooldown(provider_id, n)]
        return available or names

    async def call_provider_routed(
        self, ctx: ChatContext, enabled: bool = True
    ) -> AsyncGenerator[dict[str, Any], None]:
        """带同渠道自动路由的流式调用，产出事件 dict：
        - {"type": "chunk", "content": 增量文本}
        - {"type": "modelSwitch", "from": 旧模型, "to": 新模型}（实际切换时才发）

        enabled=False 时完全等价于单模型 call_provider 行为。
        可重试错误仅在尚未产出任何 chunk 时触发切换；已输出过内容维持报错。
        """
        if not enabled:
            async for chunk in self.call_provider(ctx):
                yield {"type": "chunk", "content": chunk}
            return

        candidates = await self._routing_candidates(ctx)
        last_error: RetryableUpstreamError | None = None
        failed_model: str | None = None
        for model_name in candidates:
            ctx.model_name = model_name
            announced = False
            try:
                async for chunk in self.call_provider(ctx):
                    if failed_model is not None and not announced:
                        # 新模型成功产出内容才宣告切换，连续失败时不误报
                        yield {
                            "type": "modelSwitch",
                            "from": failed_model,
                            "to": model_name,
                        }
                        announced = True
                    yield {"type": "chunk", "content": chunk}
                return
            except RetryableUpstreamError as exc:
                if ctx.response_text:
                    # 已向客户端输出过内容：不再切换，维持现有报错行为
                    raise
                if ctx.provider_id:
                    _set_cooldown(ctx.provider_id, model_name)
                logger.warning(
                    "模型 %s 调用失败（%s），尝试同渠道自动路由", model_name, exc
                )
                last_error = exc
                failed_model = model_name
        raise PipelineError(
            f"已尝试 {len(candidates)} 个模型，均不可用；最后错误：{last_error}"
        )

    @staticmethod
    def _summarize_error(status: int, body: bytes, ctx: ChatContext) -> str:
        """从上游错误响应中提取 message 摘要；绝不暴露 Key。"""
        message = ""
        try:
            data = json.loads(body.decode("utf-8", errors="replace"))
            err = data.get("error") if isinstance(data, dict) else None
            if isinstance(err, dict):
                message = str(err.get("message") or "")
            elif isinstance(err, str):
                message = err
            elif isinstance(data, dict):
                message = str(data.get("message") or data.get("detail") or "")
        except ValueError:
            message = body.decode("utf-8", errors="replace")[:200]
        if ctx.api_key:
            message = message.replace(ctx.api_key, "***")
        message = message.strip()[:300]
        return f"上游服务返回错误（HTTP {status}）" + (f"：{message}" if message else "")

    async def persist(self, ctx: ChatContext) -> Message | None:
        """持久化模型回复（含 tokenCount 与搜索 sources），并刷新会话 updatedAt。"""
        if not ctx.response_text:
            return None
        completion_tokens = (
            ctx.usage.get("completionTokens") if ctx.usage else None
        )
        # 联网搜索来源：只存 id/title/url；无搜索则 NULL
        sources = ctx.extra.get("sources")
        sources_json = (
            json.dumps(
                [{"id": s["id"], "title": s["title"], "url": s["url"]} for s in sources],
                ensure_ascii=False,
            )
            if sources
            else None
        )
        message = Message(
            conversation_id=ctx.conversation_id,
            role="assistant",
            content=ctx.response_text,
            token_count=completion_tokens,
            sources=sources_json,
        )
        self.session.add(message)
        conversation = await conv_service.get_conversation(
            self.session, ctx.conversation_id
        )
        if conversation is not None:
            conversation.updated_at = conv_service._now()
            # 首条消息生成后：仍为默认标题则用 user 内容前 20 字符命名
            if conversation.title == "新对话" and ctx.user_message:
                conversation.title = ctx.user_message[:20]
        await self.session.commit()
        return message

    async def run(self, ctx: ChatContext) -> ChatContext:
        """非流式便捷入口：按顺序执行全部步骤并聚合完整回复。"""
        ctx = await self.load_history(ctx)
        ctx = await self.select_model(ctx)
        async for _ in self.call_provider(ctx):
            pass
        await self.persist(ctx)
        return ctx
