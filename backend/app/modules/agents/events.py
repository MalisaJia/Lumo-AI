"""进程内异步事件总线，用于 Agent → SSE → 前端的结构化事件分发。"""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncIterator


logger = logging.getLogger(__name__)


@dataclass
class AgentEvent:
    """结构化代理事件。"""

    type: str
    data: dict[str, Any] = field(default_factory=dict)
    conversation_id: str = ""


class AgentEventBus:
    """进程级事件总线。每个 SSE 连接 subscribe 一个队列。"""

    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._stream_subscribers: dict[str, asyncio.Queue] = {}

    def subscribe(
        self, conversation_id: str, *, replace: bool = False
    ) -> asyncio.Queue:
        # Only replace the SSE owner; independent observers retain fan-out.
        if replace:
            previous = self._stream_subscribers.get(conversation_id)
            if previous is not None:
                self.unsubscribe(conversation_id, previous)
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(conversation_id, []).append(queue)
        if replace:
            self._stream_subscribers[conversation_id] = queue
        return queue

    def unsubscribe(self, conversation_id: str, queue: asyncio.Queue) -> None:
        queues = self._subscribers.get(conversation_id, [])
        try:
            remaining = [subscriber for subscriber in queues if subscriber is not queue]
            if remaining:
                self._subscribers[conversation_id] = remaining
            else:
                self._subscribers.pop(conversation_id, None)
        finally:
            if self._stream_subscribers.get(conversation_id) is queue:
                self._stream_subscribers.pop(conversation_id, None)
            # Drop stale events and wake a replaced/disconnected consumer.
            while not queue.empty():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            queue.put_nowait(AgentEvent(type="__close__", conversation_id=conversation_id))

    async def publish(self, event: AgentEvent) -> None:
        # Unbounded queues never need to suspend or retain a cancelled publisher.
        for queue in tuple(self._subscribers.get(event.conversation_id, ())):
            try:
                queue.put_nowait(event)
            except Exception:
                logger.exception(
                    "Agent event delivery failed: conversation_id=%s type=%s",
                    event.conversation_id,
                    event.type,
                )
                self.unsubscribe(event.conversation_id, queue)

    async def iter_events(self, conversation_id: str) -> AsyncIterator[AgentEvent]:
        queue = self.subscribe(conversation_id)
        try:
            while True:
                event = await queue.get()
                if event.type == "__close__":
                    break
                yield event
        finally:
            self.unsubscribe(conversation_id, queue)


# 进程级单例
event_bus = AgentEventBus()
