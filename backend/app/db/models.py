"""SQLAlchemy ORM models.

Mirrors the tables documented in ``engineering_spec.md`` section 12 and
``docs/architecture.md`` section 8. Complex Pydantic objects are stored
as JSON text strings so the MVP can run on SQLite without a JSONB type.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, index=True)
    industry = Column(String, nullable=False, default="")
    # ``goals`` is a JSON-encoded list of strings.
    goals = Column(Text, nullable=False, default="[]")
    status = Column(String, nullable=False, default="created", index=True)
    output_language = Column(String, nullable=False, default="zh")
    report_depth = Column(String, nullable=False, default="standard")
    data_mode = Column(String, nullable=False, default="demo")
    industry_type = Column(String, nullable=False, default="general")
    analysis_purpose = Column(String, nullable=False, default="unknown")
    analysis_frameworks = Column(String, nullable=False, default='["swot"]')   # JSON list
    custom_dimensions = Column(String, nullable=False, default="[]")   # JSON list
    research_inputs = Column(Text, nullable=False, default="[]")   # JSON list
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    competitors = relationship(
        "Competitor",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    sources = relationship(
        "Source",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    knowledge_records = relationship(
        "CompetitorKnowledgeRecord",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    agent_runs = relationship(
        "AgentRun",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    qa_results = relationship(
        "QAResultRecord",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    reports = relationship(
        "Report",
        back_populates="project",
        cascade="all, delete-orphan",
    )


class Competitor(Base):
    __tablename__ = "competitors"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String, nullable=False)
    url = Column(String, nullable=False)
    description = Column(Text, nullable=False, default="")
    role = Column(String, nullable=False, default="direct_competitor")
    extra_urls = Column(Text, nullable=False, default="[]")

    project = relationship("Project", back_populates="competitors")


class Source(Base):
    __tablename__ = "sources"

    id = Column(String, primary_key=True, index=True)
    # ``external_id`` preserves the original fixture/upstream identifier so
    # we can trace a DB row back to its origin (e.g. ``src_cursor_001``)
    # without polluting the globally-unique primary key.
    external_id = Column(String, nullable=True, index=True)
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    competitor_id = Column(String, nullable=False, default="", index=True)
    competitor_name = Column(String, nullable=False, default="")
    source_type = Column(String, nullable=False, default="manual_input")
    url = Column(String, nullable=False, default="")
    title = Column(String, nullable=False, default="")
    snippet = Column(Text, nullable=False, default="")
    content = Column(Text, nullable=False, default="")
    retrieved_at = Column(String, nullable=False, default="")
    reliability = Column(String, nullable=False, default="medium")
    data_source = Column(String, nullable=False, default="demo")
    screenshot_path = Column(Text, nullable=False, default="")
    screenshot_url = Column(Text, nullable=False, default="")

    project = relationship("Project", back_populates="sources")


class CompetitorKnowledgeRecord(Base):
    __tablename__ = "competitor_knowledge"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    competitor_id = Column(String, nullable=False, index=True)
    # ``knowledge_json`` is the JSON-encoded CompetitorKnowledge object.
    knowledge_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    project = relationship("Project", back_populates="knowledge_records")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    agent_name = Column(String, nullable=False, index=True)
    input_json = Column(Text, nullable=False, default="{}")
    output_json = Column(Text, nullable=False, default="{}")
    status = Column(String, nullable=False, default="running")
    error_message = Column(Text, nullable=True)
    latency_ms = Column(Integer, nullable=False, default=0)
    token_usage_json = Column(Text, nullable=False, default="{}")
    retry_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="agent_runs")


class WorkflowJob(Base):
    __tablename__ = "workflow_jobs"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status = Column(String, nullable=False, default="queued", index=True)
    backend = Column(String, nullable=False, default="background_tasks")
    payload_json = Column(Text, nullable=False, default="{}")
    error_message = Column(Text, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    project = relationship("Project")


class QAResultRecord(Base):
    __tablename__ = "qa_results"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    passed = Column(Boolean, nullable=False, default=False)
    score = Column(Integer, nullable=False, default=0)
    issues_json = Column(Text, nullable=False, default="[]")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="qa_results")


class Report(Base):
    __tablename__ = "reports"

    id = Column(String, primary_key=True, index=True)
    project_id = Column(
        String,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    markdown_content = Column(Text, nullable=False, default="")
    json_content = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="reports")
