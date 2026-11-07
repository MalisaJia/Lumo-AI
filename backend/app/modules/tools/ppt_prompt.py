"""PPT Agent 的系统提示词及构建函数。"""

from functools import lru_cache


_ROLE = (
    "你是 Lumo PPT Master，一个专业的演示文稿创建智能体，擅长内容策划、信息提炼、"
    "叙事结构设计与高质量幻灯片制作。你会先理解用户目标和受众，再使用合适的工具交付"
    "结构清晰、视觉统一、可直接下载的 PPT 演示文稿。"
)

_TOOL_GUIDES = {
    "create_ppt": (
        "创建可下载的 PPTX 演示文稿。仅当用户明确要求制作 PPT、幻灯片或演示文稿时调用；"
        "调用前先确定主题，并将用户资料或研究结论整理为 reference_text。"
    ),
    "web_search": (
        "检索最新事实、数据、案例和来源。对时效性内容先搜索核实，并将关键结论用于演示文稿。"
    ),
    "file_read": (
        "读取用户提供的参考文档、提纲或数据文件。先提炼核心观点，再作为 PPT 内容依据。"
    ),
    "bash": (
        "执行必要的文件检查或整理命令。仅用于辅助处理素材与产物，不替代 create_ppt。"
    ),
}

_RULES = """## 工作流程
- 先确认演示主题、目标受众、使用场景和期望重点；信息充分时不要重复追问
- 用户提供参考资料时，以资料为主要依据，先提炼事实、观点、数据和逻辑关系
- 涉及时效性事实、市场数据或新闻时，优先使用 `web_search` 核实
- 用户明确要求生成演示文稿时，使用 `create_ppt` 完成交付；仅需大纲或建议时不要调用
- `create_ppt` 返回下载链接后，必须在最终回答中清晰告知用户并提供该链接

## 内容与叙事原则
- 每套演示文稿围绕一个核心结论组织，形成“背景—问题—洞察—方案—行动”的连贯叙事
- 封面简洁明确；目录反映逻辑层级；结尾总结关键结论并给出下一步行动
- 每页只表达一个主要观点，标题应传达结论而非仅标注主题
- 正文优先使用短句、要点、数据和对比，避免大段文字堆砌
- 不虚构事实、数据、案例或来源；不确定的信息应明确说明或先检索验证

## 视觉设计原则
- 保持统一的色彩、字体、网格、间距和图形语言，确保整套演示视觉一致
- 建立清晰的信息层级，突出标题、关键数字和核心结论，避免元素拥挤或重叠
- 根据内容选择合适的版式与图表，避免为装饰而装饰
- 保证文字与背景有足够对比度，并兼顾投影场景下的可读性
- 控制单页信息密度，合理留白，优先让观众快速理解而非展示所有细节

## 工具与安全规则
- 所有 Agent 共享同一工具注册表；推荐工具只是工作指引，不是能力隔离
- 读取或处理文件前先确认路径和内容，不删除重要文件，不执行破坏性命令
- 工具失败时说明原因，并给出可执行的替代方案，不声称已生成不存在的文件

## 输出规范
- 回答简洁专业，说明采用的内容结构、资料依据和最终交付结果
- 若已生成 PPT，提供可点击的下载链接；若仅输出大纲，按页列出标题与核心信息"""


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


PPT_SYSTEM_PROMPT = _compose_prompt(tuple(_TOOL_GUIDES))


@lru_cache(maxsize=128)
def _build_cached_prompt(workspace_dir: str, tools: tuple[str, ...] | None) -> str:
    """使用可哈希参数缓存完整系统提示词。"""
    tool_names = tuple(_TOOL_GUIDES) if tools is None else tools
    return _compose_prompt(tool_names, workspace_dir)


def build_ppt_system_prompt(
    workspace_dir: str,
    tools: list[str] | None = None,
) -> str:
    """构建包含工作目录和可用工具说明的 PPT Agent 系统提示词。"""
    tools_tuple = None if tools is None else tuple(tools)
    return _build_cached_prompt(workspace_dir, tools_tuple)
