"""任务生命周期、依赖关系与取消传播管理器。"""

import json
import uuid
import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AgentRun, Task
from app.modules.agents.events import AgentEvent, AgentEventBus, event_bus
from app.modules.agents.runner import cancel_runner


logger = logging.getLogger(__name__)


def _gen_id() -> str:
    return uuid.uuid4().hex[:16]


def _parse_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def _dump_json_list(values: list[str]) -> str | None:
    unique = list(dict.fromkeys(values))
    return json.dumps(unique, ensure_ascii=False) if unique else None


class TaskManager:
    def __init__(
        self, db: AsyncSession, agent_event_bus: AgentEventBus = event_bus
    ):
        self.db = db
        self.event_bus = agent_event_bus

    async def _flush(self, operation: str) -> None:
        """Flush one unit of work and restore the session after a DB failure."""
        try:
            await self.db.flush()
        except Exception:
            logger.exception("TaskManager database operation failed: %s", operation)
            try:
                await self.db.rollback()
            except Exception:
                logger.exception("TaskManager rollback failed: %s", operation)
            raise

    async def _execute(self, statement):
        """Execute a query and restore the session after a DB failure."""
        try:
            return await self.db.execute(statement)
        except Exception:
            logger.exception("TaskManager database query failed")
            try:
                await self.db.rollback()
            except Exception:
                logger.exception("TaskManager query rollback failed")
            raise

    async def create_task(
        self,
        conversation_id: str,
        description: str,
        parent_task_id: str | None = None,
        blocked_by: list[str] | None = None,
        priority: int = 0,
    ) -> Task:
        task = Task(
            id=_gen_id(),
            conversation_id=conversation_id,
            parent_task_id=parent_task_id,
            description=description,
            status="pending",
            priority=priority,
        )
        self.db.add(task)
        await self._flush("create_task")
        for dependency_id in dict.fromkeys(blocked_by or []):
            await self.add_dependency(task.id, dependency_id)
        await self.event_bus.publish(
            AgentEvent(
                type="taskCreated",
                data={
                    "taskId": task.id,
                    "parentTaskId": task.parent_task_id,
                    "description": task.description,
                },
                conversation_id=task.conversation_id,
            )
        )
        return task

    async def create_agent_run(
        self,
        conversation_id: str,
        task_id: str | None,
        agent_type: str,
        model_name: str | None = None,
        parent_run_id: str | None = None,
        workspace_dir: str | None = None,
    ) -> AgentRun:
        run = AgentRun(
            id=_gen_id(),
            conversation_id=conversation_id,
            task_id=task_id,
            parent_run_id=parent_run_id,
            agent_type=agent_type,
            model_name=model_name,
            status="running",
            workspace_dir=workspace_dir,
        )
        self.db.add(run)
        await self._flush("create_agent_run")
        return run

    async def get_task(self, task_id: str) -> Task | None:
        result = await self._execute(select(Task).where(Task.id == task_id))
        return result.scalar_one_or_none()

    async def list_tasks(
        self, conversation_id: str, status: str | None = None
    ) -> list[Task]:
        stmt = select(Task).where(Task.conversation_id == conversation_id)
        if status:
            stmt = stmt.where(Task.status == status)
        stmt = stmt.order_by(Task.created_at)
        result = await self._execute(stmt)
        return list(result.scalars().all())

    async def add_dependency(self, task_id: str, depends_on_id: str) -> None:
        """Add a dependency and keep both blocked_by and blocks synchronized."""
        if task_id == depends_on_id:
            raise ValueError("任务不能依赖自身")
        task = await self.get_task(task_id)
        dependency = await self.get_task(depends_on_id)
        if task is None or dependency is None:
            raise ValueError("任务或依赖任务不存在")
        if task.conversation_id != dependency.conversation_id:
            raise ValueError("不能跨会话添加任务依赖")

        blocked_by = _parse_json_list(task.blocked_by)
        blocks = _parse_json_list(dependency.blocks)
        if dependency.status != "completed" and depends_on_id not in blocked_by:
            blocked_by.append(depends_on_id)
        if task_id not in blocks:
            blocks.append(task_id)
        task.blocked_by = _dump_json_list(blocked_by)
        dependency.blocks = _dump_json_list(blocks)
        task.updated_at = datetime.utcnow()
        dependency.updated_at = datetime.utcnow()
        await self._flush("add_dependency")

    async def resolve_ready_tasks(self, conversation_id: str) -> list[Task]:
        """Return pending tasks whose remaining dependencies are all complete."""
        tasks = await self.list_tasks(conversation_id)
        statuses = {task.id: task.status for task in tasks}
        ready = []
        for task in tasks:
            if task.status != "pending":
                continue
            dependencies = _parse_json_list(task.blocked_by)
            if all(statuses.get(dep_id) == "completed" for dep_id in dependencies):
                ready.append(task)
        return sorted(ready, key=lambda task: (-task.priority, task.created_at))

    async def check_deadlock(self, conversation_id: str) -> bool:
        """Detect a cycle among non-terminal tasks in one conversation."""
        tasks = await self.list_tasks(conversation_id)
        active = {
            task.id: task
            for task in tasks
            if task.status in ("pending", "running")
        }
        graph = {
            task_id: [
                dep_id
                for dep_id in _parse_json_list(task.blocked_by)
                if dep_id in active
            ]
            for task_id, task in active.items()
        }
        visiting: set[str] = set()
        visited: set[str] = set()

        def has_cycle(task_id: str) -> bool:
            if task_id in visiting:
                return True
            if task_id in visited:
                return False
            visiting.add(task_id)
            for dependency_id in graph.get(task_id, []):
                if has_cycle(dependency_id):
                    return True
            visiting.remove(task_id)
            visited.add(task_id)
            return False

        return any(has_cycle(task_id) for task_id in graph if task_id not in visited)

    async def _release_dependents(self, completed_task: Task) -> None:
        dependent_ids = set(_parse_json_list(completed_task.blocks))
        # Scan as a compatibility fallback for rows created before reverse links existed.
        tasks = await self.list_tasks(completed_task.conversation_id)
        dependent_ids.update(
            task.id
            for task in tasks
            if completed_task.id in _parse_json_list(task.blocked_by)
        )
        for task in tasks:
            if task.id not in dependent_ids:
                continue
            remaining = [
                dep_id
                for dep_id in _parse_json_list(task.blocked_by)
                if dep_id != completed_task.id
            ]
            task.blocked_by = _dump_json_list(remaining)
            task.updated_at = datetime.utcnow()

    async def update_task_status(
        self, task_id: str, status: str, result: str | None = None
    ) -> Task | None:
        task = await self.get_task(task_id)
        if not task:
            return None
        task.status = status
        task.updated_at = datetime.utcnow()
        if result is not None:
            task.result = result
        if status == "completed":
            await self._release_dependents(task)
        await self._flush("update_task_status")
        await self.event_bus.publish(
            AgentEvent(
                type="taskStatusChanged",
                data={
                    "taskId": task.id,
                    "status": task.status,
                    "result": task.result,
                },
                conversation_id=task.conversation_id,
            )
        )
        return task

    async def update_agent_run(
        self,
        run_id: str,
        status: str,
        tool_rounds: int | None = None,
        token_usage: dict | None = None,
    ) -> AgentRun | None:
        result = await self._execute(select(AgentRun).where(AgentRun.id == run_id))
        run = result.scalar_one_or_none()
        if not run:
            return None
        run.status = status
        if status in ("completed", "failed", "cancelled"):
            run.finished_at = datetime.utcnow()
        if tool_rounds is not None:
            run.tool_rounds = tool_rounds
        if token_usage is not None:
            run.token_usage = json.dumps(token_usage)
        await self._flush("update_agent_run")
        return run

    async def cancel_task(self, task_id: str) -> Task | None:
        """Cancel a task tree and propagate cancellation to every live runner."""
        task = await self.get_task(task_id)
        if not task:
            return None

        all_tasks = await self.list_tasks(task.conversation_id)
        children_by_parent: dict[str, list[Task]] = {}
        for candidate in all_tasks:
            if candidate.parent_task_id:
                children_by_parent.setdefault(candidate.parent_task_id, []).append(candidate)

        targets: list[Task] = []
        stack = [task]
        while stack:
            current = stack.pop()
            targets.append(current)
            stack.extend(children_by_parent.get(current.id, []))

        target_ids = {target.id for target in targets}
        run_result = await self._execute(
            select(AgentRun).where(AgentRun.task_id.in_(target_ids))
        )
        runs = list(run_result.scalars().all())
        runs_by_task: dict[str, list[AgentRun]] = {}
        for run in runs:
            if run.task_id:
                runs_by_task.setdefault(run.task_id, []).append(run)

        for target in targets:
            if target.status not in ("completed", "failed", "cancelled"):
                target.status = "cancelled"
                target.updated_at = datetime.utcnow()
                await self.event_bus.publish(
                    AgentEvent(
                        type="taskStatusChanged",
                        data={"taskId": target.id, "status": "cancelled"},
                        conversation_id=target.conversation_id,
                    )
                )
            related_runs = runs_by_task.get(target.id, [])
            if target.agent_run_id and all(
                run.id != target.agent_run_id for run in related_runs
            ):
                run_result = await self._execute(
                    select(AgentRun).where(AgentRun.id == target.agent_run_id)
                )
                linked_run = run_result.scalar_one_or_none()
                if linked_run:
                    related_runs.append(linked_run)
            for run in related_runs:
                cancel_runner(run.id)
                if run.status not in ("completed", "failed", "cancelled"):
                    run.status = "cancelled"
                    run.finished_at = datetime.utcnow()

        await self._flush("cancel_task")
        return task
