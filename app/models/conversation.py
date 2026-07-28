"""Conversation state and memory models."""

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class ConversationState(str, Enum):
    """Conversation state machine states."""

    NEW = "NEW"
    QUALIFYING = "QUALIFYING"
    INTERESTED = "INTERESTED"
    ACTION = "ACTION"
    WAITING = "WAITING"
    ENDED = "ENDED"


class ConversationTurn(BaseModel):
    """Single turn in a conversation."""

    ts: datetime
    from_role: Literal["merchant", "customer", "vera"]
    message: str
    engagement: str | None = None
    auto_reply_detected: bool = False
    intent: str | None = None


class ConversationSession(BaseModel):
    """Complete conversation session."""

    conversation_id: str
    merchant_id: str
    customer_id: str | None = None
    state: ConversationState = ConversationState.NEW
    history: list[ConversationTurn] = Field(default_factory=list)
    last_trigger_id: str | None = None
    last_cta: str | None = None
    last_decision: str | None = None
    suppression_keys_used: list[str] = Field(default_factory=list)
    auto_reply_count: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
