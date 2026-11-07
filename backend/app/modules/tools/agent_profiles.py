"""Agent Profile 注册表：管理不同 Agent 类型的配置。"""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentProfile:
    """Agent 配置档案。"""

    agent_type: str
    display_name: str
    description: str
    build_prompt: Callable[..., str]
    recommended_tools: tuple[str, ...]
    icon: str = ""


# Lazy-import prompt builders to avoid circular imports
def _get_coding_prompt_builder():
    from app.modules.tools.coding_prompt import build_coding_system_prompt

    return build_coding_system_prompt


def _get_ppt_prompt_builder():
    from app.modules.tools.ppt_prompt import build_ppt_system_prompt

    return build_ppt_system_prompt


_PROFILES: dict[str, AgentProfile] = {}


def register_profile(profile: AgentProfile) -> None:
    _PROFILES[profile.agent_type] = profile


def get_profile(agent_type: str) -> AgentProfile | None:
    return _PROFILES.get(agent_type)


def get_all_profiles() -> list[AgentProfile]:
    return list(_PROFILES.values())


def get_default_profile() -> AgentProfile:
    return _PROFILES.get("coding", list(_PROFILES.values())[0])


# Register built-in profiles
register_profile(
    AgentProfile(
        agent_type="coding",
        display_name="Lumo Coding Master",
        description="专业编码智能体，可读写文件、搜索代码、执行命令、创建子任务",
        build_prompt=_get_coding_prompt_builder(),
        recommended_tools=(
            "file_read",
            "file_write",
            "file_edit",
            "glob",
            "grep",
            "bash",
            "ask_user",
            "check_background_task",
            "agent",
            "parallel_agents",
            "publish_context",
            "read_shared_context",
        ),
        icon="🔧",
    )
)

register_profile(
    AgentProfile(
        agent_type="ppt",
        display_name="Lumo PPT Master",
        description="专业演示文稿智能体，可创建精美的 PPT 演示文稿",
        build_prompt=_get_ppt_prompt_builder(),
        recommended_tools=("create_ppt", "web_search", "file_read"),
        icon="📊",
    )
)
