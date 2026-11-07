"""文件读取、写入与精确搜索替换工具。"""

import asyncio
import itertools
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.modules.agents.events import AgentEvent, event_bus
from app.modules.tools import sandbox
from app.modules.tools.registry import tool


def _event_conversation_id(ctx: Any) -> str:
    extra = getattr(ctx, "extra", {})
    parent_id = extra.get("event_conversation_id") if isinstance(extra, dict) else None
    return str(parent_id or getattr(ctx, "conversation_id", ""))


def _parse_optional_line_number(value: Any, name: str) -> tuple[int | None, str | None]:
    """解析可选行号，失败时返回中文错误。"""
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, f"读取失败：{name} 必须是正整数。"
    try:
        line_number = int(value)
    except (TypeError, ValueError):
        return None, f"读取失败：{name} 必须是正整数。"
    if line_number < 1:
        return None, f"读取失败：{name} 必须从 1 开始。"
    return line_number, None


def _number_lines(lines: list[str], first_line: int) -> str:
    """为文本行添加右对齐的行号。"""
    return "\n".join(
        f"{line_number:>6} | {line}"
        for line_number, line in enumerate(lines, start=first_line)
    )


def _truncate_read_result(output: str, total_lines: int) -> str:
    """按工具结果上限截断读取结果，并附带文件行数说明。"""
    if len(output) <= settings.max_tool_result_chars:
        return output
    truncated = output[:settings.max_tool_result_chars]
    shown_lines = truncated.count("\n") + (1 if truncated else 0)
    return (
        f"{truncated}\n... (截断：文件共 {total_lines} 行，"
        f"已显示 {shown_lines} 行)"
    )


@tool(
    name="file_read",
    description="读取文件内容。支持通过行号范围读取部分内容。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "start_line": {
                "type": "integer",
                "description": "起始行号（从1开始，可选）",
            },
            "end_line": {
                "type": "integer",
                "description": "结束行号（包含，可选）",
            },
        },
        "required": ["path"],
    },
    timeout=15.0,
)
async def file_read(ctx: Any, arguments: dict[str, Any]) -> str:
    path = str(arguments.get("path") or "").strip()
    if not path:
        return "读取失败：文件路径为空。"

    workspace_dir = sandbox.get_context_workspace_dir(ctx)
    # 相对路径先按工作区根目录展开，再校验与读写（与 bash 工具行为一致）
    path = sandbox.resolve_workspace_path(path, workspace_dir)
    validation_error = sandbox.validate_path(
        path, extra_allowed_dirs=[workspace_dir] if workspace_dir else None
    )
    if validation_error is not None:
        return validation_error

    start_line, error = _parse_optional_line_number(
        arguments.get("start_line"), "start_line"
    )
    if error is not None:
        return error
    end_line, error = _parse_optional_line_number(arguments.get("end_line"), "end_line")
    if error is not None:
        return error
    if start_line is not None and end_line is not None and end_line < start_line:
        return "读取失败：end_line 不能小于 start_line。"

    file_path = Path(path)
    try:
        content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
        lines = content.splitlines()
        total_lines = len(lines)
        first_line = start_line or 1
        if first_line > total_lines:
            return f"读取提示：start_line（{first_line}）超出文件总行数（{total_lines}），文件路径：{path}"
        stop_line = end_line if end_line is not None else total_lines
        selected_lines = list(
            itertools.islice(lines, first_line - 1, max(stop_line, first_line - 1))
        )
        output = _number_lines(selected_lines, first_line)
        return _truncate_read_result(output, total_lines)
    except FileNotFoundError:
        return f"读取失败：文件不存在：{path}"
    except IsADirectoryError:
        return f"读取失败：路径是目录而不是文件：{path}"
    except UnicodeDecodeError:
        return f"读取失败：文件不是有效的 UTF-8 文本：{path}"
    except PermissionError:
        return f"读取失败：没有权限读取文件：{path}"
    except OSError as exc:
        return f"读取失败：{exc}"
    except Exception as exc:
        return f"读取失败：{exc.__class__.__name__}：{exc}"


@tool(
    name="file_write",
    description="创建或覆写文件。会自动创建不存在的父目录。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "content": {"type": "string", "description": "要写入的文件内容"},
        },
        "required": ["path", "content"],
    },
    timeout=15.0,
)
async def file_write(ctx: Any, arguments: dict[str, Any]) -> str:
    path = str(arguments.get("path") or "").strip()
    if not path:
        return "写入失败：文件路径为空。"
    content = arguments.get("content")
    if not isinstance(content, str):
        return "写入失败：content 必须是字符串。"

    workspace_dir = sandbox.get_context_workspace_dir(ctx)
    # 相对路径先按工作区根目录展开，再校验与读写（与 bash 工具行为一致）
    path = sandbox.resolve_workspace_path(path, workspace_dir)
    validation_error = sandbox.validate_path(
        path, extra_allowed_dirs=[workspace_dir] if workspace_dir else None
    )
    if validation_error is not None:
        return validation_error

    try:
        content_size = len(content.encode("utf-8"))
        max_file_size = sandbox.get_sandbox_config().max_file_size
        if content_size > max_file_size:
            return (
                f"写入失败：内容大小 {content_size} 字节超过限制 "
                f"{max_file_size} 字节。"
            )

        file_path = Path(path)
        old_content = (
            await asyncio.to_thread(file_path.read_text, encoding="utf-8")
            if file_path.exists()
            else ""
        )
        await asyncio.to_thread(file_path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(file_path.write_text, content, encoding="utf-8")
        conversation_id = _event_conversation_id(ctx)
        if conversation_id:
            await event_bus.publish(
                AgentEvent(
                    type="fileChanged",
                    data={
                        "path": path,
                        "changeType": "write",
                        "oldContent": old_content,
                        "newContent": content,
                    },
                    conversation_id=conversation_id,
                )
            )
        return f"已写入 {path}（{len(content)} 字符）"
    except IsADirectoryError:
        return f"写入失败：路径是目录而不是文件：{path}"
    except PermissionError:
        return f"写入失败：没有权限写入文件：{path}"
    except UnicodeEncodeError:
        return f"写入失败：内容无法编码为 UTF-8：{path}"
    except OSError as exc:
        return f"写入失败：{exc}"
    except Exception as exc:
        return f"写入失败：{exc.__class__.__name__}：{exc}"


@tool(
    name="file_edit",
    description="通过搜索替换编辑文件。old_text 必须精确匹配文件中的内容（包括空白和缩进），且只能匹配一处。",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径"},
            "old_text": {
                "type": "string",
                "description": "要被替换的原始文本（必须精确匹配）",
            },
            "new_text": {"type": "string", "description": "替换后的新文本"},
        },
        "required": ["path", "old_text", "new_text"],
    },
    timeout=15.0,
)
async def file_edit(ctx: Any, arguments: dict[str, Any]) -> str:
    path = str(arguments.get("path") or "").strip()
    if not path:
        return "编辑失败：文件路径为空。"
    old_text = arguments.get("old_text")
    new_text = arguments.get("new_text")
    if not isinstance(old_text, str) or not isinstance(new_text, str):
        return "编辑失败：old_text 和 new_text 必须是字符串。"
    if not old_text:
        return "编辑失败：old_text 不能为空。"

    workspace_dir = sandbox.get_context_workspace_dir(ctx)
    # 相对路径先按工作区根目录展开，再校验与读写（与 bash 工具行为一致）
    path = sandbox.resolve_workspace_path(path, workspace_dir)
    validation_error = sandbox.validate_path(
        path, extra_allowed_dirs=[workspace_dir] if workspace_dir else None
    )
    if validation_error is not None:
        return validation_error

    file_path = Path(path)
    try:
        content = await asyncio.to_thread(file_path.read_text, encoding="utf-8")
        occurrence_count = content.count(old_text)
        if occurrence_count == 0:
            context_lines = list(itertools.islice(content.splitlines(), 50))
            context = _number_lines(context_lines, 1)
            return (
                "编辑失败：未找到 old_text 的精确匹配。"
                f"\n文件前 {len(context_lines)} 行：\n{context}"
            )
        if occurrence_count > 1:
            line_numbers: list[int] = []
            search_from = 0
            while True:
                match_at = content.find(old_text, search_from)
                if match_at < 0:
                    break
                line_numbers.append(content.count("\n", 0, match_at) + 1)
                search_from = match_at + len(old_text)
            lines_text = ", ".join(str(number) for number in line_numbers)
            return (
                f"编辑失败：old_text 匹配了 {occurrence_count} 处，必须只匹配一处。"
                f"匹配行号：{lines_text}"
            )

        updated_content = content.replace(old_text, new_text, 1)
        updated_size = len(updated_content.encode("utf-8"))
        max_file_size = sandbox.get_sandbox_config().max_file_size
        if updated_size > max_file_size:
            return (
                f"编辑失败：替换后文件大小 {updated_size} 字节超过限制 "
                f"{max_file_size} 字节。"
            )
        await asyncio.to_thread(file_path.write_text, updated_content, encoding="utf-8")
        conversation_id = _event_conversation_id(ctx)
        if conversation_id:
            await event_bus.publish(
                AgentEvent(
                    type="fileChanged",
                    data={
                        "path": path,
                        "changeType": "edit",
                        "oldContent": content,
                        "newContent": updated_content,
                    },
                    conversation_id=conversation_id,
                )
            )
        return f"已编辑 {path}（替换 1 处）"
    except FileNotFoundError:
        return f"编辑失败：文件不存在：{path}"
    except IsADirectoryError:
        return f"编辑失败：路径是目录而不是文件：{path}"
    except UnicodeDecodeError:
        return f"编辑失败：文件不是有效的 UTF-8 文本：{path}"
    except PermissionError:
        return f"编辑失败：没有权限编辑文件：{path}"
    except OSError as exc:
        return f"编辑失败：{exc}"
    except Exception as exc:
        return f"编辑失败：{exc.__class__.__name__}：{exc}"
