"""Observable multi-round tool-calling runner."""

import asyncio
import base64
import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import aclosing
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import DATA_DIR, AgentConfig
from app.models import Model
from app.modules.agents.context import ContextBudget, ContextManager
from app.modules.agents.events import AgentEvent, event_bus
from app.modules.routing.classifier import default_capabilities, get_tags
from app.modules.tools.permissions import permission_engine
from app.modules.tools.registry import (
    ToolResult,
    ToolResultPart,
    get_registry,
    normalize_arguments,
)
from app.pipeline.chat_pipeline import (
    RETRYABLE_STATUS_CODES,
    STREAM_TIMEOUT,
    ChatContext,
    ChatPipeline,
    PipelineError,
    RetryableUpstreamError,
    _set_cooldown,
)

logger = logging.getLogger(__name__)

# Long-running tool keepalive interval, in seconds.
KEEPALIVE_INTERVAL = 10.0
# Negative-cache duration for upstream models that reject tool fields.
TOOL_UNSUPPORTED_SECONDS = 600.0
TOOL_SCREENSHOT_DIR = DATA_DIR / "uploads"
VISION_UNSUPPORTED_NOTE = (
    "[Screenshot captured but current model does not support vision. "
    "Switch to a vision-capable model to see screenshots.]"
)

# {(provider_id, model_name): expiry according to time.monotonic()}.
_tool_unsupported: dict[tuple[str, str], float] = {}

# Process-level registry used by task cancellation to reach live runners.
_active_runners: dict[str, "AgentRunner"] = {}


def register_runner(run_id: str, runner: "AgentRunner") -> None:
    """Register a live runner under its persisted AgentRun ID."""
    previous = _active_runners.pop(run_id, None)
    if previous is not None and previous is not runner:
        previous.cancel()
        logger.warning("Replacing stale runner: run_id=%s", run_id)
    runner._run_id = run_id
    _active_runners[run_id] = runner


def unregister_runner(run_id: str, runner: "AgentRunner | None" = None) -> None:
    """Remove only the requested owner when a replacement is already running."""
    if runner is None or _active_runners.get(run_id) is runner:
        _active_runners.pop(run_id, None)


def cancel_runner(run_id: str) -> bool:
    """Cancel a live runner. Return whether the run was registered."""
    runner = _active_runners.get(run_id)
    if runner is None:
        return False
    runner.cancel()
    return True


async def _publish_event(event: AgentEvent) -> None:
    """Observability is best effort and must not break tool execution."""
    try:
        await event_bus.publish(event)
    except Exception:
        logger.exception(
            "Agent event publication failed: conversation_id=%s type=%s",
            event.conversation_id,
            event.type,
        )


class _ToolUnsupportedError(PipelineError):
    """The upstream returned HTTP 400 because it does not support tools."""


def _set_tool_unsupported(ctx: ChatContext) -> None:
    now = time.monotonic()
    expired = [key for key, deadline in _tool_unsupported.items() if deadline <= now]
    for key in expired:
        del _tool_unsupported[key]
    _tool_unsupported[(ctx.provider_id or "", ctx.model_name or "")] = (
        now + TOOL_UNSUPPORTED_SECONDS
    )


def _tool_unsupported_cached(ctx: ChatContext) -> bool:
    return (
        _tool_unsupported.get((ctx.provider_id or "", ctx.model_name or ""), 0.0)
        > time.monotonic()
    )


_UNSUPPORTED_SIGNALS = (
    "not support",
    "unsupported",
    "unknown parameter",
    "unexpected",
    "invalid parameter",
    "不支持",
)


def _error_indicates_tools_unsupported(summary: str) -> bool:
    """Require both tool semantics and an unsupported-parameter signal."""
    text = summary.lower()
    if "tool" not in text and "function" not in text:
        return False
    return any(signal in text for signal in _UNSUPPORTED_SIGNALS)


def _accumulate_usage(ctx: ChatContext, usage: dict[str, Any]) -> None:
    """Merge one round's final usage into the cross-round context usage."""
    current = ctx.usage or {"promptTokens": 0, "completionTokens": 0}
    ctx.usage = {
        "promptTokens": current.get("promptTokens", 0)
        + int(usage.get("prompt_tokens") or 0),
        "completionTokens": current.get("completionTokens", 0)
        + int(usage.get("completion_tokens") or 0),
    }


def _event_conversation_id(ctx: ChatContext) -> str:
    event_conversation_id = ctx.extra.get("event_conversation_id")
    return str(event_conversation_id or ctx.conversation_id)


def _extract_thinking_text(event: dict[str, Any]) -> str:
    """Extract reasoning deltas from OpenAI- and Anthropic-compatible chunks."""
    pieces: list[str] = []

    def append_text(value: Any) -> None:
        if isinstance(value, str) and value and value not in pieces:
            pieces.append(value)

    def append_content_parts(value: Any) -> None:
        if not isinstance(value, list):
            return
        for part in value:
            if not isinstance(part, dict):
                continue
            if part.get("type") in {"thinking", "reasoning", "thinking_delta"}:
                append_text(part.get("thinking") or part.get("reasoning_content") or part.get("text"))

    choices = event.get("choices") or []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        for source in (choice.get("delta"), choice.get("message")):
            if not isinstance(source, dict):
                continue
            append_text(source.get("reasoning_content"))
            append_text(source.get("thinking"))
            append_content_parts(source.get("content"))

    native_delta = event.get("delta")
    if isinstance(native_delta, dict):
        append_text(native_delta.get("reasoning_content"))
        if native_delta.get("type") in {"thinking", "thinking_delta", "reasoning"}:
            append_text(native_delta.get("thinking") or native_delta.get("text"))

    content_block = event.get("content_block")
    if isinstance(content_block, dict) and content_block.get("type") == "thinking":
        append_text(content_block.get("thinking") or content_block.get("text"))
    append_content_parts(event.get("content"))
    return "".join(pieces)


def _parse_arguments(raw: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(raw) if raw else {}
    except ValueError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return {"value": parsed}


async def _stream_round(
    ctx: ChatContext,
    messages: list[dict[str, Any]],
    tools_payload: list[dict[str, Any]] | None,
    tool_calls: list[dict[str, str]],
) -> AsyncGenerator[str, None]:
    """Stream one model round and accumulate tool-call deltas by index."""
    round_usage: dict[str, Any] | None = None
    payload: dict[str, Any] = {
        "model": ctx.model_name,
        "messages": messages,
        "stream": True,
    }
    if tools_payload:
        payload["tools"] = tools_payload
        payload["tool_choice"] = "auto"
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
                    summary = ChatPipeline._summarize_error(
                        resp.status_code, body, ctx
                    )
                    if (
                        resp.status_code == 400
                        and tools_payload
                        and _error_indicates_tools_unsupported(summary)
                    ):
                        logger.info(
                            "判定上游不支持 tools（message=%s），将降级为纯聊天",
                            summary,
                        )
                        raise _ToolUnsupportedError(summary)
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
                        round_usage = usage
                    thinking_text = _extract_thinking_text(event)
                    if thinking_text:
                        await _publish_event(
                            AgentEvent(
                                type="thinking",
                                data={"content": thinking_text},
                                conversation_id=_event_conversation_id(ctx),
                            )
                        )
                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    for tool_call in delta.get("tool_calls") or []:
                        try:
                            index = int(tool_call.get("index") or 0)
                        except (TypeError, ValueError):
                            continue
                        while len(tool_calls) <= index:
                            tool_calls.append(
                                {"id": "", "name": "", "arguments": ""}
                            )
                        if tool_call.get("id"):
                            tool_calls[index]["id"] = str(tool_call["id"])
                        function = tool_call.get("function") or {}
                        if function.get("name"):
                            tool_calls[index]["name"] += str(function["name"])
                        if function.get("arguments"):
                            tool_calls[index]["arguments"] += str(
                                function["arguments"]
                            )
                    content = delta.get("content")
                    if isinstance(content, list):
                        content = "".join(
                            str(part.get("text") or "")
                            for part in content
                            if isinstance(part, dict)
                            and part.get("type") not in {
                                "thinking",
                                "reasoning",
                                "thinking_delta",
                            }
                        )
                    if isinstance(content, str) and content:
                        ctx.response_text += content
                        yield content
            if round_usage is not None:
                _accumulate_usage(ctx, round_usage)
    except PipelineError:
        raise
    except httpx.TimeoutException as exc:
        raise RetryableUpstreamError("连接上游模型服务超时") from exc
    except httpx.HTTPError as exc:
        raise RetryableUpstreamError(
            f"网络错误：无法连接上游模型服务（{exc.__class__.__name__}）"
        ) from exc


def _text_tool_result(content: str) -> ToolResult:
    return ToolResult(parts=[ToolResultPart(type="text", content=content)])


def _truncate_tool_result(result: ToolResult, max_chars: int) -> ToolResult:
    """Truncate aggregate text content while preserving every image part."""
    remaining = max(0, max_chars)
    parts: list[ToolResultPart] = []
    for part in result.parts:
        if part.type != "text":
            parts.append(part)
            continue
        content = part.content[:remaining]
        remaining -= len(content)
        parts.append(
            ToolResultPart(type="text", content=content, mime_type=part.mime_type)
        )
    return ToolResult(parts=parts, metadata=dict(result.metadata))


def format_tool_result_message(tool_call_id: str, result: ToolResult) -> dict[str, Any]:
    """Format a structured tool result for an OpenAI-compatible request."""
    if not result.has_images():
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": result.text_content(),
        }

    content_parts: list[dict[str, Any]] = []
    for part in result.parts:
        if part.type == "text":
            content_parts.append({"type": "text", "text": part.content})
        elif part.type == "image":
            content_parts.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{part.mime_type};base64,{part.content}"
                    },
                }
            )
    return {
        "role": "tool",
        "tool_call_id": tool_call_id,
        "content": content_parts,
    }


async def _load_model_capabilities(
    pipeline: ChatPipeline, ctx: ChatContext
) -> None:
    """Load configured capability tags, falling back to the model-name table."""
    if ctx.extra.get("model_capabilities"):
        return
    try:
        result = await pipeline.session.execute(
            select(Model).where(
                Model.provider_id == ctx.provider_id,
                Model.name == ctx.model_name,
            )
        )
        model = result.scalars().first()
        if model is not None:
            ctx.extra["model_capabilities"] = get_tags(model)
            return
    except Exception:
        logger.warning("Failed to load model capability tags", exc_info=True)
    ctx.extra["model_capabilities"] = default_capabilities(ctx.model_name or "")


def _model_supports_vision(ctx: ChatContext) -> bool:
    configured = ctx.extra.get("model_capabilities") or ctx.extra.get(
        "capability_tags"
    )
    if isinstance(configured, str):
        try:
            configured = json.loads(configured)
        except ValueError:
            configured = None
    if isinstance(configured, list):
        return "vision" in configured
    return "vision" in default_capabilities(ctx.model_name or "")


def _save_tool_result_images(result: ToolResult) -> list[str]:
    """Persist image parts and return database-safe screenshot references."""
    references: list[str] = []
    if not result.has_images():
        return references
    for part in result.image_parts():
        try:
            TOOL_SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
            image_data = base64.b64decode(part.content, validate=True)
            filename = f"{uuid.uuid4().hex}.png"
            (TOOL_SCREENSHOT_DIR / filename).write_bytes(image_data)
            references.append(f"[screenshot:{filename}]")
        except (OSError, ValueError):
            logger.warning("Failed to persist tool screenshot", exc_info=True)
    return references


async def _execute_tool_calls(
    ctx: ChatContext,
    calls: list[dict[str, Any]],
    result_cache: dict[tuple[str, str], ToolResult],
    max_result_chars: int,
    allowed_tools: set[str] | None,
) -> list[ToolResult]:
    """Execute parallel tools first, then serial tools, preserving call order."""
    registry = get_registry()

    async def execute_one(call: dict[str, Any]) -> ToolResult:
        name: str = call["name"]
        if allowed_tools is not None and name not in allowed_tools:
            logger.warning("拒绝执行未授权工具：%s", name)
            return _text_tool_result(f"工具 {name} 未获当前 Agent 授权，调用已拒绝。")
        parsed: dict[str, Any] | None = call["arguments_parsed"]
        if parsed is None:
            return _text_tool_result(
                f"工具 {name} 调用失败：参数不是合法 JSON"
                f"（原始参数：{(call.get('arguments') or '')[:200]}）。"
                "请修正参数后重试或直接回答。"
            )
        decision, reason = permission_engine.evaluate(name, parsed)
        if decision == "deny":
            logger.warning("权限策略拒绝工具 %s：%s", name, reason or "未说明原因")
            detail = f"：{reason}" if reason else ""
            return _text_tool_result(f"工具 {name} 被权限策略拒绝{detail}。")
        if decision == "ask":
            logger.warning(
                "工具 %s 命中 ask 权限规则，Phase 3f UI 确认接入前暂时放行：%s",
                name,
                reason or "未说明原因",
            )

        tool_obj = registry.get_tool(name)
        key = (name, normalize_arguments(parsed))
        cacheable = bool(tool_obj is None or tool_obj.cacheable) and name not in {
            "check_background_task",
            "publish_context",
            "read_shared_context",
        }
        cached = result_cache.get(key) if cacheable else None
        if cached is not None:
            return cached
        event_conversation_id = _event_conversation_id(ctx)
        event_data = {
            "agentId": ctx.conversation_id,
            "toolName": name,
            "toolCallId": str(call.get("id") or ""),
        }
        await _publish_event(
            AgentEvent(
                type="toolStart",
                data=event_data,
                conversation_id=event_conversation_id,
            )
        )
        status = "completed"
        try:
            execution_arguments = parsed
            if name == "ask_user":
                execution_arguments = {
                    **parsed,
                    "_tool_call_id": str(call.get("id") or ""),
                }
            result = await registry.execute(ctx, name, execution_arguments)
            result = _truncate_tool_result(result, max_result_chars)
            if cacheable:
                result_cache[key] = result
        except (asyncio.CancelledError, GeneratorExit):
            await _publish_event(
                AgentEvent(
                    type="toolEnd",
                    data={**event_data, "status": "cancelled"},
                    conversation_id=event_conversation_id,
                )
            )
            raise
        except SQLAlchemyError:
            raise
        except Exception as exc:
            logger.exception(
                "Tool execution failed: conversation_id=%s tool=%s tool_call_id=%s",
                ctx.conversation_id,
                name,
                call.get("id"),
            )
            status = "failed"
            result = _text_tool_result(
                f"Tool {name} failed ({exc.__class__.__name__}). "
                "Correct the call or continue with available information."
            )
        await _publish_event(
            AgentEvent(
                type="toolEnd",
                data={**event_data, "status": status},
                conversation_id=event_conversation_id,
            )
        )
        return result

    async def run_one(call: dict[str, Any]) -> ToolResult:
        try:
            return await execute_one(call)
        except SQLAlchemyError:
            raise
        except Exception as exc:
            name = str(call.get("name") or "unknown")
            logger.exception(
                "Tool preparation failed: conversation_id=%s tool=%s tool_call_id=%s",
                ctx.conversation_id,
                name,
                call.get("id"),
            )
            await _publish_event(
                AgentEvent(
                    type="toolEnd",
                    data={
                        "agentId": ctx.conversation_id,
                        "toolName": name,
                        "toolCallId": str(call.get("id") or ""),
                        "status": "failed",
                    },
                    conversation_id=_event_conversation_id(ctx),
                )
            )
            return _text_tool_result(
                f"Tool {name} failed ({exc.__class__.__name__}). "
                "Correct the call or continue with available information."
            )

    parallel_calls: list[tuple[int, dict[str, Any]]] = []
    serial_calls: list[tuple[int, dict[str, Any]]] = []
    for index, call in enumerate(calls):
        tool_obj = registry.get_tool(str(call.get("name") or ""))
        target = (
            serial_calls
            if tool_obj and tool_obj.execution_mode == "serial"
            else parallel_calls
        )
        target.append((index, call))

    results: list[ToolResult | None] = [None] * len(calls)
    tasks = [asyncio.create_task(run_one(call)) for _, call in parallel_calls]
    try:
        if tasks:
            parallel_results = await asyncio.gather(*tasks)
            for (index, _), result in zip(parallel_calls, parallel_results):
                results[index] = result
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    for index, call in serial_calls:
        results[index] = await run_one(call)

    return [
        result if result is not None else _text_tool_result("Tool returned no result.")
        for result in results
    ]


class AgentRunner:
    """可观察的工具调用循环引擎。"""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.context_manager = ContextManager(
            ContextBudget(
                max_tokens=config.context_max_tokens,
                compress_threshold=config.context_compress_threshold,
                keep_recent=config.context_keep_recent,
            )
        )
        self.current_round: int = 0
        self.status: str = "idle"
        self._run_id: str | None = None
        self.active_tool_calls: list[str] = []
        self._allowed_tools = (
            set(config.allowed_tools) if config.allowed_tools is not None else None
        )
        self._cancel_event = config.cancellation_event or asyncio.Event()

    def cancel(self) -> None:
        self._cancel_event.set()
        self.status = "cancelled"

    async def run(
        self,
        pipeline: ChatPipeline,
        ctx: ChatContext,
        tools: list[dict[str, Any]],
        is_disconnected: Callable[[], Awaitable[bool]] | None = None,
        routing_enabled: bool = True,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """执行工具调用循环，yield SSE 事件。"""
        self.status = "running"
        self.current_round = 0
        self.context_manager.compressed_summary = None
        event_conversation_id = _event_conversation_id(ctx)
        run_id = self._run_id or str(ctx.extra.get("agent_run_id") or "")
        if run_id:
            register_runner(run_id, self)
        try:
            await _publish_event(
                AgentEvent(
                    type="agentStarted",
                    data={"agentId": ctx.conversation_id, "status": self.status},
                    conversation_id=event_conversation_id,
                )
            )
            visible_tools = tools
            if self._allowed_tools is not None:
                visible_tools = [
                    tool_payload
                    for tool_payload in tools
                    if (tool_payload.get("function") or {}).get("name")
                    in self._allowed_tools
                ]
                ctx.extra["allowed_tools"] = sorted(self._allowed_tools)
            if self.config.workspace_dir is not None:
                ctx.extra["workspace_dir"] = self.config.workspace_dir
            # Tool handlers receive the exact parent configuration through ChatContext.
            ctx.extra["_agent_config"] = self.config
            ctx.extra["agent_current_depth"] = self.config.current_depth
            ctx.extra["agent_max_depth"] = self.config.max_depth
            await _load_model_capabilities(pipeline, ctx)
            async with aclosing(self._run_loop(
                pipeline,
                ctx,
                visible_tools,
                is_disconnected=is_disconnected,
                routing_enabled=routing_enabled,
            )) as loop:
                async for event in loop:
                    yield event
        except (asyncio.CancelledError, GeneratorExit):
            self.status = "cancelled"
            raise
        except BaseException:
            self.status = "failed"
            raise
        else:
            self.status = (
                "cancelled" if self._cancel_event.is_set() else "completed"
            )
        finally:
            references = ctx.extra.get("tool_screenshot_references") or []
            if references:
                marker_block = "\n".join(str(reference) for reference in references)
                if marker_block not in ctx.response_text:
                    separator = "\n\n" if ctx.response_text else ""
                    ctx.response_text += separator + marker_block
            self.active_tool_calls = []
            if run_id:
                unregister_runner(run_id, self)
            await _publish_event(
                AgentEvent(
                    type="agentStopped",
                    data={
                        "agentId": ctx.conversation_id,
                        "status": self.status,
                        "rounds": self.current_round,
                    },
                    conversation_id=event_conversation_id,
                )
            )

    async def _run_loop(
        self,
        pipeline: ChatPipeline,
        ctx: ChatContext,
        tools: list[dict[str, Any]],
        is_disconnected: Callable[[], Awaitable[bool]] | None,
        routing_enabled: bool,
    ) -> AsyncGenerator[dict[str, Any], None]:
        async def fallback_plain() -> AsyncGenerator[dict[str, Any], None]:
            async for event in pipeline.call_provider_routed(
                ctx, enabled=routing_enabled
            ):
                if self._cancel_event.is_set():
                    return
                yield event

        if self._cancel_event.is_set():
            return

        if _tool_unsupported_cached(ctx):
            async for event in fallback_plain():
                yield event
            return

        async def disconnected() -> bool:
            if is_disconnected is None:
                return False
            try:
                return bool(await is_disconnected())
            except Exception:
                return False

        messages: list[dict[str, Any]] = list(
            ChatPipeline._build_upstream_messages(ctx.history)
        )
        result_cache: dict[tuple[str, str], ToolResult] = {}
        last_round_sig: str | None = None
        force_no_tools = False
        streamed_any = False

        async def summarize_context(
            summary_messages: list[dict[str, str]],
        ) -> str:
            # 局部导入避免 rewriter -> chat_pipeline 与 runner 的导入环。
            from app.modules.search.rewriter import llm_complete

            summary = await llm_complete(
                ctx, summary_messages, max_tokens=2048
            )
            if not summary:
                raise PipelineError("上下文摘要调用未返回内容")
            return summary

        try:
            for round_num in range(self.config.max_tool_rounds + 1):
                self.current_round = round_num + 1
                if self._cancel_event.is_set() or await disconnected():
                    return
                if self.context_manager.should_compress(messages):
                    messages = await self.context_manager.compress(
                        messages, summarize_context
                    )
                round_start_len = len(ctx.response_text)
                use_tools = (
                    bool(tools)
                    and not force_no_tools
                    and round_num < self.config.max_tool_rounds
                    and not _tool_unsupported_cached(ctx)
                )

                tool_calls: list[dict[str, str]] = []
                async with aclosing(_stream_round(
                    ctx, messages, tools if use_tools else None, tool_calls
                )) as round_stream:
                    async for chunk in round_stream:
                        if self._cancel_event.is_set():
                            return
                        streamed_any = True
                        yield {"type": "chunk", "content": chunk}

                if self._cancel_event.is_set():
                    return
                # 上游分片偶尔只带 index 不带内容，聚合后会留下 name 与
                # arguments 全空的伪 tool_call；在唯一收口点过滤，保证持久化的
                # assistant tool_calls 与实际执行的 calls 下标严格对应。
                tool_calls = [
                    entry for entry in tool_calls if entry["name"] or entry["arguments"]
                ]
                if not tool_calls:
                    return

                round_content = ctx.response_text[round_start_len:]
                ctx.response_text = ctx.response_text[:round_start_len]

                # 下标由本推导式的 enumerate 显式绑定，id 缺失时按轮次+下标合成
                assistant_tool_calls = [
                    {
                        "id": tool_call["id"] or f"call_{round_num}_{index}",
                        "type": "function",
                        "function": {
                            "name": tool_call["name"],
                            "arguments": tool_call["arguments"],
                        },
                    }
                    for index, tool_call in enumerate(tool_calls)
                ]
                messages.append(
                    {
                        "role": "assistant",
                        "content": round_content,
                        "tool_calls": assistant_tool_calls,
                    }
                )

                calls = [
                    {
                        "id": assistant_tool_calls[index]["id"],
                        "name": tool_call["name"],
                        "arguments": tool_call["arguments"],
                        "arguments_parsed": _parse_arguments(
                            tool_call["arguments"]
                        ),
                    }
                    for index, tool_call in enumerate(tool_calls)
                ]

                signature = "|".join(
                    f"{call['name']}::{normalize_arguments(call['arguments_parsed'])}"
                    for call in calls
                )
                if signature == last_round_sig:
                    logger.info(
                        "检测到连续重复工具调用，强制收尾（第 %d 轮）",
                        round_num,
                    )
                    force_no_tools = True
                last_round_sig = signature

                self.active_tool_calls = [call["name"] for call in calls]
                exec_task = asyncio.ensure_future(
                    _execute_tool_calls(
                        ctx,
                        calls,
                        result_cache,
                        self.config.max_tool_result_chars,
                        self._allowed_tools,
                    )
                )
                try:
                    while True:
                        if self._cancel_event.is_set():
                            exec_task.cancel()
                            return
                        try:
                            results = await asyncio.wait_for(
                                asyncio.shield(exec_task),
                                timeout=KEEPALIVE_INTERVAL,
                            )
                            break
                        except asyncio.TimeoutError:
                            if self._cancel_event.is_set() or await disconnected():
                                logger.warning(
                                    "工具循环已取消，取消工具执行任务"
                                    "（工具若在子进程/线程中运行可能残留）"
                                )
                                exec_task.cancel()
                                return
                            yield {"type": "keepalive"}
                except BaseException:
                    logger.warning(
                        "工具循环中断，取消工具执行任务"
                        "（工具若在子进程/线程中运行可能残留）"
                    )
                    exec_task.cancel()
                    raise
                finally:
                    if not exec_task.done():
                        exec_task.cancel()
                    await asyncio.gather(exec_task, return_exceptions=True)
                    self.active_tool_calls = []

                supports_vision = _model_supports_vision(ctx)
                for index, result in enumerate(results):
                    call = calls[index]
                    references = _save_tool_result_images(result)
                    if references:
                        stored_references = ctx.extra.setdefault(
                            "tool_screenshot_references", []
                        )
                        for reference in references:
                            if reference not in stored_references:
                                stored_references.append(reference)

                    result_for_model = result
                    if result.has_images() and not supports_vision:
                        result_for_model = _text_tool_result(
                            result.text_content() + "\n" + VISION_UNSUPPORTED_NOTE
                        )
                    result_text = result.text_content()
                    if call["name"] == "bash" and result_text:
                        arguments = call.get("arguments_parsed") or {}
                        yield {
                            "type": "toolExecution",
                            "toolName": call["name"],
                            "command": str(arguments.get("command") or ""),
                            "output": result_text,
                        }
                    messages.append(
                        format_tool_result_message(
                            assistant_tool_calls[index]["id"], result_for_model
                        )
                    )
            return
        except _ToolUnsupportedError:
            _set_tool_unsupported(ctx)
            logger.warning(
                "上游不支持 tools 字段，静默降级为纯聊天（模型=%s）",
                ctx.model_name,
            )
            if streamed_any:
                raise PipelineError("上游服务返回了不支持的错误") from None
        except RetryableUpstreamError as exc:
            if streamed_any or ctx.response_text:
                raise
            if ctx.provider_id and ctx.model_name:
                _set_cooldown(ctx.provider_id, ctx.model_name)
            logger.warning(
                "工具循环遇可重试故障（%s），已设模型冷却并降级为无工具调用",
                exc,
            )
        except SQLAlchemyError:
            # Core pipeline database failures are not recoverable tool failures.
            raise
        except Exception as exc:
            if streamed_any or ctx.response_text:
                raise
            logger.warning(
                "工具循环异常，降级为无工具调用：%s", exc, exc_info=True
            )

        if self._cancel_event.is_set():
            return
        async for event in fallback_plain():
            yield event

