"""Multi-agent orchestration tools for isolated and parallel sub-tasks."""

import asyncio
import json
import logging
from typing import Any

from app.modules.tools import sandbox
from app.modules.tools.registry import tool

logger = logging.getLogger(__name__)

_DEFAULT_SYSTEM_PROMPT = (
    "你是一个专业的编码子智能体。你的任务是完成分配给你的具体子任务，"
    "使用可用的工具（文件读写、搜索、命令执行等）高效完成工作。"
    "完成后请简洁总结你做了什么以及结果。"
)
_AGENT_TOOL_NAMES = {"agent", "parallel_agents"}
_MUTATING_TOOL_NAMES = {"file_write", "file_edit", "bash", "create_ppt"}


def _normalize_review_result(result: str) -> str:
    """Guarantee the review tool result follows the findings JSON contract."""
    candidate = result.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        lines = candidate.splitlines()
        candidate = "\n".join(lines[1:-1]).strip()
    try:
        payload = json.loads(candidate)
    except (TypeError, ValueError):
        payload = {
            "findings": [
                {
                    "severity": "info",
                    "file": "",
                    "line": None,
                    "message": result.strip() or "审查代理未返回内容。",
                }
            ]
        }
    if not isinstance(payload, dict) or not isinstance(payload.get("findings"), list):
        payload = {
            "findings": [
                {
                    "severity": "info",
                    "file": "",
                    "line": None,
                    "message": str(payload),
                }
            ]
        }
    normalized = []
    for finding in payload["findings"]:
        if not isinstance(finding, dict):
            continue
        normalized.append(
            {
                "severity": str(finding.get("severity") or "info"),
                "file": str(finding.get("file") or ""),
                "line": finding.get("line"),
                "message": str(finding.get("message") or ""),
            }
        )
    return json.dumps({"findings": normalized}, ensure_ascii=False)


@tool(
    name="agent",
    description=(
        "创建子智能体执行子任务。子智能体拥有独立的对话上下文，可使用文件、搜索、"
        "命令等工具完成任务后返回结果。适用于将复杂任务分解为独立的子任务并行处理。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "task": {
                "type": "string",
                "description": "子任务描述（尽量详细，包含所有必要上下文）",
            },
            "system_prompt": {
                "type": "string",
                "description": "子智能体的角色定义（可选，默认为通用编码助手）",
            },
            "role": {
                "type": "string",
                "description": (
                    "预定义角色名称（可选）：coding/research/review/debug，"
                    "也可使用工作区 .agents/ 中的自定义角色"
                ),
            },
            "tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "子智能体可用的工具列表（可选，默认为除 agent/parallel_agents "
                    "外的全部工具）"
                ),
            },
        },
        "required": ["task"],
    },
    timeout=600.0,
)
async def spawn_agent(ctx: Any, arguments: dict[str, Any]) -> str:
    """Run one tracked sub-task in an isolated conversation and DB session."""
    task_description = str(arguments.get("task", "")).strip()
    if not task_description:
        return "子任务描述不能为空。"

    parent_conversation_id = str(getattr(ctx, "conversation_id", "")).strip()
    if not parent_conversation_id:
        return "子智能体执行失败：缺少父会话 ID。"

    custom_prompt = arguments.get("system_prompt")
    allowed_tools = arguments.get("tools")
    role_name = str(arguments.get("role") or "").strip()
    ctx_extra = getattr(ctx, "extra", None)
    ctx_extra = ctx_extra if isinstance(ctx_extra, dict) else {}
    parent_task_id = arguments.get("_parent_task_id") or ctx_extra.get("agent_task_id")
    parent_run_id = arguments.get("_parent_run_id") or ctx_extra.get("agent_run_id")

    # Local imports avoid cycles while tool modules register at package import time.
    import uuid

    from app.core.config import AgentConfig
    from app.core.db import async_session_factory
    from app.models import Conversation, Message
    from app.modules.agents.roles.registry import role_registry
    from app.modules.agents.runner import (
        AgentRunner,
        register_runner,
        unregister_runner,
    )
    from app.modules.agents.shared_context import shared_context
    from app.modules.tasks.manager import TaskManager
    from app.modules.tools.registry import get_registry
    from app.pipeline.chat_pipeline import ChatContext, ChatPipeline

    parent_config = ctx_extra.get("_agent_config")
    if not isinstance(parent_config, AgentConfig):
        parent_config = AgentConfig(
            current_depth=int(ctx_extra.get("agent_current_depth", 0) or 0),
            max_depth=int(ctx_extra.get("agent_max_depth", 3) or 3),
        )
    parent_depth = max(parent_config.current_depth, 0)
    max_depth = max(parent_config.max_depth, 0)
    if parent_depth >= max_depth:
        return "已达最大嵌套深度"
    child_depth = parent_depth + 1

    context_workspace_dir = sandbox.get_context_workspace_dir(ctx)

    async with async_session_factory() as sub_session:
        manager = TaskManager(sub_session)
        task_id: str | None = None
        run_id: str | None = None
        runner: AgentRunner | None = None
        sub_ctx: ChatContext | None = None

        async def finish_records(status: str, result: str | None = None) -> None:
            if task_id:
                await manager.update_task_status(task_id, status, result)
            if run_id:
                await manager.update_agent_run(
                    run_id,
                    status,
                    tool_rounds=runner.current_round if runner else None,
                    token_usage=sub_ctx.usage if sub_ctx else None,
                )
            await sub_session.commit()

        try:
            parent_conversation = await sub_session.get(
                Conversation, parent_conversation_id
            )
            workspace_dir = context_workspace_dir or (
                parent_conversation.workspace_dir if parent_conversation else None
            )

            role = None
            if role_name:
                if workspace_dir:
                    role_registry.load_from_workspace(workspace_dir)
                role = role_registry.get(role_name)
                if role is None:
                    available = ", ".join(
                        sorted(item.name for item in role_registry.list_roles())
                    )
                    return (
                        f"子智能体执行失败：未知角色 {role_name}。"
                        f"可用角色：{available}"
                    )

            role_prompt = role.system_prompt.strip() if role else ""
            custom_prompt_text = (
                str(custom_prompt).strip() if custom_prompt else ""
            )
            if role_prompt and custom_prompt_text:
                sub_system_prompt = (
                    f"{role_prompt}\n\n[附加角色指令]\n{custom_prompt_text}"
                )
            else:
                sub_system_prompt = (
                    role_prompt or custom_prompt_text or _DEFAULT_SYSTEM_PROMPT
                )

            # A role is a hard capability ceiling. Parent and caller tool lists
            # may narrow it further, but can never widen it.
            all_tools = set(get_registry().names())
            requested_tools = (
                {str(name) for name in allowed_tools if str(name).strip()}
                if isinstance(allowed_tools, list)
                else None
            )
            parent_allowed_value = ctx_extra.get("allowed_tools")
            parent_allowed_tools = (
                {str(name) for name in parent_allowed_value}
                if isinstance(parent_allowed_value, list)
                else None
            )
            if role is not None:
                effective_tools = set(role.tools)
                if requested_tools is not None:
                    effective_tools &= requested_tools
            elif requested_tools is not None:
                effective_tools = requested_tools
            elif parent_allowed_tools is not None:
                effective_tools = set(parent_allowed_tools)
            else:
                effective_tools = set(all_tools)
            effective_tools &= all_tools
            if parent_allowed_tools is not None:
                effective_tools &= parent_allowed_tools
            if role is not None and role.read_only:
                effective_tools -= _MUTATING_TOOL_NAMES
            if child_depth >= max_depth:
                effective_tools -= _AGENT_TOOL_NAMES
            exclude_tools = all_tools - effective_tools

            sub_conv = Conversation(
                id=uuid.uuid4().hex,
                user_id=getattr(ctx, "user_id", "local"),
                title=f"sub-agent: {task_description[:30]}",
                system_prompt=sub_system_prompt,
                provider_id=getattr(ctx, "provider_id", None),
                model_name=(
                    role.model_preference
                    if role is not None and role.model_preference
                    else getattr(ctx, "model_name", None)
                ),
                workspace_dir=workspace_dir,
                agent_type="sub_agent",
            )
            sub_session.add(sub_conv)
            sub_session.add(
                Message(
                    id=uuid.uuid4().hex,
                    conversation_id=sub_conv.id,
                    role="user",
                    content=task_description,
                )
            )
            await sub_session.commit()

            task_record = await manager.create_task(
                conversation_id=parent_conversation_id,
                description=task_description,
                parent_task_id=str(parent_task_id) if parent_task_id else None,
            )
            task_id = task_record.id
            await manager.update_task_status(task_id, "running")
            run_record = await manager.create_agent_run(
                conversation_id=parent_conversation_id,
                task_id=task_id,
                agent_type=role.name if role is not None else "agent",
                model_name=(
                    role.model_preference
                    if role is not None and role.model_preference
                    else getattr(ctx, "model_name", None)
                ),
                parent_run_id=str(parent_run_id) if parent_run_id else None,
                workspace_dir=workspace_dir,
            )
            run_id = run_record.id
            task_record.agent_run_id = run_id
            await sub_session.commit()

            pipeline = ChatPipeline(sub_session)
            sub_ctx = ChatContext(
                conversation_id=sub_conv.id,
                user_id=sub_conv.user_id,
                user_message=task_description,
            )
            sub_ctx.extra["event_conversation_id"] = parent_conversation_id
            sub_ctx.extra["agent_task_id"] = task_id
            sub_ctx.extra["agent_run_id"] = run_id
            sub_ctx.extra["shared_conversation_id"] = parent_conversation_id
            sub_ctx.extra["shared_agent_id"] = sub_conv.id
            sub_ctx.extra["shared_agent_type"] = (
                role.name if role is not None else "sub_agent"
            )
            await pipeline.load_history(sub_ctx)
            await pipeline.select_model(sub_ctx)
            run_record.model_name = sub_ctx.model_name
            await sub_session.commit()

            tools_payload = get_registry().build_openai_tools(exclude=exclude_tools)
            parent_max_rounds = parent_config.max_tool_rounds
            sub_agent_rounds = (
                min(max(role.max_tool_rounds, 1), parent_max_rounds)
                if role is not None
                else max(parent_max_rounds // 2, 5)
            )
            sub_agent_config = AgentConfig(
                max_tool_rounds=sub_agent_rounds,
                max_tool_result_chars=parent_config.max_tool_result_chars,
                allowed_tools=sorted(effective_tools),
                workspace_dir=workspace_dir,
                context_max_tokens=parent_config.context_max_tokens,
                context_compress_threshold=parent_config.context_compress_threshold,
                context_keep_recent=parent_config.context_keep_recent,
                current_depth=child_depth,
                max_depth=max_depth,
            )
            runner = AgentRunner(sub_agent_config)
            register_runner(run_id, runner)
            async for _event in runner.run(pipeline, sub_ctx, tools_payload):
                pass

            await pipeline.persist(sub_ctx)
            raw_result = sub_ctx.response_text or "子智能体未产生回复。"
            result = (
                _normalize_review_result(raw_result)
                if role is not None and role.name == "review"
                else raw_result
            )
            await shared_context.publish(
                parent_conversation_id,
                sub_conv.id,
                role.name if role is not None else "sub_agent",
                "agent_output",
                result,
            )
            final_status = "cancelled" if runner.status == "cancelled" else "completed"
            await finish_records(final_status, result)
            if final_status == "cancelled":
                return f"子智能体已取消：{result}"
            if role is not None and role.name == "review":
                return result
            return f"[子智能体完成]\n{result}"
        except asyncio.CancelledError:
            await sub_session.rollback()
            try:
                await finish_records("cancelled", "子智能体执行已取消。")
            except Exception:
                logger.warning("记录子智能体取消状态失败", exc_info=True)
            raise
        except Exception as exc:
            await sub_session.rollback()
            try:
                await finish_records(
                    "failed", f"{exc.__class__.__name__}: {exc}"
                )
            except Exception:
                logger.warning("记录子智能体失败状态失败", exc_info=True)
            logger.warning("子智能体执行失败：%s", exc, exc_info=True)
            return f"子智能体执行失败：{exc.__class__.__name__}: {exc}"
        finally:
            if run_id:
                unregister_runner(run_id)


@tool(
    name="parallel_agents",
    description=(
        "并行创建多个子智能体执行多个独立子任务。每个子任务由独立的子智能体处理，"
        "所有子任务并行执行。返回所有子任务的结果汇总。"
    ),
    parameters={
        "type": "object",
        "properties": {
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string", "description": "子任务描述"},
                        "system_prompt": {
                            "type": "string",
                            "description": "子智能体角色（可选）",
                        },
                        "role": {
                            "type": "string",
                            "description": "预定义或自定义角色名称（可选）",
                        },
                        "tools": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "进一步限制子智能体工具（可选）",
                        },
                    },
                    "required": ["task"],
                },
                "description": "子任务列表，每个子任务将由独立的子智能体并行处理",
            }
        },
        "required": ["tasks"],
    },
    timeout=900.0,
)
async def parallel_agents_handler(ctx: Any, arguments: dict[str, Any]) -> str:
    """Run and track up to five independent sub-agents concurrently."""
    tasks_list = arguments.get("tasks", [])
    if not isinstance(tasks_list, list) or not tasks_list:
        return "任务列表不能为空。"
    if len(tasks_list) > 5:
        return "并行子任务数量上限为 5 个，请减少任务数量。"

    normalized_tasks = [task if isinstance(task, dict) else {} for task in tasks_list]
    parent_conversation_id = str(getattr(ctx, "conversation_id", "")).strip()
    if not parent_conversation_id:
        return "并行子智能体执行失败：缺少父会话 ID。"

    from app.core.db import async_session_factory
    from app.models import Conversation
    from app.modules.tasks.manager import TaskManager

    async with async_session_factory() as session:
        manager = TaskManager(session)
        parent_task_id: str | None = None
        parent_run_id: str | None = None

        async def finish_parent(status: str, result: str | None = None) -> None:
            if parent_task_id:
                await manager.update_task_status(parent_task_id, status, result)
            if parent_run_id:
                await manager.update_agent_run(parent_run_id, status)
            await session.commit()

        try:
            conversation = await session.get(Conversation, parent_conversation_id)
            workspace_dir = conversation.workspace_dir if conversation else None
            descriptions = [
                str(task_def.get("task", "")).strip()
                for task_def in normalized_tasks
            ]
            parent_task = await manager.create_task(
                conversation_id=parent_conversation_id,
                description="并行执行子任务：" + "；".join(descriptions),
            )
            parent_task_id = parent_task.id
            await manager.update_task_status(parent_task_id, "running")
            parent_run = await manager.create_agent_run(
                conversation_id=parent_conversation_id,
                task_id=parent_task_id,
                agent_type="parallel_agents",
                model_name=getattr(ctx, "model_name", None),
                workspace_dir=workspace_dir,
            )
            parent_run_id = parent_run.id
            parent_task.agent_run_id = parent_run_id
            await session.commit()

            results = await asyncio.gather(
                *(
                    spawn_agent(
                        ctx,
                        {
                            "task": task_def.get("task", ""),
                            "system_prompt": task_def.get("system_prompt"),
                            "role": task_def.get("role"),
                            "tools": task_def.get("tools"),
                            "_parent_task_id": parent_task_id,
                            "_parent_run_id": parent_run_id,
                        },
                    )
                    for task_def in normalized_tasks
                ),
                return_exceptions=True,
            )

            parts: list[str] = []
            failed = False
            for index, (task_def, result) in enumerate(
                zip(normalized_tasks, results), start=1
            ):
                task_desc = str(task_def.get("task", ""))[:50]
                if isinstance(result, BaseException):
                    failed = True
                    parts.append(
                        f"### 子任务 {index}：{task_desc}\n执行失败：{result}"
                    )
                else:
                    result_text = str(result)
                    failed = failed or result_text.startswith("子智能体执行失败：")
                    parts.append(f"### 子任务 {index}：{task_desc}\n{result_text}")

            summary = "\n\n---\n\n".join(parts)
            await finish_parent("failed" if failed else "completed", summary)
            return summary
        except asyncio.CancelledError:
            await session.rollback()
            try:
                await finish_parent("cancelled", "并行子智能体执行已取消。")
            except Exception:
                logger.warning("记录并行子智能体取消状态失败", exc_info=True)
            raise
        except Exception as exc:
            await session.rollback()
            try:
                await finish_parent(
                    "failed", f"{exc.__class__.__name__}: {exc}"
                )
            except Exception:
                logger.warning("记录并行子智能体失败状态失败", exc_info=True)
            logger.warning("并行子智能体执行失败：%s", exc, exc_info=True)
            return f"并行子智能体执行失败：{exc.__class__.__name__}: {exc}"
