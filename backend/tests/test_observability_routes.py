"""Tests for workflow graph and metrics observability routes."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    from app.api import deps
    from app.db import models, session as db_session
    from app.main import app
    import app.main as main_module

    monkeypatch.setattr(db_session, "engine", engine)
    monkeypatch.setattr(db_session, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(main_module, "engine", engine)
    models.Base.metadata.create_all(bind=engine)

    def override_session():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[deps.get_session] = override_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def test_graph_route_registered(client):
    response = client.get("/api/graph")
    assert response.status_code == 200
    body = response.json()
    assert "nodes" in body
    assert "edges" in body
    node_ids = {node["id"] for node in body["nodes"]}
    assert "collect_sources" in node_ids
    assert "qa_review" in node_ids


def test_metrics_route_registered(client):
    response = client.get("/api/metrics")
    assert response.status_code == 200
    body = response.json()
    assert "total_cost_usd" in body
    assert "total_tokens" in body
    assert "run_count" in body
    assert "by_agent" in body
