"""工具调用执行器：多轮 tool-calling 流式编排（静默执行）。

关键约束：
- 工具轮消息绝不能走 ``ChatPipeline._build_upstream_messages`` 重新序列化
  （该方法会剥离 tool_calls/tool_call_id 字段）。本执行器仅用它生成
  "基础消息"，之后自行向 messages 追加带完整字段的 assistant(tool_calls)
  与 {"role": "tool"} 消息。
- 产出事件与 ``call_provider_routed`` 一致：{"type": "chunk"} /
  {"type": "modelSwitch"}（仅降级路径可能产出）；额外的
  {"type": "keepalive"} 由路由层渲染为 `:keepalive` SSE 注释。
- 任何失败都优先降级作答，绝不因工具把管线炸掉。
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

import httpx

from app.modules.tools.registry import get_registry, normalize_arguments
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

# 工具轮数硬上限（不含最终回答轮）
MAX_TOOL_ROUNDS = 4
# 单个工具结果截断长度，防止撑爆上下文
MAX_TOOL_RESULT_CHARS = 8000
# 长工具等待期间的 keepalive 间隔（秒）
KEEPALIVE_INTERVAL = 10.0
# "上游不支持 tools" 负缓存时长（秒）
TOOL_UNSUPPORTED_SECONDS = 600.0

# 模块级负缓存 {(provider_id, model_name): 过期时间（time.monotonic）}；
# 复刻 chat_pipeline._model_cooldowns 的过期清理模式
_tool_unsupported: dict[tuple[str, str], float] = {}


class _ToolUnsupportedError(PipelineError):
    """上游收到 400 且错误体表明不支持 tools/function 字段。"""


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


# “不支持 tools” 判定信号：错误消息需同时命中工具语义与不支持语义，
# 避免网关在错误体回显请求参数（含 "tools"/"tool_choice"）造成误判。
_UNSUPPORTED_SIGNALS = (
    # "not support" 同时覆盖 "not supported" / "does not support"
    "not support",
    "unsupported",
    "unknown parameter",
    "unexpected",
    "invalid parameter",
    "不支持",
)


def _error_indicates_tools_unsupported(summary: str) -> bool:
    """仅基于 _summarize_error 提取的结构化错误消息判定：
    同时包含 tool/function 语义与不支持/未知参数语义才命中。"""
    text = summary.lower()
    if "tool" not in text and "function" not in text:
        return False
    return any(sig in text for sig in _UNSUPPORTED_SIGNALS)


def _accumulate_usage(ctx: ChatContext, usage: dict[str, Any]) -> None:
    """把单轮最后一次 usage 并入 ctx.usage（轮内覆盖、跨轮累加）。"""
    current = ctx.usage or {"promptTokens": 0, "completionTokens": 0}
    ctx.usage = {
        "promptTokens": current.get("promptTokens", 0)
        + int(usage.get("prompt_tokens") or 0),
        "completionTokens": current.get("completionTokens", 0)
        + int(usage.get("completion_tokens") or 0),
    }


def _parse_arguments(raw: str) -> dict[str, Any] | None:
    """解析模型给出的 arguments JSON；失败返回 None（转错误文本回喂）。"""
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
    """单轮流式请求；产出增量文本，同时把 delta.tool_calls 按 index 累积。

    tool_calls 累积元素形如 {"id": ..., "name": ..., "arguments": ...}。
    """
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
                        # 轮内覆盖：只记录该轮最后一次下发（与原管线语义一致），
                        # 轮末再并入 ctx.usage，避免同一轮重复累加虚高
                        round_usage = usage
                    choices = event.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    # 按 index 累积工具调用片段（name 一次给出，arguments 流式分片）
                    for tc in delta.get("tool_calls") or []:
                        try:
                            idx = int(tc.get("index") or 0)
                        except (TypeError, ValueError):
                            continue
                        while len(tool_calls) <= idx:
                            tool_calls.append({"id": "", "name": "", "arguments": ""})
                        if tc.get("id"):
                            tool_calls[idx]["id"] = str(tc["id"])
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            tool_calls[idx]["name"] += str(fn["name"])
                        if fn.get("arguments"):
                            tool_calls[idx]["arguments"] += str(fn["arguments"])
                    content = delta.get("content")
                    if content:
                        # 乐观流式输出并累加（工具轮会在轮末回退）
                        ctx.response_text += content
                        yield content
            # 轮末：把本轮最后一次 usage 并入 ctx.usage（跨轮累加）
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


async def _execute_tool_calls(
    ctx: ChatContext,
    calls: list[dict[str, Any]],
    result_cache: dict[tuple[str, str], str],
) -> list[str]:
    """并发执行全部工具调用，返回与 calls 同序的结果文本列表。

    registry.execute 内部已统一超时与异常兜底，这里只做请求内结果缓存去重。
    """
    registry = get_registry()

    async def run_one(call: dict[str, Any]) -> str:
        name: str = call["name"]
        parsed: dict[str, Any] | None = call["arguments_parsed"]
        if parsed is None:
            return (
                f"工具 {name} 调用失败：参数不是合法 JSON"
                f"（原始参数：{(call.get('arguments') or '')[:200]}）。"
                "请修正参数后重试或直接回答。"
            )
        key = (name, normalize_arguments(parsed))
        cached = result_cache.get(key)
        if cached is not None:
            return cached
        result = await registry.execute(ctx, name, parsed)
        result = result[:MAX_TOOL_RESULT_CHARS]
        result_cache[key] = result
        return result

    return list(await asyncio.gather(*(run_one(c) for c in calls)))


async def stream_with_tools(
    pipeline: ChatPipeline,
    ctx: ChatContext,
    tools: list[dict[str, Any]],
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    routing_enabled: bool = True,
) -> AsyncGenerator[dict[str, Any], None]:
    """带工具循环的流式调用。事件形态与 call_provider_routed 对齐，
    额外产出 {"type": "keepalive"}（路由层渲染为 `:keepalive` SSE 注释）。

    routing_enabled 仅用于降级路径是否启用同渠道模型自动路由。
    """
    registry = get_registry()

    async def _fallback_plain() -> AsyncGenerator[dict[str, Any], None]:
        """剥离 tools 走原管线（保留模型自动路由能力）。"""
        async for event in pipeline.call_provider_routed(ctx, enabled=routing_enabled):
            yield event

    # 负缓存命中：上一轮已确认该模型不支持 tools，直接降级不再尝试
    if _tool_unsupported_cached(ctx):
        async for event in _fallback_plain():
            yield event
        return

    async def _disconnected() -> bool:
        if is_disconnected is None:
            return False
        try:
            return bool(await is_disconnected())
        except Exception:
            return False

    # 基础消息：仅此处复用管线序列化（处理附件）；
    # 后续工具轮消息直接追加完整字段，绝不重新序列化
    messages: list[dict[str, Any]] = list(
        ChatPipeline._build_upstream_messages(ctx.history)
    )
    result_cache: dict[tuple[str, str], str] = {}
    last_round_sig: str | None = None
    force_no_tools = False
    streamed_any = False

    try:
        for round_num in range(MAX_TOOL_ROUNDS + 1):
            if await _disconnected():
                return
            round_start_len = len(ctx.response_text)
            use_tools = (
                bool(tools)
                and not force_no_tools
                and round_num < MAX_TOOL_ROUNDS
                and not _tool_unsupported_cached(ctx)
            )

            tool_calls: list[dict[str, str]] = []
            async for chunk in _stream_round(
                ctx, messages, tools if use_tools else None, tool_calls
            ):
                streamed_any = True
                yield {"type": "chunk", "content": chunk}

            if not tool_calls:
                # 最终轮：内容即最终答案，结束
                return

            # 工具轮：本轮 content 不入最终答案（不影响故障路由判据/持久化）
            round_content = ctx.response_text[round_start_len:]
            ctx.response_text = ctx.response_text[:round_start_len]

            assistant_tool_calls = [
                {
                    "id": tc["id"] or f"call_{round_num}_{i}",
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": tc["arguments"],
                    },
                }
                for i, tc in enumerate(tool_calls)
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
                    "name": tc["name"],
                    "arguments": tc["arguments"],
                    "arguments_parsed": _parse_arguments(tc["arguments"]),
                }
                for tc in tool_calls
            ]

            # 请求内去重：连续两轮完全相同的工具调用视为收敛，
            # 本轮结果照常回喂，但下一轮强制剥离 tools 收尾
            sig = "|".join(
                f"{c['name']}::{normalize_arguments(c['arguments_parsed'])}"
                for c in calls
            )
            if sig == last_round_sig:
                logger.info("检测到连续重复工具调用，强制收尾（第 %d 轮）", round_num)
                force_no_tools = True
            last_round_sig = sig

            # 并发执行工具；长等待每 ~10s 产出 keepalive（兼顾断开检测）。
            # shield + wait_for：超时只打断等待不取消任务；
            # 生成器被 aclose（GeneratorExit）时取消未完成任务防泄漏。
            exec_task = asyncio.ensure_future(
                _execute_tool_calls(ctx, calls, result_cache)
            )
            try:
                while True:
                    try:
                        results = await asyncio.wait_for(
                            asyncio.shield(exec_task), timeout=KEEPALIVE_INTERVAL
                        )
                        break
                    except asyncio.TimeoutError:
                        if await _disconnected():
                            logger.warning(
                                "客户端断开，取消工具执行任务"
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

            for i, result_text in enumerate(results):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": assistant_tool_calls[i]["id"],
                        "content": result_text,
                    }
                )
        # 轮数耗尽仍未收敛：最后一轮已在 use_tools=False 下强制产出最终回答
        return
    except _ToolUnsupportedError:
        _set_tool_unsupported(ctx)
        logger.warning(
            "上游不支持 tools 字段，静默降级为纯聊天（模型=%s）", ctx.model_name
        )
        if streamed_any:
            # 极罕见（后续轮才 400）：不重复输出，交由外层错误处理
            raise PipelineError("上游服务返回了不支持的错误") from None
    except RetryableUpstreamError as exc:
        if streamed_any or ctx.response_text:
            # 已输出内容：维持原报错语义（外层保存部分内容）
            raise
        # 首轮可重试故障：先设冷却再降级，否则 _routing_candidates 会把
        # 刚失败的模型置顶再打一次，故障恢复延迟翻倍且多压一次限流上游
        if ctx.provider_id and ctx.model_name:
            _set_cooldown(ctx.provider_id, ctx.model_name)
        logger.warning(
            "工具循环遇可重试故障（%s），已设模型冷却并降级为无工具调用",
            exc,
        )
    except Exception as exc:
        if streamed_any or ctx.response_text:
            # 已输出内容：维持原报错语义（外层保存部分内容）
            raise
        logger.warning("工具循环异常，降级为无工具调用：%s", exc, exc_info=True)

    # 降级：剥离 tools 走原管线，保证用户始终有回答
    async for event in _fallback_plain():
        yield event
