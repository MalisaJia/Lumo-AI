"""任务感知智能选模：任务类型分类 + 模型能力匹配 + 会话粘性缓存。

任务类型固定六种：code / writing / long_text / reasoning / vision / general。
分类先走零成本规则；模糊时才用轻量 LLM 兜底（llm_complete，失败降级 general）。
"""

import json
import logging
import re
from itertools import islice
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models import Model
    from app.pipeline.chat_pipeline import ChatContext

logger = logging.getLogger(__name__)

# 六种任务类型（同时是 capability_tags 的合法取值全集）
TASK_TYPES = ("code", "writing", "long_text", "reasoning", "vision", "general")

# 长文本判定阈值
LONG_TEXT_MIN_CHARS = 2000
LONG_TEXT_MIN_NEWLINES = 15
# 花括号密度：出现次数达到该值视为代码片段
CODE_BRACE_THRESHOLD = 4

# 注意顺序：code 关键词优先于 writing/reasoning（"写代码"同时含"写"）
_CODE_PATTERN = re.compile(
    r"```|def |import |function|写代码|写个脚本|写脚本|debug|报错|bug|函数|正则",
    re.IGNORECASE,
)
_WRITING_PATTERN = re.compile(
    r"写一篇|文案|润色|改写|翻译|标题|作文|文章|广告词|slogan", re.IGNORECASE
)
_REASONING_PATTERN = re.compile(r"证明|推导|计算|分析|比较|为什么|原理|逻辑", re.IGNORECASE)

_CLASSIFY_SYSTEM = (
    "你是任务类型分类器。根据用户消息判断其任务类型，"
    "从 code、writing、long_text、reasoning、vision、general 六个词中选择一个，"
    "只输出这一个词本身，不要任何解释、引号或标点。"
)

# 模型名（小写子串匹配，按顺序取首个命中组）→ 默认能力标签
DEFAULT_CAPABILITIES: list[tuple[tuple[str, ...], list[str]]] = [
    (("claude",), ["code", "reasoning", "vision"]),
    (("chatgpt", "gpt", "o1", "o3"), ["writing", "general", "vision"]),
    (("kimi", "moonshot"), ["long_text", "writing"]),
    (("deepseek",), ["code", "reasoning"]),
    (("gemini",), ["general", "long_text", "vision"]),
]
_FALLBACK_CAPABILITIES = ["general"]

# 会话粘性缓存 {conversation_id: (task_type, model_name)}；
# 进程内存态，重启即清零，可接受
_last_selection: dict[str, tuple[str, str]] = {}
# 缓存容量上限；超出时淘汰最旧的一半（dict 保持插入序）
_STICKY_MAX_SIZE = 500


def classify_by_rules(user_message: str, has_image_attachments: bool) -> str | None:
    """零成本规则分类；无法确定时返回 None（交给 LLM 兜底）。

    仅图片附件强制 vision；纯文档附件继续走后续文本规则。
    """
    if has_image_attachments:
        return "vision"
    text = user_message or ""
    if (
        _CODE_PATTERN.search(text)
        or text.count("{") + text.count("}") >= CODE_BRACE_THRESHOLD
    ):
        return "code"
    if len(text) > LONG_TEXT_MIN_CHARS or text.count("\n") > LONG_TEXT_MIN_NEWLINES:
        return "long_text"
    if _WRITING_PATTERN.search(text):
        return "writing"
    if _REASONING_PATTERN.search(text):
        return "reasoning"
    return None


async def classify_by_llm(ctx: "ChatContext", user_message: str) -> str:
    """轻量 LLM 分类兜底；要求 ctx 的 base_url/api_key/model_name 已就绪。

    输出非法或调用失败一律降级 "general"。
    """
    # 局部导入避免循环依赖（rewriter -> chat_pipeline）
    from app.modules.search.rewriter import llm_complete

    result = await llm_complete(
        ctx,
        [
            {"role": "system", "content": _CLASSIFY_SYSTEM},
            {"role": "user", "content": (user_message or "")[:1000]},
        ],
        max_tokens=10,
    )
    if not result:
        return "general"
    cleaned = result.strip().strip("\"'“”。.").lower()
    if cleaned in TASK_TYPES:
        return cleaned
    for task_type in TASK_TYPES:
        if task_type in cleaned:
            return task_type
    return "general"


def default_capabilities(model_name: str) -> list[str]:
    """按模型名小写子串匹配默认能力表；无命中返回 ["general"]。"""
    lowered = (model_name or "").lower()
    for keywords, tags in DEFAULT_CAPABILITIES:
        if any(k in lowered for k in keywords):
            return list(tags)
    return list(_FALLBACK_CAPABILITIES)


def get_tags(model: "Model") -> list[str]:
    """模型能力标签：capability_tags 列优先，解析失败/为空降级默认表。"""
    raw = getattr(model, "capability_tags", None)
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and parsed:
                return [str(t) for t in parsed]
        except ValueError:
            logger.warning("capability_tags 解析失败，降级默认能力表：%s", model.name)
    return default_capabilities(model.name)


def rank_models(models: list["Model"], task_type: str) -> list["Model"]:
    """按任务类型排序：含该标签的在前；long_text 匹配组内按上下文长度降序。

    输入应已按 is_default desc / created_at 排序；无任何模型匹配时返回原顺序。
    """
    matched = [m for m in models if task_type in get_tags(m)]
    if not matched:
        return list(models)
    if task_type == "long_text":
        matched.sort(
            key=lambda m: (-(m.context_length or 0), not m.is_default, m.created_at)
        )
    matched_ids = {id(m) for m in matched}
    rest = [m for m in models if id(m) not in matched_ids]
    return matched + rest


def get_sticky(conversation_id: str) -> tuple[str, str] | None:
    """读取会话粘性缓存：(task_type, model_name)；无记录返回 None。"""
    return _last_selection.get(conversation_id)


def set_sticky(conversation_id: str, task_type: str, model_name: str) -> None:
    if len(_last_selection) > _STICKY_MAX_SIZE:
        for key in list(islice(_last_selection, len(_last_selection) // 2)):
            del _last_selection[key]
    _last_selection[conversation_id] = (task_type, model_name)
