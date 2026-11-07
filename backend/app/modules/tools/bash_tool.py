"""受沙箱策略约束、支持超时后台化的 Shell 命令执行工具。"""

import asyncio
import json
import time
import uuid
from typing import Any

from app.core.config import settings
from app.modules.tools import sandbox
from app.modules.tools.registry import tool


_background_tasks: dict[str, dict[str, Any]] = {}


def _decode_output(value: bytes) -> str:
    return value.decode(encoding="utf-8", errors="replace")


def _completed_output(
    stdout: bytes, stderr: bytes, returncode: int | None
) -> dict[str, Any]:
    return {
        "stdout": _decode_output(stdout),
        "stderr": _decode_output(stderr),
        "returncode": returncode,
    }


async def _collect_background(
    task_id: str,
    process: asyncio.subprocess.Process,
    communication_task: asyncio.Task[tuple[bytes, bytes]],
) -> None:
    """Collect a backgrounded process using its original communicate task."""
    try:
        stdout, stderr = await communication_task
        task = _background_tasks.get(task_id)
        if task is not None:
            task["status"] = "completed"
            task["output"] = _completed_output(stdout, stderr, process.returncode)
            task["completed_at"] = time.time()
    except Exception as exc:
        task = _background_tasks.get(task_id)
        if task is not None:
            task["status"] = "failed"
            task["output"] = {"error": f"{exc.__class__.__name__}: {exc}"}
            task["completed_at"] = time.time()


async def _run_with_background(
    command: str, timeout: int, cwd: str
) -> dict[str, Any]:
    """执行命令；超时后保留进程并转入进程级后台任务表。"""
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    communication_task = asyncio.create_task(process.communicate())
    try:
        stdout, stderr = await asyncio.wait_for(
            asyncio.shield(communication_task), timeout=timeout
        )
        return {
            "status": "completed",
            **_completed_output(stdout, stderr, process.returncode),
        }
    except asyncio.TimeoutError:
        task_id = uuid.uuid4().hex[:12]
        _background_tasks[task_id] = {
            "process": process,
            "communication_task": communication_task,
            "status": "running",
            "started_at": time.time(),
            "output": None,
        }
        asyncio.create_task(
            _collect_background(task_id, process, communication_task)
        )
        return {
            "status": "backgrounded",
            "background_task_id": task_id,
            "message": (
                f"命令已超时({timeout}s)但仍在后台运行，"
                "可用 task_id 查询状态"
            ),
        }


@tool(
    name="bash",
    description="执行 Shell 命令并返回输出；超时后自动转入后台运行。",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "要执行的命令"},
            "timeout": {
                "type": "integer",
                "description": "超时时间（秒，可选，默认 60，上限 120）",
            },
            "working_dir": {
                "type": "string",
                "description": "工作目录（可选，默认为配置的工作目录）",
            },
        },
        "required": ["command"],
    },
    timeout=130.0,
)
async def bash(ctx: Any, arguments: dict[str, Any]) -> str:
    command = str(arguments.get("command") or "")
    validation_error = sandbox.validate_command(command)
    if validation_error is not None:
        return validation_error
    if not command.strip():
        return "命令执行失败：命令为空。"

    timeout_value = arguments.get("timeout", 60)
    if isinstance(timeout_value, bool):
        return "命令执行失败：timeout 必须是正整数。"
    try:
        user_timeout = int(timeout_value)
    except (TypeError, ValueError):
        return "命令执行失败：timeout 必须是正整数。"
    if user_timeout < 1:
        return "命令执行失败：timeout 必须大于 0。"
    user_timeout = min(user_timeout, 120)

    workspace_dir = sandbox.get_context_workspace_dir(ctx)
    extra_allowed_dirs = [workspace_dir] if workspace_dir else None
    working_dir_value = arguments.get("working_dir")
    if working_dir_value is None:
        working_dir = workspace_dir or settings.workspace_dir
    else:
        working_dir = str(working_dir_value).strip()
        if not working_dir:
            return "命令执行失败：working_dir 不能为空。"
    validation_error = sandbox.validate_path(
        working_dir, extra_allowed_dirs=extra_allowed_dirs
    )
    if validation_error is not None:
        return validation_error

    try:
        result = await _run_with_background(command, user_timeout, working_dir)
        return json.dumps(result, ensure_ascii=False)
    except FileNotFoundError:
        return f"命令执行失败：工作目录不存在：{working_dir}"
    except NotADirectoryError:
        return f"命令执行失败：工作目录不是目录：{working_dir}"
    except PermissionError:
        return f"命令执行失败：没有权限访问工作目录：{working_dir}"
    except OSError as exc:
        return f"命令执行失败：{exc}"
    except Exception as exc:
        return f"命令执行失败：{exc.__class__.__name__}：{exc}"


@tool(
    name="check_background_task",
    description="查询 bash 超时后转入后台运行的任务状态。",
    parameters={
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "bash 返回的 background_task_id",
            }
        },
        "required": ["task_id"],
    },
)
async def check_background_task(ctx: Any, arguments: dict[str, Any]) -> str:
    del ctx
    task_id = str(arguments.get("task_id") or "").strip()
    if not task_id:
        return json.dumps(
            {"status": "error", "message": "task_id 不能为空"},
            ensure_ascii=False,
        )

    task = _background_tasks.get(task_id)
    if task is None:
        return json.dumps(
            {
                "status": "not_found",
                "background_task_id": task_id,
                "message": "未找到后台任务",
            },
            ensure_ascii=False,
        )

    response: dict[str, Any] = {
        "status": task["status"],
        "background_task_id": task_id,
        "started_at": task["started_at"],
    }
    if task["status"] == "running":
        response["elapsed_seconds"] = round(time.time() - task["started_at"], 3)
    else:
        response["output"] = task["output"]
        response["completed_at"] = task.get("completed_at")
    return json.dumps(response, ensure_ascii=False)
