# SPDX-License-Identifier: AGPL-3.0-only
"""Dedicated dialogue schema, deliberately separate from research events."""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class DialogueBase(DeclarativeBase):
    pass


class SchemaVersion(DialogueBase):
    __tablename__ = "dialogue_schema_versions"
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)


class Bucket(DialogueBase):
    __tablename__ = "dialogue_buckets"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)


class Conversation(DialogueBase):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_key: Mapped[str] = mapped_column(String(64), index=True)
    exercise_id: Mapped[str] = mapped_column(String(64))
    exercise_version: Mapped[str] = mapped_column(String(64))
    assignment_key: Mapped[str] = mapped_column(String(64), index=True)
    policy_id: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[int] = mapped_column(Integer, index=True)
    deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    byte_count: Mapped[int] = mapped_column(Integer, default=0)
    pending_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pending_until: Mapped[int] = mapped_column(Integer, default=0)


class Turn(DialogueBase):
    __tablename__ = "conversation_turns"
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), primary_key=True)
    request_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))
    response: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Message(DialogueBase):
    __tablename__ = "conversation_messages"
    __table_args__ = (UniqueConstraint("conversation_id", "sequence"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(64))
    sequence: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    byte_count: Mapped[int] = mapped_column(Integer)
