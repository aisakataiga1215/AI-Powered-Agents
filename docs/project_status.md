# Project Status

**Last updated:** 2026-06-02

## Current Status: Deterministic Markdown Renderer Complete

---

## Milestones

### Milestone 1: Project Setup ✅ COMPLETE

- Repository structure created
- FastAPI backend set up
- Base documentation added
- Environment variables configured
- Initial Pydantic schemas added
- Runtime business agent skeletons added

### Milestone 2: Schema Design ✅ COMPLETE

- Competitor knowledge schema (`CompetitorKnowledge`, `ProductProfile`, `FeatureItem`, etc.)
- Source evidence schema (`SourceEvidence`, `SourceType`, `Reliability`)
- Claim schema (`Claim`, `ConfidenceLevel`)
- Agent message schema (`AgentMessage`, `MessageType`)
- QA result schema (`QAResult`, `QAIssue`, `IssueSeverity`)
- Report schema (`CompetitiveReport`)
- Raw extraction schema (`RawCompetitorExtraction`) for two-stage LLM pipeline
- All schemas documented in `docs/schema_design.md`

### Milestone 3: Basic Agent Workflow ✅ COMPLETE

- [x] CollectorAgent (demo fixtures for Cursor, Trae, Windsurf)
- [x] AnalystAgent (two-stage extraction: RawCompetitorExtraction → normalization_service → CompetitorKnowledge)
- [x] WriterAgent (deterministic pricing + feature tables; inline `[src_xxx]` citations in markdown)
- [x] QAAgent (rule-based checks, rework routing)
- [x] LangGraph workflow with rework loop
- [x] Retry and routing logic (MAX_REPAIR_LOOPS)
- [x] QAAgent rejects outputs with missing citations, missing pricing, missing required fields

### Milestone 4: Traceability and Observability ✅ COMPLETE

- [x] Agent inputs and outputs stored (AgentRun table)
- [x] Source references stored (Source table)
- [x] Agent execution status stored
- [x] QA feedback stored (QAResult table)
- [x] Retry and rework records stored
- [x] Token usage captured for AnalystAgent and WriterAgent
- [x] Agent trace timeline displayed in frontend (TraceTimeline + AgentRunCard)

### Milestone 5: Report Viewer ✅ COMPLETE

- [x] Report rendered in frontend (7-tab layout: Summary, Pricing, Features, SWOT, Recommendations, Markdown, QA Result)
- [x] FeatureComparisonTable: matrix table with competitors as columns, feature categories as rows
- [x] Citation click behavior: numbered `[N]` badges in ClaimList and `[src_xxx]` badges in MarkdownTab
- [x] Source inspection panel: slide-in SourcePanel with full source detail

### Milestone 6: Demo Scenario ✅ COMPLETE

- [x] AI coding tools demo case (Cursor / Trae / Windsurf)
- [x] Demo fixtures (no network needed)
- [x] Real DeepSeek LLM workflow runs end-to-end
- [x] Status `completed`, QA passes first attempt
- [x] Frontend demo flow: create project → run workflow → view traces → view report → click citations

---

## Component Status

| Component | Status |
|-----------|--------|
| FastAPI backend | ✅ Complete |
| SQLite database | ✅ Complete |
| CollectorAgent (demo fixtures) | ✅ Complete |
| AnalystAgent (two-stage extraction) | ✅ Complete |
| WriterAgent (deterministic markdown renderer, stable [^src_xxx] citations) | ✅ Complete |
| output_language wired EN/ZH through full stack | ✅ Complete |
| 152 passing tests | ✅ Complete |
| Real DeepSeek LLM workflow end-to-end | ✅ Complete |
| Token usage tracking | ✅ Complete |
| Next.js frontend (4 pages) | ✅ Complete |
| Report viewer UI (7 tabs) | ✅ Complete |
| Agent trace timeline UI | ✅ Complete |
| Source citation side panel | ✅ Complete |
| AgentDAG visualization (React Flow) | ✅ Complete |

---

## Current Focus

v1 polish. The MVP is usable end-to-end; next focus is quality and reliability improvements.

## Next Steps (v1)

1. Add frontend automated tests (Playwright E2E for the golden path)
2. Add real web crawling via CollectorAgent (replace demo fixtures with live data)
3. Improve `user_personas` (needs/pain_points currently empty when LLM omits them)
4. Add project title field to creation form (currently shows project_id in listings)
5. Pagination on projects list page (currently unbounded)
6. Add PostgreSQL support as an alternative to SQLite
7. Improve MarkdownTab prose styling (code blocks, tables, lists)

---

## Known Limitations (Not Blocking MVP)

- `user_personas` needs/pain_points are empty stubs when LLM omits them
- No real web crawling (demo fixtures only)
- Single-user, no auth
- SQLite only (no PostgreSQL)
- No frontend automated tests

---

## Risks

### Risk 1: Web data collection instability

Mitigation: Use fallback demo data. Store source snapshots. Allow manual source input.

### Risk 2: LLM output format instability

Mitigation: Two-stage extraction pipeline (RawCompetitorExtraction → normalization_service). StrList coercion for list/string quirks. Rule-based QA rejects malformed outputs.

### Risk 3: QA feedback loop becomes fake

Mitigation: Rule-based QA checks implemented. Deterministic pricing/feature overrides prevent LLM from contradicting structured data. Rework routing tested with integration tests.

### Risk 4: Demo latency too high

Mitigation: ENABLE_DEMO_FIXTURES=true for offline dev. DeepSeek API significantly cheaper than OpenAI for live runs.
