"""多智能体编排器 — Leader-Worker 模式。"""

import asyncio
import copy
import logging
from dataclasses import dataclass
from typing import Any

from app.core.config import AgentConfig
from app.modules.agents.events import AgentEvent, event_bus
from app.modules.agents.runner import (
    AgentRunner,
    register_runner,
    unregister_runner,
)
from app.modules.tasks.manager import TaskManager
from app.modules.tools.registry import get_registry

logger = logging.getLogger(__name__)


@dataclass
class WorkerResult:
    task_id: str
    status: str  # completed/failed/cancelled
    output: str
    agent_run_id: str | None = None


class AgentOrchestrator:
    """Leader agent 编排多个 Worker agent。"""

    def __init__(
        self,
        task_manager: TaskManager,
        conversation_id: str,
        base_config: AgentConfig,
        max_concurrent: int = 5,
        max_depth: int = 3,
        max_retries: int = 1,
    ):
        self.task_manager = task_manager
        self.conversation_id = conversation_id
        self.base_config = base_config
        self.max_concurrent = max(max_concurrent, 1)
        self.max_depth = max(min(max_depth, base_config.max_depth), 0)
        self.max_retries = max(max_retries, 0)
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        self._db_lock = asyncio.Lock()
        self._cancel_event = asyncio.Event()
        self._workers: dict[str, asyncio.Task[WorkerResult]] = {}

    async def execute_task_tree(
        self, root_task_id: str, pipeline: Any, ctx: Any
    ) -> list[WorkerResult]:
        """执行指定任务树，按依赖顺序和优先级调度。"""
        results: list[WorkerResult] = []
        tasks = await self.task_manager.list_tasks(self.conversation_id)
        by_id = {task.id: task for task in tasks}
        if root_task_id not in by_id:
            return results

        children_by_parent: dict[str, list[str]] = {}
        for task in tasks:
            if task.parent_task_id:
                children_by_parent.setdefault(task.parent_task_id, []).append(task.id)
        tree_ids: set[str] = set()
        stack = [root_task_id]
        while stack:
            task_id = stack.pop()
            if task_id in tree_ids:
                continue
            tree_ids.add(task_id)
            stack.extend(children_by_parent.get(task_id, []))

        pending = {
            task.id: task
            for task in tasks
            if task.id in tree_ids and task.status in ("pending", "running")
        }
        completed_ids = {task.id for task in tasks if task.status == "completed"}
        failed_ids = {
            task.id
            for task in tasks
            if task.status in ("failed", "cancelled")
        }

        while pending and not self._cancel_event.is_set():
            ready = []
            blocked_by_failure = []
            for task in pending.values():
                dependencies = self._parse_json_list(task.blocked_by)
                if any(dep_id in failed_ids for dep_id in dependencies):
                    blocked_by_failure.append(task)
                elif all(dep_id in completed_ids for dep_id in dependencies):
                    ready.append(task)

            for task in blocked_by_failure:
                message = "依赖任务失败或已取消"
                async with self._db_lock:
                    await self.task_manager.update_task_status(task.id, "failed", message)
                failed_ids.add(task.id)
                pending.pop(task.id, None)
                results.append(WorkerResult(task.id, "failed", message))

            if not ready:
                if pending and not blocked_by_failure:
                    logger.error("Task deadlock detected: %s", list(pending))
                    for task in list(pending.values()):
                        message = "依赖死锁"
                        async with self._db_lock:
                            await self.task_manager.update_task_status(
                                task.id, "failed", message
                            )
                        results.append(WorkerResult(task.id, "failed", message))
                        failed_ids.add(task.id)
                        pending.pop(task.id, None)
                continue

            ready.sort(key=lambda task: (-task.priority, task.created_at))
            batch: list[tuple[Any, asyncio.Task[WorkerResult]]] = []
            for task in ready:
                worker_task = asyncio.create_task(self._run_worker(task, pipeline, ctx))
                self._workers[task.id] = worker_task
                batch.append((task, worker_task))

            batch_results = await asyncio.gather(
                *(worker_task for _, worker_task in batch),
                return_exceptions=True,
            )
            for (task, _worker_task), result in zip(batch, batch_results):
                self._workers.pop(task.id, None)
                pending.pop(task.id, None)
                if isinstance(result, BaseException):
                    status = (
                        "cancelled"
                        if isinstance(result, asyncio.CancelledError)
                        else "failed"
                    )
                    output = str(result) or status
                    async with self._db_lock:
                        await self.task_manager.update_task_status(
                            task.id, status, output[:500]
                        )
                    worker_result = WorkerResult(task.id, status, output)
                else:
                    worker_result = result
                results.append(worker_result)
                if worker_result.status == "completed":
                    completed_ids.add(task.id)
                else:
                    failed_ids.add(task.id)

        if self._cancel_event.is_set():
            for task in list(pending.values()):
                async with self._db_lock:
                    await self.task_manager.update_task_status(
                        task.id, "cancelled", "编排任务已取消"
                    )
                results.append(WorkerResult(task.id, "cancelled", ""))
        return results

    async def _run_worker(self, task: Any, pipeline: Any, ctx: Any) -> WorkerResult:
        """在信号量控制下执行单个 worker，并注册持久化运行记录。"""
        async with self._semaphore:
            if self._cancel_event.is_set():
                return WorkerResult(task.id, "cancelled", "")
            if self.base_config.current_depth >= self.max_depth:
                message = "已达最大嵌套深度"
                async with self._db_lock:
                    await self.task_manager.update_task_status(task.id, "failed", message)
                return WorkerResult(task.id, "failed", message)

            async with self._db_lock:
                await self.task_manager.update_task_status(task.id, "running")
                run = await self.task_manager.create_agent_run(
                    conversation_id=self.conversation_id,
                    task_id=task.id,
                    agent_type="orchestrator_worker",
                    model_name=getattr(ctx, "model_name", None),
                    parent_run_id=(getattr(ctx, "extra", {}) or {}).get("agent_run_id"),
                    workspace_dir=self.base_config.workspace_dir,
                )
                task.agent_run_id = run.id
                await self.task_manager.db.flush()

            await event_bus.publish(
                AgentEvent(
                    type="workerStarted",
                    data={"taskId": task.id, "agentRunId": run.id},
                    conversation_id=self.conversation_id,
                )
            )
            final_runner: AgentRunner | None = None
            last_error = ""
            try:
                for attempt in range(self.max_retries + 1):
                    if self._cancel_event.is_set():
                        raise asyncio.CancelledError
                    cancel_event = asyncio.Event()
                    worker_config = AgentConfig(
                        max_tool_rounds=self.base_config.max_tool_rounds,
                        max_tool_result_chars=self.base_config.max_tool_result_chars,
                        allowed_tools=self.base_config.allowed_tools,
                        workspace_dir=self.base_config.workspace_dir,
                        context_max_tokens=self.base_config.context_max_tokens,
                        context_compress_threshold=(
                            self.base_config.context_compress_threshold
                        ),
                        context_keep_recent=self.base_config.context_keep_recent,
                        cancellation_event=cancel_event,
                        current_depth=self.base_config.current_depth + 1,
                        max_depth=self.max_depth,
                    )
                    final_runner = AgentRunner(worker_config)
                    register_runner(run.id, final_runner)
                    worker_ctx = self._worker_context(ctx, task.description, run.id, task.id)
                    tools = get_registry().build_openai_tools()
                    output_parts: list[str] = []
                    try:
                        async for event in final_runner.run(
                            pipeline, worker_ctx, tools
                        ):
                            if event.get("type") == "chunk":
                                content = event.get("content")
                                if content is None:
                                    content = (event.get("data") or {}).get("content", "")
                                output_parts.append(str(content or ""))
                        output = "".join(output_parts) or worker_ctx.response_text
                        if final_runner.status == "cancelled":
                            raise asyncio.CancelledError
                        async with self._db_lock:
                            await self.task_manager.update_task_status(
                                task.id, "completed", output[:2000]
                            )
                            await self.task_manager.update_agent_run(
                                run.id,
                                "completed",
                                tool_rounds=final_runner.current_round,
                                token_usage=worker_ctx.usage,
                            )
                        return WorkerResult(task.id, "completed", output, run.id)
                    except asyncio.CancelledError:
                        raise
                    except Exception as exc:
                        last_error = f"{exc.__class__.__name__}: {exc}"
                        logger.warning(
                            "Worker %s attempt %d failed: %s",
                            task.id,
                            attempt + 1,
                            exc,
                            exc_info=True,
                        )
                        if attempt >= self.max_retries:
                            break
                    finally:
                        unregister_runner(run.id)

                async with self._db_lock:
                    await self.task_manager.update_task_status(
                        task.id, "failed", last_error[:500]
                    )
                    await self.task_manager.update_agent_run(
                        run.id,
                        "failed",
                        tool_rounds=final_runner.current_round if final_runner else None,
                    )
                return WorkerResult(task.id, "failed", last_error, run.id)
            except asyncio.CancelledError:
                if final_runner:
                    final_runner.cancel()
                async with self._db_lock:
                    await self.task_manager.update_task_status(
                        task.id, "cancelled", "Worker 已取消"
                    )
                    await self.task_manager.update_agent_run(
                        run.id,
                        "cancelled",
                        tool_rounds=final_runner.current_round if final_runner else None,
                    )
                return WorkerResult(task.id, "cancelled", "", run.id)
            finally:
                unregister_runner(run.id)
                await event_bus.publish(
                    AgentEvent(
                        type="workerStopped",
                        data={
                            "taskId": task.id,
                            "agentRunId": run.id,
                            "status": final_runner.status if final_runner else "cancelled",
                        },
                        conversation_id=self.conversation_id,
                    )
                )

    def cancel(self) -> None:
        """取消所有工作，并让 asyncio 取消传播到每个 runner。"""
        self._cancel_event.set()
        for worker_task in list(self._workers.values()):
            worker_task.cancel()

    @staticmethod
    def _worker_context(ctx: Any, description: str, run_id: str, task_id: str) -> Any:
        worker_ctx = copy.copy(ctx)
        worker_ctx.history = list(getattr(ctx, "history", []))
        worker_ctx.history.append({"role": "user", "content": description})
        worker_ctx.extra = dict(getattr(ctx, "extra", {}) or {})
        worker_ctx.extra["agent_run_id"] = run_id
        worker_ctx.extra["agent_task_id"] = task_id
        worker_ctx.user_message = description
        worker_ctx.response_text = ""
        worker_ctx.usage = None
        return worker_ctx

    @staticmethod
    def _parse_json_list(value: str | None) -> list[str]:
        if not value:
            return []
        import json

        try:
            result = json.loads(value)
            return [str(item) for item in result] if isinstance(result, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
