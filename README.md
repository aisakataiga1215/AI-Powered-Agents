---
title: AI-Powered Competitive Analysis Agents
emoji: 🤖
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
short_description: Multi-agent competitive analysis (FastAPI + LangGraph)
---

# AI-Powered Competitive Analysis Agents

Multi-agent system that researches competitors, generates structured analysis, and produces traceable reports via a LangGraph DAG workflow.

## Live Demo

| Surface | URL |
|---------|-----|
| Frontend (Vercel) | https://ai-powered-agents.vercel.app/ |
| Backend (Hugging Face Space) | https://aisakamai-ai-powered-agents.hf.space |
| Backend API docs | https://aisakamai-ai-powered-agents.hf.space/docs |
| Backend health check | https://aisakamai-ai-powered-agents.hf.space/api/health |

> The HF Space free tier sleeps after ~48h of inactivity. First request may take 30–60s to wake.

## Architecture

```
Next.js Frontend (port 3000 dev / Vercel prod)
  ↓
FastAPI Backend (port 8000 dev / HF Space port 7860 prod)
  ↓
LangGraph: CollectorAgent → AnalystAgent → WriterAgent → QAAgent
  ↓
SQLite (dev / HF Space ephemeral) / PostgreSQL (prod recommended)
```

---

## Prerequisites

| Tool | Version |
|------|---------|
| Python | ≥ 3.11 |
| Node.js | ≥ 18 |
| npm | ≥ 9 |

Python interpreter used in this project: `E:\miniforge\envs\common\python.exe`

---

## Quick Start

### 1. Clone and configure environment

```bash
git clone <repo-url>
cd AI-Powered-Agents

# Copy and edit environment config (stays at project root)
cp .env.example .env
```

Open `.env` and fill in the required values (see [Environment Variables](#environment-variables) below).

### 2. Start the backend

```bash
cd backend
E:\miniforge\envs\common\python.exe -m pip install -e .
E:\miniforge\envs\common\python.exe -m uvicorn app.main:app --reload --port 8000
```

Backend API docs: http://localhost:8000/docs

### 3. Start the frontend

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

App: http://localhost:3000

---

## Environment Variables

Key variables in `.env` (project root — backend reads it from there):

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | LLM calls (AnalystAgent, WriterAgent) |
| `OPENAI_BASE_URL` | No | Override for OpenAI-compatible providers (e.g. DeepSeek: `https://api.deepseek.com`) |
| `DEFAULT_MODEL` | No | Default: `deepseek-v4-flash`. Options: `gpt-4.1-mini`, `gpt-4o`, `deepseek-v4-flash`, `deepseek-v4-pro` |
| `LLM_DISABLE_THINKING` | No | Set `true` for models that enable thinking by default (e.g. `deepseek-v4-pro`) |
| `DATABASE_URL` | No | Default: `sqlite:///./dev.db` |
| `ENABLE_DEMO_FIXTURES` | No | `true` = use local fixtures, no network calls (default) |
| `ENABLE_LIVE_SEARCH` | No | `true` = live web crawling |
| `TAVILY_API_KEY` | No | Required when `ENABLE_LIVE_SEARCH=true` for extra URL discovery |
| `LANGSMITH_TRACING` | No | `true` = upload traces to LangSmith |
| `LANGSMITH_API_KEY` | No | LangSmith API key |
| `FRONTEND_ORIGINS` | No | Comma-separated CORS allow-list. Defaults to `*` for the demo |

### Frontend env

Create `frontend/.env.local`:

```ini
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

---

## Deployment

The repo is wired up for a zero-cost demo deployment.

| Component | Platform | Notes |
|-----------|----------|-------|
| Backend | Hugging Face Space (Docker SDK) | Uses root `Dockerfile`, listens on port `7860`, SQLite is ephemeral on free tier |
| Frontend | Vercel | Set **Root Directory** to `frontend` when importing the repo |

### Backend → Hugging Face Space

1. Create a new Space with **SDK = Docker**, **Template = Blank**.
2. Add the Space as a git remote and force-push the repo:

   ```bash
   git remote add space https://huggingface.co/spaces/<owner>/<name>
   git -c http.version=HTTP/1.1 push -f space main
   ```

3. In the Space → **Settings → Variables and secrets**, add:
   `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `DEFAULT_MODEL`, `TAVILY_API_KEY`,
   `LANGSMITH_API_KEY`, `LANGSMITH_TRACING`, `ENABLE_DEMO_FIXTURES`,
   and (optionally) `FRONTEND_ORIGINS` to lock CORS down to the Vercel domain.

### Frontend → Vercel

1. Import the GitHub repo at https://vercel.com/new.
2. **Root Directory** → `frontend` (Framework is auto-detected as Next.js).
3. Add environment variable `NEXT_PUBLIC_API_BASE_URL` = your HF Space URL,
   e.g. `https://aisakamai-ai-powered-agents.hf.space`.

---

## Data Modes

| Mode | Config | Behavior |
|------|--------|----------|
| Demo | `ENABLE_DEMO_FIXTURES=true` | Reads from `scripts/demo_fixtures/*.json`, no network |
| Live (crawl only) | `ENABLE_DEMO_FIXTURES=false`, `ENABLE_LIVE_SEARCH=false` | Crawls known paths on competitor domains |
| Live + Search | `ENABLE_LIVE_SEARCH=true`, `TAVILY_API_KEY=<key>` | Crawl + Tavily web search for additional URL discovery |

---

## Running Tests

```bash
cd backend
E:\miniforge\envs\common\python.exe -m pytest
```

With coverage:

```bash
E:\miniforge\envs\common\python.exe -m pytest --cov=app --cov-report=term-missing
```

---

## Project Structure

```
backend/
  app/
    agents/          # CollectorAgent, AnalystAgent, WriterAgent, QAAgent
    services/        # crawler, search_provider, search_service, source_discovery
    schemas/         # Pydantic models
    core/            # config, logging
    api/             # FastAPI routes
  tests/
frontend/
  app/               # Next.js pages
  components/        # UI components (report viewer, source panel, trace panel)
  lib/               # types, API client
docs/
  architecture.md
  changelog.md
  project_status.md
scripts/
  demo_fixtures/     # Static JSON data for demo mode
```

---

## Docs

- [Architecture](docs/architecture.md)
- [Changelog](docs/changelog.md)
- [Project Status](docs/project_status.md)
- [Engineering Spec](engineering_spec.md)
- [Product Spec](product_spec.md)
