# app/models.py
import datetime as dt
from typing import Optional, Any
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import BigInteger, String, DateTime, JSON, Boolean, Integer, ForeignKey, Text, UniqueConstraint

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default="user", index=True)
    language_code: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    profile_data: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.utcnow
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

class UserEvent(Base):
    __tablename__ = "user_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.utcnow, index=True
    )

class MenuItem(Base):
    __tablename__ = "menu_items"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(256))
    roles: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("menu_items.id"), nullable=True
    )
    parent: Mapped["MenuItem"] = relationship(
        "MenuItem", remote_side="MenuItem.id", backref="children"
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    action_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # flowise_agentflow, submenu, profile, custom
    action_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)  # JSON config for action
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.utcnow
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

    def roles_list(self) -> list[str]:
        if not self.roles:
            return []
        return [r.strip() for r in self.roles.split(",") if r.strip()]
    
    def get_agentflow_id(self) -> str | None:
        """Extract agentflow_id from action_config if action_type is flowise_agentflow"""
        if self.action_type == "flowise_agentflow" and self.action_config:
            return self.action_config.get("agentflow_id")
        return None

class TestChatSession(Base):
    __tablename__ = "test_chat_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    user: Mapped[User] = relationship("User", backref="testchat_sessions")
    flowise_session_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.utcnow
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

class TestChatMessage(Base):
    __tablename__ = "test_chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("test_chat_sessions.id"), index=True
    )
    session: Mapped[TestChatSession] = relationship(
        "TestChatSession", backref="messages"
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.utcnow, index=True
    )

class SysopkaSession(Base):
    __tablename__ = "sysopka_sessions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    user: Mapped[User] = relationship("User", backref="sysopka_sessions")
    sysopka_type: Mapped[str] = mapped_column(String(32), index=True)  # claudecli, proxmox, homenet, chatbot
    flowise_session_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.utcnow
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

class SysopkaMessage(Base):
    __tablename__ = "sysopka_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("sysopka_sessions.id"), index=True
    )
    session: Mapped[SysopkaSession] = relationship(
        "SysopkaSession", backref="messages"
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.utcnow, index=True
    )

class ClaudeCLISession(Base):
    __tablename__ = "claude_cli_sessions"
    __table_args__ = (
        UniqueConstraint('user_id', 'session_name', name='claude_cli_sessions_user_session_unique'),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    user: Mapped[User] = relationship("User", backref="claude_cli_sessions")
    session_name: Mapped[str] = mapped_column(String(128), index=True)
    uuid: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)  # UUID from Claude CLI
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.utcnow
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

class ClaudeCLIMessage(Base):
    __tablename__ = "claude_cli_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("claude_cli_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session: Mapped[ClaudeCLISession] = relationship(
        "ClaudeCLISession", backref="messages"
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    query: Mapped[str] = mapped_column(Text)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    flags_used: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.utcnow, index=True
    )

class CursorCLISession(Base):
    __tablename__ = "cursor_cli_sessions"
    __table_args__ = (
        UniqueConstraint('user_id', 'session_name', name='cursor_cli_sessions_user_session_unique'),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    user: Mapped[User] = relationship("User", backref="cursor_cli_sessions")
    session_name: Mapped[str] = mapped_column(String(128), index=True)
    uuid: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)  # UUID from Cursor CLI
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.utcnow
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

class CursorCLIMessage(Base):
    __tablename__ = "cursor_cli_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cursor_cli_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session: Mapped[CursorCLISession] = relationship(
        "CursorCLISession", backref="messages"
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    query: Mapped[str] = mapped_column(Text)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    flags_used: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.utcnow, index=True
    )

class ChatGPTCLISession(Base):
    __tablename__ = "chatgpt_cli_sessions"
    __table_args__ = (
        UniqueConstraint('user_id', 'session_name', name='chatgpt_cli_sessions_user_session_unique'),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    user: Mapped[User] = relationship("User", backref="chatgpt_cli_sessions")
    session_name: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.utcnow
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow
    )

class ChatGPTCLIMessage(Base):
    __tablename__ = "chatgpt_cli_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("chatgpt_cli_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session: Mapped[ChatGPTCLISession] = relationship(
        "ChatGPTCLISession", backref="messages"
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    query: Mapped[str] = mapped_column(Text)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_used: Mapped[str | None] = mapped_column(String(64), nullable=True)  # Model name used for this query
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.utcnow, index=True
    )
