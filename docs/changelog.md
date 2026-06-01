# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] — Frontend MVP

### Added

- **Pages**: project creation (`/`), projects list (`/projects`), workflow execution + polling (`/projects/[id]`), report viewer (`/projects/[id]/report`), agent trace timeline (`/projects/[id]/traces`)
- **AgentDAG**: React Flow visualization with custom rework arcs; rework/pass labels are data-driven from trace output — only shown when traces confirm those paths were taken
- **FeatureComparisonTable**: parses `"Category: F1, F2 | Cat2: F3"` strings into a matrix table (competitors = columns, feature categories = rows)
- **ClaimList**: numbered `[N]` citation badges (mapped to `source_list` index) that open the source panel on click; falls back to source ID when no index available
- **MarkdownTab**: ReactMarkdown renderer with `[src_xxxxxxxx]` → `[[N]](cite:…)` pre-processing; clicking any badge opens the source panel
- **SourcePanel**: slide-in drawer; loads full source via `GET /api/sources/{id}`; shows title, URL, reliability, snippet, and collapsible full content
- **TraceTimeline + AgentRunCard**: agent execution timeline with status, latency, token usage, and expandable I/O
- **QAResultBanner**: passed/failed, score, per-issue severity + suggested action
- **SWOTView, ComparisonCards, TabsBar, AgentStatusBadge**: supporting report components
- **TanStack Query polling**: 3-second refetch on `/projects/[id]` while `status === 'running'`
- **Zustand source panel store**: shared `openSource` / `closeSource` state across all tabs and components

### Fixed

- CORS: changed from `allow_origins=["*"]` + `allow_credentials=True` (browser-rejected) to explicit origins + `allow_credentials=False`
- `writer.md` system prompt now requires `[src_xxxxxxxx]` inline citations in `markdown_content`; new workflow runs will have clickable inline citations

### Tests

- Backend: 142 tests unchanged, all passing
- Frontend automated tests deferred to v1

---

## [Unreleased] — Backend Hardening Pass

### Added

- `_build_pricing_comparison()` and `_build_pricing_markdown()` in WriterAgent — deterministic rendering from `pricing_model.plans`
- `_build_feature_comparison()` in WriterAgent — deterministic rendering from `feature_tree`
- `_typed_source_ids()` in normalization_service — routes evidence to type-appropriate sources (pricing → pricing_page, features → official_website/docs, feedback → review)
- `sources` parameter to `normalization_service.normalize()` for typed evidence routing
- User persona fallback: derive from `target_users` when LLM omits `user_personas`
- Token usage capture in AnalystAgent (cumulative across competitors) and WriterAgent
- `competitor_id` slug set on all SourceEvidence by CollectorAgent
- 15 new regression tests (pricing consistency, source competitor_id, persona fallback, evidence alignment)
- `docs/handoff_frontend_mvp.md`

### Fixed

- WriterAgent `_bind_report_fields` now always overwrites `competitor_overview` with analyst's structured knowledge — prevents QA false positives from LLM-invented prices in the report's competitor profiles
- `check_pricing_consistency` no longer fires when deterministic pricing_comparison matches pricing_model.plans
- Feature availability contradictions eliminated (Trae Builder Mode no longer shown as "none")

### Tests

- 127 → 142 tests, all passing
- Real DeepSeek workflow: status `completed`, QA passes first attempt

---

## [Unreleased] — Backend + Agents MVP

### Added

- Initial project planning.
- Defined MVP, v1, v2, and future phases.
- Added product specification.
- Added engineering specification.
- Added initial architecture documentation.
- Added Claude Code collaboration guide.
- Implemented CollectorAgent, AnalystAgent, WriterAgent, and QAAgent business agents.
- Implemented LangGraph workflow with deterministic source collection, analysis, writing, QA review, and rework routing.
- Added rule-based QA checks for required sections, evidence coverage, pricing presence, and feature trees.
- Added rework loop with upstream-first agent prioritization and bounded retry via `max_repair_loops`.
- Added prompt files for Analyst, Writer, and QA agents under `backend/app/agents/prompts/`.
- Added unit and integration tests for QA rules, routing helpers, collector, and prompt builders.

### Changed

- Clarified the distinction between Claude Code development subagents and runtime business Agents.

### Fixed

- N/A
