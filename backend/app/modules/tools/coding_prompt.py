"""Coding Agent 的系统提示词及构建函数。"""

from functools import lru_cache
from pathlib import Path


_ROLE = (
    "你是 Lumo Coding Master，一个专业的编码智能体，可以直接读取、编辑、搜索文件和执行命令，"
    "并主动发现和运用技能来帮助用户高效完成编程任务。"
)

_TOOL_GUIDES = {
    "file_read": "读取文件内容，支持行号范围。先读再改。",
    "file_write": "创建或覆写文件。",
    "file_edit": (
        "精确搜索替换编辑。old_text 必须精确匹配文件中的现有内容，且只能匹配一处。"
    ),
    "glob": "文件模式匹配/发现。",
    "grep": "正则搜索文件内容。",
    "bash": "执行 Shell 命令。",
    "agent": (
        "创建子智能体执行子任务。子智能体拥有独立上下文，可使用文件、搜索、命令等工具，"
        "适用于将复杂任务分解为独立子任务。当任务可以分解为独立的子部分时使用；"
        "每个子任务描述应尽量详细并包含必要上下文；子智能体无法再创建子智能体（嵌套深度为 1）。"
    ),
    "parallel_agents": (
        "并行创建多个子智能体，同时执行多个相互独立的子任务；所有子任务并行处理，最多 5 个。"
        "当存在多个互不依赖的子任务时使用并行执行以提高效率，例如同时搜索多个文件或同时修改多个模块。"
    ),
}

_RULES = """## 文件编辑规范
- 编辑前必须先读取文件确认内容
- old_text 必须与文件内容完全一致（包括空白和缩进）
- 一次只修改一处，避免大范围替换

## 主动发现技能（Skill Discovery）
- 遇到不确定如何高效完成的任务时，主动使用 `glob` 和 `grep` 搜索工作目录中的技能定义文件（如 `SKILL.md`、`AGENTS.md`、`CLAUDE.md`、`README.md`、`*.skill` 等）
- 找到相关技能文件后，使用 `file_read` 阅读其内容，理解技能的用法和最佳实践
- 将学到的技能知识应用到当前任务中
- 特别关注项目根目录和 `skills/`、`.claude-plugin/` 等常见技能目录
- 不要假设自己已经知道所有最佳实践——先搜索、先学习、再执行

## 安全规则
- 不删除重要文件和目录
- 不执行破坏性命令（rm -rf、format 等）
- 修改前先理解上下文

## 输出规范
- 执行操作后说明做了什么以及为什么
- 遇到错误时分析原因并提出解决方案"""


def _load_project_context(
    workspace_dir: str, max_lines: int = 200, max_bytes: int = 25600
) -> str | None:
    """扫描工作区根目录，按优先级加载项目说明文件。"""
    candidates = [
        "AGENTS.md",
        ".agents.md",
        "SKILL.md",
        ".skill.md",
        "CLAUDE.md",
        ".claude.md",
        "README.md",
    ]
    workspace = Path(workspace_dir)
    parts: list[str] = []
    for name in candidates:
        file_path = workspace / name
        try:
            if not file_path.is_file():
                continue
            content = file_path.read_text(encoding="utf-8", errors="replace")
            text = "\n".join(content.splitlines()[:max_lines])
            encoded = text.encode("utf-8")
            if len(encoded) > max_bytes:
                text = encoded[:max_bytes].decode("utf-8", errors="ignore")
            parts.append(f"### {name}\n\n{text}")
        except Exception:
            continue
    return "\n\n---\n\n".join(parts) if parts else None


def _compose_prompt(tool_names: tuple[str, ...], workspace_dir: str | None = None) -> str:
    """按指定工具集合组装系统提示词。"""
    sections = [_ROLE]
    if workspace_dir is not None:
        sections.append(f"当前工作目录: {workspace_dir}")

    selected = set(tool_names)
    tool_lines = [
        f"- `{name}`: {description}"
        for name, description in _TOOL_GUIDES.items()
        if name in selected
    ]
    tools_section = "## 可用工具"
    if tool_lines:
        tools_section += "\n" + "\n".join(tool_lines)
    else:
        tools_section += "\n当前未提供可用工具。"
    sections.extend((tools_section, _RULES))
    return "\n\n".join(sections)


CODING_SYSTEM_PROMPT = _compose_prompt(tuple(_TOOL_GUIDES))


@lru_cache(maxsize=128)
def _build_cached_prompt(workspace_dir: str, tools: tuple[str, ...] | None) -> str:
    """使用可哈希参数缓存完整系统提示词。"""
    tool_names = tuple(_TOOL_GUIDES) if tools is None else tools
    return _compose_prompt(tool_names, workspace_dir)


def build_coding_system_prompt(
    workspace_dir: str,
    tools: list[str] | None = None,
) -> str:
    """构建包含工作目录、可用工具和项目说明的 Coding Agent 系统提示词。"""
    tools_tuple = None if tools is None else tuple(tools)
    prompt = _build_cached_prompt(workspace_dir, tools_tuple)
    if workspace_dir:
        project_context = _load_project_context(workspace_dir)
        if project_context:
            prompt += (
                "\n\n## 项目上下文\n\n"
                "以下是项目的说明文件内容：\n\n"
                f"{project_context}"
            )
    return prompt
