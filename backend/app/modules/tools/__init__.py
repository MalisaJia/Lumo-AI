"""Agent 工具（skills）模块。

导入各工具子模块即触发 @tool 注册；对外暴露注册表与执行器。
"""

# 顺序导入触发工具注册（装饰器副作用）
from app.modules.tools import builtin  # noqa: F401
from app.modules.tools import ppt_tool  # noqa: F401
from app.modules.tools import web_search_tool  # noqa: F401
from app.modules.tools.registry import get_registry

__all__ = ["get_registry"]
