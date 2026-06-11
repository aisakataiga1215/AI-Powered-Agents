"""Agent run / trace schema.

Each Agent invocation is recorded as an :class:`AgentRun` so that the
frontend trace timeline can display agent inputs, outputs, latency, and
errors.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class AgentRunStatus(str, Enum):
    success = "success"
    failed = "failed"
    skipped = "skipped"
    running = "running"


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class AgentRun(BaseModel):
    agent_run_id: str = Field(default_factory=lambda: f"run_{uuid.uuid4().hex[:8]}")
    project_id: str
    agent_name: str
    input: dict = Field(default_factory=dict)
    output: dict = Field(default_factory=dict)
    status: AgentRunStatus = AgentRunStatus.running
    error_message: str | None = None
    latency_ms: int = 0
    token_usage: TokenUsage = Field(default_factory=TokenUsage)
    retry_count: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
