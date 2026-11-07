"""Backward-compatible entry point for the observable agent tool loop."""

from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import aclosing
from typing import Any

from app.core.config import AgentConfig
from app.modules.agents.runner import AgentRunner
from app.pipeline.chat_pipeline import ChatContext, ChatPipeline


async def stream_with_tools(
    pipeline: ChatPipeline,
    ctx: ChatContext,
    tools: list[dict[str, Any]],
    is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    routing_enabled: bool = True,
    agent_config: AgentConfig | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """Run the observable tool loop while preserving the legacy call surface."""
    config = agent_config or AgentConfig()
    runner = AgentRunner(config)
    async with aclosing(runner.run(
        pipeline,
        ctx,
        tools,
        is_disconnected=is_disconnected,
        routing_enabled=routing_enabled,
    )) as stream:
        async for event in stream:
            yield event
