"""分层权限引擎 — 参考 Claude Code 的 Tool(pattern) 规则系统。

规则格式：
  {"tool": "bash", "decision": "ask"}           — bash 工具需要确认
  {"tool": "bash(rm *)", "decision": "deny"}     — 包含 rm 的 bash 命令拒绝
  {"tool": "file_write", "decision": "allow"}    — 文件写入自动允许
  {"tool": "*", "decision": "allow"}             — 默认允许所有

优先级：deny > ask > allow（同一工具多条规则时）
"""

import asyncio
import logging
import re
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass
class PermissionRule:
    tool: str
    decision: str
    reason: str = ""


DEFAULT_RULES: list[PermissionRule] = [
    PermissionRule(tool="bash(rm *)", decision="deny", reason="禁止执行删除命令"),
    PermissionRule(
        tool="bash(rmdir *)", decision="deny", reason="禁止执行删除目录命令"
    ),
    PermissionRule(tool="bash(format *)", decision="deny", reason="禁止格式化命令"),
    PermissionRule(tool="bash(del *)", decision="deny", reason="禁止 Windows 删除命令"),
    PermissionRule(
        tool="bash(rd *)", decision="deny", reason="禁止 Windows 删除目录命令"
    ),
    PermissionRule(tool="*", decision="allow"),
]


class PermissionEngine:
    """Evaluate layered tool rules without coupling policy to tool handlers."""

    def __init__(self, rules: list[PermissionRule] | None = None):
        self.rules = list(DEFAULT_RULES if rules is None else rules)

    def evaluate(
        self, tool_name: str, tool_args: dict | None = None
    ) -> tuple[str, str]:
        """评估权限并返回 (decision, reason)。"""
        matches = [
            rule
            for rule in self.rules
            if self._matches(rule.tool, tool_name, tool_args)
        ]
        for decision in ("deny", "ask", "allow"):
            for match in matches:
                if match.decision == decision:
                    return (match.decision, match.reason)
        return ("allow", "")

    def _matches(
        self, pattern: str, tool_name: str, tool_args: dict | None
    ) -> bool:
        if pattern == "*":
            return True

        paren_match = re.fullmatch(r"(\w+)\((.+)\)", pattern)
        if paren_match:
            pattern_tool, argument_pattern = paren_match.groups()
            if pattern_tool != tool_name or not tool_args:
                return False
            command = str(tool_args.get("command", ""))
            regex = re.escape(argument_pattern).replace(r"\*", ".*")
            return bool(re.search(regex, command, re.IGNORECASE))

        return pattern == tool_name


permission_engine = PermissionEngine()


# Pending confirmations: {confirmation_id: confirmation state}
_pending_confirmations: dict[str, dict] = {}


async def request_confirmation(
    sse_send: Callable[[dict], Awaitable[None]],
    action: str,
    description: str,
    risk_level: str,
    screenshot_base64: str | None = None,
    timeout: float = 60.0,
) -> tuple[bool, str]:
    """Send a confirmation request and block until the user responds or timeout."""
    conf_id = str(uuid.uuid4())
    event = asyncio.Event()
    _pending_confirmations[conf_id] = {
        "event": event,
        "approved": False,
        "reason": "",
    }

    await sse_send(
        {
            "type": "confirmationRequest",
            "id": conf_id,
            "action": action,
            "description": description,
            "risk_level": risk_level,
            "screenshot_base64": (
                screenshot_base64[:5000] if screenshot_base64 else None
            ),
        }
    )

    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
        result = _pending_confirmations[conf_id]
        return result["approved"], result["reason"]
    except asyncio.TimeoutError:
        return False, "Confirmation timed out (60s)"
    finally:
        _pending_confirmations.pop(conf_id, None)


def resolve_confirmation(conf_id: str, approved: bool, reason: str = "") -> bool:
    """Resolve a pending confirmation from an HTTP response."""
    if conf_id in _pending_confirmations:
        _pending_confirmations[conf_id]["approved"] = approved
        _pending_confirmations[conf_id]["reason"] = reason
        _pending_confirmations[conf_id]["event"].set()
        return True
    return False


RISK_LEVELS = {
    "screenshot": "low",
    "mouse_move": "low",
    "wait": "low",
    "mouse_click": "medium",
    "scroll": "medium",
    "drag": "medium",
    "keyboard_type": "high",
    "keyboard_hotkey": "high",
}

# Auto-approved action types for the lifetime of each conversation.
_session_approvals: dict[str, set[str]] = {}


def get_risk_level(action: str) -> str:
    """Return the configured risk level, defaulting unknown actions to high."""
    return RISK_LEVELS.get(action, "high")


def needs_confirmation(conversation_id: str, action: str, risk_level: str) -> bool:
    """Determine whether a computer use action requires user confirmation."""
    if risk_level == "low":
        return False
    if risk_level == "medium":
        approved_actions = _session_approvals.setdefault(conversation_id, set())
        return action not in approved_actions
    return True


def record_approval(conversation_id: str, action: str) -> None:
    """Record approval of an action type for the current conversation."""
    _session_approvals.setdefault(conversation_id, set()).add(action)


def clear_session_approvals(conversation_id: str) -> None:
    """Clear remembered approvals when a conversation session ends."""
    _session_approvals.pop(conversation_id, None)
