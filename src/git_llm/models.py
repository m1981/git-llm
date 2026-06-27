"""Pydantic domain models. Pure — no DB or IO concerns."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from git_llm.taxonomy import MasterClass, Role


class Turn(BaseModel):
    """A single utterance in a chat."""

    chat_id: int
    idx: int = Field(ge=0, description="Zero-based position within the chat.")
    role: Role
    content: str
    token_estimate: int = 0
    id: int | None = None


class Chat(BaseModel):
    title: str
    source: str = "manual"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    raw_path: str | None = None
    session_id: str | None = None  # pi.dev session UUID; dedup key for bulk import
    id: int | None = None


class Label(BaseModel):
    turn_id: int
    name: str
    master_class: MasterClass
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    labeler: str = "manual"  # "manual" | "llm:<model>" | "stub"
    id: int | None = None


ArtifactKind = Literal["knowledge", "adr"]


class Artifact(BaseModel):
    chat_id: int
    kind: ArtifactKind
    title: str
    body: str
    zk_id: str  # e.g. "202606271430-boilerplate-tax"
    turn_start: int  # turn idx range (inclusive)
    turn_end: int
    labels: list[str] = []
    file_path: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    id: int | None = None
