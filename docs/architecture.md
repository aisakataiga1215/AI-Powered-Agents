# Architecture

## 1. Overview

This document describes the system architecture of the AI-powered competitive analysis multi-agent system.

The system is designed to simulate a digital research team. Multiple runtime business Agents collaborate through a LangGraph workflow to collect public information, extract structured competitor knowledge, generate analysis, write reports, and perform quality assurance.

For product goals, see [../product_spec.md](../product_spec.md).  
For engineering details, see [../engineering_spec.md](../engineering_spec.md).  
For schema definitions, see [schema_design.md](schema_design.md).  
For Agent communication rules, see [agent_protocol.md](agent_protocol.md).

## 2. High-Level System Flow

```txt
User Input
  ↓
Project Creation
  ↓
Backend API
  ↓
LangGraph Workflow
  ↓
CollectorAgent
  ↓
AnalystAgent
  ↓
WriterAgent
  ↓
QAAgent
  ↓
Pass → Final Report
  ↓
Fail → Rework Route
  ↓
CollectorAgent / AnalystAgent / WriterAgent
```

## 3. Main Components

### 3.1 Frontend

The frontend provides the user-facing product interface.

Responsibilities:

* Create competitive analysis projects.
* Display project status.
* Visualize Agent workflow.
* Display Agent trace timeline.
* Display final report.
* Show source citation details.
* Show QA feedback and rework history.
* Support manual report correction with versioned report persistence and a `HumanReviewer` trace event.

Recommended stack:

* Next.js
* React
* TypeScript
* Tailwind CSS
* shadcn/ui
* React Flow
* TanStack Query

### 3.2 Backend API

The backend provides REST APIs and coordinates application services.

Responsibilities:

* Manage projects.
* Start Agent workflows.
* Store and return reports.
* Store and return trace logs.
* Store and return source evidence.
* Validate structured outputs.
* Handle errors and partial failures.

Recommended stack:

* FastAPI
* Pydantic
* SQLAlchemy
* PostgreSQL or SQLite for MVP

### 3.3 LangGraph Workflow

The LangGraph workflow coordinates runtime business Agents.

Responsibilities:

* Maintain workflow state.
* Execute Agent nodes.
* Route outputs between Agents.
* Trigger QA review.
* Route failed outputs back to upstream Agents.
* Finalize successful reports.

### 3.4 Runtime Business Agents

Runtime business Agents are part of the application.

They are different from Claude Code development subagents.

Runtime business Agents:

| Agent          | Responsibility                                                      |
| -------------- | ------------------------------------------------------------------- |
| CollectorAgent | Collect public information and source evidence                      |
| AnalystAgent   | Extract structured competitor knowledge and perform analysis        |
| WriterAgent    | Generate structured and human-readable reports                      |
| QAAgent        | Validate schema completeness, evidence coverage, and report quality |

#### 3.4.1 LLM Provider

The system uses the **Volcengine Doubao (火山引擎豆包)** LLM provider via an OpenAI-compatible endpoint (`https://ark.cn-beijing.volces.com/api/v3`). The endpoint supports full function calling, enabling `ChatOpenAI.with_structured_output(method="function_calling")` as the primary structured output path for both AnalystAgent and WriterAgent.

Configuration is in `.env`:
- `OPENAI_BASE_URL=https://ark.cn-beijing.volces.com/api/v3`
- `DEFAULT_MODEL=<endpoint-id>`
- `LLM_DISABLE_THINKING=false` (not needed for Doubao; defaults to `false` in `config.py`)

#### 3.4.2 Structured Output Strategy

Both AnalystAgent and WriterAgent use a **function-calling-first, JSON-fallback** pattern:

1. **Primary path**: `ChatOpenAI.with_structured_output(Schema, method="function_calling", include_raw=True)` -- returns a dict with `parsed` (Pydantic object) and `raw` (provider metadata for token usage).
2. **Fallback path**: On any exception from function calling, the agent retries with `response_format={"type": "json_object"}` and parses the JSON content manually. The `_extract_json_text()` helper strips markdown fences the model may emit.
3. **Trace observability**: `parse_status` in agent trace output records which path was used (`function_calling_parsed`, `json_output_parsed`, `json_output_fallback_empty`, or `llm_error_fallback_empty`).

### 3.5 Data Layer

The data layer stores:

* Projects
* Competitors
* Sources
* Structured competitor knowledge
* Agent runs
* QA results
* Reports

### 3.6 Trace Layer

The trace layer records:

* Agent name
* Agent input
* Agent output
* Prompt version
* Status
* Error message
* Latency
* Token usage
* Retry count
* QA feedback
* Rework target

## 4. Project Structure

The project should use the following structure:

```txt
AI-Powered-Agents/
├── .claude/
│   └── agents/
│       ├── architect.md
│       ├── backend-engineer.md
│       ├── frontend-engineer.md
│       ├── agent-workflow-engineer.md
│       ├── qa-observability-engineer.md
│       └── docs-maintainer.md
├── README.md
├── CLAUDE.md
├── product_spec.md
├── engineering_spec.md
├── pyproject.toml
├── package.json
├── .env.example
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── logging.py
│   │   │   └── errors.py
│   │   ├── api/
│   │   │   ├── deps.py
│   │   │   └── routes/
│   │   │       ├── projects.py
│   │   │       ├── reports.py
│   │   │       ├── sources.py
│   │   │       ├── traces.py
│   │   │       └── health.py
│   │   ├── agents/
│   │   │   ├── collector_agent.py
│   │   │   ├── analyst_agent.py
│   │   │   ├── writer_agent.py
│   │   │   ├── qa_agent.py
│   │   │   └── prompts/
│   │   │       ├── collector.md
│   │   │       ├── analyst.md
│   │   │       ├── writer.md
│   │   │       └── qa.md
│   │   ├── graph/
│   │   │   ├── workflow.py
│   │   │   ├── state.py
│   │   │   ├── nodes.py
│   │   │   └── routing.py
│   │   ├── schemas/
│   │   │   ├── project.py
│   │   │   ├── competitor.py
│   │   │   ├── source.py
│   │   │   ├── claim.py
│   │   │   ├── knowledge.py
│   │   │   ├── report.py
│   │   │   ├── agent_message.py
│   │   │   ├── qa.py
│   │   │   └── trace.py
│   │   ├── services/
│   │   │   ├── project_service.py
│   │   │   ├── crawler_service.py
│   │   │   ├── source_service.py
│   │   │   ├── report_service.py
│   │   │   ├── trace_service.py
│   │   │   └── qa_service.py
│   │   ├── db/
│   │   │   ├── models.py
│   │   │   ├── session.py
│   │   │   └── migrations/
│   │   └── utils/
│   │       ├── citation.py
│   │       ├── sanitizer.py
│   │       ├── retry.py
│   │       └── time.py
│   └── tests/
│       ├── test_schema_validation.py
│       ├── test_qa_rules.py
│       ├── test_workflow_routing.py
│       └── test_api_projects.py
├── frontend/
│   ├── app/
│   │   ├── page.tsx
│   │   ├── projects/
│   │   │   ├── new/
│   │   │   │   └── page.tsx
│   │   │   └── [projectId]/
│   │   │       ├── page.tsx
│   │   │       ├── report/
│   │   │       │   └── page.tsx
│   │   │       └── traces/
│   │   │           └── page.tsx
│   │   └── layout.tsx
│   ├── components/
│   │   ├── agent-flow/
│   │   │   ├── AgentFlowGraph.tsx
│   │   │   └── AgentNodeCard.tsx
│   │   ├── report-viewer/
│   │   │   ├── ReportViewer.tsx
│   │   │   ├── CitationBadge.tsx
│   │   │   └── SourceList.tsx
│   │   ├── source-viewer/
│   │   │   └── SourcePanel.tsx
│   │   ├── trace-panel/
│   │   │   ├── TraceTimeline.tsx
│   │   │   └── TraceDetail.tsx
│   │   └── qa/
│   │       └── QAResultPanel.tsx
│   ├── lib/
│   │   ├── api.ts
│   │   └── types.ts
│   └── styles/
├── docs/
│   ├── architecture.md
│   ├── changelog.md
│   ├── project_status.md
│   ├── agent_protocol.md
│   ├── schema_design.md
│   └── deployment.md
└── scripts/
    ├── seed_demo_data.py
    └── run_demo_task.py
```

## 5. Backend Module Responsibilities

### 5.1 `backend/app/api/`

Defines HTTP API routes.

Routes should be thin. They should call service functions instead of containing business logic.

### 5.2 `backend/app/agents/`

Contains runtime business Agent implementations:

* CollectorAgent
* AnalystAgent
* WriterAgent
* QAAgent

These files should not contain FastAPI route logic.

### 5.3 `backend/app/graph/`

Contains LangGraph workflow logic.

Files:

| File          | Responsibility                            |
| ------------- | ----------------------------------------- |
| `workflow.py` | Builds and exports the LangGraph workflow |
| `state.py`    | Defines shared workflow state (`WorkflowState` TypedDict, includes `industry_type: str`) |
| `nodes.py`    | Wraps Agent calls as graph nodes          |
| `routing.py`  | Defines conditional routing after QA      |

### 5.4 `backend/app/schemas/`

Contains Pydantic schemas.

Schema definitions should follow [schema_design.md](schema_design.md).

### 5.5 `backend/app/services/`

Contains application services:

| Service                  | Responsibility                                                                                |
| ------------------------ | --------------------------------------------------------------------------------------------- |
| `project_service.py`     | Project creation, status updates                                                              |
| `crawler_service.py`     | Public data collection (httpx + BeautifulSoup, 10s timeout, robots.txt best-effort)           |
| `source_discovery.py`    | Probes industry-specific candidate URL paths on the competitor root domain. **Not a web crawler** — constructs known path variants (e.g. `/pricing`, `/seller-fees`) and probes them directly. No sitemap parsing, link following, or search-engine discovery. Industry-keyed path sets: `ai_saas` (10 paths, max 5 pages), `ecommerce` (14 paths, max 8 pages), `local_services` (12 paths, max 8 pages), `general` (6 paths, max 5 pages). `industry_type` is set per project at creation and threads through the workflow to CollectorAgent. Public helper `get_industry_max_pages(industry_type)` exposed for `CollectorAgent`. |
| `search_provider.py`     | `SearchProvider` Protocol + `TavilySearchProvider` (wraps Tavily SDK) + `NullSearchProvider` (no-op) + `create_search_provider()` factory. Active when `ENABLE_LIVE_SEARCH=true` and `TAVILY_API_KEY` is set; degrades to `NullSearchProvider` otherwise. |
| `search_service.py`      | Industry-keyed web search query templates -> URL discovery via `SearchProvider` -> `_is_crawlable()` filter (`_BLOCKED_DOMAINS` covers youtube/twitter/reddit/linkedin; `_UNSUPPORTED_EXTENSIONS` blocks binary files) -> `_SEARCH_MAX_URLS=5` cap. Acts as a second URL-discovery channel alongside `source_discovery` inside `CollectorAgent._collect_live()`. Tavily title/snippet are discovery-only -- never stored as evidence. Exposes three methods: `discover_urls()` for silent background discovery (workflow; accepts optional `rework_hints` to prepend targeted queries via `_build_hint_queries()` which maps hint keywords like "pricing"/"features"/"docs" to specific Tavily search templates), `search_sources()` for interactive per-competitor candidate search (used by `POST /api/search/sources`) returning `CandidateSource` items annotated with `suggested_source_type`/`confidence`/`reason`, and `discover_competitors()` for industry-driven candidate-competitor discovery (used by `POST /api/search/competitors`) returning `CandidateCompetitor` items with provenance + relevance score. Aggregator/listicle/news domains are excluded via `_DISCOVERY_BLOCKED_DOMAINS` and `_LISTICLE_TITLE_RE`. |
| `source_classifier.py`   | URL-path-first keyword classifier mapping discovered pages to `SourceType` (`features_page`, `security`, `privacy`, `unknown`, etc.) |
| `coverage_evaluator.py`  | Per-competitor source coverage scoring (homepage/pricing/features/security weights, `WEAK_THRESHOLD=40`). Drives QA coverage checks. |
| `source_service.py`      | Source storage and retrieval                                                                  |
| `report_service.py`      | Report generation and retrieval                                                               |
| `trace_service.py`       | Agent trace logging                                                                           |
| `qa_service.py`          | Rule-based QA validation                                                                      |

### 5.6 `backend/app/db/`

Contains database models and sessions.

### 5.7 `backend/tests/`

Contains backend tests.

MVP test priorities:

* Schema validation
* QA rule validation
* Workflow routing
* API response shape

## 6. Frontend Module Responsibilities

### 6.1 `frontend/app/`

Contains Next.js routes.

Core pages:

| Page                           | Responsibility             |
| ------------------------------ | -------------------------- |
| `/`                            | Landing or project list    |
| `/projects/new`                | Create analysis project    |
| `/projects/[projectId]`        | Project execution overview |
| `/projects/[projectId]/report` | Report viewer              |
| `/projects/[projectId]/traces` | Agent trace viewer         |

### 6.2 `frontend/components/agent-flow/`

Displays the Agent DAG and execution status.

### 6.3 `frontend/components/report-viewer/`

Displays report sections, citations, and source list.

### 6.4 `frontend/components/source-viewer/`

Displays original source details when a citation is clicked.

### 6.5 `frontend/components/trace-panel/`

Displays Agent input, output, prompt, token usage, latency, and retry history.

### 6.6 `frontend/components/qa/`

Displays QAAgent results and rework decisions.

### 6.7 `frontend/components/search/`

Interactive source search UI. `CandidateSourcePanel.tsx` lets the user pick per-competitor `CandidateSource` URLs (M15A); selected URLs are submitted as `CompetitorInput.extra_urls`.

### 6.8 `frontend/components/competitor/`

Competitor discovery UI. `CompetitorDiscoveryPanel.tsx` (M15B) calls `POST /api/search/competitors` for the project's industry/topic, displays `CandidateCompetitor` items with relevance score and suggested role, and pushes selected candidates into the form's competitor list.

## 7. Runtime Workflow

### 7.1 MVP Workflow

```txt
start
  ↓
collect_sources
  ↓
analyze_competitors
  ↓
write_report
  ↓
qa_review
  ↓
conditional route
    ├── pass → finalize_report
    └── fail → rework
```

### 7.2 Rework Routing

QAAgent can route failed outputs to:

| Failure Type                | Target Agent   |
| --------------------------- | -------------- |
| Missing source              | CollectorAgent |
| Missing pricing data        | CollectorAgent |
| Invalid structured analysis | AnalystAgent   |
| SWOT lacks evidence         | AnalystAgent   |
| Report section missing      | WriterAgent    |
| Citation missing in report  | WriterAgent    |

### 7.3 Rework Limit

To avoid infinite loops, MVP should set a maximum rework count.

Recommended MVP value:

```txt
max_rework_attempts = 2
```

If the workflow still fails after the limit, the project status should become:

```txt
qa_failed
```

The frontend should show the partial result and QA issues.

## 8. Data Model Overview

MVP database tables:

| Table                  | Purpose                        |
| ---------------------- | ------------------------------ |
| `projects`             | Analysis tasks                 |
| `competitors`          | Competitors in each project    |
| `sources`              | Collected source evidence      |
| `competitor_knowledge` | Structured extracted knowledge |
| `agent_runs`           | Agent execution records        |
| `qa_results`           | QA validation results          |
| `reports`              | Final or partial reports       |

## 9. API Overview

Core MVP APIs:

| Method | Path                                   | Purpose                               |
| ------ | -------------------------------------- | ------------------------------------- |
| POST   | `/api/projects`                        | Create project                        |
| POST   | `/api/projects/{project_id}/run`       | Start analysis                        |
| GET    | `/api/projects/{project_id}`           | Get project status                    |
| GET    | `/api/projects/{project_id}/traces`    | Get Agent traces                      |
| GET    | `/api/projects/{project_id}/report`    | Get report                            |
| GET    | `/api/sources/{source_id}`             | Get source detail                     |
| POST   | `/api/search/sources`                  | Interactive per-competitor candidate URL search (returns `list[CandidateSource]`; requires `ENABLE_LIVE_SEARCH=true` and `TAVILY_API_KEY`) |
| POST   | `/api/search/competitors`              | Industry-driven competitor discovery (accepts `{ industry, industry_type }`, returns `list[CandidateCompetitor]`; requires `ENABLE_LIVE_SEARCH=true` and `TAVILY_API_KEY`) |
| PATCH  | `/api/projects/{project_id}/knowledge` | Manually correct structured knowledge |
| GET    | `/api/graph`                           | Export the compiled LangGraph DAG for the frontend workflow view |
| GET    | `/api/metrics`                         | Aggregate AgentRun token usage and estimated cost by agent, project, and day |

## 10. Traceability Design

Each important report claim should point to one or more `source_id`.

Example:

```json
{
  "claim": "Cursor uses a freemium pricing model.",
  "evidence": ["source_cursor_pricing_001"]
}
```

The frontend should allow the user to click the citation and inspect:

* URL
* Page title
* Retrieved time
* Original snippet
* Related claim

## 11. Observability Design

Each Agent run should be stored as an `agent_runs` record.

Required fields:

```json
{
  "agent_run_id": "string",
  "project_id": "string",
  "agent_name": "CollectorAgent",
  "input": {},
  "output": {},
  "status": "success | failed | skipped",
  "error_message": null,
  "latency_ms": 1200,
  "token_usage": {
    "prompt_tokens": 1000,
    "completion_tokens": 500,
    "total_tokens": 1500
  },
  "retry_count": 0,
  "created_at": "string"
}
```

## 12. Demo Mode

The system should support two modes:

### 12.1 Real Mode

Uses live crawling and LLM calls.

### 12.2 Cached Demo Mode

Uses pre-collected source data and deterministic mock outputs.

Cached demo mode is required for competition stability.

Suggested files:

```txt
scripts/seed_demo_data.py
scripts/run_demo_task.py
```

## 13. Development Assistance

This project may include Claude Code development subagents under:

```txt
.claude/agents/
```

These are development helpers, not runtime business Agents.

Development subagent rules are described in [../CLAUDE.md](../CLAUDE.md).

## 14. Update Rules

Update this document when:

* Project structure changes.
* Runtime Agent workflow changes.
* Backend module boundaries change.
* Frontend page structure changes.
* Database design changes.
* API structure changes.
