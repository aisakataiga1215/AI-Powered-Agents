"""Agent message schema.

Defines structured communication between runtime business Agents.
See ``docs/agent_protocol.md`` for the full message catalog.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    source_collection_request = "source_collection_request"
    source_collection_result = "source_collection_result"
    analysis_request = "analysis_request"
    analysis_result = "analysis_result"
    report_write_request = "report_write_request"
    report_draft = "report_draft"
    qa_review_request = "qa_review_request"
    qa_review_result = "qa_review_result"
    rework_request = "rework_request"
    final_report = "final_report"
    error = "error"


class AgentMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:8]}")
    project_id: str
    from_agent: str
    to_agent: str
    message_type: MessageType
    payload: dict = Field(default_factory=dict)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
