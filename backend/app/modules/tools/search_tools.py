"""文件路径 glob 搜索与文件内容正则搜索工具。"""

import asyncio
import itertools
import re
import shutil
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.modules.tools import sandbox
from app.modules.tools.registry import tool

_RG_PATH = shutil.which("rg")
_MAX_GLOB_RESULTS = 2000


def _glob_paths(root: Path, pattern: str) -> tuple[list[Path], bool]:
    """在线程中执行 glob，并额外取一项判断结果是否被截断。"""
    matches = list(itertools.islice(root.glob(pattern), _MAX_GLOB_RESULTS + 1))
    return matches[:_MAX_GLOB_RESULTS], len(matches) > _MAX_GLOB_RESULTS


def _relative_display(path: Path, root: Path) -> str:
    """尽可能返回相对搜索根目录的可读路径。"""
    base = root if root.is_dir() else root.parent
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except (OSError, ValueError):
        return str(path)


def _python_grep(
    search_path: Path,
    compiled_pattern: re.Pattern[str],
    include: str | None,
) -> str:
    """ripgrep 不可用时，在线程中以 Python 正则递归搜索。"""
    if search_path.is_file():
        candidates = [search_path]
    else:
        candidates = search_path.rglob(include or "*")

    results: list[str] = []
    result_chars = 0
    base = search_path if search_path.is_dir() else search_path.parent
    for candidate in candidates:
        if not candidate.is_file():
            continue
        if include and search_path.is_file() and not candidate.match(include):
            continue
        try:
            with candidate.open("r", encoding="utf-8", errors="replace") as file:
                matches_in_file = 0
                for line_number, line in enumerate(file, start=1):
                    if compiled_pattern.search(line) is None:
                        continue
                    relative_path = _relative_display(candidate, base)
                    result = f"{relative_path}:{line_number}:{line.rstrip()}"
                    results.append(result)
                    result_chars += len(result) + 1
                    matches_in_file += 1
                    if result_chars >= settings.max_tool_result_chars:
                        return "\n".join(results)[:settings.max_tool_result_chars]
                    if matches_in_file >= 100:
                        break
        except (OSError, UnicodeError):
            continue
    return "\n".join(results)


def _normalize_rg_output(output: str, search_path: Path) -> str:
    """把 ripgrep 输出中的绝对路径转换为相对搜索根目录的路径。"""
    base = search_path if search_path.is_dir() else search_path.parent
    normalized: list[str] = []
    line_pattern = re.compile(r"^(.+?):(\d+):(.*)$")
    for line in output.splitlines():
        match = line_pattern.match(line)
        if match is None:
            normalized.append(line)
            continue
        file_name, line_number, content = match.groups()
        display_path = _relative_display(Path(file_name), base)
        normalized.append(f"{display_path}:{line_number}:{content}")
    return "\n".join(normalized)


@tool(
    name="glob",
    description="按 glob 模式搜索文件。返回匹配的文件路径列表，最多 2000 条。",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "glob 模式，例如 '**/*.py'",
            },
            "path": {
                "type": "string",
                "description": "搜索根目录（可选，默认为工作目录）",
            },
        },
        "required": ["pattern"],
    },
    timeout=15.0,
)
async def glob_search(ctx: Any, arguments: dict[str, Any]) -> str:
    pattern = str(arguments.get("pattern") or "").strip()
    if not pattern:
        return "文件搜索失败：glob 模式为空。"
    workspace_dir = sandbox.get_context_workspace_dir(ctx)
    path = str(arguments.get("path") or workspace_dir or settings.workspace_dir)
    if arguments.get("path"):
        # 显式传入的相对路径按工作区根目录展开（与 file_* / bash 工具一致）；
        # 未传 path 时维持上面的工作区默认值，行为不变
        path = sandbox.resolve_workspace_path(path, workspace_dir)

    validation_error = sandbox.validate_path(
        path, extra_allowed_dirs=[workspace_dir] if workspace_dir else None
    )
    if validation_error is not None:
        return validation_error

    root = Path(path)
    try:
        if not root.exists():
            return f"文件搜索失败：路径不存在：{path}"
        if not root.is_dir():
            return f"文件搜索失败：搜索根路径不是目录：{path}"
        matches, truncated = await asyncio.to_thread(_glob_paths, root, pattern)
        if not matches:
            return "未找到匹配的文件。"
        output = "\n".join(_relative_display(match, root) for match in matches)
        if truncated:
            output += "\n... (结果已截断，共显示 2000 条，可能还有更多匹配)"
        return output
    except (OSError, ValueError) as exc:
        return f"文件搜索失败：{exc}"
    except Exception as exc:
        return f"文件搜索失败：{exc.__class__.__name__}：{exc}"


@tool(
    name="grep",
    description="在文件中搜索匹配正则表达式的内容。返回匹配的 文件:行号:内容 列表。",
    parameters={
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "正则表达式模式"},
            "path": {
                "type": "string",
                "description": "搜索目录或文件路径（可选，默认为工作目录）",
            },
            "include": {
                "type": "string",
                "description": "文件名过滤 glob（可选，例如 '*.py'）",
            },
        },
        "required": ["pattern"],
    },
    timeout=30.0,
)
async def grep(ctx: Any, arguments: dict[str, Any]) -> str:
    pattern = str(arguments.get("pattern") or "")
    if not pattern:
        return "内容搜索失败：正则表达式为空。"
    workspace_dir = sandbox.get_context_workspace_dir(ctx)
    path = str(arguments.get("path") or workspace_dir or settings.workspace_dir)
    if arguments.get("path"):
        # 显式传入的相对路径按工作区根目录展开（与 file_* / bash 工具一致）；
        # 未传 path 时维持上面的工作区默认值，行为不变
        path = sandbox.resolve_workspace_path(path, workspace_dir)
    include_value = arguments.get("include")
    include = str(include_value).strip() if include_value is not None else None
    include = include or None

    validation_error = sandbox.validate_path(
        path, extra_allowed_dirs=[workspace_dir] if workspace_dir else None
    )
    if validation_error is not None:
        return validation_error

    search_path = Path(path)
    try:
        if not search_path.exists():
            return f"内容搜索失败：路径不存在：{path}"

        if _RG_PATH is None:
            try:
                compiled_pattern = re.compile(pattern)
            except re.error as exc:
                return f"内容搜索失败：正则表达式无效（{exc}）。"
            output = await asyncio.to_thread(
                _python_grep, search_path, compiled_pattern, include
            )
        else:
            cmd = [
                _RG_PATH,
                "--no-heading",
                "--with-filename",
                "--line-number",
                "--color",
                "never",
                "--max-count",
                "100",
            ]
            if include:
                cmd.extend(["--glob", include])
            cmd.extend([pattern, str(search_path)])
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=25
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                return "内容搜索超时：搜索命令执行时间过长，已终止进程。"
            except asyncio.CancelledError:
                process.kill()
                await process.wait()
                raise
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace").strip()
            if process.returncode not in (0, 1):
                return f"内容搜索失败：{stderr_text or f'ripgrep 退出码 {process.returncode}'}"
            output = _normalize_rg_output(stdout_text, search_path)

        if not output:
            return "未找到匹配内容。"
        return output[:settings.max_tool_result_chars]
    except PermissionError:
        return f"内容搜索失败：没有权限访问路径：{path}"
    except OSError as exc:
        return f"内容搜索失败：{exc}"
    except Exception as exc:
        return f"内容搜索失败：{exc.__class__.__name__}：{exc}"
