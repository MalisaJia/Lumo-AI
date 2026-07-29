import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """用户（多用户预备；单用户模式下不使用，数据归属默认用户 "local"）。"""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    # 数据归属用户（单用户模式下恒为 "local"）
    user_id: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="local", index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    models: Mapped[list["Model"]] = relationship(back_populates="provider")


class Model(Base):
    __tablename__ = "models"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    provider_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("providers.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    context_length: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 能力标签（JSON 数组字符串：["code","reasoning"]）；空时按模型名走默认能力表
    capability_tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    provider: Mapped["Provider"] = relationship(back_populates="models")


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_user_updated", "user_id", "updated_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    # 数据归属用户（单用户模式下恒为 "local"）
    user_id: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="local", index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False, default="新对话")
    provider_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now, nullable=False
    )

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    conversation_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # 联网搜索来源（JSON 字符串：[{id,title,url}]）；无搜索时为 NULL
    sources: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 图片附件（JSON 字符串：[{id,url,fileName,mimeType}]）；无附件时为 NULL
    attachments: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class Memory(Base):
    """长期记忆：用户事实(fact)/偏好(preference)/会话摘要(summary)。"""

    __tablename__ = "memories"
    __table_args__ = (
        Index("ix_memories_type_created", "memory_type", "created_at"),
        Index(
            "ix_memories_user_type_created", "user_id", "memory_type", "created_at"
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    # 数据归属用户（单用户模式下恒为 "local"）
    user_id: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="local", index=True
    )
    memory_type: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 标签（JSON 数组字符串：["关键词"]）；无标签时为 NULL
    tags: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 来源会话/消息（不加外键，会话删除后记忆仍保留）
    source_conversation_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_message_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # 扩展 JSON（summary 行存 {"coveredCount": K}）
    extra: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now, nullable=False
    )


class Setting(Base):
    """按用户隔离的 key-value 设置（如联网搜索配置）；敏感值加密后存入。"""

    __tablename__ = "settings"

    # 数据归属用户（单用户模式下恒为 "local"）；与 key 构成复合主键
    user_id: Mapped[str] = mapped_column(
        String(32), primary_key=True, server_default="local"
    )
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now, nullable=False
    )
