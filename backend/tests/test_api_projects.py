"""API tests.

Exercises the project routes against an in-memory SQLite database with
the FastAPI TestClient. These tests deliberately use a fresh engine per
session so they do not pollute the local dev database.
"""

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure the backend package is importable when running from repo root.
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# Force the database URL to an in-memory SQLite before importing the
# application so the engine in app.db.session points at the test DB.
os.environ["DATABASE_URL"] = "sqlite:///:memory:"


@pytest.fixture()
def workflow_calls(monkeypatch):
    calls = []

    def fake_run_workflow_background(*args, **kwargs):
        calls.append((args, kwargs))

    import app.api.routes.projects as projects_route

    monkeypatch.setattr(projects_route, "run_workflow_background", fake_run_workflow_background)
    return calls


@pytest.fixture()
def client(monkeypatch):
    # Use a shared in-memory engine via StaticPool so the FastAPI app
    # and the test fixture see the same data.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )

    from app.api import deps
    from app.db import models, session as db_session
    from app.main import app
    import app.main as main_module

    # Replace the engine and session factory used by the application.
    monkeypatch.setattr(db_session, "engine", engine)
    monkeypatch.setattr(db_session, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(main_module, "engine", engine)

    # Prevent background tasks from making real LLM calls in unit tests unless a test
    # already patched the route to capture workflow arguments.
    import app.api.routes.projects as projects_route
    if projects_route.run_workflow_background is not None:
        monkeypatch.setattr(projects_route, "run_workflow_background", lambda *a, **kw: None)

    models.Base.metadata.create_all(bind=engine)

    def override_session():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[deps.get_session] = override_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_project_returns_id_and_created_status(client):
    payload = {
        "industry": "AI Coding Tools",
        "competitors": [
            {"name": "Cursor", "url": "https://cursor.com"},
            {"name": "Trae", "url": "https://www.trae.ai"},
        ],
        "goals": ["feature_comparison", "pricing_analysis"],
    }
    response = client.post("/api/projects", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["project_id"].startswith("proj_")
    assert body["status"] == "created"


def test_get_project_returns_project_response_shape(client):
    create = client.post(
        "/api/projects",
        json={
            "industry": "AI Coding Tools",
            "competitors": [
                {"name": "Cursor", "url": "https://cursor.com"},
            ],
            "goals": ["swot"],
        },
    )
    project_id = create.json()["project_id"]

    response = client.get(f"/api/projects/{project_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == project_id
    assert body["industry"] == "AI Coding Tools"
    assert body["goals"] == ["swot"]
    assert body["status"] == "created"


def test_get_project_missing_returns_404(client):
    response = client.get("/api/projects/does-not-exist")
    assert response.status_code == 404
    assert "error" in response.json()


def test_run_project_marks_running(client):
    create = client.post(
        "/api/projects",
        json={
            "industry": "AI Coding Tools",
            "competitors": [{"name": "Cursor", "url": "https://cursor.com"}],
            "goals": ["feature_comparison"],
        },
    )
    project_id = create.json()["project_id"]

    response = client.post(f"/api/projects/{project_id}/run")
    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == project_id
    assert body["status"] == "running"

    follow_up = client.get(f"/api/projects/{project_id}")
    assert follow_up.json()["status"] == "running"


def test_run_project_missing_returns_404(client):
    response = client.post("/api/projects/missing/run")
    assert response.status_code == 404


def test_traces_endpoint_returns_empty_list_for_new_project(client):
    create = client.post(
        "/api/projects",
        json={
            "industry": "AI Coding Tools",
            "competitors": [{"name": "Cursor", "url": "https://cursor.com"}],
            "goals": ["swot"],
        },
    )
    project_id = create.json()["project_id"]
    response = client.get(f"/api/projects/{project_id}/traces")
    assert response.status_code == 200
    body = response.json()
    assert body["project_id"] == project_id
    assert body["traces"] == []


def test_report_missing_returns_404_when_no_report(client):
    create = client.post(
        "/api/projects",
        json={
            "industry": "AI Coding Tools",
            "competitors": [{"name": "Cursor", "url": "https://cursor.com"}],
            "goals": ["swot"],
        },
    )
    project_id = create.json()["project_id"]
    response = client.get(f"/api/projects/{project_id}/report")
    assert response.status_code == 404


def test_source_missing_returns_404(client):
    response = client.get("/api/sources/does-not-exist")
    assert response.status_code == 404


def test_patch_knowledge_validates_payload(client):
    create = client.post(
        "/api/projects",
        json={
            "industry": "AI Coding Tools",
            "competitors": [{"name": "Cursor", "url": "https://cursor.com"}],
            "goals": ["swot"],
        },
    )
    project_id = create.json()["project_id"]

    bad = client.patch(
        f"/api/projects/{project_id}/knowledge",
        json={"competitor_knowledge": []},
    )
    assert bad.status_code == 422

    good = client.patch(
        f"/api/projects/{project_id}/knowledge",
        json={
            "competitor_knowledge": [
                {
                    "competitor_id": "comp_demo",
                    "competitor_name": "Cursor",
                    "sources": ["src_demo"],
                }
            ]
        },
    )
    assert good.status_code == 200
    assert good.json()["updated_competitor_ids"] == ["comp_demo"]


def test_industry_type_round_trips_through_create_and_get(client):
    """industry_type=ecommerce should persist and be returned in GET /projects/{id}."""
    payload = {
        "industry": "E-commerce",
        "industry_type": "ecommerce",
        "competitors": [
            {"name": "Amazon", "url": "https://amazon.com"},
        ],
        "goals": ["pricing_analysis"],
    }
    create = client.post("/api/projects", json=payload)
    assert create.status_code == 200
    project_id = create.json()["project_id"]

    response = client.get(f"/api/projects/{project_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["industry_type"] == "ecommerce"


def test_analysis_purpose_and_custom_dimensions_round_trip(client):
    """analysis_purpose, custom_dimensions, and competitor role persist through create→GET."""
    payload = {
        "industry": "AI Tools",
        "analysis_purpose": "build_similar_product",
        "custom_dimensions": ["pricing transparency"],
        "competitors": [
            {"name": "Notion", "url": "https://notion.so", "role": "inspiration_product"},
        ],
        "goals": ["feature_comparison"],
    }
    create = client.post("/api/projects", json=payload)
    assert create.status_code == 200
    project_id = create.json()["project_id"]

    response = client.get(f"/api/projects/{project_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["analysis_purpose"] == "build_similar_product"
    assert body["custom_dimensions"] == ["pricing transparency"]
    assert body["competitors"][0]["role"] == "inspiration_product"


def test_legacy_analysis_purpose_normalizes_to_canonical(client):
    payload = {
        "industry": "AI Tools",
        "analysis_purpose": "choose_product",
        "competitors": [
            {"name": "Cursor", "url": "https://cursor.com"},
        ],
        "goals": ["feature_comparison"],
    }
    create = client.post("/api/projects", json=payload)
    assert create.status_code == 200
    project_id = create.json()["project_id"]

    response = client.get(f"/api/projects/{project_id}")
    assert response.status_code == 200
    assert response.json()["analysis_purpose"] == "choose_product_to_use"


def test_project_create_rejects_unknown_analysis_purpose(client):
    response = client.post(
        "/api/projects",
        json={
            "industry": "AI Tools",
            "analysis_purpose": "not_a_supported_purpose",
            "competitors": [{"name": "Cursor", "url": "https://cursor.com"}],
            "goals": ["feature_comparison"],
        },
    )
    assert response.status_code == 422


def test_competitor_extra_urls_round_trip_through_create_and_get(client):
    payload = {
        "industry": "AI Coding Tools",
        "competitors": [
            {
                "name": "Cursor",
                "url": "https://cursor.com",
                "extra_urls": [
                    "https://cursor.com/pricing",
                    "https://docs.cursor.com",
                ],
            },
        ],
        "goals": ["pricing_analysis"],
    }
    create = client.post("/api/projects", json=payload)
    assert create.status_code == 200
    project_id = create.json()["project_id"]

    response = client.get(f"/api/projects/{project_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["competitors"] == [
        {
            "name": "Cursor",
            "url": "https://cursor.com",
            "role": "direct_competitor",
            "extra_urls": [
                "https://cursor.com/pricing",
                "https://docs.cursor.com",
            ],
        }
    ]


def test_project_create_normalizes_competitor_urls_and_deduplicates(client):
    payload = {
        "industry": "AI Coding Tools",
        "competitors": [
            {"name": "Cursor", "url": "cursor.com"},
            {"name": "Cursor", "url": "https://cursor.com"},
            {"name": "Trae", "url": "www.trae.ai"},
            {"name": "Cursor Pricing", "url": "https://cursor.com/pricing"},
        ],
        "goals": ["feature_comparison"],
    }
    create = client.post("/api/projects", json=payload)
    assert create.status_code == 200
    project_id = create.json()["project_id"]

    response = client.get(f"/api/projects/{project_id}")
    assert response.status_code == 200
    assert response.json()["competitors"] == [
        {
            "name": "Cursor",
            "url": "https://cursor.com",
            "role": "direct_competitor",
            "extra_urls": [],
        },
        {
            "name": "Trae",
            "url": "https://www.trae.ai",
            "role": "direct_competitor",
            "extra_urls": [],
        },
        {
            "name": "Cursor Pricing",
            "url": "https://cursor.com/pricing",
            "role": "direct_competitor",
            "extra_urls": [],
        },
    ]


def test_project_create_rejects_empty_competitor_url(client):
    response = client.post(
        "/api/projects",
        json={
            "industry": "AI Coding Tools",
            "competitors": [{"name": "Cursor", "url": ""}],
            "goals": ["feature_comparison"],
        },
    )
    assert response.status_code == 422


def test_project_create_rejects_private_competitor_url(client):
    response = client.post(
        "/api/projects",
        json={
            "industry": "AI Coding Tools",
            "competitors": [{"name": "Local", "url": "http://127.0.0.1:8000"}],
            "goals": ["feature_comparison"],
        },
    )
    assert response.status_code == 422


def test_research_inputs_round_trip_through_create_and_get(client):
    payload = {
        "industry": "AI Coding Tools",
        "competitors": [{"name": "Cursor", "url": "https://cursor.com"}],
        "goals": ["user_personas"],
        "research_inputs": [
            {
                "title": "Developer interview notes",
                "source_kind": "interview",
                "competitor_name": "Cursor",
                "content": "Interviewees value codebase-aware chat but worry about privacy.",
            }
        ],
    }
    create = client.post("/api/projects", json=payload)
    assert create.status_code == 200
    project_id = create.json()["project_id"]

    response = client.get(f"/api/projects/{project_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["research_inputs"] == payload["research_inputs"]


def test_project_create_rejects_private_extra_url(client):
    response = client.post(
        "/api/projects",
        json={
            "industry": "AI Coding Tools",
            "competitors": [
                {
                    "name": "Cursor",
                    "url": "https://cursor.com",
                    "extra_urls": ["http://127.0.0.1:8000/admin"],
                }
            ],
            "goals": ["pricing_analysis"],
        },
    )
    assert response.status_code == 422


def test_run_project_passes_extra_urls_to_workflow(client, workflow_calls):
    create = client.post(
        "/api/projects",
        json={
            "industry": "AI Coding Tools",
            "competitors": [
                {
                    "name": "Cursor",
                    "url": "https://cursor.com",
                    "role": "direct_competitor",
                    "extra_urls": ["https://cursor.com/pricing"],
                }
            ],
            "goals": ["pricing_analysis"],
        },
    )
    assert create.status_code == 200
    project_id = create.json()["project_id"]

    response = client.post(f"/api/projects/{project_id}/run")
    assert response.status_code == 200
    assert len(workflow_calls) == 1
    args, _ = workflow_calls[0]
    competitors_payload = args[1]
    assert competitors_payload == [
        {
            "name": "Cursor",
            "url": "https://cursor.com",
            "role": "direct_competitor",
            "extra_urls": ["https://cursor.com/pricing"],
        }
    ]


def test_run_project_passes_research_inputs_to_workflow(client, workflow_calls):
    research_inputs = [
        {
            "title": "Survey summary",
            "source_kind": "survey",
            "competitor_name": "",
            "content": "Survey respondents prefer simple onboarding and transparent pricing.",
        }
    ]
    create = client.post(
        "/api/projects",
        json={
            "industry": "AI Coding Tools",
            "competitors": [{"name": "Cursor", "url": "https://cursor.com"}],
            "goals": ["user_personas"],
            "research_inputs": research_inputs,
        },
    )
    assert create.status_code == 200
    project_id = create.json()["project_id"]

    response = client.post(f"/api/projects/{project_id}/run")
    assert response.status_code == 200
    assert len(workflow_calls) == 1
    args, _ = workflow_calls[0]
    assert args[9] == research_inputs
