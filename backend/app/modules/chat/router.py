import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import async_session_factory, get_session
from app.models import Message
from app.modules.conversations import service as conv_service
from app.modules.memory import extractor as memory_extractor
from app.modules.memory import service as memory_service
from app.modules.routing import service as routing_service
from app.modules.search import service as search_service
from app.pipeline.chat_pipeline import ChatContext, ChatPipeline, PipelineError
from app.schemas import ChatStreamRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _sse(payload: dict) -> str:
    """一行 SSE 事件：data: 开头、双换行结尾。"""
    return f"data:{json.dumps(payload, ensure_ascii=False)}\n\n"


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
):
    conversation = await conv_service.get_conversation(session, body.conversation_id)
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

    async def event_stream() -> AsyncGenerator[str, None]:
        # StreamingResponse 生命周期长于 Depends 会话，这里独立开一个
        async with async_session_factory() as stream_session:
            pipeline = ChatPipeline(stream_session)
            ctx = ChatContext(
                conversation_id=conversation_id, user_message=user_content
            )
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
                    if await memory_service.is_memory_enabled(stream_session):
                        memory_block = await memory_service.build_memory_context(
                            stream_session, ctx.user_message
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
                    stream_session
                )
                agen = pipeline.call_provider_routed(ctx, enabled=auto_routing)
                try:
                    async for event in agen:
                        if await request.is_disconnected():
                            # 客户端断开：取消上游，但仍保存已累积内容
                            disconnected = True
                            break
                        # 事件本身已是 {"type": "chunk"|"modelSwitch", ...}
                        yield _sse(event)
                finally:
                    await agen.aclose()

                message = await pipeline.persist(ctx)
                # 后台记忆提取：不 await，失败在任务内部自行记日志；
                # disconnected（客户端中止）也同样触发
                try:
                    if ctx.response_text:
                        asyncio.create_task(
                            memory_extractor.extract_after_reply(
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
                await pipeline.persist(ctx)  # 出错前的部分内容也保存
                yield _sse({"type": "error", "message": str(exc)})
            except Exception:
                await pipeline.persist(ctx)
                yield _sse({"type": "error", "message": "服务器内部错误，请稍后重试"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
