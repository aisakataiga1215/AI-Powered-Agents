"""Schema validation tests.

Smoke tests for the Pydantic schemas that exercise the contracts in
``docs/schema_design.md``. These run without network or LLM access.
"""

import pytest
from pydantic import ValidationError

from app.schemas.agent_message import AgentMessage, MessageType
from app.schemas.claim import Claim, ConfidenceLevel
from app.schemas.competitor import Competitor, CompetitorInput
from app.schemas.knowledge import (
    CompetitorKnowledge,
    FeatureCategory,
    FeatureItem,
    PricingModel,
    PricingPlan,
    ProductProfile,
    SWOTAnalysis,
    UserFeedbackSummary,
    UserPersona,
)
from app.schemas.project import ProjectCreate, ProjectStatus
from app.schemas.qa import IssueSeverity, IssueType, QAIssue, QAResult
from app.schemas.report import CompetitiveReport
from app.schemas.source import Reliability, SourceEvidence, SourceType
from app.schemas.trace import AgentRun, AgentRunStatus, TokenUsage


def test_claim_defaults_and_evidence_list():
    claim = Claim(text="Cursor offers AI completions.")
    assert claim.claim_id.startswith("claim_")
    assert claim.confidence is ConfidenceLevel.medium
    assert claim.evidence == []
    assert claim.is_hypothesis is False
    assert claim.created_by == "AnalystAgent"


def test_claim_accepts_evidence_and_hypothesis_flag():
    claim = Claim(
        text="Pricing might rise.",
        confidence=ConfidenceLevel.low,
        is_hypothesis=True,
        evidence=["src_abcdef12"],
    )
    assert claim.is_hypothesis
    assert claim.evidence == ["src_abcdef12"]


def test_source_evidence_requires_url_and_competitor_name():
    source = SourceEvidence(
        competitor_name="Cursor",
        source_type=SourceType.pricing_page,
        url="https://cursor.com/pricing",
        title="Pricing",
    )
    assert source.source_id.startswith("src_")
    assert source.reliability is Reliability.medium
    assert source.source_type is SourceType.pricing_page


def test_source_evidence_rejects_invalid_source_type():
    with pytest.raises(ValidationError):
        SourceEvidence(
            competitor_name="Cursor",
            source_type="not_a_real_type",  # type: ignore[arg-type]
            url="https://cursor.com",
            title="Home",
        )


def test_competitor_input_and_competitor_full():
    input_form = CompetitorInput(name="Cursor", url="https://cursor.com")
    assert input_form.name == "Cursor"

    full = Competitor(name="Cursor", website="https://cursor.com")
    assert full.competitor_id.startswith("comp_")
    assert full.metadata == {}


def test_competitor_knowledge_supports_full_tree():
    knowledge = CompetitorKnowledge(
        competitor_id="comp_1",
        competitor_name="Cursor",
        product_profile=ProductProfile(name="Cursor", website="https://cursor.com"),
        feature_tree=[
            FeatureCategory(
                category="AI Coding",
                features=[
                    FeatureItem(
                        name="Code completion",
                        availability="available",
                        evidence=["src_aaa"],
                    )
                ],
            )
        ],
        pricing_model=PricingModel(
            has_free_plan=True,
            plans=[PricingPlan(name="Pro", price="$20")],
        ),
        user_personas=[UserPersona(name="Developer")],
        user_feedback_summary=UserFeedbackSummary(summary="Generally positive."),
        swot=SWOTAnalysis(),
        sources=["src_aaa"],
    )
    assert knowledge.feature_tree[0].features[0].evidence == ["src_aaa"]
    assert knowledge.pricing_model.plans[0].billing_cycle == "monthly"


def test_qa_result_score_constraints():
    issue = QAIssue(
        severity=IssueSeverity.high,
        issue_type=IssueType.missing_source,
        target_agent="CollectorAgent",
        message="Missing pricing source.",
    )
    result = QAResult(project_id="proj_1", passed=False, score=72, issues=[issue])
    assert result.passed is False
    assert result.issues[0].issue_type is IssueType.missing_source

    with pytest.raises(ValidationError):
        QAResult(project_id="proj_1", passed=False, score=120)


def test_agent_message_with_payload():
    message = AgentMessage(
        project_id="proj_1",
        from_agent="CollectorAgent",
        to_agent="AnalystAgent",
        message_type=MessageType.source_collection_result,
        payload={"sources": []},
    )
    assert message.message_id.startswith("msg_")
    assert message.message_type is MessageType.source_collection_result


def test_agent_run_defaults():
    run = AgentRun(project_id="proj_1", agent_name="CollectorAgent")
    assert run.status is AgentRunStatus.running
    assert isinstance(run.token_usage, TokenUsage)
    assert run.token_usage.total_tokens == 0
    assert run.retry_count == 0


def test_project_create_defaults_and_status_enum():
    payload = ProjectCreate(
        industry="AI Coding Tools",
        competitors=[CompetitorInput(name="Cursor", url="https://cursor.com")],
        goals=["feature_comparison"],
    )
    assert payload.output_language == "en"
    assert payload.report_depth == "standard"
    assert payload.analysis_purpose == "understand_industry"
    assert ProjectStatus("created") is ProjectStatus.created


def test_competitive_report_round_trip():
    report = CompetitiveReport(project_id="proj_1")
    dumped = report.model_dump(mode="json")
    rehydrated = CompetitiveReport.model_validate(dumped)
    assert rehydrated.project_id == "proj_1"
    assert rehydrated.report_id == report.report_id
