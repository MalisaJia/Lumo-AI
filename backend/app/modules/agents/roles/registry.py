"""角色注册表 — 管理内置和自定义角色配置。"""

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class AgentRole:
    name: str
    display_name: str
    description: str
    system_prompt: str
    tools: list[str]
    model_preference: str | None = None
    read_only: bool = False
    max_tool_rounds: int = 30


BUILTIN_ROLES: dict[str, AgentRole] = {
    "coding": AgentRole(
        name="coding",
        display_name="编程助手",
        description="全栈编程代理，可读写文件、执行命令",
        system_prompt="",
        tools=[
            "file_read",
            "file_write",
            "file_edit",
            "glob",
            "grep",
            "bash",
            "agent",
            "parallel_agents",
            "web_search",
            "calculator",
            "current_time",
            "ask_user",
            "publish_context",
            "read_shared_context",
            "check_background_task",
        ],
    ),
    "research": AgentRole(
        name="research",
        display_name="调研分析",
        description="只读调研代理，搜索和分析代码但不修改",
        system_prompt=(
            "你是一个调研分析代理。你的任务是搜索、阅读和分析代码及文档，"
            "然后提供结构化报告。你不应该修改任何文件。"
        ),
        tools=[
            "file_read",
            "glob",
            "grep",
            "web_search",
            "publish_context",
            "read_shared_context",
        ],
        read_only=True,
    ),
    "review": AgentRole(
        name="review",
        display_name="代码审查",
        description="代码审查代理，检查代码质量和潜在问题",
        system_prompt=(
            "你是一个代码审查代理。仔细审查代码变更，检查逻辑错误、安全漏洞、"
            "性能问题和代码风格。只输出合法 JSON 对象，格式为 "
            '{"findings":[{"severity":"high|medium|low|info",'
            '"file":"文件路径","line":行号或null,"message":"问题说明"}]}。'
            '没有问题时输出 {"findings":[]}，不要输出 Markdown 代码块或额外文字。'
        ),
        tools=["file_read", "glob", "grep", "publish_context"],
        read_only=True,
    ),
    "debug": AgentRole(
        name="debug",
        display_name="调试专家",
        description="调试代理，诊断和修复问题",
        system_prompt=(
            "你是一个调试专家。系统地诊断问题：重现 → 隔离 → 定位根因 → 修复 → 验证。"
        ),
        tools=[
            "file_read",
            "file_write",
            "file_edit",
            "glob",
            "grep",
            "bash",
            "publish_context",
            "read_shared_context",
        ],
    ),
}


class RoleRegistry:
    def __init__(self):
        self._roles: dict[str, AgentRole] = dict(BUILTIN_ROLES)

    def get(self, name: str) -> AgentRole | None:
        return self._roles.get(name)

    def register(self, role: AgentRole):
        self._roles[role.name] = role

    def list_roles(self) -> list[AgentRole]:
        return list(self._roles.values())

    def load_from_workspace(self, workspace_dir: str):
        """从工作区 .agents/ 目录加载自定义角色（Markdown 格式）。"""
        agents_dir = Path(workspace_dir) / ".agents"
        if not agents_dir.is_dir():
            return
        for md_file in agents_dir.glob("*.md"):
            try:
                role = self._parse_role_markdown(md_file)
                if role:
                    self._roles[role.name] = role
                    logger.info("Loaded custom agent role: %s", role.name)
            except Exception as exc:
                logger.warning("Failed to load role %s: %s", md_file.name, exc)

    def _parse_role_markdown(self, path: Path) -> AgentRole | None:
        """解析 Markdown 角色文件。格式：YAML frontmatter + Markdown body as system prompt。"""
        content = path.read_text(encoding="utf-8", errors="replace")
        if not content.startswith("---"):
            return None
        parts = content.split("---", 2)
        if len(parts) < 3:
            return None

        import yaml

        meta = yaml.safe_load(parts[1]) or {}
        if not isinstance(meta, dict):
            return None
        body = parts[2].strip()
        tools = meta.get("tools", [])
        if not isinstance(tools, list):
            tools = []

        return AgentRole(
            name=str(meta.get("name") or path.stem),
            display_name=str(meta.get("display_name") or path.stem),
            description=str(meta.get("description") or ""),
            system_prompt=body,
            tools=[str(name) for name in tools if str(name).strip()],
            model_preference=(
                str(meta["model"]) if meta.get("model") is not None else None
            ),
            read_only=bool(meta.get("read_only", False)),
            max_tool_rounds=max(int(meta.get("max_tool_rounds", 30)), 1),
        )


role_registry = RoleRegistry()
