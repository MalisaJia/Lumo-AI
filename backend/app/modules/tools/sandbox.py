"""文件操作与命令执行的沙箱安全校验。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePath

from app.core.config import settings


@dataclass
class SandboxConfig:
    """沙箱目录白名单、命令黑名单与文件大小限制。"""

    allowed_dirs: list[Path]
    blocked_commands: list[str]
    max_file_size: int = 10_000_000


@lru_cache(maxsize=1)
def get_sandbox_config() -> SandboxConfig:
    """读取并缓存应用配置中的沙箱安全策略。"""
    allowed_dirs = [
        Path(item.strip()).resolve()
        for item in settings.sandbox_allowed_dirs.split(",")
        if item.strip()
    ]
    blocked_commands = [
        item.strip()
        for item in settings.sandbox_blocked_commands.split(",")
        if item.strip()
    ]
    return SandboxConfig(
        allowed_dirs=allowed_dirs,
        blocked_commands=blocked_commands,
    )


@lru_cache(maxsize=32)
def _compile_blocked_pattern(
    blocked_commands: tuple[str, ...],
) -> re.Pattern[str] | None:
    """将命令黑名单合并为一个正则表达式并缓存。"""
    if not blocked_commands:
        return None
    alternatives = (re.escape(command) for command in blocked_commands)
    return re.compile("|".join(alternatives), re.IGNORECASE)


def get_context_workspace_dir(ctx: object) -> str | None:
    """Return the per-run workspace stored on a ChatContext, when present."""
    extra = getattr(ctx, "extra", None)
    if not isinstance(extra, dict):
        return None
    value = extra.get("workspace_dir")
    if value is None:
        return None
    workspace_dir = str(value).strip()
    return workspace_dir or None


def resolve_workspace_path(path: str, workspace_dir: str | None = None) -> str:
    """将相对路径按工作区根目录解析为绝对路径，绝对路径原样返回。

    模型给出的相对路径语义上是相对工作区根目录的，而不是后端进程的当前
    工作目录；若直接交给 Path(path) 解析会按进程 CWD 展开，导致白名单校验
    必然失败。工作区根目录的取值与 bash 工具一致（本次运行的 workspace_dir
    优先，其次为配置项）。
    """
    raw = str(path or "").strip()
    if not raw:
        return raw
    candidate = Path(raw)
    if candidate.is_absolute():
        return raw
    root = str(workspace_dir or settings.workspace_dir or "").strip()
    if not root:
        return raw
    root_path = Path(root)
    if not root_path.is_absolute():
        # 配置项可以是相对启动目录的路径，先展开为绝对路径再拼接
        root_path = root_path.resolve()
    return str(root_path / candidate)


def validate_path(
    path: str | Path,
    config: SandboxConfig | None = None,
    extra_allowed_dirs: list[str] | None = None,
) -> str | None:
    """校验路径是否位于白名单目录内，失败时返回中文错误。"""
    try:
        sandbox_config = config or get_sandbox_config()
        allowed_dirs = list(sandbox_config.allowed_dirs)
        if extra_allowed_dirs:
            allowed_dirs.extend(
                Path(item.strip()).resolve()
                for item in extra_allowed_dirs
                if item and item.strip()
            )
        resolved_path = Path(path).resolve()
        if not allowed_dirs:
            return None
        if any(
            PurePath(resolved_path).is_relative_to(PurePath(allowed_dir))
            for allowed_dir in allowed_dirs
        ):
            return None
        return f"路径 {path} 不在允许的目录范围内"
    except Exception as exc:
        return f"路径 {path} 校验失败：{exc}"


def validate_command(
    cmd: str,
    config: SandboxConfig | None = None,
) -> str | None:
    """校验命令是否命中黑名单，失败时返回中文错误。"""
    try:
        sandbox_config = config or get_sandbox_config()
        pattern = _compile_blocked_pattern(tuple(sandbox_config.blocked_commands))
        if pattern is None:
            return None
        match = pattern.search(cmd)
        if match is None:
            return None
        return f"命令被安全策略阻止：包含被禁止的操作 '{match.group(0)}'"
    except Exception as exc:
        return f"命令安全校验失败：{exc}"
