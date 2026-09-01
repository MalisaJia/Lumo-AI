"""Pydantic Schema 定义。

所有请求/响应模型统一继承 CamelModel，JSON 字段一律 camelCase。
"""

import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """共享基类：字段序列化为 camelCase，同时允许以蛇形命名赋值。"""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


class ModelIn(CamelModel):
    """创建/更新 Provider 时携带的模型条目。"""

    name: str
    label: str | None = None
    is_default: bool = False
    context_length: int | None = None
    # 能力标签（取值限六种任务类型）；不传/空时按模型名走默认能力表
    capability_tags: list[str] | None = None


class ModelOut(CamelModel):
    id: str
    name: str
    label: str
    is_default: bool
    context_length: int | None = None
    capability_tags: list[str] | None = None


class ProviderCreate(CamelModel):
    name: str
    base_url: str
    api_key: str
    models: list[ModelIn] = []
    is_default: bool = False


class ProviderUpdate(CamelModel):
    """PUT 更新：所有字段可选；apiKey 不传则保留原 Key。"""

    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    models: list[ModelIn] | None = None
    is_default: bool | None = None


class ProviderOut(CamelModel):
    id: str
    name: str
    base_url: str
    masked_key: str
    is_default: bool
    models: list[ModelOut] = []


class ValidateRequest(CamelModel):
    base_url: str
    api_key: str


class ValidateResponse(CamelModel):
    valid: bool
    models: list[str] | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Conversations / Messages
# ---------------------------------------------------------------------------


class ConversationCreate(CamelModel):
    title: str | None = None
    provider_id: str | None = None
    model_name: str | None = None


class ConversationUpdate(CamelModel):
    title: str | None = None
    provider_id: str | None = None
    model_name: str | None = None


class ConversationOut(CamelModel):
    id: str
    title: str
    provider_id: str | None = None
    model_name: str | None = None
    created_at: datetime
    updated_at: datetime


class SourceOut(CamelModel):
    """联网搜索引用来源（持久化/响应均只含 id/title/url）。"""

    id: int
    title: str
    url: str


class AttachmentOut(CamelModel):
    """消息图片附件（持久化/响应均含 id/url/fileName/mimeType）。"""

    id: str
    url: str
    file_name: str = ""
    mime_type: str = ""


class AttachmentIn(CamelModel):
    """聊天请求携带的图片附件引用（已通过 /api/uploads 上传）。"""

    id: str
    url: str
    file_name: str | None = None
    mime_type: str | None = None


class MessageOut(CamelModel):
    id: str
    conversation_id: str
    role: str
    content: str
    token_count: int | None = None
    sources: list[SourceOut] | None = None
    attachments: list[AttachmentOut] | None = None
    created_at: datetime

    @field_validator("sources", "attachments", mode="before")
    @classmethod
    def _parse_json_column(cls, v: object) -> object:
        # DB 中为 JSON 字符串；解析失败视为无值
        if isinstance(v, str):
            try:
                return json.loads(v)
            except ValueError:
                return None
        return v


class MessageUpdate(CamelModel):
    content: str


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


class ChatStreamRequest(CamelModel):
    conversation_id: str
    content: str | None = None
    regenerate: bool = False
    enable_search: bool = False
    attachments: list[AttachmentIn] | None = None


class UploadOut(CamelModel):
    """POST /api/uploads 响应。"""

    id: str
    url: str
    file_name: str
    mime_type: str
    size: int


# ---------------------------------------------------------------------------
# Search Settings
# ---------------------------------------------------------------------------


class SearchSettingsOut(CamelModel):
    """GET 响应：Tavily Key 只返回脱敏形式，绝不返回明文。"""

    search_provider: Literal["ddgs", "tavily", "searxng"] = "ddgs"
    tavily_masked_key: str | None = None
    searxng_url: str | None = None


class SearchSettingsUpdate(CamelModel):
    """PUT 请求：tavilyApiKey 不传则保留原 Key。"""

    search_provider: Literal["ddgs", "tavily", "searxng"] | None = None
    tavily_api_key: str | None = None
    searxng_url: str | None = None


# ---------------------------------------------------------------------------
# Routing Settings
# ---------------------------------------------------------------------------


class RoutingSettingsOut(CamelModel):
    """GET/PUT 响应：同渠道模型自动路由与任务感知智能选模开关。"""

    enabled: bool = True
    smart_selection_enabled: bool = False


class RoutingSettingsUpdate(CamelModel):
    enabled: bool
    # 可选：旧客户端不传时保持现值（向后兼容）
    smart_selection_enabled: bool | None = None


class ToolsSettingsOut(CamelModel):
    """GET/PUT 响应：Agent 工具（skills）开关。"""

    enabled: bool = True


class ToolsSettingsUpdate(CamelModel):
    enabled: bool


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------


class MemorySettingsOut(CamelModel):
    """GET/PUT 响应：长期记忆总开关。"""

    enabled: bool = True


class MemorySettingsUpdate(CamelModel):
    enabled: bool


class MemoryOut(CamelModel):
    id: str
    memory_type: Literal["fact", "preference", "summary"]
    content: str
    tags: list[str] = []
    source_conversation_id: str | None = None
    is_enabled: bool
    created_at: datetime
    updated_at: datetime


class MemoryCreate(CamelModel):
    content: str
    type: Literal["fact", "preference", "summary"] = "fact"
    tags: list[str] | None = None


class MemoryUpdate(CamelModel):
    """PUT 局部更新：未传字段保持原值。"""

    content: str | None = None
    tags: list[str] | None = None
    is_enabled: bool | None = None
