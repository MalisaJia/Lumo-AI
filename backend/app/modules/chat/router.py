import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from contextlib import aclosing
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user_id
from app.core.config import AgentConfig
from app.core.db import async_session_factory, get_session
from app.models import Message
from app.modules.agents.events import AgentEvent, event_bus
from app.modules.conversations import service as conv_service
from app.modules.memory import extractor as memory_extractor
from app.modules.memory import service as memory_service
from app.modules.routing import service as routing_service
from app.modules.search import service as search_service
from app.modules.tools import executor as tools_executor
from app.modules.tools import get_registry, service as tools_service
from app.modules.tools.agent_profiles import get_default_profile, get_profile
from app.pipeline.chat_pipeline import ChatContext, ChatPipeline, PipelineError
from app.schemas import ChatStreamRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])
computer_use_router = APIRouter(tags=["computer-use"])


def _sse(payload: dict) -> str:
    """一行 SSE 事件：data: 开头、双换行结尾。"""
    return f"data:{json.dumps(payload, ensure_ascii=False)}\n\n"


async def _merge_agent_events(
    stream: AsyncGenerator[dict[str, Any], None],
    event_queue: asyncio.Queue,
) -> AsyncGenerator[dict[str, Any], None]:
    """Merge tool-loop output and conversation-scoped AgentEventBus events."""
    stream_task: asyncio.Task | None = asyncio.create_task(stream.__anext__())
    event_task: asyncio.Task | None = asyncio.create_task(event_queue.get())
    try:
        while stream_task is not None:
            wait_set = {stream_task}
            if event_task is not None:
                wait_set.add(event_task)
            done, _ = await asyncio.wait(
                wait_set, return_when=asyncio.FIRST_COMPLETED
            )

            if event_task is not None and event_task in done:
                agent_event: AgentEvent = event_task.result()
                if agent_event.type == "__close__":
                    return
                yield {"type": agent_event.type, **agent_event.data}
                event_task = asyncio.create_task(event_queue.get())

            if stream_task in done:
                try:
                    yield stream_task.result()
                except StopAsyncIteration:
                    stream_task = None
                    await asyncio.sleep(0)
                    if event_task is not None and event_task.done():
                        agent_event = event_task.result()
                        if agent_event.type != "__close__":
                            yield {"type": agent_event.type, **agent_event.data}
                        event_task = None
                    while True:
                        try:
                            agent_event = event_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                        if agent_event.type != "__close__":
                            yield {"type": agent_event.type, **agent_event.data}
                else:
                    stream_task = asyncio.create_task(stream.__anext__())
    finally:
        pending = [task for task in (stream_task, event_task) if task is not None]
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)
        try:
            await stream.aclose()
        except Exception:
            logger.exception("Failed to close merged upstream stream")


async def _persist_safely(pipeline: ChatPipeline, ctx: ChatContext) -> Any:
    """Persist a partial reply without hiding the original stream failure."""
    try:
        return await pipeline.persist(ctx)
    except Exception:
        logger.exception(
            "Failed to persist chat reply: conversation_id=%s",
            ctx.conversation_id,
        )
        try:
            await pipeline.session.rollback()
        except Exception:
            logger.exception(
                "Failed to roll back chat session: conversation_id=%s",
                ctx.conversation_id,
            )
        return None


def _fallback_usage(ctx: ChatContext) -> dict[str, int]:
    """上游未返回 usage 时的粗略估算（约 4 字符/`token`）。"""
    prompt_chars = sum(len(str(m.get("content", ""))) for m in ctx.history)
    return {
        "promptTokens": max(prompt_chars // 4, 1),
        "completionTokens": max(len(ctx.response_text) // 4, 1),
    }


@router.post("/stream")
async def chat_stream(
    body: ChatStreamRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
    user_id: str = Depends(get_current_user_id),
):
    # 归属校验：他人 conversation_id 查不到即 404
    conversation = await conv_service.get_conversation(
        session, body.conversation_id, user_id
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    # 有图片附件时允许 content 为空（纯图提问）
    if (
        not body.regenerate
        and not (body.content or "").strip()
        and not body.attachments
    ):
        raise HTTPException(status_code=422, detail="content 不能为空")

    # content/attachments 有值：先落库 user 消息再生成；regenerate 则直接以现有历史生成
    if (body.content or body.attachments) and not body.regenerate:
        attachments_json = (
            json.dumps(
                [
                    {
                        "id": a.id,
                        "url": a.url,
                        "fileName": a.file_name or "",
                        "mimeType": a.mime_type or "",
                    }
                    for a in body.attachments
                ],
                ensure_ascii=False,
            )
            if body.attachments
            else None
        )
        session.add(
            Message(
                conversation_id=conversation.id,
                role="user",
                content=body.content or "",
                attachments=attachments_json,
            )
        )
        conversation.updated_at = conv_service._now()
        await session.commit()

    user_content = body.content or ""
    conversation_id = body.conversation_id
    enable_search = body.enable_search
    agent_profile = (
        get_profile(conversation.agent_type or "") or get_default_profile()
    )
    agent_config = AgentConfig(
        allowed_tools=list(agent_profile.recommended_tools),
        workspace_dir=conversation.workspace_dir,
    )

    async def event_stream() -> AsyncGenerator[str, None]:
        # StreamingResponse 生命周期长于 Depends 会话，这里独立开一个；
        # 自建 session 不携带请求上下文，user_id 必须显式传入 ChatContext
        async with async_session_factory() as stream_session:
            pipeline = ChatPipeline(stream_session)
            ctx = ChatContext(
                conversation_id=conversation_id,
                user_id=user_id,
                user_message=user_content,
            )
            event_queue = event_bus.subscribe(conversation_id, replace=True)
            try:
                await pipeline.load_history(ctx)
                if not ctx.user_message:
                    # regenerate：用历史中最后一条 user 消息做标题兜底
                    for m in reversed(ctx.history):
                        if m.get("role") == "user":
                            ctx.user_message = str(m.get("content", ""))
                            break
                
                # 长期记忆：开启时把相关记忆作为 system 消息注入本次上下文（不持久化）
                try:
                    if await memory_service.is_memory_enabled(
                        stream_session, user_id
                    ):
                        memory_block = await memory_service.build_memory_context(
                            stream_session, user_id, ctx.user_message
                        )
                        if memory_block:
                            idx = (
                                1
                                if ctx.history
                                and ctx.history[0].get("role") == "system"
                                else 0
                            )
                            ctx.history.insert(
                                idx, {"role": "system", "content": memory_block}
                            )
                except Exception:
                    logger.warning("记忆注入失败，本轮不带记忆上下文", exc_info=True)
                
                await pipeline.select_model(ctx)

                # 智能选模命中：告知前端实际使用的模型与任务类型
                if ctx.extra.get("autoModel"):
                    yield _sse(
                        {
                            "type": "autoModel",
                            "model": ctx.extra["autoModel"]["model"],
                            "taskType": ctx.extra["autoModel"]["taskType"],
                        }
                    )

                # 联网搜索：仅开启时产出 status/sources/searchNotice 事件，
                # 未开启时事件序列与之前完全一致
                if enable_search and ctx.user_message:
                    async for event in search_service.run_search_pipeline(
                        stream_session, ctx, ctx.user_message
                    ):
                        if event["type"] == "status":
                            yield _sse(event)
                        elif event["type"] == "notice":
                            # 判定跳过/搜索无结果：告知前端降级原因
                            yield _sse(
                                {"type": "searchNotice", "reason": event["reason"]}
                            )
                        elif event["type"] == "result" and event["sources"]:
                            sources = event["sources"]
                            ctx.extra["sources"] = sources
                            yield _sse(
                                {
                                    "type": "sources",
                                    "sources": [
                                        {
                                            "id": s["id"],
                                            "title": s["title"],
                                            "url": s["url"],
                                        }
                                        for s in sources
                                    ],
                                }
                            )
                            # 搜索结果作为 system 消息注入本次上下文（不持久化）
                            ctx.history.append(
                                {
                                    "role": "system",
                                    "content": search_service.build_search_context(
                                        sources
                                    ),
                                }
                            )

                disconnected = False
                # 同渠道模型自动路由：开关关闭时完全等价于单模型行为
                auto_routing = await routing_service.is_auto_routing_enabled(
                    stream_session, user_id
                )
                # Agent 工具：开关开启且非 regenerate 时走工具循环；
                # 前置搜索已产出 sources 时剔除 web_search 避免双路搜索
                agen = None
                if not body.regenerate and await tools_service.is_tools_enabled(
                    stream_session, user_id
                ):
                    exclude = {"web_search"} if ctx.extra.get("sources") else set()
                    tools_payload = get_registry().build_openai_tools(exclude)
                    if tools_payload:
                        agen = tools_executor.stream_with_tools(
                            pipeline,
                            ctx,
                            tools_payload,
                            is_disconnected=request.is_disconnected,
                            routing_enabled=auto_routing,
                            agent_config=agent_config,
                        )
                if agen is None:
                    agen = pipeline.call_provider_routed(ctx, enabled=auto_routing)
                async with aclosing(_merge_agent_events(agen, event_queue)) as merged:
                    async for event in merged:
                        if await request.is_disconnected():
                            # 客户端断开：取消上游，但仍保存已累积内容
                            disconnected = True
                            break
                        if event.get("type") == "keepalive":
                            # 长工具等待保活：SSE 注释，前端解析器天然忽略
                            yield ":keepalive\n\n"
                            continue
                        # 事件本身已是 {"type": "chunk"|"modelSwitch", ...}
                        yield _sse(event)

                message = await pipeline.persist(ctx)
                # 后台记忆提取：不 await，失败在任务内部自行记日志；
                # disconnected（客户端中止）也同样触发；
                # 后台任务自建 session 丢失请求上下文，user_id 必须显式传递
                try:
                    if ctx.response_text:
                        asyncio.create_task(
                            memory_extractor.extract_after_reply(
                                user_id=user_id,
                                conversation_id=ctx.conversation_id,
                                user_message=ctx.user_message,
                                response_text=ctx.response_text,
                                base_url=ctx.base_url,
                                api_key=ctx.api_key,
                                model_name=ctx.model_name,
                            )
                        )
                except Exception:
                    logger.warning("触发后台记忆提取失败（已忽略）", exc_info=True)
                if not disconnected:
                    yield _sse(
                        {
                            "type": "done",
                            "messageId": message.id if message else "",
                            "usage": ctx.usage or _fallback_usage(ctx),
                        }
                    )
            except PipelineError as exc:
                logger.exception(
                    "Chat pipeline failed: conversation_id=%s",
                    conversation_id,
                )
                await _persist_safely(pipeline, ctx)
                yield _sse({"type": "error", "message": str(exc)})
            except Exception as exc:
                logger.exception(
                    "Unexpected chat stream failure: conversation_id=%s",
                    conversation_id,
                )
                await _persist_safely(pipeline, ctx)
                # 前端直接展示 error 事件的 message，此处拼接简短异常摘要便于定位
                summary = f"{exc.__class__.__name__}: {exc}".strip(": ")[:200]
                yield _sse(
                    {
                        "type": "error",
                        "message": f"服务器内部错误，请稍后重试（{summary}）",
                    }
                )
            finally:
                event_bus.unsubscribe(conversation_id, event_queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@computer_use_router.post("/api/tools/confirm/{confirmation_id}")
async def confirm_action(
    confirmation_id: str,
    body: dict,
    _user_id: str = Depends(get_current_user_id),
):
    """Confirm or deny a pending computer use action."""
    from app.modules.tools.permissions import resolve_confirmation

    approved = body.get("approved", False)
    reason = body.get("reason", "")
    found = resolve_confirmation(confirmation_id, approved, reason)
    if not found:
        raise HTTPException(
            status_code=404, detail="Confirmation not found or expired"
        )
    return {"status": "ok"}


@computer_use_router.get("/api/audit/computer-use")
async def get_computer_use_audit(
    conversation_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    _user_id: str = Depends(get_current_user_id),
):
    """Return recent computer use audit entries."""
    from app.modules.tools.audit import get_audit_log

    entries = await get_audit_log(conversation_id, limit, offset)
    return [
        {
            "id": entry.id,
            "conversation_id": entry.conversation_id,
            "timestamp": entry.timestamp.isoformat(),
            "action": entry.action,
            "confirmation_status": entry.confirmation_status,
            "result_summary": entry.result_summary,
            "duration_ms": entry.duration_ms,
        }
        for entry in entries
    ]
