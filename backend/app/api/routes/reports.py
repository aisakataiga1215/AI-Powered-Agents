"""Report retrieval and human correction routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.errors import NotFoundError, ValidationError
from app.schemas.trace import AgentRun, AgentRunStatus
from app.services import project_service, report_service, trace_service

router = APIRouter()


@router.get("/projects/{project_id}/report")
def get_project_report(
    project_id: str,
    db: Session = Depends(get_session),
) -> dict:
    project = project_service.get_project(db, project_id)
    if project is None:
        raise NotFoundError("Project", project_id)
    record = report_service.get_report(db, project_id)
    if record is None:
        raise NotFoundError("Report", project_id)
    return report_service.serialize_report(record)


@router.patch("/projects/{project_id}/report")
def patch_project_report(
    project_id: str,
    payload: dict,
    db: Session = Depends(get_session),
) -> dict:
    """Save a human-corrected report revision.

    The payload accepts a partial correction for fields a reviewer can edit
    safely in the UI. A new Report row is created so the previous generated
    report remains auditable.
    """
    project = project_service.get_project(db, project_id)
    if project is None:
        raise NotFoundError("Project", project_id)
    record = report_service.get_report(db, project_id)
    if record is None:
        raise NotFoundError("Report", project_id)

    current = report_service.serialize_report(record)
    editable_fields = {
        "title",
        "executive_summary",
        "competitor_overview",
        "feature_comparison",
        "pricing_comparison",
        "user_persona_comparison",
        "swot_comparison",
        "strategic_recommendations",
        "framework_sections",
        "custom_dimension_sections",
        "purpose_sections",
        "competitor_scores",
        "analysis_objective",
        "competitor_selection_rationale",
    }
    updates = {k: v for k, v in payload.items() if k in editable_fields}
    if not updates:
        raise ValidationError(
            "Request body must include at least one editable report field."
        )

    corrected = {**current, **updates}
    saved = report_service.save_report_from_payload(db, project_id, corrected)

    trace_service.save_agent_run(
        db,
        AgentRun(
            project_id=project_id,
            agent_name="HumanReviewer",
            input={
                "report_id": record.id,
                "editable_fields": sorted(updates.keys()),
            },
            output={
                "decision_summary": "Human reviewer saved a corrected report revision.",
                "new_report_id": saved.id,
                "changed_fields": sorted(updates.keys()),
            },
            status=AgentRunStatus.success,
        ),
    )

    return report_service.serialize_report(saved)
