#!/usr/bin/env python3
"""
Seed demo data for the AI Coding Tools competitive analysis scenario.
Usage: python scripts/seed_demo_data.py --project-id <project_id>
"""
import argparse
import json
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

def load_fixtures(competitor: str) -> list[dict]:
    fixture_file = Path(__file__).parent / "demo_fixtures" / f"{competitor.lower()}_sources.json"
    if not fixture_file.exists():
        print(f"Warning: fixture file not found: {fixture_file}")
        return []
    with open(fixture_file) as f:
        return json.load(f)

def seed_project(project_id: str) -> None:
    from app.db.session import SessionLocal
    from app.db.models import Source
    import uuid

    db = SessionLocal()
    try:
        for competitor in ["cursor", "trae", "windsurf"]:
            sources = load_fixtures(competitor)
            for s in sources:
                s["project_id"] = project_id
                existing = db.query(Source).filter_by(id=s["source_id"]).first()
                if not existing:
                    db.add(Source(
                        id=s["source_id"],
                        project_id=project_id,
                        competitor_id=s.get("competitor_id", ""),
                        competitor_name=s["competitor_name"],
                        source_type=s["source_type"],
                        url=s["url"],
                        title=s["title"],
                        snippet=s.get("snippet", ""),
                        content=s.get("content", ""),
                        retrieved_at=s.get("retrieved_at", ""),
                        reliability=s.get("reliability", "medium"),
                    ))
        db.commit()
        print(f"Seeded demo sources for project {project_id}")
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    args = parser.parse_args()
    seed_project(args.project_id)
