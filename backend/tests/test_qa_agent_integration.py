"""QAAgent end-to-end integration tests.

Exercises ``qa_agent.run`` against a real (in-memory) SQLite engine so
the QAResult and AgentRun records get persisted exactly like in
production. No LLM access.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.agents import qa_agent
from app.db import models
from app.schemas.claim import Claim
from app.schemas.knowledge import (
    CompetitorKnowledge,
    FeatureCategory,
    FeatureItem,
    PricingModel,
    PricingPlan,
    ProductProfile,
    SWOTAnalysis,
)
from app.schemas.report import CompetitiveReport
from app.schemas.source import Reliability, SourceEvidence, SourceType


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    models.Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = session_factory()
    project = models.Project(
        id="proj_qa",
        industry="AI Coding",
        goals="[]",
        status="running",
        output_language="en",
        report_depth="standard",
    )
    session.add(project)
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _source(source_id: str = "src_qaaaaaa1") -> SourceEvidence:
    return SourceEvidence(
        source_id=source_id,
        project_id="proj_qa",
        competitor_name="Cursor",
        source_type=SourceType.official_website,
        url="https://cursor.com",
        title="Home",
        snippet="",
        content="",
        reliability=Reliability.high,
    )


def _pricing_source(source_id: str = "src_qaprice01") -> SourceEvidence:
    """A pricing_page source. The split pricing rule requires one of these
    for any competitor when ``pricing_analysis`` is a goal."""
    return SourceEvidence(
        source_id=source_id,
        project_id="proj_qa",
        competitor_name="Cursor",
        source_type=SourceType.pricing_page,
        url="https://cursor.com/pricing",
        title="Pricing",
        snippet="",
        content="",
        reliability=Reliability.high,
    )


def _full_competitor(source_id: str = "src_qaaaaaa1") -> CompetitorKnowledge:
    return CompetitorKnowledge(
        competitor_id="comp_1",
        competitor_name="Cursor",
        product_profile=ProductProfile(
            name="Cursor",
            website="https://cursor.com",
            positioning=Claim(text="AI code editor", evidence=[source_id]),
        ),
        feature_tree=[
            FeatureCategory(
                category="AI",
                features=[
                    FeatureItem(
                        name="Tab",
                        availability="available",
                        evidence=[source_id],
                    )
                ],
            )
        ],
        pricing_model=PricingModel(
            has_free_plan=True,
            plans=[PricingPlan(name="Pro", price="$20")],
        ),
        swot=SWOTAnalysis(
            strengths=[Claim(text="Great UX", evidence=[source_id])],
        ),
        sources=[source_id],
    )


def _passing_report(source_id: str = "src_qaaaaaa1") -> CompetitiveReport:
    return CompetitiveReport(
        project_id="proj_qa",
        executive_summary=[Claim(text="Strong market", evidence=[source_id])],
        competitor_overview=[_full_competitor(source_id)],
        feature_comparison={"AI": {"Cursor": "available"}},
        pricing_comparison={"Cursor": "$20/mo Pro"},
        swot_comparison={"Cursor": "Strong UX"},
        strategic_recommendations=[
            Claim(text="Bundle SKU", evidence=[source_id])
        ],
        source_list=[_source(source_id)],
    )


def test_qa_run_passes_full_report(db_session):
    report = _passing_report()
    sources = [_source(), _pricing_source()]
    result = qa_agent.run(
        db=db_session,
        project_id="proj_qa",
        report=report,
        knowledge=report.competitor_overview,
        sources=sources,
        goals=["pricing_analysis"],
    )
    assert result.passed is True
    assert result.score == 100
    assert result.issues == []


def test_qa_run_fails_when_pricing_missing_and_goal_set(db_session):
    report = _passing_report()
    report.competitor_overview[0].pricing_model = None
    result = qa_agent.run(
        db=db_session,
        project_id="proj_qa",
        report=report,
        knowledge=report.competitor_overview,
        sources=[_source()],
        goals=["pricing_analysis"],
    )
    assert result.passed is False
    assert any(i.target_agent == "CollectorAgent" for i in result.issues)


def test_qa_run_persists_result_and_trace(db_session):
    report = _passing_report()
    qa_agent.run(
        db=db_session,
        project_id="proj_qa",
        report=report,
        knowledge=report.competitor_overview,
        sources=[_source()],
        goals=[],
    )
    qa_rows = (
        db_session.query(models.QAResultRecord)
        .filter(models.QAResultRecord.project_id == "proj_qa")
        .all()
    )
    assert len(qa_rows) == 1
    runs = (
        db_session.query(models.AgentRun)
        .filter(models.AgentRun.agent_name == "QAAgent")
        .all()
    )
    assert len(runs) == 1
    assert runs[0].status == "success"


def test_qa_run_blocks_when_claim_lacks_evidence(db_session):
    report = _passing_report()
    report.strategic_recommendations = [Claim(text="bare claim", evidence=[])]
    result = qa_agent.run(
        db=db_session,
        project_id="proj_qa",
        report=report,
        knowledge=report.competitor_overview,
        sources=[_source()],
        goals=[],
    )
    assert result.passed is False
    assert any(
        i.target_agent == "WriterAgent"
        and i.issue_type.value == "missing_citation_in_report"
        for i in result.issues
    )


# pricing_consistency regression ---------------------------------------------


def test_check_pricing_consistency_catches_mismatch():
    """Windsurf pricing_comparison says $35 but pricing_model.plans says $40."""
    from app.agents.qa_agent import check_pricing_consistency
    from app.schemas.knowledge import CompetitorKnowledge, PricingModel, PricingPlan, ProductProfile
    from app.schemas.report import CompetitiveReport

    ck = CompetitorKnowledge(
        competitor_id="windsurf",
        competitor_name="Windsurf",
        product_profile=ProductProfile(name="Windsurf", website="https://windsurf.com"),
        pricing_model=PricingModel(
            plans=[
                PricingPlan(name="Free", price="free", billing_cycle="monthly"),
                PricingPlan(name="Pro Ultimate", price="$40", billing_cycle="monthly"),
            ]
        ),
    )
    report = CompetitiveReport(
        project_id="proj_test",
        competitor_overview=[ck],
        pricing_comparison={"Windsurf": "Pro Ultimate: $35/month"},
    )
    issues: list = []
    check_pricing_consistency(report, issues)

    assert len(issues) == 1
    assert issues[0].severity.value == "high"
    assert issues[0].target_agent == "WriterAgent"
    assert "35" in issues[0].message
    assert "40" in issues[0].message


def test_check_pricing_consistency_passes_when_prices_match():
    """No issue when pricing_comparison dollar amounts are a subset of plan prices."""
    from app.agents.qa_agent import check_pricing_consistency
    from app.schemas.knowledge import CompetitorKnowledge, PricingModel, PricingPlan, ProductProfile
    from app.schemas.report import CompetitiveReport

    ck = CompetitorKnowledge(
        competitor_id="cursor",
        competitor_name="Cursor",
        product_profile=ProductProfile(name="Cursor", website="https://cursor.com"),
        pricing_model=PricingModel(
            plans=[
                PricingPlan(name="Hobby", price="free", billing_cycle="monthly"),
                PricingPlan(name="Pro", price="$20", billing_cycle="monthly"),
                PricingPlan(name="Business", price="$40", billing_cycle="monthly"),
            ]
        ),
    )
    report = CompetitiveReport(
        project_id="proj_test",
        competitor_overview=[ck],
        pricing_comparison={"Cursor": "Pro: $20/month | Business: $40/month"},
    )
    issues: list = []
    check_pricing_consistency(report, issues)
    assert issues == []


def test_check_pricing_consistency_no_issue_when_comparison_empty():
    """Empty pricing_comparison dict -> no consistency issues raised."""
    from app.agents.qa_agent import check_pricing_consistency
    from app.schemas.knowledge import CompetitorKnowledge, PricingModel, PricingPlan, ProductProfile
    from app.schemas.report import CompetitiveReport

    ck = CompetitorKnowledge(
        competitor_id="trae",
        competitor_name="Trae",
        product_profile=ProductProfile(name="Trae", website="https://trae.ai"),
        pricing_model=PricingModel(plans=[PricingPlan(name="Free", price="free")]),
    )
    report = CompetitiveReport(
        project_id="proj_test",
        competitor_overview=[ck],
        pricing_comparison={},
    )
    issues: list = []
    check_pricing_consistency(report, issues)
    assert issues == []
